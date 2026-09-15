"""WebView2 表现层测试。

覆盖换架构后新引入的部分：
- 桥接层（WebApi）每个方法都可调用且返回可序列化结果
- 非法输入不抛异常（前端会静默失败，必须在这里兜住）
- 窗口几何钳制与多显示器
- WebView2 运行时检测
- 前端资源完整、无外部依赖（离线可用）

不需要真的开窗口——桥接层与窗口层都设计成可脱离 GUI 测试。
"""

import json
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from roller.application.app_controller import AppController
from roller.infrastructure.config_store import ConfigStore
from roller.infrastructure.roster_parser import RosterParser
from roller.presentation.api import WebApi


def _api(with_roster: bool = True):
    cfg = Path(tempfile.mkdtemp()) / "config.json"
    ctrl = AppController(ConfigStore(cfg), RosterParser())
    if with_roster:
        for name in ("张三", "李四", "王五"):
            ctrl.add_student(name)
    return WebApi(ctrl, window=None), ctrl


# ── 桥接层：基本信息 ──────────────────────────────────────
def test_overview_shape():
    api, _ = _api()
    data = api.overview()
    assert data["count"] == 3
    assert data["names"] == ["张三", "李四", "王五"]


def test_overview_empty_roster():
    api, _ = _api(with_roster=False)
    data = api.overview()
    assert data["count"] == 0
    assert data["names"] == []


def test_status_text():
    api, _ = _api()
    text = api.status()
    assert "3 名学生" in text
    assert "已抽 0 次" in text


def test_status_mentions_fair_mode_when_on():
    api, ctrl = _api()
    ctrl.set_fair_mode(True)
    assert "一轮不重复" in api.status()


def test_history_empty():
    assert _api()[0].history() == []


def test_history_newest_first():
    api, ctrl = _api()
    for _ in range(3):
        ctrl.draw_now()
    records = api.history()
    assert len(records) == 3
    # 每条含 name/time，且可 JSON 序列化
    json.dumps(records)
    assert all(set(r) == {"name", "time"} for r in records)


def test_settings_payload():
    api, _ = _api()
    cfg = api.settings()
    for key in ("always_on_top", "fair_mode", "animations", "config_path"):
        assert key in cfg, key
    json.dumps(cfg)          # 必须可序列化，否则前端拿不到


# ── 桥接层：抽奖 ──────────────────────────────────────────
def test_draw_returns_name_in_roster():
    api, _ = _api()
    for _ in range(20):
        assert api.draw() in ("张三", "李四", "王五")


def test_draw_empty_roster_returns_none():
    api, _ = _api(with_roster=False)
    assert api.draw() is None


# ── 桥接层：名单操作 ──────────────────────────────────────
def test_add_students_parses_separators():
    api, ctrl = _api(with_roster=False)
    result = api.add_students("甲，乙、丙,丁")
    assert result["added"] == 4
    assert ctrl.student_count == 4


def test_add_students_allows_same_name():
    """手动添加允许同名——班里确实可能有两个张伟。"""
    api, ctrl = _api()
    result = api.add_students("张三")
    assert result["added"] == 1
    assert ctrl.student_count == 4
    assert ctrl.roster.count_of("张三") == 2


def test_add_students_handles_garbage():
    """非法输入不能抛异常——前端会静默失败。"""
    api, _ = _api()
    for bad in ("", "   ", ",,,", "、，", None if False else ""):
        result = api.add_students(bad)
        assert "added" in result


def test_clear_roster():
    api, ctrl = _api()
    assert api.clear_roster() is True
    assert ctrl.student_count == 0


def test_clear_history():
    api, ctrl = _api()
    ctrl.draw_now()
    assert api.clear_history() is True
    assert ctrl.history == []


def test_import_roster_missing_file_returns_error():
    """文件对话框被取消/文件不存在时返回结构化结果，不抛异常。"""
    api, _ = _api()
    api._pick_open_file = lambda: None          # 模拟用户取消
    result = api.import_roster()
    assert result.get("cancelled") is True


def test_import_roster_bad_path():
    api, _ = _api()
    api._pick_open_file = lambda: "Z:/不存在的文件.txt"
    result = api.import_roster()
    assert "error" in result


def test_import_roster_success():
    api, ctrl = _api(with_roster=False)
    fixture = ROOT / "tests" / "fixtures" / "A_plain.txt"
    api._pick_open_file = lambda: str(fixture)
    result = api.import_roster()
    assert result["count"] == 3
    assert result["total"] == 3
    assert ctrl.student_count == 3


def test_export_roster_cancelled():
    api, _ = _api()
    api._pick_save_file = lambda: None
    assert api.export_roster().get("cancelled") is True


def test_export_roster_empty_roster():
    api, _ = _api(with_roster=False)
    assert "error" in api.export_roster()


def test_export_roster_success():
    api, _ = _api()
    target = Path(tempfile.mkdtemp()) / "out.txt"
    api._pick_save_file = lambda: str(target)
    result = api.export_roster()
    assert result["ok"] is True
    assert target.exists()


# ── 桥接层：设置 ──────────────────────────────────────────
def test_toggle_topmost():
    api, ctrl = _api()
    before = ctrl.config.always_on_top
    after = api.toggle_topmost()
    assert after is (not before)
    assert ctrl.config.always_on_top is after


def test_set_fair_mode():
    api, ctrl = _api()
    api.set_fair_mode(True)
    assert ctrl.config.fair_mode is True
    api.set_fair_mode(False)
    assert ctrl.config.fair_mode is False




def test_set_animations():
    api, ctrl = _api()
    api.set_animations(False)
    assert ctrl.config.animations is False


def test_window_controls_without_window_do_not_crash():
    """没有窗口对象时（如测试环境）调用窗口控制不能崩。"""
    api, _ = _api()
    assert api.minimize() is False
    assert api.close() is False


# ── 窗口层 ────────────────────────────────────────────────
def test_clamp_keeps_window_inside_work_area():
    from roller.presentation.window_utils import (
        clamp_to_work_area,
        primary_work_area,
    )

    left, top, right, bottom = primary_work_area()
    x, y, w, h = clamp_to_work_area(-9999, -9999, 99999, 99999)
    assert left <= x and top <= y
    assert x + w <= right and y + h <= bottom


def test_clamp_accepts_valid_geometry_unchanged():
    from roller.presentation.window_utils import clamp_to_work_area

    x, y, w, h = clamp_to_work_area(300, 200, 460, 520)
    assert (x, y, w, h) == (300, 200, 460, 520)


def test_clamp_negatives_allowed_for_secondary_monitor():
    """副屏在主屏左侧是合法布置，不能把负坐标一律判为非法。"""
    from roller.presentation.window_utils import clamp_to_work_area

    x, y, w, h = clamp_to_work_area(-1900, 100, 460, 520)
    assert w == 460 and h == 520


def test_webview2_detection_returns_version_or_none():
    from roller.presentation.web_window import has_webview2, webview2_version

    version = webview2_version()
    assert version is None or isinstance(version, str)
    assert has_webview2() is (version is not None)


def test_window_size_bounds():
    """尺寸边界常量必须自洽。"""
    from roller.presentation import web_window as ww

    assert ww.MIN_W < ww.MAX_W
    assert ww.MIN_H < ww.MAX_H
    # 允许缩到很小（用户反馈"缩不到更小"）
    assert ww.MIN_W <= 260
    assert ww.MIN_H <= 200


# ── 前端资源 ──────────────────────────────────────────────
def test_web_assets_present():
    from roller.presentation.resources import web_dir

    base = web_dir()
    for name in ("index.html", "app.css", "app.js"):
        assert (base / name).exists(), f"缺少前端文件 {name}"


def test_web_ui_has_no_external_resources():
    """界面必须完全离线可用：不能引用外部 CDN/字体/图片。"""
    from roller.presentation.resources import web_dir

    base = web_dir()
    text = "".join(
        (base / name).read_text(encoding="utf-8")
        for name in ("index.html", "app.css", "app.js")
    ).lower()
    for pattern in ("http://", "https://", "//cdn", "cdnjs", "unpkg", "googleapis"):
        assert pattern not in text, f"界面引用了外部资源：{pattern}"



def test_web_ui_respects_reduced_motion():
    """必须尊重系统「减少动态效果」。"""
    from roller.presentation.resources import web_dir

    css = (web_dir() / "app.css").read_text(encoding="utf-8")
    assert "prefers-reduced-motion" in css


def test_web_ui_has_transparent_background():
    """页面背景必须透明，否则玻璃透不出桌面。"""
    from roller.presentation.resources import web_dir

    css = (web_dir() / "app.css").read_text(encoding="utf-8")
    assert "background: transparent" in css


def test_web_ui_exposes_required_api_calls():
    """前端调用的每个后端方法都必须真实存在。"""
    from roller.presentation.api import WebApi

    js = (ROOT / "roller" / "presentation" / "web" / "app.js").read_text(
        encoding="utf-8"
    )
    import re

    called = set(re.findall(r"call\(['\"](\w+)['\"]", js))
    called |= set(re.findall(r"api\(\)\.(\w+)\(", js))
    missing = [name for name in called if not hasattr(WebApi, name)]
    assert not missing, f"前端调用了后端不存在的方法：{missing}"


def test_index_uri_points_to_existing_file():
    """起始页 URI 必须指向真实存在的文件。

    回归测试：打包后 sys._MEIPASS 指向 _internal，若用
    Path(__file__).parent 这种写法会解析到归档内的虚拟路径，
    表现为窗口打开后显示 ERR_FILE_NOT_FOUND。
    """
    from urllib.parse import unquote, urlparse

    from roller.presentation.resources import index_uri

    uri = index_uri()
    parsed = urlparse(uri)
    assert parsed.scheme == "file", uri
    path = Path(unquote(parsed.path.lstrip("/")))
    assert path.exists(), f"起始页不存在: {path}"


def test_web_dir_follows_frozen_layout():
    """模拟 PyInstaller 打包布局：资源在 _MEIPASS/presentation/web。

    这条保证 resources.web_dir() 会优先尝试 _MEIPASS 路径，
    而不是依赖模块文件位置。
    """
    import importlib

    from roller.presentation import resources

    # 伪造 _MEIPASS 指向临时目录，并按打包布局放置资源
    import tempfile
    import sys as _sys

    tmp = Path(tempfile.mkdtemp())
    (tmp / "presentation" / "web").mkdir(parents=True)
    for name in ("index.html", "app.css", "app.js"):
        (tmp / "presentation" / "web" / name).write_text("x", encoding="utf-8")

    had = hasattr(_sys, "_MEIPASS")
    old = getattr(_sys, "_MEIPASS", None)
    _sys._MEIPASS = str(tmp)
    try:
        resolved = resources.web_dir()
        assert resolved == tmp / "presentation" / "web", resolved
        assert resources.index_uri().endswith("index.html")
    finally:
        if had:
            _sys._MEIPASS = old
        else:
            delattr(_sys, "_MEIPASS")


def test_window_uses_shared_index_uri():
    """窗口层必须复用 resources.index_uri()，不得自己拼路径。

    回归测试：曾用模块级 WEB_DIR = Path(__file__).parent / "web"，
    开发时正常、打包后失效。
    """
    src = (ROOT / "roller" / "presentation" / "web_window.py").read_text(
        encoding="utf-8"
    )
    assert "index_uri()" in src, "窗口应使用 resources.index_uri()"
    assert "WEB_DIR" not in src, "不应再自建 WEB_DIR 常量"



def test_ui_draws_its_own_material():
    """界面材料必须自绘，不依赖窗口透明。

    实测结论：Windows 拿不到窗口外内容的模糊，真透明会透出杂乱背景。
    因此材料（明度层次、高光、描边）必须在 CSS 里自绘。
    """
    from roller.presentation.resources import web_dir

    css = (web_dir() / "app.css").read_text(encoding="utf-8")
    assert "--surface" in css, "缺少材料明度定义"
    assert "inset 0 1px 0" in css, "缺少顶缘高光（材料的关键）"
    assert "border-radius: var(--r-window)" in css or "var(--r-window)" in css


def test_window_is_not_transparent():
    """窗口不做透明——透明需要背景模糊，Windows 上做不到。"""
    src = (ROOT / "roller" / "presentation" / "web_window.py").read_text(
        encoding="utf-8"
    )
    assert "transparent=False" in src, "窗口应为不透明"


def test_draw_animation_exists():
    """抽奖必须有分段动画（起跑/减速/落定），不是固定频率闪烁。"""
    js = (ROOT / "roller" / "presentation" / "web" / "app.js").read_text(
        encoding="utf-8"
    )
    assert "requestAnimationFrame" in js, "应自控动画节奏"
    assert "TIMING" in js and "runup" in js and "slow" in js, "应有分段时长"
    assert "settleWinner" in js, "应有落定动画"


def test_ui_no_external_resources_still():
    """界面完全离线：不引用任何外部资源。"""
    from roller.presentation.resources import web_dir

    base = web_dir()
    text = "".join(
        (base / n).read_text(encoding="utf-8")
        for n in ("index.html", "app.css", "app.js")
    ).lower()
    for pattern in ("http://", "https://", "//cdn", "unpkg", "googleapis"):
        assert pattern not in text, f"引用了外部资源: {pattern}"







if __name__ == "__main__":
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except Exception as exc:
                failures.append((name, exc))
                print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
    print()
    print("全部通过" if not failures else f"{len(failures)} 个失败")
    raise SystemExit(1 if failures else 0)
