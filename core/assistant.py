"""
Orchestrator — owns the background pipeline thread and state machine.
All UI state changes are dispatched via a registered callback so the Tk
event loop is never touched from the worker thread.
"""
import threading
from typing import Callable

from core.state import AssistantState
from core.conversation import ConversationManager
from services.audio_input import record_until_silence
from services.audio_output import play_wav_bytes
from services import stt, tts
from utils.exceptions import AssistantError
from utils.logger import get_logger

log = get_logger(__name__)

StateCallback = Callable[[AssistantState], None]
TranscriptCallback = Callable[[str, str], None]   # (role, text)


class Assistant:
    def __init__(
        self,
        conversation: ConversationManager,
        sarvam_api_key: str,
        on_state_change: StateCallback | None = None,
        on_transcript: TranscriptCallback | None = None,
    ) -> None:
        self._conv = conversation
        self._sarvam_key = sarvam_api_key
        self._on_state = on_state_change or (lambda s: None)
        self._on_transcript = on_transcript or (lambda r, t: None)
        self._stop_recording = threading.Event()
        self._lock = threading.Lock()
        self._running = False

    def start(self) -> None:
        """Initialise the conversation (fetch HA entities, start Gemini session)."""
        self._conv.start()
        log.info("assistant: ready")

    def listen_and_respond(self) -> None:
        """
        Launch the full pipeline on a background thread.
        Safe to call from the UI thread.
        """
        with self._lock:
            if self._running:
                return
            self._running = True

        thread = threading.Thread(target=self._pipeline, daemon=True)
        thread.start()

    def stop_listening(self) -> None:
        """Signal the recording loop to stop early."""
        self._stop_recording.set()

    def _set_state(self, state: AssistantState) -> None:
        log.info("assistant: state", state=state.name)
        self._on_state(state)

    def _pipeline(self) -> None:
        try:
            # --- LISTEN ---
            self._stop_recording.clear()
            self._set_state(AssistantState.LISTENING)
            wav_bytes = record_until_silence(stop_event=self._stop_recording)

            # --- STT ---
            self._set_state(AssistantState.THINKING)
            transcript = stt.transcribe(wav_bytes, self._sarvam_key)
            if not transcript:
                self._set_state(AssistantState.IDLE)
                return
            self._on_transcript("user", transcript)

            # --- LLM + HA ---
            reply = self._conv.send(transcript)
            self._on_transcript("assistant", reply)

            # --- TTS ---
            self._set_state(AssistantState.SPEAKING)
            audio = tts.synthesize(reply, self._sarvam_key)
            play_wav_bytes(audio)

        except AssistantError as e:
            log.error("assistant: pipeline error", error=str(e))
            self._set_state(AssistantState.ERROR)
        except Exception as e:
            log.error("assistant: unexpected error", error=str(e))
            self._set_state(AssistantState.ERROR)
        finally:
            self._set_state(AssistantState.IDLE)
            with self._lock:
                self._running = False
