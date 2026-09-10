"""领域模型。

这里的类型是纯数据 + 纯规则，不 import tkinter、不读写文件，
因此可以被单元测试直接驱动。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Iterable, Iterator, List, Optional, Sequence


@dataclass(frozen=True)
class Student:
    """一名学生。姓名是唯一有意义的属性。"""

    name: str

    def __post_init__(self) -> None:
        cleaned = self.name.strip()
        if not cleaned:
            raise ValueError("学生姓名不能为空")
        # frozen dataclass 需要用 object.__setattr__ 修正
        object.__setattr__(self, "name", cleaned)

    def __str__(self) -> str:  # 便于直接塞进 UI 显示
        return self.name


class Roster:
    """学生名单。

    保证内部顺序稳定、姓名不重复（同名会被忽略）。
    """

    def __init__(self, names: Optional[Iterable[str]] = None) -> None:
        self._students: List[Student] = []
        self._seen: set[str] = set()
        if names:
            self.extend(names)

    # ── 查询 ──────────────────────────────────────────────
    def __len__(self) -> int:
        return len(self._students)

    def __iter__(self) -> Iterator[Student]:
        return iter(self._students)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name.strip() in self._seen

    def __getitem__(self, index: int) -> Student:
        return self._students[index]

    def is_empty(self) -> bool:
        return not self._students

    @property
    def students(self) -> Sequence[Student]:
        """只读视图，防止外部直接改写内部列表。"""
        return tuple(self._students)

    def names(self) -> List[str]:
        return [s.name for s in self._students]

    # ── 变更 ──────────────────────────────────────────────
    def add(self, name: str) -> bool:
        """新增一名学生。返回 False 表示空名或重名。"""
        cleaned = (name or "").strip()
        if not cleaned or cleaned in self._seen:
            return False
        self._students.append(Student(cleaned))
        self._seen.add(cleaned)
        return True

    def extend(self, names: Iterable[str]) -> int:
        """批量新增，返回实际新增数量。"""
        added = 0
        for name in names:
            if self.add(name):
                added += 1
        return added

    def remove(self, name: str) -> bool:
        cleaned = (name or "").strip()
        if cleaned not in self._seen:
            return False
        self._students = [s for s in self._students if s.name != cleaned]
        self._seen.discard(cleaned)
        return True

    def clear(self) -> None:
        self._students.clear()
        self._seen.clear()

    def replace_all(self, names: Iterable[str]) -> int:
        self.clear()
        return self.extend(names)


@dataclass
class DrawRecord:
    """一次抽奖结果。"""

    name: str
    timestamp: datetime = field(default_factory=datetime.now)

    def to_dict(self) -> dict:
        return {"name": self.name, "timestamp": self.timestamp.isoformat()}

    @classmethod
    def from_dict(cls, raw: dict) -> "DrawRecord":
        try:
            ts = datetime.fromisoformat(raw.get("timestamp", ""))
        except (TypeError, ValueError):
            ts = datetime.now()
        return cls(name=str(raw.get("name", "")), timestamp=ts)

    def display_time(self) -> str:
        return self.timestamp.strftime("%m-%d %H:%M")
