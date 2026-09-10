"""基础设施层测试：名单解析与配置持久化。"""

import json
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from roller.infrastructure.config_store import AppConfig, ConfigStore
from roller.infrastructure.roster_parser import RosterParser
from roller.domain.models import DrawRecord


# ── 名单解析 ──────────────────────────────────────────────
def test_parse_plain_lines():
    result = RosterParser().parse_text("张三\n李四\n王五")
    assert result.names == ["张三", "李四", "王五"]


def test_parse_comma_separated():
    result = RosterParser().parse_text("张三,李四,王五")
    assert result.names == ["张三", "李四", "王五"]


def test_parse_chinese_comma():
    result = RosterParser().parse_text("张三，李四，王五")
    assert result.names == ["张三", "李四", "王五"]


def test_parse_tab_separated():
    result = RosterParser().parse_text("张三\t李四\t王五")
    assert result.names == ["张三", "李四", "王五"]


def test_parse_skips_comment_and_blank_lines():
    text = "# 这是注释\n\n张三\n\n李四\n"
    assert RosterParser().parse_text(text).names == ["张三", "李四"]


def test_parse_skips_header_line():
    text = "姓名\n张三\n李四"
    assert RosterParser().parse_text(text).names == ["张三", "李四"]


def test_parse_strips_leading_index():
    text = "1. 张三\n2、李四\n3) 王五\n①赵六"
    assert RosterParser().parse_text(text).names == ["张三", "李四", "王五", "赵六"]


def test_parse_takes_first_cell_of_multi_column():
    text = "1,张三,男\n2,李四,女"
    assert RosterParser().parse_text(text).names == ["张三", "李四"]


def test_parse_records_skipped():
    # 纯数字与超长内容应被跳过并记录
    result = RosterParser().parse_text("123\n" + "超" * 30 + "\n张三")
    assert "张三" in result.names
    assert result.skipped


def test_parse_empty_text():
    result = RosterParser().parse_text("")
    assert result.names == []
    assert result.count == 0


def test_parse_file_utf8(tmp_path=None):
    path = Path(tempfile.mkdtemp()) / "names.txt"
    path.write_text("张三\n李四\n", encoding="utf-8")
    result = RosterParser().parse_file(path)
    assert result.names == ["张三", "李四"]
    assert result.encoding.startswith("utf-8")


def test_parse_file_gbk():
    path = Path(tempfile.mkdtemp()) / "gbk.txt"
    path.write_bytes("张三\n李四\n".encode("gbk"))
    result = RosterParser().parse_file(path)
    assert result.names == ["张三", "李四"]


def test_export_names():
    path = Path(tempfile.mkdtemp()) / "out.txt"
    RosterParser.export_names(["张三", "李四"], path)
    assert path.read_text(encoding="utf-8") == "张三\n李四\n"


# ── 配置持久化 ────────────────────────────────────────────
def test_config_roundtrip():
    path = Path(tempfile.mkdtemp()) / "config.json"
    store = ConfigStore(path)

    cfg = AppConfig()
    cfg.names = ["张三", "李四"]
    cfg.history = [DrawRecord("张三")]
    cfg.always_on_top = True
    cfg.window_width = 620
    cfg.window_height = 480
    store.save(cfg)

    loaded = store.load()
    assert loaded.names == ["张三", "李四"]
    assert len(loaded.history) == 1
    assert loaded.history[0].name == "张三"
    assert loaded.always_on_top is True
    assert loaded.window_width == 620
    assert loaded.window_height == 480


def test_config_missing_file_returns_default():
    path = Path(tempfile.mkdtemp()) / "nope.json"
    assert ConfigStore(path).load().names == []


def test_config_corrupt_file_returns_default():
    path = Path(tempfile.mkdtemp()) / "bad.json"
    path.write_text("{ 这不是 json", encoding="utf-8")
    assert ConfigStore(path).load().names == []


def test_config_clamps_window_size():
    raw = {"window_width": 99999, "window_height": 5}
    cfg = AppConfig.from_dict(raw)
    assert cfg.window_width == 4000
    assert cfg.window_height == 280


def test_config_ignores_bad_types():
    raw = {"names": "不是列表", "history": 123, "always_on_top": "yes"}
    cfg = AppConfig.from_dict(raw)
    assert cfg.names == []
    assert cfg.history == []
    assert cfg.always_on_top is True


def test_config_from_dict_skips_empty_names():
    raw = {"names": ["张三", "", "  ", "李四"]}
    assert AppConfig.from_dict(raw).names == ["张三", "李四"]


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
