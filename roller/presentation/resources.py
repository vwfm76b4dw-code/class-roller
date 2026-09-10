"""资源路径解析。

打包后资源被解压到 sys._MEIPASS，开发时在包目录下，
两种情形统一通过 asset_path() 访问。
"""

from __future__ import annotations

import sys
from pathlib import Path


def _base_dir() -> Path:
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled)
    # roller/presentation/resources.py → roller/
    return Path(__file__).resolve().parent.parent


def asset_path(name: str) -> Path:
    """返回 roller/assets/ 下资源文件的实际路径。"""
    return _base_dir() / "assets" / name


def apply_app_icon(window) -> None:
    """给窗口设置应用图标。

    CustomTkinter 会在初始化时覆盖图标，因此设置两次：立即一次，
    稍后再补一次。
    """
    path = asset_path("app.ico")
    if not path.exists():
        return
    for delay in (0, 300):
        try:
            if delay:
                window.after(delay, lambda: _set_icon(window, path))
            else:
                _set_icon(window, path)
        except Exception:
            pass


def _set_icon(window, path: Path) -> None:
    try:
        window.iconbitmap(str(path))
    except Exception:
        pass
