# Personal AI Assistant

A Python-based voice AI assistant with Home Assistant integration, powered by Google Gemini and Sarvam speech services.

## Features (Phase 1)

- Dark-themed desktop UI with animated glowing sphere
- Voice control for Home Assistant (lights, switches, scenes)
- Sarvam STT/TTS for Indian-English speech
- Google Gemini as the LLM brain with function calling

## Setup

1. **Clone the repo and install dependencies:**
   ```bash
   pip install -r requirements.txt
   ```

2. **Configure credentials:**
   Copy `.env.example` to `.env` and fill in your keys:
   ```
   GEMINI_API_KEY=...
   SARVAM_API_KEY=...
   HA_URL=http://192.168.x.x:8123
   HA_TOKEN=...
   ```
   Alternatively, launch the app and fill in credentials via the UI dialog.

3. **Get a Home Assistant Long-Lived Access Token:**
   HA → Profile → Long-Lived Access Tokens → Create Token

4. **Run:**
   ```bash
   python main.py
   ```

## Usage

- Click the sphere (or press **Space**) to start listening
- Speak your command, e.g. "Turn off the living room lights"
- The assistant executes the command and speaks a confirmation

## Project Structure

```
config/         Credential management
core/           Orchestrator, conversation, state machine
services/       Audio I/O, Sarvam STT/TTS, Gemini client
integrations/   Home Assistant REST client + Gemini tool declarations
ui/             CustomTkinter UI — sphere, chat panel, credential dialog
utils/          Logger, custom exceptions
```

## Roadmap

- [ ] Phase 2: Zomato food ordering
- [ ] Phase 3: Movie ticket booking
