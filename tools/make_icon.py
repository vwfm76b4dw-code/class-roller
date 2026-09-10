"""生成应用图标。

在 256px 画布上绘制后降采样到各标准尺寸，保证小尺寸下依然清晰。
设计：系统蓝圆角方块 + 白色骰子五点，一眼可读为"随机抽取"。

用法：python tools/make_icon.py
输出：roller/assets/app.ico
"""

from __future__ import annotations

import sys
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "roller" / "assets" / "app.ico"

# 与 theme.Palette.accent 保持一致
ACCENT = (15, 108, 189, 255)
WHITE = (255, 255, 255, 255)

SIZE = 256
CORNER = 58
SIZES = [256, 128, 64, 48, 32, 24, 16]


def draw_master() -> Image.Image:
    img = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 圆角底
    draw.rounded_rectangle([0, 0, SIZE - 1, SIZE - 1], radius=CORNER, fill=ACCENT)

    # 骰子五点
    cx = cy = SIZE // 2
    offset = 55
    dot = 27
    points = [
        (cx - offset, cy - offset),
        (cx + offset, cy - offset),
        (cx, cy),
        (cx - offset, cy + offset),
        (cx + offset, cy + offset),
    ]
    for x, y in points:
        draw.ellipse([x - dot, y - dot, x + dot, y + dot], fill=WHITE)

    return img


def main() -> int:
    master = draw_master()
    OUT.parent.mkdir(parents=True, exist_ok=True)
    master.save(OUT, format="ICO", sizes=[(s, s) for s in SIZES])
    print(f"已生成 {OUT}")

    # 同时导出一张 PNG 便于预览
    preview = ROOT / "docs" / "icon_preview.png"
    preview.parent.mkdir(parents=True, exist_ok=True)
    strip = Image.new("RGBA", (sum(SIZES) + 8 * len(SIZES), 256 + 16), (243, 243, 243, 255))
    x = 8
    for s in SIZES:
        thumb = master.resize((s, s), Image.LANCZOS)
        strip.paste(thumb, (x, 8 + (256 - s) // 2), thumb)
        x += s + 8
    strip.save(preview)
    print(f"已生成预览 {preview}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
