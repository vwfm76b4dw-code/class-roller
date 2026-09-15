"""公平抽取回归测试。

**用户实测发现的 bug**（2026-09-15）：
39 人班级，公平模式开启，第 2 轮出现 10 处重复——方闻在第 37、43、48 次
被抽到，最短间隔仅 5 次。

根因：早期实现从历史记录反推"本轮还剩谁"，在轮次边界有歧义：

    39 人，历史 39 条 → 回溯覆盖满名单 → 判定"完成一轮" → 开新一轮  正确
    39 人，历史 40 条 → 回溯同样覆盖满名单 → 也被判定"完成一轮" → 开新一轮
                        ✗ 错误！此时新一轮已经抽了 1 个人

两种情况无法区分，于是第二轮刚开始就被重置，刚抽过的人立刻可能重复。
实测数据里候选池为空的位置正好是第 40~48 次，与此完全吻合。

修法：显式维护抽取袋状态（本轮还剩谁、上一位是谁），不再从历史推断。
"""

import sys
import tempfile
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from roller.application.app_controller import AppController
from roller.domain.draw_service import SystemRandom
from roller.domain.fair_bag import FairBag, rebuild_from_history
from roller.infrastructure.config_store import ConfigStore
from roller.infrastructure.roster_parser import RosterParser

# 用户真实名单（39 人）
REAL_ROSTER = [
    "陈星圻", "崔思涵", "崔伊婷", "丁蓓琪", "董培迪", "杜雨辰", "方闻",
    "付子涵", "龚鋫", "龚天昀", "郭子悦", "纪明泽", "嵇向嵘", "李馨宁",
    "李鑫瑞", "刘嘉轩", "刘翊", "刘元", "路嘉峰", "罗奕莀", "马悦菡",
    "马雨彤", "孟晨希", "潘熙昀", "申雨菲", "孙雨彤", "汪禹诺", "王家凯",
    "王梓默", "魏钰芳", "吴舜天", "杨其羽", "殷钰荞", "于沐之", "张驰",
    "张淇骏", "张睿莹", "张斯佳", "赵婳铱",
]


def _controller(names=None, fair=True):
    ctrl = AppController(
        ConfigStore(Path(tempfile.mkdtemp()) / "config.json"), RosterParser()
    )
    ctrl.set_fair_mode(fair)
    for n in (names or []):
        ctrl.add_student(n)
    return ctrl


# ── 核心：一轮之内不得重复 ────────────────────────────────
def test_no_repeat_within_round_5_people():
    ctrl = _controller(["A", "B", "C", "D", "E"])
    first = [ctrl.draw_now() for _ in range(5)]
    assert sorted(first) == ["A", "B", "C", "D", "E"], first


def test_no_repeat_within_round_39_people():
    """用户场景：39 人班级的第一轮必须恰好覆盖全班。"""
    ctrl = _controller(REAL_ROSTER)
    first = [ctrl.draw_now() for _ in range(39)]
    assert sorted(first) == sorted(REAL_ROSTER), (
        f"第一轮未覆盖全班，重复: "
        f"{[n for n, c in Counter(first).items() if c > 1]}"
    )


def test_second_round_also_no_repeat():
    """bug 出在第二轮——这里必须也是完整覆盖。"""
    ctrl = _controller(REAL_ROSTER)
    all_draws = [ctrl.draw_now() for _ in range(78)]
    second = all_draws[39:78]
    dup = [n for n, c in Counter(second).items() if c > 1]
    assert not dup, f"第二轮出现重复: {dup}（旧实现就是这里错的）"
    assert sorted(second) == sorted(REAL_ROSTER)


def test_many_rounds_no_dup_within_any_round():
    ctrl = _controller(REAL_ROSTER)
    draws = [ctrl.draw_now() for _ in range(39 * 5)]
    for r in range(5):
        seg = draws[r * 39:(r + 1) * 39]
        dup = [n for n, c in Counter(seg).items() if c > 1]
        assert not dup, f"第 {r + 1} 轮重复: {dup}"


def test_no_adjacent_repeat_across_round_boundary():
    """跨轮不得紧邻重复（一轮末位 ≠ 下一轮首位）。"""
    ctrl = _controller(REAL_ROSTER)
    draws = [ctrl.draw_now() for _ in range(39 * 6)]
    bad = [
        (i + 1, draws[i])
        for i in range(len(draws) - 1)
        if draws[i] == draws[i + 1]
    ]
    assert not bad, f"出现紧邻重复: {bad}"


def test_user_real_case_fangwen_not_repeated_early():
    """回归用户的具体反馈：方闻不应在 39 次内被抽到两次。"""
    ctrl = _controller(REAL_ROSTER)
    draws = [ctrl.draw_now() for _ in range(39)]
    positions = [i for i, n in enumerate(draws, 1) if n == "方闻"]
    assert len(positions) == 1, f"方闻在第一轮出现 {len(positions)} 次: {positions}"


# ── 袋子自身行为 ──────────────────────────────────────────
def test_bag_remaining_decreases_monotonically():
    bag = FairBag()
    rng = SystemRandom(seed=1)
    names = ["A", "B", "C"]
    counts = []
    for _ in range(3):
        bag.draw(rng, names)
        counts.append(bag.remaining_count())
    assert counts == [2, 1, 0], counts


def test_bag_restarts_after_exhausted():
    bag = FairBag()
    rng = SystemRandom(seed=2)
    names = ["A", "B"]
    seen = [bag.draw(rng, names) for _ in range(2)]
    assert sorted(seen) == ["A", "B"]
    third = bag.draw(rng, names)
    assert third in names, third


def test_bag_handles_duplicate_names():
    """同名按多重集：两个张伟在一轮内应各被抽到一次。"""
    bag = FairBag()
    rng = SystemRandom(seed=3)
    names = ["张伟", "张伟", "李四"]
    seen = [bag.draw(rng, names) for _ in range(3)]
    assert seen.count("张伟") == 2, seen
    assert seen.count("李四") == 1, seen


def test_bag_adapts_to_new_student():
    """中途加入新学生 → 本轮即可被抽到（不破坏已抽记录）。"""
    bag = FairBag()
    rng = SystemRandom(seed=4)
    bag.draw(rng, ["A", "B", "C"])
    bag.sync(["A", "B", "C", "D"])          # 新增 D
    assert "D" in bag.remaining


def test_bag_drops_removed_student():
    """学生被移除 → 不应再从袋里抽出。"""
    bag = FairBag()
    rng = SystemRandom(seed=5)
    bag.sync(["A", "B", "C"])
    bag.sync(["A", "B"])                     # 移除 C
    for _ in range(3):
        assert bag.draw(rng, ["A", "B"]) in ("A", "B")


def test_empty_roster_returns_none():
    bag = FairBag()
    assert bag.draw(SystemRandom(), []) is None


def test_single_student_can_repeat():
    """只有一名学生时必须能重复（否则永远抽不出）。"""
    bag = FairBag()
    rng = SystemRandom(seed=6)
    results = [bag.draw(rng, ["独苗"]) for _ in range(3)]
    assert results == ["独苗", "独苗", "独苗"]


# ── 状态持久化 ────────────────────────────────────────────
def test_bag_state_survives_restart():
    """袋子状态必须落盘——重启后仍在本轮内，不得重复。"""
    cfg = Path(tempfile.mkdtemp()) / "config.json"
    ctrl1 = AppController(ConfigStore(cfg), RosterParser())
    ctrl1.set_fair_mode(True)
    for n in ["A", "B", "C", "D", "E"]:
        ctrl1.add_student(n)
    first = [ctrl1.draw_now() for _ in range(3)]     # 抽 3 个

    ctrl2 = AppController(ConfigStore(cfg), RosterParser())
    assert ctrl2.config.fair_mode is True
    rest = [ctrl2.draw_now() for _ in range(4)]
    # 前 3 + 后 2 = 一轮的 5 人，应无重复
    combo = first + rest[:2]
    dup = [n for n, c in Counter(combo).items() if c > 1]
    assert not dup, f"重启后本轮内重复: {dup}（combo={combo}）"


def test_old_config_without_bag_rebuilds_from_history():
    """旧配置没有袋子状态 → 从历史重建，不能把已完成轮误判成新一轮。"""
    import json

    cfg = Path(tempfile.mkdtemp()) / "config.json"
    names = ["A", "B", "C", "D"]
    # 4 人，历史 4 条 = 恰好一轮完成
    cfg.write_text(json.dumps({
        "names": names,
        "history": [{"name": n, "timestamp": "2026-09-15T10:00:00"} for n in names],
        "fair_mode": True,
    }, ensure_ascii=False), encoding="utf-8")

    ctrl = AppController(ConfigStore(cfg), RosterParser())
    assert ctrl.config.fair_mode is True
    # 新一轮开始：接下来 4 次应覆盖全班，无内部重复
    nxt = [ctrl.draw_now() for _ in range(4)]
    assert sorted(nxt) == sorted(names), f"新一轮应覆盖全班，实际 {nxt}"


def test_old_config_mid_round_rebuilds_correctly():
    """4 人、历史 5 条（第二轮已抽 1 人）→ 重建后本轮还剩 3 人。"""
    bag = rebuild_from_history(["A", "B", "C", "D"], ["A", "B", "C", "D", "A"])
    assert bag.remaining_count() == 3, bag.remaining
    assert "A" not in bag.remaining, "A 本轮已抽过，不应在袋里"


def test_clear_history_resets_bag():
    ctrl = _controller(["A", "B", "C"])
    ctrl.draw_now()
    ctrl.clear_history()
    nxt = [ctrl.draw_now() for _ in range(3)]
    assert sorted(nxt) == ["A", "B", "C"]


def test_fair_mode_off_uses_uniform():
    """关闭公平模式 → 纯均匀，允许重复。"""
    ctrl = _controller(["A", "B", "C"], fair=False)
    draws = [ctrl.draw_now() for _ in range(40)]
    assert len(set(draws)) < 40, "纯均匀模式应出现重复"


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
