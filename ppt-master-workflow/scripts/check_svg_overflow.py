#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""SVG 文本溢出预检：估算每个 <text> 的渲染宽度，
按所在卡片（最近的包含该行的 <rect>）右边界判断是否超宽。

用法：
    python3 check_svg_overflow.py <svg_dir> [--margin 24]

输出：
    <file> y=.. x=.. est_w=.. card_right=.. OVER by .. :: 文本前 44 字
退出码：0 = 无超宽；1 = 存在超宽（供 CI/QA 门禁使用）。

注意：这是粗略估算（未计字距/粗细/字体回退），估算宽度 < 边界 +2px 的行
通常没问题；中文 1.0em / 拉丁 0.55em / 空格 0.33em。
"""
import argparse
import glob
import os
import re
import sys
import unicodedata

TEXT_RE = re.compile(
    r'<text x="([\d.]+)" y="([\d.]+)" font-size="([\d.]+)"([^>]*)>(.*?)</text>', re.S)
RECT_RE = re.compile(r'<rect x="([\d.]+)" y="([\d.]+)" width="([\d.]+)" height="([\d.]+)"')
TAG_RE = re.compile(r'<[^>]+>')


def est_width(text, size):
    w = 0.0
    for ch in text:
        if unicodedata.east_asian_width(ch) in ("F", "W"):
            w += size
        elif ch == " ":
            w += size * 0.33
        else:
            w += size * 0.55
    return w


def check_file(path, margin, slack=20):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    rects = [(float(m.group(1)), float(m.group(2)), float(m.group(3)), float(m.group(4)))
             for m in RECT_RE.finditer(src)]
    issues = []
    for m in TEXT_RE.finditer(src):
        x, y, size = float(m.group(1)), float(m.group(2)), float(m.group(3))
        attrs, inner = m.group(4), m.group(5)
        text = TAG_RE.sub("", inner)
        w = est_width(text, size)
        anchored_middle = "text-anchor=\"middle\"" in attrs or "text-anchor='middle'" in attrs
        # 最紧包含卡片：(rx, right=rx+rw-margin)
        tight = None
        for rx, ry, rw, rh in rects:
            if rx - 4 <= x <= rx + rw + 4 and ry - 6 <= y <= ry + rh + 6 and rw > 50:
                right = rx + rw - margin
                if tight is None or right < tight[1]:
                    tight = (rx, right)
        if tight is not None:
            rx, right = tight
            if anchored_middle:
                over = max(x + w / 2 - right, rx - (x - w / 2))
            else:
                over = x + w - right
            if over > slack:
                issues.append((y, x, w, right, text, over))
    return issues


def main():
    ap = argparse.ArgumentParser(description="SVG 文本溢出预检")
    ap.add_argument("svg_dir", help="svg_output 目录")
    ap.add_argument("--margin", type=int, default=24, help="卡片内边距（px），默认 24")
    args = ap.parse_args()

    files = sorted(glob.glob(os.path.join(args.svg_dir, "*.svg")))
    if not files:
        print("No SVG files found in", args.svg_dir)
        sys.exit(1)

    n_issues = 0
    for f in files:
        for y, x, w, right, text, over in check_file(f, args.margin):
            n_issues += 1
            print(f"{os.path.basename(f):24s} y={y:5.0f} x={x:5.0f} est_w={w:5.0f} "
                  f"card_right={right:5.0f} OVER by {over:4.0f} :: {text[:44]}")
    print(f"\n{'OK' if n_issues == 0 else 'OVERFLOW'}: {n_issues} text line(s) beyond card bounds "
          f"({len(files)} files)")
    sys.exit(1 if n_issues else 0)


if __name__ == "__main__":
    main()
