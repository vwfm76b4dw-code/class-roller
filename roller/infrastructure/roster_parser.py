"""名单文件解析。

单独成模块是因为"格式兼容"是最容易出错、也最需要测试的部分。

设计要点：
- 表头只可能在文件开头出现，因此只在开头若干行做表头判定，
  正文中的姓名（哪怕含"学生""名单"字样）绝不被丢弃。
- 编码嗅探用启发式打分：big5 字节常能被 gb18030 "解码"成乱码，
  单看是否抛异常会选错，必须看解码结果的质量。
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Iterable, List, Sequence

# 行首序号：
#   （1）/ (1)        带括号
#   1. / 1、 / 1)     数字加分隔符
#   ①                 圈号（可紧贴姓名，如 "①赵六"）
#   1 张三            数字加空格（后面必须是非数字）
_LEADING_INDEX = re.compile(
    r"^\s*(?:"
    r"[（(]\s*[0-9①②③④⑤⑥⑦⑧⑨⑩]+\s*[)）]\s*"
    r"|[0-9①②③④⑤⑥⑦⑧⑨⑩]+\s*[.、)）]\s*"
    r"|[①②③④⑤⑥⑦⑧⑨⑩]\s*"
    r"|[0-9]+\s+(?=\D)"
    r")"
)

# 行内编号："1.张三 2.李四" / "①张三 ②李四" —— 把编号当分隔符切开
_INLINE_INDEX = re.compile(
    r"(?<!^)\s*(?:"
    r"[（(]\s*[0-9①②③④⑤⑥⑦⑧⑨⑩]+\s*[)）]"
    r"|[0-9①②③④⑤⑥⑦⑧⑨⑩]+\s*[.、)）]"
    r"|[①②③④⑤⑥⑦⑧⑨⑩]"
    r")(?=\D)"
)

# 姓名后的备注：括号内容（含中英文括号）
_ANNOTATION = re.compile(r"[（(【\[].*?[）)】\]）]\s*$")

# 纯表头词。只有整行内容完全等于（或由这些词加分隔符组成）时才算表头。
_HEADER_WORDS = {
    "姓名", "名字", "学生", "学生姓名", "名单", "学生名单", "班级", "班级名单",
    "序号", "编号", "学号", "性别", "备注", "组别", "小组",
    "name", "student", "students", "no", "no.", "number", "id", "class",
    "index", "gender", "sex",
}

# 表头最多出现在文件开头这么多行内
_HEADER_SCAN_LINES = 5

# 常见列分隔符（含中文顿号）
_SEPARATORS = ("\t", ",", "，", "、", ";", "；", "|")

# 编码尝试顺序：先 utf-8 系，再中文编码，最后 big5
_ENCODINGS = ("utf-8-sig", "utf-8", "gbk", "gb18030", "big5")

# Unicode 私用区与替换字符，出现即说明解码错了
_BAD_RANGES = (
    (0xE000, 0xF8FF),  # 私用区
    (0xFFF0, 0xFFFF),  # 特殊字符
)


def _score_text(text: str) -> float:
    """给解码结果打分，越高越可能是正确编码。

    私用区/替换字符是硬扣分项；CJK 与常见标点加分。
    """
    if not text:
        return 0.0

    bad = 0
    good = 0
    for ch in text:
        code = ord(ch)
        if any(lo <= code <= hi for lo, hi in _BAD_RANGES):
            bad += 1
        elif ch == "\ufffd":
            bad += 2
        elif 0x4E00 <= code <= 0x9FFF:  # CJK 统一汉字
            good += 2
        elif ch.isalpha() or ch.isdigit():
            good += 1
        elif ch in " \t\r\n·.、，,;；|（）()":
            good += 0.5

    total = bad + good
    if total == 0:
        return 0.0
    return (good - bad * 3) / total


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
    """把任意格式的名单文件解析成姓名列表。

    支持的输入形态：
    - 每行一个姓名
    - 逗号 / 制表符 / 分号 / 竖线 / 中文逗号分隔
    - 带行首序号（1. ① （1） 1、）
    - 带表头行、注释行（# 开头）、空行
    - 表格行（1,张三,男）取姓名列
    """

    def __init__(self, max_name_length: int = 20) -> None:
        self._max_len = max_name_length

    # ── 公开接口 ──────────────────────────────────────────
    def parse_text(self, text: str) -> ParseResult:
        result = ParseResult()
        lines = text.splitlines()

        # 只在文件开头若干行内识别表头，正文中的姓名不受影响
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

        text, encoding = self._decode(data)
        result = self.parse_text(text)
        result.encoding = encoding
        return result

    # ── 编码嗅探 ──────────────────────────────────────────
    def _decode(self, data: bytes) -> tuple[str, str]:
        """按打分选出最可能的编码。

        gb18030 几乎能解码任意字节序列（会产出私用区乱码），
        因此不能只看"能否解码"，必须比较解码结果的质量。
        """
        if not data:
            return "", "utf-8"

        best_text = ""
        best_enc = ""
        best_score = float("-inf")

        for enc in _ENCODINGS:
            try:
                text = data.decode(enc)
            except (UnicodeDecodeError, LookupError):
                continue

            score = _score_text(text)
            # 同分时保留先尝试的编码（utf-8 优先）
            if score > best_score:
                best_score = score
                best_text = text
                best_enc = enc

        if not best_enc:
            # 全部失败，退回容错解码
            best_text = data.decode("utf-8", errors="replace")
            best_enc = "utf-8(replace)"

        return best_text, best_enc

    # ── 表头识别 ──────────────────────────────────────────
    def _detect_header_block(self, lines: Sequence[str]) -> int:
        """返回正文起始行号。

        只看开头若干行；连续的空行/注释行/表头行都算头部。
        """
        index = 0
        for line in lines[:_HEADER_SCAN_LINES]:
            stripped = line.strip()
            if not stripped:
                index += 1
                continue
            if stripped.startswith("#"):
                index += 1
                continue
            if self._is_header_line(stripped):
                index += 1
                continue
            break
        return index

    @staticmethod
    def _is_header_line(line: str) -> bool:
        """整行是表头才返回 True。

        形如 "姓名"、"姓名,性别"、"序号\t姓名\t性别" 都算表头；
        "学生李四" 这种是姓名，不算。
        """
        # 先按分隔符拆开
        cells = [line]
        for sep in _SEPARATORS:
            if sep in line:
                cells = [c.strip() for c in line.split(sep) if c.strip()]
                break

        if not cells:
            return False

        normalized = [c.lower().strip(".:：") for c in cells]
        # 每个单元格都必须是表头词
        return all(c in _HEADER_WORDS for c in normalized)

    # ── 行处理 ────────────────────────────────────────────
    def _consume_line(self, raw_line: str, result: ParseResult) -> None:
        line = raw_line.strip()
        if not line:
            return
        if line.startswith("#"):
            return

        cleaned = self._strip_leading_index(line)
        if not cleaned:
            return

        candidates = self._split_cells(cleaned)
        # 形如 "1,张三,男" 的表格行：首格是序号，取第二列当姓名，
        # 否则 "1,张三,男" 会把性别也当成学生。
        if len(candidates) >= 2 and candidates[0].isdigit():
            candidates = candidates[1:2]

        for candidate in candidates:
            name = self._normalize(candidate)
            if self._is_valid_name(name):
                result.names.append(name)
            elif candidate:
                result.skipped.append(candidate)

    @staticmethod
    def _strip_leading_index(line: str) -> str:
        return _LEADING_INDEX.sub("", line, count=1).strip()

    @staticmethod
    def _split_cells(line: str) -> Sequence[str]:
        # 先把行内编号（"1.张三 2.李四"）变成分隔符
        line = _INLINE_INDEX.sub("|", line)
        for sep in _SEPARATORS:
            if sep in line:
                return [cell.strip() for cell in line.split(sep) if cell.strip()]
        return [line]

    def _normalize(self, cell: str) -> str:
        # 去掉包裹的引号与空白
        cell = cell.strip().strip('"').strip("'").strip()
        # 全角空格归一
        cell = cell.replace("\u3000", " ")
        # 去掉姓名后的备注，如 "张三（请假）" → "张三"
        cell = _ANNOTATION.sub("", cell).strip()
        # 去掉拆行后残留的分隔符，如 "张三、" → "张三"
        cell = cell.strip("、,，;；|/\\-— \t")
        # 压缩内部空白
        return re.sub(r"\s+", " ", cell).strip()

    def _is_valid_name(self, name: str) -> bool:
        if not name:
            return False
        if len(name) > self._max_len:
            return False
        if name.isdigit():
            return False
        # 纯符号视为无效
        if not any(ch.isalnum() or "\u4e00" <= ch <= "\u9fff" for ch in name):
            return False
        return True

    # ── 导出 ──────────────────────────────────────────────
    @staticmethod
    def export_names(names: Iterable[str], path: str | Path) -> Path:
        """把名单写成规范的 txt（每行一个姓名）。"""
        target = Path(path)
        target.write_text("\n".join(names) + "\n", encoding="utf-8")
        return target
