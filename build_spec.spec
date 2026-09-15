# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置（v4.5 WebView2 版）。

采用 onedir（文件夹式）：
- onefile 每次启动都要把运行时解压到 %TEMP%，启动慢且易被拦；
- onedir 直接加载同目录 DLL，启动快。

WebView2 相关：
- 界面资源（roller/presentation/web）作为数据一并打包
- 依赖目标机器已安装的 WebView2 运行时（Win11 自带）
- 若随包携带 bootstrapper，会打进 vendor/ 供首次运行自动安装
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

_version_ns: dict = {}
exec(
    (Path(SPECPATH) / "roller" / "_version.py").read_text(encoding="utf-8"),
    _version_ns,
)
VERSION = _version_ns["__version__"]

datas = collect_data_files("customtkinter")          # 兼容旧主题资源
datas += [("roller/assets", "assets")]
datas += [("roller/presentation/web", "presentation/web")]

# WebView2 bootstrapper（可选）：存在就打进去，用于缺运行时的机器自动安装
_vendor = Path(SPECPATH) / "vendor"
if _vendor.is_dir():
    datas += [(str(_vendor), "webview2")]

hiddenimports = collect_submodules("webview") + [
    "pystray",
    "PIL",
    "clr_loader",
    "pythonnet",
]

a = Analysis(
    ["roller/__main__.py"],
    pathex=[],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        "numpy", "pygame", "matplotlib", "scipy", "pandas", "pytest",
        "setuptools", "pip", "tkinter.test", "test",
    ],
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="class-roller",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon="roller/assets/app.ico",
    version="build/version_info.txt" if Path(SPECPATH, "build", "version_info.txt").exists() else None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="class-roller",
)
