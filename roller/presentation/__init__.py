"""表现层。

v4.5 起改用 WebView2 渲染：
- web/          前端界面（HTML/CSS/JS），负责呈现与动画
- api.py        JS ↔ Python 桥接（抽奖、名单、配置）
- web_window.py 窗口层（透明无边框、置顶、托盘、几何持久化）
- window_utils.py 工作区与多显示器工具
- tray.py       系统托盘
- resources.py  资源路径解析
"""

__all__ = [
    "api",
    "web_window",
    "window_utils",
    "tray",
    "resources",
]
