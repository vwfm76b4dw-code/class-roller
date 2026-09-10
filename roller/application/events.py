"""极简事件总线。

UI 只订阅事件，不直接调用业务逻辑；控制器只发事件，不 import UI。
两边因此可以独立测试。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Callable, Dict, List


class EventType(Enum):
    ROSTER_CHANGED = auto()
    ROSTER_IMPORTED = auto()
    DRAW_FINISHED = auto()
    HISTORY_CHANGED = auto()
    STATUS_MESSAGE = auto()
    ERROR = auto()


@dataclass
class Event:
    type: EventType
    payload: Dict[str, Any] = field(default_factory=dict)


Handler = Callable[[Event], None]


class EventBus:
    """同步事件分发。UI 线程内使用，无需加锁。"""

    def __init__(self) -> None:
        self._handlers: Dict[EventType, List[Handler]] = {}

    def subscribe(self, event_type: EventType, handler: Handler) -> None:
        self._handlers.setdefault(event_type, []).append(handler)

    def unsubscribe(self, event_type: EventType, handler: Handler) -> None:
        handlers = self._handlers.get(event_type)
        if handlers and handler in handlers:
            handlers.remove(handler)

    def emit(self, event_type: EventType, **payload: Any) -> None:
        event = Event(event_type, payload)
        for handler in list(self._handlers.get(event_type, ())):
            try:
                handler(event)
            except Exception:
                # 单个订阅者出错不应中断整条链路
                continue
