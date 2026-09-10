"""模拟一个独立的置顶全屏窗口（类似 PPT 放映）。

独立进程运行，与测试窗口没有 owner 关系——这是关键，
否则 owned window 会被系统强制置于 owner 之上，测不出真实行为。

用法：python tools/fake_topmost_window.py
启动后打印 HWND，然后保持窗口存活直到被关闭。
"""

import ctypes
import sys
import time
import tkinter as tk


def main() -> int:
    root = tk.Tk()
    root.title("模拟PPT放映")
    root.geometry("600x400+80+80")
    root.attributes("-topmost", True)
    root.configure(bg="#202020")

    tk.Label(
        root,
        text="模拟 PPT 放映窗口",
        font=("Microsoft YaHei UI", 20),
        fg="#ffffff",
        bg="#202020",
    ).pack(expand=True)

    root.update_idletasks()
    user32 = ctypes.windll.user32
    hwnd = user32.GetParent(root.winfo_id()) or root.winfo_id()
    print(f"HWND={hwnd}", flush=True)

    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
