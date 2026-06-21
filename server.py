"""
FastAPI web server for the Ronny personal AI assistant.
Replaces the desktop CustomTkinter UI with a browser-based interface.
"""
import base64
import time
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
import utils.db as db
import utils.profile as profile_store
import services.stt as stt_service
import services.tts as tts_service

setup_logging()
db.init_db()
log = get_logger(__name__)

_settings = None
_conv: ConversationManager | None = None
_tts_speaker: str = "rahul"
_call_store: CallStore | None = None
_contacts: ContactBook | None = None

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
    global _settings, _conv, _tts_speaker, _call_store, _contacts
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
    _contacts = contacts
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


async def _llm_and_tts(
    user_text: str,
    input_type: str = "text",
    stt_ms: int = 0,
) -> AssistantResponse:
    t_llm = time.perf_counter()
    try:
        reply = await run_in_threadpool(_conv.send, user_text)
    except Exception as e:
        log.error("server: LLM error", error=str(e))
        llm_ms = int((time.perf_counter() - t_llm) * 1000)
        db.log_request(
            input_type=input_type, transcript=user_text, reply=None,
            status="error", error=str(e),
            stt_ms=stt_ms, llm_ms=llm_ms, total_ms=stt_ms + llm_ms,
        )
        raise HTTPException(status_code=502, detail="Assistant service unavailable. Please try again.")
    llm_ms = int((time.perf_counter() - t_llm) * 1000)

    t_tts = time.perf_counter()
    try:
        wav_bytes = await run_in_threadpool(
            tts_service.synthesize, reply, _settings.SARVAM_API_KEY, _settings.TTS_LANGUAGE, _tts_speaker
        )
    except Exception as e:
        log.error("server: TTS error", error=str(e))
        tts_ms = int((time.perf_counter() - t_tts) * 1000)
        db.log_request(
            input_type=input_type, transcript=user_text, reply=reply,
            status="error", error=f"TTS: {e}",
            stt_ms=stt_ms, llm_ms=llm_ms, tts_ms=tts_ms, total_ms=stt_ms + llm_ms + tts_ms,
        )
        raise HTTPException(status_code=502, detail="Voice service unavailable. Please try again.")
    tts_ms = int((time.perf_counter() - t_tts) * 1000)
    total_ms = stt_ms + llm_ms + tts_ms

    db.log_request(
        input_type=input_type, transcript=user_text, reply=reply,
        status="success",
        stt_ms=stt_ms, llm_ms=llm_ms, tts_ms=tts_ms, total_ms=total_ms,
    )
    log.info("server: request complete", stt_ms=stt_ms, llm_ms=llm_ms, tts_ms=tts_ms, total_ms=total_ms)

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
    t_stt = time.perf_counter()
    try:
        transcript = await run_in_threadpool(
            stt_service.transcribe, audio_bytes, _settings.SARVAM_API_KEY
        )
    except Exception as e:
        log.error("server: STT error", error=str(e))
        stt_ms = int((time.perf_counter() - t_stt) * 1000)
        db.log_request(input_type="voice", transcript=None, reply=None,
                       status="error", error=f"STT: {e}", stt_ms=stt_ms, total_ms=stt_ms)
        raise HTTPException(status_code=502, detail="Voice recognition unavailable. Please try again.")
    stt_ms = int((time.perf_counter() - t_stt) * 1000)

    if not transcript:
        raise HTTPException(status_code=422, detail="No speech detected.")

    log.info("server: voice input", transcript=transcript)
    response = await _llm_and_tts(transcript, input_type="voice", stt_ms=stt_ms)
    response.transcript = transcript
    return response


@app.post("/api/text", response_model=AssistantResponse)
@limiter.limit("10/minute")
async def text_input(request: Request, req: TextRequest, _: None = Depends(verify_token)):
    log.info("server: text input", text=req.text)
    return await _llm_and_tts(req.text.strip(), input_type="text")


# ---------------------------------------------------------------------------
# Calling module endpoints
# ---------------------------------------------------------------------------

class CallResultPayload(BaseModel):
    call_id: str
    status: str
    response: str | None = None
    summary: str | None = None
    transcript: list | None = None


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
    # Persist to SQLite for permanent transcript record
    record = _call_store.get(payload.call_id)
    db.log_call(
        call_id=payload.call_id,
        contact=record.contact_name if record else None,
        phone=record.phone_number if record else None,
        mission=record.mission if record else None,
        status=payload.status,
        response=payload.response,
        summary=payload.summary,
        transcript=payload.transcript,
        completed_at=record.completed_at.isoformat() if record and record.completed_at else None,
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


# ---------------------------------------------------------------------------
# Profile endpoints
# ---------------------------------------------------------------------------

class ProfileRequest(BaseModel):
    name: str = Field(default="", max_length=100)
    about: str = Field(default="", max_length=2000)


@app.get("/api/profile")
async def get_profile(_: None = Depends(verify_token)):
    return profile_store.load()


@app.post("/api/profile")
async def save_profile(req: ProfileRequest, _: None = Depends(verify_token)):
    profile_store.save({"name": req.name, "about": req.about})
    return {"ok": True}


# ---------------------------------------------------------------------------
# Contacts endpoints
# ---------------------------------------------------------------------------

class ContactRequest(BaseModel):
    name: str = Field(..., min_length=1, max_length=100)
    phone: str = Field(..., min_length=1, max_length=30)


@app.get("/api/contacts")
async def get_contacts(_: None = Depends(verify_token)):
    if _contacts is None:
        return {"contacts": {}}
    return {"contacts": _contacts.list_all()}


@app.post("/api/contacts")
async def add_contact(req: ContactRequest, _: None = Depends(verify_token)):
    if _contacts is None:
        raise HTTPException(status_code=503, detail="Contacts not available.")
    _contacts.add(req.name, req.phone)
    return {"ok": True}


@app.delete("/api/contacts/{name}")
async def delete_contact(name: str, _: None = Depends(verify_token)):
    if _contacts is None:
        raise HTTPException(status_code=503, detail="Contacts not available.")
    removed = _contacts.remove(name)
    if not removed:
        raise HTTPException(status_code=404, detail="Contact not found.")
    return {"ok": True}


# ---------------------------------------------------------------------------
# Profile page
# ---------------------------------------------------------------------------

@app.get("/profile")
async def profile_page():
    html = Path("web/profile.html").read_text(encoding="utf-8")
    import json as _json
    token = _settings.API_TOKEN if _settings else ""
    html = html.replace(
        "</head>",
        f'<script>window.RONNY_API_TOKEN={_json.dumps(token)};</script>\n</head>',
        1,
    )
    return HTMLResponse(html)


@app.get("/api/call-logs")
async def get_call_logs(_: None = Depends(verify_token)):
    return {"calls": db.get_call_logs(200)}


@app.get("/calls")
async def calls_viewer():
    import json as _json
    token = _settings.API_TOKEN if _settings else ""
    html = Path("web/calls.html").read_text(encoding="utf-8")
    html = html.replace(
        "</head>",
        f'<script>window.RONNY_API_TOKEN={_json.dumps(token)};</script>\n</head>',
        1,
    )
    return HTMLResponse(html)


@app.get("/api/logs")
async def get_logs(_: None = Depends(verify_token)):
    """Return recent request logs as JSON."""
    return {"logs": db.get_recent_logs(100)}


@app.get("/logs")
async def logs_viewer(_: None = Depends(verify_token)):
    """Simple HTML viewer for request logs."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Ronny — Request Logs</title>
<style>
  body{font-family:system-ui,sans-serif;background:#0d0d0d;color:#e0e0e0;margin:0;padding:1rem}
  h1{margin:0 0 1rem;font-size:1.2rem;color:#fff}
  table{width:100%;border-collapse:collapse;font-size:.8rem}
  th{text-align:left;padding:.4rem .6rem;background:#1a1a1a;color:#999;border-bottom:1px solid #333;position:sticky;top:0}
  td{padding:.4rem .6rem;border-bottom:1px solid #1e1e1e;vertical-align:top;max-width:28rem;word-break:break-word}
  tr:hover td{background:#141414}
  .ok{color:#4ade80}.err{color:#f87171}.voice{color:#60a5fa}.text{color:#a78bfa}
  .ms{color:#fbbf24;font-variant-numeric:tabular-nums}
  .ts{color:#555;white-space:nowrap}
</style>
</head>
<body>
<h1>Ronny — Request Logs <span id="count" style="color:#555;font-weight:400"></span></h1>
<table>
<thead><tr>
  <th>Time</th><th>Type</th><th>Status</th>
  <th>STT ms</th><th>LLM ms</th><th>TTS ms</th><th>Total ms</th>
  <th>Transcript</th><th>Reply / Error</th>
</tr></thead>
<tbody id="tbody"></tbody>
</table>
<script>
async function load(){
  const r=await fetch('/api/logs',{headers:{Authorization:'Bearer '+window.RONNY_API_TOKEN||''}});
  const {logs}=await r.json();
  document.getElementById('count').textContent='('+logs.length+' rows)';
  const tb=document.getElementById('tbody');
  for(const l of logs){
    const tr=document.createElement('tr');
    const status=l.status==='success'?'<span class="ok">✓</span>':'<span class="err">✗</span>';
    const type=l.input_type==='voice'?'<span class="voice">voice</span>':'<span class="text">text</span>';
    const ts=l.ts?l.ts.replace('T',' ').slice(0,19):'';
    const err=l.error||l.reply||'';
    tr.innerHTML=`
      <td class="ts">${ts}</td>
      <td>${type}</td>
      <td>${status}</td>
      <td class="ms">${l.stt_ms||0}</td>
      <td class="ms">${l.llm_ms||0}</td>
      <td class="ms">${l.tts_ms||0}</td>
      <td class="ms">${l.total_ms||0}</td>
      <td>${esc(l.transcript||'')}</td>
      <td>${esc(err)}</td>`;
    tb.appendChild(tr);
  }
}
function esc(s){return s.replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')}
load();
</script>
</body>
</html>"""
    # Inject token so the viewer's fetch can auth
    import json as _json
    token = _settings.API_TOKEN if _settings else ""
    html = html.replace("window.RONNY_API_TOKEN||''", f"'{token}'", 1)
    return HTMLResponse(html)


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
