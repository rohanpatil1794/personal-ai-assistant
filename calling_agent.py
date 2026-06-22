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

    from datetime import datetime, timedelta, timezone
    import re as _re
    IST = timezone(timedelta(hours=5, minutes=30))
    today_ist = datetime.now(IST).strftime("%Y-%m-%d")

    # Pre-convert first-person references in the message
    delivered_message = _re.sub(r"\bI'm\b", f"{user_name} is", message)
    delivered_message = _re.sub(r"\bI've\b", f"{user_name} has", delivered_message)
    delivered_message = _re.sub(r"\bI'll\b", f"{user_name} will", delivered_message)
    delivered_message = _re.sub(r"\bI\b", user_name, delivered_message)
    delivered_message = _re.sub(r"\bmy\b", f"{user_name}'s", delivered_message, flags=_re.IGNORECASE)
    delivered_message = _re.sub(r"\bme\b", user_name, delivered_message, flags=_re.IGNORECASE)

    system_prompt = (
        f"You are Ronny, {user_name}'s personal AI assistant, making a phone call on their behalf. "
        f"Speak ONLY as yourself — never write the other person's lines or stage directions. "
        f"Keep each reply to 1-2 short sentences, exactly like a real phone conversation. "
        f"IMPORTANT: You are NOT {user_name}. You are Ronny, calling on their behalf. "
        f"Always refer to {user_name} in third person — never say 'I' when meaning {user_name}. "
        f"For example, if the message is 'I will be late', say '{user_name} will be late'. "
        f"Today's date is {today_ist} (IST).\n"
        f"Your goal:\n"
        f"1. The greeting and the following message have ALREADY been spoken — do NOT repeat them.\n"
        f"   Message already delivered: {delivered_message}\n"
        f"2. Listen for their response and note: {extract_intent}.\n"
        f"3. Act autonomously on small follow-up tasks without asking {user_name} for permission:\n"
        f"   - If rescheduling comes up: call check_calendar to find a free slot on a nearby date, "
        f"     propose that specific time to the other person, and if they confirm, call create_calendar_event "
        f"     to book it immediately. Do not ask {user_name} — just do it.\n"
        f"   - Use your best judgement for similar small logistics.\n"
        f"4. Once the conversation is complete, say a warm, complete farewell (e.g. 'That's all, have a great day! Goodbye!'). "
        f"   Wait until you have fully said goodbye, THEN call end_call.\n"
        f"Do not narrate, do not script the other person's side, do not add stage directions."
    )

    # Signals
    call_ended = asyncio.Event()
    participant_left = asyncio.Event()
    calendar_actions: list[dict] = []  # track any calendar events created

    # ── Tool: end call ──
    @agents.function_tool
    async def end_call() -> str:
        """End the phone call. Call this once the conversation is complete and you have said goodbye."""
        call_ended.set()
        return "Call ended."

    # ── Tool: check calendar availability ──
    @agents.function_tool
    async def check_calendar(date: str) -> str:
        """Check Rohan's calendar availability for a given date (YYYY-MM-DD format).
        Returns busy periods and whether the day is free. Use this before proposing a reschedule time."""
        try:
            from integrations.google_calendar_client import GoogleCalendarClient
            gcal = await asyncio.get_event_loop().run_in_executor(None, GoogleCalendarClient)
            if not gcal.available:
                return "Calendar not available."
            result = await asyncio.get_event_loop().run_in_executor(None, gcal.check_availability, date)
            if result.get("is_free_all_day"):
                return f"{date} is completely free."
            busy = result.get("busy_periods", [])
            busy_str = ", ".join(f"{b['start'][11:16]}–{b['end'][11:16]}" for b in busy)
            return f"{date} busy periods (IST): {busy_str}. Rest of the day is free."
        except Exception as e:
            return f"Could not check calendar: {e}"

    # ── Tool: create calendar event ──
    @agents.function_tool
    async def create_calendar_event(summary: str, start_datetime: str, end_datetime: str, description: str = "") -> str:
        """Create a calendar event for Rohan. Use ISO 8601 datetime strings in IST (e.g. 2026-06-23T15:00:00+05:30).
        Call this only after the other person has confirmed the rescheduled time."""
        try:
            from integrations.google_calendar_client import GoogleCalendarClient
            gcal = await asyncio.get_event_loop().run_in_executor(None, GoogleCalendarClient)
            if not gcal.available:
                return "Calendar not available — could not create event."
            event = await asyncio.get_event_loop().run_in_executor(
                None, lambda: gcal.create_event(summary=summary, start_datetime=start_datetime,
                                                  end_datetime=end_datetime, description=description)
            )
            calendar_actions.append({"action": "created", "summary": summary,
                                      "start": start_datetime, "end": end_datetime})
            log.info("calling_agent: calendar event created call_id=%s summary=%s", call_id, summary)
            return f"Event '{summary}' created on {start_datetime[:10]} from {start_datetime[11:16]} to {end_datetime[11:16]} IST."
        except Exception as e:
            log.warning("calling_agent: failed to create event call_id=%s error=%s", call_id, e)
            return f"Failed to create event: {e}"

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
            tools=[end_call, check_calendar, create_calendar_event],
            max_endpointing_delay=3.0,
        ),
        room=ctx.room,
        room_input_options=RoomInputOptions(participant_identity=sip_participant.identity),
    )

    # Speak the greeting immediately via say() — skips the LLM so audio starts ~2s faster.
    greeting = f"Hi, I'm Ronny, {user_name}'s personal AI assistant."
    await session.say(greeting)
    # Use say() for the message too — avoids duplicate delivery caused by LLM context race
    await session.say(delivered_message)

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
            await asyncio.sleep(4)  # let TTS finish playing before disconnect propagates
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
            raw = m.content
            if isinstance(raw, list):
                content = " ".join(str(c) for c in raw if c).strip()
            else:
                content = str(raw).strip() if raw else ""
            if role in ("assistant", "user") and content:
                transcript.append({"role": role, "text": content})

        user_msgs = [t["text"] for t in transcript if t["role"] == "user"]
        response = user_msgs[-1] if user_msgs else None
        summary = f"{contact_name} said: {response}" if response else f"Call with {contact_name} completed, no response captured."
        if calendar_actions:
            actions_str = "; ".join(f"Created '{a['summary']}' on {a['start'][:10]}" for a in calendar_actions)
            summary += f" Calendar actions: {actions_str}."
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
