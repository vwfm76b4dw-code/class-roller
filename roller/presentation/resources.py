"""资源路径解析。

打包后（PyInstaller onedir/onefile）资源位于 sys._MEIPASS 下，
开发时就在包目录里。统一通过这里的函数解析，避免界面文件里
硬编码相对路径而在打包后失效。
"""

from __future__ import annotations

import sys
from pathlib import Path


def _base_dir() -> Path:
    """打包后返回 _MEIPASS，否则返回 roller 包目录。"""
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled)
    return Path(__file__).resolve().parent.parent


def package_dir() -> Path:
    """roller 包的根目录（含 assets/ 与 presentation/）。"""
    return _base_dir()


def web_dir() -> Path:
    """Web 界面目录。

    PyInstaller 会把 roller/presentation/web 作为数据一并打进 _MEIPASS，
    因此打包后路径是 <_MEIPASS>/presentation/web。
    """
    candidates = [
        _base_dir() / "presentation" / "web",
        Path(__file__).resolve().parent / "web",
    ]
    for path in candidates:
        if path.is_dir() and (path / "index.html").exists():
            return path
    return candidates[0]


def asset_path(name: str) -> Path:
    """roller/assets/ 下的资源文件。"""
    return _base_dir() / "assets" / name


def index_uri() -> str:
    """界面首页的 file:// URI。"""
    return (web_dir() / "index.html").as_uri()
