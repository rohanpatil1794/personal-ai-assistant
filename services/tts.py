import base64
import httpx
from utils.exceptions import TTSError
from utils.logger import get_logger

log = get_logger(__name__)

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"


def synthesize(text: str, api_key: str, language_code: str = "en-IN", speaker: str = "rahul") -> bytes:
    """
    Send text to Sarvam TTS and return WAV bytes.
    """
    log.info("tts: synthesizing", text=text[:60])
    try:
        resp = httpx.post(
            SARVAM_TTS_URL,
            headers={
                "api-subscription-key": api_key,
                "Content-Type": "application/json",
            },
            json={
                "inputs": [text],
                "target_language_code": language_code,
                "speaker": speaker,
                "model": "bulbul:v3",
                "output_audio_codec": "wav",
            },
            timeout=30,
        )
        resp.raise_for_status()
    except httpx.HTTPStatusError as e:
        raise TTSError(f"Sarvam TTS HTTP {e.response.status_code}: {e.response.text}") from e
    except Exception as e:
        raise TTSError(f"Sarvam TTS request failed: {e}") from e

    data = resp.json()
    audio_b64 = data.get("audios", [None])[0]
    if not audio_b64:
        raise TTSError("Sarvam TTS returned no audio data.")
    wav_bytes = base64.b64decode(audio_b64)
    log.info("tts: audio received", bytes=len(wav_bytes))
    return wav_bytes
