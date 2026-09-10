"""轻量输入/确认弹窗。间距与主界面统一取自 theme。"""

from __future__ import annotations

from typing import Optional

import customtkinter as ctk

from roller.presentation.resources import apply_app_icon
from roller.presentation.theme import (
    BORDER_W,
    FONT_BODY,
    FONT_SMALL,
    HEIGHT_BUTTON_SM,
    HEIGHT_INPUT,
    RADIUS_SM,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_TIGHT,
    Palette,
)
from roller.presentation.window_utils import apply_modern_frame

BTN_W = 90


class _BaseDialog(ctk.CTkToplevel):
    """输入/确认弹窗的公共部分。"""

    def __init__(
        self,
        master,
        palette: Palette,
        title: str,
        width: int = 380,
        height: int = 190,
    ) -> None:
        super().__init__(master)
        self._palette = palette

        self.title(title)
        self.geometry(f"{width}x{height}")
        self.resizable(False, False)
        self.configure(fg_color=palette.bg_root)
        self.transient(master)
        apply_app_icon(self)

        self.grid_columnconfigure(0, weight=1)

        self._center_on(master, width, height)
        self.bind("<Escape>", lambda _e: self._cancel())
        self.after(50, self._activate)

    def _center_on(self, master, width: int, height: int) -> None:
        self.update_idletasks()
        try:
            mx, my = master.winfo_rootx(), master.winfo_rooty()
            mw, mh = master.winfo_width(), master.winfo_height()
            x = mx + (mw - width) // 2
            y = my + (mh - height) // 2
            sw, sh = self.winfo_screenwidth(), self.winfo_screenheight()
            x = max(8, min(x, sw - width - 8))
            y = max(8, min(y, sh - height - 48))
            self.geometry(f"{width}x{height}+{x}+{y}")
        except Exception:
            pass

    def _activate(self) -> None:
        try:
            self.grab_set()
            self.focus_force()
            apply_modern_frame(
                self,
                caption_color=self._palette.bg_root,
                border_color=self._palette.border_strong,
                text_color=self._palette.text_primary,
            )
            if getattr(self.master, "_topmost", None) is not None:
                if self.master._topmost.enabled:
                    self.attributes("-topmost", True)
        except Exception:
            pass

    def _cancel(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    def _close(self) -> None:
        try:
            self.grab_release()
        except Exception:
            pass
        self.destroy()

    # ── 通用按钮 ──────────────────────────────────────────
    def _button(self, master, text, command, primary: bool = False, danger=False):
        if primary:
            fg, hover, color = (
                self._palette.accent,
                self._palette.accent_hover,
                "#ffffff",
            )
        elif danger:
            fg, hover, color = (
                self._palette.danger,
                "#a82519",
                "#ffffff",
            )
        else:
            fg, hover, color = (
                self._palette.bg_elevated,
                self._palette.bg_hover,
                self._palette.text_primary,
            )
        return ctk.CTkButton(
            master,
            text=text,
            width=BTN_W,
            height=HEIGHT_BUTTON_SM,
            corner_radius=RADIUS_SM,
            font=FONT_SMALL,
            fg_color=fg,
            hover_color=hover,
            text_color=color,
            border_width=0 if primary or danger else BORDER_W,
            border_color=self._palette.border_strong,
            command=command,
        )


class TextPrompt(_BaseDialog):
    """单行文本输入。结果放在 self.result。"""

    def __init__(
        self,
        master,
        palette: Palette,
        title: str,
        label: str,
    ) -> None:
        self.result: Optional[str] = None
        super().__init__(master, palette, title, width=380, height=200)

        ctk.CTkLabel(
            self,
            text=label,
            font=FONT_SMALL,
            text_color=palette.text_secondary,
            anchor="w",
        ).grid(
            row=0,
            column=0,
            sticky="ew",
            padx=SPACE_LG,
            pady=(SPACE_LG + SPACE_TIGHT, SPACE_SM),
        )

        self._entry = ctk.CTkEntry(
            self,
            height=HEIGHT_INPUT,
            corner_radius=RADIUS_SM,
            fg_color=palette.bg_elevated,
            border_color=palette.border_strong,
            text_color=palette.text_primary,
            font=FONT_BODY,
        )
        self._entry.grid(row=1, column=0, sticky="ew", padx=SPACE_LG)
        self._entry.focus_set()
        self._entry.bind("<Return>", lambda _e: self._ok())

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=2, column=0, pady=SPACE_LG)

        self._button(btns, "取消", self._cancel).pack(side="left", padx=SPACE_TIGHT)
        self._button(btns, "确定", self._ok, primary=True).pack(
            side="left", padx=SPACE_TIGHT
        )

        self.wait_window()

    def _ok(self) -> None:
        self.result = self._entry.get().strip()
        self._close()


class ConfirmDialog(_BaseDialog):
    """确认弹窗。结果放在 self.confirmed。"""

    def __init__(
        self,
        master,
        palette: Palette,
        title: str,
        message: str,
    ) -> None:
        self.confirmed = False
        super().__init__(master, palette, title, width=380, height=200)

        self.grid_rowconfigure(0, weight=1)

        ctk.CTkLabel(
            self,
            text=message,
            font=FONT_BODY,
            text_color=palette.text_primary,
            wraplength=310,
            justify="center",
        ).grid(row=0, column=0, sticky="nsew", pady=(SPACE_LG, 0))

        btns = ctk.CTkFrame(self, fg_color="transparent")
        btns.grid(row=1, column=0, pady=(SPACE_MD, SPACE_LG))

        self._button(btns, "取消", self._cancel).pack(side="left", padx=SPACE_TIGHT)
        self._button(btns, "确认", self._ok, danger=True).pack(
            side="left", padx=SPACE_TIGHT
        )

        self.wait_window()

    def _ok(self) -> None:
        self.confirmed = True
        self._close()
