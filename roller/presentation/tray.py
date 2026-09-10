"""系统托盘服务。

托盘运行在独立线程（pystray 的要求），所有对 tkinter 的调用
都必须回到主线程执行，因此通过 after(0, ...) 投递。
"""

from __future__ import annotations

import threading
from typing import Callable, Optional

try:
    import pystray
    from PIL import Image, ImageDraw
    HAS_PYSTRAY = True
except ImportError:  # 缺少依赖时降级为"无托盘"，不影响主功能
    HAS_PYSTRAY = False

ICON_SIZE = 64


def _make_icon_image() -> "Image.Image":
    """程序内绘制托盘图标，避免额外图片资源。"""
    img = Image.new("RGBA", (ICON_SIZE, ICON_SIZE), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # 圆角方块底
    draw.rounded_rectangle(
        [4, 4, ICON_SIZE - 4, ICON_SIZE - 4],
        radius=16,
        fill=(76, 141, 255, 255),
    )
    # 三个点，象征"抽签"
    for i, cx in enumerate((22, 32, 42)):
        cy = 32 if i == 1 else 32
        r = 5 if i == 1 else 4
        draw.ellipse([cx - r, cy - r, cx + r, cy + r], fill=(255, 255, 255, 255))
    return img


class TrayService:
    """封装 pystray，提供显示/停止接口。"""

    def __init__(
        self,
        on_show: Callable[[], None],
        on_quit: Callable[[], None],
        title: str = "课堂抽奖器",
    ) -> None:
        self._on_show = on_show
        self._on_quit = on_quit
        self._title = title
        self._icon: Optional["pystray.Icon"] = None
        self._thread: Optional[threading.Thread] = None

    @property
    def available(self) -> bool:
        return HAS_PYSTRAY

    def start(self) -> bool:
        if not HAS_PYSTRAY or self._icon is not None:
            return False

        menu = pystray.Menu(
            pystray.MenuItem("显示窗口", self._handle_show, default=True),
            pystray.MenuItem("退出", self._handle_quit),
        )
        self._icon = pystray.Icon(
            "class-roller",
            _make_icon_image(),
            self._title,
            menu,
        )
        self._thread = threading.Thread(target=self._icon.run, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        if self._icon is not None:
            try:
                self._icon.stop()
            except Exception:
                pass
            self._icon = None

    def notify(self, message: str, title: str = "") -> None:
        if self._icon is None:
            return
        try:
            self._icon.notify(message, title or self._title)
        except Exception:
            pass

    # ── 菜单回调（在托盘线程中执行）──────────────────────
    def _handle_show(self, _icon=None, _item=None) -> None:
        self._on_show()

    def _handle_quit(self, _icon=None, _item=None) -> None:
        self.stop()
        self._on_quit()
