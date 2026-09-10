"""兼容开关。

某些环境下个别机制可能与本机软件冲突（输入法、游戏全屏、杀软的窗口钩子等），
出现异常时可逐项关闭定位问题。日常使用不需要动这些。

通过环境变量启用，例如：
    set CR_NO_TOPMOST=1
    class-roller.exe
"""

from __future__ import annotations

import os


def _flag(name: str) -> bool:
    return os.environ.get(name, "").strip().lower() in ("1", "true", "yes", "on")


# 关闭"窗口置顶保持器"（不再周期性抢 z 序）
NO_TOPMOST = _flag("CR_NO_TOPMOST")
# 关闭 DWM 圆角与标题栏着色
NO_DWM = _flag("CR_NO_DWM")
# 不设置窗口/任务栏图标
NO_ICON = _flag("CR_NO_ICON")
# 不创建托盘图标
NO_TRAY = _flag("CR_NO_TRAY")
# 关闭"关闭窗口即缩到托盘"，改为直接退出
NO_TRAY_ON_CLOSE = _flag("CR_NO_TRAY_ON_CLOSE")
# 不记忆窗口尺寸（避免频繁写配置文件）
NO_SIZE_MEMORY = _flag("CR_NO_SIZE_MEMORY")
# 强力置顶：周期性抢 z 序，用于压制 PPT 放映窗口。
# 默认关闭——它需要持续调用 Win32 API，个别环境下会干扰窗口消息，
# 导致窗口异常收到关闭请求。仅在确实需要压过 PPT 时开启。
AGGRESSIVE_TOPMOST = _flag("CR_AGGRESSIVE_TOPMOST")

# 是否启用了任一兼容开关
ANY_ENABLED = any(
    [
        NO_TOPMOST,
        NO_DWM,
        NO_ICON,
        NO_TRAY,
        NO_TRAY_ON_CLOSE,
        NO_SIZE_MEMORY,
        AGGRESSIVE_TOPMOST,
    ]
)


def describe() -> str:
    """返回已启用的开关列表，便于日志记录。"""
    active = []
    if NO_TOPMOST:
        active.append("NO_TOPMOST")
    if NO_DWM:
        active.append("NO_DWM")
    if NO_ICON:
        active.append("NO_ICON")
    if NO_TRAY:
        active.append("NO_TRAY")
    if NO_TRAY_ON_CLOSE:
        active.append("NO_TRAY_ON_CLOSE")
    if NO_SIZE_MEMORY:
        active.append("NO_SIZE_MEMORY")
    if AGGRESSIVE_TOPMOST:
        active.append("AGGRESSIVE_TOPMOST")
    return ", ".join(active) if active else "(无)"
