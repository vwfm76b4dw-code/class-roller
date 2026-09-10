# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller 打包配置。

采用 **onedir（文件夹式）** 而非 onefile：
- onefile 每次启动都要把 Python 运行时解压到 %TEMP%，启动慢、易被杀软拦截；
- onedir 直接加载同目录的 DLL，启动快，形态与常见 Windows 软件一致。

产物 dist/class-roller/ 整个文件夹可以直接拷给别人用，
需要单文件分发时用 tools/make_release.py 打 zip。
"""

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# 版本号从包内读取，避免两处维护
_version_ns: dict = {}
exec(
    (Path(SPECPATH) / "roller" / "_version.py").read_text(encoding="utf-8"),
    _version_ns,
)
VERSION = _version_ns["__version__"]
VERSION_TUPLE = tuple(int(x) for x in VERSION.split(".")) + (0,)

datas = collect_data_files("customtkinter")
# 应用图标等资源要一起打进去
datas += [("roller/assets", "assets")]

hiddenimports = collect_submodules("customtkinter") + ["pystray", "PIL"]

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
        "numpy",
        "pygame",
        "matplotlib",
        "scipy",
        "pandas",
        "pytest",
        "setuptools",
        "pip",
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
