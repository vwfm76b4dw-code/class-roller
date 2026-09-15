"""JS ↔ Python 桥接层。

前端只做呈现与交互；抽奖、名单解析、配置持久化仍由既有分层代码负责
（domain / infrastructure / application 三层原样复用，不因换界面而改动）。

pywebview 会把本类中不以 _ 开头的方法暴露成 window.pywebview.api.xxx。
所有方法都必须返回可 JSON 序列化的值，且不应抛异常——异常会让前端
静默失败，因此统一在这里兜住并返回结构化错误。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path
from typing import Any, Dict, List, Optional

from roller.application.app_controller import AppController

# 玻璃强度范围（百分比）
GLASS_MIN, GLASS_MAX = 60, 160


class WebApi:
    """暴露给前端的接口。"""

    def __init__(self, controller: AppController, window=None) -> None:
        self._c = controller
        self._window = window
        self._on_close = None
        self._on_backdrop = None

    def attach_window(self, window) -> None:
        self._window = window

    def set_close_handler(self, fn) -> None:
        self._on_close = fn

    # ── 基础信息 ──────────────────────────────────────────
    def overview(self) -> Dict[str, Any]:
        """名单概览：供前端判断能否抽奖并取滚动用的名字池。"""
        try:
            names = self._c.roster.names()
            return {"count": len(names), "names": names}
        except Exception as exc:
            return {"count": 0, "names": [], "error": str(exc)}

    def status(self) -> str:
        try:
            count = self._c.student_count
            drawn = len(self._c.history)
            if count == 0:
                return "尚未导入名单"
            text = f"{count} 名学生 · 已抽 {drawn} 次"
            if self._c.config.fair_mode:
                text += " · 一轮不重复"
            return text
        except Exception:
            return ""

    def roster_names(self) -> List[str]:
        try:
            return self._c.roster.names()
        except Exception:
            return []

    def history(self) -> List[Dict[str, str]]:
        """最近记录在前，便于直接渲染。"""
        try:
            records = self._c.history
            out = []
            for r in reversed(records[-200:]):
                out.append({"name": r.name, "time": r.display_time()})
            return out
        except Exception:
            return []

    def settings(self) -> Dict[str, Any]:
        try:
            cfg = self._c.config
            store = getattr(self._c, "_config_store", None)
            return {
                "always_on_top": cfg.always_on_top,
                "fair_mode": cfg.fair_mode,
                "animations": cfg.animations,
                "config_path": str(store.path) if store is not None else "",
                "portable": bool(getattr(store, "is_portable", False)),
            }
        except Exception as exc:
            return {"error": str(exc)}

    # ── 抽奖 ──────────────────────────────────────────────
    def draw(self) -> Optional[str]:
        return self._c.draw_now()

    # ── 名单管理 ──────────────────────────────────────────
    def import_roster(self) -> Dict[str, Any]:
        """弹出系统文件对话框导入名单。"""
        try:
            path = self._pick_open_file()
            if not path:
                return {"cancelled": True}
            result = self._c.import_roster(path)
            if result.count == 0:
                return {"error": "文件里没找到有效姓名"}
            return {"count": result.count, "total": self._c.student_count}
        except Exception as exc:
            return {"error": f"导入失败：{exc}"}

    def add_students(self, text: str) -> Dict[str, Any]:
        try:
            added = 0
            for part in str(text).replace("，", ",").replace("、", ",").split(","):
                if self._c.add_student(part):
                    added += 1
            return {"added": added}
        except Exception as exc:
            return {"added": 0, "error": str(exc)}

    def export_roster(self) -> Dict[str, Any]:
        try:
            if self._c.roster.is_empty():
                return {"error": "名单为空"}
            path = self._pick_save_file()
            if not path:
                return {"cancelled": True}
            ok = self._c.export_roster(path)
            return {"ok": True, "path": Path(path).name} if ok else {"error": "导出失败"}
        except Exception as exc:
            return {"error": f"导出失败：{exc}"}

    def clear_roster(self) -> bool:
        try:
            self._c.clear_roster()
            return True
        except Exception:
            return False

    def clear_history(self) -> bool:
        try:
            self._c.clear_history()
            return True
        except Exception:
            return False

    def open_config_dir(self) -> bool:
        try:
            store = getattr(self._c, "_config_store", None)
            if store is None:
                return False
            path = store.path
            if not path.exists():
                self._c.shutdown()
            if sys.platform == "win32":
                if path.exists():
                    subprocess.Popen(["explorer", "/select,", str(path)])
                else:
                    subprocess.Popen(["explorer", str(path.parent)])
            else:
                subprocess.Popen(["xdg-open", str(path.parent)])
            return True
        except Exception:
            return False

    # ── 设置 ──────────────────────────────────────────────
    def toggle_topmost(self) -> bool:
        try:
            current = bool(self._c.config.always_on_top)
            self._c.set_always_on_top(not current)
            self._apply_topmost(not current)
            return not current
        except Exception:
            return False

    def set_topmost(self, value: bool) -> bool:
        try:
            self._c.set_always_on_top(bool(value))
            self._apply_topmost(bool(value))
            return bool(value)
        except Exception:
            return False

    def set_fair_mode(self, value: bool) -> bool:
        try:
            self._c.set_fair_mode(bool(value))
            return True
        except Exception:
            return False

    def set_animations(self, value: bool) -> bool:
        try:
            self._c.set_animations(bool(value))
            return True
        except Exception:
            return False

    def minimize(self) -> bool:
        """最小化窗口；没有窗口对象时如实返回 False。"""
        if self._window is None:
            return False
        try:
            self._window.minimize()
            return True
        except Exception:
            return False

    def close(self) -> bool:
        """关闭请求；没有窗口对象时如实返回 False。"""
        if self._on_close is None and self._window is None:
            return False
        try:
            if self._on_close is not None:
                self._on_close()
            else:
                self._window.destroy()
            return True
        except Exception:
            return False

    # ── 内部 ──────────────────────────────────────────────
    def _apply_topmost(self, value: bool) -> None:
        if self._window is None:
            return
        try:
            self._window.on_top = bool(value)
        except Exception:
            pass

    def _pick_open_file(self) -> Optional[str]:
        """打开系统文件选择框（用独立 Tk 根窗口，避免影响主窗口）。"""
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            return filedialog.askopenfilename(
                title="选择名单文件",
                filetypes=[("文本文件", "*.txt"), ("CSV 文件", "*.csv"),
                           ("所有文件", "*.*")],
                initialdir=self._c.config.last_dir or None,
            )
        finally:
            root.destroy()

    def _pick_save_file(self) -> Optional[str]:
        import tkinter as tk
        from tkinter import filedialog

        root = tk.Tk()
        root.withdraw()
        root.attributes("-topmost", True)
        try:
            return filedialog.asksaveasfilename(
                title="导出名单",
                defaultextension=".txt",
                filetypes=[("文本文件", "*.txt")],
                initialfile="学生名单.txt",
            )
        finally:
            root.destroy()
