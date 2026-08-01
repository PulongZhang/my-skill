from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np


class TempoAnalysisError(RuntimeError):
    """Raised when a reliable musical beat grid cannot be estimated."""


@dataclass(frozen=True)
class TempoAnalysis:
    raw_bpm: float
    source_bpm: float
    beat_times: np.ndarray
    anchor_seconds: float
    grid_period_seconds: float
    grid_origin_seconds: float
    grid_error_p50_ms: float
    grid_error_p95_ms: float
    estimated_end_drift_ms: float
    confidence: float


def normalize_bpm(bpm: float, minimum: float = 70.0, maximum: float = 130.0) -> float:
    if not np.isfinite(bpm) or bpm <= 0:
        raise TempoAnalysisError(f"Invalid BPM estimate: {bpm}")
    normalized = float(bpm)
    while normalized < minimum:
        normalized *= 2.0
    while normalized > maximum:
        normalized /= 2.0
    return normalized


def choose_target_bpm(source_bpm: float, preferred: tuple[float, ...] = (90.0, 95.0)) -> float:
    if source_bpm <= 0 or not preferred:
        raise ValueError("Source BPM and preferred target list must be positive")
    return min(preferred, key=lambda value: (abs(np.log(value / source_bpm)), -value))


def parse_target_bpm(value: str, source_bpm: float) -> float:
    if value.strip().lower() == "auto":
        return choose_target_bpm(source_bpm)
    try:
        target = float(value)
    except ValueError as exc:
        raise ValueError("Target BPM must be 'auto' or a positive number") from exc
    if not np.isfinite(target) or target <= 0:
        raise ValueError("Target BPM must be a positive finite number")
    return target


def _tempo_scalar(value: object) -> float:
    array = np.asarray(value, dtype=float).reshape(-1)
    if array.size == 0:
        raise TempoAnalysisError("Tempo estimator returned no BPM value")
    return float(array[0])


def _fit_grid(beat_times: np.ndarray) -> tuple[float, float, np.ndarray]:
    indexes = np.arange(beat_times.size, dtype=np.float64)
    period, origin = np.polyfit(indexes, beat_times, 1)
    fitted = origin + indexes * period
    residuals = beat_times - fitted
    return float(period), float(origin), residuals


def analyze_tempo(
    audio: np.ndarray,
    sample_rate: int,
    first_beat: float | None = None,
) -> TempoAnalysis:
    if audio.ndim == 2:
        mono = np.mean(audio, axis=1, dtype=np.float64)
    elif audio.ndim == 1:
        mono = np.asarray(audio, dtype=np.float64)
    else:
        raise TempoAnalysisError("Audio must be mono or frame-by-channel stereo data")
    if mono.size < sample_rate * 2:
        raise TempoAnalysisError("Audio is too short for reliable tempo analysis")

    analysis_rate = 22050
    if sample_rate != analysis_rate:
        mono = librosa.resample(mono, orig_sr=sample_rate, target_sr=analysis_rate)
    percussive = librosa.effects.percussive(mono)
    onset_envelope = librosa.onset.onset_strength(y=percussive, sr=analysis_rate)
    raw_bpm = _tempo_scalar(
        librosa.feature.tempo(onset_envelope=onset_envelope, sr=analysis_rate)
    )
    normalized_bpm = normalize_bpm(raw_bpm)
    _, beat_frames = librosa.beat.beat_track(
        onset_envelope=onset_envelope,
        sr=analysis_rate,
        bpm=normalized_bpm,
        sparse=True,
    )
    beat_times = np.asarray(
        librosa.frames_to_time(beat_frames, sr=analysis_rate), dtype=np.float64
    )
    if beat_times.size < 8:
        raise TempoAnalysisError(
            f"Only {beat_times.size} beats were detected; at least 8 are required"
        )

    period, origin, residuals = _fit_grid(beat_times)
    fitted_bpm = normalize_bpm(60.0 / period)
    if fitted_bpm != 60.0 / period:
        period = 60.0 / fitted_bpm
        origin = float(np.median(beat_times - np.arange(beat_times.size) * period))
        residuals = beat_times - (origin + np.arange(beat_times.size) * period)

    absolute_ms = np.abs(residuals) * 1000.0
    p50 = float(np.percentile(absolute_ms, 50))
    p95 = float(np.percentile(absolute_ms, 95))
    end_drift = float(abs(residuals[-1] - residuals[0]) * 1000.0)
    count_score = min(1.0, beat_times.size / 32.0)
    error_score = max(0.0, 1.0 - p95 / 100.0)
    confidence = float(count_score * error_score)

    anchor = float(first_beat) if first_beat is not None else float(beat_times[0])
    if not np.isfinite(anchor) or anchor < 0 or anchor >= mono.size / analysis_rate:
        raise TempoAnalysisError("First-beat anchor is outside the audio duration")

    return TempoAnalysis(
        raw_bpm=raw_bpm,
        source_bpm=fitted_bpm,
        beat_times=beat_times,
        anchor_seconds=anchor,
        grid_period_seconds=period,
        grid_origin_seconds=origin,
        grid_error_p50_ms=p50,
        grid_error_p95_ms=p95,
        estimated_end_drift_ms=end_drift,
        confidence=confidence,
    )


def alignment_result(
    p50_ms: float,
    p95_ms: float,
    end_drift_ms: float,
    threshold_p95_ms: float = 30.0,
) -> dict[str, float | bool]:
    return {
        "predicted_p50_ms": p50_ms,
        "predicted_p95_ms": p95_ms,
        "estimated_end_drift_ms": end_drift_ms,
        "threshold_p95_ms": threshold_p95_ms,
        "passed": p95_ms <= threshold_p95_ms,
    }


def transformed_alignment(
    beat_times: np.ndarray,
    anchor_input: float,
    stretch_ratio: float,
    target_bpm: float,
    strict: bool,
) -> dict[str, float | bool]:
    anchor_output = anchor_input / stretch_ratio
    source_bpm = target_bpm / stretch_ratio
    indexes = np.rint((beat_times - anchor_input) * source_bpm / 60.0)
    target_times = anchor_output + indexes * 60.0 / target_bpm
    if strict:
        mapped = target_times
    else:
        mapped = beat_times / stretch_ratio
    errors_ms = np.abs(mapped - target_times) * 1000.0
    p50 = float(np.percentile(errors_ms, 50))
    p95 = float(np.percentile(errors_ms, 95))
    end_drift = float(
        abs(
            (mapped[-1] - target_times[-1])
            - (mapped[0] - target_times[0])
        )
        * 1000.0
    )
    return alignment_result(p50, p95, end_drift)
