import io
import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wav

from utils.exceptions import AudioError
from utils.logger import get_logger

log = get_logger(__name__)


def play_wav_bytes(wav_bytes: bytes) -> None:
    """Play raw WAV bytes synchronously."""
    try:
        buf = io.BytesIO(wav_bytes)
        rate, data = wav.read(buf)
        if data.ndim == 1:
            data = data.reshape(-1, 1)
        sd.play(data, samplerate=rate)
        sd.wait()
        log.info("audio_output: playback complete")
    except Exception as e:
        raise AudioError(f"Playback failed: {e}") from e
