"""设置弹窗：名单管理、历史、偏好。

主界面只保留抽奖和设置入口，其余功能都在这里。
所有间距取自 theme 的 SPACE_* / HEIGHT_* 刻度。
"""

from __future__ import annotations

from typing import Callable, Optional

import customtkinter as ctk

from roller.application.app_controller import AppController
from roller.presentation.resources import apply_app_icon
from roller.presentation.theme import (
    BORDER_W,
    FONT_BODY,
    FONT_SMALL,
    HEIGHT_BUTTON_MD,
    HEIGHT_BUTTON_SM,
    RADIUS_LG,
    RADIUS_MD,
    RADIUS_SM,
    SPACE_LG,
    SPACE_MD,
    SPACE_SM,
    SPACE_TIGHT,
    SPACE_XS,
    SPACE_XXS,
    Palette,
)
from roller.presentation.window_utils import apply_modern_frame

# 小按钮统一宽度，保证工具栏视觉整齐
SMALL_BTN_W = 84


class SettingsDialog(ctk.CTkToplevel):
    """设置窗口：三个标签页。"""

    def __init__(
        self,
        master,
        controller: AppController,
        palette: Palette,
        on_changed: Optional[Callable[[], None]] = None,
    ) -> None:
        super().__init__(master)
        self._controller = controller
        self._palette = palette
        self._on_changed = on_changed

        # 与主窗口背景模式保持一致：玻璃模式沿用同一冷调画布与卡片色。
        # 用 dataclasses.replace 只改需要的字段，避免逐个列举导致漏项。
        from dataclasses import replace

        from roller.presentation.window_utils import Backdrop

        if getattr(controller.config, "backdrop", "opaque") == Backdrop.GLASS:
            palette = replace(
                palette,
                bg_root=palette.bg_glass,
                bg_card=palette.bg_card_glass,
                bg_elevated=palette.bg_inner_glass,
            )
        self.title("设置")
        # 逻辑尺寸（CTk 会按 DPI 乘回去），小屏也放得下
        self.geometry("540x620")
        self.minsize(460, 480)
        self.resizable(True, True)
        self.configure(fg_color=palette.bg_root)
        self.transient(master)
        apply_app_icon(self)

        self.grid_columnconfigure(0, weight=1)
        self.grid_rowconfigure(0, weight=1)

        self._build()
        self._refresh_roster()
        self._refresh_history()

        self._position_beside(master)
        self.bind("<Escape>", lambda _e: self._close())
        self.after(50, self._activate)

    # ── 骨架 ──────────────────────────────────────────────
    def _build(self) -> None:
        self._tabs = ctk.CTkTabview(
            self,
            fg_color=self._palette.bg_card,
            segmented_button_selected_color=self._palette.accent,
            segmented_button_selected_hover_color=self._palette.accent_hover,
            segmented_button_unselected_color=self._palette.bg_elevated,
            segmented_button_unselected_hover_color=self._palette.bg_hover,
            text_color=self._palette.text_primary,
            corner_radius=RADIUS_MD,
            border_width=BORDER_W,
            border_color=self._palette.border,
        )
        self._tabs.grid(
            row=0,
            column=0,
            sticky="nsew",
            padx=SPACE_MD,
            pady=(SPACE_MD, SPACE_SM),
        )

        self._build_roster_tab(self._tabs.add("名单"))
        self._build_history_tab(self._tabs.add("历史"))
        self._build_prefs_tab(self._tabs.add("偏好"))
        self._build_appearance_tab(self._tabs.add("外观"))

        ctk.CTkButton(
            self,
            text="完成",
            width=120,
            height=HEIGHT_BUTTON_MD,
            corner_radius=RADIUS_SM,
            font=FONT_BODY,
            fg_color=self._palette.accent,
            hover_color=self._palette.accent_hover,
            text_color="#ffffff",
            command=self._close,
        ).grid(row=1, column=0, pady=(0, SPACE_MD))

    # ── 名单页 ────────────────────────────────────────────
    def _build_roster_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        toolbar = ctk.CTkFrame(parent, fg_color="transparent")
        toolbar.grid(row=0, column=0, sticky="ew", pady=(SPACE_SM, SPACE_MD))

        self._small_button(
            toolbar, "导入文件", self._import_file, primary=True
        ).pack(side="left", padx=(0, SPACE_TIGHT))
        self._small_button(toolbar, "添加", self._add_manual).pack(
            side="left", padx=SPACE_TIGHT
        )
        self._small_button(toolbar, "导出", self._export_file).pack(
            side="left", padx=SPACE_TIGHT
        )
        self._small_button(toolbar, "清空", self._clear_roster, danger=True).pack(
            side="left", padx=SPACE_TIGHT
        )

        self._roster_box = self._text_area(parent)
        self._roster_box.grid(row=1, column=0, sticky="nsew")
        self._roster_box.configure(state="disabled")

        self._roster_hint = self._hint_label(parent)
        self._roster_hint.grid(row=2, column=0, sticky="ew", pady=(SPACE_SM, 0))

    # ── 历史页 ────────────────────────────────────────────
    def _build_history_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)
        parent.grid_rowconfigure(1, weight=1)

        head = ctk.CTkFrame(parent, fg_color="transparent")
        head.grid(row=0, column=0, sticky="ew", pady=(SPACE_SM, SPACE_MD))

        self._history_hint = ctk.CTkLabel(
            head,
            text="共 0 条记录",
            font=FONT_SMALL,
            text_color=self._palette.text_secondary,
        )
        self._history_hint.pack(side="left")

        self._small_button(
            head, "清空历史", self._clear_history, danger=True
        ).pack(side="right")

        self._history_box = self._text_area(parent)
        self._history_box.grid(row=1, column=0, sticky="nsew")
        self._history_box.configure(state="disabled")

    # ── 偏好页 ────────────────────────────────────────────
    def _build_prefs_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)

        card = ctk.CTkFrame(
            parent,
            fg_color=self._palette.bg_elevated,
            corner_radius=RADIUS_LG,
            border_width=BORDER_W,
            border_color=self._palette.border,
        )
        card.grid(row=0, column=0, sticky="ew", pady=(SPACE_SM, 0))
        card.grid_columnconfigure(0, weight=1)

        # ── 置顶 ──
        row = ctk.CTkFrame(card, fg_color="transparent")
        row.grid(
            row=0, column=0, sticky="ew", padx=SPACE_MD, pady=(SPACE_MD, SPACE_XXS)
        )
        row.grid_columnconfigure(0, weight=1)

        self._row_label(row, "窗口始终置顶").grid(row=0, column=0, sticky="w")

        self._top_switch = ctk.CTkSwitch(
            row,
            text="",
            width=44,
            progress_color=self._palette.accent,
            command=self._toggle_on_top,
        )
        self._top_switch.grid(row=0, column=1, sticky="e")
        if self._controller.config.always_on_top:
            self._top_switch.select()

        self._row_hint(card, "投影、PPT 放映时也不会被其他窗口盖住").grid(
            row=1, column=0, sticky="w", padx=SPACE_MD, pady=(0, SPACE_MD)
        )

        self._divider(card).grid(row=2, column=0, sticky="ew", padx=SPACE_MD)

        # ── 公平抽取 ──
        row2 = ctk.CTkFrame(card, fg_color="transparent")
        row2.grid(
            row=3, column=0, sticky="ew", padx=SPACE_MD, pady=(SPACE_MD, SPACE_XS)
        )
        row2.grid_columnconfigure(0, weight=1)

        self._row_label(row2, "公平抽取").grid(row=0, column=0, sticky="w")

        self._fair_switch = ctk.CTkSwitch(
            row2,
            text="",
            width=44,
            progress_color=self._palette.accent,
            command=self._toggle_fair,
        )
        self._fair_switch.grid(row=0, column=1, sticky="e")
        if self._controller.config.fair_mode:
            self._fair_switch.select()

        self._row_hint(
            card,
            "关闭（默认）：每次独立抽取，概率严格相等\n"
            "开启：一轮之内不重复点名，抽完一轮自动重新开始",
        ).grid(row=4, column=0, sticky="w", padx=SPACE_MD, pady=(0, SPACE_MD))

        # ── 配置文件位置 ──
        self._build_config_card(parent, row=1)

    def _build_config_card(self, parent, row: int) -> None:
        """显示配置文件路径，让用户能找到、编辑、备份它。"""
        card = ctk.CTkFrame(
            parent,
            fg_color=self._palette.bg_elevated,
            corner_radius=RADIUS_LG,
            border_width=BORDER_W,
            border_color=self._palette.border,
        )
        card.grid(row=row, column=0, sticky="ew", pady=(SPACE_MD, 0))
        card.grid_columnconfigure(0, weight=1)

        store = getattr(self._controller, "_config_store", None)
        path = str(store.path) if store is not None else "（未知）"
        portable = bool(getattr(store, "is_portable", False))

        head = ctk.CTkFrame(card, fg_color="transparent")
        head.grid(
            row=0, column=0, sticky="ew", padx=SPACE_MD, pady=(SPACE_MD, SPACE_XS)
        )
        head.grid_columnconfigure(0, weight=1)

        self._row_label(head, "配置文件").grid(row=0, column=0, sticky="w")

        ctk.CTkLabel(
            head,
            text="便携" if portable else "用户目录",
            font=FONT_SMALL,
            text_color=self._palette.accent,
        ).grid(row=0, column=1, sticky="e")

        self._config_path_label = ctk.CTkLabel(
            card,
            text=path,
            font=FONT_SMALL,
            text_color=self._palette.text_secondary,
            anchor="w",
            justify="left",
            wraplength=390,
        )
        self._config_path_label.grid(
            row=1, column=0, sticky="ew", padx=SPACE_MD, pady=(0, SPACE_SM)
        )

        buttons = ctk.CTkFrame(card, fg_color="transparent")
        buttons.grid(row=2, column=0, sticky="w", padx=SPACE_MD, pady=(0, SPACE_MD))

        self._small_button(buttons, "打开所在文件夹", self._open_config_dir).pack(
            side="left"
        )

        self._row_hint(
            card, "名单、历史、窗口设置都存在这个文件里，可以备份或拷到别的电脑。"
        ).grid(row=3, column=0, sticky="w", padx=SPACE_MD, pady=(0, SPACE_MD))

        from roller import __version__

        ctk.CTkLabel(
            parent,
            text=f"课堂抽奖器 v{__version__}",
            font=FONT_SMALL,
            text_color=self._palette.text_muted,
        ).grid(row=row + 1, column=0, sticky="e", pady=(SPACE_SM, 0))


    # ── 外观页 ────────────────────────────────────────────
    def _build_appearance_tab(self, parent) -> None:
        parent.grid_columnconfigure(0, weight=1)

        # 背景效果
        card = ctk.CTkFrame(
            parent,
            fg_color=self._palette.bg_elevated,
            corner_radius=RADIUS_LG,
            border_width=BORDER_W,
            border_color=self._palette.border,
        )
        card.grid(row=0, column=0, sticky="ew", pady=(SPACE_SM, 0))
        card.grid_columnconfigure(0, weight=1)

        self._row_label(card, "窗口背景").grid(
            row=0, column=0, sticky="w", padx=SPACE_MD, pady=(SPACE_MD, SPACE_XS)
        )

        self._backdrop_var = ctk.StringVar(value=self._controller.config.backdrop)
        options = [
            ("opaque", "不透明", "最清晰，兼容性最好"),
            ("translucent", "半透明", "整窗轻微透明，所有系统可用"),
            ("glass", "液态玻璃", "冷调画布 + 浮起的白卡片，带柔和投影"),
        ]
        for index, (value, label, hint) in enumerate(options):
            # 单选按钮一行，说明另起一行缩进对齐——避免右对齐小字被挤断
            radio = ctk.CTkRadioButton(
                card,
                text=label,
                value=value,
                variable=self._backdrop_var,
                font=FONT_BODY,
                text_color=self._palette.text_primary,
                fg_color=self._palette.accent,
                hover_color=self._palette.accent_hover,
                command=self._on_backdrop_change,
            )
            radio.grid(
                row=1 + index * 2, column=0, sticky="w",
                padx=SPACE_MD, pady=(SPACE_TIGHT if index else 0, 0),
            )
            ctk.CTkLabel(
                card,
                text=hint,
                font=FONT_SMALL,
                text_color=self._palette.text_muted,
                anchor="w",
                justify="left",
                wraplength=380,
            ).grid(
                row=2 + index * 2, column=0, sticky="w",
                padx=(SPACE_MD + 24, SPACE_MD),
            )

        ctk.CTkLabel(
            card,
            text="液态玻璃用冷调配色与层次投影表现通透感，不依赖系统模糊，"
                 "因此在各版本 Windows 上观感一致，也不会让文字发虚。",
            font=FONT_SMALL,
            text_color=self._palette.text_muted,
            anchor="w",
            justify="left",
            wraplength=390,
        ).grid(
            row=1 + len(options) * 2, column=0, sticky="w",
            padx=SPACE_MD, pady=(SPACE_SM, SPACE_MD),
        )

        # 动画
        card2 = ctk.CTkFrame(
            parent,
            fg_color=self._palette.bg_elevated,
            corner_radius=RADIUS_LG,
            border_width=BORDER_W,
            border_color=self._palette.border,
        )
        card2.grid(row=1, column=0, sticky="ew", pady=(SPACE_MD, 0))
        card2.grid_columnconfigure(0, weight=1)

        row = ctk.CTkFrame(card2, fg_color="transparent")
        row.grid(row=0, column=0, sticky="ew", padx=SPACE_MD, pady=(SPACE_MD, SPACE_XXS))
        row.grid_columnconfigure(0, weight=1)

        self._row_label(row, "界面动画").grid(row=0, column=0, sticky="w")

        self._anim_switch = ctk.CTkSwitch(
            row,
            text="",
            width=44,
            progress_color=self._palette.accent,
            command=self._toggle_animations,
        )
        self._anim_switch.grid(row=0, column=1, sticky="e")
        if self._controller.config.animations:
            self._anim_switch.select()

        self._row_hint(
            card2, "抽中时的结果揭示与按压反馈；系统开启「减少动态效果」时会自动停用"
        ).grid(row=1, column=0, sticky="w", padx=SPACE_MD, pady=(0, SPACE_MD))

        ctk.CTkLabel(
            parent,
            text="窗口尺寸与位置会按屏幕 DPI 正确换算，换投影/换电脑时不会异常放大，"
                 "也不会越出屏幕。",
            font=FONT_SMALL,
            text_color=self._palette.text_muted,
            anchor="w",
            justify="left",
            wraplength=380,
        ).grid(row=2, column=0, sticky="ew", pady=(SPACE_MD, 0))

    # ── 通用控件构造 ──────────────────────────────────────
    def _text_area(self, master) -> ctk.CTkTextbox:
        return ctk.CTkTextbox(
            master,
            fg_color=self._palette.bg_elevated,
            text_color=self._palette.text_primary,
            font=FONT_SMALL,
            corner_radius=RADIUS_SM,
            border_width=BORDER_W,
            border_color=self._palette.border,
        )

    def _hint_label(self, master) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            master,
            text="",
            font=FONT_SMALL,
            text_color=self._palette.text_muted,
            anchor="w",
        )

    def _row_label(self, master, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            master,
            text=text,
            font=FONT_BODY,
            text_color=self._palette.text_primary,
            anchor="w",
        )

    def _row_hint(self, master, text: str) -> ctk.CTkLabel:
        return ctk.CTkLabel(
            master,
            text=text,
            font=FONT_SMALL,
            text_color=self._palette.text_muted,
            anchor="w",
            justify="left",
            wraplength=390,
        )

    def _divider(self, master) -> ctk.CTkFrame:
        return ctk.CTkFrame(master, height=1, fg_color=self._palette.border)

    def _small_button(
        self,
        master,
        text: str,
        command,
        primary: bool = False,
        danger: bool = False,
    ) -> ctk.CTkButton:
        if primary:
            fg, hover, color, border = (
                self._palette.accent,
                self._palette.accent_hover,
                "#ffffff",
                0,
            )
        elif danger:
            fg, hover, color, border = (
                self._palette.bg_elevated,
                "#f7dede",
                self._palette.danger,
                BORDER_W,
            )
        else:
            fg, hover, color, border = (
                self._palette.bg_elevated,
                self._palette.bg_hover,
                self._palette.text_primary,
                BORDER_W,
            )
        return ctk.CTkButton(
            master,
            text=text,
            width=SMALL_BTN_W,
            height=HEIGHT_BUTTON_SM,
            corner_radius=RADIUS_SM,
            font=FONT_SMALL,
            fg_color=fg,
            hover_color=hover,
            text_color=color,
            border_width=border,
            border_color=self._palette.border_strong,
            command=command,
        )

    # ── 数据刷新 ──────────────────────────────────────────
    def _refresh_roster(self) -> None:
        names = self._controller.roster.names()
        self._roster_box.configure(state="normal")
        self._roster_box.delete("1.0", "end")
        self._roster_box.insert(
            "1.0",
            "\n".join(names) if names else "（名单为空，点击「导入文件」添加）",
        )
        self._roster_box.configure(state="disabled")
        self._roster_hint.configure(
            text=f"共 {len(names)} 名学生", text_color=self._palette.text_muted
        )

    def _refresh_history(self) -> None:
        records = self._controller.history
        self._history_box.configure(state="normal")
        self._history_box.delete("1.0", "end")
        if records:
            lines = [f"{r.display_time()}    {r.name}" for r in reversed(records)]
            self._history_box.insert("1.0", "\n".join(lines))
        else:
            self._history_box.insert("1.0", "（暂无抽奖记录）")
        self._history_box.configure(state="disabled")
        self._history_hint.configure(text=f"共 {len(records)} 条记录")

    def _notify_changed(self) -> None:
        if self._on_changed:
            self._on_changed()

    # ── 操作回调 ──────────────────────────────────────────
    def _import_file(self) -> None:
        from tkinter import filedialog

        path = filedialog.askopenfilename(
            title="选择名单文件",
            filetypes=[
                ("文本文件", "*.txt"),
                ("CSV 文件", "*.csv"),
                ("所有文件", "*.*"),
            ],
            initialdir=self._controller.config.last_dir or None,
            parent=self,
        )
        if not path:
            return

        result = self._controller.import_roster(path)
        self._refresh_roster()
        if result.count:
            self._roster_hint.configure(
                text=f"本次导入 {result.count} 条，名单共 {self._controller.student_count} 人",
                text_color=self._palette.success,
            )
        self._notify_changed()

    def _add_manual(self) -> None:
        from roller.presentation.dialogs.prompts import TextPrompt

        dialog = TextPrompt(
            self, self._palette, "添加学生", "姓名（多个用逗号分隔）"
        )
        if not dialog.result:
            return
        added = 0
        for part in dialog.result.replace("，", ",").replace("、", ",").split(","):
            if self._controller.add_student(part):
                added += 1
        self._refresh_roster()
        self._roster_hint.configure(
            text=f"新增 {added} 人", text_color=self._palette.success
        )
        self._notify_changed()

    def _export_file(self) -> None:
        from tkinter import filedialog

        if self._controller.roster.is_empty():
            self._roster_hint.configure(
                text="名单为空，无需导出", text_color=self._palette.warning
            )
            return

        path = filedialog.asksaveasfilename(
            title="导出名单",
            defaultextension=".txt",
            filetypes=[("文本文件", "*.txt")],
            initialfile="学生名单.txt",
            parent=self,
        )
        if path and self._controller.export_roster(path):
            self._roster_hint.configure(
                text="导出成功", text_color=self._palette.success
            )

    def _clear_roster(self) -> None:
        from roller.presentation.dialogs.prompts import ConfirmDialog

        if self._controller.roster.is_empty():
            return
        dialog = ConfirmDialog(
            self,
            self._palette,
            "清空名单",
            f"确认清空全部 {self._controller.student_count} 名学生？",
        )
        if dialog.confirmed:
            self._controller.clear_roster()
            self._refresh_roster()
            self._notify_changed()

    def _clear_history(self) -> None:
        from roller.presentation.dialogs.prompts import ConfirmDialog

        if not self._controller.history:
            return
        dialog = ConfirmDialog(
            self, self._palette, "清空历史", "确认清空全部抽奖历史？"
        )
        if dialog.confirmed:
            self._controller.clear_history()
            self._refresh_history()

    def _open_config_dir(self) -> None:
        """在文件管理器中定位配置文件。"""
        import subprocess
        import sys

        store = getattr(self._controller, "_config_store", None)
        if store is None:
            return
        path = store.path

        try:
            if sys.platform == "win32":
                # 先确保文件存在，否则 /select 会报错
                if not path.exists():
                    self._controller.shutdown()
                if path.exists():
                    subprocess.Popen(["explorer", "/select,", str(path)])
                else:
                    subprocess.Popen(["explorer", str(path.parent)])
            else:
                subprocess.Popen(["xdg-open", str(path.parent)])
        except Exception:
            pass

    def _toggle_on_top(self) -> None:
        self._controller.set_always_on_top(bool(self._top_switch.get()))
        self._notify_changed()

    def _on_backdrop_change(self) -> None:
        self._controller.set_backdrop(self._backdrop_var.get())
        self._notify_changed()

    def _toggle_animations(self) -> None:
        self._controller.set_animations(bool(self._anim_switch.get()))
        self._notify_changed()

    def _toggle_fair(self) -> None:
        self._controller.set_fair_mode(bool(self._fair_switch.get()))
        self._notify_changed()

    # ── 定位与关闭 ────────────────────────────────────────
    def _position_beside(self, master) -> None:
        """放在主窗口旁边且不越出所在显示器工作区。

        用主窗口所在显示器的工作区（多显示器下各自独立，允许负坐标），
        而不是全局屏幕尺寸——否则副屏/投影场景会被拽回主屏。
        """
        self.update_idletasks()
        try:
            from roller.presentation.window_utils import (
                clamp_to_work_area,
                work_area_for_window,
            )

            area_l, area_t, area_r, area_b = work_area_for_window(master)
            mx, my = master.winfo_rootx(), master.winfo_rooty()
            mw, mh = master.winfo_width(), master.winfo_height()
            w, h = self.winfo_width(), self.winfo_height()
            gap = 12

            # 优先右侧，放不下改左侧，都放不下则与主窗口左对齐
            x = mx + mw + gap
            if x + w > area_r:
                alt = mx - w - gap
                x = alt if alt >= area_l else mx
            y = my

            x, y, w, h = clamp_to_work_area(x, y, w, h)
            self.geometry(f"{w}x{h}+{x}+{y}")
        except Exception:
            pass

    def _activate(self) -> None:
        try:
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

    def _close(self) -> None:
        self.destroy()
