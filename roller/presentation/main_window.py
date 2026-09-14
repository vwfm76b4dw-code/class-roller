"""主窗口。

    原生标题栏
    ┌──────────────────────────────┐
    │                              │
    │           姓名结果            │
    │                              │
    └──────────────────────────────┘
    [      抽 奖      ] [ 设置 ]
       20 名学生，已抽 3 次

要点：
- 所有间距取自 theme 的 SPACE_* 刻度，不写字面量
- 窗口尺寸按 DPI 以**逻辑单位**持久化（见 dpi.py），高 DPI 下不会循环放大
- 窗口位置与尺寸一律钳制到所在显示器工作区，不越界、不盖任务栏
- 背景效果（不透明 / 半透明 / 液态玻璃）由 Backdrop 处理并自动降级
- 动画只做服务于功能的反馈（结果揭示、按压），并尊重系统"减少动态效果"
"""

from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from roller.application.app_controller import AppController
from roller.application.events import Event, EventType
from roller.presentation.animations import Animator
from roller.presentation.dialogs.settings_dialog import SettingsDialog
from roller.presentation.dpi import (
    DEFAULT_H,
    DEFAULT_W,
    sanitize_size,
    to_logical,
    to_physical,
    window_scaling_of,
)
from roller.presentation.resources import apply_app_icon
from roller.presentation.theme import (
    BORDER_W,
    RADIUS_GLASS,
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
    Backdrop,
    TopmostKeeper,
    apply_modern_frame,
    clamp_to_work_area,
    work_area_for_point,
)

# 逻辑单位下的最小尺寸
MIN_LOGIC_W = 320
MIN_LOGIC_H = 260


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
        self._backdrop: Optional[Backdrop] = None
        self._animator: Optional[Animator] = None
        self._size_job: Optional[str] = None

        # 用户是否主动隐藏（用于区分"意外隐藏"）
        self._user_hid = False
        self._guard_job: Optional[str] = None
        self._guard_until = 0.0

        self._setup_window()
        self._build()
        self._subscribe_events()
        self._restore_state()

    # ── 尺寸换算（逻辑 ↔ 物理）────────────────────────────
    @property
    def _scaling(self) -> float:
        return window_scaling_of(self)

    def _apply_logical_geometry(self, w: int, h: int, x=None, y=None) -> None:
        """按逻辑尺寸设置窗口几何并钳制到工作区。

        CTk 会把逻辑尺寸乘上缩放系数，所以传逻辑值即可得到预期的物理大小。
        """
        scaling = self._scaling
        phys_w = to_physical(w, scaling)
        phys_h = to_physical(h, scaling)

        if x is None or y is None:
            area_l, area_t, area_r, area_b = work_area_for_point(None, None)
            x = area_l + (area_r - area_l - phys_w) // 2
            y = area_t + (area_b - area_t - phys_h) // 3

        px, py, pw, ph = clamp_to_work_area(x, y, phys_w, phys_h)
        # 钳制后物理尺寸可能变化，换回逻辑值交给 CTk
        self.geometry(
            f"{to_logical(pw, scaling)}x{to_logical(ph, scaling)}+{px}+{py}"
        )

    # ── 窗口初始化 ────────────────────────────────────────
    def _setup_window(self) -> None:
        from roller import compat

        self.title("课堂抽奖器")
        if not compat.NO_ICON:
            apply_app_icon(self)

        cfg = self._controller.config
        size = sanitize_size(cfg.window_width, cfg.window_height)
        if size is None:
            size = (DEFAULT_W, DEFAULT_H)
        w, h = size

        self.minsize(MIN_LOGIC_W, MIN_LOGIC_H)
        self.resizable(True, True)
        self.configure(fg_color=self._palette.bg_root)

        self._apply_logical_geometry(w, h, cfg.window_x, cfg.window_y)

        self.protocol("WM_DELETE_WINDOW", self._hide_to_tray)
        self.bind("<Configure>", self._on_configure)

        if not compat.NO_DWM:
            apply_modern_frame(
                self,
                caption_color=self._palette.bg_root,
                border_color=self._palette.border_strong,
                text_color=self._palette.text_primary,
            )

        self._backdrop = Backdrop(self)
        self._backdrop.apply(cfg.backdrop)

        self._animator = Animator(self)
        self._animator.set_enabled(cfg.animations)

        if not compat.NO_TOPMOST:
            self._topmost = TopmostKeeper(
                self,
                interval_ms=900,
                aggressive=compat.AGGRESSIVE_TOPMOST,
            )

        self._start_visibility_guard()
        self._restyle_after_backdrop()

    # ── 尺寸变化与保存 ────────────────────────────────────
    def _on_configure(self, event) -> None:
        """尺寸/位置变化时延迟保存，避免拖动过程中频繁写盘。"""
        from roller import compat

        if event.widget is not self or compat.NO_SIZE_MEMORY:
            return
        if self._size_job is not None:
            try:
                self.after_cancel(self._size_job)
            except Exception:
                pass
        self._size_job = self.after(600, self._save_size)

    def _save_size(self) -> None:
        """保存逻辑尺寸与物理位置。

        逻辑尺寸 = 物理像素 ÷ 缩放，下次启动 CTk 乘回去后完全一致，
        因此不会出现每重启放大一圈的问题。
        """
        self._size_job = None
        try:
            if self.state() in ("iconic", "zoomed"):
                return
            phys_w, phys_h = self.winfo_width(), self.winfo_height()
            if phys_w <= 1 or phys_h <= 1:
                return
            px, py, pw, ph = clamp_to_work_area(
                self.winfo_x(), self.winfo_y(), phys_w, phys_h
            )
            scaling = self._scaling
            logic_w = to_logical(pw, scaling)
            logic_h = to_logical(ph, scaling)
            if sanitize_size(logic_w, logic_h) is None:
                return
            self._controller.set_window_size(logic_w, logic_h)
            self._controller.set_window_position(px, py)
        except Exception:
            pass

    # ── 布局 ──────────────────────────────────────────────
    def _build(self) -> None:
        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        # 结果卡下方的投影层：玻璃模式下显示，制造"卡片浮起"的纵深。
        # 与卡片放在同一网格单元、四周各外扩 3px、整体下移 3px。
        self._shadow = ctk.CTkFrame(
            self,
            fg_color=self._palette.bg_root,
            corner_radius=RADIUS_MD,
        )
        self._shadow.grid(
            row=0, column=0, sticky="nsew",
            padx=SPACE_LG - 4, pady=(SPACE_LG + 4, SPACE_SM - 4),
        )
        self._shadow.grid_remove()

        self._display = NameDisplay(self, self._palette)
        self._display.grid(
            row=0, column=0, sticky="nsew",
            padx=SPACE_LG, pady=(SPACE_LG, SPACE_SM),
        )

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
        self._draw_btn.bind("<ButtonPress-1>", self._on_button_press, add="+")
        self._draw_btn.bind("<ButtonRelease-1>", self._on_button_release, add="+")

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

        # 注意：状态文字必须落在不透明底色上。玻璃模式用色键挖空画布，
        # 若文字直接画在画布上，抗锯齿边缘会被一起挖掉、笔画断裂。
        self._status = ctk.CTkLabel(
            self,
            text="",
            font=FONT_SMALL,
            text_color=self._palette.text_muted,
            fg_color=self._palette.bg_root,
            corner_radius=0,
        )
        self._status.grid(row=2, column=0, pady=(0, SPACE_SM))

    # ── 按压反馈 ──────────────────────────────────────────
    def _on_button_press(self, _event) -> None:
        try:
            self._draw_btn.configure(fg_color=self._palette.accent_press)
        except Exception:
            pass

    def _on_button_release(self, _event) -> None:
        try:
            self._draw_btn.configure(fg_color=self._palette.accent)
        except Exception:
            pass

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
        name = event.payload.get("name", "")
        if self._animator is not None:
            self._display.reveal(name, self._animator)
        else:
            self._display.show_winner(name)

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
            return
        text = f"{count} 名学生，已抽 {history} 次"
        if self._controller.config.fair_mode:
            text += " · 一轮不重复"
        self._status.configure(text=text, text_color=self._palette.text_muted)

    def _flash_status(self, message: str, color: str) -> None:
        self._status.configure(text=message, text_color=color)
        self.after(2600, self._update_status)

    # ── 外观 ──────────────────────────────────────────────
    def _restyle_after_backdrop(self) -> None:
        """按当前背景模式刷新画布、卡片表面与标题栏。

        玻璃模式下画布用透明色键（被系统挖空 → 露出模糊背景），
        内容卡片保持不透明浮在上面，形成"浮在磨砂玻璃上的卡片"。
        卡片四周的间距就是透出背景的区域。
        """
        if self._backdrop is None:
            return
        mode = self._backdrop.mode
        glass = mode == Backdrop.GLASS
        soft = mode != Backdrop.OPAQUE

        canvas = self._palette.bg_glass if soft else self._palette.bg_root
        card = self._palette.bg_card_glass if soft else self._palette.bg_card
        # 玻璃模式下卡片带白色高光边，模拟玻璃厚度与边缘反光
        edge = self._palette.glass_edge if glass else self._palette.border
        edge_width = 2 if glass else BORDER_W

        try:
            self.configure(fg_color=canvas)
            self._status.configure(fg_color=canvas)
            # 投影层仅在玻璃模式显示
            if glass:
                self._shadow.configure(
                    fg_color=self._palette.glass_shadow,
                    corner_radius=RADIUS_GLASS,
                )
                self._shadow.grid()
                self._shadow.lower(self._display)
            else:
                self._shadow.grid_remove()
            self._display.apply_surface(
                card, glass=glass, border_color=edge, border_width=edge_width
            )
            self._settings_btn.configure(
                fg_color=card if glass else self._palette.bg_elevated,
                border_color=edge if glass else self._palette.border_strong,
            )
            apply_modern_frame(
                self,
                caption_color=canvas,
                border_color=self._palette.glass_shadow if glass
                else self._palette.border_strong,
                text_color=self._palette.text_primary,
            )
        except Exception:
            pass

    # ── 可见性守护 ────────────────────────────────────────
    def _start_visibility_guard(self) -> None:
        """启动后一段时间防止窗口被意外隐藏（外部程序干扰的兜底）。"""
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
        """设置里改了置顶/外观/动画后立即生效。"""
        self._update_status()
        cfg = self._controller.config

        if self._topmost is not None:
            self._topmost.set_enabled(cfg.always_on_top)

        if self._animator is not None:
            self._animator.set_enabled(cfg.animations)

        if self._backdrop is not None:
            self._backdrop.apply(cfg.backdrop)

        self._restyle_after_backdrop()

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
        if self._animator is not None:
            self._animator.cancel_all()
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
