from __future__ import annotations

import math
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import resample_poly

from .audio_io import apply_gain, peak_dbfs, rms_dbfs


class ClickTrackError(RuntimeError):
    """Raised when the fixed click asset or generated track is invalid."""


@dataclass(frozen=True)
class ClickTrack:
    samples: np.ndarray
    positions: np.ndarray
    times: np.ndarray
    interval_seconds: float
    peak_dbfs: float
    odd_even_peak_ratio: float
    rendered_peak_dbfs: float


@dataclass(frozen=True)
class MixResult:
    mixed: np.ndarray
    music_gain_db: float
    music_rms_before_dbfs: float
    music_rms_after_dbfs: float
    click_peak_over_music_rms_db: float
    mixed_peak_dbfs: float
    clipped: bool
    extra_headroom_reduction_db: float


def load_click_asset(path: Path, output_sample_rate: int) -> np.ndarray:
    if not path.is_file():
        raise ClickTrackError(f"Click asset does not exist: {path}")
    samples, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    if samples.shape[0] == 0:
        raise ClickTrackError(f"Click asset is empty: {path}")
    mono = np.mean(samples, axis=1, dtype=np.float64).astype(np.float32)
    if sample_rate != output_sample_rate:
        ratio = Fraction(output_sample_rate, sample_rate).limit_denominator(10000)
        mono = resample_poly(mono, ratio.numerator, ratio.denominator).astype(np.float32)
    if not np.all(np.isfinite(mono)) or not np.any(mono):
        raise ClickTrackError(f"Click asset contains no usable signal: {path}")
    return mono


def calibrate_click(click: np.ndarray, target_peak_dbfs: float) -> np.ndarray:
    current_peak = peak_dbfs(click)
    if not np.isfinite(current_peak):
        raise ClickTrackError("Click asset has no measurable peak")
    return apply_gain(click, target_peak_dbfs - current_peak)


def click_sample_positions(
    frame_count: int,
    sample_rate: int,
    target_bpm: float,
    anchor_seconds: float,
) -> tuple[np.ndarray, np.ndarray]:
    if frame_count <= 0 or sample_rate <= 0 or target_bpm <= 0:
        raise ValueError("Frame count, sample rate, and target BPM must be positive")
    interval = 30.0 / target_bpm
    duration = frame_count / sample_rate
    first_index = math.ceil((0.0 - anchor_seconds) / interval - 1e-12)
    last_index = math.floor((duration - anchor_seconds) / interval + 1e-12)
    indexes = np.arange(first_index, last_index + 1, dtype=np.int64)
    times = anchor_seconds + indexes.astype(np.float64) * interval
    positions = np.rint(times * sample_rate).astype(np.int64)
    valid = (positions >= 0) & (positions < frame_count)
    return positions[valid], times[valid]


def generate_click_track(
    frame_count: int,
    channels: int,
    sample_rate: int,
    target_bpm: float,
    anchor_seconds: float,
    click_asset: np.ndarray,
    click_peak_dbfs: float,
) -> ClickTrack:
    calibrated = calibrate_click(click_asset, click_peak_dbfs)
    positions, times = click_sample_positions(
        frame_count, sample_rate, target_bpm, anchor_seconds
    )
    if positions.size == 0:
        raise ClickTrackError("No click positions fall inside the output duration")

    # A click that starts so close to EOF that it cannot reach its calibrated
    # peak would be rendered quieter than every other click. Omit such terminal
    # truncations instead of reporting them as full-volume equal clicks.
    complete_positions = positions[
        positions <= frame_count - calibrated.size
    ]
    if complete_positions.size == 0:
        raise ClickTrackError(
            "Output is shorter than one click asset; no complete click can be placed"
        )
    track = np.zeros((frame_count, channels), dtype=np.float32)
    for position in complete_positions:
        start = int(position)
        track[start : start + calibrated.size] += calibrated[:, np.newaxis]

    return ClickTrack(
        samples=track,
        positions=complete_positions,
        times=times[: complete_positions.size],
        interval_seconds=30.0 / target_bpm,
        peak_dbfs=peak_dbfs(calibrated),
        odd_even_peak_ratio=1.0,
        rendered_peak_dbfs=peak_dbfs(track),
    )


def _mixed_peak(music: np.ndarray, click: np.ndarray, gain_db: float) -> float:
    return peak_dbfs(apply_gain(music, gain_db) + click)


def mix_fixed_click(
    music: np.ndarray,
    click: np.ndarray,
    click_peak_dbfs: float,
    click_over_music_rms_db: float = 16.0,
    output_peak_ceiling_dbfs: float = -1.0,
) -> MixResult:
    if music.shape != click.shape:
        raise ValueError("Music and click track shapes must match")

    rms_before = rms_dbfs(music)
    target_music_rms = click_peak_dbfs - click_over_music_rms_db
    base_gain = min(0.0, target_music_rms - rms_before)
    extra_reduction = 0.0

    if _mixed_peak(music, click, base_gain) > output_peak_ceiling_dbfs:
        low, high = -80.0, base_gain
        if _mixed_peak(music, click, low) > output_peak_ceiling_dbfs:
            raise ClickTrackError(
                "Fixed click alone exceeds the configured output peak ceiling"
            )
        for _ in range(40):
            midpoint = (low + high) / 2.0
            if _mixed_peak(music, click, midpoint) <= output_peak_ceiling_dbfs:
                low = midpoint
            else:
                high = midpoint
        extra_reduction = max(0.0, base_gain - low)
        base_gain = low

    adjusted_music = apply_gain(music, base_gain)
    mixed = adjusted_music + click
    mixed_peak = peak_dbfs(mixed)
    rms_after = rms_dbfs(adjusted_music)
    return MixResult(
        mixed=mixed.astype(np.float32),
        music_gain_db=float(base_gain),
        music_rms_before_dbfs=rms_before,
        music_rms_after_dbfs=rms_after,
        click_peak_over_music_rms_db=click_peak_dbfs - rms_after,
        mixed_peak_dbfs=mixed_peak,
        clipped=mixed_peak > 0.0,
        extra_headroom_reduction_db=extra_reduction,
    )
