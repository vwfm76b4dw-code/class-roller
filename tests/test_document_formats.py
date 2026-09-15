"""文档来源与编码的完整测试。

用户反馈"根本不能完全识别文档里的所有人"。抽奖算法已用统计检验证明均匀，
问题出在名单进入系统这一步——学校名单大量是 Word/Excel 和 UTF-16 编码，
早期版本会把它们解成乱码或整份丢失。

这里覆盖：各编码（含 UTF-16/32）、.docx、.xlsx、CSV 变体、
姓名内空格、序号尾巴、性别列过滤，以及"解析数 == 导入数"的一致性。
"""

import io
import sys
import tempfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from roller.application.app_controller import AppController
from roller.infrastructure.config_store import ConfigStore
from roller.infrastructure.roster_parser import RosterParser

NAMES = ["张三", "李四", "王五", "赵六", "钱七"]


def _tmp_file(name: str, data: bytes) -> Path:
    path = Path(tempfile.mkdtemp()) / name
    path.write_bytes(data)
    return path


def parse_bytes(data: bytes, name: str = "t.txt"):
    return RosterParser().parse_file(_tmp_file(name, data))


def parse_text(text: str):
    return RosterParser().parse_text(text)


# ── A. 编码 ───────────────────────────────────────────────
def test_utf8_plain():
    assert parse_bytes("\n".join(NAMES).encode("utf-8")).names == NAMES


def test_utf8_with_bom():
    assert parse_bytes("\n".join(NAMES).encode("utf-8-sig")).names == NAMES


def test_gbk():
    assert parse_bytes("\n".join(NAMES).encode("gbk")).names == NAMES


def test_gb18030():
    assert parse_bytes("\n".join(NAMES).encode("gb18030")).names == NAMES


def test_utf16_le_with_bom():
    """记事本「Unicode」另存为——学校最常见，早期版本全乱码。"""
    result = parse_bytes("\n".join(NAMES).encode("utf-16"))
    assert result.names == NAMES, result.names
    assert result.encoding.startswith("utf-16")


def test_utf16_be_with_bom():
    data = b"\xfe\xff" + "\n".join(NAMES).encode("utf-16-be")
    assert parse_bytes(data).names == NAMES


def test_utf16_without_bom():
    """部分系统导出无 BOM 的 UTF-16，必须在打分阶段胜出。"""
    assert parse_bytes("\n".join(NAMES).encode("utf-16-le")).names == NAMES


def test_utf32():
    assert parse_bytes("\n".join(NAMES).encode("utf-32")).names == NAMES


# ── B. Word / Excel ──────────────────────────────────────
def _docx_bytes(names) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        body = "".join(f"<w:p><w:r><w:t>{n}</w:t></w:r></w:p>" for n in names)
        z.writestr(
            "word/document.xml",
            '<?xml version="1.0"?><w:document xmlns:w="http://schemas.'
            'openxmlformats.org/wordprocessingml/2006/main"><w:body>'
            + body + "</w:body></w:document>",
        )
    return buf.getvalue()


def _xlsx_bytes(names) -> bytes:
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        rows = "".join(
            f'<row r="{i+1}"><c r="A{i+1}" t="inlineStr"><is><t>{n}</t></is></c></row>'
            for i, n in enumerate(names)
        )
        z.writestr(
            "xl/worksheets/sheet1.xml",
            '<?xml version="1.0"?><worksheet xmlns="http://schemas.'
            'openxmlformats.org/spreadsheetml/2006/main"><sheetData>'
            + rows + "</sheetData></worksheet>",
        )
    return buf.getvalue()


def test_docx():
    """Word 文档——早期版本一个名字都提不出来。"""
    result = parse_bytes(_docx_bytes(NAMES), "名单.docx")
    assert result.names == NAMES, result.names
    assert result.encoding == "docx"


def test_docx_one_name_per_paragraph():
    """每个段落一个姓名，不能粘成一行。"""
    many = [f"学生{i:02d}" for i in range(1, 21)]
    result = parse_bytes(_docx_bytes(many), "大名单.docx")
    assert result.names == many, result.names


def test_xlsx():
    result = parse_bytes(_xlsx_bytes(NAMES), "名单.xlsx")
    assert result.names == NAMES, result.names


def test_xlsx_shared_strings():
    """Excel 常用共享字符串表（sharedStrings.xml）存文本。"""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as z:
        z.writestr("[Content_Types].xml", '<?xml version="1.0"?><Types/>')
        shared = "".join(f"<si><t>{n}</t></si>" for n in NAMES)
        z.writestr(
            "xl/sharedStrings.xml",
            '<?xml version="1.0"?><sst xmlns="http://schemas.openxmlformats.org/'
            'spreadsheetml/2006/main">' + shared + "</sst>",
        )
    result = parse_bytes(buf.getvalue(), "共享.xlsx")
    assert result.names == NAMES, result.names


# ── C. CSV 变体 ───────────────────────────────────────────
def test_csv_index_and_name():
    text = "序号,姓名\n" + "".join(f"{i+1},{n}\n" for i, n in enumerate(NAMES))
    assert parse_text(text).names == NAMES


def test_csv_name_and_gender_filtered():
    """性别列不能被当成学生——这是真实表格最常见的形态。"""
    text = "姓名,性别\n" + "".join(f"{n},男\n" for n in NAMES)
    assert parse_text(text).names == NAMES, parse_text(text).names


def test_table_row_filters_gender():
    assert parse_text("1,张三,男\n2,李四,女").names == ["张三", "李四"]
    assert parse_text("1 张三 男\n2 李四 女").names == ["张三", "李四"]


def test_csv_quoted_single_row():
    assert parse_text('"张三","李四","王五"').names == NAMES[:3]


# ── D. 姓名的特殊形态 ────────────────────────────────────
def test_space_inside_chinese_name_removed():
    """中文名中间误加空格应合并——不能拆成两个人。"""
    assert parse_text("李 明\n王 芳").names == ["李明", "王芳"]


def test_space_separated_names_split():
    """整行都是完整中文姓名时才按空格拆开。"""
    assert parse_text("张三 李四 王五").names == ["张三", "李四", "王五"]
    assert parse_text("张三　李四　王五").names == ["张三", "李四", "王五"]


def test_western_name_kept_whole():
    assert parse_text("Li Hua").names == ["Li Hua"]


def test_trailing_number_removed():
    assert parse_text("张三 1\n李四 2").names == ["张三", "李四"]


def test_annotation_removed():
    assert parse_text("张三(请假)\n李四（病假）").names == ["张三", "李四"]


def test_duplicate_names_both_kept():
    """同名不能被吞掉——班里可能真有两个张伟。"""
    result = parse_text("张伟\n李四\n张伟\n王五")
    assert result.names == ["张伟", "李四", "张伟", "王五"]


def test_protected_names_resembling_title():
    """含"名单/学生"的正常姓名不能被当标题丢掉。"""
    result = parse_text("学生李四\n李名单\n王班级")
    assert result.names == ["学生李四", "李名单", "王班级"], result.names


def test_document_title_skipped():
    assert parse_text("初一(3)班学生名单\n张三\n李四").names == ["张三", "李四"]


# ── E. 端到端一致性 ──────────────────────────────────────
def test_parsed_count_equals_imported_count():
    """解析出的条数必须等于导入后的学生数（不能有静默丢失）。"""
    payload = "\n".join(f"学生{i:02d}" for i in range(1, 51))
    path = _tmp_file("big.txt", payload.encode("utf-8"))

    parsed = RosterParser().parse_file(path)
    assert parsed.count == 50, parsed.count

    ctrl = AppController(
        ConfigStore(Path(tempfile.mkdtemp()) / "config.json"), RosterParser()
    )
    ctrl.import_roster(str(path))
    assert ctrl.student_count == parsed.count, (
        f"解析 {parsed.count} 条，实际导入 {ctrl.student_count} 人"
    )


def test_reimport_same_file_does_not_double():
    """同一文件重复导入不应让名单翻倍。"""
    path = _tmp_file("n.txt", "\n".join(NAMES).encode("utf-8"))
    ctrl = AppController(
        ConfigStore(Path(tempfile.mkdtemp()) / "config.json"), RosterParser()
    )
    ctrl.import_roster(str(path))
    first = ctrl.student_count
    ctrl.import_roster(str(path))
    assert ctrl.student_count == first, ctrl.roster.names()


def test_import_with_duplicates_keeps_them():
    """文件里本来就有同名（两个张伟），导入后应都在。"""
    path = _tmp_file("dup.txt", "张伟\n李四\n张伟\n王五\n".encode("utf-8"))
    ctrl = AppController(
        ConfigStore(Path(tempfile.mkdtemp()) / "config.json"), RosterParser()
    )
    ctrl.import_roster(str(path))
    assert ctrl.student_count == 4, ctrl.roster.names()
    assert ctrl.roster.count_of("张伟") == 2


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
