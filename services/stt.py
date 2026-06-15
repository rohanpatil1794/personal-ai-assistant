import httpx
from utils.exceptions import STTError
from utils.logger import get_logger

log = get_logger(__name__)

SARVAM_STT_URL = "https://api.sarvam.ai/speech-to-text"


def transcribe(wav_bytes: bytes, api_key: str, language_code: str = "en-IN") -> str:
    """
    Send WAV bytes to Sarvam STT and return the transcript string.
    """
    log.info("stt: sending audio to Sarvam")
    try:
        resp = httpx.post(
            SARVAM_STT_URL,
            headers={"api-subscription-key": api_key},
            files={"file": ("audio.wav", wav_bytes, "audio/wav")},
            data={"model": "saarika:v2", "language_code": language_code},
            timeout=30,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise STTError(f"Sarvam STT HTTP {e.response.status_code}: {e.response.text}") from e
    except Exception as e:
        raise STTError(f"Sarvam STT request failed: {e}") from e

    data = resp.json()
    transcript = data.get("transcript", "").strip()
    log.info("stt: transcript received", text=transcript)
    return transcript
