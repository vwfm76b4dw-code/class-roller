"""程序入口：依赖装配。

这是唯一知道"具体实现"的地方——其他模块都只依赖抽象。
"""

from __future__ import annotations

import sys
from pathlib import Path

# 允许以脚本方式直接运行（未安装为包时）
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from roller import __app_name__
from roller.application.app_controller import AppController
from roller.infrastructure.config_store import ConfigStore
from roller.infrastructure.roster_parser import RosterParser
from roller.presentation.main_window import MainWindow
from roller.presentation.theme import apply_theme
from roller.presentation.tray import TrayService


def build_controller() -> AppController:
    """构造控制器及其依赖。测试时可复用此函数。"""
    return AppController(
        config_store=ConfigStore(),
        parser=RosterParser(),
    )


def main() -> int:
    palette = apply_theme()
    controller = build_controller()

    tray: TrayService | None = None
    app: MainWindow | None = None

    from roller import compat

    def hide_to_tray() -> None:
        """关闭/最小化时缩到托盘。"""
        if compat.NO_TRAY:
            return
        if tray is not None and tray.available:
            tray.start()

    def quit_app() -> None:
        controller.shutdown()
        if tray is not None:
            tray.stop()
        if app is not None:
            app.destroy()

    app = MainWindow(
        controller,
        palette,
        on_hide_to_tray=hide_to_tray,
        on_quit=quit_app,
    )

    # 托盘回调发生在托盘线程，必须回到 tkinter 主线程
    tray = TrayService(
        on_show=lambda: app.after(0, app.restore_from_tray),
        on_quit=lambda: app.after(0, quit_app),
        title=__app_name__,
    )

    try:
        app.mainloop()
    finally:
        controller.shutdown()
        if tray is not None:
            tray.stop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
