"""基础设施层：文件、配置、托盘等外部世界的适配器。"""

from roller.infrastructure.config_store import ConfigStore, AppConfig
from roller.infrastructure.roster_parser import RosterParser, ParseResult

__all__ = [
    "ConfigStore",
    "AppConfig",
    "RosterParser",
    "ParseResult",
]
