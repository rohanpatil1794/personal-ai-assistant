import base64
import httpx
from utils.exceptions import TTSError
from utils.logger import get_logger
from utils.retry import with_retry

log = get_logger(__name__)

SARVAM_TTS_URL = "https://api.sarvam.ai/text-to-speech"


def validate_speaker(api_key: str, speaker: str, language_code: str = "en-IN") -> str:
    """Test the speaker with a short API call. Returns speaker if valid, falls back to 'rahul'."""
    speaker = speaker.lower().strip()
    try:
        synthesize("hello", api_key, language_code, speaker)
        log.info("tts: speaker validated", speaker=speaker)
        return speaker
    except TTSError:
        log.warning("tts: speaker not valid, falling back to rahul", speaker=speaker)
        return "rahul"


def _tts_request(text: str, api_key: str, language_code: str, speaker: str) -> bytes:
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
    return base64.b64decode(audio_b64)


def synthesize(text: str, api_key: str, language_code: str = "en-IN", speaker: str = "rahul") -> bytes:
    """Send text to Sarvam TTS and return WAV bytes (retries up to 3x)."""
    log.info("tts: synthesizing", text=text[:60])
    wav_bytes = with_retry(_tts_request, text, api_key, language_code, speaker, retries=3, initial_delay=1.0)
    log.info("tts: audio received", bytes=len(wav_bytes))
    return wav_bytes
