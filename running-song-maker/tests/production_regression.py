#!/usr/bin/env python3
"""Read-only measurements for an existing running-song WAV corpus."""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import butter, fftconvolve, find_peaks, sosfilt

SCRIPTS_DIR = Path(__file__).resolve().parents[1] / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))
from lib.audio_io import resample_audio  # noqa: E402


SCRIPT_PATH = SCRIPTS_DIR / "make_running_song.py"
DEFAULT_CLICK = Path(__file__).resolve().parents[1] / "assets" / (
    "running_wood_click_580hz_soft6ms.wav"
)
BPM_PATTERN = re.compile(r"\((?P<bpm>[0-9]+(?:\.[0-9]+)?)bpm\)\.wav$", re.I)
EXPECTED_SAMPLE_RATE = 48000
EXPECTED_CHANNELS = 2
EXPECTED_SUBTYPE = "PCM_24"
PEAK_TOLERANCE_DB = 0.05
CADENCE_TOLERANCE_SPM = 0.5
GRID_TOLERANCE_SECONDS = 0.015
MIN_MATCH_RATIO = 0.95
MATCH_SCORE_THRESHOLD = 0.50


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure existing running-song WAV files without modifying them"
    )
    parser.add_argument("--corpus", required=True, type=Path)
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("running-song-maker-workspace/production-regression/results.json"),
    )
    parser.add_argument("--click-file", type=Path, default=DEFAULT_CLICK)
    parser.add_argument(
        "--skip-analysis",
        action="store_true",
        help="Skip the uv-managed analyze-only pass and only measure rendered WAVs",
    )
    return parser.parse_args()


def _peak_dbfs(samples: np.ndarray) -> float:
    peak = float(np.max(np.abs(samples))) if samples.size else 0.0
    if peak <= 0.0:
        return float("-inf")
    return 20.0 * np.log10(peak)


def _expected_bpm(path: Path) -> float | None:
    match = BPM_PATTERN.search(path.name)
    return float(match.group("bpm")) if match else None


def _bandpass(samples: np.ndarray, sample_rate: int) -> np.ndarray:
    high_cut = min(1400.0, sample_rate * 0.45)
    if high_cut <= 350.0:
        return samples.astype(np.float32, copy=False)
    sos = butter(
        4,
        [350.0, high_cut],
        btype="bandpass",
        fs=sample_rate,
        output="sos",
    )
    return sosfilt(sos, samples).astype(np.float32, copy=False)


def _load_click_template(path: Path, output_sample_rate: int) -> np.ndarray:
    samples, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    template = np.mean(samples, axis=1, dtype=np.float64).astype(np.float32)
    if sample_rate != output_sample_rate:
        template = resample_audio(template, sample_rate, output_sample_rate)
    if template.size == 0 or not np.any(template):
        raise ValueError(f"Click asset has no usable signal: {path}")
    return _bandpass(template, output_sample_rate)


def _template_matches(
    mono: np.ndarray,
    sample_rate: int,
    template: np.ndarray,
    expected_interval: float,
) -> tuple[np.ndarray, np.ndarray]:
    decimation = max(1, int(round(sample_rate / 48000.0)))
    signal = _bandpass(mono, sample_rate)[::decimation].astype(np.float64)
    template = template[::decimation].astype(np.float64)
    if signal.size <= template.size + 2:
        return np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.float64)

    template_energy = float(np.dot(template, template))
    if template_energy <= 0.0:
        return np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.float64)
    downsampled_rate = sample_rate / decimation
    window_size = min(signal.size, int(round(120.0 * downsampled_rate)))
    if window_size <= template.size + 2:
        return np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.float64)

    window_starts = sorted(
        {
            0,
            max(0, (signal.size - window_size) // 2),
            max(0, signal.size - window_size),
        }
    )
    detected_times: list[float] = []
    detected_levels: list[float] = []
    distance = max(1, int(round(expected_interval * downsampled_rate * 0.55)))
    template_reversed = template[::-1]
    normalizer = np.ones(template.size, dtype=np.float64)

    for window_start in window_starts:
        window = signal[window_start : window_start + window_size]
        correlation = fftconvolve(window, template_reversed, mode="valid")
        energy = fftconvolve(window * window, normalizer, mode="valid")
        scores = np.zeros_like(correlation, dtype=np.float64)
        valid_energy = energy > template_energy * 0.02
        scores[valid_energy] = correlation[valid_energy] / np.sqrt(
            energy[valid_energy] * template_energy
        )
        peaks, properties = find_peaks(
            scores,
            height=MATCH_SCORE_THRESHOLD,
            distance=distance,
            prominence=0.05,
        )
        detected_times.extend(
            (window_start + peaks).astype(np.float64).tolist()
        )
        # The normalized correlation is useful for finding clicks, but its
        # value changes with unrelated music energy. Use the matched-filter
        # coefficient for the equal-volume measurement instead.
        detected_levels.extend(
            (correlation[peaks] / template_energy).astype(np.float64).tolist()
        )

    if not detected_times:
        return np.zeros(0, dtype=np.float64), np.zeros(0, dtype=np.float64)
    order = np.argsort(np.asarray(detected_times, dtype=np.float64))
    raw_times = np.asarray(detected_times, dtype=np.float64)[order] / downsampled_rate
    raw_levels = np.asarray(detected_levels, dtype=np.float64)[order]
    times: list[float] = []
    levels: list[float] = []
    dedupe_distance = expected_interval * 0.25
    for time, level in zip(raw_times, raw_levels, strict=True):
        if times and time - times[-1] < dedupe_distance:
            if level > levels[-1]:
                times[-1] = float(time)
                levels[-1] = float(level)
            continue
        times.append(float(time))
        levels.append(float(level))
    return np.asarray(times), np.asarray(levels)


def _match_to_expected_grid(
    detected_times: np.ndarray,
    detected_levels: np.ndarray,
    expected_interval: float,
    duration: float,
) -> dict[str, object]:
    if detected_times.size == 0:
        return {
            "expected_interval_seconds": expected_interval,
            "actual_interval_seconds": None,
            "actual_cadence_spm": None,
            "phase_seconds": None,
            "expected_click_count": 0,
            "matched_click_count": 0,
            "match_ratio": 0.0,
            "missing_click_count": 0,
            "extra_peak_count": 0,
            "p50_ms": None,
            "p95_ms": None,
            "end_drift_ms": None,
            "odd_even_peak_ratio": None,
        }

    if detected_times.size >= 2:
        actual_interval = float(np.median(np.diff(detected_times)))
        actual_cadence = 60.0 / actual_interval if actual_interval > 0 else None
    else:
        actual_interval = None
        actual_cadence = None

    expected_count = max(1, int(round(duration / expected_interval)))
    phase = float(np.mod(detected_times[0], expected_interval))
    expected_times = detected_times[0] + np.arange(
        detected_times.size, dtype=np.float64
    ) * expected_interval
    residuals = detected_times - expected_times

    # Fit the observed detections to their own uniform grid. This separates
    # detector coverage from the independent target-grid drift check below:
    # a small sample-clock offset should not masquerade as missing clicks,
    # while a wrong cadence must still produce large target-grid residuals.
    if detected_times.size >= 2:
        indexes = np.arange(detected_times.size, dtype=np.float64)
        fitted_slope, fitted_intercept = np.polyfit(indexes, detected_times, 1)
        fitted_times = fitted_intercept + fitted_slope * indexes
        fitted_residuals = detected_times - fitted_times
        matched_count = int(
            np.count_nonzero(np.abs(fitted_residuals) <= GRID_TOLERANCE_SECONDS)
        )
    else:
        matched_count = 1

    if detected_levels.size >= 2:
        odd = float(np.median(detected_levels[::2]))
        even = float(np.median(detected_levels[1::2]))
        odd_even_ratio = min(odd, even) / max(odd, even) if max(odd, even) else 0.0
    else:
        odd_even_ratio = None

    detected_count = int(detected_times.size)
    return {
        "expected_interval_seconds": expected_interval,
        "actual_interval_seconds": actual_interval,
        "actual_cadence_spm": actual_cadence,
        "phase_seconds": phase,
        "expected_click_count": expected_count,
        "matched_click_count": matched_count,
        "match_ratio": min(1.0, matched_count / expected_count),
        "missing_click_count": max(0, expected_count - detected_count),
        "extra_peak_count": max(0, detected_count - expected_count),
        "p50_ms": float(np.percentile(np.abs(residuals) * 1000.0, 50)),
        "p95_ms": float(np.percentile(np.abs(residuals) * 1000.0, 95)),
        "end_drift_ms": abs(float(residuals[-1] - residuals[0])) * 1000.0,
        "odd_even_peak_ratio": odd_even_ratio,
    }


def measure_click_grid(
    samples: np.ndarray,
    sample_rate: int,
    expected_bpm: float,
    click_template: np.ndarray,
) -> dict[str, object]:
    expected_interval = 30.0 / expected_bpm
    mono = np.mean(samples, axis=1, dtype=np.float64).astype(np.float32)
    detected_times, detected_levels = _template_matches(
        mono,
        sample_rate,
        click_template,
        expected_interval,
    )
    return _match_to_expected_grid(
        detected_times,
        detected_levels,
        expected_interval,
        samples.shape[0] / sample_rate,
    )


def analyze_only(path: Path, click_file: Path) -> dict[str, object]:
    result = subprocess.run(
        [
            sys.executable,
            "-W",
            "error",
            str(SCRIPT_PATH),
            "--input",
            str(path),
            "--click-file",
            str(click_file),
            "--analyze-only",
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        return {"error": result.stderr.strip() or "analyze-only failed"}
    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError:
        return {"error": "analyze-only returned invalid JSON"}
    analysis = payload.get("analysis", {})
    recommendation = payload.get("recommendation", {})
    return {
        "raw_bpm": analysis.get("raw_bpm"),
        "source_bpm": analysis.get("source_bpm"),
        "beat_count": analysis.get("beat_count"),
        "observed_beat_ratio": analysis.get("observed_beat_ratio"),
        "max_missing_beat_run": analysis.get("max_missing_beat_run"),
        "grid_error_p50_ms": analysis.get("grid_error_p50_ms"),
        "grid_error_p95_ms": analysis.get("grid_error_p95_ms"),
        "estimated_end_drift_ms": analysis.get("estimated_end_drift_ms"),
        "confidence": analysis.get("confidence"),
        "recommended_target_bpm": recommendation.get("target_bpm"),
        "recommended_tempo_mode": recommendation.get("tempo_mode"),
        "predicted_alignment": recommendation.get("predicted_alignment"),
    }


def check_track(
    info: object,
    samples: np.ndarray,
    expected_bpm: float | None,
    click_measurement: dict[str, object],
) -> dict[str, object]:
    peak = _peak_dbfs(samples)
    checks = {
        "sample_rate": bool(info.samplerate == EXPECTED_SAMPLE_RATE),
        "channels": bool(info.channels == EXPECTED_CHANNELS),
        "subtype": bool(info.subtype == EXPECTED_SUBTYPE),
        "finite_samples": bool(np.all(np.isfinite(samples))),
        "peak_ceiling": bool(peak <= -1.0 + PEAK_TOLERANCE_DB),
    }
    if expected_bpm is not None:
        actual_cadence = click_measurement["actual_cadence_spm"]
        checks.update(
            {
                "cadence": bool(
                    actual_cadence is not None
                    and abs(float(actual_cadence) - expected_bpm * 2.0)
                    <= CADENCE_TOLERANCE_SPM
                ),
                "click_match_ratio": bool(
                    float(click_measurement["match_ratio"]) >= MIN_MATCH_RATIO
                ),
                "alignment_p95": bool(
                    click_measurement["p95_ms"] is not None
                    and float(click_measurement["p95_ms"]) <= 30.0
                ),
                "alignment_end_drift": bool(
                    click_measurement["end_drift_ms"] is not None
                    and float(click_measurement["end_drift_ms"]) <= 50.0
                ),
                "click_equal_volume": bool(
                    click_measurement["odd_even_peak_ratio"] is not None
                    and float(click_measurement["odd_even_peak_ratio"]) >= 0.99
                ),
            }
        )
    checks["passed"] = all(bool(value) for value in checks.values())
    return {
        "sample_rate": info.samplerate,
        "channels": info.channels,
        "subtype": info.subtype,
        "frames": info.frames,
        "duration_seconds": info.frames / info.samplerate,
        "peak_dbfs": peak,
        "expected_bpm_from_filename": expected_bpm,
        "click": click_measurement,
        "checks": checks,
    }


def run(args: argparse.Namespace) -> int:
    corpus = args.corpus.resolve()
    click_file = args.click_file.resolve()
    if not corpus.is_dir():
        raise SystemExit(f"Corpus directory does not exist: {corpus}")
    if not click_file.is_file():
        raise SystemExit(f"Click asset does not exist: {click_file}")

    tracks = sorted(corpus.glob("*.wav"), key=lambda path: path.name.lower())
    results: list[dict[str, object]] = []
    for path in tracks:
        info = sf.info(path)
        samples, sample_rate = sf.read(path, dtype="float32", always_2d=True)
        expected_bpm = _expected_bpm(path)
        click_measurement = (
            measure_click_grid(
                samples,
                sample_rate,
                expected_bpm,
                _load_click_template(click_file, sample_rate),
            )
            if expected_bpm is not None
            else {}
        )
        track: dict[str, object] = {
            "file": path.name,
            "measurement": check_track(
                info, samples, expected_bpm, click_measurement
            ),
        }
        if not args.skip_analysis:
            track["analysis"] = analyze_only(path, click_file)
        results.append(track)

    payload = {
        "track_count": len(results),
        "files": [track["file"] for track in results],
        "tracks": results,
        "passed": bool(
            results
            and all(
                bool(track["measurement"]["checks"]["passed"])
                for track in results
            )
        ),
    }
    output_path = args.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    serialized = json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)
    output_path.write_text(serialized + "\n", encoding="utf-8")
    print(serialized)
    return 0 if payload["passed"] else 3


if __name__ == "__main__":
    raise SystemExit(run(parse_args()))
