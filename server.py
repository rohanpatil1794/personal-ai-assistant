"""
FastAPI web server for the Ronny personal AI assistant.
Replaces the desktop CustomTkinter UI with a browser-based interface.
"""
import base64
from contextlib import asynccontextmanager

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from starlette.concurrency import run_in_threadpool

from config.settings import load_settings
from core.conversation import ConversationManager
from core.registry import IntegrationRegistry
from integrations.ha_client import HAClient
from integrations.ha_integration import HAIntegration
from integrations.swiggy_client import SwiggyClient
from integrations.swiggy_integration import SwiggyIntegration
from integrations.google_calendar_client import GoogleCalendarClient
from integrations.google_calendar_integration import GoogleCalendarIntegration
from services.llm import LLMClient
from utils.logger import get_logger, setup_logging
import services.stt as stt_service
import services.tts as tts_service

setup_logging()
log = get_logger(__name__)

_settings = None
_conv: ConversationManager | None = None
_tts_speaker: str = "rahul"


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _settings, _conv, _tts_speaker
    _settings = load_settings()
    _tts_speaker = await run_in_threadpool(
        tts_service.validate_speaker, _settings.SARVAM_API_KEY, _settings.TTS_SPEAKER, _settings.TTS_LANGUAGE
    )

    # Build clients
    ha_client = HAClient(_settings.HA_URL, _settings.HA_TOKEN)
    swiggy_client = SwiggyClient(_settings.SWIGGY_ACCESS_TOKEN)
    gcal_client = GoogleCalendarClient(_settings.GOOGLE_CALENDAR_TOKEN, _settings.GOOGLE_CALENDAR_CREDENTIALS)

    # Register integrations — add or remove features here, nothing else changes
    registry = IntegrationRegistry()
    registry.register(HAIntegration(ha_client))
    registry.register(SwiggyIntegration(swiggy_client))
    registry.register(GoogleCalendarIntegration(gcal_client))

    llm = LLMClient(_settings.GROQ_API_KEY, tools=registry.get_all_tools())
    ha_integration = registry.get_integration("ha")
    _conv = ConversationManager(llm, ha_integration, registry)
    await run_in_threadpool(_conv.start)
    log.info("server: Ronny is ready")
    yield


app = FastAPI(title="Ronny", lifespan=lifespan)


class TextRequest(BaseModel):
    text: str


class AssistantResponse(BaseModel):
    transcript: str | None = None
    reply: str
    audio_b64: str
    confirmation_required: bool = False
    order_summary: dict | None = None


async def _llm_and_tts(user_text: str) -> AssistantResponse:
    try:
        reply = await run_in_threadpool(_conv.send, user_text)
    except Exception as e:
        log.error("server: LLM error", error=str(e))
        raise HTTPException(status_code=502, detail=f"LLM error: {e}")

    try:
        wav_bytes = await run_in_threadpool(
            tts_service.synthesize, reply, _settings.SARVAM_API_KEY, _settings.TTS_LANGUAGE, _tts_speaker
        )
    except Exception as e:
        log.error("server: TTS error", error=str(e))
        raise HTTPException(status_code=502, detail=f"TTS error: {e}")

    pending = _conv.get_pending_order()

    return AssistantResponse(
        reply=reply,
        audio_b64=base64.b64encode(wav_bytes).decode(),
        confirmation_required=pending is not None,
        order_summary=pending,
    )


@app.get("/api/status")
async def status():
    return {"status": "ok", "ready": _conv is not None}


@app.post("/api/voice", response_model=AssistantResponse)
async def voice(file: UploadFile = File(...)):
    audio_bytes = await file.read()
    try:
        transcript = await run_in_threadpool(
            stt_service.transcribe, audio_bytes, _settings.SARVAM_API_KEY
        )
    except Exception as e:
        log.error("server: STT error", error=str(e))
        raise HTTPException(status_code=502, detail=f"STT error: {e}")

    if not transcript:
        raise HTTPException(status_code=422, detail="No speech detected.")

    log.info("server: voice input", transcript=transcript)
    response = await _llm_and_tts(transcript)
    response.transcript = transcript
    return response


@app.post("/api/text", response_model=AssistantResponse)
async def text_input(req: TextRequest):
    if not req.text.strip():
        raise HTTPException(status_code=422, detail="Empty input.")
    log.info("server: text input", text=req.text)
    return await _llm_and_tts(req.text.strip())


# Static files — mount AFTER API routes
app.mount("/static", StaticFiles(directory="web/static"), name="static")


@app.get("/{full_path:path}")
async def spa(full_path: str):
    return FileResponse("web/index.html")
