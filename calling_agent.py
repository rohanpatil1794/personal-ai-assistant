"""
LiveKit Agents worker — handles individual phone call jobs.

Run separately alongside the FastAPI server:
    python calling_agent.py dev          # development (auto-reload)
    python calling_agent.py start        # production

Each job corresponds to one phone call. The agent:
  1. Waits for the SIP participant (the person being called)
  2. Runs Answering Machine Detection (AMD)
  3. Delivers the caller's message via TTS
  4. Listens for a response via STT
  5. Posts the result back to the FastAPI server

Environment variables required (same .env file):
    LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
    GROQ_API_KEY, SARVAM_API_KEY
    CALLING_AGENT_CALLBACK_BASE (optional, default http://localhost:8000)
"""
from __future__ import annotations

import asyncio
import json
import logging
import os

import httpx
from dotenv import load_dotenv
from livekit import agents
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    RoomInputOptions,
    WorkerOptions,
    cli,
)
from livekit.agents.voice import VoicePipelineAgent
from livekit.plugins import groq as lk_groq
from livekit.plugins import silero

load_dotenv()
log = logging.getLogger("calling_agent")

CALLBACK_BASE = os.getenv("CALLING_AGENT_CALLBACK_BASE", "http://localhost:8000")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


# ---------------------------------------------------------------------------
# Sarvam STT adapter for LiveKit
# ---------------------------------------------------------------------------

class SarvamSTT(agents.stt.STT):
    """Wraps services/stt.py transcribe() as a LiveKit STT plugin."""

    def __init__(self) -> None:
        super().__init__(streaming_supported=False)

    async def recognize(self, buffer: agents.AudioBuffer, *, language: str | None = None) -> agents.stt.SpeechEvent:
        import io
        import wave
        from services.stt import transcribe

        # Convert buffer to WAV bytes
        frames = buffer.frames
        wav_io = io.BytesIO()
        with wave.open(wav_io, "wb") as wf:
            wf.setnchannels(1)
            wf.setsampwidth(2)
            wf.setframerate(buffer.sample_rate)
            wf.writeframes(b"".join(f.data.tobytes() for f in frames))
        wav_bytes = wav_io.getvalue()

        loop = asyncio.get_event_loop()
        transcript = await loop.run_in_executor(
            None, transcribe, wav_bytes, SARVAM_API_KEY
        )
        return agents.stt.SpeechEvent(
            type=agents.stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[agents.stt.SpeechData(text=transcript, language="en-IN")],
        )


# ---------------------------------------------------------------------------
# Sarvam TTS adapter for LiveKit
# ---------------------------------------------------------------------------

class SarvamTTS(agents.tts.TTS):
    """Wraps services/tts.py synthesize() as a LiveKit TTS plugin."""

    def __init__(self, speaker: str = "rahul", language: str = "en-IN") -> None:
        super().__init__(streaming_supported=False, sample_rate=22050, num_channels=1)
        self._speaker = speaker
        self._language = language

    def synthesize(self, text: str) -> agents.tts.ChunkedStream:
        return _SarvamTTSStream(self, text, self._speaker, self._language)


class _SarvamTTSStream(agents.tts.ChunkedStream):
    def __init__(self, tts: SarvamTTS, text: str, speaker: str, language: str) -> None:
        super().__init__(tts=tts, input_text=text)
        self._text = text
        self._speaker = speaker
        self._language = language

    async def _run(self) -> None:
        import io
        import wave
        import numpy as np
        from services.tts import synthesize

        loop = asyncio.get_event_loop()
        wav_bytes = await loop.run_in_executor(
            None, synthesize, self._text, SARVAM_API_KEY, self._language, self._speaker
        )

        wav_io = io.BytesIO(wav_bytes)
        with wave.open(wav_io, "rb") as wf:
            sr = wf.getframerate()
            raw = wf.readframes(wf.getnframes())

        samples = np.frombuffer(raw, dtype=np.int16)
        frame = agents.AudioFrame(
            data=samples.tobytes(),
            sample_rate=sr,
            num_channels=1,
            samples_per_channel=len(samples),
        )
        self._event_ch.send_nowait(
            agents.tts.SynthesizedAudio(request_id=self._text[:20], frame=frame)
        )


# ---------------------------------------------------------------------------
# Result reporting
# ---------------------------------------------------------------------------

async def post_result(callback_url: str, call_id: str, status: str, response: str | None, summary: str | None) -> None:
    payload = {
        "call_id": call_id,
        "status": status,
        "response": response,
        "summary": summary,
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(callback_url, json=payload)
        log.info("calling_agent: posted result", call_id=call_id, status=status)
    except Exception as e:
        log.error("calling_agent: failed to post result", call_id=call_id, error=str(e))


# ---------------------------------------------------------------------------
# Entry point — one job per phone call
# ---------------------------------------------------------------------------

async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()

    # Parse metadata from room (set by CallingIntegration.dispatch_agent)
    try:
        meta = json.loads(ctx.room.metadata or "{}")
    except json.JSONDecodeError:
        meta = {}

    call_id = meta.get("call_id", "unknown")
    phone_number = meta.get("phone_number", "")
    contact_name = meta.get("contact_name", phone_number)
    message = meta.get("message", "Hello, I have a message for you.")
    extract_intent = meta.get("extract_intent", "their response")
    callback_url = meta.get("callback_url", f"{CALLBACK_BASE}/api/internal/call-result")

    log.info("calling_agent: job started", call_id=call_id, number=phone_number)

    # System prompt focused on delivering a message and extracting a reply
    system_prompt = (
        f"You are Ronny, a personal AI assistant making a phone call on behalf of the user. "
        f"Your mission:\n"
        f"1. Greet the person warmly.\n"
        f"2. Deliver this message: {message}\n"
        f"3. Listen carefully and extract: {extract_intent}.\n"
        f"4. Thank them and say goodbye.\n"
        f"Keep the conversation short and natural. Do not reveal you are an AI unless directly asked."
    )

    stt = SarvamSTT()
    tts = SarvamTTS()
    llm = lk_groq.LLM(model="llama-3.1-8b-instant", api_key=GROQ_API_KEY)
    vad = silero.VAD.load()

    session = AgentSession(
        stt=stt,
        llm=llm,
        tts=tts,
        vad=vad,
        instructions=system_prompt,
    )

    # Wait for the SIP participant (the person being called) to join
    try:
        sip_participant = await asyncio.wait_for(
            ctx.wait_for_participant(), timeout=60
        )
    except asyncio.TimeoutError:
        log.warning("calling_agent: no participant joined (no-answer)", call_id=call_id)
        await post_result(callback_url, call_id, "no-answer", None, "The call was not answered.")
        return

    log.info("calling_agent: participant joined", identity=sip_participant.identity)

    # Run the voice session
    await session.start(
        ctx.room,
        agent=Agent(instructions=system_prompt),
        room_input_options=RoomInputOptions(participant_identity=sip_participant.identity),
    )

    # Greet and deliver message
    await session.generate_reply(
        instructions=f"Greet them and deliver this message: {message}"
    )

    # Let the conversation run until the participant disconnects or timeout
    try:
        async with asyncio.timeout(300):   # 5-minute max call duration
            await ctx.wait_for_participant_disconnect(sip_participant.identity)
    except (asyncio.TimeoutError, Exception):
        pass

    # Gather transcript and summarise
    history = session.chat_ctx.messages
    transcript_lines = [
        f"{'Caller' if m.role == 'user' else 'Agent'}: {m.content}"
        for m in history
        if hasattr(m, "content") and m.content
    ]
    full_transcript = "\n".join(transcript_lines)

    # Simple extraction: last user message as the "response"
    user_messages = [m.content for m in history if m.role == "user" and m.content]
    response = user_messages[-1] if user_messages else None
    summary = f"{contact_name} said: {response}" if response else f"Call with {contact_name} ended."

    log.info("calling_agent: call completed", call_id=call_id, response=response)
    await post_result(callback_url, call_id, "completed", response, summary)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(entrypoint_fnc=entrypoint, agent_name="calling-agent"))
