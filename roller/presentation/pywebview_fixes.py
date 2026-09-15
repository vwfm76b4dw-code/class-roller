"""修复 pywebview 在 64 位 Windows 上的窗口移动缺陷。

问题（实测崩溃栈确认）：
pywebview 的 winforms.py:620 `BrowserForm.move()` 里：

    windll.user32.SetWindowPos(
        self.Handle.ToInt32(), None,
        x_phys, y_phys,
        None, None,                    # ← 应为 0
        SWP_NOSIZE | SWP_NOZORDER | SWP_SHOWWINDOW,
    )

两处缺陷：
1. `cx/cy` 传了 `None`。设置了 SWP_NOSIZE 时应传 0，传 None 会让
   ctypes 抛 `TypeError: 'NoneType' object cannot be interpreted as an
   integer` → **进程直接崩溃**。
2. `self.Handle.ToInt32()` 在 64 位下会溢出（HWND 是指针宽度）。

由于 pywebview 的 `easy_drag` 默认开启，**用户一拖窗口就会崩**，
表现为"莫名其妙的崩溃"。

修复方式：运行期替换这两个方法（move / resize），用正确的实现。
不修改第三方库文件本身——升级依赖不会丢失修复。
"""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

_patched = False

SWP_NOSIZE = 0x0001
SWP_NOZORDER = 0x0004
SWP_SHOWWINDOW = 0x0040


def patch_pywebview_move() -> bool:
    """把 pywebview 的 move/resize 换成 64 位安全实现。返回是否成功。"""
    global _patched
    if _patched:
        return True
    if sys.platform != "win32":
        return False

    try:
        from webview.platforms import winforms  # type: ignore
        from webview.platforms.winforms import BrowserView  # type: ignore

        user32 = ctypes.WinDLL("user32", use_last_error=True)
        user32.SetWindowPos.restype = wintypes.BOOL
        user32.SetWindowPos.argtypes = [
            wintypes.HWND, wintypes.HWND,
            ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
            wintypes.UINT,
        ]

        form_cls = BrowserView.BrowserForm

        def _hwnd(self) -> int:
            # ToInt64：64 位下 HWND 是 8 字节，ToInt32 会溢出
            try:
                return int(self.Handle.ToInt64())
            except Exception:
                return int(self.Handle.ToInt32())

        def move(self, x, y):          # type: ignore[no-untyped-def]
            """移动窗口（逻辑像素 → 物理像素），尺寸不变。"""
            try:
                scale = getattr(self, "_scale", 1) or 1
                x_phys = int(x * scale)
                y_phys = int(y * scale)
                user32.SetWindowPos(
                    wintypes.HWND(_hwnd(self)),
                    None,
                    x_phys,
                    y_phys,
                    0,                      # cx：SWP_NOSIZE 时必须为 0
                    0,                      # cy：同上
                    SWP_NOSIZE | SWP_NOZORDER | SWP_SHOWWINDOW,
                )
            except Exception:
                pass

        def resize(self, width, height, fix_point):   # type: ignore[no-untyped-def]
            """调整窗口尺寸（逻辑像素），保持指定锚点。"""
            try:
                from webview.platforms.winforms import FixPoint  # type: ignore

                scale = getattr(self, "_scale", 1) or 1
                phys_w = int(width * scale)
                phys_h = int(height * scale)
                x = int(self.Location.X)
                y = int(self.Location.Y)
                if fix_point & FixPoint.EAST:
                    x = x + int(self.Width) - phys_w
                if fix_point & FixPoint.SOUTH:
                    y = y + int(self.Height) - phys_h
                user32.SetWindowPos(
                    wintypes.HWND(_hwnd(self)),
                    None,
                    x, y, phys_w, phys_h,
                    SWP_NOZORDER,
                )
            except Exception:
                pass

        form_cls.move = move
        form_cls.resize = resize
        _ = winforms          # 保持模块引用
        _patched = True
        return True
    except Exception:
        return False
