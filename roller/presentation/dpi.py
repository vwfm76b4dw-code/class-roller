"""窗口尺寸的 DPI 换算。

背景：CustomTkinter 的 `geometry()` 会把你给的尺寸乘以 window_scaling
（= 屏幕 DPI / 96，学校投影常见 150% → 1.5），而 `winfo_width()` 返回的是
乘完之后的物理像素。

如果直接保存 winfo_width()，下次启动 CTk 会再乘一次 1.5：
    保存 600（物理）→ 恢复时 CTk 乘 1.5 得到 900（物理）→ 再保存 900
    → 再恢复 1350 …
窗口每重启一次放大 50%，直到越过屏幕、盖住任务栏。

正确做法：**配置里存逻辑尺寸**。
    保存：logic = 物理 ÷ 缩放
    恢复：geometry(logic)，CTk 自己乘回缩放 → 物理尺寸与保存时一致
这样一个来回完全相等，且高 DPI 屏上 UI 与窗口按系统比例一起放大，
不会出现"字体放大、窗口没放大"的错配。

缩放系数取窗口所在显示器，而非全局——多屏混合 DPI 时才对得上。
"""

from __future__ import annotations

from typing import Optional, Tuple

# 合理性边界（逻辑单位）。超出范围视为脏数据，直接丢弃。
MIN_LOGIC_W, MIN_LOGIC_H = 200, 160
MAX_LOGIC_W, MAX_LOGIC_H = 4000, 3000

DEFAULT_W, DEFAULT_H = 400, 340


def window_scaling_of(window) -> float:
    """取窗口当前的 CTk 窗口缩放系数；拿不到时返回 1.0。"""
    try:
        from customtkinter import ScalingTracker

        value = float(ScalingTracker.get_window_scaling(window))
        # 防御异常值（CTk 内部下限是 0.4）
        if value <= 0.05 or value > 8.0:
            return 1.0
        return value
    except Exception:
        return 1.0


def to_logical(physical: int, scaling: float) -> int:
    """物理像素 → 逻辑单位。"""
    if scaling <= 0.05:
        scaling = 1.0
    return int(round(physical / scaling))


def to_physical(logical: int, scaling: float) -> int:
    """逻辑单位 → 物理像素。"""
    if scaling <= 0.05:
        scaling = 1.0
    return int(round(logical * scaling))


def sanitize_size(width: int, height: int) -> Optional[Tuple[int, int]]:
    """校验逻辑尺寸是否在合理范围内；不合理返回 None。"""
    try:
        w, h = int(width), int(height)
    except (TypeError, ValueError):
        return None
    if not (MIN_LOGIC_W <= w <= MAX_LOGIC_W):
        return None
    if not (MIN_LOGIC_H <= h <= MAX_LOGIC_H):
        return None
    return w, h
