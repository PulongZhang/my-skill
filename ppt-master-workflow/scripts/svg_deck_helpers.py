# -*- coding: utf-8 -*-
"""ppt-master Quick Generate 的公共 SVG 生成 helper。

CET 绿白商务风示例配色与常用元素：页面头尾、卡片、圆点列表、图标圆底、
宽度估算。用法：`from svg_deck_helpers import *` 后按需拼装 SVG 字符串。

所有输出符合 ppt-master shared-standards-core：
- 颜色大写 #RRGGBB；字体微软雅黑；文本用 esc() 转义；
- 加粗用 <tspan font-weight="bold">，禁止 <b>；
- 根元素 data-pptx-page-role="cover|toc|content|ending"。
"""

# ---- CET 品牌色 ----
GREEN = "#00B050"      # 主绿
DGREEN = "#0E6B35"     # 深绿
MGREEN = "#1E8A4C"     # 中绿
LGREEN = "#E8F7EE"     # 浅绿底
LGLINE = "#C9E8D4"     # 浅绿线
INK = "#1F2937"        # 墨色正文
GRAY = "#6B7280"       # 灰注释
LIGHT = "#F5F8F6"      # 浅灰底
WHITE = "#FFFFFF"
FONT = "微软雅黑"


def esc(s):
    """XML 转义（& < >）。→ · 「」 等 Unicode 直接保留。"""
    return s.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def svg_open(page_role):
    return (f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 1280 720" '
            f'data-pptx-page-role="{page_role}" font-family="{FONT}">\n')


def end_svg():
    return "</svg>\n"


def bg_dec(image="images/bg-isometric.png", x=880, y=320, w=520, h=400, opacity=0.35):
    """内容页背景：白底 + 右下角浅灰等轴纹理（模板提取的装饰图）。"""
    return (f'<rect x="0" y="0" width="1280" height="720" fill="{WHITE}"/>'
            f'<image href="{image}" x="{x}" y="{y}" width="{w}" height="{h}" opacity="{opacity}"/>')


def header(title, tag, page_no, total=11, subtitle=None, footer="CET 中电技术 · 蓝云平台研发部"):
    """内容页顶部标题区 + 页脚。标题过长时把补充信息放 subtitle，避免与右侧标签重叠。"""
    parts = [
        f'<rect x="0" y="0" width="1280" height="14" fill="{DGREEN}"/>',
        f'<rect x="64" y="52" width="8" height="44" fill="{GREEN}"/>',
        f'<text x="92" y="84" font-size="32" font-weight="bold" fill="{INK}">{esc(title)}</text>',
    ]
    if subtitle:
        parts.append(f'<text x="94" y="110" font-size="15" fill="{GRAY}">{esc(subtitle)}</text>')
    parts.append(f'<rect x="1056" y="60" width="160" height="34" rx="17" fill="{LGREEN}"/>')
    parts.append(f'<text x="1136" y="83" font-size="15" fill="{MGREEN}" text-anchor="middle">{esc(tag)}</text>')
    parts.append(f'<line x1="64" y1="676" x2="1216" y2="676" stroke="{LGLINE}" stroke-width="1"/>')
    parts.append(f'<text x="64" y="700" font-size="12" fill="{GRAY}">{esc(footer)}</text>')
    parts.append(f'<text x="1216" y="700" font-size="12" fill="{GRAY}" text-anchor="end">{page_no:02d} / {total}</text>')
    return "\n".join(parts)


def card(x, y, w, h, fill=LGREEN, rx=12):
    return f'<rect x="{x}" y="{y}" width="{w}" height="{h}" rx="{rx}" fill="{fill}"/>'


def card_title(x, y, text, color=DGREEN, size=19):
    return f'<text x="{x}" y="{y}" font-size="{size}" font-weight="bold" fill="{color}">{esc(text)}</text>'


def bullet(x, y, text, size=15, color=INK, gap=26, dot=GREEN, bold_head=None):
    """带圆点列表项。bold_head 为前缀加粗（如 '标题：'）。返回 (parts_list, next_y)。"""
    parts = [f'<circle cx="{x+5}" cy="{y-5}" r="5" fill="{dot}"/>']
    if bold_head:
        parts.append(f'<text x="{x+22}" y="{y}" font-size="{size}" fill="{color}">'
                     f'<tspan font-weight="bold" fill="{DGREEN}">{esc(bold_head)}</tspan>{esc(text)}</text>')
    else:
        parts.append(f'<text x="{x+22}" y="{y}" font-size="{size}" fill="{color}">{esc(text)}</text>')
    return parts, y + gap


def icon_circle(x, y, icon, size=44, circle_fill=LGREEN, icon_fill=MGREEN):
    """绿底圆 + tabler 图标。"""
    return (f'<circle cx="{x+size/2}" cy="{y+size/2}" r="{size/2}" fill="{circle_fill}"/>'
            f'<use data-icon="tabler-outline/{icon}" x="{x+10}" y="{y+10}" '
            f'width="{size-20}" height="{size-20}" fill="{icon_fill}"/>')


# ---- 文本宽度估算（用于人工预拆行，避免中文溢出卡片）----
import unicodedata


def est_width(text, font_size):
    """估算单行文本宽度：中文/全角 ≈ 1.0×size，拉丁/数字 ≈ 0.55×size，空格 ≈ 0.33×size。"""
    w = 0.0
    for ch in text:
        if unicodedata.east_asian_width(ch) in ("F", "W"):
            w += font_size
        elif ch == " ":
            w += font_size * 0.33
        else:
            w += font_size * 0.55
    return w


def split_lines(text, font_size, max_width, prefix=""):
    """把长文本按估算宽度拆成多行（在标点处断行优先）。返回行列表。"""
    lines, cur = [], ""
    for ch in text:
        if est_width(prefix + cur + ch, font_size) > max_width and cur:
            lines.append(prefix + cur)
            cur = ch
        else:
            cur += ch
    if cur:
        lines.append(prefix + cur)
    return lines
