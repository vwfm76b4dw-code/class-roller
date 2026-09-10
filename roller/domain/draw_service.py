"""抽奖服务：随机选取逻辑。

随机源通过构造注入，测试时可替换成确定性实现。
"""

from __future__ import annotations

import random
from typing import Optional, Protocol, Sequence, TypeVar

from roller.domain.models import Roster, Student

T = TypeVar("T")


class RandomSource(Protocol):
    """随机源抽象，方便替换与测试。"""

    def choice(self, seq: Sequence[T]) -> T: ...

    def random(self) -> float: ...


class SystemRandom:
    """默认随机源，包装标准库 random.Random。"""

    def __init__(self, seed: Optional[int] = None) -> None:
        self._rng = random.Random(seed)

    def choice(self, seq: Sequence[T]) -> T:
        return self._rng.choice(seq)

    def random(self) -> float:
        return self._rng.random()


class DrawService:
    """抽奖领域服务。"""

    def __init__(self, random_source: Optional[RandomSource] = None) -> None:
        self._rng: RandomSource = random_source or SystemRandom()

    def draw(self, roster: Roster) -> Optional[Student]:
        """从名单中抽取一人；名单为空返回 None。"""
        if roster.is_empty():
            return None
        return self._rng.choice(roster.students)

    def draw_from(self, candidates: Sequence[Student]) -> Optional[Student]:
        """从给定的候选中抽取一人；空候选返回 None。"""
        if not candidates:
            return None
        return self._rng.choice(list(candidates))
