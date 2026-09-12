"""主窗口。

用系统原生边框（可拖动调整大小、外观与系统一致），叠加 Win11 的圆角
和无缝标题栏配色，让它看起来像系统原生应用。

    原生标题栏
    ┌──────────────────────────────┐
    │                              │
    │           姓名结果            │
    │                              │
    └──────────────────────────────┘
    [      抽 奖      ] [ 设置 ]
       20 名学生，已抽 3 次

所有间距取自 theme 的 SPACE_* 刻度，不在本文件写字面量。
"""

from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from roller.application.app_controller import AppController
from roller.application.events import Event, EventType
from roller.presentation.dialogs.settings_dialog import SettingsDialog
from roller.presentation.resources import apply_app_icon
from roller.presentation.theme import (
    BORDER_W,
    FONT_BODY,
    FONT_BUTTON,
    FONT_SMALL,
    HEIGHT_BUTTON,
    RADIUS_MD,
    SPACE_LG,
    SPACE_SM,
    SPACE_XS,
    Palette,
)
from roller.presentation.widgets.name_display import NameDisplay
from roller.presentation.window_utils import (
    TopmostKeeper,
    apply_modern_frame,
    clamp_to_work_area,
)

MIN_W = 320
MIN_H = 260


class MainWindow(ctk.CTk):
    """应用主窗口。"""

    def __init__(
        self,
        controller: AppController,
        palette: Palette,
        on_hide_to_tray=None,
        on_quit=None,
    ) -> None:
        super().__init__()
        self._controller = controller
        self._palette = palette
        self._on_hide_to_tray = on_hide_to_tray
        self._on_quit = on_quit


        self._settings_open = False
        self._topmost: Optional[TopmostKeeper] = None
        self._size_job: Optional[str] = None
        # 用户是否主动隐藏（缩到托盘）——用于区分"意外隐藏"
        self._user_hid = False
        self._guard_job: Optional[str] = None
        self._guard_until = 0.0

        self._setup_window()
        self._build()
        self._subscribe_events()
        self._restore_state()

    # ── 窗口初始化 ────────────────────────────────────────
    def _setup_window(self) -> None:
        from roller import compat

        self.title("课堂抽奖器")
        if not compat.NO_ICON:
            apply_app_icon(self)

        cfg = self._controller.config
        self.minsize(MIN_W, MIN_H)
        self.resizable(True, True)
        self.configure(fg_color=self._palette.bg_root)

        # 恢复尺寸并钳制到工作区：防止旧配置里被 DPI 放大的尺寸
        # 再次越出屏幕、盖住任务栏（学校投影常见 150% 缩放）
        x, y, w, h = clamp_to_work_area(
            cfg.window_x, cfg.window_y,
            cfg.window_width, cfg.window_height,
        )
        self.geometry(f"{w}x{h}+{x}+{y}")

        # 关闭按钮 → 缩到托盘
        self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        self.bind("<Configure>", self._on_configure)

        # Win11 圆角 + 标题栏与画布同色，视觉上连成一片
        if not compat.NO_DWM:
            apply_modern_frame(
            self,
                caption_color=self._palette.bg_root,
                border_color=self._palette.border_strong,
                text_color=self._palette.text_primary,
            )

        if not compat.NO_TOPMOST:
            self._topmost = TopmostKeeper(
                self,
                interval_ms=900,
                aggressive=compat.AGGRESSIVE_TOPMOST,
            )

        self._start_visibility_guard()




    def _on_configure(self, event) -> None:
        """窗口尺寸变化时延迟保存，避免拖动过程中频繁写盘。"""
        if event.widget is not self:
            return
        from roller import compat
        if compat.NO_SIZE_MEMORY:
            return

        if self._size_job is not None:
            try:
                self.after_cancel(self._size_job)
            except Exception:
                pass
        self._size_job = self.after(600, self._save_size)

    def _save_size(self) -> None:
        self._size_job = None
        try:
            # 跳过最小化和最大化状态，只记忆普通状态的用户尺寸
            if self.state() in ("iconic", "zoomed"):
                return
            x = self.winfo_x()
            y = self.winfo_y()
            width, height = self.winfo_width(), self.winfo_height()
            if width > 1 and height > 1:
                # 保存前钳制到工作区，绝不让越界尺寸进入配置
                x, y, width, height = clamp_to_work_area(x, y, width, height)
                self._controller.set_window_size(width, height)
                self._controller.set_window_position(x, y)
        except Exception:
            pass


    # ── 可见性守护 ────────────────────────────────────────
    def _start_visibility_guard(self) -> None:
        """启动后的一段时间内，防止窗口被意外隐藏。

        实测在个别环境下窗口会在启动几秒后莫名收到关闭请求而缩到托盘
        （原因未定位，疑似与其它抓取窗口的程序冲突）。这里在启动后
        短暂守护：若不是用户主动隐藏，就把窗口拉回来，保证用户总能看到界面。
        """
        import time

        self._guard_until = time.time() + 45.0
        self._schedule_guard()

    def _schedule_guard(self) -> None:
        self._cancel_guard()
        try:
            self._guard_job = self.after(1500, self._check_visibility)
        except Exception:
            self._guard_job = None

    def _cancel_guard(self) -> None:
        if self._guard_job is not None:
            try:
                self.after_cancel(self._guard_job)
            except Exception:
                pass
            self._guard_job = None

    def _check_visibility(self) -> None:
        import time

        self._guard_job = None
        if time.time() > self._guard_until:
            return

        try:
            # 用户主动缩到托盘 / 主动最小化，都不干预
            if not self._user_hid and self.state() == "withdrawn":
                self.deiconify()
                self.lift()
                if self._topmost is not None:
                    self._topmost.refresh()
        except Exception:
            pass

        self._schedule_guard()

    def _stop_visibility_guard(self) -> None:
        self._guard_until = 0.0
        self._cancel_guard()

    # ── 布局 ──────────────────────────────────────────────
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 结果卡
        self._display = NameDisplay(self, self._palette)
        self._display.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=SPACE_LG,
            pady=(SPACE_LG, SPACE_SM),
        )

        # 操作行
        actions = ctk.CTkFrame(self, fg_color="transparent")
        actions.grid(
            row=1, column=0, sticky="ew", padx=SPACE_LG, pady=(0, SPACE_SM)
        )
        actions.grid_columnconfigure(0, weight=1)

        self._draw_btn = ctk.CTkButton(
            actions,
            text="抽 奖",
            height=HEIGHT_BUTTON,
            corner_radius=RADIUS_MD,
            font=FONT_BUTTON,
            fg_color=self._palette.accent,
            hover_color=self._palette.accent_hover,
            text_color="#ffffff",
            command=self._draw,
        )
        self._draw_btn.grid(row=0, column=0, sticky="ew")

        self._settings_btn = ctk.CTkButton(
            actions,
            text="设置",
            width=84,
            height=HEIGHT_BUTTON,
            corner_radius=RADIUS_MD,
            font=FONT_BODY,
            fg_color=self._palette.bg_elevated,
            hover_color=self._palette.bg_hover,
            text_color=self._palette.text_primary,
            border_width=BORDER_W,
            border_color=self._palette.border_strong,
            command=self._open_settings,
        )
        self._settings_btn.grid(row=0, column=1, padx=(SPACE_SM, 0))

        self._status = ctk.CTkLabel(
            self,
            text="",
            font=FONT_SMALL,
            text_color=self._palette.text_muted,
        )
        self._status.grid(row=2, column=0, pady=(0, SPACE_LG - SPACE_XS))

    # ── 事件订阅 ──────────────────────────────────────────
    def _subscribe_events(self) -> None:
        bus = self._controller.bus
        bus.subscribe(EventType.ROSTER_CHANGED, self._on_roster_changed)
        bus.subscribe(EventType.ROSTER_IMPORTED, self._on_roster_imported)
        bus.subscribe(EventType.DRAW_FINISHED, self._on_draw_finished)
        bus.subscribe(EventType.ERROR, self._on_error)
        bus.subscribe(EventType.STATUS_MESSAGE, self._on_status_message)

    def _restore_state(self) -> None:
        pinned = self._controller.config.always_on_top
        if self._topmost is not None:
            self._topmost.set_enabled(pinned)

        if self._controller.roster.is_empty():
            self._display.show_empty()
        else:
            self._display.show_idle()
        self._update_status()

    # ── 抽奖 ──────────────────────────────────────────────
    def _draw(self) -> None:
        """一次点击直接抽取。"""
        self._controller.draw_now()
        self._update_status()

    # ── 事件处理 ──────────────────────────────────────────
    def _on_roster_changed(self, _event: Event) -> None:
        self._update_status()
        if self._controller.roster.is_empty():
            self._display.show_empty()

    def _on_roster_imported(self, event: Event) -> None:
        total = event.payload.get("total", 0)
        self._flash_status(f"已导入，名单共 {total} 人", self._palette.success)

    def _on_draw_finished(self, event: Event) -> None:
        self._display.show_winner(event.payload.get("name", ""))

    def _on_error(self, event: Event) -> None:
        self._flash_status(
            event.payload.get("message", "发生错误"), self._palette.danger
        )

    def _on_status_message(self, event: Event) -> None:
        self._flash_status(event.payload.get("message", ""), self._palette.success)

    # ── 状态条 ────────────────────────────────────────────
    def _update_status(self) -> None:
        count = self._controller.student_count
        history = len(self._controller.history)
        if count == 0:
            self._status.configure(
                text="尚未导入名单，点「设置」导入",
                text_color=self._palette.text_muted,
            )
        else:
            self._status.configure(
                text=f"{count} 名学生，已抽 {history} 次",
                text_color=self._palette.text_muted,
            )

    def _flash_status(self, message: str, color: str) -> None:
        self._status.configure(text=message, text_color=color)
        self.after(2600, self._update_status)

    # ── 窗口行为 ──────────────────────────────────────────
    def _open_settings(self) -> None:
        if self._settings_open:
            return
        self._settings_open = True
        try:
            SettingsDialog(
                self,
                self._controller,
                self._palette,
                on_changed=self._on_settings_changed,
            )
        finally:
            self._settings_open = False
            self._update_status()

    def _on_settings_changed(self) -> None:
        self._update_status()
        pinned = self._controller.config.always_on_top
        if self._topmost is not None:
            self._topmost.set_enabled(pinned)

    def _hide_to_tray(self) -> None:
        from roller import compat

        if compat.NO_TRAY_ON_CLOSE:
            self._quit()
            return
        self._user_hid = True
        self._save_size()
        self.withdraw()
        if self._on_hide_to_tray:
            self._on_hide_to_tray()

    def _quit(self) -> None:
        self._stop_visibility_guard()
        self._save_size()
        if self._topmost is not None:
            self._topmost.stop()
        self._controller.shutdown()
        if self._on_quit:
            self._on_quit()
        else:
            self.destroy()

    # ── 托盘唤出 ──────────────────────────────────────────
    def restore_from_tray(self) -> None:
        self._user_hid = False
        self.deiconify()
        self.lift()
        self.focus_force()
        if self._topmost is not None:
            self._topmost.refresh()
