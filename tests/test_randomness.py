"""随机性与公平抽取测试。

覆盖：
- SystemRandom 默认走 OS CSPRNG（不可预测）
- undrawn_from_history 的轮次重建（含名单增删、历史不足、历史超一轮）
- draw_fair 的一轮内不重复保证
- 控制器集成：公平模式跨重启（从落盘历史恢复）仍保持
"""

import random
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from roller.application.app_controller import AppController
from roller.domain.draw_service import (
    DrawService,
    SystemRandom,
    undrawn_from_history,
)
from roller.infrastructure.config_store import ConfigStore
from roller.domain.models import Roster


# ── 随机源 ────────────────────────────────────────────────
def test_system_random_uses_os_csprng_by_default():
    """默认随机源必须是 OS CSPRNG，不可预测也不可重现。"""
    rng = SystemRandom()
    assert isinstance(rng._rng, random.SystemRandom), type(rng._rng)


def test_system_random_seed_falls_back_to_reproducible():
    """传 seed 时用可复现的 Mersenne Twister（供测试）。"""
    a = SystemRandom(seed=42)
    b = SystemRandom(seed=42)
    seq_a = [a.choice("abcdef") for _ in range(20)]
    seq_b = [b.choice("abcdef") for _ in range(20)]
    assert seq_a == seq_b


def test_csprng_draws_are_reasonably_spread():
    """CSPRNG 抽 5000 次应覆盖所有人且大致均匀（卡方粗检）。"""
    roster = Roster([str(i) for i in range(6)])
    svc = DrawService()
    counts = {name: 0 for name in roster.names()}
    for _ in range(6000):
        counts[svc.draw(roster).name] += 1
    # 每人期望 1000，允许 ±25%（宽松界，只抓"有人永远抽不到"这类错误）
    for name, c in counts.items():
        assert 700 <= c <= 1300, f"{name}: {c}"
        assert c > 0


# ── 轮次重建 ──────────────────────────────────────────────
def test_undrawn_full_when_no_history():
    assert undrawn_from_history(["A", "B", "C"], []) == ["A", "B", "C"]


def test_undrawn_excludes_recent_winners():
    # 本轮已抽 A、B（最近的在历史尾部）
    assert undrawn_from_history(["A", "B", "C"], ["A", "B"]) == ["C"]


def test_undrawn_starts_new_round_when_all_drawn():
    assert undrawn_from_history(["A", "B"], ["A", "B"]) == []


def test_undrawn_handles_multiple_rounds():
    # 两轮完整历史（每轮恰好覆盖 A,B,C）→ 本轮刚结束，未抽为空
    # （draw_fair 遇空袋会自动开启新一轮）
    history = ["A", "B", "C", "C", "B", "A"]
    assert undrawn_from_history(["A", "B", "C"], history) == []


def test_undrawn_ignores_names_not_in_roster():
    # 历史里有已移除的学生，不应干扰轮次计算
    assert undrawn_from_history(["A", "B", "C"], ["A", "X", "B"]) == ["C"]


def test_undrawn_includes_newcomers():
    # 名单新增 D（本轮没抽过）→ D 属于未抽
    assert undrawn_from_history(["A", "B", "C", "D"], ["A", "B", "C"]) == ["D"]


def test_undrawn_partial_history():
    # 历史不足以覆盖一轮：抽过 A，未抽 B、C
    assert undrawn_from_history(["A", "B", "C"], ["A"]) == ["B", "C"]


# ── 公平抽取 ──────────────────────────────────────────────
def test_draw_fair_no_repeat_within_round():
    """一轮之内（N 次抽取）绝不重复。"""
    names = [f"S{i}" for i in range(8)]
    roster = Roster(names)
    svc = DrawService(SystemRandom(seed=7))
    history = []
    drawn = []
    for _ in range(len(names)):
        winner = svc.draw_fair(roster, history).name
        assert winner not in drawn, f"{winner} 在一轮内被抽了两次"
        drawn.append(winner)
        history.append(winner)
    assert sorted(drawn) == sorted(names), "一轮应恰好覆盖所有人"


def test_draw_fair_new_round_after_exhausted():
    """一轮抽完后重新开始，第二轮可以抽到任何人。"""
    roster = Roster(["A", "B"])
    svc = DrawService(SystemRandom(seed=1))
    history = ["A", "B"]          # 第一轮结束
    w = svc.draw_fair(roster, history)
    assert w.name in {"A", "B"}


def test_draw_fair_empty_roster():
    assert DrawService().draw_fair(Roster(), []) is None


def test_draw_fair_uses_injected_rng():
    """注入固定源时行为可预测（测试确定性）。"""
    class First:
        def choice(self, seq):
            return seq[0]
        def random(self):
            return 0.0

    roster = Roster(["张三", "李四"])
    svc = DrawService(First())
    assert svc.draw_fair(roster, []).name == "张三"


# ── 控制器集成 ────────────────────────────────────────────
def _controller():
    cfg = Path(tempfile.mkdtemp()) / "config.json"
    return AppController(ConfigStore(cfg))


def test_controller_fair_mode_default_off():
    """默认是纯均匀随机（每次独立、概率严格相等），公平模式为可选。"""
    ctrl = _controller()
    assert ctrl.config.fair_mode is False


def test_default_mode_no_position_bias():
    """核心要求：每个人被抽中的概率与它在名单中的位置无关。

    用 4 人名单各抽 4000 次（纯均匀模式），每人期望 1000 次；
    允许 ±12% 偏差（宽松界，只抓"某个位置明显偏低"这类真实偏差）。
    """
    ctrl = _controller()
    ctrl.replace_roster(str(ROOT / "tests" / "fixtures" / "D4.txt"))         if (ROOT / "tests" / "fixtures" / "D4.txt").exists() else None
    for name in ["甲", "乙", "丙", "丁"]:
        ctrl.add_student(name)
    counts = {n: 0 for n in ctrl.roster.names()}
    N = 4000
    for _ in range(N):
        counts[ctrl.draw_now()] += 1
    expect = N / len(counts)
    for name, c in counts.items():
        assert 0.88 * expect <= c <= 1.12 * expect, f"{name}: {c}（期望 {expect:.0f}）"


def test_fair_mode_no_position_bias_over_rounds():
    """公平模式下同样无位置偏差：整轮是均匀随机排列，每人每轮必被抽到一次。

    验证方式：统计每人在"一轮中的第几个被抽到"的分布，
    若实现有位置偏好，某些人会被系统性地排在前面。
    """
    from roller.domain.draw_service import DrawService, SystemRandom
    from roller.domain.models import Roster

    names = ["甲", "乙", "丙", "丁"]
    roster = Roster(names)
    svc = DrawService(SystemRandom(seed=20260915))
    first_position_counts = {n: 0 for n in names}
    ROUNDS = 1200
    for _ in range(ROUNDS):
        history = []
        for _ in range(len(names)):
            w = svc.draw_fair(roster, history).name
            history.append(w)
        first_position_counts[history[0]] += 1
    expect = ROUNDS / len(names)
    for name, c in first_position_counts.items():
        assert 0.8 * expect <= c <= 1.2 * expect, (
            f"{name} 被首位抽中的次数 {c}（期望 {expect:.0f}）——存在位置偏差"
        )


def test_controller_fair_draw_no_repeat_until_round_done():
    ctrl = _controller()
    ctrl.set_fair_mode(True)          # 公平模式需显式开启
    ctrl.replace_roster(str(ROOT / "tests" / "fixtures" / "A_plain.txt"))  # 3 人
    drawn = [ctrl.draw_now() for _ in range(3)]
    assert len(set(drawn)) == 3, f"一轮内重复: {drawn}"


def test_controller_fairness_survives_restart():
    """公平状态来自历史，重启（重建控制器）后一轮内依然不重复。"""
    cfg = Path(tempfile.mkdtemp()) / "config.json"

    ctrl1 = AppController(ConfigStore(cfg))
    ctrl1.set_fair_mode(True)
    ctrl1.replace_roster(str(ROOT / "tests" / "fixtures" / "A_plain.txt"))
    first = ctrl1.draw_now()

    # 模拟重启
    ctrl2 = AppController(ConfigStore(cfg))
    assert ctrl2.config.fair_mode is True
    rest = []
    for _ in range(2):
        rest.append(ctrl2.draw_now())
    assert first not in rest, f"重启后本轮重复: {first} vs {rest}"
    assert len(set([first] + rest)) == 3


def test_controller_manual_mode_allows_repeat():
    """纯均匀模式下允许重复（默认即此模式）。"""
    ctrl = _controller()
    ctrl.replace_roster(str(ROOT / "tests" / "fixtures" / "A_plain.txt"))
    assert ctrl.config.fair_mode is False
    seen = [ctrl.draw_now() for _ in range(30)]
    assert len(set(seen)) < 30, "纯均匀模式应允许重复抽取"


def test_fair_mode_persisted():
    cfg = Path(tempfile.mkdtemp()) / "config.json"
    ctrl1 = AppController(ConfigStore(cfg))
    ctrl1.set_fair_mode(True)

    ctrl2 = AppController(ConfigStore(cfg))
    assert ctrl2.config.fair_mode is True


def test_old_config_without_fair_field_uses_default():
    """旧配置没有 fair_mode 字段 → 用当前默认（纯均匀）。"""
    import json
    cfg = Path(tempfile.mkdtemp()) / "config.json"
    cfg.write_text(json.dumps({"names": ["张三"], "version": 3}), encoding="utf-8")
    ctrl = AppController(ConfigStore(cfg))
    assert ctrl.config.fair_mode is False


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
