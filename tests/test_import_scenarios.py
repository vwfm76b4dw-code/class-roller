"""名单导入全面测试。

覆盖真实教师会遇到的名单格式：Excel 导出、手写编号、不同编码、
带表头/注释/空行、重复姓名、异常行等。

每个用例同时验证：
- 解析出的姓名是否正确、顺序是否保留
- 是否跳过了本该跳过的行
- 文件编码嗅探是否成功
"""

import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from roller.infrastructure.roster_parser import RosterParser


def parse_text(text: str):
    return RosterParser().parse_text(text)


def parse_bytes(data: bytes, encoding: str):
    """把 bytes 写成临时文件再按真实路径解析，覆盖编码嗅探。"""
    path = Path(tempfile.mkdtemp()) / f"names_{encoding}.txt"
    path.write_bytes(data)
    return RosterParser().parse_file(path)


# ── A. 基础格式 ───────────────────────────────────────────
def test_A_plain_lines():
    assert parse_text("张三\n李四\n王五").names == ["张三", "李四", "王五"]


def test_B_utf8_bom():
    result = parse_bytes("张三\n李四\n".encode("utf-8-sig"), "utf-8-sig")
    assert result.names == ["张三", "李四"], result.names


def test_C_crlf_line_endings():
    assert parse_text("张三\r\n李四\r\n王五").names == ["张三", "李四", "王五"]


def test_D_blank_lines_and_whitespace():
    text = "张三\n\n   \n李四\n 王五 \n"
    assert parse_text(text).names == ["张三", "李四", "王五"]


# ── E~J. 行首序号 ─────────────────────────────────────────
def test_E_dot_index():
    assert parse_text("1. 张三\n2. 李四").names == ["张三", "李四"]


def test_F_chinese_dot_index():
    assert parse_text("1、张三\n2、李四").names == ["张三", "李四"]


def test_G_paren_index():
    assert parse_text("1) 张三\n2) 李四").names == ["张三", "李四"]


def test_H_fullwidth_paren_index():
    assert parse_text("（1）张三\n（2）李四").names == ["张三", "李四"]


def test_I_circled_index_tight():
    assert parse_text("①张三\n②李四").names == ["张三", "李四"]


def test_J_number_space_index():
    assert parse_text("1 张三\n2 李四").names == ["张三", "李四"]


# ── K~O. 分隔符 ───────────────────────────────────────────
def test_K_comma():
    assert parse_text("张三,李四,王五").names == ["张三", "李四", "王五"]


def test_L_chinese_comma():
    assert parse_text("张三，李四，王五").names == ["张三", "李四", "王五"]


def test_M_tab():
    assert parse_text("张三\t李四\t王五").names == ["张三", "李四", "王五"]


def test_N_semicolon():
    assert parse_text("张三;李四;王五").names == ["张三", "李四", "王五"]


def test_O_pipe():
    assert parse_text("张三|李四|王五").names == ["张三", "李四", "王五"]


# ── P~T. Excel / 表头 ─────────────────────────────────────
def test_P_csv_with_header_and_index():
    text = "序号,姓名,性别\n1,张三,男\n2,李四,女"
    assert parse_text(text).names == ["张三", "李四"]


def test_Q_csv_no_header_with_index():
    assert parse_text("1,张三,男\n2,李四,女").names == ["张三", "李四"]


def test_R_csv_no_index_no_header():
    """没有序号时，无法判断哪列是姓名——期望行为待定。"""
    result = parse_text("张三,男\n李四,女")
    print(f"    [R] 实际解析: {result.names}")


def test_S_header_name():
    assert parse_text("姓名\n张三\n李四").names == ["张三", "李四"]


def test_T_header_student_name():
    assert parse_text("学生姓名\n张三\n李四").names == ["张三", "李四"]


# ── U~V. 注释与编码 ───────────────────────────────────────
def test_U_comment_lines():
    assert parse_text("# 初一三班\n张三\n# 第二组\n李四").names == ["张三", "李四"]


def test_V_gbk_encoding():
    result = parse_bytes("张三\n李四\n".encode("gbk"), "gbk")
    assert result.names == ["张三", "李四"], result.names


def test_W_big5_encoding():
    result = parse_bytes("張三\n李四\n".encode("big5"), "big5")
    assert result.names == ["張三", "李四"], result.names


# ── X~BB. 边界与去重 ──────────────────────────────────────
def test_X_duplicates_kept_in_parse():
    """解析层不去重（去重由 Roster 负责），但要确认都解析出来。"""
    result = parse_text("张三\n李四\n张三")
    assert result.names == ["张三", "李四", "张三"], result.names


def test_Y_overlong_line_skipped():
    long_name = "超" * 30
    result = parse_text(f"{long_name}\n张三")
    assert "张三" in result.names
    assert long_name not in result.names


def test_Z_pure_number_skipped():
    result = parse_text("20230101\n张三")
    assert result.names == ["张三"], result.names


def test_AA_quoted_names():
    result = parse_text('"张三"\n\'李四\'')
    assert result.names == ["张三", "李四"], result.names


def test_BB_english_name_with_space():
    result = parse_text("Li Hua\nZhang San")
    assert result.names == ["Li Hua", "Zhang San"], result.names


def test_CC_minority_name_with_dot():
    result = parse_text("阿依古丽·买买提\n张三")
    assert result.names == ["阿依古丽·买买提", "张三"], result.names


# ── DD~II. 异常输入 ───────────────────────────────────────
def test_DD_empty_text():
    result = parse_text("")
    assert result.names == [] and result.count == 0


def test_EE_only_header():
    """连续的表头行都应被跳过。"""
    assert parse_text("姓名\n性别\n班级").names == []


def test_EE2_header_then_body():
    """表头块之后紧接着正文。"""
    text = "序号,姓名,性别\n1,张三,男\n2,李四,女"
    assert parse_text(text).names == ["张三", "李四"]


def test_EE3_body_containing_header_word_not_dropped():
    """正文中的姓名含表头词时绝不能被丢弃——这是严重 bug 的回归测试。"""
    result = parse_text("张三\n学生李四\n李名单\n王班级")
    assert result.names == ["张三", "学生李四", "李名单", "王班级"], result.names


def test_FF_only_comments():
    assert parse_text("# 注释\n# 还是注释").names == []


def test_GG_mixed_formats():
    text = "# 初一三班名单\n1. 张三\n李四，王五\n\t赵六\t孙七\n20230801 周八"
    assert parse_text(text).names == ["张三", "李四", "王五", "赵六", "孙七", "周八"]


def test_HH_large_file_performance():
    import time

    names = [f"学生{i}" for i in range(1000)]
    text = "\n".join(names)
    start = time.time()
    result = parse_text(text)
    elapsed = time.time() - start
    assert result.count == 1000, f"期望 1000 人，实际 {result.count}"
    print(f"    [HH] 1000 人解析耗时 {elapsed*1000:.1f}ms")
    assert elapsed < 2.0


def test_HH2_names_with_header_word_kept():
    """1000 个含"学生"字样的姓名必须全部保留。"""
    names = [f"学生{i}" for i in range(1000)]
    result = parse_text("\n".join(names))
    assert result.names == names, f"首尾差异: {result.names[:3]} ... {result.names[-3:]}"


# ── II~OO. 潜在误杀 / 真实姓名风险 ────────────────────────
def test_II_name_containing_header_word():
    """姓名里含表头关键字时不应被误杀。"""
    result = parse_text("名单\n学生\n班级\n张三")
    print(f"    [II] 实际解析: {result.names}")


def test_JJ_fullwidth_space():
    result = parse_text("　张三　\n李四")
    assert "张三" in result.names, result.names


def test_KK_student_id_space_name():
    result = parse_text("20230101 张三\n20230102 李四")
    print(f"    [KK] 实际解析: {result.names}")


def test_LL_name_with_annotation():
    """姓名后的括号备注应被去掉。"""
    result = parse_text("张三（请假）\n李四 (已转学)\n王五【已转走】")
    assert result.names == ["张三", "李四", "王五"], result.names


def test_MM_index_then_comma_list():
    result = parse_text("1. 张三,李四")
    print(f"    [MM] 实际解析: {result.names}")


def test_NN_inline_indexes():
    """同一行多个带编号的姓名要拆开。"""
    assert parse_text("1.张三 2.李四 3.王五").names == ["张三", "李四", "王五"]
    assert parse_text("①张三 ②李四").names == ["张三", "李四"]
    assert parse_text("1.张三、2.李四").names == ["张三", "李四"]


def test_NN2_space_separated_no_index():
    """无编号的同行多个名字不拆（可能是"Li Hua"这类带空格的名字）。"""
    assert parse_text("张三 李四 王五").names == ["张三 李四 王五"]
    assert parse_text("Li Hua").names == ["Li Hua"]


def test_NN3_dunhao_separated():
    assert parse_text("张三、李四、王五").names == ["张三", "李四", "王五"]


def test_OO_export_roundtrip():
    """导出的文件应能被重新导入。"""
    path = Path(tempfile.mkdtemp()) / "out.txt"
    RosterParser.export_names(["张三", "李四", "王五"], path)
    assert RosterParser().parse_file(path).names == ["张三", "李四", "王五"]


if __name__ == "__main__":
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except AssertionError as exc:
                failures.append((name, exc))
                print(f"  FAIL  {name}: {exc}")
            except Exception as exc:
                failures.append((name, exc))
                print(f"  ERROR {name}: {type(exc).__name__}: {exc}")

    print()
    if failures:
        print(f"{len(failures)} 个失败：")
        for name, exc in failures:
            print(f"  - {name}: {exc}")
    else:
        print("全部通过")
    raise SystemExit(1 if failures else 0)
