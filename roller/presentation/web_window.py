"""WebView2 窗口层。

替代原来的 Tk 表现层。要点：

- **无边框**：frameless，标题栏由页面自绘，可拖拽移动。
- **不做窗口透明**：实测 Windows 拿不到"窗口外内容的背景模糊"——
  CSS backdrop-filter 取不到窗口外像素，DWM 亚克力在部分版本只上色调
  不模糊。没有模糊的真透明会透出清晰杂乱的背景，文字难读。
  因此界面材料在页面内自绘（见 web/app.css），不依赖系统能力。
- **尺寸存物理像素**：WebView2 自己处理 DPI 缩放，网页内容随窗口
  自适应重排，不再需要"逻辑尺寸 ÷ 缩放系数"的换算。
- **始终钳制到工作区**：窗口不越出屏幕、不盖住任务栏。
- WebView2 运行时缺失时给出指引（随包携带 bootstrapper 时可自动安装）。
"""

from __future__ import annotations

import os
import subprocess
import sys
import threading
from pathlib import Path
from typing import Optional

from roller.presentation.resources import index_uri
from roller.presentation.window_utils import (
    clamp_to_work_area,
    primary_work_area,
)

# 窗口尺寸边界（物理像素）
MIN_W, MIN_H = 220, 170    # 允许缩到很小
MAX_W, MAX_H = 3000, 2000

# WebView2 运行时注册表位置（官方 bootstrapper 用的 key）
_WEBVIEW2_KEYS = (
    r"SOFTWARE\WOW6432Node\Microsoft\EdgeUpdate\Clients"
    r"\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
    r"SOFTWARE\Microsoft\EdgeUpdate\Clients"
    r"\{F3017226-FE2A-4295-8BDF-00C3A9A7E4C5}",
)


def webview2_version() -> Optional[str]:
    """检测已安装的 WebView2 运行时版本；未安装返回 None。"""
    if sys.platform != "win32":
        return None
    try:
        import winreg

        for root in (winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER):
            for key in _WEBVIEW2_KEYS:
                try:
                    with winreg.OpenKey(root, key) as handle:
                        value, _ = winreg.QueryValueEx(handle, "pv")
                        if value:
                            return str(value)
                except OSError:
                    continue
    except Exception:
        pass
    return None


def has_webview2() -> bool:
    return webview2_version() is not None


class WebView2Missing(RuntimeError):
    """WebView2 运行时未安装。"""

    def __init__(self) -> None:
        super().__init__(
            "缺少 Microsoft Edge WebView2 运行时。\n\n"
            "这是显示界面所必需的组件（Win11 自带，部分 Win10 需要安装）。\n"
            "安装地址：https://go.microsoft.com/fwlink/p/?LinkId=2124703"
        )


def install_webview2(progress=None) -> bool:
    """用微软官方 bootstrapper 安装 WebView2 运行时。

    仅在随包附带 bootstrapper 时可用；否则返回 False，由调用方提示用户
    手动安装。需要联网。
    """
    bootstrap = _find_bootstrapper()
    if bootstrap is None:
        return False
    try:
        if progress:
            progress("正在安装 WebView2 运行时…")
        creation = 0
        if sys.platform == "win32":
            creation = subprocess.CREATE_NO_WINDOW  # type: ignore[attr-defined]
        rc = subprocess.call(
            [str(bootstrap), "/silent", "/install"],
            creationflags=creation,
        )
        return rc == 0 and has_webview2()
    except Exception:
        return False


def _find_bootstrapper() -> Optional[Path]:
    """查找随包携带的 WebView2 bootstrapper。"""
    from roller.presentation.resources import package_dir

    candidates = [
        # 打包后：随包携带（spec 里 vendor → _internal/webview2）
        package_dir() / "webview2" / "MicrosoftEdgeWebview2Setup.exe",
        # onedir：程序目录旁边
        Path(sys.executable).resolve().parent / "webview2" / "MicrosoftEdgeWebview2Setup.exe",
        # 开发时：项目 vendor 目录
        Path(__file__).resolve().parent.parent.parent / "vendor" / "MicrosoftEdgeWebview2Setup.exe",
    ]
    for path in candidates:
        try:
            if path and path.exists():
                return path
        except Exception:
            continue
    return None


class WebWindow:
    """管理 pywebview 窗口的生命周期。"""

    def __init__(self, controller, on_hide_to_tray=None, on_quit=None) -> None:
        self._c = controller
        self._window = None
        self._api = None
        self._on_hide_to_tray = on_hide_to_tray
        self._on_quit = on_quit
        self._save_job: Optional[threading.Timer] = None
        self._quitting = False

    # ── 创建 ──────────────────────────────────────────────
    def create(self):
        import webview

        from roller.presentation.api import WebApi

        cfg = self._c.config
        width, height = self._initial_size()
        x, y = self._initial_position(width, height)

        self._api = WebApi(self._c, None)
        self._api.set_close_handler(self.hide_to_tray)

        self._window = webview.create_window(
            "课堂抽奖器",
            url=index_uri(),
            js_api=self._api,
            width=width,
            height=height,
            x=x,
            y=y,
            min_size=(MIN_W, MIN_H),
            frameless=True,          # 无系统标题栏（自绘）
            # 不做透明：实测 Windows 拿不到"窗口外内容的模糊"，
            # 无模糊的真透明会透出杂乱背景。改在页面内自绘材料质感。
            transparent=False,
            on_top=bool(cfg.always_on_top),
            easy_drag=False,         # 拖动由页面上的 -webkit-app-region 控制
            resizable=True,
            text_select=False,
            confirm_close=False,
        )
        self._api.attach_window(self._window)

        self._window.events.resized += self._on_resized
        self._window.events.moved += self._on_moved
        self._window.events.closing += self._on_closing
        return self._window

    def _initial_size(self):
        cfg = self._c.config
        w = int(getattr(cfg, "window_width", 400) or 400)
        h = int(getattr(cfg, "window_height", 430) or 430)
        w = max(MIN_W, min(MAX_W, w))
        h = max(MIN_H, min(MAX_H, h))
        return w, h

    def _initial_position(self, width: int, height: int):
        cfg = self._c.config
        x = int(getattr(cfg, "window_x", -1) or -1)
        y = int(getattr(cfg, "window_y", -1) or -1)
        if x < 0 or y < 0:
            left, top, right, bottom = primary_work_area()
            x = left + (right - left - width) // 2
            y = top + (bottom - top - height) // 3
        return clamp_to_work_area(x, y, width, height)[:2]

    # ── 运行 ──────────────────────────────────────────────
    def run(self) -> int:
        import webview

        if not has_webview2():
            if install_webview2():
                pass
            else:
                raise WebView2Missing()
        self.create()
        webview.start(gui="edgechromium", debug=bool(os.environ.get("CR_WEB_DEBUG")))
        return 0

    # ── 事件 ──────────────────────────────────────────────
    def _on_resized(self, width, height) -> None:
        self._schedule_save()

    def _on_moved(self, x, y) -> None:
        self._schedule_save()

    def _on_closing(self) -> bool:
        """关闭按钮 → 缩到托盘（除非正在真正退出）。"""
        if self._quitting:
            self._persist_geometry()
            return True
        self.hide_to_tray()
        return False        # 阻止真正销毁


    # ── 几何持久化 ────────────────────────────────────────
    def _schedule_save(self) -> None:
        if self._save_job is not None:
            self._save_job.cancel()
        self._save_job = threading.Timer(0.6, self._persist_geometry)
        self._save_job.daemon = True
        self._save_job.start()

    def _persist_geometry(self) -> None:
        try:
            if self._window is None:
                return
            w = int(self._window.width or 0)
            h = int(self._window.height or 0)
            if w < MIN_W or h < MIN_H:
                return
            x = int(self._window.x or 0)
            y = int(self._window.y or 0)
            x, y, w, h = clamp_to_work_area(x, y, w, h)
            self._c.set_window_size(w, h)
            self._c.set_window_position(x, y)
        except Exception:
            pass

    # ── 外部控制 ──────────────────────────────────────────
    def hide_to_tray(self) -> None:
        self._persist_geometry()
        try:
            if self._window is not None:
                self._window.hide()
        except Exception:
            pass
        if self._on_hide_to_tray:
            self._on_hide_to_tray()

    def show_from_tray(self) -> None:
        try:
            if self._window is not None:
                self._window.show()
        except Exception:
            pass

    def quit(self) -> None:
        self._quitting = True
        self._persist_geometry()
        self._c.shutdown()
        try:
            if self._window is not None:
                self._window.destroy()
        except Exception:
            pass
        if self._on_quit:
            self._on_quit()
