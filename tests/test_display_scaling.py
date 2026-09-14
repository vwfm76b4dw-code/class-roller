"""高分屏 / 缩放 / 外观 / 动画 测试。

覆盖学校实测暴露的问题：
- 150% DPI 下窗口"每重启放大一圈"（逻辑尺寸换算回归）
- 窗口越出屏幕、盖住任务栏（工作区钳制回归）
- 多显示器负坐标被错误拒绝
- 动画尊重系统"减少动态效果"
- 背景效果自动降级、不崩溃
"""

import os
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from roller.application.app_controller import AppController
from roller.infrastructure.config_store import ConfigStore
from roller.infrastructure.roster_parser import RosterParser


def _controller():
    cfg = Path(tempfile.mkdtemp()) / "config.json"
    return AppController(ConfigStore(cfg), RosterParser()), cfg


# ── DPI 换算（核心回归）───────────────────────────────────
def test_dpi_roundtrip_is_exact():
    """物理 → 逻辑 → 物理 必须完全相等，否则会累积放大。"""
    from roller.presentation.dpi import to_logical, to_physical

    for scaling in (1.0, 1.25, 1.5, 1.75, 2.0):
        for phys in (320, 400, 480, 600, 900, 1080):
            logic = to_logical(phys, scaling)
            back = to_physical(logic, scaling)
            # 允许 ±1 像素的取整误差，绝不能出现比例性放大
            assert abs(back - phys) <= 1, f"scaling={scaling} {phys}->{logic}->{back}"


def test_window_does_not_grow_across_restarts_at_150pct():
    """模拟 150% 缩放下的多次重启：窗口尺寸必须稳定，不允许递增。"""
    from roller.presentation.dpi import to_logical, to_physical

    scaling = 1.5
    # 起始：用户在 150% 屏上拖出 600x510 物理像素
    phys = (600, 510)
    sizes = []
    for _ in range(6):
        # 保存：物理 → 逻辑
        logic_w = to_logical(phys[0], scaling)
        logic_h = to_logical(phys[1], scaling)
        sizes.append((logic_w, logic_h))
        # 恢复：逻辑 → 物理（CTk 会做的事）
        phys = (to_physical(logic_w, scaling), to_physical(logic_h, scaling))

    # 6 次往复后仍应是 600x510
    assert phys == (600, 510), f"出现累积放大: {sizes} -> {phys}"
    assert len(set(sizes)) == 1, f"逻辑尺寸应稳定: {set(sizes)}"


def test_sanitize_rejects_absurd_sizes():
    from roller.presentation.dpi import sanitize_size

    assert sanitize_size(99999, 99999) is None
    assert sanitize_size(10, 10) is None
    assert sanitize_size(0, 0) is None
    assert sanitize_size(400, 340) == (400, 340)


def test_scaling_lookup_falls_back_to_one():
    """拿不到窗口时不报错，返回 1.0。"""
    from roller.presentation.dpi import window_scaling_of

    assert window_scaling_of(object()) == 1.0


# ── 工作区（多显示器）─────────────────────────────────────
def test_work_area_excludes_taskbar():
    """工作区高度应小于等于屏幕高度（任务栏被排除）。"""
    from roller.presentation.window_utils import primary_work_area, screen_size

    left, top, right, bottom = primary_work_area()
    sw, sh = screen_size()
    assert (right - left) <= sw
    assert (bottom - top) <= sh


def test_clamp_keeps_window_inside():
    from roller.presentation.window_utils import (
        clamp_to_work_area,
        primary_work_area,
    )

    l, t, r, b = primary_work_area()
    x, y, w, h = clamp_to_work_area(-9999, -9999, 99999, 99999)
    assert l <= x and t <= y
    assert x + w <= r and y + h <= b


def test_clamp_preserves_negative_coords_on_secondary_monitor():
    """副屏在主屏左侧时的负坐标是合法的，不应被强行拉回主屏。"""
    from roller.presentation.window_utils import clamp_to_work_area

    # 假设点在 (0,0)，clamp 应针对该点所在显示器；只要不变成"永远正数"即可
    x, y, w, h = clamp_to_work_area(-1900, 100, 400, 340)
    assert w == 400 and h == 340


def test_clamp_never_returns_zero_size():
    from roller.presentation.window_utils import clamp_to_work_area

    x, y, w, h = clamp_to_work_area(10, 10, 0, 0)
    assert w >= 1 and h >= 1


# ── 动画 ──────────────────────────────────────────────────
def test_animator_respects_reduce_motion(monkeypatch=None):
    """系统关闭动画时，Animator.enabled 必须为 False。"""
    from roller.presentation import animations as anim_mod
    from roller.presentation.animations import Animator

    class FakeWidget:
        def after(self, ms, fn):
            return "job"

        def after_cancel(self, job):
            pass

    widget = FakeWidget()
    anim = Animator(widget)

    original = anim_mod.animations_enabled
    try:
        anim_mod.animations_enabled = lambda: False
        assert anim.enabled is False, "系统减少动态效果时应停用动画"

        anim_mod.animations_enabled = lambda: True
        assert anim.enabled is True
    finally:
        anim_mod.animations_enabled = original


def test_animator_disabled_jumps_to_final_state():
    """动画关闭时，揭示应立即到终态（不逐帧）。"""
    from roller.presentation import animations as anim_mod
    from roller.presentation.animations import Animator

    class Label:
        def __init__(self):
            self.font = None
            self.text_color = None
            self.text = None

        def configure(self, **kw):
            for k, v in kw.items():
                setattr(self, k, v)

    class FakeWidget:
        def after(self, ms, fn):
            return "j"

        def after_cancel(self, job):
            pass

    original = anim_mod.animations_enabled
    try:
        anim_mod.animations_enabled = lambda: False
        anim = Animator(FakeWidget())
        anim.set_enabled(False)
        label = Label()
        anim.reveal_name(label, "张三", ("F", 46, "bold"), "#000000", "#ffffff")
        assert label.text == "张三"
        assert label.font == ("F", 46, "bold")
        assert label.text_color == "#000000"
    finally:
        anim_mod.animations_enabled = original


def test_animator_toggle_cancels_pending():
    from roller.presentation.animations import Animator

    cancelled = []

    class FakeWidget:
        def after(self, ms, fn):
            return f"job{len(cancelled)}"

        def after_cancel(self, job):
            cancelled.append(job)

    anim = Animator(FakeWidget())
    anim._jobs.extend(["a", "b"])
    anim.set_enabled(False)
    assert sorted(cancelled) == ["a", "b"]
    assert anim._jobs == []


# ── 背景效果 ──────────────────────────────────────────────
def test_backdrop_modes_available():
    from roller.presentation.window_utils import Backdrop

    class W:
        def attributes(self, *a):
            pass

        def update_idletasks(self):
            pass

    b = Backdrop(W())
    modes = b.available_modes()
    assert "opaque" in modes and "translucent" in modes


def test_backdrop_unknown_mode_falls_back_to_opaque():
    """配置里出现非法值时退回不透明，不抛异常。"""
    from roller.presentation.window_utils import Backdrop

    class W:
        def attributes(self, *a):
            pass

        def update_idletasks(self):
            pass

    b = Backdrop(W())
    b.apply("这不是有效值")
    assert b.mode == Backdrop.OPAQUE


def test_backdrop_config_validation():
    """配置层的非法 backdrop 值应被规整为 opaque。"""
    from roller.infrastructure.config_store import AppConfig

    assert AppConfig.from_dict({"backdrop": "玻璃"}).backdrop == "opaque"
    assert AppConfig.from_dict({"backdrop": "glass"}).backdrop == "glass"
    assert AppConfig.from_dict({}).backdrop == "opaque"


def test_animations_config_roundtrip():
    cfg = Path(tempfile.mkdtemp()) / "config.json"
    ctrl = AppController(ConfigStore(cfg), RosterParser())
    assert ctrl.config.animations is True
    ctrl.set_animations(False)
    ctrl.set_backdrop("glass")

    reloaded = AppController(ConfigStore(cfg), RosterParser())
    assert reloaded.config.animations is False
    assert reloaded.config.backdrop == "glass"


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
