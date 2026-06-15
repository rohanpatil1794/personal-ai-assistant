"""
Main application window.
"""
import customtkinter as ctk
from core.state import AssistantState
from ui.sphere_widget import SphereWidget
from ui.chat_panel import ChatPanel

STATE_LABELS = {
    AssistantState.IDLE:      "Ready  —  press Space or click the sphere",
    AssistantState.LISTENING: "Listening...",
    AssistantState.THINKING:  "Thinking...",
    AssistantState.SPEAKING:  "Speaking...",
    AssistantState.ERROR:     "Something went wrong. Try again.",
}


class MainWindow(ctk.CTk):
    def __init__(self, on_trigger: callable, on_stop: callable):
        super().__init__()
        self.title("AI Assistant")
        self.geometry("700x700")
        self.configure(fg_color="#080810")
        self.resizable(True, True)

        self._on_trigger = on_trigger
        self._on_stop = on_stop

        # --- Sphere ---
        sphere_frame = ctk.CTkFrame(self, fg_color="transparent")
        sphere_frame.pack(pady=(30, 5))
        self._sphere = SphereWidget(sphere_frame)
        self._sphere.pack()
        self._sphere._canvas.bind("<Button-1>", self._handle_click)

        # --- Status label ---
        self._status = ctk.CTkLabel(
            self,
            text=STATE_LABELS[AssistantState.IDLE],
            font=ctk.CTkFont(family="Segoe UI", size=13),
            text_color="#556677",
        )
        self._status.pack(pady=(4, 8))

        # --- Chat panel ---
        self._chat = ChatPanel(self)
        self._chat.pack(fill="both", expand=True, padx=20, pady=(0, 10))

        # --- Hold button ---
        self._btn = ctk.CTkButton(
            self,
            text="Hold to Speak",
            font=ctk.CTkFont(size=14, weight="bold"),
            fg_color="#1a3a6a",
            hover_color="#2a5aaa",
            height=44,
            command=self._handle_click,
        )
        self._btn.pack(pady=(0, 20), ipadx=20)

        # Space bar shortcut
        self.bind("<space>", lambda e: self._handle_click())
        self.bind("<Return>", lambda e: self._handle_click())

    def _handle_click(self, *_) -> None:
        self._on_trigger()

    def set_state(self, state: AssistantState) -> None:
        """Thread-safe state update via after()."""
        self.after(0, self._apply_state, state)

    def _apply_state(self, state: AssistantState) -> None:
        self._sphere.set_state(state)
        self._status.configure(text=STATE_LABELS.get(state, ""))
        if state == AssistantState.IDLE:
            self._btn.configure(text="Hold to Speak", state="normal")
        elif state == AssistantState.LISTENING:
            self._btn.configure(text="Listening... (click to stop)", state="normal")
        else:
            self._btn.configure(text=STATE_LABELS[state], state="disabled")

    def add_message(self, role: str, text: str) -> None:
        """Thread-safe transcript append."""
        self.after(0, self._chat.add_message, role, text)
