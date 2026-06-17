# Personal AI Assistant — Ronny

A Python-based voice AI assistant that controls smart home devices, orders food, manages your Google Calendar, and places outbound phone calls — all via voice commands. Powered by Groq LLM, Sarvam Indian-English speech services, and deployed as a web app accessible from anywhere.

---

## Phases

### ✅ Phase 1 — Home Assistant Control
- Browser-based dark UI with animated glowing sphere (4 states: idle, listening, thinking, speaking)
- Voice and text input with push-to-talk (hold Space or tap button)
- Controls lights, switches, fans, scenes, climate, and media players via Home Assistant REST API
- Sarvam AI for Indian-English STT (`saarika:v2.5`) and TTS (`bulbul:v3`, speaker: rahul)
- Groq `llama-3.3-70b-versatile` as the LLM with OpenAI-compatible function calling
- Deployed as a FastAPI web server exposed via Cloudflare Tunnel (`asistant.rvhome.space`)

### 🔄 Phase 2 — Swiggy Food & Grocery Ordering *(waiting for OAuth token)*
- Order food from restaurants via Swiggy voice commands
- Order groceries via Swiggy Instamart
- Book dine-out restaurant tables (free reservations)
- Physical confirmation modal in the browser UI before any order is placed
- Cash on Delivery payment (COD only, ₹1,000 cart cap per Swiggy Builders Club v1)
- Address management — ask user to choose from saved addresses

### ✅ Phase 3 — Google Calendar Integration
- List upcoming events: *"What's on my calendar this week?"*
- Create events: *"Add a meeting called Design Review at 3pm tomorrow"*
- Delete events: *"Cancel my 5pm appointment"*
- Check availability: *"Am I free on Friday?"*
- OAuth2 authorization with auto token refresh

### ✅ Phase 4 — Outbound Phone Calling
- Place PSTN calls on the user's behalf via LiveKit SIP: *"Call mom and tell her I'll be late"*
- Ronny introduces itself as "the user's personal AI assistant" and delivers the message in third person
- Live voice conversation on the call — STT, LLM, TTS pipeline runs inside the call
- Extracts the other person's response and reports back: *"They said okay, no problem"*
- Contact book (`contacts.json`) with fuzzy name lookup
- Add contacts at runtime: *"Save John's number as +91XXXXXXXXXX"*
- Powered by LiveKit cloud (India West region), Groq LLM, and Sarvam TTS/STT

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | Groq `llama-3.3-70b-versatile` |
| STT | Sarvam AI `saarika:v2.5` |
| TTS | Sarvam AI `bulbul:v3` (speaker: rahul) |
| Home Automation | Home Assistant REST API |
| Food Ordering | Swiggy Builders Club MCP API (OAuth 2.1) |
| Calendar | Google Calendar API v3 (OAuth2) |
| Calling | LiveKit Agents + SIP trunk (outbound PSTN) |
| Backend | FastAPI + uvicorn |
| Frontend | Vanilla JS, Web Audio API, MediaRecorder |
| Deployment | Cloudflare Tunnel → `asistant.rvhome.space` |

---

## Setup

### 1. Clone and install dependencies

```bash
git clone https://github.com/rohanpatil1794/personal-ai-assistant.git
cd personal-ai-assistant
python -m venv venv
venv\Scripts\activate        # Windows
pip install -r requirements.txt
```

### 2. Configure credentials

Copy `.env.example` to `.env` and fill in your keys:

```env
GROQ_API_KEY=...             # console.groq.com
SARVAM_API_KEY=...           # app.sarvam.ai
HA_URL=http://192.168.x.x:8123
HA_TOKEN=...                 # HA → Profile → Long-Lived Access Tokens
SWIGGY_ACCESS_TOKEN=...      # Swiggy Builders Club OAuth 2.1 token (optional)
GROQ_MODEL=llama-3.3-70b-versatile   # optional — override the default model
TTS_SPEAKER=Rahul            # optional — Sarvam TTS voice

# LiveKit — calling module (leave blank to disable)
LIVEKIT_URL=wss://your-project.livekit.cloud
LIVEKIT_API_KEY=...
LIVEKIT_API_SECRET=...
LIVEKIT_SIP_TRUNK_ID=...     # Dashboard → SIP → Trunks → outbound trunk ID
CALLING_AGENT_CALLBACK_BASE=http://localhost:8000
```

### 3. Set up Google Calendar (optional)

1. Go to [console.cloud.google.com](https://console.cloud.google.com) → create a project
2. Enable **Google Calendar API** (APIs & Services → Library)
3. Create OAuth client ID (Desktop app type) → download JSON → save as `credentials.json` in project root
4. Add your Gmail as a test user under OAuth consent screen
5. Run the one-time auth script:

```powershell
venv\Scripts\python integrations\google_auth.py
```

A browser window will open for authorization. After approving, `token.json` is saved and auto-refreshed on future runs.

### 4. Set up phone calling (optional)

1. Sign up at [livekit.io](https://livekit.io) → create a project → copy URL, API key, secret into `.env`
2. Dashboard → SIP → Trunks → create an outbound SIP trunk → copy trunk ID into `.env`
3. Add contacts to `contacts.json`:
```json
{
  "mom": "+91XXXXXXXXXX",
  "dad": "+91XXXXXXXXXX",
  "rahul": "+91XXXXXXXXXX"
}
```

### 5. Run

Start both processes (two terminal windows):

```powershell
# Window 1 — main assistant server
venv\Scripts\uvicorn server:app --host 0.0.0.0 --port 8000

# Window 2 — calling agent worker (needed for outbound calls)
venv\Scripts\python calling_agent.py dev
```

Open `http://localhost:8000` in your browser.

---

## Usage

- **Voice:** Hold **Space** (or the Hold to Talk button) → speak → release
- **Text:** Type a message and press **Enter** or click **Send**
- **Home control:** *"Turn off the AC"*, *"Dim the bedroom lights to 40%"*, *"Activate movie night scene"*
- **Food order:** *"Order butter chicken from Behrouz"* → Ronny searches, builds cart, shows confirmation modal → click **Confirm Order**
- **Grocery:** *"Get 2 litres of milk from Instamart"* → same flow
- **Dine-out:** *"Book a table for 2 at an Italian restaurant tonight"*
- **Calendar:** *"What's on my calendar today?"*, *"Add a dentist appointment at 11am on Monday"*, *"Am I free this Saturday?"*
- **Phone calls:** *"Call mom and tell her I'll be late"*, *"Call John and ask if he's coming tonight"* → Ronny calls, talks, and reports back what they said

---

## Project Structure

```
server.py               FastAPI entry point
config/                 Credential management (pydantic-settings)
core/                   ConversationManager — LLM loop, tool dispatch, pending order state
services/               Groq LLM client, Sarvam STT/TTS
integrations/
  ha_client.py          Home Assistant REST client
  ha_tools.py           HA tool declarations (OpenAI schema)
  swiggy_client.py      Swiggy REST client (food, Instamart, Dineout)
  swiggy_tools.py       Swiggy tool declarations (OpenAI schema)
  google_calendar_client.py   Google Calendar API client (OAuth2)
  google_calendar_tools.py    Calendar tool declarations (OpenAI schema)
  google_auth.py        One-time OAuth2 authorization script
  livekit_client.py     LiveKit REST client (room, SIP, agent dispatch)
  calling_integration.py  Calling tool integration (place call, get result, contacts)
  calling_tools.py      Calling tool declarations (OpenAI schema)
  call_store.py         In-memory call record store
  contacts.py           Contact book backed by contacts.json
calling_agent.py        LiveKit Agents worker — runs the voice pipeline on outbound calls
contacts.json           Phone contacts (name → E.164 number, never committed with real numbers)
web/
  index.html            Single-page app shell
  static/style.css      Dark theme + sphere animations + order modal
  static/app.js         MediaRecorder, Web Audio, state machine, confirmation modal
utils/                  Logger, custom exceptions
```

---

## Deployment (Cloudflare Tunnel)

```powershell
cloudflared tunnel login
cloudflared tunnel create rvhome
cloudflared tunnel route dns rvhome asistant.rvhome.space
cloudflared service install   # run as Administrator — auto-starts on boot
uvicorn server:app --host 0.0.0.0 --port 8000
```
