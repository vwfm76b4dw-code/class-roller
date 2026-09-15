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
from roller.domain.fair_bag import FairBag, rebuild_from_history
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

        # 公平抽取袋：优先用配置里保存的状态；旧配置没有则从历史重建
        self._fair_bag = FairBag.from_dict(self._config.fair_bag_state)
        if not self._fair_bag.remaining and not self._config.fair_bag_state:
            self._fair_bag = rebuild_from_history(
                self._roster.names(), [r.name for r in self._history]
            )

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

        self._sync_fair_bag()
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

        self._sync_fair_bag()
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
            self._sync_fair_bag()
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
        self._fair_bag = FairBag()
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

        if self._config.fair_mode:
            # 用显式维护的抽取袋，而不是从历史反推"本轮还剩谁"。
            # 反推在轮次边界有歧义：39 人名单、39 条历史与 40 条历史都会
            # 被判定为"又完成一轮"，导致新一轮刚开始就被重置、刚抽过的人
            # 立刻重复（用户实测数据里 10 次内同一人出现两次）。
            name = self._fair_bag.draw(self._draw_service.rng, self._roster.names())
            winner = None
            if name is not None:
                for stu in self._roster.students:
                    if stu.name == name:
                        winner = stu
                        break
        else:
            winner = self._draw_service.draw(self._roster)
        if winner is None:
            return None

        record = DrawRecord(name=winner.name)
        self._history.append(record)
        if len(self._history) > MAX_HISTORY:
            self._history = self._history[-MAX_HISTORY:]
        self._persist()

        self._bus.emit(EventType.DRAW_FINISHED, name=winner.name)
        self._bus.emit(EventType.HISTORY_CHANGED, count=len(self._history))
        return winner.name

    # ── 历史 ──────────────────────────────────────────────
    def clear_history(self) -> None:
        self._history.clear()
        self._fair_bag = FairBag()          # 袋子一并重置
        self._persist()
        self._bus.emit(EventType.HISTORY_CHANGED, count=0)

    # ── 设置 ──────────────────────────────────────────────
    def set_always_on_top(self, value: bool) -> None:
        self._config.always_on_top = bool(value)
        self._persist()

    def set_backdrop(self, mode: str) -> None:
        """背景效果：opaque / translucent / glass。"""
        self._config.backdrop = str(mode)
        self._persist()

    def set_animations(self, enabled: bool) -> None:
        """界面动画开关。"""
        self._config.animations = bool(enabled)
        self._persist()

    def set_glass_strength(self, value: int) -> None:
        """玻璃强度百分比（60-160）。"""
        self._config.glass_strength = max(60, min(160, int(value)))
        self._persist()

    def _sync_fair_bag(self) -> None:
        """名单变动后让抽取袋与名单一致（剔除已移除者、补进新增者）。"""
        try:
            self._fair_bag.sync(self._roster.names())
        except Exception:
            pass

    def set_fair_mode(self, enabled: bool) -> None:
        """公平模式：本轮所有人被抽过之前不重复（默认开）。"""
        self._config.fair_mode = bool(enabled)
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

    def set_window_position(self, x: int, y: int) -> None:
        """记住窗口位置；坐标异常（如 -32000 最小化残留）时忽略。"""
        try:
            x, y = int(x), int(y)
        except (TypeError, ValueError):
            return
        if x < -8 or y < -8 or x > 99999 or y > 99999:
            return
        if (x, y) == (self._config.window_x, self._config.window_y):
            return
        self._config.window_x = x
        self._config.window_y = y
        self._persist()

    def shutdown(self) -> None:
        """退出前落盘。"""
        self._persist()

    # ── 内部 ──────────────────────────────────────────────
    def _persist(self) -> None:
        self._config.names = self._roster.names()
        self._config.history = list(self._history)
        self._config.fair_bag_state = self._fair_bag.to_dict()
        self._config_store.save(self._config)
