"""构建 Windows 安装包。

流程：读版本 → 确保程序目录已打包 → 调 Inno Setup 编译 → 输出 setup.exe。

用法：
    python tools/build_installer.py              # 需要 dist/class-roller 已存在
    python tools/build_installer.py --with-app   # 先构建程序再打安装包
"""

from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DIST = ROOT / "dist"
APP_DIR = DIST / "class-roller"
ISS = ROOT / "installer" / "class-roller.iss"

# Inno Setup 常见安装位置
ISCC_CANDIDATES = [
    Path(os.environ.get("LOCALAPPDATA", "")) / "Programs" / "Inno Setup 6" / "ISCC.exe",
    Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"),
    Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"),
    Path(os.environ.get("ProgramFiles(x86)", "")) / "Inno Setup 6" / "ISCC.exe",
]


def find_iscc() -> Path | None:
    """定位 Inno Setup 命令行编译器。"""
    # 1. 环境变量优先
    env = os.environ.get("ISCC_PATH")
    if env and Path(env).exists():
        return Path(env)

    # 2. 常见安装位置
    for candidate in ISCC_CANDIDATES:
        if candidate and candidate.exists():
            return candidate

    # 3. PATH 中查找
    found = shutil.which("ISCC") or shutil.which("iscc")
    if found:
        return Path(found)
    return None


def read_version() -> str:
    ns: dict = {}
    exec((ROOT / "roller" / "_version.py").read_text(encoding="utf-8"), ns)
    return ns["__version__"]


def check_app_built() -> bool:
    exe = APP_DIR / "class-roller.exe"
    if not exe.exists():
        print(f"未找到程序目录：{APP_DIR}")
        print("请先运行：python tools/build.py   （或加 --with-app 参数）")
        return False
    # 确认关键运行时文件都在，避免打出残缺的安装包
    internal = APP_DIR / "_internal"
    required = [internal / "python313.dll", internal / "assets" / "app.ico"]
    missing = [str(p) for p in required if not p.exists()]
    if missing:
        print("程序目录不完整，缺少：")
        for m in missing:
            print(f"  - {m}")
        return False
    return True


def compile_installer(iscc: Path, version: str) -> bool:
    output_dir = DIST
    output_dir.mkdir(parents=True, exist_ok=True)

    cmd = [
        str(iscc),
        f"/DMyAppVersion={version}",
        f"/DSourceDir={APP_DIR}",
        f"/DOutputDir={output_dir}",
        str(ISS),
    ]
    print(f"$ {' '.join(cmd)}\n")
    rc = subprocess.call(cmd, cwd=ROOT / "installer")
    if rc != 0:
        print(f"\nInno Setup 编译失败，退出码 {rc}")
        return False
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="构建 Windows 安装包")
    parser.add_argument(
        "--with-app", action="store_true", help="先构建程序再打安装包"
    )
    parser.add_argument("--version", help="覆盖版本号")
    args = parser.parse_args()

    version = args.version or read_version()
    print(f"课堂抽奖器 v{version} — 构建安装包\n")

    if args.with_app:
        print("先构建程序...\n")
        rc = subprocess.call([sys.executable, str(ROOT / "tools" / "build.py")])
        if rc != 0:
            print("程序构建失败")
            return 1
        print()

    if not check_app_built():
        return 1

    iscc = find_iscc()
    if iscc is None:
        print("未找到 Inno Setup 编译器 (ISCC.exe)。\n")
        print("安装方式（任选其一）：")
        print("  winget install JRSoftware.InnoSetup")
        print("  或到 https://jrsoftware.org/isdl.php 下载")
        print("\n已安装但不在默认位置时，可设置环境变量 ISCC_PATH 指向 ISCC.exe。")
        return 1
    print(f"编译器: {iscc}\n")

    if not compile_installer(iscc, version):
        return 1

    # 列出产物
    installers = sorted(DIST.glob("*-setup.exe"))
    if installers:
        print("\n安装包：")
        for path in installers:
            size = path.stat().st_size / 1024 / 1024
            print(f"  {path.name}  ({size:.1f} MB)")

    print("\n完成。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
