"""
LiveKit Agents worker — handles individual phone call jobs.

Run separately alongside the FastAPI server:
    python calling_agent.py dev          # development
    python calling_agent.py start        # production

Each job corresponds to one phone call. The agent:
  1. Waits for the SIP participant (the person being called)
  2. Delivers the caller's message via TTS
  3. Listens for a response via STT
  4. Posts the result back to the FastAPI server

Environment variables required (same .env file):
    LIVEKIT_URL, LIVEKIT_API_KEY, LIVEKIT_API_SECRET
    GROQ_API_KEY, SARVAM_API_KEY
    CALLING_AGENT_CALLBACK_BASE (optional, default http://localhost:8000)
"""
from __future__ import annotations

import asyncio
import io
import json
import logging
import os
import wave

import httpx
from dotenv import load_dotenv
from livekit import agents, rtc
from livekit.agents import (
    Agent,
    AgentSession,
    JobContext,
    WorkerOptions,
    cli,
)
from livekit.agents import stt, tts
from livekit.agents.stt import STTCapabilities
from livekit.agents.tts import TTSCapabilities
from livekit.agents.types import NOT_GIVEN, APIConnectOptions
from livekit.agents import RoomInputOptions
from livekit.plugins import groq as lk_groq
from livekit.plugins import silero

load_dotenv()
log = logging.getLogger("calling_agent")

CALLBACK_BASE = os.getenv("CALLING_AGENT_CALLBACK_BASE", "http://localhost:8000")
SARVAM_API_KEY = os.getenv("SARVAM_API_KEY", "")
GROQ_API_KEY = os.getenv("GROQ_API_KEY", "")


# ---------------------------------------------------------------------------
# Sarvam STT adapter for LiveKit agents v1.6
# ---------------------------------------------------------------------------

class SarvamSTT(stt.STT):
    def __init__(self) -> None:
        super().__init__(capabilities=STTCapabilities(
            streaming=False,
            interim_results=False,
        ))

    async def _recognize_impl(
        self,
        buffer,
        *,
        language=NOT_GIVEN,
        conn_options: APIConnectOptions = APIConnectOptions(),
    ) -> stt.SpeechEvent:
        from services.stt import transcribe

        # buffer is an AudioFrame — use its built-in WAV export
        wav_bytes = buffer.to_wav_bytes()

        transcript = await asyncio.get_event_loop().run_in_executor(
            None, transcribe, wav_bytes, SARVAM_API_KEY
        )
        return stt.SpeechEvent(
            type=stt.SpeechEventType.FINAL_TRANSCRIPT,
            alternatives=[stt.SpeechData(text=transcript or "", language="en-IN")],
        )


# ---------------------------------------------------------------------------
# Sarvam TTS adapter for LiveKit agents v1.6
# ---------------------------------------------------------------------------

class SarvamTTS(tts.TTS):
    def __init__(self, speaker: str = "rahul", language: str = "en-IN") -> None:
        super().__init__(capabilities=TTSCapabilities(streaming=False), sample_rate=22050, num_channels=1)
        self._speaker = speaker
        self._language = language

    def synthesize(self, text: str, *, conn_options: APIConnectOptions = APIConnectOptions()) -> tts.ChunkedStream:
        return _SarvamTTSStream(self, text, self._speaker, self._language, conn_options)


class _SarvamTTSStream(tts.ChunkedStream):
    def __init__(self, tts_inst: SarvamTTS, text: str, speaker: str, language: str, conn_options: APIConnectOptions) -> None:
        super().__init__(tts=tts_inst, input_text=text, conn_options=conn_options)
        self._text = text
        self._speaker = speaker
        self._language = language

    async def _run(self, output_emitter: tts.AudioEmitter) -> None:
        from services.tts import synthesize as sarvam_synthesize

        wav_bytes = await asyncio.get_event_loop().run_in_executor(
            None, sarvam_synthesize, self._text, SARVAM_API_KEY, self._language, self._speaker
        )

        # Parse WAV to get sample rate and raw PCM bytes
        wav_io = io.BytesIO(wav_bytes)
        with wave.open(wav_io, "rb") as wf:
            sample_rate = wf.getframerate()
            num_channels = wf.getnchannels()
            raw_pcm = wf.readframes(wf.getnframes())

        output_emitter.initialize(
            request_id=self._text[:32],
            sample_rate=sample_rate,
            num_channels=num_channels,
            mime_type="audio/pcm",
        )
        output_emitter.push(raw_pcm)
        output_emitter.end_input()


# ---------------------------------------------------------------------------
# Result reporting
# ---------------------------------------------------------------------------

async def post_result(
    callback_url: str,
    call_id: str,
    status: str,
    response: str | None,
    summary: str | None,
    transcript: list | None = None,
) -> None:
    payload = {
        "call_id": call_id,
        "status": status,
        "response": response,
        "summary": summary,
        "transcript": transcript or [],
    }
    try:
        async with httpx.AsyncClient(timeout=10) as client:
            await client.post(callback_url, json=payload)
        log.info("calling_agent: posted result call_id=%s status=%s", call_id, status)
    except Exception as e:
        log.error("calling_agent: failed to post result call_id=%s error=%s", call_id, e)


# ---------------------------------------------------------------------------
# Entry point — one job per phone call
# ---------------------------------------------------------------------------

async def entrypoint(ctx: JobContext) -> None:
    await ctx.connect()

    # Metadata is set on the job by CallingIntegration.dispatch_agent
    try:
        meta = json.loads(ctx.job.metadata or "{}")
    except (json.JSONDecodeError, AttributeError):
        meta = {}

    # Fallback: also try room metadata
    if not meta:
        try:
            meta = json.loads(ctx.room.metadata or "{}")
        except (json.JSONDecodeError, AttributeError):
            meta = {}

    call_id = meta.get("call_id", "unknown")
    phone_number = meta.get("phone_number", "")
    contact_name = meta.get("contact_name", phone_number)
    message = meta.get("message", "Hello, I have a message for you.")
    extract_intent = meta.get("extract_intent", "their response")
    callback_url = meta.get("callback_url", f"{CALLBACK_BASE}/api/internal/call-result")

    # Load the user's real name from profile
    import sys as _sys, os as _os
    _sys.path.insert(0, _os.path.dirname(_os.path.abspath(__file__)))
    from utils.profile import load as _load_profile
    user_name = _load_profile().get("name", "").strip() or "the user"

    log.info("calling_agent: job started call_id=%s number=%s user_name=%s", call_id, phone_number, user_name)

    system_prompt = (
        f"You are Ronny, {user_name}'s personal AI assistant, making a phone call on their behalf. "
        f"Speak ONLY as yourself — never write the other person's lines or stage directions. "
        f"Keep each reply to 1-2 short sentences, exactly like a real phone conversation. "
        f"IMPORTANT: You are NOT {user_name}. You are Ronny, calling on their behalf. "
        f"Always refer to {user_name} in third person — never say 'I' when meaning {user_name}. "
        f"For example, if the message is 'I will be late', say '{user_name} will be late'. "
        f"Your goal:\n"
        f"1. You have already introduced yourself. Now deliver this message, converting any first-person "
        f"   references ('I', 'my', 'me') to '{user_name}': {message}\n"
        f"2. Listen for their response and note: {extract_intent}.\n"
        f"3. Once the message is delivered and acknowledged, say a brief goodbye and call end_call immediately.\n"
        f"Do not narrate, do not script the other person's side, do not add stage directions."
    )

    # Signals
    call_ended = asyncio.Event()
    participant_left = asyncio.Event()

    # Tool the LLM calls to hang up
    @agents.function_tool
    async def end_call() -> str:
        """End the phone call. Call this as soon as the message has been delivered and acknowledged, or after saying goodbye."""
        call_ended.set()
        return "Call ended."

    stt_plugin = SarvamSTT()
    tts_plugin = SarvamTTS()
    llm_plugin = lk_groq.LLM(model="llama-3.3-70b-versatile", api_key=GROQ_API_KEY)
    vad_plugin = silero.VAD.load()

    # Wait for the SIP participant to join
    try:
        sip_participant = await asyncio.wait_for(ctx.wait_for_participant(), timeout=60)
    except asyncio.TimeoutError:
        log.warning("calling_agent: no participant joined (no-answer) call_id=%s", call_id)
        await post_result(callback_url, call_id, "no-answer", None, "The call was not answered.")
        return

    log.info("calling_agent: participant joined identity=%s", sip_participant.identity)

    # Track disconnect event
    @ctx.room.on("participant_disconnected")
    def on_disconnect(participant):
        if participant.identity == sip_participant.identity:
            participant_left.set()

    session = AgentSession(
        stt=stt_plugin,
        llm=llm_plugin,
        tts=tts_plugin,
        vad=vad_plugin,
    )

    await session.start(
        Agent(
            instructions=system_prompt,
            tools=[end_call],
            max_endpointing_delay=3.0,
        ),
        room=ctx.room,
        room_input_options=RoomInputOptions(participant_identity=sip_participant.identity),
    )

    # Speak the greeting immediately via say() — skips the LLM so audio starts ~2s faster.
    greeting = f"Hi, I'm Ronny, {user_name}'s personal AI assistant."
    await session.say(greeting)

    # Deliver the actual message — LLM must convert any first-person to user_name
    await session.generate_reply(
        instructions=(
            f"Deliver the following message to the person on the call. "
            f"Convert any first-person references ('I', 'my', 'me') to '{user_name}'. "
            f"Speak naturally in 1-2 sentences: {message}"
        )
    )

    # Wait until: agent calls end_call, participant hangs up, or 5-min max
    try:
        async with asyncio.timeout(300):
            while not call_ended.is_set() and not participant_left.is_set():
                await asyncio.sleep(0.5)
    except asyncio.TimeoutError:
        log.warning("calling_agent: call hit 5-minute limit call_id=%s", call_id)

    # If agent ended it, remove the SIP participant (hang up our side)
    if call_ended.is_set() and not participant_left.is_set():
        try:
            from livekit.api import LiveKitAPI, RoomParticipantIdentity
            async with LiveKitAPI(
                os.getenv("LIVEKIT_URL"),
                os.getenv("LIVEKIT_API_KEY"),
                os.getenv("LIVEKIT_API_SECRET"),
            ) as lk:
                await lk.room.remove_participant(RoomParticipantIdentity(
                    room=ctx.room.name,
                    identity=sip_participant.identity,
                ))
            log.info("calling_agent: hung up call_id=%s", call_id)
            await asyncio.sleep(1)  # let disconnect propagate
        except Exception as e:
            log.warning("calling_agent: hangup failed: %s", e)

    # Gather full transcript and last user response
    transcript: list[dict] = []
    response = None
    summary = f"Call with {contact_name} completed."
    try:
        chat_messages = session.history.messages()
        for m in chat_messages:
            role = str(getattr(m, "role", "")).lower()
            content = str(m.content).strip() if m.content else ""
            if role in ("assistant", "user") and content:
                transcript.append({"role": role, "text": content})

        user_msgs = [t["text"] for t in transcript if t["role"] == "user"]
        response = user_msgs[-1] if user_msgs else None
        summary = f"{contact_name} said: {response}" if response else f"Call with {contact_name} completed, no response captured."
    except Exception as e:
        log.warning("calling_agent: could not read transcript: %s", e)

    log.info("calling_agent: call completed call_id=%s turns=%d", call_id, len(transcript))
    await post_result(callback_url, call_id, "completed", response, summary, transcript)


if __name__ == "__main__":
    cli.run_app(WorkerOptions(
        entrypoint_fnc=entrypoint,
        agent_name="calling-agent",
        num_idle_processes=1,  # keep one warm process ready — eliminates cold-start delay
    ))
