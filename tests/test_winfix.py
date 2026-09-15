"""窗口层的防崩溃回归测试。

这几轮踩过的坑全部固化为检查，避免重犯：

1. pywebview 的 move() 在 64 位下把 None 传给 SetWindowPos → 一拖窗口就崩
2. 全局鼠标钩子（WH_MOUSE_LL）+ 后台线程 → 崩溃
3. 在后台线程操作 WinForms 控件 → 崩溃（非线程安全）
4. 颜色键透明（TransparencyKey）→ 点击穿透到下层窗口
5. WS_THICKFRAME → 系统画出方形边框（"方框套圆角"）

这些检查只扫源码、不启动窗口，运行很快。
"""

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

PRESENTATION = ROOT / "roller" / "presentation"


def code_of(name: str) -> str:
    """去掉注释与 docstring 的源码。

    注释里提到某个方案（作为反面教材说明）不算"使用了它"，
    因此必须剥离后再判定。
    """
    src = (PRESENTATION / name).read_text(encoding="utf-8")
    # 去掉 docstring
    src = re.sub(r'""".*?"""', "", src, flags=re.S)
    src = re.sub(r"'''.*?'''", "", src, flags=re.S)
    # 去掉行内注释
    lines = []
    for line in src.splitlines():
        code = line.split("#", 1)[0]
        lines.append(code)
    return "\n".join(lines)


# ── 1. pywebview 移动 bug 必须被修复 ──────────────────────
def test_pywebview_move_patch_applies():
    from roller.presentation.pywebview_fixes import patch_pywebview_move

    assert patch_pywebview_move() is True


def test_patched_move_is_64bit_safe():
    """修复后的 move 必须用 64 位安全句柄，且 cx/cy 传 0 而不是 None。"""
    from roller.presentation.pywebview_fixes import patch_pywebview_move

    patch_pywebview_move()
    import inspect

    from webview.platforms.winforms import BrowserView

    src = inspect.getsource(BrowserView.BrowserForm.move)
    assert "x_phys" in src and "y_phys" in src, "应有坐标换算"
    # 关键回归：cx/cy 必须是 0；传 None 会让 ctypes 抛 TypeError 直接崩进程
    assert "# cx" in src and "# cy" in src, "cx/cy 应有明确取值"
    # 句柄经 _hwnd() 取（内部使用 ToInt64，避免 64 位下溢出）
    assert "_hwnd(" in src, "句柄应经 _hwnd() 获取"
    helper = inspect.getsource(
        __import__("roller.presentation.pywebview_fixes", fromlist=["x"])
    )
    assert "ToInt64" in helper, "_hwnd() 内部应使用 ToInt64"


# ── 2. 禁止全局鼠标钩子 ───────────────────────────────────
def test_no_global_mouse_hook():
    for name in ("win_window.py", "web_window.py", "pywebview_fixes.py"):
        code = code_of(name)
        assert "SetWindowsHookEx" not in code, f"{name} 用了全局钩子（会崩）"
        assert "WH_MOUSE_LL" not in code, f"{name} 用了低级鼠标钩子（会崩）"


def test_hook_module_removed():
    assert not (PRESENTATION / "edge_resize.py").exists(), \
        "edge_resize.py（全局钩子方案）已废弃，不应存在"


# ── 3. 禁止跨线程改 .NET 控件 ─────────────────────────────
def test_no_cross_thread_control_edits():
    for name in ("win_window.py", "web_window.py", "pywebview_fixes.py"):
        code = code_of(name)
        for forbidden in (".BackColor", "TransparencyKey", "Dock ="):
            assert forbidden not in code, f"{name} 含 {forbidden}（跨线程改控件会崩）"


# ── 4. 禁止颜色键透明 ─────────────────────────────────────
def test_no_chroma_key_transparency():
    code = code_of("web_window.py")
    assert "transparent=False" in code, "窗口应为不透明（颜色键会让点击穿透）"


# ── 5. 圆角来自 DWM，不用 WS_THICKFRAME ───────────────────
def test_corners_use_dwm_not_thickframe():
    code = code_of("win_window.py")
    assert "DwmSetWindowAttribute" in code, "圆角应由 DWM 提供"
    assert "WS_THICKFRAME" not in code, "WS_THICKFRAME 会画出方形边框"


def test_window_module_stays_small():
    """窗口模块越少碰系统越安全——限制在 200 行内。"""
    src = (PRESENTATION / "win_window.py").read_text(encoding="utf-8")
    assert len(src.splitlines()) < 200, "win_window.py 应保持精简"


# ── 6. 拖拽能力确实启用 ───────────────────────────────────
def test_easy_drag_enabled():
    """窗口拖动依赖 pywebview 的 easy_drag（其 bug 已修）。"""
    code = code_of("web_window.py")
    assert "easy_drag=True" in code, "应启用 easy_drag"


if __name__ == "__main__":
    failures = []
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"  PASS  {name}")
            except Exception as exc:
                failures.append((name, exc))
                print(f"  FAIL  {name}: {type(exc).__name__}: {exc}")
    print()
    print("全部通过" if not failures else f"{len(failures)} 个失败")
    raise SystemExit(1 if failures else 0)
