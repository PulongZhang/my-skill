from __future__ import annotations

from dataclasses import dataclass

import librosa
import numpy as np
from scipy.signal import find_peaks


class TempoAnalysisError(RuntimeError):
    """Raised when a reliable musical beat grid cannot be estimated."""


@dataclass(frozen=True)
class TempoAnalysis:
    raw_bpm: float
    source_bpm: float
    beat_times: np.ndarray
    beat_ordinals: np.ndarray
    anchor_seconds: float
    grid_period_seconds: float
    grid_origin_seconds: float
    grid_error_p50_ms: float
    grid_error_p95_ms: float
    estimated_end_drift_ms: float
    confidence: float
    observed_beat_ratio: float
    max_missing_beat_run: int
    anchor_is_manual: bool
    candidate_margin: float


@dataclass(frozen=True)
class TempoResolution:
    source_bpm: float
    candidate_margin: float


ANALYSIS_RATE = 22050
HOP = 512


def normalize_bpm(bpm: float, minimum: float = 70.0, maximum: float = 130.0) -> float:
    """Map a tempo estimate into the configured running range by powers of two."""
    if not np.isfinite(bpm) or bpm <= 0:
        raise TempoAnalysisError(f"Invalid BPM estimate: {bpm}")
    center = (minimum + maximum) / 2.0
    candidates = [bpm * (2.0**power) for power in range(-8, 9)]
    in_range = [value for value in candidates if minimum <= value <= maximum]
    if in_range:
        return float(min(in_range, key=lambda value: abs(np.log(value / center))))
    return float(
        min(
            candidates,
            key=lambda value: (
                0.0
                if minimum <= value <= maximum
                else min(abs(value - minimum), abs(value - maximum)),
                abs(np.log(value / center)),
            ),
        )
    )


def choose_target_bpm(
    source_bpm: float, preferred: tuple[float, ...] = (90.0, 95.0)
) -> float:
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


def _onset_envelope(audio: np.ndarray, sample_rate: int) -> np.ndarray:
    if audio.ndim == 2:
        mono = np.mean(audio, axis=1, dtype=np.float64)
    elif audio.ndim == 1:
        mono = np.asarray(audio, dtype=np.float64)
    else:
        raise TempoAnalysisError("Audio must be mono or frame-by-channel stereo data")
    if mono.size < sample_rate * 2:
        raise TempoAnalysisError("Audio is too short for reliable tempo analysis")
    if sample_rate != ANALYSIS_RATE:
        mono = librosa.resample(mono, orig_sr=sample_rate, target_sr=ANALYSIS_RATE)
    percussive = librosa.effects.percussive(mono)
    return librosa.onset.onset_strength(y=percussive, sr=ANALYSIS_RATE)


def _tempo_candidates(
    onset_envelope: np.ndarray,
    min_bpm: float = 40.0,
    max_bpm: float = 240.0,
    top_n: int = 8,
) -> list[tuple[float, float]]:
    """Return (BPM, autocorrelation prominence) candidates from the onset grid."""
    signal = onset_envelope.astype(np.float64)
    autocorr = librosa.autocorrelate(signal - signal.mean(), max_size=signal.size)[1:]
    lags = np.arange(1, autocorr.size + 1)
    bpms = 60.0 * (ANALYSIS_RATE / HOP) / lags
    mask = (bpms >= min_bpm) & (bpms <= max_bpm)
    if not np.any(mask):
        raise TempoAnalysisError("No tempo candidates found in the autocorrelation")
    peaks, props = find_peaks(
        autocorr[mask], prominence=max(float(autocorr[mask].max()) * 0.04, 1e-12)
    )
    if peaks.size == 0:
        best = int(np.argmax(autocorr[mask]))
        return [(float(bpms[mask][best]), float(autocorr[mask][best]))]
    order = np.argsort(props["prominences"])[::-1][:top_n]
    return [
        (float(bpms[mask][peaks[index]]), float(props["prominences"][index]))
        for index in order
    ]


def _scaled_variants(bpm: float, low: float = 35.0, high: float = 300.0) -> list[float]:
    variants: list[float] = []
    value = bpm
    while value <= high:
        variants.append(value)
        value *= 2.0
    value = bpm / 2.0
    while value >= low:
        variants.append(value)
        value /= 2.0
    return variants


def _resolve_source_bpm(
    onset_envelope: np.ndarray,
    candidates: list[tuple[float, float]],
    minimum_bpm: float = 70.0,
    maximum_bpm: float = 130.0,
) -> TempoResolution:
    """Resolve source tempo from audio evidence, independent of target preference."""
    variants: list[tuple[float, float, float]] = []
    max_prominence = max((prominence for _, prominence in candidates), default=1.0)
    for candidate, prominence in candidates:
        for variant in _scaled_variants(candidate):
            if not minimum_bpm <= variant <= maximum_bpm:
                continue
            period_frames = 60.0 / variant * ANALYSIS_RATE / HOP
            if period_frames <= 1.0:
                continue
            phase_step = max(0.5, min(2.0, period_frames / 32.0))
            energy = max(
                _grid_energy(onset_envelope, period_frames, phase)
                for phase in np.arange(0.0, period_frames, phase_step)
            )
            variants.append(
                (
                    variant,
                    energy,
                    prominence / max_prominence if max_prominence > 0 else 0.0,
                )
            )
    if not variants:
        raise TempoAnalysisError("Could not resolve a source BPM from candidates")

    max_energy = max(energy for _, energy, _ in variants)
    variants.sort(
        key=lambda item: (
            0.75 * (item[1] / max_energy if max_energy > 0 else 0.0)
            + 0.25 * item[2]
        ),
        reverse=True,
    )

    refined: list[tuple[float, float, float, float]] = []
    for variant, _, prominence_score in variants[:6]:
        period_frames = 60.0 / variant * ANALYSIS_RATE / HOP
        refined_period, refined_phase = _refine_grid(
            onset_envelope,
            period_frames,
            0.0,
            period_radius=period_frames * 0.015,
            period_step=0.002,
        )
        energy = _grid_energy(onset_envelope, refined_period, refined_phase)
        refined_bpm = 60.0 / (refined_period * HOP / ANALYSIS_RATE)
        hit = _hit_ratio(
            onset_envelope,
            max(1, int(round(refined_period))),
            int(round(refined_phase)) % max(1, int(round(refined_period))),
        )
        refined.append((refined_bpm, energy, hit, prominence_score))

    max_energy = max(energy for _, energy, _, _ in refined)
    max_hit = max(hit for _, _, hit, _ in refined)

    def score(item: tuple[float, float, float, float]) -> float:
        _, energy, hit, prominence = item
        energy_score = energy / max_energy if max_energy > 0 else 0.0
        hit_score = hit / max_hit if max_hit > 0 else 0.0
        return 0.55 * energy_score + 0.30 * hit_score + 0.15 * prominence

    refined.sort(key=score, reverse=True)
    best = refined[0]
    best_score = score(best)
    second_score = score(refined[1]) if len(refined) > 1 else 0.0
    return TempoResolution(best[0], max(0.0, best_score - second_score))


def _grid_energy(
    onset_envelope: np.ndarray,
    period_frames: float,
    phase_frames: float,
) -> float:
    positions = np.rint(
        phase_frames + np.arange(0.0, onset_envelope.size - phase_frames, period_frames)
    ).astype(np.int64)
    positions = positions[(positions >= 0) & (positions < onset_envelope.size)]
    if positions.size == 0:
        return 0.0
    return float(np.mean(onset_envelope[positions]))


def _grid_phase_search(
    onset_envelope: np.ndarray,
    period_frames: int,
) -> tuple[int, float]:
    best_phase = 0
    best_sum = -1.0
    for phase in range(period_frames):
        total = float(onset_envelope[phase::period_frames].sum())
        if total > best_sum:
            best_sum, best_phase = total, phase
    return best_phase, best_sum


def _refine_grid(
    onset_envelope: np.ndarray,
    period_frames: float,
    phase_frames: float,
    period_radius: float = 1.0,
    period_step: float = 0.02,
) -> tuple[float, float]:
    """Jointly refine the grid period and phase on a fractional scale."""
    best_period = float(period_frames)
    best_phase = float(phase_frames)
    best_score = _grid_energy(onset_envelope, best_period, best_phase)

    coarse_step = max(period_step * 5.0, 0.1)
    for candidate_period in np.arange(
        period_frames - period_radius,
        period_frames + period_radius + coarse_step / 2,
        coarse_step,
    ):
        if candidate_period <= 1.0:
            continue
        for candidate_phase in np.arange(0.0, candidate_period, 0.25):
            score = _grid_energy(onset_envelope, candidate_period, candidate_phase)
            if score > best_score:
                best_score = score
                best_period, best_phase = candidate_period, candidate_phase

    fine_phase_low = max(0.0, best_phase - 0.5)
    for candidate_period in np.arange(
        best_period - coarse_step,
        best_period + coarse_step + period_step / 2,
        period_step,
    ):
        if candidate_period <= 1.0:
            continue
        for candidate_phase in np.arange(fine_phase_low, best_phase + 0.51, 0.01):
            score = _grid_energy(onset_envelope, candidate_period, candidate_phase)
            if score > best_score:
                best_score = score
                best_period, best_phase = candidate_period, candidate_phase
    return best_period, best_phase


def _hit_ratio(
    onset_envelope: np.ndarray,
    period_frames: int,
    phase: int,
    sample_phases: int = 12,
    seed: int = 0,
) -> float:
    period_frames = max(1, period_frames)
    phase %= period_frames
    rng = np.random.default_rng(seed)
    on_grid = onset_envelope[phase::period_frames].mean()
    off_total = 0.0
    for _ in range(sample_phases):
        off_phase = int(rng.integers(0, period_frames))
        off_total += onset_envelope[off_phase::period_frames].mean()
    off_grid = off_total / sample_phases
    if off_grid <= 0:
        return 1.0
    return float(np.clip(on_grid / off_grid, 0.0, 4.0) / 4.0)


def _snap_beats_to_onsets(
    onset_envelope: np.ndarray,
    beat_frames: np.ndarray,
    beat_ordinals: np.ndarray,
    period_frames: float,
    snap_fraction: float = 0.05,
) -> tuple[np.ndarray, np.ndarray]:
    """Return only observed onset peaks and their original grid ordinals."""
    if beat_frames.size != beat_ordinals.size:
        raise TempoAnalysisError("Beat frames and ordinals must have equal length")
    if beat_frames.size == 0:
        return np.zeros(0, dtype=np.int64), np.zeros(0, dtype=np.int64)

    envelope_max = float(np.max(onset_envelope))
    prominence = max(float(np.std(onset_envelope)) * 0.05, envelope_max * 0.01, 1e-8)
    narrow_window = max(1, int(round(period_frames * snap_fraction)))
    wide_window = max(narrow_window, int(round(period_frames * 0.15)))
    observed_frames: list[int] = []
    observed_ordinals: list[int] = []

    for beat, ordinal in zip(beat_frames, beat_ordinals, strict=True):
        center = int(beat)
        selected: int | None = None
        # Prefer the nearest onset peak inside the narrow window; only fall
        # back to the wider window when the beat lands in a quiet gap.
        for window in (narrow_window, wide_window):
            low = max(0, center - window)
            high = min(onset_envelope.size - 1, center + window)
            segment = onset_envelope[low : high + 1]
            if segment.size == 0:
                continue
            peaks, _ = find_peaks(segment, prominence=prominence)
            if peaks.size == 0:
                continue
            nearest = int(peaks[int(np.argmin(np.abs(peaks - (center - low))))])
            selected = low + nearest
            break
        if selected is None:
            continue
        observed_frames.append(selected)
        observed_ordinals.append(int(ordinal))

    return (
        np.asarray(observed_frames, dtype=np.int64),
        np.asarray(observed_ordinals, dtype=np.int64),
    )


def _fit_grid(beat_times: np.ndarray) -> tuple[float, float, np.ndarray]:
    indexes = np.arange(beat_times.size, dtype=np.float64)
    period, origin = np.polyfit(indexes, beat_times, 1)
    fitted = origin + indexes * period
    residuals = beat_times - fitted
    return float(period), float(origin), residuals


def _observation_metrics(
    beat_times: np.ndarray,
    beat_ordinals: np.ndarray,
    anchor_seconds: float,
    period_seconds: float,
) -> tuple[float, float, float]:
    expected = anchor_seconds + beat_ordinals.astype(np.float64) * period_seconds
    residuals = beat_times - expected
    absolute_ms = np.abs(residuals) * 1000.0
    if absolute_ms.size == 0:
        return float("inf"), float("inf"), float("inf")
    drift_ms = 0.0
    if residuals.size >= 2:
        drift_ms = abs(float(residuals[-1] - residuals[0])) * 1000.0
    return (
        float(np.percentile(absolute_ms, 50)),
        float(np.percentile(absolute_ms, 95)),
        drift_ms,
    )


def _max_missing_beat_run(
    candidate_ordinals: np.ndarray,
    observed_ordinals: np.ndarray,
) -> int:
    candidates = np.asarray(candidate_ordinals, dtype=np.int64)
    observed = np.asarray(observed_ordinals, dtype=np.int64)
    if candidates.size == 0:
        return 0
    observed_set = set(int(value) for value in observed)
    longest = 0
    current = 0
    for ordinal in candidates:
        if int(ordinal) in observed_set:
            current = 0
        else:
            current += 1
            longest = max(longest, current)
    return int(longest)


def fit_click_grid(
    audio: np.ndarray,
    sample_rate: int,
    expected_bpm: float,
    anchor_hint_seconds: float | None = None,
    lock_anchor: bool = False,
    period_fraction: float = 0.015,
) -> tuple[float, float]:
    """Fit a quarter-note period near expected BPM and return period/phase seconds."""
    onset_envelope = _onset_envelope(audio, sample_rate)
    expected_period = 60.0 / expected_bpm * ANALYSIS_RATE / HOP
    phase_hint = 0.0
    if anchor_hint_seconds is not None:
        phase_hint = (anchor_hint_seconds * ANALYSIS_RATE / HOP) % expected_period
    period_frames, phase = _refine_grid(
        onset_envelope,
        expected_period,
        phase_hint,
        period_radius=expected_period * period_fraction,
        period_step=0.002,
    )
    period_seconds = period_frames * HOP / ANALYSIS_RATE
    if lock_anchor and anchor_hint_seconds is not None:
        return period_seconds, float(anchor_hint_seconds)
    return period_seconds, phase * HOP / ANALYSIS_RATE


def analyze_tempo(
    audio: np.ndarray,
    sample_rate: int,
    first_beat: float | None = None,
) -> TempoAnalysis:
    onset_envelope = _onset_envelope(audio, sample_rate)
    candidates = _tempo_candidates(onset_envelope)
    resolution = _resolve_source_bpm(onset_envelope, candidates)
    source_bpm = resolution.source_bpm

    expected_period = 60.0 / source_bpm * ANALYSIS_RATE / HOP
    integer_period = max(1, int(round(expected_period)))
    integer_phase, _ = _grid_phase_search(onset_envelope, integer_period)
    period_frames, phase = _refine_grid(
        onset_envelope,
        expected_period,
        float(integer_phase),
        period_radius=expected_period * 0.015,
        period_step=0.002,
    )

    if first_beat is not None:
        if not np.isfinite(first_beat) or first_beat < 0 or first_beat >= audio.shape[0] / sample_rate:
            raise TempoAnalysisError("First-beat anchor is outside the audio duration")
        anchor_frame = first_beat * ANALYSIS_RATE / HOP
        first_grid_index = int(np.ceil((0.0 - anchor_frame) / period_frames))
        last_grid_index = int(np.floor((onset_envelope.size - anchor_frame) / period_frames))
        grid_indexes = np.arange(first_grid_index, last_grid_index + 1, dtype=np.int64)
        grid_frames = np.rint(anchor_frame + grid_indexes * period_frames).astype(np.int64)
        valid = (grid_frames >= 0) & (grid_frames < onset_envelope.size)
        grid_frames = grid_frames[valid]
        grid_indexes = grid_indexes[valid]
        anchor = float(first_beat)
        grid_origin = anchor
    else:
        last_index = int((onset_envelope.size - phase) // period_frames)
        grid_indexes = np.arange(last_index + 1, dtype=np.int64)
        grid_frames = np.rint(phase + grid_indexes * period_frames).astype(np.int64)
        valid = (grid_frames >= 0) & (grid_frames < onset_envelope.size)
        grid_frames = grid_frames[valid]
        grid_indexes = grid_indexes[valid]
        anchor = 0.0
        grid_origin = phase * HOP / ANALYSIS_RATE

    observed_frames, observed_ordinals = _snap_beats_to_onsets(
        onset_envelope,
        grid_frames,
        grid_indexes,
        period_frames,
    )
    if observed_frames.size < 8:
        raise TempoAnalysisError(
            f"Only {observed_frames.size} observed grid beats were detected; at least 8 are required"
        )

    beat_times = observed_frames * HOP / ANALYSIS_RATE
    if first_beat is None:
        anchor = float(beat_times[0])
        first_ordinal = int(observed_ordinals[0])
        observed_ordinals = observed_ordinals - first_ordinal
        grid_origin = anchor

    period_seconds = period_frames * HOP / ANALYSIS_RATE
    p50, p95, observed_drift = _observation_metrics(
        beat_times, observed_ordinals, anchor, period_seconds
    )
    coverage = float(observed_frames.size / max(1, grid_frames.size))
    max_missing_run = _max_missing_beat_run(grid_indexes, observed_ordinals)
    hit = _hit_ratio(
        onset_envelope,
        max(1, int(round(period_frames))),
        int(round(phase)) % max(1, int(round(period_frames))),
    )
    grid_quality = float(np.exp(-p95 / 45.0))
    base_confidence = (
        0.35 * hit
        + 0.30 * min(1.0, coverage)
        + 0.20 * grid_quality
        + 0.15 * min(1.0, resolution.candidate_margin * 8.0)
    )
    gap_penalty = min(1.0, 8.0 / max(1.0, max_missing_run + 1.0))
    confidence = float(
        np.clip(base_confidence * min(1.0, coverage) * gap_penalty, 0.0, 1.0)
    )

    refined_bpm = 60.0 / period_seconds
    return TempoAnalysis(
        raw_bpm=candidates[0][0],
        source_bpm=refined_bpm,
        beat_times=beat_times.astype(np.float64),
        beat_ordinals=observed_ordinals.astype(np.int64),
        anchor_seconds=anchor,
        grid_period_seconds=period_seconds,
        grid_origin_seconds=grid_origin,
        grid_error_p50_ms=p50,
        grid_error_p95_ms=p95,
        estimated_end_drift_ms=float(observed_drift),
        confidence=confidence,
        observed_beat_ratio=coverage,
        max_missing_beat_run=max_missing_run,
        anchor_is_manual=first_beat is not None,
        candidate_margin=resolution.candidate_margin,
    )


def alignment_result(
    p50_ms: float,
    p95_ms: float,
    end_drift_ms: float,
    threshold_p95_ms: float = 30.0,
    threshold_end_drift_ms: float = 50.0,
) -> dict[str, float | bool]:
    return {
        "predicted_p50_ms": p50_ms,
        "predicted_p95_ms": p95_ms,
        "estimated_end_drift_ms": end_drift_ms,
        "threshold_p95_ms": threshold_p95_ms,
        "threshold_end_drift_ms": threshold_end_drift_ms,
        "passed": p95_ms <= threshold_p95_ms and end_drift_ms <= threshold_end_drift_ms,
    }


def transformed_alignment(
    beat_times: np.ndarray,
    anchor_input: float,
    stretch_ratio: float,
    target_bpm: float,
    strict: bool,
    beat_ordinals: np.ndarray | None = None,
    output_grid_period_seconds: float | None = None,
    output_grid_origin_seconds: float | None = None,
) -> dict[str, float | bool]:
    beats = np.asarray(beat_times, dtype=np.float64)
    if beats.size == 0:
        raise TempoAnalysisError("At least one beat is required for alignment")
    if beat_ordinals is None:
        source_bpm = target_bpm / stretch_ratio
        ordinals = np.rint((beats - anchor_input) * source_bpm / 60.0).astype(np.int64)
    else:
        ordinals = np.asarray(beat_ordinals, dtype=np.int64)
        if ordinals.shape != beats.shape:
            raise TempoAnalysisError("Beat times and ordinals must have equal shape")

    period = output_grid_period_seconds or 60.0 / target_bpm
    origin = (
        output_grid_origin_seconds
        if output_grid_origin_seconds is not None
        else anchor_input / stretch_ratio
    )
    target_times = origin + ordinals.astype(np.float64) * period
    mapped = target_times if strict else beats / stretch_ratio
    signed_errors = mapped - target_times
    errors_ms = np.abs(signed_errors) * 1000.0
    p50 = float(np.percentile(errors_ms, 50))
    p95 = float(np.percentile(errors_ms, 95))
    end_drift = (
        abs(float(signed_errors[-1] - signed_errors[0])) * 1000.0
        if signed_errors.size >= 2
        else 0.0
    )
    return alignment_result(p50, p95, end_drift)
