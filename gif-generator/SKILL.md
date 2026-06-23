---
name: gif-generator
description: Create, edit, and optimize GIF animations from green-screen based images, generated frames, sprite sheets, screenshots, or video-derived frames. Use when Codex needs to make a GIF, animated emoji, sticker, looping demo, before/after animation, object turntable, 3D spin, frame sequence animation, or fix GIF artifacts such as white halos, green-screen fringes, ghosted transitions, bad timing, cropping, or excessive file size. Require generated or repaired source frames to use a flat #00ff00 green-screen intermediate before final GIF composition.
---

# GIF Generator

## Core Rules

Start from clean frames. Most GIF quality problems come from bad frame sources, not from the final GIF encoder.

- Use real frames for the requested motion. Do not fake complex 3D motion by rotating one flat image unless the user asks for a flat sticker effect.
- Require generated, redrawn, repaired, or background-removed frames to use a flat #00ff00 green-screen intermediate.
- Avoid white source backgrounds when the subject has white clothing or pale edges; antialiasing will create white halos.
- Do not crossfade unrelated views unless a ghosted transition is explicitly desired.
- Keep user-facing GIF outputs outside project repos unless the user asks for project assets.

## Workflow

### 1. Identify the GIF Type

- **Image sequence**: combine existing PNG/JPG frames in order.
- **Sprite sheet**: split a grid or horizontal sheet into frames, then center and compose.
- **Generated animation**: create the missing frames first, usually as PNGs or a sprite sheet.
- **Object turntable / 3D spin**: generate or draw multiple real views, such as front, side, back, and intermediate angles.
- **Screen/demo GIF**: extract frames from a video or capture sequence, then downscale and optimize.

### 2. Build or Clean Green-Screen Frames

Use consistent canvas size, baseline, subject scale, and alignment across frames.

For generated, redrawn, or repaired frames, always request green-screen source material:

```text
Create the animation frames on a perfectly flat solid #00ff00 chroma-key background.
The background must be one uniform color with no shadow, gradient, texture, reflection,
floor plane, watermark, text, or frame border. Keep each frame separated and aligned.
Do not use #00ff00 anywhere in the subject.
```

Do not substitute white, transparent, magenta, gradient, or photographic backgrounds during the source-generation stage. If a user supplies non-green-screen frames and asks for cleanup, first create or regenerate a green-screen intermediate when practical, then compose the final GIF from the cleaned frames.

### 3. Remove Halos and Fringes

White borders usually come from antialiased edge pixels generated against a white background. Green borders come from incomplete green-screen removal.

Fixes:

- Regenerate or repair source frames on flat #00ff00 green-screen.
- Use soft matte, edge contraction around 1 px, edge feathering, and despill.
- Inspect frames on both white and dark backgrounds.
- If a GIF shows ghosted front/back overlap, remove blended transition frames and use only real keyframes.

### 4. Compose the GIF

For a horizontal green-screen sprite sheet, use:

```bash
python scripts/sprite_sheet_to_gif.py \
  --input path/to/sprite-sheet.png \
  --out path/to/final.gif \
  --preview path/to/preview.png \
  --frames-dir path/to/frames \
  --count 8 \
  --canvas 512 \
  --duration 55 \
  --chroma auto \
  --background white
```

For ordinary frame files, use `scripts/images_to_gif.py` only after the frames have already passed through the green-screen cleanup step:

```bash
python scripts/images_to_gif.py \
  --input-dir path/to/frames \
  --glob "*.png" \
  --out path/to/final.gif \
  --preview path/to/preview.png \
  --canvas 512 \
  --duration 55 \
  --background white
```

### 5. Tune for Use Case

- Chat stickers/emojis: 384-512 px, 8-16 frames, short loop, small file size.
- UI demos: reduce FPS, crop to the meaningful region, and downscale before optimizing.
- Smooth motion: use more real frames, not crossfaded duplicates.
- File too large: reduce canvas, frame count, color count, or duration complexity before lowering visual quality.

## Validation Checklist

Before responding:

- Open a preview sheet of key frames.
- Confirm generated or repaired source frames used a flat #00ff00 green-screen intermediate.
- Confirm timing, loop behavior, crop, and alignment.
- Check edges for white or green fringes.
- Check that no unintended ghost frames appear.
- Report the final GIF path and include a Markdown image preview with an absolute path.
