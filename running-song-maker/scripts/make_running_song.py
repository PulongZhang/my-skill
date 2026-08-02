#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import os
import sys
import tempfile
from pathlib import Path

import numpy as np

from lib.audio_io import (
    AudioProcessingError,
    decode_audio,
    duration_seconds,
    estimate_delay_samples,
    output_sample_rate,
    peak_dbfs,
    resample_audio,
    resolve_output_spec,
    write_output_audio,
    write_pcm_wav,
)
from lib.click_track import (
    ClickTrackError,
    generate_click_track,
    load_click_asset,
    mix_fixed_click,
)
from lib.tempo_analysis import (
    TempoAnalysis,
    TempoAnalysisError,
    alignment_result,
    analyze_tempo,
    fit_click_grid,
    parse_target_bpm,
    transformed_alignment,
)
from lib.tempo_stretch import (
    TempoStretchError,
    build_time_map,
    choose_engine,
    stretch_audio_file,
    write_time_map,
)


SKILL_DIR = Path(__file__).resolve().parents[1]
DEFAULT_CLICK = SKILL_DIR / "assets" / "running_wood_click_580hz_soft6ms.wav"
LOW_CONFIDENCE_THRESHOLD = 0.35
MAX_UNCONFIRMED_STRETCH_PERCENT = 12.0
STRICT_GRID_ERROR_P95_MS = 25.0
STRICT_END_DRIFT_MS = 50.0
PEAK_VALIDATION_TOLERANCE_DB = 0.05
CLICK_RATE_TOLERANCE_SPM = 0.5
LOSSY_DURATION_TOLERANCE_SECONDS = 0.02
LOSSY_DELAY_TOLERANCE_SECONDS = 0.02
AUTO_GLOBAL_MIN_OBSERVED_RATIO = 0.85
AUTO_GLOBAL_MAX_MISSING_BEAT_RUN = 8


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=(
            "Create a pitch-preserving, cadence-aligned running-song mix with a fixed "
            "equal-volume click track."
        )
    )
    parser.add_argument("--input", required=True, type=Path, help="Source song path")
    parser.add_argument(
        "--output",
        type=Path,
        help=(
            "Output path; defaults to <原歌曲名>(<bpm>bpm).wav next to the input"
        ),
    )
    parser.add_argument(
        "--target-bpm",
        default="auto",
        help="Target music BPM, or 'auto' to choose between 90 and 95",
    )
    parser.add_argument(
        "--first-beat",
        type=float,
        help="Manual quarter-note beat anchor in source seconds",
    )
    parser.add_argument(
        "--tempo-mode",
        choices=("auto", "global", "strict"),
        default="auto",
        help="Use one global stretch or a Rubber Band beat time map",
    )
    parser.add_argument(
        "--engine",
        choices=("auto", "rubberband", "ffmpeg"),
        default="auto",
        help="Pitch-preserving stretch engine",
    )
    parser.add_argument(
        "--click-file",
        type=Path,
        default=DEFAULT_CLICK,
        help="Fixed click WAV asset",
    )
    parser.add_argument(
        "--click-peak-dbfs",
        type=float,
        default=-6.0,
        help="Fixed click peak level in dBFS",
    )
    parser.add_argument(
        "--click-over-rms-db",
        type=float,
        default=16.0,
        help="Click peak above music average RMS",
    )
    parser.add_argument(
        "--output-peak-dbfs",
        type=float,
        default=-1.0,
        help="Maximum mixed sample peak",
    )
    parser.add_argument(
        "--max-stretch-percent",
        type=float,
        default=MAX_UNCONFIRMED_STRETCH_PERCENT,
        help="Stricter speed-change threshold; cannot exceed 12 percent",
    )
    parser.add_argument(
        "--allow-large-stretch",
        action="store_true",
        help="Allow speed changes beyond the configured vocal-safety threshold",
    )
    parser.add_argument(
        "--allow-low-confidence",
        action="store_true",
        help=(
            "Continue when automatic beat confidence is below "
            f"{LOW_CONFIDENCE_THRESHOLD:.2f}"
        ),
    )
    parser.add_argument(
        "--preserve-stereo-width",
        action="store_true",
        help="Disable Rubber Band centre-focus stereo coupling",
    )
    parser.add_argument(
        "--report",
        type=Path,
        help="JSON report path; defaults to <output>.report.json",
    )
    parser.add_argument(
        "--analyze-only",
        action="store_true",
        help="Analyze BPM and recommend settings without creating audio",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacing an existing output and report",
    )
    return parser.parse_args()


def _risk_label(stretch_percent: float) -> str:
    amount = abs(stretch_percent)
    if amount <= 5.0:
        return "low"
    if amount <= 8.0:
        return "moderate"
    if amount <= 12.0:
        return "high"
    return "very-high"


def _tempo_report_fields(
    target_bpm: float,
    stretch_ratio: float,
    stretch_percent: float,
) -> dict[str, float | str]:
    return {
        "target_bpm": target_bpm,
        "cadence_spm": target_bpm * 2.0,
        "stretch_ratio": stretch_ratio,
        "stretch_percent": stretch_percent,
        "vocal_risk": _risk_label(stretch_percent),
    }


def _needs_strict_tempo_map(alignment: dict[str, float | bool]) -> bool:
    return bool(
        float(alignment["predicted_p95_ms"]) > STRICT_GRID_ERROR_P95_MS
        or float(alignment["estimated_end_drift_ms"]) > STRICT_END_DRIFT_MS
    )


def _analysis_payload(
    input_path: Path,
    sample_rate: int,
    channels: int,
    duration: float,
    analysis: TempoAnalysis,
    tempo_fields: dict[str, float | str],
    tempo_mode: str,
    predicted_alignment: dict[str, float | bool],
) -> dict[str, object]:
    return {
        "input": {
            "path": str(input_path.resolve()),
            "sample_rate": sample_rate,
            "channels": channels,
            "duration_seconds": duration,
        },
        "analysis": {
            "raw_bpm": analysis.raw_bpm,
            "source_bpm": analysis.source_bpm,
            "beat_count": int(analysis.beat_times.size),
            "observed_beat_ratio": analysis.observed_beat_ratio,
            "max_missing_beat_run": analysis.max_missing_beat_run,
            "anchor_seconds": analysis.anchor_seconds,
            "anchor_is_manual": analysis.anchor_is_manual,
            "grid_error_p50_ms": analysis.grid_error_p50_ms,
            "grid_error_p95_ms": analysis.grid_error_p95_ms,
            "estimated_end_drift_ms": analysis.estimated_end_drift_ms,
            "confidence": analysis.confidence,
            "candidate_margin": analysis.candidate_margin,
        },
        "recommendation": {
            **tempo_fields,
            "tempo_mode": tempo_mode,
            "predicted_alignment": predicted_alignment,
        },
    }


def _paths_collide(left: Path, right: Path) -> bool:
    if left == right:
        return True
    try:
        return left.exists() and right.exists() and os.path.samefile(left, right)
    except OSError:
        return False


def _validate_numeric_args(args: argparse.Namespace) -> None:
    values = {
        "--click-peak-dbfs": args.click_peak_dbfs,
        "--click-over-rms-db": args.click_over_rms_db,
        "--output-peak-dbfs": args.output_peak_dbfs,
        "--max-stretch-percent": args.max_stretch_percent,
    }
    if args.first_beat is not None:
        values["--first-beat"] = args.first_beat
    for option, value in values.items():
        if not math.isfinite(value):
            raise ValueError(f"{option} must be finite")

    if args.first_beat is not None and args.first_beat < 0:
        raise ValueError("--first-beat must be zero or greater")
    if not -60.0 <= args.click_peak_dbfs <= 0.0:
        raise ValueError("--click-peak-dbfs must be between -60 and 0")
    if not 0.0 < args.click_over_rms_db <= 80.0:
        raise ValueError("--click-over-rms-db must be greater than 0 and at most 80")
    if not -60.0 <= args.output_peak_dbfs <= 0.0:
        raise ValueError("--output-peak-dbfs must be between -60 and 0")
    if not 0.0 <= args.max_stretch_percent <= MAX_UNCONFIRMED_STRETCH_PERCENT:
        raise ValueError(
            "--max-stretch-percent must be between 0 and "
            f"{MAX_UNCONFIRMED_STRETCH_PERCENT:g}"
        )


def _validate_input_path(args: argparse.Namespace) -> Path:
    input_path = args.input.resolve()
    if not input_path.is_file():
        raise AudioProcessingError(f"Input audio does not exist: {input_path}")
    return input_path


def _validate_click_path(args: argparse.Namespace) -> Path:
    click_path = args.click_file.resolve()
    if not click_path.is_file():
        raise ClickTrackError(f"Click asset does not exist: {click_path}")
    return click_path


def _format_bpm_filename(value: float) -> str:
    text = f"{value:.12f}".rstrip("0").rstrip(".")
    return text or "0"


def _resolve_output_paths(
    args: argparse.Namespace,
    input_path: Path,
    click_path: Path,
    target_bpm: float,
) -> tuple[Path, Path]:
    if args.output is None:
        output_path = input_path.with_name(
            f"{input_path.stem}({_format_bpm_filename(target_bpm)}bpm).wav"
        )
    else:
        output_path = args.output.resolve()
    if not output_path.suffix:
        raise AudioProcessingError("Output path must include an audio file extension")
    report_path = (
        args.report.resolve()
        if args.report
        else output_path.with_suffix(output_path.suffix + ".report.json")
    )

    named_paths = (
        ("input", input_path),
        ("click", click_path),
        ("output", output_path),
        ("report", report_path),
    )
    for index, (left_name, left_path) in enumerate(named_paths):
        for right_name, right_path in named_paths[index + 1 :]:
            if _paths_collide(left_path, right_path):
                raise AudioProcessingError(
                    f"{left_name.capitalize()} and {right_name} paths must be distinct: "
                    f"{left_path}"
                )

    for path in (output_path, report_path):
        if path.exists() and not args.overwrite:
            raise AudioProcessingError(
                f"Output already exists: {path}. Use --overwrite to replace it."
            )
    return output_path, report_path


def _tempo_mode(
    args: argparse.Namespace,
    predicted_alignment: dict[str, float | bool],
    analysis: TempoAnalysis,
) -> str:
    if args.tempo_mode != "auto":
        return args.tempo_mode
    insufficient_coverage = (
        analysis.observed_beat_ratio < AUTO_GLOBAL_MIN_OBSERVED_RATIO
        or analysis.max_missing_beat_run > AUTO_GLOBAL_MAX_MISSING_BEAT_RUN
    )
    return (
        "strict"
        if insufficient_coverage or _needs_strict_tempo_map(predicted_alignment)
        else "global"
    )


def _format_json(payload: dict[str, object]) -> str:
    return json.dumps(payload, ensure_ascii=False, indent=2, allow_nan=False)


def _write_report(path: Path, report: dict[str, object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(_format_json(report) + "\n", encoding="utf-8")


def run(args: argparse.Namespace) -> int:
    _validate_numeric_args(args)
    input_path = _validate_input_path(args)
    warnings: list[str] = []

    with tempfile.TemporaryDirectory(prefix="running-song-maker-") as temporary:
        temp_dir = Path(temporary)
        source_audio, source_sample_rate = decode_audio(
            input_path, temp_dir / "decoded-input.wav"
        )
        source_channels = source_audio.shape[1]
        source_duration = duration_seconds(source_audio, source_sample_rate)
        analysis = analyze_tempo(source_audio, source_sample_rate, args.first_beat)
        target_bpm = parse_target_bpm(args.target_bpm, analysis.source_bpm)
        stretch_ratio = target_bpm / analysis.source_bpm
        stretch_percent = (stretch_ratio - 1.0) * 100.0
        tempo_fields = _tempo_report_fields(
            target_bpm,
            stretch_ratio,
            stretch_percent,
        )
        predicted_alignment = transformed_alignment(
            analysis.beat_times,
            analysis.anchor_seconds,
            stretch_ratio,
            target_bpm,
            strict=False,
            beat_ordinals=analysis.beat_ordinals,
        )
        mode = _tempo_mode(args, predicted_alignment, analysis)
        payload = _analysis_payload(
            input_path,
            source_sample_rate,
            source_channels,
            source_duration,
            analysis,
            tempo_fields,
            mode,
            predicted_alignment,
        )

        if args.analyze_only:
            print(_format_json(payload))
            return 0

        click_path = _validate_click_path(args)
        output_path, report_path = _resolve_output_paths(
            args, input_path, click_path, target_bpm
        )
        output_spec = resolve_output_spec(output_path, source_sample_rate)
        final_sample_rate = output_sample_rate(output_spec, source_sample_rate)

        if analysis.confidence < LOW_CONFIDENCE_THRESHOLD:
            if not args.allow_low_confidence:
                raise TempoAnalysisError(
                    f"Beat confidence is only {analysis.confidence:.2f}. After manually "
                    "verifying the BPM, provide --first-beat when phase correction is needed "
                    "and use --allow-low-confidence to confirm the analysis."
                )
            warnings.append(
                f"Low automatic beat confidence accepted: {analysis.confidence:.2f}"
            )

        if abs(stretch_percent) > args.max_stretch_percent:
            if not args.allow_large_stretch:
                raise TempoStretchError(
                    f"Target requires {stretch_percent:+.2f}% speed change, above the "
                    f"{args.max_stretch_percent:.2f}% vocal-safety threshold. Choose a closer "
                    "target or explicitly use --allow-large-stretch after accepting the risk."
                )
            warnings.append(
                f"Large speed change explicitly accepted: {stretch_percent:+.2f}%"
            )

        strict = mode == "strict"
        if args.tempo_mode == "auto" and strict and (
            analysis.observed_beat_ratio < AUTO_GLOBAL_MIN_OBSERVED_RATIO
            or analysis.max_missing_beat_run > AUTO_GLOBAL_MAX_MISSING_BEAT_RUN
        ):
            warnings.append(
                "Auto selected strict mode because beat observations have insufficient "
                "coverage or a long missing ordinal run"
            )
        if args.tempo_mode == "global" and _needs_strict_tempo_map(predicted_alignment):
            warnings.append(
                "Global mode was forced although the source beat grid predicts audible drift"
            )

        time_map = None
        time_map_path = None
        no_stretch_needed = math.isclose(stretch_ratio, 1.0, abs_tol=1e-8)
        if strict and not no_stretch_needed:
            local_limit = 1.0 if args.allow_large_stretch else 0.20
            time_map = build_time_map(
                analysis.beat_times,
                analysis.source_bpm,
                target_bpm,
                analysis.anchor_seconds,
                source_duration,
                source_sample_rate,
                max_local_tempo_change=local_limit,
                beat_ordinals=analysis.beat_ordinals,
            )
            time_map_path = temp_dir / "rubberband-timemap.txt"
            write_time_map(time_map_path, time_map)
        if no_stretch_needed:
            actual_engine = "none"
            stretched_audio = source_audio
            stretched_rate = source_sample_rate
        else:
            selected_engine = choose_engine(args.engine, strict)
            if selected_engine == "ffmpeg-atempo":
                warnings.append(
                    "FFmpeg atempo fallback used instead of Rubber Band R3/Finer"
                )

            source_wav = temp_dir / "source-float.wav"
            stretched_wav = temp_dir / "stretched-float.wav"
            write_pcm_wav(source_wav, source_audio, source_sample_rate)
            actual_engine = stretch_audio_file(
                source_wav,
                stretched_wav,
                selected_engine,
                stretch_ratio,
                centre_focus=(
                    source_channels == 2 and not args.preserve_stereo_width
                ),
                time_map_path=time_map_path,
                output_duration_seconds=(
                    time_map.output_duration_seconds if time_map else None
                ),
            )
            stretched_audio, stretched_rate = decode_audio(stretched_wav)

        del source_audio
        if stretched_rate != source_sample_rate:
            raise AudioProcessingError(
                f"Stretch engine changed sample rate from {source_sample_rate} to {stretched_rate}"
            )
        if stretched_audio.shape[1] != source_channels:
            raise AudioProcessingError("Stretch engine changed the channel count")

        if final_sample_rate != source_sample_rate:
            stretched_audio = resample_audio(
                stretched_audio, source_sample_rate, final_sample_rate
            )
        sample_rate = final_sample_rate
        stretched_channels = stretched_audio.shape[1]
        centre_focus_enabled = (
            actual_engine == "rubberband"
            and not args.preserve_stereo_width
            and stretched_channels == 2
        )

        manual_output_anchor = (
            analysis.anchor_seconds / stretch_ratio if analysis.anchor_is_manual else None
        )
        if time_map:
            click_bpm = target_bpm
            click_phase = time_map.anchor_output_seconds
            click_period = 60.0 / target_bpm
        else:
            click_period, fitted_phase = fit_click_grid(
                stretched_audio,
                sample_rate,
                target_bpm,
                anchor_hint_seconds=manual_output_anchor,
                lock_anchor=manual_output_anchor is not None,
            )
            click_bpm = 60.0 / click_period
            click_phase = (
                manual_output_anchor
                if manual_output_anchor is not None
                else fitted_phase
            )

        click_asset = load_click_asset(click_path, sample_rate)
        click_track = generate_click_track(
            stretched_audio.shape[0],
            stretched_channels,
            sample_rate,
            click_bpm,
            click_phase,
            click_asset,
            args.click_peak_dbfs,
        )
        click_report = {
            "asset": str(click_path),
            "count": int(click_track.positions.size),
            "interval_seconds": click_track.interval_seconds,
            "rate_per_minute": 60.0 / click_track.interval_seconds,
            "first_seconds": float(click_track.times[0]),
            "last_seconds": float(click_track.times[-1]),
            "peak_dbfs": click_track.peak_dbfs,
            "odd_even_peak_ratio": click_track.odd_even_peak_ratio,
            "rendered_peak_dbfs": click_track.rendered_peak_dbfs,
            "target_rate_per_minute": target_bpm * 2.0,
        }
        mix = mix_fixed_click(
            stretched_audio,
            click_track.samples,
            args.click_peak_dbfs,
            args.click_over_rms_db,
            args.output_peak_dbfs,
        )
        if mix.extra_headroom_reduction_db > 0.01:
            warnings.append(
                "Music was reduced further to preserve the fixed click level without clipping"
            )
        master_frame_count = mix.mixed.shape[0]
        master_duration = duration_seconds(mix.mixed, sample_rate)
        loudness_report = {
            "music_rms_before_dbfs": mix.music_rms_before_dbfs,
            "music_gain_db": mix.music_gain_db,
            "music_rms_after_dbfs": mix.music_rms_after_dbfs,
            "click_peak_over_music_rms_db": mix.click_peak_over_music_rms_db,
            "mixed_peak_dbfs": mix.mixed_peak_dbfs,
            "clipped": mix.clipped,
        }

        encoded_master = temp_dir / "encoded-master.wav"
        write_output_audio(
            output_path,
            mix.mixed,
            sample_rate,
            encoded_master,
        )
        del click_track, mix, stretched_audio

        verified_audio, verified_rate = decode_audio(
            output_path, temp_dir / "verified-output.wav"
        )
        if verified_rate != final_sample_rate:
            raise AudioProcessingError(
                f"Encoded output sample rate is {verified_rate}, expected {final_sample_rate}"
            )
        if verified_audio.shape[1] != stretched_channels:
            raise AudioProcessingError("Encoded output changed the channel count")

        verified_peak = peak_dbfs(verified_audio)
        decoded_duration = duration_seconds(verified_audio, verified_rate)
        duration_error_seconds = decoded_duration - master_duration
        duration_tolerance = (
            output_spec.duration_tolerance_seconds
            if output_spec.lossy and output_spec.duration_tolerance_seconds is not None
            else LOSSY_DURATION_TOLERANCE_SECONDS
            if output_spec.lossy
            else 1.0 / verified_rate
        )
        duration_passed = abs(duration_error_seconds) <= duration_tolerance
        delay_samples = 0
        delay_seconds = 0.0
        tail_padding_samples = verified_audio.shape[0] - master_frame_count
        delay_passed = True
        if output_spec.lossy:
            lossless_audio, lossless_rate = decode_audio(encoded_master)
            if lossless_rate != verified_rate:
                raise AudioProcessingError(
                    "Lossless master and encoded output have different sample rates"
                )
            delay_samples = estimate_delay_samples(
                lossless_audio, verified_audio, verified_rate
            )
            delay_seconds = delay_samples / verified_rate
            tail_padding_samples = (
                verified_audio.shape[0] - master_frame_count - delay_samples
            )
            delay_tolerance = (
                output_spec.delay_tolerance_seconds
                if output_spec.delay_tolerance_seconds is not None
                else LOSSY_DELAY_TOLERANCE_SECONDS
            )
            delay_passed = abs(delay_seconds) <= delay_tolerance
            if not delay_passed:
                warnings.append(
                    f"Lossy codec introduced an estimated {abs(delay_seconds)*1000:.1f} ms "
                    "of encoder delay or padding"
                )

        peak_ceiling_passed = (
            verified_peak <= args.output_peak_dbfs + PEAK_VALIDATION_TOLERANCE_DB
        )
        clipped = verified_peak > 0.0
        if not peak_ceiling_passed:
            warnings.append(
                f"Decoded output peak {verified_peak:.2f} dBFS exceeds the configured "
                f"{args.output_peak_dbfs:.2f} dBFS ceiling"
            )
        if not duration_passed:
            warnings.append(
                f"Decoded output duration differs from the PCM master by "
                f"{abs(duration_error_seconds)*1000:.1f} ms"
            )

        click_rate_passed = bool(
            abs(
                click_report["rate_per_minute"]
                - click_report["target_rate_per_minute"]
            )
            <= CLICK_RATE_TOLERANCE_SPM
        )
        if not click_rate_passed:
            warnings.append(
                f"Rendered click rate {click_report['rate_per_minute']:.3f} SPM differs "
                f"from target {click_report['target_rate_per_minute']:.3f} SPM"
            )

        if time_map:
            alignment = alignment_result(
                time_map.predicted_p50_ms,
                time_map.predicted_p95_ms,
                time_map.estimated_end_drift_ms,
            )
        else:
            alignment = transformed_alignment(
                analysis.beat_times,
                analysis.anchor_seconds,
                stretch_ratio,
                target_bpm,
                strict=False,
                beat_ordinals=analysis.beat_ordinals,
                output_grid_period_seconds=60.0 / click_bpm,
                output_grid_origin_seconds=click_phase,
            )

        click_equal_volume = bool(click_report["odd_even_peak_ratio"] >= 0.99)
        acceptance_checks = {
            "output_readable": True,
            "sample_rate": verified_rate == final_sample_rate,
            "channels": verified_audio.shape[1] == stretched_channels,
            "duration": duration_passed,
            "final_peak_ceiling": peak_ceiling_passed,
            "not_clipped": not clipped,
            "codec_delay": delay_passed,
            "click_cadence": click_rate_passed,
            "click_equal_volume": click_equal_volume,
            "alignment_p95": bool(alignment["predicted_p95_ms"] <= 30.0),
            "alignment_end_drift": bool(
                alignment["estimated_end_drift_ms"] <= STRICT_END_DRIFT_MS
            ),
        }
        passed = all(acceptance_checks.values())
        loudness_report.update(
            {
                "decoded_peak_dbfs": verified_peak,
                "peak_ceiling_passed": peak_ceiling_passed,
                "estimated_delay_seconds": delay_seconds,
                "tail_padding_samples": tail_padding_samples,
                "duration_error_seconds": duration_error_seconds,
                "duration_passed": duration_passed,
                "clipped": clipped,
            }
        )
        report = {
            "input": payload["input"],
            "analysis": payload["analysis"],
            "processing": {
                **tempo_fields,
                "engine": actual_engine,
                "tempo_mode": mode,
                "pitch_ratio": 1.0,
                "actual_bpm": click_bpm,
                "centre_focus": centre_focus_enabled,
                "time_map_anchor_stride_beats": (
                    time_map.anchor_stride_beats if time_map else None
                ),
                "local_tempo_ratio_min": (
                    time_map.local_tempo_ratio_min if time_map else None
                ),
                "local_tempo_ratio_max": (
                    time_map.local_tempo_ratio_max if time_map else None
                ),
            },
            "click": click_report,
            "loudness": loudness_report,
            "alignment": alignment,
            "acceptance": {
                "checks": acceptance_checks,
                "passed": passed,
            },
            "output": {
                "path": str(output_path.resolve()),
                "report_path": str(report_path.resolve()),
                "sample_rate": verified_rate,
                "channels": int(verified_audio.shape[1]),
                "duration_seconds": decoded_duration,
                "expected_duration_seconds": master_duration,
                "duration_error_seconds": duration_error_seconds,
                "format": output_path.suffix.lower().lstrip("."),
            },
            "warnings": warnings,
            "passed": passed,
        }
        _write_report(report_path, report)
        print(_format_json(report))
        return 0 if passed else 3


def main() -> int:
    args = parse_args()
    try:
        return run(args)
    except (
        AudioProcessingError,
        ClickTrackError,
        TempoAnalysisError,
        TempoStretchError,
        ValueError,
    ) as exc:
        print(f"error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
