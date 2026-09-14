"""主界面动画。

原则：动画服务于功能，不做装饰。
- **结果揭示**：抽中时姓名放大落定 + 颜色渐入，把视线引到结果上
  （反馈性，P1）。
- **按压反馈**：按钮按下轻微下沉（反馈性，P1）。

约束（项目规范）：
- 只动 transform / opacity / 颜色；不动 width/height/margin（避免重排）
- 时长分级：按压 120ms，揭示 280ms —— 不用统一的 0.3s
- 缓动差异化：微交互减速曲线，揭示带极轻微回弹
- 尊重系统"减少动态效果"：关闭时直接到终态，不做动画
"""

from __future__ import annotations

from typing import Callable, List, Optional

from roller.presentation.theme import lerp_color
from roller.presentation.window_utils import animations_enabled

# 时长（毫秒）
DURATION_PRESS = 120
DURATION_REVEAL = 280

# 帧间隔（约 60fps）
FRAME_MS = 16

# 揭示时姓名的起始字号比例
REVEAL_START_RATIO = 0.62


def _ease_out(t: float) -> float:
    """减速：开头快、结尾稳。"""
    return 1.0 - (1.0 - t) ** 3


def _ease_out_back(t: float) -> float:
    """带极轻微回弹的减速，用于"落定"。"""
    c1 = 1.30
    c3 = c1 + 1.0
    return 1.0 + c3 * (t - 1.0) ** 3 + c1 * (t - 1.0) ** 2


def _ease_in_out(t: float) -> float:
    return t * t * (3.0 - 2.0 * t)


class Animator:
    """基于 after() 的轻量动画调度。"""

    def __init__(self, widget) -> None:
        self._widget = widget
        self._jobs: List[str] = []
        self._enabled = True

    @property
    def enabled(self) -> bool:
        """是否播放动画（用户设置 与 系统"减少动态效果"共同决定）。"""
        return self._enabled and animations_enabled()

    def set_enabled(self, enabled: bool) -> None:
        self._enabled = bool(enabled)
        if not self._enabled:
            self.cancel_all()

    def cancel_all(self) -> None:
        for job in list(self._jobs):
            try:
                self._widget.after_cancel(job)
            except Exception:
                pass
        self._jobs.clear()

    def _after(self, delay: int, fn: Callable[[], None]) -> None:
        holder: List[str] = []

        def wrapper() -> None:
            for job in holder:
                if job in self._jobs:
                    self._jobs.remove(job)
            try:
                fn()
            except Exception:
                pass

        try:
            holder.append(self._widget.after(delay, wrapper))
            self._jobs.extend(holder)
        except Exception:
            pass

    def _animate(
        self,
        duration: int,
        easing: Callable[[float], float],
        step: Callable[[float], None],
        done: Optional[Callable[[], None]] = None,
    ) -> None:
        """逐帧驱动 step(progress)，progress 已过缓动。"""
        if not self.enabled or duration <= 0:
            step(1.0)
            if done:
                done()
            return

        frames = max(1, int(duration / FRAME_MS))

        def tick(index: int) -> None:
            raw = min(1.0, index / frames)
            step(easing(raw))
            if index < frames:
                self._after(FRAME_MS, lambda: tick(index + 1))
            elif done:
                done()

        tick(0)

    # ── 结果揭示 ──────────────────────────────────────────
    def reveal_name(
        self,
        label,
        name: str,
        target_font,
        target_color: str,
        base_color: str,
        on_done: Optional[Callable[[], None]] = None,
    ) -> None:
        """抽中结果的揭示：字号放大落定 + 颜色渐入。"""
        self.cancel_all()
        label.configure(text=name)

        if not self.enabled:
            label.configure(font=target_font, text_color=target_color)
            if on_done:
                on_done()
            return

        try:
            family, size, weight = target_font
        except Exception:
            label.configure(text_color=target_color)
            if on_done:
                on_done()
            return

        start_size = max(10, int(size * REVEAL_START_RATIO))
        start_color = lerp_color(base_color, target_color, 0.12)

        def step(p: float) -> None:
            cur = int(round(start_size + (size - start_size) * p))
            try:
                label.configure(
                    font=(family, cur, weight),
                    text_color=lerp_color(start_color, target_color, p),
                )
            except Exception:
                pass

        self._animate(DURATION_REVEAL, _ease_out_back, step, done=on_done)

    # ── 状态提示 ──────────────────────────────────────────
    def pulse_color(
        self,
        label,
        color_from: str,
        color_to: str,
        duration: int = 180,
    ) -> None:
        """一次颜色脉冲（如"正在抽取"的呼吸感）。"""

        def step(p: float) -> None:
            # 0→1→0 往返
            t = 1.0 - abs(2.0 * p - 1.0)
            try:
                label.configure(text_color=lerp_color(color_from, color_to, t))
            except Exception:
                pass

        self.cancel_all()
        if not self.enabled:
            label.configure(text_color=color_to)
            return
        self._animate(duration, _ease_in_out, step)

    def button_press(self, button, color_pressed: str, color_normal: str) -> None:
        """按钮按压反馈：颜色加深后立即恢复。"""
        self.cancel_all()
        try:
            button.configure(fg_color=color_pressed)
        except Exception:
            return

        def restore() -> None:
            try:
                button.configure(fg_color=color_normal)
            except Exception:
                pass

        self._after(DURATION_PRESS, restore)
