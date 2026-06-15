"""
Animated glowing sphere widget driven by AssistantState.
Draws concentric ovals with modulated size and color on a CTkCanvas.
"""
import math
import tkinter as tk
import customtkinter as ctk
from core.state import AssistantState

# (base_color_hex, glow_color_hex)
STATE_COLORS: dict[AssistantState, tuple[str, str]] = {
    AssistantState.IDLE:      ("#1a2a4a", "#2a4a8a"),
    AssistantState.LISTENING: ("#003333", "#00cccc"),
    AssistantState.THINKING:  ("#332200", "#ffaa00"),
    AssistantState.SPEAKING:  ("#003300", "#00dd44"),
    AssistantState.ERROR:     ("#330000", "#ff2222"),
}

SPHERE_SIZE = 200        # canvas width/height in pixels
LAYERS = 7               # number of concentric rings
TICK_MS = 40             # animation interval


class SphereWidget(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="transparent", **kwargs)
        self._state = AssistantState.IDLE
        self._phase = 0.0          # 0.0 – 2π, drives pulse animation
        self._pulse_amp = 0.0      # current pulse amplitude (0–1)

        self._canvas = tk.Canvas(
            self,
            width=SPHERE_SIZE,
            height=SPHERE_SIZE,
            bg="#0a0a0f",
            highlightthickness=0,
        )
        self._canvas.pack()
        self._ovals: list[int] = []
        self._draw_initial()
        self._animate()

    def set_state(self, state: AssistantState) -> None:
        self._state = state
        # Reset phase on state change for snappy transition
        self._phase = 0.0

    def _draw_initial(self) -> None:
        cx = cy = SPHERE_SIZE // 2
        for _ in range(LAYERS):
            oid = self._canvas.create_oval(cx, cy, cx, cy, fill="#1a2a4a", outline="")
            self._ovals.append(oid)

    def _animate(self) -> None:
        self._phase = (self._phase + 0.12) % (2 * math.pi)
        pulse = (math.sin(self._phase) + 1) / 2   # 0–1

        base_col, glow_col = STATE_COLORS.get(self._state, STATE_COLORS[AssistantState.IDLE])
        cx = cy = SPHERE_SIZE // 2

        # Idle: slow gentle breathe; others: faster fuller pulse
        if self._state == AssistantState.IDLE:
            scale = 0.6 + pulse * 0.08
        else:
            scale = 0.55 + pulse * 0.25

        max_r = (SPHERE_SIZE // 2) * scale

        for i, oid in enumerate(self._ovals):
            layer_frac = (LAYERS - i) / LAYERS   # inner layers are bigger fraction
            r = max_r * layer_frac
            alpha_frac = layer_frac ** 1.5        # inner rings brighter

            color = self._lerp_color(base_col, glow_col, alpha_frac * pulse + 0.3)
            self._canvas.coords(oid, cx - r, cy - r, cx + r, cy + r)
            self._canvas.itemconfig(oid, fill=color)

        self._canvas.after(TICK_MS, self._animate)

    @staticmethod
    def _lerp_color(c1: str, c2: str, t: float) -> str:
        """Linear interpolate between two hex colors."""
        t = max(0.0, min(1.0, t))
        r1, g1, b1 = int(c1[1:3], 16), int(c1[3:5], 16), int(c1[5:7], 16)
        r2, g2, b2 = int(c2[1:3], 16), int(c2[3:5], 16), int(c2[5:7], 16)
        r = int(r1 + (r2 - r1) * t)
        g = int(g1 + (g2 - g1) * t)
        b = int(b1 + (b2 - b1) * t)
        return f"#{r:02x}{g:02x}{b:02x}"
