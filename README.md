# SignAid

An ASL communication aid for emergency medical situations. A Deaf patient answers a medic's questions with signs (YES/NO, pain 1–10, a few key medical signs, fingerspelling), and SignAid speaks the answers aloud and shows the medic's speech as large captions.

Built at HackNC 2026.

> SignAid is a communication aid, not a medical device, and not a replacement for a qualified ASL interpreter.

## How it works

- **Browser (`web/`):** webcam, MediaPipe hand tracking, speech-to-text and text-to-speech (Web Speech API), patient UI.
- **Python (`server/`):** FastAPI server, sign classifier (nearest-neighbor on hand landmarks), Gemini for plain-language questions, answers, and the handoff summary.

## Sign list

### Recognition modes

The classifier only compares against the signs for the current mode. This avoids clashes between signs that share a handshape (YES and the letter S, 6 and W, 2 and V). Gemini picks the mode from the medic's question, and the patient can switch modes with on-screen buttons.

| Mode | When | Signs it listens for |
|---|---|---|
| **Yes/No** | Medic asks a yes/no question | YES, NO |
| **Number** | Medic asks for a pain score | 1–10 |
| **Spelling** | Patient spells a name, allergy or medication | A–Z except J and Z (on-screen keyboard for those) |
| **Free** | Patient starts saying something themselves | The 8 medical signs below |

### Yes/No mode

| Sign | Description |
|---|---|
| YES | Fist (S hand), nodding like a head |
| NO | Index and middle fingers close onto the thumb |

### Number mode

1–10. Numbers 6–9 are subtle (the thumb touches a different finger for each), so test them early. The on-screen pain scale is the backup.

### Spelling mode

A–Z except J and Z, which need motion and are typed on an on-screen keyboard.

### Free mode: medical signs

| # | Sign | Description |
|---|---|---|
| 1 | PAIN | Two index fingers point at each other and twist (body map gives the location) |
| 2 | HELP | Thumbs-up fist resting on the other flat palm, lifting |
| 3 | WATER | W hand taps the chin |
| 4 | FOOD / EAT | Flat O hand taps the mouth |
| 5 | BATHROOM | T hand shakes side to side |
| 6 | COLD | Both fists shake in front of the chest (shivering) |
| 7 | STOP | Edge of a flat hand chops down onto the other palm |
| 8 | PHONE / CALL | Y hand held at the side of the face |

Every free-mode sign has a different handshape, so recognition doesn't need face tracking for location.

### Cut from recognition

| Cut | Why | Covered by |
|---|---|---|
| Headache | Same handshape as PAIN | PAIN + tapping the head on the body map |
| Dizzy, Breathe, Tired, Nauseous, Fever | Depend on motion or location, or are easily confused | Medic asks ("Do you feel dizzy?"), patient answers YES/NO; also on the phrase board |
| Medications | One hand covers the other, which confuses hand tracking | Phrase board button + fingerspelling the drug name |
| Deaf | Motion between ear and mouth | Shown automatically at start: "I'm Deaf, I'll answer with signs" |

### Recording rules

- Watch each sign on [Lifeprint](https://www.lifeprint.com) or [Handspeak](https://www.handspeak.com), pick one version, and everyone copies it exactly.
- Sign with your dominant hand. Left-handed signers tell the vision person so their samples can be mirrored.
- Record YES, NO and 1–10 first.
- Final samples are recorded on the demo laptop, in demo-like lighting.

### Checking that signs register

1. **Tracking (no code):** try each sign in the MediaPipe Studio hand landmarker demo. If the dots don't follow the fingers, or a hand disappears in a two-hand sign, replace the sign.
2. **Classifier:** about 20 samples per sign from every teammate. Train on everyone but one person, test on that person, and check the confusion matrix. Target: about 90% correct per sign.
3. **Live:** 10 tries per sign in the app, including people outside the team, different lighting, distance and sleeves. Weak signs at hour 16 become phrase board buttons.

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
