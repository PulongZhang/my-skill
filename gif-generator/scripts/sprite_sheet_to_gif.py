#!/usr/bin/env python3
"""Convert a horizontal sprite sheet into a clean GIF.

Designed for chroma-key or transparent multi-frame sheets. It removes a
flat key background, crops each view, centers it on a stable canvas, and writes
real keyframes only; it intentionally does not crossfade frames.
"""

from __future__ import annotations

import argparse
import math
from pathlib import Path
from statistics import median

from PIL import Image, ImageDraw


def parse_color(value: str) -> tuple[int, int, int]:
    value = value.strip().lower()
    names = {"white": (255, 255, 255), "black": (0, 0, 0), "transparent": (255, 255, 255)}
    if value in names:
        return names[value]
    if value.startswith("#") and len(value) == 7:
        return tuple(int(value[i : i + 2], 16) for i in (1, 3, 5))
    raise ValueError(f"Unsupported color: {value}")


def sample_border_key(im: Image.Image) -> tuple[int, int, int]:
    rgb = im.convert("RGB")
    w, h = rgb.size
    samples = []
    for x in range(w):
        samples.append(rgb.getpixel((x, 0)))
        samples.append(rgb.getpixel((x, h - 1)))
    for y in range(h):
        samples.append(rgb.getpixel((0, y)))
        samples.append(rgb.getpixel((w - 1, y)))
    return tuple(int(median(channel)) for channel in zip(*samples))


def remove_chroma(
    im: Image.Image,
    key: tuple[int, int, int] | None,
    transparent_threshold: float,
    opaque_threshold: float,
    despill: bool,
) -> Image.Image:
    rgba = im.convert("RGBA")
    if key is None:
        return rgba

    px = rgba.load()
    w, h = rgba.size
    kr, kg, kb = key
    key_is_green = kg > kr + 30 and kg > kb + 30

    for y in range(h):
        for x in range(w):
            r, g, b, a = px[x, y]
            dist = math.sqrt((r - kr) ** 2 + (g - kg) ** 2 + (b - kb) ** 2)
            if dist <= transparent_threshold:
                px[x, y] = (r, g, b, 0)
                continue
            if dist < opaque_threshold:
                alpha = int(255 * (dist - transparent_threshold) / (opaque_threshold - transparent_threshold))
                a = min(a, max(0, min(255, alpha)))
            if despill and a < 255:
                if key_is_green and g > max(r, b):
                    g = int((r + b) / 2)
            px[x, y] = (r, g, b, a)
    return rgba


def require_green_key(key: tuple[int, int, int]) -> None:
    r, g, b = key
    if g < 140 or g < r + 45 or g < b + 45:
        raise ValueError(
            f"Expected a flat green-screen border key, got #{r:02x}{g:02x}{b:02x}. "
            "Regenerate or repair the source on #00ff00 green-screen before making the GIF."
        )


def alpha_column_runs(im: Image.Image, count: int) -> list[tuple[int, int]]:
    alpha = im.getchannel("A")
    w, h = im.size
    runs = []
    in_run = False
    start = 0
    for x in range(w):
        visible = alpha.crop((x, 0, x + 1, h)).getbbox() is not None
        if visible and not in_run:
            start = x
            in_run = True
        elif not visible and in_run:
            if x - start > 8:
                runs.append((start, x - 1))
            in_run = False
    if in_run:
        runs.append((start, w - 1))
    if len(runs) == count:
        return runs

    # Fallback for sheets where views touch or detection is imperfect.
    step = w / count
    fallback = []
    for i in range(count):
        left = int(round(i * step))
        right = int(round((i + 1) * step)) - 1
        fallback.append((left, min(w - 1, right)))
    return fallback


def crop_visible(im: Image.Image, pad: int) -> Image.Image:
    bbox = im.getchannel("A").getbbox()
    if bbox is None:
        return im
    left, top, right, bottom = bbox
    left = max(0, left - pad)
    top = max(0, top - pad)
    right = min(im.width, right + pad)
    bottom = min(im.height, bottom + pad)
    return im.crop((left, top, right, bottom))


def build_frames(args: argparse.Namespace) -> list[Image.Image]:
    source = Image.open(args.input)
    key = None if args.chroma == "none" else sample_border_key(source) if args.chroma == "auto" else parse_color(args.chroma)
    if key is not None:
        require_green_key(key)
    sheet = remove_chroma(source, key, args.transparent_threshold, args.opaque_threshold, args.despill)
    runs = alpha_column_runs(sheet, args.count)
    frames = []
    bg_rgb = parse_color(args.background)

    frames_dir = Path(args.frames_dir) if args.frames_dir else None
    if frames_dir:
        frames_dir.mkdir(parents=True, exist_ok=True)

    for index, (left, right) in enumerate(runs):
        view = sheet.crop((max(0, left - args.pad), 0, min(sheet.width, right + args.pad), sheet.height))
        view = crop_visible(view, args.pad)
        view.thumbnail((args.canvas - 2 * args.margin, args.canvas - 2 * args.margin), Image.Resampling.LANCZOS)

        transparent = Image.new("RGBA", (args.canvas, args.canvas), (255, 255, 255, 0))
        x = (args.canvas - view.width) // 2
        y = (args.canvas - view.height) // 2 + args.y_offset
        transparent.alpha_composite(view, (x, y))
        if frames_dir:
            transparent.save(frames_dir / f"frame_{index:02d}.png")

        composed = Image.new("RGBA", (args.canvas, args.canvas), (*bg_rgb, 255))
        composed.alpha_composite(transparent)
        frames.append(composed.convert("RGB"))
    return frames


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
    parser.add_argument("--input", required=True, type=Path)
    parser.add_argument("--out", required=True, type=Path)
    parser.add_argument("--preview", type=Path)
    parser.add_argument("--frames-dir")
    parser.add_argument("--count", type=int, default=8)
    parser.add_argument("--canvas", type=int, default=512)
    parser.add_argument("--duration", type=int, default=55)
    parser.add_argument("--chroma", default="auto", help="'auto', 'none', or green hex color like #00ff00")
    parser.add_argument("--background", default="white")
    parser.add_argument("--transparent-threshold", type=float, default=20)
    parser.add_argument("--opaque-threshold", type=float, default=120)
    parser.add_argument("--pad", type=int, default=24)
    parser.add_argument("--margin", type=int, default=28)
    parser.add_argument("--y-offset", type=int, default=4)
    parser.add_argument("--despill", action="store_true", default=True)
    args = parser.parse_args()

    frames = build_frames(args)
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
