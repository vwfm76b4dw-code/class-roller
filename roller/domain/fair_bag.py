"""公平抽取袋（shuffle bag）。

## 为什么要显式维护状态

早期版本是"从历史记录反推本轮还剩谁"，这个推断在**轮次边界有歧义**：

    39 人名单，历史 39 条 → 正好一轮结束 → 开新一轮       正确
    39 人名单，历史 40 条 → 回溯也能覆盖全部 39 人
                          → 被误判成"又完成一轮" → 开新一轮  错误！

两种情况下"回溯覆盖满名单"都成立，算法无法区分，于是第二轮刚开始就被
重置成新轮，**刚抽过的人立刻可能重复**。用户实测数据里出现过
"10 次抽取内同一人出现两次"，且间隔最小只有 5 次。

改为显式维护袋子：本轮还剩谁、上一轮最后抽到谁，都作为状态保存。
状态由调用方持久化，不再依赖对历史的推断。

## 两条保证

1. **一轮之内不重复**：本轮未抽名单用尽前，不会重复抽到同一人。
2. **跨轮不紧邻重复**：开启新一轮时，第一个人不会等于上一轮的最后一人
   （否则会出现"连着两次抽到同一个人"的观感）。

同名按多重集处理：名单里两个"张伟"，一轮内需各自被抽到一次。
"""

from __future__ import annotations

from collections import Counter
from typing import Any, Dict, List, Optional, Protocol, Sequence


class _RandomLike(Protocol):
    def choice(self, seq: Sequence[str]) -> str: ...


class FairBag:
    """公平抽取袋。"""

    def __init__(
        self,
        remaining: Optional[Sequence[str]] = None,
        last_winner: Optional[str] = None,
        drawn_this_round: Optional[Sequence[str]] = None,
    ) -> None:
        self._remaining: List[str] = list(remaining or [])
        self._last_winner: Optional[str] = last_winner
        # 本轮已抽过的人（用于区分"新增学生"与"本轮抽过的人"）
        self._drawn_this_round: List[str] = list(drawn_this_round or [])

    # ── 只读 ──────────────────────────────────────────────
    @property
    def remaining(self) -> List[str]:
        return list(self._remaining)

    @property
    def last_winner(self) -> Optional[str]:
        return self._last_winner

    def remaining_count(self) -> int:
        return len(self._remaining)

    # ── 抽取 ──────────────────────────────────────────────
    def sync(self, roster_names: Sequence[str]) -> None:
        """公开入口：名单变动后让袋子保持一致。"""
        self._sync_with_roster(roster_names)

    def draw(self, rng: _RandomLike, roster_names: Sequence[str]) -> Optional[str]:
        """按公平规则抽一人。

        roster_names 为当前名单（含重复）。名单变化时自动适应：
        已不在名单里的人从剩余袋中剔除，新加入的人补进袋里。
        """
        if not roster_names:
            return None

        self._sync_with_roster(roster_names)

        if not self._remaining:
            self._start_new_round(roster_names)

        pick = self._pick(rng)
        self._last_winner = pick
        return pick

    def _pick(self, rng: _RandomLike) -> str:
        # 跨轮不紧邻重复：若本轮只剩一人且正是上轮最后一位，
        # 说明名单只有一人或退化场景，此时不必避让
        if (
            self._last_winner is not None
            and len(self._remaining) > 1
        ):
            pool = [n for n in self._remaining if n != self._last_winner]
            if not pool:
                pool = list(self._remaining)
        else:
            pool = list(self._remaining)

        pick = rng.choice(pool)
        # 从剩余袋中移除一份（同名多重集，只移除一个），并登记本轮已抽
        for i, name in enumerate(self._remaining):
            if name == pick:
                del self._remaining[i]
                break
        self._drawn_this_round.append(pick)
        return pick

    def _start_new_round(self, roster_names: Sequence[str]) -> None:
        self._remaining = list(roster_names)
        self._drawn_this_round = []

    def _sync_with_roster(self, roster_names: Sequence[str]) -> None:
        """名单发生变化时，让袋子跟上。

        只做两件事，且**只在必要时**：
        - 剔除已从名单移除的人（否则会抽出不在名单里的名字）
        - 补进名单里新增的人（本轮尚未抽过，应当可抽）

        ⚠️ 不能按"名单需要的份数"补齐——那会把本轮已经抽掉的人重新塞回
        袋里，等于每抽一次就重置，同轮内会不断重复（实测踩过这个坑）。
        """
        roster = Counter(roster_names)

        # 首次使用（袋子为空且从未抽过）→ 直接用当前名单填充
        if not self._remaining and self._last_winner is None:
            self._remaining = list(roster_names)
            return

        # 同时记录"本轮已抽过的人"，用于判断新增：本轮抽过的人不算新增
        already = Counter(self._drawn_this_round)

        # 1) 剔除已不在名单里的
        fixed = [n for n in self._remaining if roster.get(n, 0) > 0]
        # 若某姓名在名单里的份数少于袋中份数，按名单份数截断
        kept = Counter()
        result: List[str] = []
        for name in fixed:
            if kept[name] < roster.get(name, 0):
                result.append(name)
                kept[name] += 1
        self._remaining = result

        # 2) 补进新增的人：名单里有、但既不在袋里、也不是本轮已抽过的
        in_bag = Counter(self._remaining)
        for name, need in roster.items():
            known = in_bag.get(name, 0) + already.get(name, 0)
            for _ in range(max(0, need - known)):
                self._remaining.append(name)

    # ── 状态序列化 ────────────────────────────────────────
    def to_dict(self) -> Dict[str, Any]:
        return {
            "remaining": list(self._remaining),
            "last": self._last_winner,
            "drawn": list(self._drawn_this_round),
        }

    @classmethod
    def from_dict(cls, raw: Optional[Dict[str, Any]]) -> "FairBag":
        if not isinstance(raw, dict):
            return cls()
        remaining = raw.get("remaining")
        if not isinstance(remaining, list):
            remaining = []
        last = raw.get("last")
        drawn = raw.get("drawn")
        return cls(
            remaining=[str(x) for x in remaining],
            last_winner=str(last) if last else None,
            drawn_this_round=[str(x) for x in drawn] if isinstance(drawn, list) else None,
        )


def rebuild_from_history(
    roster_names: Sequence[str], history_names: Sequence[str]
) -> FairBag:
    """从历史记录重建袋子（用于旧配置升级）。

    用"已抽条数对名单人数取模"确定本轮已抽多少条 —— 这是无歧义的：
        39 人、40 条历史 → 40 % 39 = 1 → 本轮已抽最后 1 条
    而早期版本"回溯到覆盖满名单"的判定会把这种情况误判成"刚完成一轮"。

    最后一条记录作为 last_winner，用于避免跨轮紧邻重复。
    """
    n = len(roster_names)
    if n == 0 or not history_names:
        return FairBag()

    taken = len(history_names) % n
    if taken == 0 and history_names:
        # 恰好完成整数轮 → 新一轮尚未开始，袋为空
        taken = 0
    current_round = list(history_names[-taken:]) if taken else []

    # 本轮已抽的人从袋里扣除（多重集）
    bag = Counter(roster_names)
    for name in current_round:
        if bag.get(name, 0) > 0:
            bag[name] -= 1

    remaining: List[str] = []
    for name in roster_names:
        if bag.get(name, 0) > 0:
            remaining.append(name)
            bag[name] -= 1

    return FairBag(
        remaining=remaining,
        last_winner=history_names[-1],
        drawn_this_round=current_round,
    )
