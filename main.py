"""
Entry point for the Personal AI Assistant.
"""
import customtkinter as ctk
from pydantic import ValidationError

from config.settings import missing_fields, load_settings
from utils.logger import setup_logging, get_logger

setup_logging()
log = get_logger(__name__)

ctk.set_appearance_mode("dark")
ctk.set_default_color_theme("blue")


def _bootstrap() -> None:
    """Check credentials, show dialog if needed, then launch the main app."""
    # Temporary root needed to show credential dialog before main window
    root = ctk.CTk()
    root.withdraw()

    def _launch_main():
        root.destroy()
        _launch_app()

    fields = missing_fields()
    if fields:
        log.info("main: missing credentials", fields=fields)
        from ui.credential_dialog import CredentialDialog
        dlg = CredentialDialog(root, fields, on_saved=_launch_main)
        root.wait_window(dlg)
        # If dialog closed without saving (user X'd it), exit
        if missing_fields():
            log.error("main: credentials not provided — exiting")
            return
    else:
        _launch_main()

    root.mainloop()


def _launch_app() -> None:
    try:
        settings = load_settings()
    except ValidationError as e:
        log.error("main: invalid settings", error=str(e))
        return

    from integrations.ha_client import HAClient
    from services.llm import LLMClient
    from core.conversation import ConversationManager
    from core.assistant import Assistant
    from ui.main_window import MainWindow

    ha = HAClient(settings.HA_URL, settings.HA_TOKEN)
    llm = LLMClient(
        provider="anthropic",
        api_keys={
            "groq": settings.GROQ_API_KEY,
            "anthropic": settings.ANTHROPIC_API_KEY,
            "openai": settings.OPENAI_API_KEY,
        },
    )
    conv = ConversationManager(llm, ha)

    window = MainWindow(
        on_trigger=lambda: None,    # wired below after assistant is created
        on_stop=lambda: None,
    )

    assistant = Assistant(
        conversation=conv,
        sarvam_api_key=settings.SARVAM_API_KEY,
        on_state_change=window.set_state,
        on_transcript=window.add_message,
    )

    # Wire the trigger button to the assistant
    window._on_trigger = assistant.listen_and_respond
    window._on_stop = assistant.stop_listening

    # Initialise assistant (fetch HA entities) in background so UI appears instantly
    import threading
    threading.Thread(target=assistant.start, daemon=True).start()

    log.info("main: starting UI")
    window.mainloop()


if __name__ == "__main__":
    _bootstrap()
