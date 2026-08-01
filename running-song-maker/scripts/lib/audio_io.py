from __future__ import annotations

import locale
import math
import shutil
import subprocess
from pathlib import Path

import numpy as np
import soundfile as sf
from scipy.signal import correlate, correlation_lags


class AudioProcessingError(RuntimeError):
    """Raised when an audio file cannot be decoded, encoded, or validated."""


def find_executable(name: str) -> str | None:
    return shutil.which(name)


def require_executable(name: str) -> str:
    executable = find_executable(name)
    if executable is None:
        raise AudioProcessingError(
            f"Required executable '{name}' was not found on PATH."
        )
    return executable


def _decode_process_output(data: bytes) -> str:
    if not data:
        return ""
    try:
        return data.decode("utf-8")
    except UnicodeDecodeError:
        return data.decode(locale.getpreferredencoding(False), errors="replace")


def run_command(command: list[str], description: str) -> None:
    result = subprocess.run(command, capture_output=True, text=False, check=False)
    if result.returncode != 0:
        detail = _decode_process_output(result.stderr or result.stdout).strip()
        if not detail:
            detail = f"process exited with status {result.returncode}"
        raise AudioProcessingError(f"{description} failed: {detail}")


def _validate_audio(samples: np.ndarray, sample_rate: int, source: Path) -> np.ndarray:
    audio = np.asarray(samples, dtype=np.float32)
    if audio.ndim == 1:
        audio = audio[:, np.newaxis]
    if audio.ndim != 2 or audio.shape[0] == 0 or audio.shape[1] == 0:
        raise AudioProcessingError(f"Audio is empty or has invalid dimensions: {source}")
    if sample_rate <= 0:
        raise AudioProcessingError(f"Audio has an invalid sample rate: {source}")
    if not np.all(np.isfinite(audio)):
        raise AudioProcessingError(f"Audio contains NaN or infinite samples: {source}")
    return audio


def _read_audio(path: Path) -> tuple[np.ndarray, int]:
    samples, sample_rate = sf.read(path, dtype="float32", always_2d=True)
    return _validate_audio(samples, sample_rate, path), int(sample_rate)


def decode_audio(input_path: Path, decoded_wav: Path | None = None) -> tuple[np.ndarray, int]:
    input_path = input_path.resolve()
    if not input_path.is_file():
        raise AudioProcessingError(f"Input audio does not exist: {input_path}")

    try:
        return _read_audio(input_path)
    except (RuntimeError, sf.LibsndfileError):
        if decoded_wav is None:
            raise AudioProcessingError(
                f"libsndfile cannot decode {input_path.suffix}; provide a temporary WAV path "
                "so FFmpeg can decode it."
            ) from None

    ffmpeg = require_executable("ffmpeg")
    decoded_wav.parent.mkdir(parents=True, exist_ok=True)
    run_command(
        [
            ffmpeg,
            "-v",
            "error",
            "-y",
            "-i",
            str(input_path),
            "-vn",
            "-c:a",
            "pcm_f32le",
            str(decoded_wav),
        ],
        "FFmpeg audio decode",
    )
    return _read_audio(decoded_wav)


def write_pcm_wav(path: Path, samples: np.ndarray, sample_rate: int) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    sf.write(path, samples, sample_rate, format="WAV", subtype="FLOAT")


def _ffmpeg_audio_codec(output_path: Path) -> list[str]:
    suffix = output_path.suffix.lower()
    if suffix == ".mp3":
        return ["-c:a", "libmp3lame", "-q:a", "2"]
    if suffix in {".m4a", ".aac"}:
        return ["-c:a", "aac", "-b:a", "256k"]
    if suffix == ".opus":
        return ["-c:a", "libopus", "-b:a", "192k"]
    return []


def write_output_audio(
    output_path: Path,
    samples: np.ndarray,
    sample_rate: int,
    temporary_wav: Path,
) -> None:
    output_path = output_path.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    suffix = output_path.suffix.lower()

    if suffix in {".wav", ".flac"}:
        sf.write(
            output_path,
            samples,
            sample_rate,
            format=suffix.removeprefix(".").upper(),
            subtype="PCM_24",
        )
        return

    ffmpeg = require_executable("ffmpeg")
    sf.write(temporary_wav, samples, sample_rate, format="WAV", subtype="PCM_24")
    command = [
        ffmpeg,
        "-v",
        "error",
        "-y",
        "-i",
        str(temporary_wav),
        "-vn",
        *_ffmpeg_audio_codec(output_path),
        str(output_path),
    ]
    run_command(command, "FFmpeg audio encode")


def duration_seconds(samples: np.ndarray, sample_rate: int) -> float:
    return float(samples.shape[0] / sample_rate)


def rms_dbfs(samples: np.ndarray) -> float:
    audio = np.asarray(samples, dtype=np.float64)
    if audio.size == 0:
        return float("-inf")
    rms = float(np.sqrt(np.mean(np.square(audio))))
    if rms <= 0:
        return float("-inf")
    return 20.0 * math.log10(rms)


def peak_dbfs(samples: np.ndarray) -> float:
    audio = np.asarray(samples, dtype=np.float64)
    if audio.size == 0:
        return float("-inf")
    peak = float(np.max(np.abs(audio)))
    if peak <= 0:
        return float("-inf")
    return 20.0 * math.log10(peak)


def gain_amplitude(gain_db: float) -> float:
    return 10.0 ** (gain_db / 20.0)


def apply_gain(samples: np.ndarray, gain_db: float) -> np.ndarray:
    return np.asarray(samples, dtype=np.float32) * gain_amplitude(gain_db)


def estimate_delay_samples(
    reference: np.ndarray,
    actual: np.ndarray,
    sample_rate: int,
    analysis_seconds: float = 5.0,
    maximum_delay_seconds: float = 0.25,
) -> int:
    """Estimate whole-file codec delay from a short mono cross-correlation."""
    if sample_rate <= 0:
        raise ValueError("Sample rate must be positive")
    reference_mono = np.mean(reference, axis=1) if reference.ndim == 2 else reference
    actual_mono = np.mean(actual, axis=1) if actual.ndim == 2 else actual
    reference_frames = min(reference_mono.size, int(sample_rate * analysis_seconds))
    maximum_lag = int(sample_rate * maximum_delay_seconds)
    actual_frames = min(actual_mono.size, reference_frames + maximum_lag)
    if reference_frames < 2 or actual_frames < 2:
        return 0

    reference_window = np.asarray(reference_mono[:reference_frames], dtype=np.float64)
    actual_window = np.asarray(actual_mono[:actual_frames], dtype=np.float64)
    reference_window -= np.mean(reference_window)
    actual_window -= np.mean(actual_window)
    if not np.any(reference_window) or not np.any(actual_window):
        return 0

    correlation = correlate(actual_window, reference_window, mode="full", method="fft")
    lags = correlation_lags(actual_window.size, reference_window.size, mode="full")
    allowed = np.abs(lags) <= maximum_lag
    if not np.any(allowed):
        return 0
    allowed_indexes = np.flatnonzero(allowed)
    best = allowed_indexes[int(np.argmax(np.abs(correlation[allowed])))]
    return int(lags[best])
