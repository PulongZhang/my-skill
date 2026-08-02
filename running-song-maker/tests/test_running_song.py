from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np
import soundfile as sf


SKILL_DIR = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = SKILL_DIR / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from lib.audio_io import (  # noqa: E402
    AudioProcessingError,
    decode_audio,
    output_sample_rate,
    peak_dbfs,
    resolve_output_spec,
    write_output_audio,
)
from lib.click_track import (  # noqa: E402
    click_sample_positions,
    generate_click_track,
    load_click_asset,
    mix_fixed_click,
)
from lib.tempo_analysis import (  # noqa: E402
    _max_missing_beat_run,
    _observation_metrics,
    _resolve_source_bpm,
    _snap_beats_to_onsets,
    analyze_tempo,
    choose_target_bpm,
    normalize_bpm,
    transformed_alignment,
)
from lib.tempo_stretch import (  # noqa: E402
    _monotonic_beat_ordinals,
    atempo_filter,
    build_time_map,
)


CLICK_PATH = SKILL_DIR / "assets" / "running_wood_click_580hz_soft6ms.wav"
SCRIPT_PATH = SCRIPTS_DIR / "make_running_song.py"


def run_cli(*arguments: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, "-W", "error", str(SCRIPT_PATH), *arguments],
        capture_output=True,
        text=True,
        check=False,
    )


def synthetic_song(sample_rate: int = 22050, duration: float = 24.0) -> np.ndarray:
    frame_count = int(sample_rate * duration)
    time = np.arange(frame_count, dtype=np.float64) / sample_rate
    music = 0.04 * np.sin(2.0 * np.pi * 220.0 * time)
    pulse_length = int(0.04 * sample_rate)
    envelope = np.exp(-np.arange(pulse_length) / (0.008 * sample_rate))
    pulse = 0.55 * envelope * np.sin(
        2.0 * np.pi * 110.0 * np.arange(pulse_length) / sample_rate
    )
    for beat_time in np.arange(0.5, duration, 60.0 / 90.0):
        start = int(round(beat_time * sample_rate))
        end = min(frame_count, start + pulse_length)
        music[start:end] += pulse[: end - start]
    stereo = np.column_stack((music, music * 0.98))
    return stereo.astype(np.float32)


class ClickAssetTests(unittest.TestCase):
    def test_asset_uses_descriptive_name_and_expected_audio_shape(self):
        self.assertTrue(CLICK_PATH.is_file())
        samples, sample_rate = sf.read(CLICK_PATH, dtype="float32", always_2d=True)
        self.assertEqual(sample_rate, 22050)
        self.assertEqual(samples.shape[1], 1)
        self.assertAlmostEqual(samples.shape[0] / sample_rate, 0.18, places=3)
        self.assertLess(peak_dbfs(samples), -6.0)

    def test_asset_spectral_centroid_matches_reference_character(self):
        samples, sample_rate = sf.read(CLICK_PATH, dtype="float64")
        windowed = samples * np.hanning(samples.size)
        magnitude = np.abs(np.fft.rfft(windowed))
        frequencies = np.fft.rfftfreq(samples.size, 1.0 / sample_rate)
        audible = frequencies >= 20.0
        centroid = float(
            np.sum(frequencies[audible] * magnitude[audible])
            / np.sum(magnitude[audible])
        )
        self.assertGreater(centroid, 630.0)
        self.assertLess(centroid, 690.0)


class TempoRuleTests(unittest.TestCase):
    def test_normalizes_half_and_double_tempo(self):
        self.assertEqual(normalize_bpm(45.0), 90.0)
        self.assertEqual(normalize_bpm(190.0), 95.0)

    def test_auto_target_prefers_closest_running_bpm(self):
        self.assertEqual(choose_target_bpm(92.0), 90.0)
        self.assertEqual(choose_target_bpm(93.0), 95.0)

    def test_click_positions_use_direct_sample_formula(self):
        sample_rate = 48000
        duration = 300.0
        frame_count = int(sample_rate * duration)
        positions, times = click_sample_positions(
            frame_count, sample_rate, target_bpm=95.0, anchor_seconds=0.173
        )
        expected = np.rint(times * sample_rate).astype(np.int64)
        np.testing.assert_array_equal(positions, expected)
        actual_last = positions[-1] / sample_rate
        self.assertLessEqual(abs(actual_last - times[-1]), 0.5 / sample_rate)
        self.assertAlmostEqual(60.0 / (30.0 / 95.0), 190.0)


class ObservationEvidenceTests(unittest.TestCase):
    def test_missing_ordinal_runs_are_reported(self):
        missing = _max_missing_beat_run(
            np.arange(0, 12, dtype=np.int64),
            np.asarray([0, 1, 2, 8, 9, 10], dtype=np.int64),
        )
        self.assertEqual(missing, 5)

    def test_missing_onset_is_not_replaced_by_theoretical_grid_point(self):
        envelope = np.zeros(100, dtype=np.float64)
        envelope[11] = 1.0
        envelope[31] = 1.0
        frames, ordinals = _snap_beats_to_onsets(
            envelope,
            np.asarray([11, 21, 31], dtype=np.int64),
            np.asarray([0, 1, 2], dtype=np.int64),
            period_frames=20.0,
            snap_fraction=0.1,
        )
        np.testing.assert_array_equal(frames, np.asarray([11, 31]))
        np.testing.assert_array_equal(ordinals, np.asarray([0, 2]))

    def test_observation_metrics_keep_ordinal_gaps_in_drift_measurement(self):
        p50, p95, end_drift = _observation_metrics(
            np.asarray([0.0, 1.0, 2.1]),
            np.asarray([0, 2, 4]),
            anchor_seconds=0.0,
            period_seconds=0.5,
        )
        self.assertAlmostEqual(p50, 0.0, places=6)
        self.assertAlmostEqual(p95, 90.0, places=6)
        self.assertAlmostEqual(end_drift, 100.0, places=6)

    def test_source_bpm_resolution_has_no_target_preference_argument(self):
        period_frames = 60.0 / 110.0 * 22050.0 / 512.0
        envelope = np.zeros(2200, dtype=np.float64)
        for frame in np.arange(20.0, envelope.size - 20.0, period_frames):
            center = int(round(frame))
            envelope[center] = 1.0
        resolution = _resolve_source_bpm(
            envelope,
            [(110.0, 1.0), (90.0, 0.2)],
        )
        self.assertAlmostEqual(resolution.source_bpm, 110.0, delta=1.5)


class OutputFormatTests(unittest.TestCase):
    def test_unknown_output_extension_is_rejected_before_encoding(self):
        with self.assertRaises(AudioProcessingError):
            resolve_output_spec(Path("output.unknown"), 48000)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required for codec matrix")
    def test_codec_matrix_redecodes_and_opus_uses_48_khz(self):
        sample_rate = 22050
        time = np.arange(sample_rate, dtype=np.float32) / sample_rate
        samples = np.column_stack(
            (
                0.1 * np.sin(2.0 * np.pi * 220.0 * time),
                0.1 * np.sin(2.0 * np.pi * 330.0 * time),
            )
        ).astype(np.float32)
        suffixes = (".wav", ".flac", ".mp3", ".m4a", ".aac", ".opus")
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            for suffix in suffixes:
                output_path = directory / f"output{suffix}"
                temporary_wav = directory / f"master{suffix}.wav"
                spec = write_output_audio(
                    output_path, samples, sample_rate, temporary_wav
                )
                decoded, decoded_rate = decode_audio(
                    output_path, directory / f"decoded{suffix}.wav"
                )
                self.assertEqual(decoded.shape[1], 2)
                self.assertEqual(
                    decoded_rate,
                    output_sample_rate(spec, sample_rate),
                )
                if suffix == ".opus":
                    self.assertEqual(decoded_rate, 48000)

    @unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required for MP3 rate test")
    def test_mp3_output_plan_resamples_high_rate_input(self):
        sample_rate = 96000
        time = np.arange(sample_rate // 10, dtype=np.float32) / sample_rate
        samples = np.column_stack(
            (
                0.1 * np.sin(2.0 * np.pi * 220.0 * time),
                0.1 * np.sin(2.0 * np.pi * 330.0 * time),
            )
        ).astype(np.float32)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            output_path = directory / "output.mp3"
            spec = write_output_audio(
                output_path,
                samples,
                sample_rate,
                directory / "master.wav",
            )
            _, decoded_rate = decode_audio(output_path, directory / "decoded.wav")
            self.assertEqual(decoded_rate, 48000)
            self.assertEqual(output_sample_rate(spec, sample_rate), 48000)


class ClickMixTests(unittest.TestCase):
    def test_clicks_are_equal_volume_and_music_is_reduced_without_clipping(self):
        sample_rate = 22050
        frame_count = sample_rate * 8
        music = np.full((frame_count, 2), 0.7, dtype=np.float32)
        asset = load_click_asset(CLICK_PATH, sample_rate)
        track = generate_click_track(
            frame_count,
            channels=2,
            sample_rate=sample_rate,
            target_bpm=95.0,
            anchor_seconds=0.2,
            click_asset=asset,
            click_peak_dbfs=-6.0,
        )
        self.assertAlmostEqual(track.odd_even_peak_ratio, 1.0, places=7)
        self.assertAlmostEqual(track.peak_dbfs, -6.0, places=4)

        result = mix_fixed_click(
            music,
            track.samples,
            click_peak_dbfs=-6.0,
            click_over_music_rms_db=16.0,
            output_peak_ceiling_dbfs=-1.0,
        )
        self.assertLess(result.music_gain_db, 0.0)
        self.assertLessEqual(result.mixed_peak_dbfs, -1.0 + 1e-6)
        self.assertFalse(result.clipped)


class StretchPlanTests(unittest.TestCase):
    def test_global_alignment_is_exact_for_constant_tempo_speedup(self):
        beat_times = np.arange(0.5, 250.0, 60.0 / 90.0)
        result = transformed_alignment(
            beat_times,
            anchor_input=0.5,
            stretch_ratio=95.0 / 90.0,
            target_bpm=95.0,
            strict=False,
        )
        self.assertLessEqual(result["predicted_p95_ms"], 2.0)
        self.assertLessEqual(result["estimated_end_drift_ms"], 2.0)
        self.assertTrue(result["passed"])

    def test_global_alignment_is_exact_for_constant_tempo_slowdown(self):
        beat_times = np.arange(0.5, 250.0, 60.0 / 95.0)
        result = transformed_alignment(
            beat_times,
            anchor_input=0.5,
            stretch_ratio=90.0 / 95.0,
            target_bpm=90.0,
            strict=False,
        )
        self.assertLessEqual(result["predicted_p95_ms"], 2.0)
        self.assertLessEqual(result["estimated_end_drift_ms"], 2.0)
        self.assertTrue(result["passed"])

    def test_monotonic_ordinals_handle_gradual_tempo_drift(self):
        durations = np.full(270, 60.0 / 95.0) * np.linspace(0.95, 1.05, 270)
        beat_times = np.concatenate(([0.5], 0.5 + np.cumsum(durations)))
        ordinals = _monotonic_beat_ordinals(
            beat_times, anchor_seconds=0.5, source_bpm=95.0
        )
        self.assertTrue(np.all(np.diff(ordinals) >= 1))
        self.assertAlmostEqual(float(np.max(ordinals) - np.min(ordinals)), 270.0, delta=1.0)

    def test_ffmpeg_filter_keeps_each_stage_in_quality_range(self):
        expression = atempo_filter(4.5)
        factors = [float(item.split("=")[1]) for item in expression.split(",")]
        self.assertTrue(all(0.5 <= factor <= 2.0 for factor in factors))
        self.assertAlmostEqual(float(np.prod(factors)), 4.5)

    def test_time_map_avoids_zero_zero_and_is_monotonic(self):
        beat_times = np.arange(0.5, 30.0, 60.0 / 91.0)
        time_map = build_time_map(
            beat_times=beat_times,
            source_bpm=91.0,
            target_bpm=90.0,
            anchor_input_seconds=float(beat_times[0]),
            source_duration_seconds=30.0,
            sample_rate=48000,
        )
        self.assertNotEqual(time_map.frame_pairs[0], (0, 0))
        sources = [pair[0] for pair in time_map.frame_pairs]
        targets = [pair[1] for pair in time_map.frame_pairs]
        self.assertTrue(all(a < b for a, b in zip(sources, sources[1:])))
        self.assertTrue(all(a < b for a, b in zip(targets, targets[1:])))
        self.assertLessEqual(time_map.predicted_p95_ms, 30.0)

    def test_terminal_truncated_click_is_omitted(self):
        sample_rate = 22050
        asset = load_click_asset(CLICK_PATH, sample_rate)
        frame_count = int(sample_rate * 0.2)
        track = generate_click_track(
            frame_count,
            channels=2,
            sample_rate=sample_rate,
            target_bpm=95.0,
            anchor_seconds=0.01,
            click_asset=asset,
            click_peak_dbfs=-6.0,
        )
        self.assertLessEqual(track.positions[-1], frame_count - asset.size)
        self.assertGreaterEqual(track.rendered_peak_dbfs, -8.0)


class AnalysisAndCliTests(unittest.TestCase):
    def test_synthetic_song_analysis_finds_running_tempo(self):
        sample_rate = 22050
        song = synthetic_song(sample_rate)
        analysis = analyze_tempo(song, sample_rate)
        self.assertGreater(analysis.source_bpm, 88.0)
        self.assertLess(analysis.source_bpm, 92.0)
        self.assertGreaterEqual(analysis.beat_times.size, 20)

    def test_cli_help_has_no_warnings(self):
        result = run_cli("--help")
        self.assertEqual(result.returncode, 0, msg=result.stderr)
        self.assertIn("--target-bpm", result.stdout)

    def test_analyze_only_does_not_require_click_asset(self):
        sample_rate = 22050
        song = synthetic_song(sample_rate)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            input_path = directory / "synthetic.wav"
            sf.write(input_path, song, sample_rate, subtype="PCM_16")
            result = run_cli(
                "--input",
                str(input_path),
                "--click-file",
                str(directory / "missing-click.wav"),
                "--analyze-only",
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr)
            payload = json.loads(result.stdout)
            self.assertIn("analysis", payload)

    def test_cli_generates_no_stretch_wav_and_report(self):
        sample_rate = 22050
        song = synthetic_song(sample_rate)
        analysis = analyze_tempo(song, sample_rate)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            input_path = directory / "synthetic.wav"
            output_path = directory / "synthetic-running.wav"
            sf.write(input_path, song, sample_rate, subtype="PCM_16")
            result = run_cli(
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--target-bpm",
                f"{analysis.source_bpm:.12f}",
                "--tempo-mode",
                "global",
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr + result.stdout)
            report_path = output_path.with_suffix(".wav.report.json")
            self.assertTrue(output_path.is_file())
            self.assertTrue(report_path.is_file())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertTrue(report["passed"])
            self.assertEqual(report["processing"]["engine"], "none")
            self.assertAlmostEqual(report["click"]["rate_per_minute"], 180.0, delta=4.0)
            self.assertFalse(report["loudness"]["clipped"])
            self.assertAlmostEqual(report["click"]["odd_even_peak_ratio"], 1.0, places=4)

    def test_cli_rejects_non_finite_loudness_arguments(self):
        sample_rate = 22050
        song = synthetic_song(sample_rate)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            input_path = directory / "synthetic.wav"
            output_path = directory / "synthetic-running.wav"
            sf.write(input_path, song, sample_rate, subtype="PCM_16")
            result = run_cli(
                "--input",
                str(input_path),
                "--output",
                str(output_path),
                "--target-bpm",
                "95",
                "--tempo-mode",
                "global",
                "--output-peak-dbfs",
                "nan",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(output_path.exists())
            self.assertIn("must be finite", result.stderr)

    def test_cli_rejects_path_collisions_between_output_and_report(self):
        sample_rate = 22050
        song = synthetic_song(sample_rate)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            input_path = directory / "synthetic.wav"
            sf.write(input_path, song, sample_rate, subtype="PCM_16")
            collision = directory / "same.wav"
            result = run_cli(
                "--input",
                str(input_path),
                "--output",
                str(collision),
                "--report",
                str(collision),
                "--target-bpm",
                "95",
                "--tempo-mode",
                "global",
            )
            self.assertNotEqual(result.returncode, 0)
            self.assertFalse(collision.exists())
            self.assertIn("must be distinct", result.stderr)

    def test_cli_rejects_max_stretch_above_twelve_percent(self):
        result = run_cli(
            "--input",
            "missing.wav",
            "--max-stretch-percent",
            "12.1",
        )
        self.assertEqual(result.returncode, 2)
        self.assertIn("between 0 and 12", result.stderr)

    def test_default_output_respects_explicit_report_path(self):
        sample_rate = 22050
        song = synthetic_song(sample_rate)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            input_path = directory / "synthetic.wav"
            report_path = directory / "custom-report.json"
            sf.write(input_path, song, sample_rate, subtype="PCM_16")
            result = run_cli(
                "--input",
                str(input_path),
                "--target-bpm",
                "90",
                "--tempo-mode",
                "global",
                "--report",
                str(report_path),
            )
            self.assertEqual(result.returncode, 0, msg=result.stderr + result.stdout)
            output_path = directory / "synthetic(90bpm).wav"
            self.assertTrue(output_path.is_file())
            self.assertTrue(report_path.is_file())
            report = json.loads(report_path.read_text(encoding="utf-8"))
            self.assertEqual(
                report["output"]["report_path"], str(report_path.resolve())
            )

    def test_cli_rejects_click_asset_collision(self):
        sample_rate = 22050
        song = synthetic_song(sample_rate)
        with tempfile.TemporaryDirectory() as temporary:
            directory = Path(temporary)
            input_path = directory / "synthetic.wav"
            sf.write(input_path, song, sample_rate, subtype="PCM_16")
            result = run_cli(
                "--input",
                str(input_path),
                "--output",
                str(CLICK_PATH),
                "--target-bpm",
                "90",
                "--tempo-mode",
                "global",
            )
            self.assertEqual(result.returncode, 2)
            self.assertIn("click and output", result.stderr.lower())


if __name__ == "__main__":
    unittest.main()
