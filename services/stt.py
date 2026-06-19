import httpx
from utils.exceptions import STTError
from utils.logger import get_logger
from utils.retry import with_retry

log = get_logger(__name__)

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"


def _stt_request(wav_bytes: bytes, api_key: str, language_code: str) -> str:
    try:
        resp = httpx.post(
            SARVAM_STT_URL,
            headers={"api-subscription-key": api_key},
            files={"file": ("audio.wav", wav_bytes, "audio/wav")},
            data={"model": "saarika:v2.5", "language_code": language_code},
            timeout=30,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise STTError(f"Sarvam STT HTTP {e.response.status_code}: {e.response.text}") from e
    except Exception as e:
        raise STTError(f"Sarvam STT request failed: {e}") from e

    data = resp.json()
    return data.get("transcript", "").strip()


def transcribe(wav_bytes: bytes, api_key: str, language_code: str = "en-IN") -> str:
    """Send WAV bytes to Sarvam STT and return the transcript string (retries up to 3x)."""
    log.info("stt: sending audio to Sarvam")
    transcript = with_retry(_stt_request, wav_bytes, api_key, language_code, retries=3, initial_delay=1.0)
    log.info("stt: transcript received", text=transcript)
    return transcript
