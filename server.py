"""
FastAPI web server for the Ronny personal AI assistant.
Replaces the desktop CustomTkinter UI with a browser-based interface.
"""
import base64
from contextlib import asynccontextmanager

from pathlib import Path

from fastapi import Depends, FastAPI, File, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
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
from integrations.calling_integration import CallingIntegration
from integrations.livekit_client import LiveKitClient
from integrations.contacts import ContactBook
from integrations.call_store import CallStore
from services.llm import LLMClient
from utils.logger import get_logger, setup_logging
import services.stt as stt_service
import services.tts as tts_service

setup_logging()
log = get_logger(__name__)

_settings = None
_conv: ConversationManager | None = None
_tts_speaker: str = "rahul"
_call_store: CallStore | None = None

# Rate limiter — 10 requests per minute per IP on voice/text endpoints
limiter = Limiter(key_func=get_remote_address)

# Bearer token auth
_security = HTTPBearer(auto_error=False)


async def verify_token(credentials: HTTPAuthorizationCredentials | None = Depends(_security)) -> None:
    """Enforce bearer token auth when API_TOKEN is configured."""
    if not _settings or not _settings.API_TOKEN:
        return  # No token set — dev mode, allow all (log a warning at startup)
    if credentials is None or credentials.scheme.lower() != "bearer" or credentials.credentials != _settings.API_TOKEN:
        raise HTTPException(status_code=401, detail="Unauthorized")


@asynccontextmanager
async def lifespan(app: FastAPI):
    global _settings, _conv, _tts_speaker, _call_store
    _settings = load_settings()
    _tts_speaker = await run_in_threadpool(
        tts_service.validate_speaker, _settings.SARVAM_API_KEY, _settings.TTS_SPEAKER, _settings.TTS_LANGUAGE
    )

    # Build clients
    ha_client = HAClient(_settings.HA_URL, _settings.HA_TOKEN)
    swiggy_client = SwiggyClient(_settings.SWIGGY_ACCESS_TOKEN)
    gcal_client = GoogleCalendarClient(_settings.GOOGLE_CALENDAR_TOKEN, _settings.GOOGLE_CALENDAR_CREDENTIALS)

    # Calling module (optional — skipped if LiveKit credentials are absent)
    _call_store = CallStore()
    contacts = ContactBook()
    livekit_client: LiveKitClient | None = None
    if _settings.LIVEKIT_URL and _settings.LIVEKIT_API_KEY and _settings.LIVEKIT_API_SECRET:
        try:
            livekit_client = LiveKitClient(
                _settings.LIVEKIT_URL,
                _settings.LIVEKIT_API_KEY,
                _settings.LIVEKIT_API_SECRET,
                _settings.LIVEKIT_SIP_TRUNK_ID,
            )
        except Exception as e:
            log.warning("server: LiveKit client init failed, calling disabled", error=str(e))

    # Register integrations — add or remove features here, nothing else changes
    registry = IntegrationRegistry()
    registry.register(HAIntegration(ha_client))
    registry.register(SwiggyIntegration(swiggy_client))
    registry.register(GoogleCalendarIntegration(gcal_client))
    registry.register(CallingIntegration(
        livekit_client, contacts, _call_store,
        callback_base_url=_settings.CALLING_AGENT_CALLBACK_BASE,
    ))

    llm = LLMClient(_settings.GROQ_API_KEY, tools=registry.get_all_tools())
    ha_integration = registry.get_integration("ha")
    _conv = ConversationManager(llm, ha_integration, registry)
    await run_in_threadpool(_conv.start)

    if not _settings.API_TOKEN:
        log.warning("server: API_TOKEN is not set — all /api/* endpoints are unprotected. Set API_TOKEN in .env for production.")
    log.info("server: Ronny is ready")
    yield


app = FastAPI(title="Ronny", lifespan=lifespan)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)


class TextRequest(BaseModel):
    text: str = Field(..., min_length=1, max_length=10_000)


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
        raise HTTPException(status_code=502, detail="Assistant service unavailable. Please try again.")

    try:
        wav_bytes = await run_in_threadpool(
            tts_service.synthesize, reply, _settings.SARVAM_API_KEY, _settings.TTS_LANGUAGE, _tts_speaker
        )
    except Exception as e:
        log.error("server: TTS error", error=str(e))
        raise HTTPException(status_code=502, detail="Voice service unavailable. Please try again.")

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
@limiter.limit("10/minute")
async def voice(request: Request, file: UploadFile = File(...), _: None = Depends(verify_token)):
    audio_bytes = await file.read()
    try:
        transcript = await run_in_threadpool(
            stt_service.transcribe, audio_bytes, _settings.SARVAM_API_KEY
        )
    except Exception as e:
        log.error("server: STT error", error=str(e))
        raise HTTPException(status_code=502, detail="Voice recognition unavailable. Please try again.")

    if not transcript:
        raise HTTPException(status_code=422, detail="No speech detected.")

    log.info("server: voice input", transcript=transcript)
    response = await _llm_and_tts(transcript)
    response.transcript = transcript
    return response


@app.post("/api/text", response_model=AssistantResponse)
@limiter.limit("10/minute")
async def text_input(request: Request, req: TextRequest, _: None = Depends(verify_token)):
    log.info("server: text input", text=req.text)
    return await _llm_and_tts(req.text.strip())


# ---------------------------------------------------------------------------
# Calling module endpoints
# ---------------------------------------------------------------------------

class CallResultPayload(BaseModel):
    call_id: str
    status: str
    response: str | None = None
    summary: str | None = None


@app.post("/api/internal/call-result")
async def call_result_webhook(payload: CallResultPayload):
    """Called by calling_agent.py when a phone call ends."""
    if _call_store is None:
        raise HTTPException(status_code=503, detail="Call store not initialised.")
    _call_store.update(
        payload.call_id,
        status=payload.status,
        response=payload.response,
        summary=payload.summary,
    )
    log.info("server: call result received", call_id=payload.call_id, status=payload.status)
    return {"ok": True}


@app.get("/api/calls")
async def list_calls(_: None = Depends(verify_token)):
    """List recent call records."""
    if _call_store is None:
        return {"calls": []}
    records = _call_store.list_recent(20)
    return {
        "calls": [
            {
                "call_id": r.call_id,
                "contact": r.contact_name or r.phone_number,
                "status": r.status,
                "summary": r.summary,
                "created_at": r.created_at.isoformat(),
            }
            for r in records
        ]
    }


# Static files — mount AFTER API routes
app.mount("/static", StaticFiles(directory="web/static"), name="static")


@app.get("/{full_path:path}")
async def spa(full_path: str):
    # Inject the API token as a JS global so the frontend can auth its requests
    html = Path("web/index.html").read_text(encoding="utf-8")
    token = _settings.API_TOKEN if _settings else ""
    import json
    html = html.replace(
        "</head>",
        f'<script>window.RONNY_API_TOKEN={json.dumps(token)};</script>\n</head>',
        1,
    )
    return HTMLResponse(html)
