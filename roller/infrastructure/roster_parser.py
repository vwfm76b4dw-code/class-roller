"""名单文件解析。

这是最容易出错、也最需要测试的部分。设计原则：**宁可多认，不可漏人**。

支持范围（按学校实际来源）：
- 纯文本：UTF-8(/BOM)、GBK/GB18030、Big5、**UTF-16 LE/BE（含无 BOM）**、UTF-32
- Word **.docx**（zip 容器，取 word/document.xml 的 <w:t> 文本）
- Excel **.xlsx**（zip 容器，取 sharedStrings.xml 与工作表文本）
- CSV/TSV：逗号、制表符、顿号、分号、竖线、全角空格、半角空格
- 行首序号、行内编号、姓名后备注、表格列（性别/学号）过滤
- 标题行只在开头跳过，且必须像标题（保护"李名单"这类正常姓名）

关键的取舍：
1. UTF-16 单独处理——记事本"Unicode"另存与不少系统导出都是 UTF-16，
   早期版本只试 UTF-8/GBK，会把整份名单解成乱码（等于一个人都认不出）。
2. 姓名内的空格要区分对待：中文名去空格（"李 明"→"李明"），
   西文名保留（"Li Hua"），避免把一个人的名字拆成两个人。
3. 空格既可能是"多个姓名分隔"（"张三 李四"），也可能是"表格列分隔"
   （"1 张三 男"），靠"是否含性别/学号等非姓名单元格"来判断。
"""

from __future__ import annotations

import re
import zipfile
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Optional, Sequence, Tuple

# ── 正则 ──────────────────────────────────────────────────
# 行首序号：（1）/ 1. / 1、/ 1) / ① / "1 张三" 的数字前缀
_LEADING_INDEX = re.compile(
    r"^\s*(?:"
    r"[（(]\s*[0-9①②③④⑤⑥⑦⑧⑨⑩]+\s*[)）]\s*"
    r"|[0-9①②③④⑤⑥⑦⑧⑨⑩]+\s*[.、)）]\s*"
    r"|[①②③④⑤⑥⑦⑧⑨⑩]\s*"
    r"|[0-9]+\s+(?=\D)"
    r")"
)

# 行内编号：编号**前面有空白**才当分隔，
# 否则 "初一(3)班名单" 会被 "(3)" 切两半。
_INLINE_INDEX = re.compile(
    r"(?<=\s)(?:"
    r"[（(]\s*[0-9①②③④⑤⑥⑦⑧⑨⑩]+\s*[)）]"
    r"|[0-9①②③④⑤⑥⑦⑧⑨⑩]+\s*[.、)）]"
    r"|[①②③④⑤⑥⑦⑧⑨⑩]"
    r")(?=\D)"
)

# 姓名后的括号备注：张三（请假）→ 张三
_ANNOTATION = re.compile(r"[（(【\[].*?[）)】\]]\s*$")
# 姓名后的数字尾巴：张三 1 → 张三（但要保护"1班"这类，故要求是行尾且前面有空白）
_TRAILING_NUMBER = re.compile(r"\s+\d{1,3}\s*$")

_SEPARATORS = ("\t", ",", "，", "、", ";", "；", "|", "\u3000")
_WHITESPACE = re.compile(r"[ \u3000]+")

_HEADER_WORDS = {
    "姓名", "名字", "学生", "学生姓名", "名单", "学生名单", "班级", "班级名单",
    "序号", "编号", "学号", "性别", "备注", "组别", "小组",
    "name", "student", "students", "no", "no.", "number", "id", "class",
    "index", "gender", "sex",
}

# 非姓名单元格：出现在表格行里时应丢弃
_NON_NAME_CELLS = {
    "男", "女", "性别", "备注", "说明", "组别", "小组", "学号", "班级",
    "年级", "序号", "编号", "male", "female", "m", "f",
}

_TITLE_HINTS = ("名单", "班级", "学生", "年级", "花名册", "名册")
_TITLE_MIN_LEN = 6
_HEADER_SCAN_LINES = 5

# 编码候选：UTF-16/32 一并列出，由打分器决定用哪个
_ENCODINGS = (
    "utf-8-sig", "utf-8",
    "gbk", "gb18030", "big5",
    "utf-16", "utf-16-le", "utf-16-be",
    "utf-32",
)
_BAD_RANGES = ((0xE000, 0xF8FF), (0xFFF0, 0xFFFF))

_CJK = re.compile(r"^[\u4e00-\u9fff]{2,4}$")      # 像完整中文姓名
_HAS_CJK = re.compile(r"[\u4e00-\u9fff]")
_PURE_DIGITS = re.compile(r"^\d+$")


def _score_text(text: str) -> float:
    """给解码结果打分，越高越可能是正确编码。

    私用区/替换字符硬扣分，CJK 与常见标点加分。
    必要性：gb18030 几乎能"解码"任意字节序列（产出私用区乱码），
    单看"能否解码"必然误判——Big5 与 UTF-16 都会栽在这里。
    """
    if not text:
        return 0.0
    bad = good = 0
    for ch in text:
        code = ord(ch)
        if any(lo <= code <= hi for lo, hi in _BAD_RANGES):
            bad += 1
        elif ch == "\ufffd":
            bad += 2
        elif 0x4E00 <= code <= 0x9FFF:
            good += 2
        elif ch.isalpha() or ch.isdigit():
            good += 1
        elif ch in " \t\r\n·.、，,;；|（）()-_":
            good += 0.5
        elif code < 0x20:
            # 控制字符：UTF-16 误判的典型特征（每个字符间夹 \x00）
            bad += 1.5
    total = bad + good
    return (good - bad * 3) / total if total else 0.0


@dataclass
class ParseResult:
    """解析结果。保留被丢弃的行，便于 UI 提示用户。"""

    names: List[str] = field(default_factory=list)
    skipped: List[str] = field(default_factory=list)
    encoding: str = ""

    @property
    def count(self) -> int:
        return len(self.names)


class RosterParser:
    """把各种来源的名单解析成姓名列表（允许同名重复）。"""

    def __init__(self, max_name_length: int = 20) -> None:
        self._max_len = max_name_length

    # ── 公开接口 ──────────────────────────────────────────
    def parse_text(self, text: str) -> ParseResult:
        result = ParseResult()
        lines = text.splitlines()
        header_end = self._detect_header_block(lines)
        for raw_line in lines[header_end:]:
            self._consume_line(raw_line, result)
        return result

    def parse_file(self, path: str | Path) -> ParseResult:
        file_path = Path(path)
        try:
            data = file_path.read_bytes()
        except OSError as exc:
            raise IOError(f"无法读取文件：{file_path}") from exc

        # Office 文档是 zip 容器，先取出其中的纯文本再走文本解析
        extracted = self._extract_office_text(data, file_path)
        if extracted is not None:
            text, label = extracted
            result = self.parse_text(text)
            result.encoding = label
            return result

        text, encoding = self._decode(data)
        result = self.parse_text(text)
        result.encoding = encoding
        return result

    # ── Office 文档 ───────────────────────────────────────
    @staticmethod
    def _extract_office_text(
        data: bytes, path: Path
    ) -> Optional[Tuple[str, str]]:
        """从 .docx / .xlsx 里取出文本。

        两者都是 zip。若不是 zip（或不是 Office 文档）返回 None，
        由调用方走普通文本解码。
        """
        if data[:2] != b"PK":
            return None
        suffix = path.suffix.lower()

        try:
            import io

            with zipfile.ZipFile(io.BytesIO(data)) as zf:
                names = set(zf.namelist())

                # Word：正文在 word/document.xml，文本在 <w:t> 里；
                # 每个 <w:p> 是一段，需按段落分行才能正确拆出多个姓名。
                if "word/document.xml" in names or suffix == ".docx":
                    try:
                        xml = zf.read("word/document.xml").decode(
                            "utf-8", errors="ignore"
                        )
                    except KeyError:
                        return None
                    return (_paragraphs_to_lines(xml), "docx")

                # Excel：文本通常在 sharedStrings.xml（共享字符串表）。
                # 表格里一个姓名一个单元格，因此用换行连接即可。
                if suffix == ".xlsx" or any(
                    n.startswith("xl/") for n in names
                ):
                    chunks: List[str] = []
                    if "xl/sharedStrings.xml" in names:
                        chunks.append(
                            zf.read("xl/sharedStrings.xml").decode(
                                "utf-8", errors="ignore"
                            )
                        )
                    for name in sorted(names):
                        if name.startswith("xl/worksheets/") and name.endswith(".xml"):
                            chunks.append(
                                zf.read(name).decode("utf-8", errors="ignore")
                            )
                    if not chunks:
                        return None
                    return (_cells_to_lines("\n".join(chunks)), "xlsx")
        except (zipfile.BadZipFile, OSError, KeyError):
            return None
        return None

    # ── 编码嗅探 ──────────────────────────────────────────
    def _decode(self, data: bytes) -> Tuple[str, str]:
        if not data:
            return "", "utf-8"

        # 有 BOM 时直接采信（最可靠）
        bom_map = [
            (b"\xff\xfe\x00\x00", "utf-32"),
            (b"\x00\x00\xfe\xff", "utf-32"),
            (b"\xff\xfe", "utf-16"),
            (b"\xfe\xff", "utf-16"),
            (b"\xef\xbb\xbf", "utf-8-sig"),
        ]
        for bom, enc in bom_map:
            if data.startswith(bom):
                try:
                    return data.decode(enc).lstrip("\ufeff"), enc
                except (UnicodeDecodeError, LookupError):
                    break

        best_text, best_enc, best_score = "", "", float("-inf")
        for enc in _ENCODINGS:
            try:
                text = data.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue
            score = _score_text(text)
            if score > best_score:
                best_text, best_enc, best_score = text, enc, score
        if not best_enc:
            best_text = data.decode("utf-8", errors="replace")
            best_enc = "utf-8(replace)"
        return best_text, best_enc

    # ── 头部识别 ──────────────────────────────────────────
    def _detect_header_block(self, lines: Sequence[str]) -> int:
        index = 0
        for line in lines[:_HEADER_SCAN_LINES]:
            stripped = line.strip()
            if not stripped or stripped.startswith("#"):
                index += 1
                continue
            if self._is_header_line(stripped) or self._is_title_line(stripped):
                index += 1
                continue
            break
        return index

    @staticmethod
    def _is_header_line(line: str) -> bool:
        cells = [line]
        for sep in _SEPARATORS:
            if sep in line:
                cells = [c.strip() for c in line.split(sep) if c.strip()]
                break
        if not cells:
            return False
        return all(c.lower().strip(".:：") in _HEADER_WORDS for c in cells)

    @staticmethod
    def _is_title_line(line: str) -> bool:
        """像文档标题才跳过；长度门槛保护"李名单"这类正常姓名。"""
        if len(line) < _TITLE_MIN_LEN:
            return False
        return any(hint in line for hint in _TITLE_HINTS)

    # ── 行处理 ────────────────────────────────────────────
    def _consume_line(self, raw_line: str, result: ParseResult) -> None:
        line = raw_line.strip()
        if not line or line.startswith("#"):
            return

        cleaned = _LEADING_INDEX.sub("", line, count=1).strip()
        if not cleaned:
            return

        cells = self._split_cells(cleaned)
        # 表格行：首格是数字序号 → 取后一列（"1,张三,男" → 张三）
        if len(cells) >= 2 and cells[0].isdigit():
            cells = cells[1:2]
        # 多列且无序号 → 剔除性别/学号/备注这类非姓名列
        elif len(cells) >= 2:
            kept = [c for c in cells if not self._is_non_name_cell(c)]
            if kept:
                cells = kept

        for candidate in cells:
            name = self._normalize(candidate)
            if self._is_valid_name(name):
                result.names.append(name)
            elif candidate:
                result.skipped.append(candidate)

    def _split_cells(self, line: str) -> Sequence[str]:
        """把一个行拆成若干姓名。

        分三种情况：
        1. 有显式分隔符（逗号/制表符/顿号/分号/竖线/全角空格）→ 直接拆
        2. 只有半角空格：可能是"多个姓名"，也可能是"表格列"。
           先剔除性别/学号等非姓名单元格；
           若剩下的都是完整中文姓名 → 拆开；否则视为一个姓名（含空格的
           西文名或姓名中间误加空格的情况）
        3. 无分隔符 → 整行是一个姓名
        """
        line = _INLINE_INDEX.sub("|", line)
        for sep in _SEPARATORS:
            if sep in line:
                parts = [c.strip() for c in line.split(sep) if c.strip()]
                # 切分后每段可能仍带编号（"1.张三、2.李四" → "2.李四"），
                # 再各自剥一次行首编号
                return [
                    _LEADING_INDEX.sub("", p, count=1).strip() or p
                    for p in parts
                ]

        if _WHITESPACE.search(line):
            parts = [p for p in _WHITESPACE.split(line) if p]
            # 剔除性别/学号等列
            kept = [p for p in parts if not self._is_non_name_cell(p)]
            if len(kept) >= 2 and all(_CJK.match(p) for p in kept):
                return kept
            if kept and len(kept) < len(parts):
                # 原本是表格行，剔掉非姓名列后剩一个 → 就是它
                return kept
        return [line]

    @staticmethod
    def _is_non_name_cell(cell: str) -> bool:
        """该单元格是否明显不是姓名（性别/学号/备注等）。"""
        return cell.strip().lower() in _NON_NAME_CELLS

    def _normalize(self, cell: str) -> str:
        cell = cell.strip().strip('"').strip("'").strip()
        cell = cell.replace("\u3000", " ")
        cell = _ANNOTATION.sub("", cell).strip()
        # 姓名后的数字尾巴（"张三 1" → "张三"）
        cell = _TRAILING_NUMBER.sub("", cell).strip()
        cell = cell.strip("、,，;；|/\\-— \t")
        # 中文名内部不留空格（"李 明" → "李明"）；
        # 西文名保留（"Li Hua"）
        if _HAS_CJK.search(cell):
            cell = re.sub(r"\s+", "", cell)
        else:
            cell = re.sub(r"\s+", " ", cell).strip()
        return cell

    def _is_valid_name(self, name: str) -> bool:
        if not name or len(name) > self._max_len:
            return False
        if _PURE_DIGITS.match(name):
            return False
        if not any(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" for ch in name):
            return False
        return True

    # ── 导出 ──────────────────────────────────────────────
    @staticmethod
    def export_names(names: Iterable[str], path: str | Path) -> Path:
        target = Path(path)
        target.write_text("\n".join(names) + "\n", encoding="utf-8")
        return target


# ── Office XML → 文本行 ───────────────────────────────────
_TAG = re.compile(r"<[^>]+>")


def _paragraphs_to_lines(xml: str) -> str:
    """Word 文档：每个 <w:p> 是一段，段内 <w:t> 是文本。

    必须按段落分行，否则整篇会连成一行、姓名粘在一起。
    """
    # 先按段分割（</w:p> 是段落结束）
    lines: List[str] = []
    for para in re.split(r"</w:p>", xml):
        texts = re.findall(r"<w:t[^>]*>(.*?)</w:t>", para, re.S)
        if not texts:
            continue
        text = "".join(texts)
        text = _unescape_xml(text).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def _cells_to_lines(xml: str) -> str:
    """Excel：<t> 里是单元格文本，一个单元格一行。"""
    texts = re.findall(r"<t[^>]*>(.*?)</t>", xml, re.S)
    lines = []
    for raw in texts:
        text = _unescape_xml(raw).strip()
        if text:
            lines.append(text)
    return "\n".join(lines)


def _unescape_xml(text: str) -> str:
    return (
        text.replace("&lt;", "<")
        .replace("&gt;", ">")
        .replace("&quot;", '"')
        .replace("&apos;", "'")
        .replace("&amp;", "&")
    )
