"""程序入口：依赖装配。

这是唯一知道"具体实现"的地方——其他模块都只依赖抽象。

v4.5 起界面改用 WebView2 渲染：只有"透明窗口 + CSS backdrop-filter"
才能做出真正的液态玻璃（Tk 无法分区透明，做不到）。
领域层、基础设施层、应用层完全复用，未因换界面而改动。
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path

# 允许以脚本方式直接运行（未安装为包时）
if __package__ in (None, ""):
    sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from roller import __app_name__
from roller.application.app_controller import AppController
from roller.infrastructure.config_store import ConfigStore
from roller.infrastructure.roster_parser import RosterParser
from roller.presentation.tray import TrayService
from roller.presentation.web_window import WebView2Missing


def build_controller() -> AppController:
    """构造控制器及其依赖。测试时可复用此函数。"""
    return AppController(
        config_store=ConfigStore(),
        parser=RosterParser(),
    )


def _message_box(message: str, title: str) -> None:
    """用系统消息框报错——此时网页界面还起不来，只能走原生弹窗。"""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(None, message, title, 0x10 | 0x40000)
    except Exception:
        print(message, file=sys.stderr)


def main() -> int:
    from roller.presentation.web_window import WebWindow

    controller = build_controller()
    tray_holder: dict = {}

    window = WebWindow(controller, on_hide_to_tray=None)

    def start_tray() -> None:
        """托盘在独立线程里跑（pystray 的要求）。"""
        tray = TrayService(
            on_show=window.show_from_tray,
            on_quit=window.quit,
            title=__app_name__,
        )
        tray_holder["tray"] = tray
        if tray.available:
            tray.start()

    try:
        import webview

        def bootstrap() -> None:
            time.sleep(1.5)          # 等窗口真正显示出来
            start_tray()

        window.create()
        webview.start(
            bootstrap,
            gui="edgechromium",
            debug=bool(os.environ.get("CR_WEB_DEBUG")),
        )
    except WebView2Missing as exc:
        _message_box(str(exc), f"{__app_name__} 无法启动")
        return 2
    except Exception as exc:  # 兜底：任何启动失败都要让用户看到原因
        _message_box(f"启动失败：\n{exc!r}", f"{__app_name__} 无法启动")
        return 1
    finally:
        tray = tray_holder.get("tray")
        if tray is not None:
            tray.stop()
        controller.shutdown()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
