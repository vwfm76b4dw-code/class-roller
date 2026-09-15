"""无边框窗口的外观处理（Win11 圆角）。

只做一件安全的事：给窗口加系统圆角。
- 通过 DwmSetWindowAttribute 设置圆角与边框色，纯 Win32 调用
- 不涉及 .NET 控件的跨线程操作（WinForms 要求 UI 线程，跨线程会崩）
- 不使用全局鼠标钩子（曾导致崩溃）

历史教训（为什么这里这么"少"）：
1. 颜色键透明（TransparencyKey）会让挖空区域的鼠标事件穿透到下层窗口
2. 窗体的 WM_NCHITTEST 收不到鼠标消息——WebView2 子控件铺满了客户区，
   消息被它截获（实测：鼠标移到窗口边缘，窗体钩子收到 0 条消息）
3. 在后台线程修改 WinForms 控件会崩溃（不是线程安全的）
4. pywebview 的 move() 在 64 位下有 bug，见 pywebview_fixes.py

因此：窗口拖动交给 pywebview（已修复其 bug），
      圆角交给 DWM，界面材料在页面内绘制。
"""

from __future__ import annotations

import ctypes
import sys
import threading
import time
from ctypes import wintypes
from typing import Any, Optional

_is_windows = sys.platform == "win32"

DWMWA_WINDOW_CORNER_PREFERENCE = 33
DWMWA_BORDER_COLOR = 34
DWMWCP_ROUND = 2
DWMWA_COLOR_NONE = 0xFFFFFFFE

_dwmapi = None
_user32 = None
_loaded = False


def _load() -> bool:
    global _dwmapi, _user32, _loaded
    if not _is_windows:
        return False
    if _loaded:
        return _dwmapi is not None
    _loaded = True
    try:
        dwm = ctypes.WinDLL("dwmapi", use_last_error=True)
        dwm.DwmSetWindowAttribute.restype = ctypes.c_long
        dwm.DwmSetWindowAttribute.argtypes = [
            wintypes.HWND, wintypes.DWORD, ctypes.c_void_p, wintypes.DWORD
        ]
        _dwmapi = dwm

        u = ctypes.WinDLL("user32", use_last_error=True)
        u.GetWindowLongPtrW.restype = ctypes.c_ssize_t
        u.GetWindowLongPtrW.argtypes = [wintypes.HWND, ctypes.c_int]
        _user32 = u
        return True
    except Exception:
        _dwmapi = None
        return False


def _resolve_form(window: Any):
    try:
        import clr  # type: ignore

        clr.AddReference("System.Windows.Forms")
        from System.Windows.Forms import Form  # type: ignore
    except Exception:
        return None
    native = getattr(window, "native", None)
    if native is None:
        return None
    if isinstance(native, Form):
        return native
    try:
        return native.FindForm()
    except Exception:
        return None


def hwnd_of(window: Any) -> Optional[int]:
    """取窗口 HWND（64 位安全）。"""
    form = _resolve_form(window)
    if form is None:
        return None
    try:
        return int(form.Handle.ToInt64())
    except Exception:
        try:
            return int(form.Handle.ToInt32())
        except Exception:
            return None


def round_corners(window: Any) -> bool:
    """Win11 系统圆角 + 不画系统边框色。"""
    if not _load() or _dwmapi is None:
        return False
    hwnd = hwnd_of(window)
    if not hwnd:
        return False
    ok = False
    for attr, value in (
        (DWMWA_WINDOW_CORNER_PREFERENCE, DWMWCP_ROUND),
        (DWMWA_BORDER_COLOR, DWMWA_COLOR_NONE),
    ):
        try:
            data = ctypes.c_int(value & 0xFFFFFFFF)
            if _dwmapi.DwmSetWindowAttribute(
                wintypes.HWND(hwnd), attr, ctypes.byref(data), ctypes.sizeof(data)
            ) == 0:
                ok = True
        except Exception:
            pass
    return ok


def apply_rounded(window: Any, delay_ms: int = 600) -> None:
    """窗口显示后稍晚应用圆角（太早 DWM 还没准备好）。"""
    if not _is_windows:
        return

    def run() -> None:
        time.sleep(delay_ms / 1000.0)
        round_corners(window)
        time.sleep(0.5)
        round_corners(window)

    threading.Thread(target=run, daemon=True).start()
