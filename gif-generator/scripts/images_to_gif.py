#!/usr/bin/env python3
"""Build a clean GIF from an ordered directory of image frames."""

from __future__ import annotations

import argparse
import math
from pathlib import Path

from PIL import Image, ImageDraw


def parse_color(value: str) -> tuple[int, int, int]:
    value = value.strip().lower()
    if value == "white":
        return (255, 255, 255)
    if value == "black":
        return (0, 0, 0)
    if value.startswith("#") and len(value) == 7:
        return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))
    raise ValueError(f"Unsupported background color: {value}")


def compose_frame(path: Path, canvas: int, margin: int, background: tuple[int, int, int]) -> Image.Image:
    frame = Image.open(path).convert("RGBA")
    frame.thumbnail((canvas - 2 * margin, canvas - 2 * margin), Image.Resampling.LANCZOS)
    composed = Image.new("RGBA", (canvas, canvas), (*background, 255))
    composed.alpha_composite(frame, ((canvas - frame.width) // 2, (canvas - frame.height) // 2))
    return composed.convert("RGB")


def write_preview(frames: list[Image.Image], path: Path) -> None:
    cell_w, cell_h = 128, 148
    cols = min(4, len(frames))
    rows = math.ceil(len(frames) / cols)
    preview = Image.new("RGB", (cell_w * cols, cell_h * rows), "white")
    for i, frame in enumerate(frames):
        thumb = frame.copy()
        thumb.thumbnail((cell_w, cell_w), Image.Resampling.LANCZOS)
        cell = Image.new("RGB", (cell_w, cell_h), "white")
        cell.paste(thumb, ((cell_w - thumb.width) // 2, 0))
        ImageDraw.Draw(cell).text((4, cell_w + 4), str(i), fill=(0, 0, 0))
        preview.paste(cell, ((i % cols) * cell_w, (i // cols) * cell_h))
    preview.save(path)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-dir", required=True, type=Path)
    parser.add_argument("--glob", default="*.png")
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--preview", type=Path)
    parser.add_argument("--canvas", type=int, default=512)
    parser.add_argument("--margin", type=int, default=28)
    parser.add_argument("--duration", type=int, default=55)
    parser.add_argument("--background", default="white")
    args = parser.parse_args()

    paths = sorted(args.input_dir.glob(args.glob))
    if not paths:
        raise SystemExit(f"No input frames matched {args.glob!r} in {args.input_dir}")

    background = parse_color(args.background)
    frames = [compose_frame(path, args.canvas, args.margin, background) for path in paths]

    args.out.parent.mkdir(parents=True, exist_ok=True)
    frames[0].save(
        args.out,
        save_all=True,
        append_images=frames[1:],
        duration=args.duration,
        loop=0,
        optimize=True,
        disposal=2,
    )
    if args.preview:
        args.preview.parent.mkdir(parents=True, exist_ok=True)
        write_preview(frames, args.preview)
    print(args.out)


if __name__ == "__main__":
    main()
