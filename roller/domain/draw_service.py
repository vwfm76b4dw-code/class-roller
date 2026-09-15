"""抽奖服务：随机选取逻辑。

随机源通过构造注入。默认使用 random.SystemRandom（操作系统密码学级
熵源），序列不可预测——课堂里学生猜不出下一个是谁，才是"真随机"
应有的样子。测试可注入固定种子获得可复现序列。

公平抽取（shuffle bag 思想）也在这一层：把名单视为一轮，本轮内
人人未抽之前不重复，抽空自动开新一轮。数学上每一步都是等概率抽取，
且保证不会冷落任何学生——这既不可预测，又符合课堂对"随机"的期望。
"""

from __future__ import annotations

import random
from collections import Counter
from typing import List, Optional, Protocol, Sequence, TypeVar

from roller.domain.models import Roster, Student

T = TypeVar("T")


class RandomSource(Protocol):
    """随机源抽象，方便替换与测试。"""

    def choice(self, seq: Sequence[T]) -> T: ...

    def random(self) -> float: ...


class SystemRandom:
    """默认随机源。

    不传 seed 时用 random.SystemRandom（操作系统 CSPRNG，不可预测、
    不可重现）；传 seed 则退化为可复现的 Mersenne Twister，供测试用。
    """

    def __init__(self, seed: Optional[int] = None) -> None:
        self._rng = random.SystemRandom() if seed is None else random.Random(seed)

    def choice(self, seq: Sequence[T]) -> T:
        return self._rng.choice(seq)

    def random(self) -> float:
        return self._rng.random()


def undrawn_from_history(
    roster_names: Sequence[str], history_names: Sequence[str]
) -> List[str]:
    """根据历史记录推算"本轮还没被抽到的人"。

    按**多重集**处理：名单里有两个"张伟"，就需要本轮抽到两次才算覆盖。
    从最近一抽往前回溯，累计覆盖全部名单份数的那一刻即上一轮的边界；
    边界之后（更近的）抽中者构成当前轮，名单中尚未被覆盖的即未抽者。

    名单有增删时自动适应：离开的人被忽略，新加入的人本轮未被抽过、
    会进入未抽集合。历史覆盖不了名单（如刚清空历史）时，未抽=全名单。
    """
    if not roster_names:
        return []
    remaining = Counter(roster_names)
    for name in reversed(history_names):
        if not any(remaining.values()):
            break
        if remaining.get(name, 0) > 0:
            remaining[name] -= 1
    # 保持名单原有顺序，便于"随机滚动"时观感稳定
    bag: List[str] = []
    used = Counter()
    for name in roster_names:
        if used[name] < remaining.get(name, 0):
            bag.append(name)
            used[name] += 1
    return bag


class DrawService:
    """抽奖领域服务。"""

    def __init__(self, random_source: Optional[RandomSource] = None) -> None:
        self._rng: RandomSource = random_source or SystemRandom()

    def draw(self, roster: Roster) -> Optional[Student]:
        """从名单中均匀抽取一人；名单为空返回 None。"""
        if roster.is_empty():
            return None
        return self._rng.choice(roster.students)

    def draw_fair(
        self, roster: Roster, history_names: Sequence[str]
    ) -> Optional[Student]:
        """公平抽取：本轮未抽过的人里等概率选一个。

        本轮所有人都被抽过时自动开启新一轮（整份名单重新可抽）。
        """
        if roster.is_empty():
            return None
        names = roster.names()
        bag = undrawn_from_history(names, history_names)
        if not bag:
            bag = names
        picked = self._rng.choice(bag)
        for student in roster.students:
            if student.name == picked:
                return student
        return None  # 理论不可达：bag 取自名单

    def draw_from(self, candidates: Sequence[Student]) -> Optional[Student]:
        """从给定的候选中抽取一人；空候选返回 None。"""
        if not candidates:
            return None
        return self._rng.choice(list(candidates))
