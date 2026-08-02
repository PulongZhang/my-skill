from __future__ import annotations

import math
import shutil
from dataclasses import dataclass
from pathlib import Path

import numpy as np

from .audio_io import AudioProcessingError, find_executable, run_command


class TempoStretchError(RuntimeError):
    """Raised when a pitch-preserving time stretch cannot be performed safely."""


@dataclass(frozen=True)
class TimeMap:
    frame_pairs: tuple[tuple[int, int], ...]
    output_duration_seconds: float
    anchor_output_seconds: float
    anchor_stride_beats: int
    predicted_p50_ms: float
    predicted_p95_ms: float
    estimated_end_drift_ms: float
    local_tempo_ratio_min: float
    local_tempo_ratio_max: float


@dataclass(frozen=True)
class _TimeMapCandidate:
    source_points: np.ndarray
    target_points: np.ndarray
    stride: int
    predicted_p50_ms: float
    predicted_p95_ms: float
    estimated_end_drift_ms: float


def choose_engine(requested: str, strict: bool) -> str:
    requested = requested.lower()
    if requested not in {"auto", "rubberband", "ffmpeg"}:
        raise TempoStretchError(f"Unsupported stretch engine: {requested}")

    if requested in {"auto", "rubberband"} and find_executable("rubberband"):
        return "rubberband"
    if requested == "rubberband":
        raise TempoStretchError("Rubber Band CLI was requested but was not found on PATH")
    if strict:
        raise TempoStretchError(
            "Strict tempo-map mode requires Rubber Band CLI; FFmpeg atempo only supports global stretching"
        )
    if requested in {"auto", "ffmpeg"} and find_executable("ffmpeg"):
        return "ffmpeg-atempo"
    if requested == "ffmpeg":
        raise TempoStretchError("FFmpeg was requested but was not found on PATH")
    raise TempoStretchError(
        "No supported pitch-preserving stretch engine was found. Install Rubber Band CLI "
        "for the preferred vocal-quality path or FFmpeg for stable-tempo fallback."
    )


def _monotonic_beat_ordinals(
    beat_times: np.ndarray,
    anchor_seconds: float,
    source_bpm: float,
    tolerance_beats: float = 0.5,
) -> np.ndarray:
    """Number beats monotonically using a local phase estimate around the anchor."""
    beats = np.asarray(beat_times, dtype=np.float64)
    if beats.size == 0:
        return np.zeros(0, dtype=np.int64)
    if source_bpm <= 0 or not np.isfinite(source_bpm):
        raise TempoStretchError("Source BPM must be positive and finite")
    anchor_index = int(np.argmin(np.abs(beats - anchor_seconds)))
    beat_period = 60.0 / source_bpm
    tolerance = max(0.0, float(tolerance_beats))

    ordinals = np.zeros(beats.size, dtype=np.int64)
    ordinals[anchor_index] = 0
    previous_ordinal = 0
    for index in range(anchor_index + 1, beats.size):
        elapsed = beats[index] - beats[index - 1]
        estimate = elapsed / beat_period
        step = int(round(estimate))
        if abs(estimate - step) > tolerance:
            step = 1
        candidate = max(step, 1) + previous_ordinal
        ordinals[index] = candidate
        previous_ordinal = candidate
    previous_ordinal = 0
    for index in range(anchor_index - 1, -1, -1):
        elapsed = beats[index + 1] - beats[index]
        estimate = elapsed / beat_period
        step = int(round(estimate))
        if abs(estimate - step) > tolerance:
            step = 1
        candidate = previous_ordinal - max(step, 1)
        ordinals[index] = candidate
        previous_ordinal = candidate
    return ordinals


def _mapping_errors(
    beat_times: np.ndarray,
    beat_targets: np.ndarray,
    source_points: np.ndarray,
    target_points: np.ndarray,
) -> tuple[float, float, float]:
    predicted = np.interp(beat_times, source_points, target_points)
    errors_ms = np.abs(predicted - beat_targets) * 1000.0
    drift_ms = abs(
        (predicted[-1] - beat_targets[-1]) - (predicted[0] - beat_targets[0])
    ) * 1000.0
    return (
        float(np.percentile(errors_ms, 50)),
        float(np.percentile(errors_ms, 95)),
        float(drift_ms),
    )


def _frame_pairs(
    selected_source: np.ndarray,
    selected_target: np.ndarray,
    sample_rate: int,
) -> tuple[tuple[int, int], ...]:
    pairs: list[tuple[int, int]] = []
    for source_time, target_time in zip(selected_source, selected_target, strict=True):
        source_frame = int(round(float(source_time) * sample_rate))
        target_frame = int(round(float(target_time) * sample_rate))
        if source_frame <= 0 or target_frame <= 0:
            continue
        if pairs and (source_frame <= pairs[-1][0] or target_frame <= pairs[-1][1]):
            raise TempoStretchError("Rubber Band time-map frames must be strictly increasing")
        pairs.append((source_frame, target_frame))
    if not pairs:
        raise TempoStretchError("Time map has no nonzero landmarks")
    return tuple(pairs)


def build_time_map(
    beat_times: np.ndarray,
    source_bpm: float,
    target_bpm: float,
    anchor_input_seconds: float,
    source_duration_seconds: float,
    sample_rate: int,
    max_local_tempo_change: float = 0.20,
    alignment_threshold_ms: float = 30.0,
    beat_ordinals: np.ndarray | None = None,
) -> TimeMap:
    beats = np.asarray(beat_times, dtype=np.float64)
    if beats.ndim != 1 or beats.size < 8:
        raise TempoStretchError("At least 8 ordered beat times are required for a time map")
    if np.any(np.diff(beats) <= 0):
        raise TempoStretchError("Beat times must be strictly increasing")
    if source_duration_seconds <= 0 or sample_rate <= 0:
        raise TempoStretchError("Source duration and sample rate must be positive")
    if not 0 <= anchor_input_seconds <= source_duration_seconds:
        raise TempoStretchError("Time-map anchor must be inside the source duration")

    if beat_ordinals is None:
        ordinals = _monotonic_beat_ordinals(
            beats, anchor_input_seconds, source_bpm, tolerance_beats=0.5
        )
    else:
        ordinals = np.asarray(beat_ordinals, dtype=np.int64)
        if ordinals.shape != beats.shape:
            raise TempoStretchError("Beat times and beat ordinals must have equal shape")
        if np.any(np.diff(ordinals) <= 0):
            raise TempoStretchError("Beat ordinals must be strictly increasing")

    stretch_ratio = target_bpm / source_bpm
    if not np.isfinite(stretch_ratio) or stretch_ratio <= 0:
        raise TempoStretchError("Tempo ratio must be positive and finite")
    output_duration = source_duration_seconds / stretch_ratio
    anchor_output = anchor_input_seconds / stretch_ratio
    beat_targets = anchor_output + ordinals.astype(np.float64) * 60.0 / target_bpm

    selected: _TimeMapCandidate | None = None
    for stride in (4, 2, 1):
        mask = np.mod(ordinals, stride) == 0
        mask[-1] = True
        selected_source = beats[mask]
        selected_ordinals = ordinals[mask]

        # The manual/authoritative anchor replaces any automatic ordinal-zero
        # observation. Keeping both would map two source times to one target.
        nonzero = selected_ordinals != 0
        selected_source = selected_source[nonzero]
        selected_ordinals = selected_ordinals[nonzero]
        selected_source = np.append(selected_source, anchor_input_seconds)
        selected_ordinals = np.append(selected_ordinals, 0)

        target_for_selected = anchor_output + selected_ordinals.astype(np.float64) * (
            60.0 / target_bpm
        )
        order = np.argsort(selected_source)
        source_points = selected_source[order]
        target_points = target_for_selected[order]
        keep = np.concatenate(([True], np.diff(source_points) > 0.5 / sample_rate))
        source_points = source_points[keep]
        target_points = target_points[keep]

        if source_points[-1] < source_duration_seconds - 0.5 / sample_rate:
            source_points = np.append(source_points, source_duration_seconds)
            target_points = np.append(target_points, output_duration)
        else:
            source_points[-1] = source_duration_seconds
            target_points[-1] = output_duration

        positive = (source_points > 0) & (target_points > 0)
        source_points = source_points[positive]
        target_points = target_points[positive]
        if source_points.size < 2 or np.any(np.diff(target_points) <= 0):
            continue

        prediction_sources = np.concatenate(([0.0], source_points))
        prediction_targets = np.concatenate(([0.0], target_points))
        p50, p95, drift = _mapping_errors(
            beats, beat_targets, prediction_sources, prediction_targets
        )
        selected = _TimeMapCandidate(
            source_points=source_points,
            target_points=target_points,
            stride=stride,
            predicted_p50_ms=p50,
            predicted_p95_ms=p95,
            estimated_end_drift_ms=drift,
        )
        if p95 <= alignment_threshold_ms:
            break

    if selected is None:
        raise TempoStretchError("Could not construct a monotonic beat time map")

    source_points = selected.source_points
    target_points = selected.target_points
    stride = selected.stride
    p50 = selected.predicted_p50_ms
    p95 = selected.predicted_p95_ms
    drift = selected.estimated_end_drift_ms
    source_deltas = np.diff(np.concatenate(([0.0], source_points)))
    target_deltas = np.diff(np.concatenate(([0.0], target_points)))
    if np.any(target_deltas <= 0):
        raise TempoStretchError("Time-map target landmarks must be strictly increasing")
    local_ratios = source_deltas / target_deltas
    minimum = float(np.min(local_ratios))
    maximum = float(np.max(local_ratios))
    lower = 1.0 - max_local_tempo_change
    upper = 1.0 + max_local_tempo_change
    if minimum < lower or maximum > upper:
        raise TempoStretchError(
            "The strict time map requires local tempo ratios outside the configured "
            f"safe range {lower:.3f}..{upper:.3f}: observed {minimum:.3f}..{maximum:.3f}"
        )
    if p95 > alignment_threshold_ms:
        raise TempoStretchError(
            f"Even one-beat time-map anchors predict P95 alignment error {p95:.1f} ms"
        )

    return TimeMap(
        frame_pairs=_frame_pairs(source_points, target_points, sample_rate),
        output_duration_seconds=output_duration,
        anchor_output_seconds=anchor_output,
        anchor_stride_beats=stride,
        predicted_p50_ms=p50,
        predicted_p95_ms=p95,
        estimated_end_drift_ms=drift,
        local_tempo_ratio_min=minimum,
        local_tempo_ratio_max=maximum,
    )


def write_time_map(path: Path, time_map: TimeMap) -> None:
    content = "".join(f"{source} {target}\n" for source, target in time_map.frame_pairs)
    path.write_text(content, encoding="ascii", newline="\n")


def _atempo_factors(ratio: float) -> list[float]:
    if not math.isfinite(ratio) or ratio <= 0:
        raise TempoStretchError("Tempo ratio must be positive and finite")
    factors: list[float] = []
    remaining = ratio
    while remaining < 0.5:
        factors.append(0.5)
        remaining /= 0.5
    while remaining > 2.0:
        factors.append(2.0)
        remaining /= 2.0
    factors.append(remaining)
    return factors


def atempo_filter(ratio: float) -> str:
    return ",".join(f"atempo={factor:.12g}" for factor in _atempo_factors(ratio))


def _run_stretch_command(command: list[str], description: str) -> None:
    try:
        run_command(command, description)
    except AudioProcessingError as exc:
        raise TempoStretchError(str(exc)) from exc


def run_rubberband(
    input_wav: Path,
    output_wav: Path,
    stretch_ratio: float,
    centre_focus: bool,
    time_map_path: Path | None = None,
    output_duration_seconds: float | None = None,
) -> None:
    executable = find_executable("rubberband")
    if executable is None:
        raise TempoStretchError("Rubber Band CLI was not found on PATH")
    command = [executable, "--fine"]
    if centre_focus:
        command.append("--centre-focus")
    if time_map_path is None:
        command.extend(["--tempo", f"{stretch_ratio:.12g}"])
    else:
        if output_duration_seconds is None or output_duration_seconds <= 0:
            raise TempoStretchError("Rubber Band time maps require a positive duration")
        command.extend(
            [
                "--duration",
                f"{output_duration_seconds:.12g}",
                "--timemap",
                str(time_map_path),
            ]
        )
    command.extend([str(input_wav), str(output_wav)])
    _run_stretch_command(command, "Rubber Band R3 time stretch")


def run_ffmpeg_atempo(input_wav: Path, output_wav: Path, stretch_ratio: float) -> None:
    executable = find_executable("ffmpeg")
    if executable is None:
        raise TempoStretchError("FFmpeg was not found on PATH")
    command = [
        executable,
        "-v",
        "error",
        "-y",
        "-i",
        str(input_wav),
        "-map",
        "0:a:0",
        "-map_chapters",
        "-1",
        "-af",
        atempo_filter(stretch_ratio),
        "-c:a",
        "pcm_f32le",
        str(output_wav),
    ]
    _run_stretch_command(command, "FFmpeg atempo time stretch")


def stretch_audio_file(
    input_wav: Path,
    output_wav: Path,
    engine: str,
    stretch_ratio: float,
    centre_focus: bool,
    time_map_path: Path | None = None,
    output_duration_seconds: float | None = None,
) -> str:
    if time_map_path is None and math.isclose(stretch_ratio, 1.0, abs_tol=1e-8):
        shutil.copyfile(input_wav, output_wav)
        return "none"
    if engine == "rubberband":
        run_rubberband(
            input_wav,
            output_wav,
            stretch_ratio,
            centre_focus,
            time_map_path,
            output_duration_seconds,
        )
        return "rubberband"
    if engine == "ffmpeg-atempo":
        if time_map_path is not None:
            raise TempoStretchError("FFmpeg atempo cannot apply a time map")
        run_ffmpeg_atempo(input_wav, output_wav, stretch_ratio)
        return "ffmpeg-atempo"
    raise TempoStretchError(f"Unsupported selected engine: {engine}")
