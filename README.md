# Personal AI Assistant — Ronny

A Python-based voice AI assistant that controls smart home devices and orders food via voice commands. Powered by Groq LLM, Sarvam Indian-English speech services, and deployed as a web app accessible from anywhere.

---

## Phases

### ✅ Phase 1 — Home Assistant Control
- Browser-based dark UI with animated glowing sphere (4 states: idle, listening, thinking, speaking)
- Voice and text input with push-to-talk (hold Space or tap button)
- Controls lights, switches, fans, scenes, climate, and media players via Home Assistant REST API
- Sarvam AI for Indian-English STT (`saarika:v2.5`) and TTS (`bulbul:v3`, speaker: rahul)
- Groq `llama-3.1-8b-instant` as the LLM with OpenAI-compatible function calling
- Deployed as a FastAPI web server exposed via Cloudflare Tunnel (`assistant.rvhome.space`)

### 🔄 Phase 2 — Swiggy Food & Grocery Ordering *(in progress — awaiting OAuth token)*
- Order food from restaurants via Swiggy voice commands
- Order groceries via Swiggy Instamart
- Book dine-out restaurant tables (free reservations)
- Physical confirmation modal in the browser UI before any order is placed
- Cash on Delivery payment (COD only, ₹1,000 cart cap per Swiggy Builders Club v1)
- Address management — ask user to choose from saved addresses or add a new one

### 📋 Phase 3 — Movie Ticket Booking *(planned)*

---

## Tech Stack

| Layer | Technology |
|-------|-----------|
| LLM | Groq `llama-3.1-8b-instant` |
| STT | Sarvam AI `saarika:v2.5` |
| TTS | Sarvam AI `bulbul:v3` (speaker: rahul) |
| Home Automation | Home Assistant REST API |
| Food Ordering | Swiggy Builders Club MCP API (OAuth 2.1) |
| Backend | FastAPI + uvicorn |
| Frontend | Vanilla JS, Web Audio API, MediaRecorder |
| Deployment | Cloudflare Tunnel → `assistant.rvhome.space` |

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
SWIGGY_ACCESS_TOKEN=...      # Swiggy Builders Club OAuth 2.1 token (leave blank if not using Swiggy)
```

### 3. Run

```bash
uvicorn server:app --host 0.0.0.0 --port 8000
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
cloudflared tunnel create assistant
cloudflared tunnel route dns assistant assistant.rvhome.space
cloudflared service install   # run as Administrator — auto-starts on boot
uvicorn server:app --host 0.0.0.0 --port 8000
```
