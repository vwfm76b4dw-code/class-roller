"""置顶行为验证。

场景：PPT 全屏放映窗口本身带 WS_EX_TOPMOST，且与我们的窗口没有
owner 关系。当它成为活动窗口时会盖住我们。验证 TopmostKeeper 能
周期性地把窗口抢回 z 序顶部。

注意：模拟窗口必须运行在独立进程里。同一进程内的 Toplevel 会被
系统视为 owner 的子窗口，永远位于 owner 之上，测不出真实行为。
"""

import ctypes
import subprocess
import sys
import time
from ctypes import wintypes
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

user32 = ctypes.windll.user32

GWL_EXSTYLE = -20
WS_EX_TOPMOST = 0x00000008

P = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def is_topmost(hwnd: int) -> bool:
    return bool(user32.GetWindowLongW(hwnd, GWL_EXSTYLE) & WS_EX_TOPMOST)


def visible_z_index(hwnd: int) -> int:
    """窗口在所有可见顶层窗口中的 z 序位置，越小越靠前。"""
    order = []

    def cb(h, _l):
        if user32.IsWindowVisible(h):
            order.append(h)
        return True

    user32.EnumWindows(P(cb), 0)
    return order.index(hwnd) if hwnd in order else -1


def pump(window, seconds: float) -> None:
    """等待并保持 tkinter 事件循环运行。"""
    deadline = time.time() + seconds
    while time.time() < deadline:
        window.update()
        time.sleep(0.05)


def main() -> int:
    import tempfile
    from pathlib import Path as P2

    from roller.application.app_controller import AppController
    from roller.infrastructure.config_store import ConfigStore
    from roller.infrastructure.roster_parser import RosterParser
    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import apply_theme
    from roller.presentation.window_utils import top_level_handle

    palette = apply_theme()
    cfg = P2(tempfile.mkdtemp()) / "config.json"
    controller = AppController(ConfigStore(cfg), RosterParser())
    sample = P2(__file__).resolve().parent.parent / "sample_names.txt"
    if sample.exists():
        controller.import_roster(str(sample))

    app = MainWindow(controller, palette)
    app.update_idletasks()
    hwnd = top_level_handle(app)
    print(f"抽奖窗口 HWND = {hwnd}")

    # 启动独立进程的模拟放映窗口
    fake_script = P2(__file__).resolve().parent / "fake_topmost_window.py"
    proc = subprocess.Popen(
        [sys.executable, str(fake_script)],
        stdout=subprocess.PIPE,
        text=True,
    )
    blocker_hwnd = None
    for _ in range(60):
        line = proc.stdout.readline()
        if line.startswith("HWND="):
            blocker_hwnd = int(line.strip().split("=")[1])
            break
        time.sleep(0.1)

    if blocker_hwnd is None:
        print("FAIL 模拟窗口未启动")
        proc.kill()
        app.destroy()
        return 1

    print(f"模拟放映窗口 HWND = {blocker_hwnd}")
    time.sleep(0.8)

    # 第一步：不开启置顶，模拟窗口应该盖住我们
    pump(app, 0.5)
    our_z = visible_z_index(hwnd)
    blk_z = visible_z_index(blocker_hwnd)
    print(f"[未开启置顶] 抽奖窗口 z={our_z}, 放映窗口 z={blk_z}")

    # 第二步：开启置顶，等待保持器把 z 序抢回来
    app._title_bar.set_pinned(True)
    app._topmost.set_enabled(True)
    pump(app, 3.0)

    our_z = visible_z_index(hwnd)
    blk_z = visible_z_index(blocker_hwnd)
    print(f"[开启置顶后] 抽奖窗口 z={our_z}, 放映窗口 z={blk_z}")
    print(f"[检查] WS_EX_TOPMOST = {is_topmost(hwnd)}")

    ok = our_z != -1 and blk_z != -1 and our_z < blk_z
    print()
    if ok:
        print("PASS 置顶保持器成功把抽奖窗口保持在放映窗口之上")
    else:
        print("FAIL 抽奖窗口仍在放映窗口之下")

    app._topmost.stop()
    app.destroy()
    proc.kill()
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
