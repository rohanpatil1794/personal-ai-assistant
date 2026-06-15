"""Scrollable transcript panel showing user / assistant turns."""
import customtkinter as ctk


class ChatPanel(ctk.CTkFrame):
    def __init__(self, master, **kwargs):
        super().__init__(master, fg_color="#0d0d1a", corner_radius=12, **kwargs)

        self._textbox = ctk.CTkTextbox(
            self,
            fg_color="#0d0d1a",
            text_color="#cccccc",
            font=ctk.CTkFont(family="Segoe UI", size=13),
            wrap="word",
            state="disabled",
            corner_radius=10,
        )
        self._textbox.pack(fill="both", expand=True, padx=8, pady=8)

        self._textbox.tag_config("user", foreground="#00cccc")
        self._textbox.tag_config("assistant", foreground="#aaffaa")
        self._textbox.tag_config("error", foreground="#ff5555")

    def add_message(self, role: str, text: str) -> None:
        self._textbox.configure(state="normal")
        prefix = "You: " if role == "user" else "Assistant: "
        tag = role if role in ("user", "assistant") else "error"
        self._textbox.insert("end", f"{prefix}{text}\n\n", tag)
        self._textbox.configure(state="disabled")
        self._textbox.see("end")
