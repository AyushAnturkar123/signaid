# SignAid

An ASL communication aid for emergency medical situations. A Deaf patient answers a medic's questions with signs (YES/NO, pain 1–10, a few key medical signs, fingerspelling), and SignAid speaks the answers aloud and shows the medic's speech as large captions.

Built at HackNC 2026.

> SignAid is a communication aid, not a medical device, and not a replacement for a qualified ASL interpreter.

## How it works

- **Browser (`web/`):** webcam, MediaPipe hand tracking, speech-to-text and text-to-speech (Web Speech API), patient UI.
- **Python (`server/`):** FastAPI server, sign classifier (nearest-neighbor on hand landmarks), Gemini for plain-language questions, answers, and the handoff summary.

## Project structure

```
server/   Python backend (FastAPI, classifier, Gemini)
  data/   recorded sign samples
web/      Frontend (HTML/CSS/JS)
  ui/     UI components
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then add your GEMINI_API_KEY
```

Run instructions will be added once the server exists. Use Chrome for speech recognition.

## Team

- TBD
