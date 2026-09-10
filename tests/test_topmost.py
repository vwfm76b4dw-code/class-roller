"""置顶行为测试。

调用 tools/verify_topmost.py 的逻辑，验证窗口能在另一个独立的
TOPMOST 窗口（模拟 PPT 放映）之上保持置顶。
"""

import ctypes
import subprocess
import sys
import tempfile
import time
from ctypes import wintypes
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

user32 = ctypes.windll.user32
P = ctypes.WINFUNCTYPE(wintypes.BOOL, wintypes.HWND, wintypes.LPARAM)


def visible_z_index(hwnd: int) -> int:
    order = []

    def cb(h, _l):
        if user32.IsWindowVisible(h):
            order.append(h)
        return True

    user32.EnumWindows(P(cb), 0)
    return order.index(hwnd) if hwnd in order else -1


def pump(window, seconds: float) -> None:
    deadline = time.time() + seconds
    while time.time() < deadline:
        window.update()
        time.sleep(0.05)


def test_topmost_keeper_beats_independent_topmost_window():
    """强力置顶模式能压过同样是 TOPMOST 的独立窗口（模拟 PPT 放映）。

    注意：强力模式是**可选功能**，默认关闭。这里显式打开来验证其能力；
    默认走 simple 模式（只用 Tk 属性），由 test_presentation 中的
    test_topmost_default_is_simple_mode 守护。
    """
    from roller.application.app_controller import AppController
    from roller.infrastructure.config_store import ConfigStore
    from roller.infrastructure.roster_parser import RosterParser
    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import apply_theme
    from roller.presentation.window_utils import top_level_handle

    palette = apply_theme()
    cfg = Path(tempfile.mkdtemp()) / "config.json"
    controller = AppController(ConfigStore(cfg), RosterParser())
    sample = ROOT / "sample_names.txt"
    if sample.exists():
        controller.import_roster(str(sample))

    app = MainWindow(controller, palette)
    app.update()

    # 切到强力模式（测试目标就是这条路径）
    app._topmost._aggressive = True
    # 先关掉置顶，构造"被放映窗口盖住"的起始局面
    app._topmost.set_enabled(False)
    pump(app, 0.5)

    hwnd = top_level_handle(app)

    fake = ROOT / "tools" / "fake_topmost_window.py"
    proc = subprocess.Popen(
        [sys.executable, str(fake)], stdout=subprocess.PIPE, text=True
    )
    try:
        blocker_hwnd = None
        for _ in range(80):
            line = proc.stdout.readline()
            if line.startswith("HWND="):
                blocker_hwnd = int(line.strip().split("=")[1])
                break
            time.sleep(0.1)
        assert blocker_hwnd is not None, "模拟窗口未启动"

        time.sleep(0.8)
        pump(app, 0.4)

        # 开启置顶前，模拟窗口应在我们之上
        before_our = visible_z_index(hwnd)
        before_blk = visible_z_index(blocker_hwnd)
        assert before_our > before_blk, (
            f"前置条件不成立：我们的 z={before_our} 应大于放映窗口 z={before_blk}"
        )

        # 开启置顶，等待保持器生效
        app._topmost.set_enabled(True)
        pump(app, 3.0)

        after_our = visible_z_index(hwnd)
        after_blk = visible_z_index(blocker_hwnd)
        assert after_our != -1 and after_blk != -1
        assert after_our < after_blk, (
            f"置顶失效：我们的 z={after_our} 仍不小于放映窗口 z={after_blk}"
        )
    finally:
        app._topmost.stop()
        app.destroy()
        proc.kill()


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except Exception as exc:
                failures += 1
                print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
    print()
    print("全部通过" if not failures else f"{failures} 个失败")
    raise SystemExit(1 if failures else 0)
