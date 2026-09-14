"""Windows 窗口底层能力：DPI 正确的尺寸换算、多屏工作区、背景效果、置顶。

⚠️ 所有 Win32 调用都显式声明 argtypes/restype。
不声明时 ctypes 默认按 32 位 int 处理，而 64 位 Windows 的 HWND 是指针，
HWND_TOPMOST(-1) 这类特殊值会被错误转换，实测会让窗口收到 SC_CLOSE 自行隐藏。

DPI 处理原则：
CustomTkinter 会把 geometry() 的尺寸乘以 window_scaling（屏幕 DPI/96）。
因此**持久化的必须是逻辑尺寸**（物理像素 ÷ 缩放系数），恢复时让 CTk 乘回去，
一个来回完全相等。若简单禁用窗口缩放，会出现"字体放大 1.5 倍、窗口按 1.0
计算"的错配，内容溢出——那是错误的方向。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Optional, Tuple

# ── 常量 ──────────────────────────────────────────────────
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200

GA_ROOT = 2
MONITOR_DEFAULTTONEAREST = 2
SPI_GETWORKAREA = 0x0030
SPI_GETCLIENTAREAANIMATION = 0x1042

SM_CXSCREEN = 0
SM_CYSCREEN = 1

DWMWA_USE_IMMERSIVE_DARK_MODE = 20
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36
DWMWA_SYSTEMBACKDROP_TYPE = 38

DWMWCP_DONOTROUND = 1
DWMWCP_ROUND = 2

DWMSBT_NONE = 1
DWMSBT_MAINWINDOW = 2        # 云母
DWMSBT_TRANSIENTWINDOW = 3   # 亚克力
DWMSBT_TABBEDWINDOW = 4

WCA_ACCENT_POLICY = 19
ACCENT_DISABLED = 0
ACCENT_ENABLE_BLURBEHIND = 3
ACCENT_ENABLE_ACRYLICBLURBEHIND = 4

WIN11_BUILD = 22000
_is_windows = sys.platform == "win32"

_user32 = None
_dwmapi = None
_loaded = False


class _AccentPolicy(ctypes.Structure):
    _fields_ = [
        ("AccentState", ctypes.c_int),
        ("AccentFlags", ctypes.c_int),
        ("GradientColor", ctypes.c_uint),
        ("AnimationId", ctypes.c_int),
    ]


class _WinCompAttrData(ctypes.Structure):
    _fields_ = [
        ("Attribute", ctypes.c_int),
        ("Data", ctypes.POINTER(_AccentPolicy)),
        ("SizeOfData", ctypes.c_size_t),
    ]


class _MONITORINFO(ctypes.Structure):
    _fields_ = [
        ("cbSize", wintypes.DWORD),
        ("rcMonitor", wintypes.RECT),
        ("rcWork", wintypes.RECT),
        ("dwFlags", wintypes.DWORD),
    ]


def _load() -> bool:
    """加载并配置 Win32 函数签名（只做一次）。"""
    global _user32, _dwmapi, _loaded
    if not _is_windows:
        return False
    if _loaded:
        return _user32 is not None
    _loaded = True
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)

        user32.GetAncestor.restype = wintypes.HWND
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]

        user32.IsWindow.restype = wintypes.BOOL
        user32.IsWindow.argtypes = [wintypes.HWND]

        user32.SetWindowPos.restype = wintypes.BOOL
        user32.SetWindowPos.argtypes = [
            wintypes.HWND, wintypes.HWND, ctypes.c_int, ctypes.c_int,
            ctypes.c_int, ctypes.c_int, wintypes.UINT,
        ]

        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]

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

        if hasattr(user32, "SetWindowCompositionAttribute"):
            fn = user32.SetWindowCompositionAttribute
            fn.restype = wintypes.BOOL
            fn.argtypes = [wintypes.HWND, ctypes.POINTER(_WinCompAttrData)]

        _user32 = user32

        dwm = ctypes.WinDLL("dwmapi", use_last_error=True)
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        dwm.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD
        ]
        _dwmapi = dwm
        return True
    except Exception:
        _user32 = None
        _dwmapi = None
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
    """系统是否允许动画（"减少动态效果"关闭时为 False）。"""
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


def top_level_handle(window) -> Optional[int]:
    """取窗口真正的顶层 HWND（GA_ROOT 向上找根窗口）。"""
    if not _load():
        return None
    try:
        window.update_idletasks()
        hwnd = window.winfo_id()
        root = _user32.GetAncestor(wintypes.HWND(hwnd), GA_ROOT)
        candidate = root or hwnd
        return int(candidate) if candidate else None
    except Exception:
        return None


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


def work_area_for_point(x: Optional[int], y: Optional[int]) -> Tuple[int, int, int, int]:
    """包含该点的显示器工作区 (left, top, right, bottom)，不含任务栏。

    多显示器下各自独立，允许负坐标（副屏在主屏左侧的情况）。
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


def work_area_for_window(window) -> Tuple[int, int, int, int]:
    """窗口当前所在显示器的工作区。"""
    if _load():
        try:
            hwnd = top_level_handle(window)
            if hwnd:
                area = _work_from_monitor(
                    _user32.MonitorFromWindow(
                        wintypes.HWND(hwnd), MONITOR_DEFAULTTONEAREST
                    )
                )
                if area:
                    return area
        except Exception:
            pass
    return work_area_for_point(None, None)


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
    import tkinter as tk

    root = tk.Tk()
    root.withdraw()
    try:
        w = root.winfo_screenwidth()
        h = root.winfo_screenheight()
        return (0, 0, w, max(1, h - 48))  # 保守预留任务栏高度
    finally:
        root.destroy()


def clamp_to_work_area(
    x: int, y: int, width: int, height: int
) -> Tuple[int, int, int, int]:
    """把窗口位置与尺寸钳制到其所在显示器的工作区。

    坐标允许为负（副屏在主屏左侧/上方的正常情况）。
    """
    left, top, right, bottom = work_area_for_point(x, y)
    area_w = max(1, right - left)
    area_h = max(1, bottom - top)

    width = max(1, min(int(width), area_w))
    height = max(1, min(int(height), area_h))
    x = max(left, min(int(x), right - width))
    y = max(top, min(int(y), bottom - height))
    return x, y, width, height


# ── Win11 原生外观 ────────────────────────────────────────
def _colorref(hex_color: str) -> int:
    value = hex_color.lstrip("#")
    r = int(value[0:2], 16)
    g = int(value[2:4], 16)
    b = int(value[4:6], 16)
    return (b << 16) | (g << 8) | r


def _dwm_set(hwnd: int, attribute: int, value: int) -> bool:
    if _dwmapi is None:
        return False
    try:
        data = ctypes.c_int(value)
        return _dwmapi.DwmSetWindowAttribute(
            wintypes.HWND(hwnd), attribute, ctypes.byref(data), ctypes.sizeof(data)
        ) == 0
    except Exception:
        return False


def apply_modern_frame(
    window,
    caption_color: Optional[str] = None,
    border_color: Optional[str] = None,
    text_color: Optional[str] = None,
) -> None:
    """Win11 圆角 + 标题栏配色。

    Win10 不支持这些属性（圆角/标题栏着色是 22000+ 特性），
    DwmSetWindowAttribute 会返回失败码，静默忽略即可——
    Win10 上就是标准系统标题栏，功能不受影响。
    """
    if not _load():
        return
    hwnd = top_level_handle(window)
    if not hwnd:
        return

    if is_windows_11():
        _dwm_set(hwnd, DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)
        if caption_color:
            _dwm_set(hwnd, DWMWA_CAPTION_COLOR, _colorref(caption_color))
        if border_color:
            _dwm_set(hwnd, DWMWA_BORDER_COLOR, _colorref(border_color))
        if text_color:
            _dwm_set(hwnd, DWMWA_TEXT_COLOR, _colorref(text_color))
    else:
        _dwm_set(hwnd, DWMWA_USE_IMMERSIVE_DARK_MODE, 0)


# ── 背景效果（液态玻璃）───────────────────────────────────
class Backdrop:
    """窗口背景效果，不支持时自动降级。

    mode:
        "opaque"      不透明（默认，最稳，所有系统一致）
        "translucent" 半透明（-alpha，全系统可用）
        "glass"       亚克力/云母（Win11 用 DWM backdrop，Win10 用传统亚克力）
    """

    OPAQUE = "opaque"
    TRANSLUCENT = "translucent"
    GLASS = "glass"

    # 透明色键：Tk 会把画布中这个精确颜色挖空。取一个几乎不可能被
    # 用户界面用到的值，避免误伤正常内容。
    CHROMA_KEY = "#010203"

    def __init__(self, window) -> None:
        self._window = window
        self._mode = self.OPAQUE
        self._blur = False
        self._chroma_applied = False

    @property
    def mode(self) -> str:
        return self._mode

    @property
    def blur_active(self) -> bool:
        """是否真的启用了系统模糊（决定要不要启用透明色键）。"""
        return self._blur

    @property
    def chroma_applied(self) -> bool:
        """是否已把画布色挖空（玻璃模式下才为真）。"""
        return self._chroma_applied

    def available_modes(self) -> list:
        modes = [self.OPAQUE, self.TRANSLUCENT]
        if _is_windows:
            modes.append(self.GLASS)
        return modes

    def apply(self, mode: str, alpha: float = 0.92) -> None:
        if mode not in (self.OPAQUE, self.TRANSLUCENT, self.GLASS):
            mode = self.OPAQUE
        self._mode = mode

        self.clear_chroma()
        self._disable_blur()
        try:
            self._window.attributes("-alpha", 1.0)
        except Exception:
            pass

        if mode == self.OPAQUE:
            return

        if mode == self.TRANSLUCENT:
            self._set_alpha(alpha)
            return

        self._blur = self._enable_blur()
        if not self._blur:
            # 系统模糊不可用 → 退回半透明，至少保留通透感
            self._set_alpha(alpha)
            return

        # 模糊成功：把画布色挖空，让系统背景透出来（真正的"液态玻璃"）
        self._enable_chroma()

    def _enable_chroma(self) -> None:
        """把窗口画布设为色键并挖空，露出后面的系统模糊背景。

        只有模糊确实生效时才这么做——否则会露出未处理的桌面，很难看。
        """
        try:
            self._window.attributes("-transparentcolor", self.CHROMA_KEY)
            self._chroma_applied = True
        except Exception:
            self._chroma_applied = False

    def clear_chroma(self) -> None:
        """取消透明色键（切回不透明/半透明时必须调用）。"""
        try:
            self._window.attributes("-transparentcolor", "")
        except Exception:
            pass
        self._chroma_applied = False

    def canvas_color(self, fallback: str) -> str:
        """当前模式下窗口画布应使用的颜色。"""
        if self._mode == self.GLASS and self._chroma_applied:
            return self.CHROMA_KEY
        return fallback

    def _set_alpha(self, alpha: float) -> None:
        try:
            self._window.attributes("-alpha", max(0.35, min(1.0, float(alpha))))
        except Exception:
            pass

    def _enable_blur(self) -> bool:
        if not _load():
            return False
        hwnd = top_level_handle(self._window)
        if not hwnd:
            return False
        if is_windows_11():
            if _dwm_set(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_TRANSIENTWINDOW):
                return True
        return self._legacy_acrylic(hwnd)

    def _legacy_acrylic(self, hwnd: int) -> bool:
        try:
            fn = getattr(_user32, "SetWindowCompositionAttribute", None)
            if fn is None:
                return False
            policy = _AccentPolicy()
            # Win10 上 blurbehind 比 acrylic 稳（acrylic 在部分版本拖动会卡）
            policy.AccentState = (
                ACCENT_ENABLE_ACRYLICBLURBEHIND if is_windows_11()
                else ACCENT_ENABLE_BLURBEHIND
            )
            policy.AccentFlags = 2
            policy.GradientColor = 0x66000000
            policy.AnimationId = 0
            data = _WinCompAttrData()
            data.Attribute = WCA_ACCENT_POLICY
            data.Data = ctypes.pointer(policy)
            data.SizeOfData = ctypes.sizeof(policy)
            return bool(fn(wintypes.HWND(hwnd), ctypes.byref(data)))
        except Exception:
            return False

    def _disable_blur(self) -> None:
        if _load():
            hwnd = top_level_handle(self._window)
            if hwnd:
                if is_windows_11():
                    _dwm_set(hwnd, DWMWA_SYSTEMBACKDROP_TYPE, DWMSBT_NONE)
                try:
                    fn = getattr(_user32, "SetWindowCompositionAttribute", None)
                    if fn is not None:
                        policy = _AccentPolicy()
                        policy.AccentState = ACCENT_DISABLED
                        data = _WinCompAttrData()
                        data.Attribute = WCA_ACCENT_POLICY
                        data.Data = ctypes.pointer(policy)
                        data.SizeOfData = ctypes.sizeof(policy)
                        fn(wintypes.HWND(hwnd), ctypes.byref(data))
                except Exception:
                    pass
        self._blur = False


# ── 置顶 ──────────────────────────────────────────────────
def set_topmost(window, enabled: bool) -> None:
    try:
        window.attributes("-topmost", enabled)
    except Exception:
        pass
    _push_topmost(window, enabled)


def is_topmost(window) -> bool:
    if not _load():
        return False
    hwnd = top_level_handle(window)
    if not hwnd:
        return False
    try:
        style = _user32.GetWindowLongPtrW(wintypes.HWND(hwnd), GWL_EXSTYLE)
        return bool(style & WS_EX_TOPMOST)
    except Exception:
        return False


def _push_topmost(window, enabled: bool) -> bool:
    """只操作原生 z 序（SWP_NOACTIVATE 保证不抢键盘焦点）。"""
    if not _load():
        return False
    hwnd = top_level_handle(window)
    if not hwnd:
        return False
    try:
        if not _user32.IsWindow(wintypes.HWND(hwnd)):
            return False
        insert_after = HWND_TOPMOST if enabled else HWND_NOTOPMOST
        return bool(_user32.SetWindowPos(
            wintypes.HWND(hwnd),
            wintypes.HWND(insert_after),
            0, 0, 0, 0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOOWNERZORDER,
        ))
    except Exception:
        return False


class TopmostKeeper:
    """窗口置顶。

    simple（默认）：只用 Tk 的 -topmost 属性，标准做法、最稳。
    aggressive（可选）：周期性 SetWindowPos 重申 z 序，用于压制同样是置顶
    窗口的程序（典型：PowerPoint 全屏放映）。需要持续 Win32 调用，
    个别环境有兼容风险，故默认关闭。
    """

    def __init__(
        self, window, interval_ms: int = 900, aggressive: bool = False
    ) -> None:
        self._window = window
        self._interval = interval_ms
        self._aggressive = aggressive
        self._job: Optional[str] = None
        self._enabled = False

    @property
    def enabled(self) -> bool:
        return self._enabled

    @property
    def aggressive(self) -> bool:
        return self._aggressive

    def set_enabled(self, enabled: bool) -> None:
        enabled = bool(enabled)
        if enabled == self._enabled:
            if enabled:
                self._apply()
            return
        self._enabled = enabled
        self._apply()
        if enabled and self._aggressive:
            self._schedule()
        else:
            self._cancel()

    def refresh(self) -> None:
        if self._enabled:
            self._apply()

    def stop(self) -> None:
        self._enabled = False
        self._cancel()

    def _apply(self) -> None:
        set_topmost(self._window, self._enabled)
        if self._enabled and self._aggressive:
            _push_topmost(self._window, True)

    def _schedule(self) -> None:
        self._cancel()
        try:
            self._job = self._window.after(self._interval, self._tick)
        except Exception:
            self._job = None

    def _cancel(self) -> None:
        if self._job is not None:
            try:
                self._window.after_cancel(self._job)
            except Exception:
                pass
            self._job = None

    def _tick(self) -> None:
        """仅 aggressive 模式。每次都必须重申——带 topmost 标志不代表在最前。"""
        self._job = None
        if not self._enabled or not self._aggressive:
            return
        _push_topmost(self._window, True)
        self._schedule()
