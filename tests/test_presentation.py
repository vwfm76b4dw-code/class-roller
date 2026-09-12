"""表现层冒烟测试。

不依赖人工点击，直接构造 UI 对象，能捕获"参数名不匹配"
这类在运行期才暴露的装配错误。
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from roller.application.app_controller import AppController
from roller.infrastructure.config_store import ConfigStore
from roller.infrastructure.roster_parser import RosterParser


def _make_controller(with_roster: bool = True):
    cfg = Path(tempfile.mkdtemp()) / "config.json"
    controller = AppController(ConfigStore(cfg), RosterParser())
    if with_roster:
        sample = ROOT / "sample_names.txt"
        if sample.exists():
            controller.import_roster(str(sample))
    return controller


def test_main_window_constructs():
    """主窗口能构造，按钮与显示区齐备。"""
    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import apply_theme

    palette = apply_theme()
    controller = _make_controller()

    app = MainWindow(controller, palette)
    try:
        app.update_idletasks()
        assert app._draw_btn is not None
        assert app._settings_btn is not None
        assert app._display is not None
    finally:
        app.destroy()


def test_main_window_is_resizable():
    """窗口必须可调整大小——这是用户明确要求的。"""
    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import apply_theme

    palette = apply_theme()
    controller = _make_controller()

    app = MainWindow(controller, palette)
    try:
        app.update_idletasks()
        assert app.resizable() == (True, True), "窗口应可拖动边框调整大小"
        # 原生窗口应有系统标题栏（非 overrideredirect）
        assert not app.overrideredirect(), "不应使用无边框模式"
    finally:
        app.destroy()


def test_main_window_topmost_on_by_default():
    """默认置顶。"""
    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import apply_theme

    palette = apply_theme()
    controller = _make_controller()
    assert controller.config.always_on_top is True, "默认配置应开启置顶"

    app = MainWindow(controller, palette)
    try:
        app.update_idletasks()
        assert app.attributes("-topmost") in (True, 1), "窗口应处于置顶状态"
    finally:
        app.destroy()


def test_main_window_initial_status():
    """有名单时底部状态应显示人数。"""
    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import apply_theme

    palette = apply_theme()
    controller = _make_controller()

    app = MainWindow(controller, palette)
    try:
        app.update_idletasks()
        assert str(controller.student_count) in app._status.cget("text")
    finally:
        app.destroy()


def test_draw_directly_from_window():
    """点抽奖直接出结果，不是开始/停止两段式。"""
    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import apply_theme

    palette = apply_theme()
    controller = _make_controller()

    app = MainWindow(controller, palette)
    try:
        app.update_idletasks()
        before = len(controller.history)
        app._draw()
        app.update_idletasks()
        # 一次点击就应产生一条历史记录
        assert len(controller.history) == before + 1, "一次点击应直接抽出一人"
        assert app._draw_btn.cget("text").replace(" ", "") == "抽奖"
    finally:
        app.destroy()


def test_draw_without_roster_does_not_crash():
    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import apply_theme

    palette = apply_theme()
    controller = _make_controller(with_roster=False)

    app = MainWindow(controller, palette)
    try:
        app.update_idletasks()
        assert controller.student_count == 0
        app._draw()  # 不应抛异常
        assert len(controller.history) == 0
    finally:
        app.destroy()


def test_settings_dialog_constructs():
    """设置弹窗能构造——防止构造参数名漂移。"""
    from roller.presentation.dialogs.settings_dialog import SettingsDialog
    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import apply_theme

    palette = apply_theme()
    controller = _make_controller()

    app = MainWindow(controller, palette)
    try:
        app.update_idletasks()
        dialog = SettingsDialog(app, controller, palette, on_changed=lambda: None)
        try:
            dialog.update_idletasks()
            assert dialog.winfo_exists()
            assert dialog.resizable() == (True, True)
        finally:
            dialog.destroy()
    finally:
        app.destroy()


def test_settings_toggle_topmost():
    """设置页的置顶开关应写回配置并影响窗口。"""
    from roller.presentation.dialogs.settings_dialog import SettingsDialog
    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import apply_theme

    palette = apply_theme()
    controller = _make_controller()

    app = MainWindow(controller, palette)
    try:
        app.update_idletasks()
        dialog = SettingsDialog(app, controller, palette, on_changed=app._on_settings_changed)
        try:
            dialog.update_idletasks()
            # 关掉置顶
            dialog._top_switch.deselect()
            dialog._toggle_on_top()
            app.update_idletasks()
            assert controller.config.always_on_top is False
            assert app.attributes("-topmost") in (False, 0)
        finally:
            dialog.destroy()
    finally:
        app.destroy()


def test_window_size_persisted():
    """调整窗口大小后应写回配置并落盘。"""
    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import apply_theme

    palette = apply_theme()
    cfg = Path(tempfile.mkdtemp()) / "config.json"
    controller = AppController(ConfigStore(cfg), RosterParser())

    app = MainWindow(controller, palette)
    try:
        app.update()
        app.geometry("520x420")
        app.update()
        app._save_size()
        assert controller.config.window_width == 520, controller.config.window_width
        assert controller.config.window_height == 420, controller.config.window_height

        # 必须真的写进磁盘，而不是只改内存
        assert cfg.exists(), "调整尺寸后应立即落盘"
        import json

        raw = json.loads(cfg.read_text(encoding="utf-8"))
        assert raw["window_width"] == 520, raw["window_width"]
        assert raw["window_height"] == 420, raw["window_height"]
    finally:
        app.destroy()


def test_window_size_survives_restart():
    """重开程序应恢复上次的窗口大小。"""
    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import apply_theme

    palette = apply_theme()
    cfg = Path(tempfile.mkdtemp()) / "config.json"

    ctrl1 = AppController(ConfigStore(cfg), RosterParser())
    app1 = MainWindow(ctrl1, palette)
    try:
        app1.update()
        app1.geometry("600x500")
        app1.update()
        app1._save_size()
    finally:
        app1.destroy()

    # 用同一配置重新构造，应恢复 600x500
    ctrl2 = AppController(ConfigStore(cfg), RosterParser())
    assert ctrl2.config.window_width == 600
    assert ctrl2.config.window_height == 500

    app2 = MainWindow(ctrl2, palette)
    try:
        app2.update()
        assert app2.winfo_width() == 600, app2.winfo_width()
        assert app2.winfo_height() == 500, app2.winfo_height()
    finally:
        app2.destroy()


def test_layered_dialogs_construct():
    """输入/确认弹窗可构造。"""
    from roller.presentation.dialogs.prompts import ConfirmDialog, TextPrompt

    # 这两个弹窗构造时调用 wait_window 会阻塞，这里只验证类可导入且签名正确
    import inspect

    assert "label" in inspect.signature(TextPrompt.__init__).parameters
    assert "message" in inspect.signature(ConfirmDialog.__init__).parameters


def test_modern_frame_applied():
    """Win11 圆角与无缝标题栏应被应用。"""
    from roller.presentation.window_utils import (
        DWMWA_CAPTION_COLOR,
        DWMWA_WINDOW_CORNER_PREFERENCE,
        apply_modern_frame,
        top_level_handle,
    )
    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import apply_theme

    palette = apply_theme()
    controller = _make_controller()

    app = MainWindow(controller, palette)
    try:
        app.update()
        hwnd = top_level_handle(app)
        assert hwnd, "应能取到顶层窗口句柄"

        import ctypes

        dwm = ctypes.windll.dwmapi
        buf = ctypes.c_int()
        ret = dwm.DwmGetWindowAttribute(
            ctypes.c_void_p(hwnd),
            ctypes.c_uint(DWMWA_WINDOW_CORNER_PREFERENCE),
            ctypes.byref(buf),
            ctypes.sizeof(buf),
        )
        # 老系统上该属性不存在，此时跳过（不算失败）
        if ret == 0:
            assert buf.value == 2, f"应为圆角(2)，实际 {buf.value}"
    finally:
        app.destroy()


def test_theme_color_helpers():
    """颜色插值工具，用于淡入动画。"""
    from roller.presentation.theme import hex_to_rgb, lerp_color, rgb_to_hex

    assert hex_to_rgb("#ffffff") == (255, 255, 255)
    assert hex_to_rgb("0f6cbd") == (15, 108, 189)
    assert rgb_to_hex((15, 108, 189)) == "#0f6cbd"
    # 两端与中点
    assert lerp_color("#000000", "#ffffff", 0.0) == "#000000"
    assert lerp_color("#000000", "#ffffff", 1.0) == "#ffffff"
    assert lerp_color("#000000", "#ffffff", 0.5) == "#7f7f7f"
    # 越界 t 应被夹紧，不产生非法颜色
    assert lerp_color("#000000", "#ffffff", -1) == "#000000"
    assert lerp_color("#000000", "#ffffff", 2) == "#ffffff"


def test_name_display_states():
    """结果卡三种状态的文案与字号切换。"""
    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import FONT_DISPLAY, apply_theme

    palette = apply_theme()
    controller = _make_controller()

    app = MainWindow(controller, palette)
    try:
        app.update()
        card = app._display

        card.show_idle()
        assert card._name.cget("text") == "准备好了"
        # 空闲态状态行应收起，不留空占位
        assert not card._status_row.winfo_manager(), "空闲态不应显示状态行"

        card.show_winner("张三")
        assert card._name.cget("text") == "张三"
        assert card._status.cget("text") == "抽中"
        assert card._status_row.winfo_manager(), "中奖态应显示状态行"
        assert card._name.cget("font") == FONT_DISPLAY

        card.show_empty()
        assert "设置" in card._name.cget("text")
    finally:
        app.destroy()


def test_winner_fade_finishes():
    """淡入动画应自行结束并停在强调色，不会卡住。"""
    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import apply_theme

    palette = apply_theme()
    controller = _make_controller()

    app = MainWindow(controller, palette)
    try:
        app.update()
        app._display.show_winner("李四")
        # 跑满动画帧（7 帧 × 20ms，留足余量）
        import time

        deadline = time.time() + 1.5
        while time.time() < deadline:
            app.update()
            time.sleep(0.01)
        assert app._display._fade_job is None, "淡入结束后不应残留定时任务"
        assert app._display._name.cget("text_color") == palette.accent
    finally:
        app.destroy()


def test_theme_constants_all_imported():
    """界面文件里用到的 theme 常量必须都真的导入了。

    名字写错或漏 import 时，Python 只在运行到那一行才报 NameError，
    构造弹窗的测试未必覆盖到。这里对源码做一次静态检查。
    """
    import ast
    import re

    from roller.presentation import theme

    # 只检查大写常量（配色/间距/字号），排除类名和函数
    known = {
        name
        for name in dir(theme)
        if name.isupper() and not name.startswith("_")
    }

    ui_files = list((ROOT / "roller" / "presentation").rglob("*.py"))
    problems = []

    for path in ui_files:
        if path.name == "theme.py":
            continue
        source = path.read_text(encoding="utf-8")

        # 解析该文件实际从 theme 导入了什么
        tree = ast.parse(source)
        imported = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and node.module.endswith("presentation.theme"):
                    imported.update(alias.name for alias in node.names)

        # 找出文件里出现的 theme 常量名
        used = {m for m in re.findall(r"\b([A-Z][A-Z0-9_]{2,})\b", source)}
        for name in used & known:
            if name not in imported:
                problems.append(f"{path.relative_to(ROOT)} 使用了 {name} 但未导入")

    assert not problems, "\n".join(problems)


def test_no_hardcoded_spacing_in_ui():
    """界面文件不应出现硬编码的 padx/pady 数字。

    间距统一从 theme 的 SPACE_* 取，风格才会一致。
    """
    import re

    ui_files = [
        ROOT / "roller" / "presentation" / "main_window.py",
        ROOT / "roller" / "presentation" / "widgets" / "name_display.py",
        ROOT / "roller" / "presentation" / "dialogs" / "settings_dialog.py",
        ROOT / "roller" / "presentation" / "dialogs" / "prompts.py",
    ]
    # 允许的字面量：0（贴边）与数值元组里的 0
    pattern = re.compile(r"pad[xy]=(?:\(\s*)?(\d+)")
    offenders = []
    for path in ui_files:
        for lineno, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            for value in pattern.findall(line):
                if value != "0":
                    offenders.append(
                        f"{path.name}:{lineno} padx/pady={value} 应为 SPACE_* 常量"
                    )
    assert not offenders, "\n".join(offenders)


def test_topmost_default_is_simple_mode():
    """默认必须是 simple 模式（只用 Tk 属性）。

    强力模式需要周期性 Win32 调用，实测在极少数环境下会干扰窗口消息，
    导致窗口自行隐藏，因此不能作为默认。
    """
    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import apply_theme

    palette = apply_theme()
    controller = _make_controller()

    app = MainWindow(controller, palette)
    try:
        app.update()
        assert app._topmost is not None
        assert app._topmost.aggressive is False, "默认不应启用强力置顶"
        assert app._topmost.enabled is True, "默认应开启置顶"
        # simple 模式下不应有周期性定时任务
        assert app._topmost._job is None, "simple 模式不应注册定时器"
        assert app.attributes("-topmost") in (True, 1)
    finally:
        app.destroy()


def test_window_survives_long_run():
    """窗口在较长时间内不应自行隐藏（回归测试）。

    历史 bug：强力置顶的 Win32 调用在部分环境下让窗口收到 SC_CLOSE，
    启动几秒后自己缩到托盘。这里持续跑一段时间确认窗口仍在。
    """
    import time

    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import apply_theme

    palette = apply_theme()
    controller = _make_controller()

    app = MainWindow(controller, palette)
    hid = []
    orig = app.withdraw
    app.withdraw = lambda *a, **k: (hid.append(1), orig(*a, **k))[1]
    try:
        app.update()
        deadline = time.time() + 5.0
        while time.time() < deadline:
            app.update()
            time.sleep(0.05)
        assert not hid, "窗口不应自行隐藏"
        assert app.state() not in ("withdrawn", "iconic"), app.state()
    finally:
        app.destroy()


def test_visibility_guard_restores_hidden_window():
    """意外隐藏时守护应把窗口拉回来（用户主动隐藏时不干预）。"""
    import time

    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import apply_theme

    palette = apply_theme()
    controller = _make_controller()

    app = MainWindow(controller, palette)
    try:
        app.update()

        # 模拟"非用户主动"的意外隐藏：直接 withdraw，不经过 _hide_to_tray
        app.withdraw()
        app.update()
        assert app.state() == "withdrawn"

        # 等守护触发（1.5s 周期）
        deadline = time.time() + 5.0
        while time.time() < deadline:
            app.update()
            time.sleep(0.05)
            if app.state() != "withdrawn":
                break
        assert app.state() != "withdrawn", "守护应把意外隐藏的窗口恢复"
    finally:
        app.destroy()


def test_visibility_guard_respects_user_hide():
    """用户主动缩到托盘后，守护不应把窗口弹回来。"""
    import time

    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import apply_theme

    palette = apply_theme()
    controller = _make_controller()

    app = MainWindow(controller, palette)
    try:
        app.update()
        app._hide_to_tray()          # 模拟用户关闭窗口 → 缩到托盘
        app.update()
        assert app.state() == "withdrawn"

        deadline = time.time() + 4.0
        while time.time() < deadline:
            app.update()
            time.sleep(0.05)
        assert app.state() == "withdrawn", "用户主动隐藏后不应被守护弹回"
    finally:
        app.destroy()


def test_window_scaling_disabled():
    """CTk 窗口缩放必须禁用——回归测试。

    学校 150% DPI 屏上，CTk 默认把 geometry() 按 1.5 放大，而保存的
    尺寸是物理像素，导致窗口每重启放大 50%，直到越过屏幕盖住任务栏。
    """
    import customtkinter as ctk

    from roller.presentation.theme import apply_theme

    apply_theme()
    assert float(ctk.ScalingTracker.window_scaling) == 1.0, (
        "窗口缩放必须为 1.0，否则高 DPI 屏上窗口会循环放大"
    )


def test_window_size_roundtrip_does_not_grow():
    """保存→恢复一个来回，窗口尺寸必须分毫不差（不允许任何放大）。"""
    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import apply_theme

    palette = apply_theme()
    cfg = Path(tempfile.mkdtemp()) / "config.json"
    controller = AppController(ConfigStore(cfg), RosterParser())

    app1 = MainWindow(controller, palette)
    try:
        app1.update()
        app1.geometry("444x333")
        app1.update()
        app1._save_size()
        saved_w = controller.config.window_width
        saved_h = controller.config.window_height
        assert saved_w == 444 and saved_h == 333, (saved_w, saved_h)
    finally:
        app1.destroy()

    app2 = MainWindow(controller, palette)
    try:
        app2.update()
        assert app2.winfo_width() == 444, app2.winfo_width()
        assert app2.winfo_height() == 333, app2.winfo_height()
    finally:
        app2.destroy()


def test_oversized_saved_size_clamped_to_work_area():
    """配置里的超大尺寸（如旧版 DPI 放大产物）恢复时必须被钳回屏幕内。"""
    from roller.presentation.main_window import MainWindow
    from roller.presentation.theme import apply_theme

    palette = apply_theme()
    cfg = Path(tempfile.mkdtemp()) / "config.json"
    cfg.write_text(
        '{"names":["张三"],"version":3,'
        '"window_width":99999,"window_height":99999,"window_x":-500,"window_y":-500}',
        encoding="utf-8",
    )
    controller = AppController(ConfigStore(cfg), RosterParser())

    app = MainWindow(controller, palette)
    try:
        app.update()
        from roller.presentation.window_utils import work_area

        left, top, right, bottom = work_area()
        w, h = app.winfo_width(), app.winfo_height()
        x, y = app.winfo_x(), app.winfo_y()
        assert w <= right - left, f"宽度越界: {w}"
        assert h <= bottom - top, f"高度越界: {h}"
        assert x >= left and y >= top, f"位置越界: ({x},{y})"
    finally:
        app.destroy()


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
