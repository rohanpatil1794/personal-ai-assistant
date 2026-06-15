"""
Modal dialog that prompts for missing credentials and writes them to .env.
"""
import customtkinter as ctk
from dotenv import set_key


FIELD_LABELS = {
    "GEMINI_API_KEY": "Gemini API Key",
    "SARVAM_API_KEY": "Sarvam API Key",
    "HA_URL": "Home Assistant URL (e.g. http://192.168.1.100:8123)",
    "HA_TOKEN": "Home Assistant Long-Lived Access Token",
}


class CredentialDialog(ctk.CTkToplevel):
    def __init__(self, master, missing_fields: list[str], on_saved: callable):
        super().__init__(master)
        self.title("Setup — Enter Credentials")
        self.geometry("520x480")
        self.resizable(False, False)
        self.grab_set()
        self.configure(fg_color="#0d0d1a")

        self._missing = missing_fields
        self._on_saved = on_saved
        self._entries: dict[str, ctk.CTkEntry] = {}

        ctk.CTkLabel(
            self,
            text="Please enter your API credentials to continue.",
            font=ctk.CTkFont(size=14, weight="bold"),
            text_color="#aaaaaa",
        ).pack(pady=(20, 10))

        form = ctk.CTkFrame(self, fg_color="transparent")
        form.pack(fill="x", padx=30)

        for field in missing_fields:
            label_text = FIELD_LABELS.get(field, field)
            ctk.CTkLabel(form, text=label_text, anchor="w", text_color="#888888").pack(fill="x", pady=(10, 0))
            show = "*" if "KEY" in field or "TOKEN" in field else ""
            entry = ctk.CTkEntry(form, show=show, width=460, fg_color="#1a1a2e", text_color="#ffffff")
            entry.pack(fill="x")
            self._entries[field] = entry

        self._error_label = ctk.CTkLabel(self, text="", text_color="#ff5555")
        self._error_label.pack(pady=(8, 0))

        ctk.CTkButton(
            self,
            text="Save & Continue",
            command=self._save,
            fg_color="#1a4a8a",
            hover_color="#2a6aaa",
        ).pack(pady=20)

    def _save(self) -> None:
        for field, entry in self._entries.items():
            val = entry.get().strip()
            if not val:
                self._error_label.configure(text=f"{FIELD_LABELS.get(field, field)} cannot be empty.")
                return
            set_key(".env", field, val)

        self.destroy()
        self._on_saved()
