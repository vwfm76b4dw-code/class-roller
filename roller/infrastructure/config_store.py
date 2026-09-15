"""配置持久化。

支持两种模式：
- **便携模式**：exe 同目录下存在 config.json 或该目录可写时，配置存在程序旁边，
  用户可以随时找到、编辑、随程序一起拷走。
- **用户模式**：程序目录只读（如装在 Program Files）时，退回 %APPDATA%\\ClassRoller。

首次启动若便携目录可写，会在那里建配置；之后一直沿用同一位置。
"""

from __future__ import annotations

import json
import os
import shutil
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import List, Optional

from roller.domain.models import DrawRecord

APP_DIR_NAME = "ClassRoller"
CONFIG_FILE_NAME = "config.json"
MAX_HISTORY = 200

# 窗口尺寸约束（与 MainWindow 的 minsize 保持一致）
MIN_WINDOW_W, MIN_WINDOW_H = 220, 170
MAX_WINDOW_W, MAX_WINDOW_H = 4000, 3000


def app_dir() -> Path:
    """程序所在目录（打包后是 exe 目录，开发时是项目根）。"""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent.parent.parent


def user_dir() -> Path:
    """用户配置目录：%APPDATA%\\ClassRoller。"""
    base = os.environ.get("APPDATA")
    if base:
        return Path(base) / APP_DIR_NAME
    return Path.home() / f".{APP_DIR_NAME.lower()}"


def _is_writable(directory: Path) -> bool:
    try:
        directory.mkdir(parents=True, exist_ok=True)
        probe = directory / ".write_test"
        probe.write_text("", encoding="utf-8")
        probe.unlink()
        return True
    except OSError:
        return False


def resolve_config_path() -> Path:
    """决定配置文件的落点，并在必要时迁移旧位置的数据。

    优先级：
    1. CLASS_ROLLER_CONFIG 环境变量指定 → 用它
    2. 便携目录已有 config.json → 用它（用户已在此维护数据）
    3. 便携目录可写 → 用它（首次启动即建立便携配置）
    4. 否则 → %APPDATA%（程序装在只读位置时）

    升级场景：v2 把配置存在 %APPDATA%，若用户升级到便携版，
    这里会把旧配置搬到程序目录，避免名单和历史"消失"。
    """
    override = os.environ.get("CLASS_ROLLER_CONFIG")
    if override:
        return Path(override)

    portable = app_dir() / CONFIG_FILE_NAME
    if portable.exists():
        return portable

    if _is_writable(app_dir()):
        _migrate_legacy_config(portable)
        return portable

    return user_dir() / CONFIG_FILE_NAME


def _migrate_legacy_config(target: Path) -> None:
    """把 %APPDATA% 里的旧配置一次性搬到便携位置。

    仅在目标不存在时执行；失败不影响启动（最坏情况是用户重新导一次名单）。
    """
    legacy = user_dir() / CONFIG_FILE_NAME
    if not legacy.exists() or target.exists():
        return
    try:
        shutil.copy2(legacy, target)
        backup = legacy.with_suffix(".migrated.json")
        shutil.move(str(legacy), str(backup))
    except OSError:
        # 迁移失败就继续用旧位置，不阻断启动
        pass


@dataclass
class AppConfig:
    """全部可持久化的应用状态。"""

    names: List[str] = field(default_factory=list)
    history: List[DrawRecord] = field(default_factory=list)
    last_dir: str = ""
    # 课堂场景下默认置顶，投影时不会被其他窗口盖住
    always_on_top: bool = True
    # 公平模式（可选，默认关闭）：一轮之内不重复点名。
    # 默认关闭意味着纯均匀随机——每次独立抽取，每个人被抽中的概率
    # 严格相等（1/N），与名单顺序、位置、历史都无关。
    fair_mode: bool = False
    avoid_repeat_window: int = 0
    window_width: int = 400
    window_height: int = 430
    window_x: int = -1   # -1 = 未记录，居中显示
    window_y: int = -1
    # 背景效果：opaque / translucent / glass
    backdrop: str = "opaque"
    # 界面动画开关（另受系统"减少动态效果"约束）
    animations: bool = True
    # 玻璃强度百分比（60-160），整体缩放模糊与饱和度
    glass_strength: int = 100
    version: int = 4

    def to_dict(self) -> dict:
        return {
            "names": list(self.names),
            "history": [r.to_dict() for r in self.history],
            "last_dir": self.last_dir,
            "always_on_top": self.always_on_top,
            "fair_mode": self.fair_mode,
            "avoid_repeat_window": self.avoid_repeat_window,
            "window_width": self.window_width,
            "window_height": self.window_height,
            "window_x": self.window_x,
            "window_y": self.window_y,
            "backdrop": self.backdrop,
            "animations": self.animations,
            "glass_strength": self.glass_strength,
            "version": self.version,
        }

    @classmethod
    def from_dict(cls, raw: dict) -> "AppConfig":
        if not isinstance(raw, dict):
            return cls()

        names = raw.get("names") or []
        if not isinstance(names, list):
            names = []

        history_raw = raw.get("history") or []
        history: List[DrawRecord] = []
        if isinstance(history_raw, list):
            for item in history_raw:
                if isinstance(item, dict):
                    record = DrawRecord.from_dict(item)
                    if record.name:
                        history.append(record)

        def _choice(value, allowed, fallback: str) -> str:
            text = str(value).strip().lower() if value is not None else ""
            return text if text in allowed else fallback

        def _int(key: str, fallback: int, lo: int, hi: int) -> int:
            try:
                value = int(raw.get(key, fallback))
            except (TypeError, ValueError):
                value = fallback
            return max(lo, min(hi, value))

        return cls(
            names=[str(n) for n in names if str(n).strip()],
            history=history[-MAX_HISTORY:],
            last_dir=str(raw.get("last_dir") or ""),
            always_on_top=bool(raw.get("always_on_top", True)),
            fair_mode=bool(raw.get("fair_mode", False)),
            avoid_repeat_window=_int("avoid_repeat_window", 0, 0, 999),
            window_width=_int("window_width", 400, MIN_WINDOW_W, MAX_WINDOW_W),
            window_height=_int("window_height", 430, MIN_WINDOW_H, MAX_WINDOW_H),
            window_x=_int("window_x", -1, -1, 999999),
            window_y=_int("window_y", -1, -1, 999999),
            backdrop=_choice(raw.get("backdrop"), ("opaque", "translucent", "glass"), "opaque"),
            animations=bool(raw.get("animations", True)),
            glass_strength=_int("glass_strength", 100, 60, 160),
        )


class ConfigStore:
    """负责读写配置文件。"""

    def __init__(self, path: Optional[Path] = None) -> None:
        self._path = Path(path) if path else resolve_config_path()

    @property
    def path(self) -> Path:
        return self._path

    @property
    def is_portable(self) -> bool:
        """配置是否与程序放在一起（便携模式）。"""
        try:
            return self._path.parent.resolve() == app_dir().resolve()
        except OSError:
            return False

    def load(self) -> AppConfig:
        if not self._path.exists():
            return AppConfig()
        try:
            raw = json.loads(self._path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            # 配置损坏时不让程序崩溃，直接回到默认值
            return AppConfig()
        return AppConfig.from_dict(raw)

    def save(self, config: AppConfig) -> None:
        try:
            self._path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self._path.with_suffix(".tmp")
            tmp.write_text(
                json.dumps(config.to_dict(), ensure_ascii=False, indent=2),
                encoding="utf-8",
            )
            os.replace(tmp, self._path)
        except OSError:
            # 保存失败不应影响正在进行的抽奖
            pass
