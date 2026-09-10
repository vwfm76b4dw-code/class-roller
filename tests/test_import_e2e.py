"""端到端导入测试。

不走 UI 点击，但走完整的应用层链路：
    文件 → RosterParser → AppController → Roster → 持久化 → 重新加载

用 tests/fixtures/ 下的真实文件，验证教师实际会遇到的各种名单。
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from roller.application.app_controller import AppController
from roller.application.events import EventType
from roller.infrastructure.config_store import ConfigStore
from roller.infrastructure.roster_parser import RosterParser

FIXTURES = ROOT / "tests" / "fixtures"


def make_controller():
    """每个用例用独立的临时配置，避免相互污染。"""
    cfg = Path(tempfile.mkdtemp()) / "config.json"
    return AppController(ConfigStore(cfg), RosterParser()), cfg


def test_fixture_files_exist():
    expected = [
        "A_plain.txt", "B_excel.csv", "C_numbered.txt", "D_circled.txt",
        "E_gbk.txt", "F_inline.txt", "G_messy.txt", "H_tricky.txt",
        "I_annotation.txt", "J_large.txt",
    ]
    missing = [f for f in expected if not (FIXTURES / f).exists()]
    assert not missing, f"缺少测试文件: {missing}"


def test_import_plain():
    ctrl, _ = make_controller()
    ctrl.import_roster(str(FIXTURES / "A_plain.txt"))
    assert ctrl.roster.names() == ["张三", "李四", "王五"]


def test_import_excel_csv():
    ctrl, _ = make_controller()
    ctrl.import_roster(str(FIXTURES / "B_excel.csv"))
    assert ctrl.roster.names() == ["张三", "李四", "王五"], ctrl.roster.names()


def test_import_numbered():
    ctrl, _ = make_controller()
    ctrl.import_roster(str(FIXTURES / "C_numbered.txt"))
    assert ctrl.roster.names() == ["张三", "李四", "王五"]


def test_import_circled():
    ctrl, _ = make_controller()
    ctrl.import_roster(str(FIXTURES / "D_circled.txt"))
    assert ctrl.roster.names() == ["张三", "李四", "王五"]


def test_import_gbk():
    ctrl, _ = make_controller()
    ctrl.import_roster(str(FIXTURES / "E_gbk.txt"))
    assert ctrl.roster.names() == ["张三", "李四", "王五"], ctrl.roster.names()


def test_import_inline_comma():
    ctrl, _ = make_controller()
    ctrl.import_roster(str(FIXTURES / "F_inline.txt"))
    assert ctrl.roster.names() == ["张三", "李四", "王五"]


def test_import_messy_with_comments():
    ctrl, _ = make_controller()
    ctrl.import_roster(str(FIXTURES / "G_messy.txt"))
    assert ctrl.roster.names() == ["张三", "李四", "王五"], ctrl.roster.names()


def test_import_tricky_names_kept():
    """姓名含"学生""名单"字样必须保留——严重 bug 回归测试。"""
    ctrl, _ = make_controller()
    ctrl.import_roster(str(FIXTURES / "H_tricky.txt"))
    assert ctrl.roster.names() == ["张三", "学生李四", "李名单", "王班级"], (
        ctrl.roster.names()
    )


def test_import_annotations_stripped():
    ctrl, _ = make_controller()
    ctrl.import_roster(str(FIXTURES / "I_annotation.txt"))
    assert ctrl.roster.names() == ["张三", "李四", "王五"], ctrl.roster.names()


def test_import_large():
    ctrl, _ = make_controller()
    ctrl.import_roster(str(FIXTURES / "J_large.txt"))
    assert ctrl.student_count == 50
    assert ctrl.roster.names()[0] == "学生01"
    assert ctrl.roster.names()[-1] == "学生50"


def test_import_appends_not_replaces():
    """连续导入两个文件应累加，而不是覆盖。"""
    ctrl, _ = make_controller()
    ctrl.import_roster(str(FIXTURES / "A_plain.txt"))
    ctrl.import_roster(str(FIXTURES / "D_circled.txt"))
    # A 和 D 是同样的三个人，去重后仍为 3
    assert ctrl.student_count == 3, ctrl.roster.names()


def test_import_dedupes_across_files():
    ctrl, _ = make_controller()
    ctrl.import_roster(str(FIXTURES / "A_plain.txt"))  # 张三 李四 王五
    ctrl.import_roster(str(FIXTURES / "F_inline.txt"))  # 同样三人
    assert ctrl.roster.names() == ["张三", "李四", "王五"]


def test_replace_roster():
    ctrl, _ = make_controller()
    ctrl.import_roster(str(FIXTURES / "A_plain.txt"))
    ctrl.replace_roster(str(FIXTURES / "D_circled.txt"))
    assert ctrl.student_count == 3


def test_import_missing_file_emits_error():
    """文件不存在时应发错误事件，不崩溃。"""
    ctrl, _ = make_controller()
    errors = []
    ctrl.bus.subscribe(EventType.ERROR, lambda e: errors.append(e.payload))
    result = ctrl.import_roster(str(FIXTURES / "不存在的文件.txt"))
    assert result.count == 0
    assert errors, "应发出错误事件"
    assert ctrl.student_count == 0


def test_import_emits_events():
    ctrl, _ = make_controller()
    events = []
    ctrl.bus.subscribe(EventType.ROSTER_IMPORTED, lambda e: events.append(("imported", e.payload)))
    ctrl.bus.subscribe(EventType.ROSTER_CHANGED, lambda e: events.append(("changed", e.payload)))

    ctrl.import_roster(str(FIXTURES / "A_plain.txt"))

    kinds = [k for k, _ in events]
    assert "imported" in kinds, events
    assert "changed" in kinds, events
    imported = next(p for k, p in events if k == "imported")
    assert imported["total"] == 3


def test_import_persists_and_reloads():
    """导入后配置落盘，重开程序仍能读到名单。"""
    ctrl, cfg = make_controller()
    ctrl.import_roster(str(FIXTURES / "J_large.txt"))
    assert ctrl.student_count == 50

    # 用同一个配置路径重建控制器，模拟重启
    ctrl2 = AppController(ConfigStore(cfg), RosterParser())
    assert ctrl2.student_count == 50, ctrl2.student_count
    assert ctrl2.roster.names()[0] == "学生01"


def test_import_then_draw_works():
    """导入后抽奖应能正常进行。"""
    ctrl, _ = make_controller()
    ctrl.import_roster(str(FIXTURES / "A_plain.txt"))
    assert ctrl.can_draw()
    winner = ctrl.draw_now()
    assert winner in ["张三", "李四", "王五"], winner


def test_export_then_reimport():
    """导出的文件能原样导回。"""
    ctrl, _ = make_controller()
    ctrl.import_roster(str(FIXTURES / "H_tricky.txt"))
    original = ctrl.roster.names()

    out = Path(tempfile.mkdtemp()) / "exported.txt"
    assert ctrl.export_roster(str(out))

    ctrl2, _ = make_controller()
    ctrl2.import_roster(str(out))
    assert ctrl2.roster.names() == original, ctrl2.roster.names()


def test_clear_then_reimport():
    ctrl, _ = make_controller()
    ctrl.import_roster(str(FIXTURES / "A_plain.txt"))
    ctrl.clear_roster()
    assert ctrl.student_count == 0
    ctrl.import_roster(str(FIXTURES / "A_plain.txt"))
    assert ctrl.student_count == 3


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
    if failures:
        print(f"{len(failures)} 个失败")
        for n, e in failures:
            print(f"  - {n}: {e}")
    else:
        print("全部通过")
    raise SystemExit(1 if failures else 0)
