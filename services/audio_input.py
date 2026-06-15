import io
import threading
import numpy as np
import sounddevice as sd
import scipy.io.wavfile as wav

from utils.exceptions import AudioError
from utils.logger import get_logger

log = get_logger(__name__)

SAMPLE_RATE = 16000
CHANNELS = 1
DTYPE = "int16"
SILENCE_THRESHOLD = 500   # RMS below this = silence
SILENCE_DURATION = 1.5    # seconds of silence to stop recording
MAX_DURATION = 30         # hard cap in seconds


def _rms(block: np.ndarray) -> float:
    return float(np.sqrt(np.mean(block.astype(np.float32) ** 2)))


def record_until_silence(stop_event: threading.Event | None = None) -> bytes:
    """
    Record from the default microphone until silence is detected or stop_event is set.
    Returns raw WAV bytes (16kHz, 16-bit mono).
    """
    log.info("audio_input: recording started")
    chunks: list[np.ndarray] = []
    silent_frames = 0
    block_size = int(SAMPLE_RATE * 0.1)  # 100ms blocks
    silence_blocks = int(SILENCE_DURATION / 0.1)
    max_blocks = int(MAX_DURATION / 0.1)
    total_blocks = 0

    try:
        with sd.InputStream(
            samplerate=SAMPLE_RATE,
            channels=CHANNELS,
            dtype=DTYPE,
            blocksize=block_size,
        ) as stream:
            while total_blocks < max_blocks:
                if stop_event and stop_event.is_set():
                    break
                block, _ = stream.read(block_size)
                chunks.append(block.copy())
                total_blocks += 1
                if _rms(block) < SILENCE_THRESHOLD:
                    silent_frames += 1
                    if silent_frames >= silence_blocks and total_blocks > 10:
                        break
                else:
                    silent_frames = 0
    except Exception as e:
        raise AudioError(f"Microphone capture failed: {e}") from e

    if not chunks:
        raise AudioError("No audio captured.")

    audio = np.concatenate(chunks, axis=0)
    buf = io.BytesIO()
    wav.write(buf, SAMPLE_RATE, audio)
    log.info("audio_input: recording complete", frames=len(audio))
    return buf.getvalue()
