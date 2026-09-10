"""姓名显示区。

结果卡是界面的视觉主角：中间大字放姓名，上方一行小字标状态。
抽中时姓名做一次很短的淡入（约 140ms），读起来是"落定"的感觉，
而不是延迟——课堂投影时不能等。
"""

from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from roller.presentation.theme import (
    FONT_BODY,
    FONT_DISPLAY,
    FONT_SMALL,
    RADIUS_LG,
    SPACE_LG,
    SPACE_SM,
    SPACE_XS,
    Palette,
    lerp_color,
)

# 淡入参数
FADE_FRAMES = 7
FADE_INTERVAL_MS = 20


class NameDisplay(ctk.CTkFrame):
    """中央结果卡。"""

    def __init__(self, master, palette: Palette) -> None:
        super().__init__(
            master,
            corner_radius=RADIUS_LG,
            fg_color=palette.bg_card,
            border_width=1,
            border_color=palette.border,
        )
        self._palette = palette
        self._fade_job: Optional[str] = None

        self.grid_columnconfigure(0, weight=1)
        # 上下各留一个弹性行，让内容始终垂直居中
        self.grid_rowconfigure(0, weight=1)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=0)
        self.grid_rowconfigure(3, weight=1)

        # 状态行：色点 + 文字
        self._status_row = ctk.CTkFrame(self, fg_color="transparent")
        self._status_row.grid(row=1, column=0, pady=(0, SPACE_SM))
        self._status_row.grid_columnconfigure(0, weight=1)
        self._status_row.grid_columnconfigure(2, weight=1)

        self._dot = ctk.CTkLabel(
            self._status_row,
            text="●",
            font=(None, 8),
            text_color=palette.text_muted,
            width=10,
        )
        self._dot.grid(row=0, column=1, sticky="e", padx=(0, SPACE_XS))

        self._status = ctk.CTkLabel(
            self._status_row,
            text="",
            font=FONT_SMALL,
            text_color=palette.text_muted,
        )
        self._status.grid(row=0, column=2, sticky="w")

        # 主角：姓名
        self._name = ctk.CTkLabel(
            self,
            text="",
            font=FONT_BODY,
            text_color=palette.text_muted,
        )
        self._name.grid(row=2, column=0, sticky="nsew", padx=SPACE_LG)

    # ── 状态 ──────────────────────────────────────────────
    def _cancel_fade(self) -> None:
        if self._fade_job is not None:
            try:
                self.after_cancel(self._fade_job)
            except Exception:
                pass
            self._fade_job = None

    def _set_status(self, text: str, dot_color: Optional[str] = None) -> None:
        """状态行；没有内容时整行收起，避免留下空占位。"""
        self._status.configure(text=text)
        if text:
            self._status_row.grid()
            self._dot.configure(text_color=dot_color or self._palette.text_muted)
        else:
            self._status_row.grid_remove()

    def show_idle(self, text: str = "准备好了") -> None:
        """等待抽取：只留一行提示，不重复状态文案。"""
        self._cancel_fade()
        self._set_status("")
        self._name.configure(
            text=text,
            font=FONT_BODY,
            text_color=self._palette.text_muted,
        )

    def show_winner(self, name: str) -> None:
        """抽中：大字 + 短暂淡入。"""
        self._cancel_fade()
        self._set_status("抽中", self._palette.accent)
        self._name.configure(text=name, font=FONT_DISPLAY)

        # 从接近底色的浅灰渐入到强调色，制造"落定"感
        start = lerp_color(self._palette.bg_card, self._palette.accent, 0.15)
        self._name.configure(text_color=start)
        self._fade(0, start)

    def _fade(self, frame: int, start: str) -> None:
        if frame > FADE_FRAMES:
            self._fade_job = None
            self._name.configure(text_color=self._palette.accent)
            return
        t = frame / FADE_FRAMES
        # ease-out，开头快、结尾稳
        eased = 1 - (1 - t) ** 2
        color = lerp_color(start, self._palette.accent, eased)
        self._name.configure(text_color=color)
        self._fade_job = self.after(
            FADE_INTERVAL_MS, lambda: self._fade(frame + 1, start)
        )

    def show_empty(self) -> None:
        """还没导入名单。"""
        self._cancel_fade()
        self._set_status("")
        self._name.configure(
            text="还没有名单\n点下方「设置」导入",
            font=FONT_BODY,
            text_color=self._palette.text_muted,
        )

    def show_message(self, text: str, color: Optional[str] = None) -> None:
        self._cancel_fade()
        self._set_status(text, color)
