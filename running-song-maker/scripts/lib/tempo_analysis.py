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
    anchor_seconds: float
    grid_period_seconds: float
    grid_origin_seconds: float
    grid_error_p50_ms: float
    grid_error_p95_ms: float
    estimated_end_drift_ms: float
    confidence: float


ANALYSIS_RATE = 22050
HOP = 512


def normalize_bpm(bpm: float, minimum: float = 70.0, maximum: float = 130.0) -> float:
    """Map a tempo estimate into the running range by powers of two.

    Slow songs with a half-time feel (for example 67 BPM) and their
    double-time readings (134 BPM) must both survive normalization, so this
    returns the scaled value closest to the center of the interval instead of
    cycling forever between two values that straddle it.
    """
    if not np.isfinite(bpm) or bpm <= 0:
        raise TempoAnalysisError(f"Invalid BPM estimate: {bpm}")
    center = (minimum + maximum) / 2.0
    scaled = float(bpm)
    best = scaled
    best_distance = abs(np.log(scaled / center))
    while scaled * 2.0 <= maximum * 2.0:
        scaled *= 2.0
        distance = abs(np.log(scaled / center))
        if distance < best_distance:
            best, best_distance = scaled, distance
    scaled = float(bpm)
    while scaled / 2.0 >= minimum / 2.0:
        scaled /= 2.0
        distance = abs(np.log(scaled / center))
        if distance < best_distance:
            best, best_distance = scaled, distance
    return best


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
        autocorr[mask], prominence=autocorr[mask].max() * 0.04
    )
    order = np.argsort(props["prominences"])[::-1][:top_n]
    return [
        (float(bpms[mask][peak]), float(props["prominences"][index]))
        for index, peak in enumerate(peaks[order])
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
    candidates: list[tuple[float, float]],
    preferred: tuple[float, ...] = (90.0, 95.0),
) -> tuple[float, float]:
    """Pick the BPM and target whose powers-of-two variants are closest.

    Half-time feel songs such as Die For You (67 BPM) can be read as
    134 BPM, so each autocorrelation candidate is expanded to its powers of
    two and the variant closest to a running target wins.
    """
    best_bpm: float | None = None
    best_distance = float("inf")
    for candidate, _ in candidates:
        for variant in _scaled_variants(candidate):
            distance = min(abs(np.log(preferred_value / variant)) for preferred_value in preferred)
            if distance < best_distance:
                best_bpm, best_distance = variant, distance
    if best_bpm is None:
        raise TempoAnalysisError("Could not resolve a source BPM from candidates")
    return best_bpm, choose_target_bpm(best_bpm, preferred)


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
    return float(onset_envelope[positions].sum())


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
    """Jointly refine the grid period and phase on a fractional scale.

    Integer-frame autocorrelation only resolves BPM to about one frame
    (~1.7% at 90 BPM), which lets click grids drift noticeably over a full
    song. A coarse fractional-period scan with a full fractional-phase sweep
    finds the right attraction basin, then a fine scan around the best
    candidate locks in the exact quantization grid. The integer phase is
    unreliable when the true period is non-integer, so it is never used as a
    starting point here.
    """
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
    rng = np.random.default_rng(seed)
    on_grid = onset_envelope[phase::period_frames].mean()
    off_total = 0.0
    for _ in range(sample_phases):
        off_phase = int(rng.integers(0, period_frames))
        off_total += onset_envelope[off_phase::period_frames].mean()
    off_grid = off_total / sample_phases
    if off_grid <= 0:
        return 1.0
    return float(on_grid / off_grid)


def fit_click_grid(
    audio: np.ndarray,
    sample_rate: int,
    expected_bpm: float,
    period_fraction: float = 0.015,
) -> tuple[float, float]:
    """Fit the stretched audio's real quarter-note grid for click placement.

    Theoretical target BPM never matches the post-stretch audio exactly
    (analysis BPM error and codec behavior both leak in), so clicks should
    follow a grid fitted to the actual stretched audio near the expected
    target. Returns (period_seconds, phase_seconds).
    """
    onset_envelope = _onset_envelope(audio, sample_rate)
    expected_period = 60.0 / expected_bpm * ANALYSIS_RATE / HOP
    period_frames, phase = _refine_grid(
        onset_envelope,
        expected_period,
        0.0,
        period_radius=expected_period * period_fraction,
        period_step=0.002,
    )
    return (
        period_frames * HOP / ANALYSIS_RATE,
        phase * HOP / ANALYSIS_RATE,
    )


def _snap_beats_to_onsets(
    onset_envelope: np.ndarray,
    beat_frames: np.ndarray,
    period_frames: int,
    snap_fraction: float = 0.15,
) -> np.ndarray:
    """Pull each grid beat to the nearest onset peak inside a snap window.

    The pure grid is an idealized straight line; snapping it to the closest
    local onset peak recovers the song's real micro-timing, which is what
    drift correction and alignment error reports should measure. Picking the
    nearest peak rather than the strongest one avoids jumping to an adjacent
    eighth-note hat when a busy drum pattern dominates the onset envelope.
    """
    window = max(1, int(round(period_frames * snap_fraction)))
    snapped: list[int] = []
    for beat in beat_frames:
        low = max(0, int(beat) - window)
        high = min(onset_envelope.size - 1, int(beat) + window)
        segment = onset_envelope[low : high + 1]
        if segment.size == 0:
            snapped.append(int(beat))
            continue
        peaks, _ = find_peaks(segment)
        if peaks.size == 0:
            snapped.append(int(beat))
            continue
        nearest = int(peaks[int(np.argmin(np.abs(peaks - (int(beat) - low))))])
        snapped.append(low + nearest)
    return np.asarray(snapped, dtype=np.int64)


def _fit_grid(beat_times: np.ndarray) -> tuple[float, float, np.ndarray]:
    indexes = np.arange(beat_times.size, dtype=np.float64)
    period, origin = np.polyfit(indexes, beat_times, 1)
    fitted = origin + indexes * period
    residuals = beat_times - fitted
    return float(period), float(origin), residuals


def _segmented_drift(
    onset_envelope: np.ndarray,
    period_frames: int,
    phase: int,
    segments: int = 8,
    search_radius_frames: int = 3,
) -> float:
    """Estimate end-to-start phase drift with a fine local phase search.

    A full re-search per segment can jump to an adjacent sixteenth-note grid
    on dense, quantized electronic music and report fake drift. Instead each
    segment only searches a small radius around the globally extrapolated
    phase, so the reported drift reflects genuine micro-tempo movement rather
    than a re-quantization artifact.
    """
    if segments < 2 or onset_envelope.size <= period_frames * 2:
        return 0.0
    edges = np.linspace(0, onset_envelope.size, segments + 1).astype(int)
    residuals: list[float] = []
    for index in range(segments):
        window = onset_envelope[edges[index] : edges[index + 1]]
        if window.size < period_frames * 2:
            continue
        expected_phase = phase + index * period_frames - edges[index]
        radius = max(1, search_radius_frames)
        candidate_range = range(
            max(0, expected_phase - radius),
            min(period_frames, expected_phase + radius + 1),
        )
        best_phase, best_sum = expected_phase, -1.0
        for candidate in candidate_range:
            total = float(window[candidate::period_frames].sum())
            if total > best_sum:
                best_sum, best_phase = total, candidate
        residual = (edges[index] + best_phase) - (phase + index * period_frames)
        residuals.append(float(residual))
    if len(residuals) < 2:
        return 0.0
    # Random per-segment search noise averages out in a linear fit; a genuine
    # tempo drift shows up as a significant slope.
    if len(residuals) >= 4:
        slope = float(np.polyfit(np.arange(len(residuals)), residuals, 1)[0])
        drift_frames = slope * (len(residuals) - 1)
    else:
        drift_frames = residuals[-1] - residuals[0]
    drift_seconds = drift_frames * HOP / ANALYSIS_RATE
    return abs(drift_seconds) * 1000.0


def analyze_tempo(
    audio: np.ndarray,
    sample_rate: int,
    first_beat: float | None = None,
) -> TempoAnalysis:
    onset_envelope = _onset_envelope(audio, sample_rate)
    candidates = _tempo_candidates(onset_envelope)
    source_bpm, _ = _resolve_source_bpm(candidates)

    period_seconds = 60.0 / source_bpm
    integer_period = max(1, int(round(period_seconds * ANALYSIS_RATE / HOP)))
    integer_phase, _ = _grid_phase_search(onset_envelope, integer_period)
    period_frames, phase = _refine_grid(
        onset_envelope, float(integer_period), float(integer_phase)
    )
    hit = _hit_ratio(onset_envelope, int(round(period_frames)), int(round(phase)))

    # Build the quarter-note beat grid from the refined fractional grid, then
    # pull each beat to its local onset peak so real micro-timing survives
    # into reports and the strict time map.
    last_index = int((onset_envelope.size - phase) // period_frames)
    indexes = np.arange(last_index + 1)
    grid_frames = np.rint(phase + indexes * period_frames).astype(np.int64)
    grid_frames = grid_frames[grid_frames < onset_envelope.size]
    beat_frames = _snap_beats_to_onsets(
        onset_envelope, grid_frames, int(round(period_frames))
    )
    beat_times = (beat_frames * HOP / ANALYSIS_RATE).astype(np.float64)

    if beat_times.size < 8:
        raise TempoAnalysisError(
            f"Only {beat_times.size} grid beats were detected; at least 8 are required"
        )

    grid_residual_frames = beat_frames - grid_frames
    absolute_ms = np.abs(grid_residual_frames) * HOP / ANALYSIS_RATE * 1000.0
    p50 = float(np.percentile(absolute_ms, 50))
    p95 = float(np.percentile(absolute_ms, 95))
    drift_ms = _segmented_drift(
        onset_envelope, int(round(period_frames)), int(round(phase))
    )

    # Confidence combines how much onset energy lands on the grid (hit ratio)
    # with how reasonable the required stretch is. On dense pop productions a
    # modest hit ratio is normal, so a small stretch to a running target makes
    # the resolution trustworthy even when no single autocorrelation peak
    # dominates.
    stretch_ratio = 90.0 / source_bpm
    stretch_penalty = max(0.0, 1.0 - abs(np.log(stretch_ratio)) / 0.12)
    confidence = float(np.clip(hit * 0.6 + stretch_penalty * 0.4, 0.0, 1.0))

    anchor = float(first_beat) if first_beat is not None else float(beat_times[0])
    if not np.isfinite(anchor) or anchor < 0 or anchor >= audio.shape[0] / sample_rate:
        raise TempoAnalysisError("First-beat anchor is outside the audio duration")

    return TempoAnalysis(
        raw_bpm=candidates[0][0],
        source_bpm=source_bpm,
        beat_times=beat_times,
        anchor_seconds=anchor,
        grid_period_seconds=period_frames * HOP / ANALYSIS_RATE,
        grid_origin_seconds=phase * HOP / ANALYSIS_RATE,
        grid_error_p50_ms=p50,
        grid_error_p95_ms=p95,
        estimated_end_drift_ms=drift_ms,
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
