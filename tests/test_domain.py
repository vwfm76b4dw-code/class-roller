"""领域层测试：模型与抽奖服务。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from roller.domain.draw_service import DrawService
from roller.domain.models import Roster, Student


class FixedRandom:
    """确定性随机源：永远返回第一个元素。"""

    def choice(self, seq):
        return seq[0]

    def random(self):
        return 0.0


def test_student_strips_whitespace():
    assert Student("  张三  ").name == "张三"


def test_student_rejects_empty():
    for bad in ("", "   ", "\t"):
        try:
            Student(bad)
        except ValueError:
            continue
        raise AssertionError(f"应拒绝空姓名: {bad!r}")


def test_roster_adds_and_keeps_duplicates():
    """同名必须保留——班里可能真有两个张伟，早期版本会把其中一个吞掉。"""
    roster = Roster()
    assert roster.add("张三") is True
    assert roster.add("张三") is True    # 同名允许
    assert roster.add("   ") is False    # 空名拒绝
    assert len(roster) == 2
    assert roster.count_of("张三") == 2


def test_roster_remove_and_clear():
    roster = Roster(["张三", "李四", "王五"])
    assert roster.remove("李四") is True
    assert roster.remove("不存在") is False
    assert roster.names() == ["张三", "王五"]
    roster.clear()
    assert roster.is_empty()


def test_roster_replace_all():
    """replace_all 按多重集处理：入参里出现两份就该有两份。"""
    roster = Roster(["张三", "李四"])
    added = roster.replace_all(["王五", "赵六", "王五"])
    assert added == 3
    assert sorted(roster.names()) == ["王五", "王五", "赵六"]


def test_draw_returns_none_on_empty_roster():
    assert DrawService(FixedRandom()).draw(Roster()) is None


def test_draw_uses_random_source():
    roster = Roster(["张三", "李四"])
    assert DrawService(FixedRandom()).draw(roster).name == "张三"


def test_draw_from_candidates():
    service = DrawService(FixedRandom())
    candidates = [Student("李四"), Student("王五")]
    assert service.draw_from(candidates).name == "李四"
    assert service.draw_from([]) is None





if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except Exception as exc:
                failures += 1
                print(f"  FAIL  {name}: {exc}")
    print()
    print("全部通过" if not failures else f"{failures} 个失败")
    raise SystemExit(1 if failures else 0)
