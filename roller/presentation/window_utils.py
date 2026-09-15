"""Windows 窗口底层工具（WebView2 方案所需）。

只保留与显示器工作区、窗口句柄相关的部分：
- 窗口尺寸/位置的钳制（不越界、不盖任务栏）
- 多显示器感知（含副屏在主屏左侧/上方的负坐标）

原 Tk 方案的置顶保持器、DWM 圆角、背景模糊等已全部移除：
WebView2 自己处理 DPI 与合成，置顶交给 pywebview 的 on_top，
玻璃效果交给页面 CSS 的 backdrop-filter。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Optional, Tuple

# ── 常量 ──────────────────────────────────────────────────
GA_ROOT = 2
MONITOR_DEFAULTTONEAREST = 2
SPI_GETWORKAREA = 0x0030
SPI_GETCLIENTAREAANIMATION = 0x1042
SM_CXSCREEN = 0
SM_CYSCREEN = 1
WIN11_BUILD = 22000

_is_windows = sys.platform == "win32"

_user32 = None
_loaded = False


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def _load() -> bool:
    """加载并配置 Win32 函数签名（只做一次）。

    ⚠️ 所有 Win32 调用都显式声明 argtypes/restype。不声明时 ctypes 默认
    按 32 位 int 处理，而 64 位下 HWND 是指针，会被截断出错。
    """
    global _user32, _loaded
    if not _is_windows:
        return False
    if _loaded:
        return _user32 is not None
    _loaded = True
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)

        user32.GetAncestor.restype = wintypes.HWND
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]

        user32.GetSystemMetrics.restype = ctypes.c_int
        user32.GetSystemMetrics.argtypes = [ctypes.c_int]

        user32.MonitorFromWindow.restype = wintypes.HANDLE
        user32.MonitorFromWindow.argtypes = [wintypes.HWND, wintypes.DWORD]

        user32.MonitorFromPoint.restype = wintypes.HANDLE
        user32.MonitorFromPoint.argtypes = [wintypes.POINT, wintypes.DWORD]

        user32.GetMonitorInfoW.restype = wintypes.BOOL
        user32.GetMonitorInfoW.argtypes = [wintypes.HANDLE, ctypes.c_void_p]

        user32.SystemParametersInfoW.restype = wintypes.BOOL
        user32.SystemParametersInfoW.argtypes = [
            wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT
        ]

        _user32 = user32
        return True
    except Exception:
        _user32 = None
        return False


# ── 系统信息 ──────────────────────────────────────────────
def windows_build() -> int:
    if not _is_windows:
        return 0
    try:
        return sys.getwindowsversion().build
    except Exception:
        return 0


def is_windows_11() -> bool:
    return windows_build() >= WIN11_BUILD


def animations_enabled() -> bool:
    """系统是否允许动画（"减少动态效果"关闭时为 False）。

    网页侧还会用 prefers-reduced-motion 再判一次，两处都尊重用户设置。
    """
    if not _load():
        return True
    try:
        enabled = wintypes.BOOL(True)
        ok = _user32.SystemParametersInfoW(
            SPI_GETCLIENTAREAANIMATION, 0, ctypes.byref(enabled), 0
        )
        return bool(enabled.value) if ok else True
    except Exception:
        return True


# ── 工作区（多显示器感知）─────────────────────────────────
def _work_from_monitor(monitor) -> Optional[Tuple[int, int, int, int]]:
    if not monitor:
        return None
    info = _MONITORINFO()
    info.cbSize = ctypes.sizeof(_MONITORINFO)
    if _user32.GetMonitorInfoW(monitor, ctypes.byref(info)):
        r = info.rcWork
        return (r.left, r.top, r.right, r.bottom)
    return None


def work_area_for_point(
    x: Optional[int], y: Optional[int]
) -> Tuple[int, int, int, int]:
    """包含该点的显示器工作区 (left, top, right, bottom)，不含任务栏。

    多显示器下各自独立，允许负坐标（副屏在主屏左侧的正常情形）。
    """
    if _load():
        try:
            if x is not None and y is not None:
                pt = wintypes.POINT(int(x), int(y))
                area = _work_from_monitor(
                    _user32.MonitorFromPoint(pt, MONITOR_DEFAULTTONEAREST)
                )
                if area:
                    return area
            rect = wintypes.RECT()
            if _user32.SystemParametersInfoW(
                SPI_GETWORKAREA, 0, ctypes.byref(rect), 0
            ):
                return (rect.left, rect.top, rect.right, rect.bottom)
        except Exception:
            pass
    return _fallback_work_area()


def primary_work_area() -> Tuple[int, int, int, int]:
    return work_area_for_point(None, None)


def screen_size() -> Tuple[int, int]:
    """主屏物理分辨率。"""
    if _load():
        try:
            w = _user32.GetSystemMetrics(SM_CXSCREEN)
            h = _user32.GetSystemMetrics(SM_CYSCREEN)
            if w > 0 and h > 0:
                return (w, h)
        except Exception:
            pass
    left, top, right, bottom = primary_work_area()
    return (right - left, bottom - top)


def _fallback_work_area() -> Tuple[int, int, int, int]:
    """拿不到系统接口时的保守估计（预留任务栏高度）。"""
    return (0, 0, 1920, 1032)


def clamp_to_work_area(
    x: int, y: int, width: int, height: int
) -> Tuple[int, int, int, int]:
    """把窗口位置与尺寸钳制到其所在显示器的工作区。

    工作区不含任务栏，因此窗口不会盖住任务栏。
    坐标允许为负（副屏在主屏左侧/上方的正常情形）。
    """
    left, top, right, bottom = work_area_for_point(x, y)
    area_w = max(1, right - left)
    area_h = max(1, bottom - top)

    width = max(1, min(int(width), area_w))
    height = max(1, min(int(height), area_h))
    x = max(left, min(int(x), right - width))
    y = max(top, min(int(y), bottom - height))
    return x, y, width, height
