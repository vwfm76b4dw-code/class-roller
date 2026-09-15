"""领域模型。

这里的类型是纯数据 + 纯规则，不 import UI、不读写文件，可被单元测试直接驱动。

关于重名：**名单允许同名学生**。一个班里出现两个"张伟"是正常的，
早期版本按姓名去重，会把其中一个静默吞掉——这正是"识别不全所有人"
的根因。现在改为按**多重集**处理：同名可以存在多份，每份视作一名学生。
重复导入同一份文件不会翻倍（取每个姓名的最大出现次数），
既避免误吞，也避免重复导入导致名单膨胀。
"""

from __future__ import annotations

from collections import Counter
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
    """学生名单（多重集：允许同名学生）。

    保证内部顺序稳定；同名可存在多份，各视作独立的学生。
    """

    def __init__(self, names: Optional[Iterable[str]] = None) -> None:
        self._students: List[Student] = []
        if names:
            self.extend(names)

    # ── 查询 ──────────────────────────────────────────────
    def __len__(self) -> int:
        return len(self._students)

    def __iter__(self) -> Iterator[Student]:
        return iter(self._students)

    def __contains__(self, name: object) -> bool:
        return isinstance(name, str) and name.strip() in self.counts()

    def __getitem__(self, index: int) -> Student:
        return self._students[index]

    def is_empty(self) -> bool:
        return not self._students

    @property
    def students(self) -> Sequence[Student]:
        """只读视图，防止外部直接改写内部列表。"""
        return tuple(self._students)

    def names(self) -> List[str]:
        """按名单顺序返回全部姓名（含重复）。"""
        return [s.name for s in self._students]

    def counts(self) -> Counter:
        """每个姓名在名单中出现的份数。"""
        return Counter(s.name for s in self._students)

    def count_of(self, name: str) -> int:
        cleaned = (name or "").strip()
        return sum(1 for s in self._students if s.name == cleaned)

    # ── 变更 ──────────────────────────────────────────────
    def add(self, name: str) -> bool:
        """新增一名学生。返回 False 仅表示姓名无效。

        同名学生会被正常加入——不再因为重名而吞掉。
        """
        cleaned = (name or "").strip()
        if not cleaned:
            return False
        self._students.append(Student(cleaned))
        return True

    def extend(self, names: Iterable[str]) -> int:
        """批量新增，返回实际新增数量。

        采用**多重集并集**：某个姓名在入参里出现了 N 次、名单里已有 M 份，
        则最多补到 N 份。这样"同一份文件重复导入"不会让名单翻倍，
        而"班里本来就有两个张伟"仍能各自保留一份。
        """
        incoming = Counter(
            (n or "").strip() for n in names if (n or "").strip()
        )
        current = self.counts()
        added = 0
        for name, wanted in incoming.items():
            need = wanted - current.get(name, 0)
            for _ in range(max(0, need)):
                self._students.append(Student(name))
                added += 1
        return added

    def remove(self, name: str) -> bool:
        """移除一份该姓名的学生（同名有多份时只移除一份）。"""
        cleaned = (name or "").strip()
        for index, student in enumerate(self._students):
            if student.name == cleaned:
                del self._students[index]
                return True
        return False

    def clear(self) -> None:
        self._students.clear()

    def replace_all(self, names: Iterable[str]) -> int:
        """用给定名单整体替换。"""
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
