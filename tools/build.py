"""一键构建脚本。

流程：生成版本资源 → 跑测试 → PyInstaller 打包 → 可选打 zip。

用法：
    python tools/build.py            # 打包
    python tools/build.py --zip      # 打包并生成可分发的 zip
    python tools/build.py --no-test  # 跳过测试（不推荐）
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
APP_DIR = DIST / "class-roller"

# 测试套件（前四个无图形依赖，后两个需要桌面环境）
CORE_TESTS = [
    "tests/test_domain.py",
    "tests/test_infrastructure.py",
    "tests/test_config_location.py",
    "tests/test_randomness.py",
    "tests/test_document_formats.py",
    "tests/test_web_ui.py",
    "tests/test_import_scenarios.py",
    "tests/test_import_e2e.py",
]
# v4.5 起界面为 WebView2，测试全部无需图形环境
GUI_TESTS: list = []


def read_version() -> str:
    ns: dict = {}
    exec((ROOT / "roller" / "_version.py").read_text(encoding="utf-8"), ns)
    return ns["__version__"]


def write_version_resource(version: str) -> Path:
    """生成 Windows 版本资源，让 exe 属性里显示版本/说明。"""
    parts = tuple(int(x) for x in version.split(".")) + (0,)
    a, b, c, d = parts[:4]
    text = f"""VSVersionInfo(
  ffi=FixedFileInfo(
    filevers=({a}, {b}, {c}, {d}),
    prodvers=({a}, {b}, {c}, {d}),
    mask=0x3f,
    flags=0x0,
    OS=0x40004,
    fileType=0x1,
    subtype=0x0,
    date=(0, 0)
  ),
  kids=[
    StringFileInfo([
      StringTable(
        '080404b0',
        [StringStruct('CompanyName', '课堂工具'),
         StringStruct('FileDescription', '课堂抽奖器'),
         StringStruct('FileVersion', '{version}'),
         StringStruct('InternalName', 'class-roller'),
         StringStruct('OriginalFilename', 'class-roller.exe'),
         StringStruct('ProductName', '课堂抽奖器'),
         StringStruct('ProductVersion', '{version}'),
         StringStruct('LegalCopyright', '')])
    ]),
    VarFileInfo([VarStruct('Translation', [2052, 1200])])
  ]
)
"""
    path = ROOT / "build" / "version_info.txt"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")
    return path


def run(cmd: list[str], **kw) -> int:
    print(f"$ {' '.join(cmd)}", flush=True)
    return subprocess.call(cmd, cwd=ROOT, **kw)


def run_tests(include_gui: bool) -> bool:
    suites = CORE_TESTS + (GUI_TESTS if include_gui else [])
    failed = []
    for suite in suites:
        print(f"\n--- {suite} ---", flush=True)
        rc = run([sys.executable, suite])
        if rc != 0:
            failed.append(suite)
    if failed:
        print("\n以下测试未通过：")
        for name in failed:
            print(f"  - {name}")
        return False
    print("\n全部测试通过")
    return True


def build() -> bool:
    if DIST.exists():
        shutil.rmtree(DIST, ignore_errors=True)
    if (ROOT / "build").exists():
        # 保留 version_info.txt，只清 PyInstaller 中间产物
        for child in (ROOT / "build").iterdir():
            if child.name != "version_info.txt":
                shutil.rmtree(child, ignore_errors=True) if child.is_dir() else child.unlink()
    rc = run(
        [sys.executable, "-m", "PyInstaller", "build_spec.spec", "--clean", "--noconfirm"]
    )
    if rc != 0:
        print("打包失败")
        return False
    exe = APP_DIR / "class-roller.exe"
    if not exe.exists():
        print(f"未找到产物 {exe}")
        return False
    size = sum(f.stat().st_size for f in APP_DIR.rglob("*") if f.is_file())
    print(f"\n产物: {APP_DIR}")
    print(f"体积: {size / 1024 / 1024:.1f} MB")
    return True


def make_zip(version: str) -> Path:
    target = DIST / f"class-roller-{version}-win64.zip"
    skip = {"config.json", "class-roller.tmp"}
    with zipfile.ZipFile(target, "w", zipfile.ZIP_DEFLATED) as zf:
        for path in sorted(APP_DIR.rglob("*")):
            if not path.is_file():
                continue
            # 不把本机配置和历史打进分发包
            if path.name in skip:
                continue
            zf.write(path, Path("class-roller") / path.relative_to(APP_DIR))
        # 附一份使用说明
        readme = ROOT / "README.md"
        if readme.exists():
            zf.write(readme, "class-roller/README.md")
    size = target.stat().st_size / 1024 / 1024
    print(f"\n分发包: {target}  ({size:.1f} MB)")
    print("解压后双击 class-roller.exe 即可运行。")
    return target


def main() -> int:
    parser = argparse.ArgumentParser(description="构建课堂抽奖器")
    parser.add_argument("--zip", action="store_true", help="打包后生成分发 zip")
    parser.add_argument("--no-test", action="store_true", help="跳过测试")
    parser.add_argument(
        "--no-gui-test", action="store_true", help="跳过需要桌面环境的测试"
    )
    args = parser.parse_args()

    version = read_version()
    print(f"课堂抽奖器 v{version}\n")

    write_version_resource(version)
    print("已生成版本资源")

    if not args.no_test:
        if not run_tests(include_gui=not args.no_gui_test):
            print("\n测试未通过，已中止打包。")
            return 1

    if not build():
        return 1

    if args.zip:
        make_zip(version)

    print("\n完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
