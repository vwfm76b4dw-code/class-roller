"""Windows 窗口美化与置顶。

两件事：
1. 用 DWM 给原生窗口加 Win11 的圆角和无缝标题栏配色。
2. 维持置顶，让 PPT 全屏放映时也盖不住。

⚠️ 所有 Win32 调用都显式声明了 argtypes/restype。
不声明时 ctypes 默认按 32 位 int 处理，而 64 位 Windows 的 HWND 是指针；
HWND_TOPMOST(-1) 这类特殊值也会被错误转换，导致未定义行为——实测会让
窗口莫名其妙收到 SC_CLOSE 并自行隐藏。签名必须写全。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes
from typing import Optional

# ── Win32 常量 ────────────────────────────────────────────
GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008

HWND_TOPMOST = -1
HWND_NOTOPMOST = -2
SWP_NOSIZE = 0x0001
SWP_NOMOVE = 0x0002
SWP_NOACTIVATE = 0x0010
SWP_NOOWNERZORDER = 0x0200

GA_ROOT = 2

# DWM 窗口属性
DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWA_CAPTION_COLOR = 35
DWMWA_TEXT_COLOR = 36
DWMWCP_ROUND = 2

_is_windows = sys.platform == "win32"

# ── 函数签名（只声明一次）──────────────────────────────────
SPI_GETWORKAREA = 0x0030

_user32 = None
_dwmapi = None
_kernel32 = None


def _load() -> bool:
    """加载并配置 Win32 函数签名。"""
    global _user32, _dwmapi
    if not _is_windows:
        return False
    if _user32 is not None:
        return True
    try:
        user32 = ctypes.WinDLL("user32", use_last_error=True)

        user32.GetAncestor.restype = wintypes.HWND
        user32.GetAncestor.argtypes = [wintypes.HWND, wintypes.UINT]

        user32.GetParent.restype = wintypes.HWND
        user32.GetParent.argtypes = [wintypes.HWND]

        user32.IsWindow.restype = wintypes.BOOL
        user32.IsWindow.argtypes = [wintypes.HWND]

        user32.SetWindowPos.restype = wintypes.BOOL
        user32.SetWindowPos.argtypes = [
            wintypes.HWND,
            wintypes.HWND,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            ctypes.c_int,
            wintypes.UINT,
        ]

        user32.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        user32.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]

        user32.SystemParametersInfoW.restype = wintypes.BOOL
        user32.SystemParametersInfoW.argtypes = [
            wintypes.UINT, wintypes.UINT, ctypes.c_void_p, wintypes.UINT
        ]

        _user32 = user32

        _kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)

        dwm = ctypes.WinDLL("dwmapi", use_last_error=True)
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        dwm.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND,
            wintypes.DWORD,
            ctypes.c_void_p,
            wintypes.DWORD,
        ]
        _dwmapi = dwm
        return True
    except Exception:
        return False


def top_level_handle(window) -> Optional[int]:
    """取窗口真正的顶层 HWND。

    用 GetAncestor(GA_ROOT) 向上找到根窗口，比只取一层 GetParent 更可靠。
    """
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


# ── Win11 原生外观 ────────────────────────────────────────
def _colorref(hex_color: str) -> int:
    """把 #RRGGBB 转成 DWM 要的 COLORREF（0x00BBGGRR）。"""
    value = hex_color.lstrip("#")
    r = int(value[0:2], 16)
    g = int(value[2:4], 16)
    b = int(value[4:6], 16)
    return (b << 16) | (g << 8) | r


def apply_modern_frame(
    window,
    caption_color: Optional[str] = None,
    border_color: Optional[str] = None,
    text_color: Optional[str] = None,
) -> None:
    """给窗口加 Win11 圆角和标题栏配色。

    参数都是 #RRGGBB；传 None 表示用系统默认。低版本 Windows 上这些
    DWM 属性不存在，调用会失败，直接忽略即可（不影响功能）。
    """
    if not _load():
        return
    hwnd = top_level_handle(window)
    if not hwnd:
        return

    def _set(attribute: int, value: int) -> None:
        try:
            data = ctypes.c_int(value)
            _dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd),
                attribute,
                ctypes.byref(data),
                ctypes.sizeof(data),
            )
        except Exception:
            pass

    _set(DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND)
    if caption_color:
        _set(DWMWA_CAPTION_COLOR, _colorref(caption_color))
    if border_color:
        _set(DWMWA_BORDER_COLOR, _colorref(border_color))
    if text_color:
        _set(DWMWA_TEXT_COLOR, _colorref(text_color))


# ── 置顶 ──────────────────────────────────────────────────
def set_topmost(window, enabled: bool) -> None:
    """立即设置或取消置顶（同时同步 tkinter 属性）。"""
    try:
        window.attributes("-topmost", enabled)
    except Exception:
        pass
    _push_topmost(window, enabled)


def is_topmost(window) -> bool:
    """查询窗口当前是否带 WS_EX_TOPMOST。"""
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
    """只操作原生 z 序，不动 tkinter 属性。

    用 SWP_NOACTIVATE 保证不抢焦点——PPT 放映时翻页键仍然有效。
    返回是否调用成功。
    """
    if not _load():
        return False
    hwnd = top_level_handle(window)
    if not hwnd:
        return False
    try:
        if not _user32.IsWindow(wintypes.HWND(hwnd)):
            return False
        insert_after = HWND_TOPMOST if enabled else HWND_NOTOPMOST
        ok = _user32.SetWindowPos(
            wintypes.HWND(hwnd),
            wintypes.HWND(insert_after),
            0,
            0,
            0,
            0,
            SWP_NOSIZE | SWP_NOMOVE | SWP_NOACTIVATE | SWP_NOOWNERZORDER,
        )
        return bool(ok)
    except Exception:
        return False


class TopmostKeeper:
    """窗口置顶。

    两种模式：

    * **simple（默认）**：只用 Tk 的 -topmost 属性。这是标准做法，
      覆盖绝大多数场景（窗口保持在其它窗口之上）。不涉及周期性
      Win32 调用，行为最稳。

    * **aggressive（可选）**：周期性用 SetWindowPos 重申 z 序。
      用于和"同样是置顶窗口"的程序抢层级——最典型的是 PowerPoint
      全屏放映：放映窗口自身带 WS_EX_TOPMOST，两个置顶窗口按"最近
      被激活"排先后，放映时 PPT 是活动窗口就会把我们压到下面。
      这个模式需要持续调用 Win32 API，在部分环境下存在兼容风险
      （实测极少数情况下会干扰窗口消息），因此默认关闭。
    """

    def __init__(
        self,
        window,
        interval_ms: int = 900,
        aggressive: bool = False,
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
        """窗口重建（如从托盘恢复）后重申一次。"""
        if self._enabled:
            self._apply()

    def stop(self) -> None:
        self._enabled = False
        self._cancel()

    # ── 内部 ──────────────────────────────────────────────
    def _apply(self) -> None:
        """设置置顶。simple 模式走 Tk 属性，aggressive 额外压 z 序。"""
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
        """仅 aggressive 模式使用。

        每次都重申 z 序，不能因为"已经带 WS_EX_TOPMOST 就跳过"——
        带 topmost 标志只说明有置顶属性，但两个 topmost 窗口之间谁在前
        取决于谁最近被激活。强力模式的意义正是主动抢回第一，必须每次都压。
        """
        self._job = None
        if not self._enabled or not self._aggressive:
            return
        _push_topmost(self._window, True)
        self._schedule()

# ── 工作区（不含任务栏的屏幕区域）─────────────────────────
def work_area() -> tuple[int, int, int, int]:
    """返回主屏工作区 (left, top, right, bottom)。

    拿不到时退回整块屏幕（减去一条估计的任务栏高度），
    保证窗口永远不会越出可视范围、盖住任务栏。
    """
    if not _load():
        import tkinter as tk
        root = tk.Tk()
        root.withdraw()
        try:
            w = root.winfo_screenwidth()
            h = root.winfo_screenheight() - 40
        finally:
            root.destroy()
        return (0, 0, w, h)
    try:
        rect = wintypes.RECT()
        ok = _user32.SystemParametersInfoW(SPI_GETWORKAREA, 0, ctypes.byref(rect), 0)
        if ok:
            return (rect.left, rect.top, rect.right, rect.bottom)
    except Exception:
        pass
    import tkinter as tk
    root = tk.Tk()
    root.withdraw()
    try:
        w = root.winfo_screenwidth()
        h = root.winfo_screenheight() - 40
    finally:
        root.destroy()
    return (0, 0, w, h)


def clamp_to_work_area(
    x: int, y: int, width: int, height: int
) -> tuple[int, int, int, int]:
    """把窗口的位置和尺寸钳制到工作区内。"""
    left, top, right, bottom = work_area()
    area_w = max(1, right - left)
    area_h = max(1, bottom - top)

    width = max(1, min(width, area_w))
    height = max(1, min(height, area_h))
    x = max(left, min(x, right - width))
    y = max(top, min(y, bottom - height))
    return x, y, width, height
