"""应用控制器：所有用例的入口。

职责：
- 持有名单、历史、配置等应用状态
- 编排领域服务与基础设施
- 通过事件总线通知 UI 刷新

不 import 任何 tkinter，因此可以脱离界面测试。
"""

from __future__ import annotations

from pathlib import Path
from typing import List, Optional

from roller.application.events import EventBus, EventType
from roller.domain.draw_service import DrawService, RandomSource
from roller.domain.models import DrawRecord, Roster, Student
from roller.infrastructure.config_store import (
    MAX_HISTORY,
    MIN_WINDOW_H,
    MIN_WINDOW_W,
    MAX_WINDOW_H,
    MAX_WINDOW_W,
    AppConfig,
    ConfigStore,
)
from roller.infrastructure.roster_parser import ParseResult, RosterParser


class AppController:
    """抽奖器的主控制器。"""

    def __init__(
        self,
        config_store: ConfigStore,
        parser: Optional[RosterParser] = None,
        draw_service: Optional[DrawService] = None,
        bus: Optional[EventBus] = None,
        random_source: Optional[RandomSource] = None,
    ) -> None:
        self._config_store = config_store
        self._parser = parser or RosterParser()
        self._draw_service = draw_service or DrawService(random_source)
        self._bus = bus or EventBus()

        self._config: AppConfig = config_store.load()
        self._roster = Roster(self._config.names)
        self._history: List[DrawRecord] = list(self._config.history)

        # 近期抽中者，用于"不重复抽取"窗口
        self._recent_winners: List[str] = [r.name for r in self._history[-20:]]

    # ── 只读属性 ──────────────────────────────────────────
    @property
    def bus(self) -> EventBus:
        return self._bus

    @property
    def roster(self) -> Roster:
        return self._roster

    @property
    def history(self) -> List[DrawRecord]:
        return list(self._history)

    @property
    def config(self) -> AppConfig:
        return self._config

    @property
    def student_count(self) -> int:
        return len(self._roster)

    # ── 名单管理 ──────────────────────────────────────────
    def import_roster(self, path: str) -> ParseResult:
        """从文件导入名单，追加到现有名单。"""
        try:
            result = self._parser.parse_file(path)
        except IOError as exc:
            self._bus.emit(EventType.ERROR, message=str(exc))
            return ParseResult()

        added = self._roster.extend(result.names)
        self._config.last_dir = str(Path(path).parent)
        self._persist()

        self._bus.emit(
            EventType.ROSTER_IMPORTED,
            added=added,
            total=len(self._roster),
            skipped=len(result.skipped),
            file=Path(path).name,
        )
        self._bus.emit(EventType.ROSTER_CHANGED, count=len(self._roster))
        return result

    def replace_roster(self, path: str) -> ParseResult:
        """用文件内容替换现有名单。"""
        try:
            result = self._parser.parse_file(path)
        except IOError as exc:
            self._bus.emit(EventType.ERROR, message=str(exc))
            return ParseResult()

        self._roster.replace_all(result.names)
        self._config.last_dir = str(Path(path).parent)
        self._persist()

        self._bus.emit(
            EventType.ROSTER_IMPORTED,
            added=len(self._roster),
            total=len(self._roster),
            skipped=len(result.skipped),
            file=Path(path).name,
        )
        self._bus.emit(EventType.ROSTER_CHANGED, count=len(self._roster))
        return result

    def add_student(self, name: str) -> bool:
        ok = self._roster.add(name)
        if ok:
            self._persist()
            self._bus.emit(EventType.ROSTER_CHANGED, count=len(self._roster))
        return ok

    def remove_student(self, name: str) -> bool:
        ok = self._roster.remove(name)
        if ok:
            self._persist()
            self._bus.emit(EventType.ROSTER_CHANGED, count=len(self._roster))
        return ok

    def clear_roster(self) -> None:
        self._roster.clear()
        self._persist()
        self._bus.emit(EventType.ROSTER_CHANGED, count=0)

    def export_roster(self, path: str) -> bool:
        try:
            self._parser.export_names(self._roster.names(), path)
        except OSError as exc:
            self._bus.emit(EventType.ERROR, message=f"导出失败：{exc}")
            return False
        self._bus.emit(EventType.STATUS_MESSAGE, message=f"已导出到 {Path(path).name}")
        return True

    # ── 抽奖 ──────────────────────────────────────────────
    def can_draw(self) -> bool:
        return not self._roster.is_empty()

    def draw_now(self) -> Optional[str]:
        """直接随机抽取一人并记入历史。

        返回中奖者姓名；名单为空时返回 None 并发出错误事件。
        """
        if not self.can_draw():
            self._bus.emit(EventType.ERROR, message="请先在设置里导入学生名单")
            return None

        winner = self._pick_winner()
        if winner is None:
            return None

        record = DrawRecord(name=winner.name)
        self._history.append(record)
        if len(self._history) > MAX_HISTORY:
            self._history = self._history[-MAX_HISTORY:]
        self._remember_winner(winner.name)
        self._persist()

        self._bus.emit(EventType.DRAW_FINISHED, name=winner.name)
        self._bus.emit(EventType.HISTORY_CHANGED, count=len(self._history))
        return winner.name

    def _pick_winner(self) -> Optional[Student]:
        """应用"不重复抽取"规则后选出中奖者。"""
        window = self._config.avoid_repeat_window
        if window <= 0:
            return self._draw_service.draw(self._roster)

        recent = set(self._recent_winners[-window:])
        candidates = [s for s in self._roster if s.name not in recent]
        if not candidates:
            # 全员都抽过了，重置窗口重新开始
            self._recent_winners.clear()
            candidates = list(self._roster.students)
        return self._draw_service.draw_from(candidates)

    def _remember_winner(self, name: str) -> None:
        self._recent_winners.append(name)
        if len(self._recent_winners) > 100:
            self._recent_winners = self._recent_winners[-100:]

    # ── 历史 ──────────────────────────────────────────────
    def clear_history(self) -> None:
        self._history.clear()
        self._recent_winners.clear()
        self._persist()
        self._bus.emit(EventType.HISTORY_CHANGED, count=0)

    # ── 设置 ──────────────────────────────────────────────
    def set_always_on_top(self, value: bool) -> None:
        self._config.always_on_top = bool(value)
        self._persist()

    def set_avoid_repeat_window(self, window: int) -> None:
        self._config.avoid_repeat_window = max(0, int(window))
        self._persist()

    def set_window_size(self, width: int, height: int) -> None:
        """记住用户调整后的窗口大小。

        调用方已做防抖（拖动结束后才调），因此这里直接落盘。
        """
        new_w = max(MIN_WINDOW_W, min(MAX_WINDOW_W, int(width)))
        new_h = max(MIN_WINDOW_H, min(MAX_WINDOW_H, int(height)))
        if (new_w, new_h) == (self._config.window_width, self._config.window_height):
            return
        self._config.window_width = new_w
        self._config.window_height = new_h
        self._persist()

    def shutdown(self) -> None:
        """退出前落盘。"""
        self._persist()

    # ── 内部 ──────────────────────────────────────────────
    def _persist(self) -> None:
        self._config.names = self._roster.names()
        self._config.history = list(self._history)
        self._config_store.save(self._config)
