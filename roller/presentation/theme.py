"""视觉主题。

中性底 + 单一强调色，靠层次（画布 / 卡面 / 描边）而不是重色块来区分结构。
强调色取 Windows 系统蓝，和系统 UI 一致。字阶收敛成四级，避免字号乱用。
"""

from __future__ import annotations

from dataclasses import dataclass

import customtkinter as ctk


@dataclass(frozen=True)
class Palette:
    """浅色配色方案。"""

    # 背景三层：画布 → 卡面 → 悬浮
    bg_root: str = "#f3f3f3"       # 窗口画布
    bg_card: str = "#ffffff"       # 内容卡面
    bg_elevated: str = "#f7f7f7"   # 次级容器（输入框、次级按钮）
    bg_hover: str = "#ebebeb"

    # 文字三级
    text_primary: str = "#171717"
    text_secondary: str = "#5c5c5c"
    text_muted: str = "#8f8f8f"

    # 强调色
    accent: str = "#0f6cbd"
    accent_hover: str = "#0c5ca3"
    accent_press: str = "#0a4d88"      # 按压加深
    accent_soft: str = "#e9f2fb"

    # 状态色
    success: str = "#0e7a3c"
    warning: str = "#8a5a00"
    danger: str = "#c42b1c"

    # 描边两级
    border: str = "#e7e7e7"
    border_strong: str = "#d4d4d4"

    # 玻璃/半透明模式下的表面：留出透明度让背景效果透出来，
    # 同时保证文字对比度仍满足可读性（正文 ≥ 4.5:1）
    bg_glass: str = "#f3f3f3"
    bg_card_glass: str = "#fbfbfb"


FONT_FAMILY = "Microsoft YaHei UI"

# 字阶：只保留四级 + 一个超大字
FONT_DISPLAY = (FONT_FAMILY, 46, "bold")
FONT_TITLE = (FONT_FAMILY, 15, "bold")
FONT_BODY = (FONT_FAMILY, 13)
FONT_SMALL = (FONT_FAMILY, 11)
FONT_BUTTON = (FONT_FAMILY, 15, "bold")

# 圆角：与 Win11 观感一致，小而克制
RADIUS_LG = 10
RADIUS_MD = 8
RADIUS_SM = 6

# 间距刻度（4pt 基准，实际用 4/6/8/12/16/20）
# 所有 padx/pady 必须取这里的值，不要在界面文件里写字面量数字。
SPACE_XXS = 2
SPACE_XS = 4
SPACE_TIGHT = 6
SPACE_SM = 8
SPACE_MD = 14
SPACE_LG = 20
SPACE_XL = 24

# 控件高度统一
HEIGHT_BUTTON = 48
HEIGHT_BUTTON_SM = 32
HEIGHT_BUTTON_MD = 36
HEIGHT_INPUT = 36

# 描边宽度
BORDER_W = 1


def apply_theme() -> Palette:
    """设置全局外观并返回配色表。

    窗口缩放必须禁用：CTk 默认把 geometry() 里的尺寸按系统 DPI 缩放系数
    放大（150% 屏 → ×1.5），而我们保存的窗口尺寸是物理像素（winfo_width），
    下次启动再被放大一次——窗口每重启一次就大 50%，直到越过屏幕。
    禁用后 geometry 即物理像素，保存/恢复自洽。控件缩放保留，高分屏字体仍清晰。
    """
    ctk.set_appearance_mode("light")
    ctk.set_default_color_theme("blue")
    ctk.set_window_scaling(1.0)
    return Palette()


# ── 颜色工具 ──────────────────────────────────────────────
def hex_to_rgb(value: str) -> tuple[int, int, int]:
    value = value.lstrip("#")
    return int(value[0:2], 16), int(value[2:4], 16), int(value[4:6], 16)


def rgb_to_hex(rgb: tuple[int, int, int]) -> str:
    return "#%02x%02x%02x" % tuple(max(0, min(255, int(c))) for c in rgb)


def lerp_color(start: str, end: str, t: float) -> str:
    """在两个颜色之间线性插值，t ∈ [0, 1]。"""
    t = max(0.0, min(1.0, t))
    a = hex_to_rgb(start)
    b = hex_to_rgb(end)
    return rgb_to_hex(tuple(a[i] + (b[i] - a[i]) * t for i in range(3)))
