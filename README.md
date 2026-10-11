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
| **Free** | Patient starts saying something themselves | YES, NO, and the 8 medical signs below |
| **Pain location** | Patient shows where the pain is | CHEST, HEAD, LEGS |

Gemini doesn't pick Pain location yet: switch to it with the on-screen mode button.

### No movement

Every sign is recorded and recognized as a **held handshape with no movement**. Many of these signs normally move in ASL (YES nods, HELP lifts); here you make the final shape and hold it still for about half a second. Palm directions below are as seen by the medic, facing the signer.

### Yes/No mode

| Sign | Hold this |
|---|---|
| YES | Fist with the thumb across the front of the fingers (S hand), bent forward at the wrist, palm facing down |
| NO | Index and middle fingers straight and together, pressed down onto the thumb tip (like a closed beak) |

### Number mode

| Sign | Hold this |
|---|---|
| 1 | Index finger up, palm facing you (the signer) |
| 2 | Index and middle fingers up, spread, palm facing you |
| 3 | Thumb, index and middle fingers out, palm facing you |
| 4 | Four fingers up and spread, thumb folded into the palm, palm facing you |
| 5 | All five fingers spread, palm facing you |
| 6 | Thumb touches the pinky tip; index, middle and ring up. Palm facing out |
| 7 | Thumb touches the ring finger tip; index, middle and pinky up. Palm facing out |
| 8 | Thumb touches the middle finger tip; index, ring and pinky up. Palm facing out |
| 9 | Thumb touches the index tip; middle, ring and pinky up. Palm facing out |
| 10 | Fist with the thumb pointing straight up (thumbs up), held still |

6–9 differ only by which finger the thumb touches, so test them early. The on-screen pain scale is the backup.

### Spelling mode

J and Z need motion, so they're typed on the on-screen keyboard. Palm faces out unless noted.

| Letter | Hold this | Letter | Hold this |
|---|---|---|---|
| A | Fist, thumb resting up against the side of the index | M | Index, middle and ring fingers folded over the thumb |
| B | Four fingers straight up together, thumb folded across the palm | N | Index and middle fingers folded over the thumb |
| C | Hand curved into a C, seen from the side | O | All fingertips touching the thumb tip, making an O |
| D | Index up; other fingertips touch the thumb, making a circle | P | Like K, but pointing down |
| E | Fingertips curled down onto the thumb, which is tucked across the palm | Q | Like G, but pointing down |
| F | Thumb and index tips touch; other three fingers up and spread | R | Index and middle fingers crossed, pointing up |
| G | Index and thumb pointing sideways, parallel; other fingers closed | S | Fist, thumb across the front of the fingers |
| H | Index and middle fingers together, pointing sideways | T | Thumb tucked between the index and middle fingers |
| I | Fist with the pinky up | U | Index and middle fingers up, together |
| K | Index up, middle angled forward, thumb between them | V | Index and middle fingers up, spread |
| L | Index up and thumb out, making an L | W | Index, middle and ring fingers up and spread; thumb holds the pinky |
| | | X | Index finger bent into a hook; other fingers closed |
| | | Y | Thumb and pinky out, other fingers closed |

Letters that look alike as still shapes: A/S/T/M/N/E (fist family), U/V/R, G/H, K/P, G/Q. Watch these in the evaluation.

### Free mode: medical signs

| # | Sign | Hold this |
|---|---|---|
| 1 | PAIN | Both index fingers pointing at each other, tips almost touching, in front of the chest (body map gives the location) |
| 2 | HELP | Thumbs-up fist resting on the other hand's flat, upturned palm |
| 3 | WATER | W hand with the index finger touching the chin |
| 4 | FOOD / EAT | Flat O (fingers straight, all fingertips touching the thumb) touching the lips |
| 5 | BATHROOM | T hand held up in front of the shoulder, palm out |
| 6 | COLD | Both fists (S hands) in front of the chest, elbows tucked in |
| 7 | STOP | Other hand flat, palm up; the edge (pinky side) of the flat dominant hand resting across it |
| 8 | PHONE / CALL | Y hand at the side of the face, thumb at the ear, pinky near the mouth |

YES and NO are also in Free mode, so the patient can answer yes or no at any time. They don't clash with the medical signs: COLD is two fists, YES is one.

Every free-mode sign has a different handshape, so recognition doesn't need face tracking for location.

### Pain location mode

Three two-hand gestures for where the pain is. They are made up for SignAid, not ASL signs, so the medic and patient need the guide.

| Sign | Hold this |
|---|---|
| CHEST | Arms crossed into an X |
| HEAD | Both hands flat, held high |
| LEGS | Both hands with the fingers facing outward |

No samples are recorded yet, so none of the three is recognized until the team records them in **Record signs** (group "Pain location"). HEAD (both hands flat) is close to DONE (both hands open, palms to the camera), and the control signs are listened for in every mode, so run `python scripts/evaluate.py --mode location` after recording to check they don't clash.

### Control signs

The patient controls the app with three signs, so they never need to touch it. They work in **every mode**, and must be held for **1 second** (answer signs need 0.5 s), so they don't fire by accident.

| Sign | Hold this | What it does |
|---|---|---|
| DONE | Both hands open, fingers spread, palms facing the camera, side by side | Send the answer: it's spoken to the medic right away |
| CLEAR | Both fists side by side, thumbs pointing down | Empty the answer |
| DELETE | Both index fingers pointing left, side by side | Remove the last sign |

They're two-hand gestures, so they never clash with one-hand letters and numbers. They're listed separately from the modes (`GET /api/controls`), and `scripts/evaluate.py` checks them in every mode, so a clash with any answer sign shows up in the report.

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
- **Two-hand signs where one hand rests on the other (HELP, STOP):** hold both hands apart in view until MediaPipe draws dots on both, then bring them together. If a hand is hidden when tracking starts, it never gets found. Do this during the countdown, so recording starts with the hands already in place. Same rule when signing live.
- Final samples are recorded on the demo laptop, in demo-like lighting.

### Checking that signs register

1. **Tracking (no code):** try each sign in the MediaPipe Studio hand landmarker demo. If the dots don't follow the fingers, or a hand disappears in a two-hand sign, replace the sign.
2. **Classifier:** about 20 samples per sign from every teammate, then run `python scripts/evaluate.py` (see [Evaluating the classifier](#evaluating-the-classifier)). Target: about 90% correct per sign.
3. **Live:** 10 tries per sign in the app, including people outside the team, different lighting, distance and sleeves. Weak signs at hour 16 become phrase board buttons.

## Project structure

```
server/                 Python backend (run with uvicorn)
  main.py               FastAPI app: serves web/, WebSocket, API routes
  signs.py              sign list, grouped by recognition mode
  normalize.py          hand landmarks -> fixed-length list of numbers
  classifier.py         nearest-neighbor classifier (the recorded samples are the model)
  smoothing.py          accepts a sign only after it's held ~0.5 s
  llm.py                Gemini prompts, with offline fallbacks
  data/samples/         recorded samples, one JSON file per signer
web/                    Frontend (plain HTML/CSS/JS, no build step)
  index.html, signaid.css
  main.js               conversation loop, wires everything together
  camera.js             webcam + MediaPipe hand tracking
  socket.js             WebSocket to the classifier
  speech.js             speech-to-text and text-to-speech
  recorder.js           "Record signs" panel
  api.js                HTTP calls to the server
  ui/                   on-screen pieces of the hands-free flow
    alerts.js           "New question" flash, "Said to medic" banner
    control-guide.js    DONE / CLEAR / DELETE guide next to the camera
    phone.js            keeps a phone's screen awake
  manifest.json, icons/ lets a phone add SignAid to its home screen
```

## Setup

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env   # then add your GEMINI_API_KEY
```

### Gemini key

The key goes in a file called `.env` in the repo root. The server reads it when it starts.

1. Copy the template: `cp .env.example .env`
2. Open `.env` and put your key after `GEMINI_API_KEY=`, with no spaces or quotes.
3. Restart the server.

```
GEMINI_API_KEY=your-key-here
GEMINI_MODEL=gemini-flash-lite-latest
GEMINI_TIMEOUT_SECONDS=10
```

`.env` is git-ignored, so it is never committed. Never put a real key in `.env.example`: that file is tracked, and the server doesn't read it.

`GEMINI_MODEL` and `GEMINI_TIMEOUT_SECONDS` are optional, and default to `gemini-flash-latest` and 5 seconds. The two values above are the ones that worked when the prompts were tested (October 2026): the API rejected a 5-second deadline ("minimum allowed deadline is 10s"), and `gemini-flash-latest` timed out while `gemini-flash-lite-latest` answered in about half a second. If every call falls back, try them.

To check the key, open http://localhost:8000/api/health: `gemini.key_set` should be `true`, and after one question `gemini.last_call.result` should be `"ok"`. Anything else there is the reason Gemini fell back.

The app works without a Gemini key: questions and answers pass through unchanged, the answer mode is guessed from simple keywords, and the handoff summary is the plain transcript.

If Gemini is slower than the timeout or fails, the app uses the same offline fallback, so it never freezes. The server terminal logs every Gemini call (`Gemini answer ok in 0.84s`, or the reason it fell back). Before a demo, open http://localhost:8000/api/health to check that Gemini is working and every sign has samples.

## Run

```bash
source .venv/bin/activate
uvicorn server.main:app --reload
```

Open http://localhost:8000 in **Chrome** and click Start. Allow camera and microphone access. If speech recognition struggles, type the medic's words in the box under the question.

## Using it on a phone

SignAid runs in the phone's browser and can be added to the home screen, where it opens like an app: its own icon, no browser bars, and the screen stays awake. The Python server still runs on a laptop; the phone is the camera, microphone and screen.

On a phone the page is one column: the medic's question, the camera, what you signed, then the guides. **Full screen** on the camera shows just the video with the question and your answer underneath.

A phone only allows the camera and microphone on an **https** address (or `localhost`), so opening `http://<laptop-ip>:8000` over Wi-Fi does not work. Two ways around that:

**Android, by USB cable (nothing is public)**

1. Start the server on the laptop as usual.
2. Plug the phone in, turn on USB debugging, and open `chrome://inspect/#devices` in Chrome on the laptop.
3. Click **Port forwarding**, add port `8000` -> `localhost:8000`, and tick **Enable port forwarding**.
4. Open `http://localhost:8000` in Chrome on the phone.

**Any phone, with an https tunnel**

```bash
uvicorn server.main:app --reload            # terminal 1
cloudflared tunnel --url http://localhost:8000   # terminal 2, prints an https://....trycloudflare.com address
```

Open that https address on the phone. While the tunnel is running, anyone who has the address can use the app, including your Gemini key and the "Record signs" panel, so stop it (Ctrl+C) when you're done and don't share the address.

**Add it to the home screen**

- Android (Chrome): menu -> **Add to Home screen** (or **Install app**).
- iPhone (Safari): Share -> **Add to Home Screen**.

Notes:

- Use Chrome on Android. On an iPhone, speech recognition is less reliable; the "type what the medic said" box always works.
- Prop the phone upright, far enough back that both hands fit in the picture.
- It is a web app, not an App Store or Play Store app.

## Tests

```bash
pip install -r requirements-dev.txt
pytest
```

The tests use fake hands and a temporary samples folder, so they need no camera, never call Gemini, and never touch real recordings. Run them before you push.

## Trying the Gemini prompts

The tests never call Gemini, so the prompts in `server/llm.py` are checked with a separate script that uses the real key in `.env`:

```bash
python scripts/try_prompts.py | tee scripts/try_prompts_output.txt
python scripts/try_prompts.py --pause 0     # no waiting, on a paid key
```

It sends 12 medic questions, 10 signed answers and 3 full conversations through `simplify`, `answer` and `summary`, and prints each input and output, the time taken, and whether the offline fallback was used. The last line counts how many calls Gemini answered.

A free key allows about 20 requests a minute; after that Gemini answers 429 and the fallback runs. The script waits 4 seconds before each call to stay under that, so a run takes about 2 minutes.

Run it after changing a prompt, read the output against these rules, and commit `scripts/try_prompts_output.txt` with the change:

- **Questions:** at most 15 words, no medical jargon, and a mode the patient can answer in.
- **Answers:** first person, one short sentence, nothing the patient didn't sign, spelled words unchanged.
- **Summary:** only facts the patient confirmed, never a diagnosis, "not asked" for anything missing.

## Recording samples

1. Click **Record signs**, enter your name, and pick a sign.
2. Click **Record 20 samples**, hold the sign after the countdown, and move your hand slightly between samples.
3. Aim for 60+ samples per sign (chips turn green), from several people.

Samples are saved to `server/data/samples/<your-name>.json`. Commit your file so the whole team shares the same data. Each person has their own file, so there are no merge conflicts.

The live label in the camera view shows the distance to the closest sample. If real signs show as "Not a known sign", raise `MAX_DISTANCE` in `server/classifier.py`. If random poses get recognized, lower it.

## Follow-up questions

After the patient answers, SignAid can ask **one short follow-up** on screen and switch to the tab the patient answers in. For example, the patient signs PAIN and DONE, and SignAid asks "How bad is your pain, 1 to 10?" in Number mode, then "Where is the pain?" in **Pain location** mode (CHEST, HEAD, LEGS), then Gemini asks "Did it start suddenly?" in Yes/No mode.

- **The pain steps are a fixed rule**, not Gemini: pain level first, then location, always in that order, also offline. It skips the level if the patient already gave one, and never asks after a "no pain" answer. Gemini handles every other follow-up (allergies, medications, HELP, onset).
- Gemini also knows the Pain location tab: a medic asking "Where does it hurt?" switches to it, and CHEST becomes "The pain is in my chest."

- The question card shows **"SignAid asks"** instead of "Medic said", and the log shows **SignAid:**. Follow-ups are included in the handoff summary.
- **At most 3 follow-ups in a row**, then SignAid waits for the medic. A new medic question always takes over.
- Never a diagnosis, cause or advice, and never the same question twice.
- **Offline fallback** (no key, timeout or rate limit): the pain steps still run; other follow-ups are skipped.

Try it with the real key (it checks the mode, length, repeats and diagnosis words):

```bash
python scripts/try_followups.py
```

The free Gemini tier has a **per-minute limit**. Running many calls back to back returns error 429 and the app uses the offline fallback for a minute. Avoid heavy testing right before a demo.

## Evaluating the classifier

```bash
python scripts/evaluate.py
python scripts/evaluate.py --mode number         # one mode only
python scripts/evaluate.py --max-distance 3.0    # try a different cutoff
```

It tests each person against a classifier built from everyone else's samples, which is what happens with a real patient or a judge. For every sign it prints how often it was recognized, how often it was rejected as "not a known sign", and what it was mistaken for. Signs below 90% are marked `!!`.

It also suggests a `MAX_DISTANCE` value from the real data. That needs samples from at least 2 people.

What to do with weak signs: if two signs are mistaken for each other, re-record both and copy the reference video exactly. If one person scores much lower than the others, check their recordings. If a sign is still weak at hour 16, move it to the phrase board.

## Message formats

### WebSocket `/ws/signs`

Browser → server, about 15 times a second:

```json
{"type": "landmarks", "mode": "yesno", "left_handed": false,
 "hands": [{"handedness": "Right", "points": [[0.51, 0.62, -0.01], "...21 points"]}]}
```

Server → browser, for every frame (`label` is `null` when no sign matches):

```json
{"type": "prediction", "label": "YES", "confidence": 0.8, "distance": 1.2}
```

Once a sign has been held steadily (0.5 s, or 1 s for control signs), the server also sends:

```json
{"type": "sign", "label": "YES", "confidence": 0.8}
```

### HTTP routes

| Route | Request body | Response |
|---|---|---|
| `GET /api/health` | | Gemini status (key set, last call result and time) and which signs still need samples |
| `GET /api/controls` | | `["DONE", "CLEAR", "DELETE"]`, recognized in every mode |
| `GET /api/modes` | | `{"yesno": ["YES", "NO"], ...}` |
| `GET /api/samples` | | sample counts, `{"YES": 40, ...}` |
| `POST /api/samples` | `{"label", "signer", "left_handed", "frames": [hands, ...]}` | `{"label", "count"}` |
| `DELETE /api/samples/{label}?signer=Name` | | `{"removed": 20}` |
| `POST /api/simplify` | `{"text": "medic's words"}` | `{"text": "plain version", "mode": "yesno"}` |
| `POST /api/answer` | `{"signs": ["8"], "mode": "number", "question": "..."}` | `{"text": "8 out of 10."}` |
| `POST /api/follow-up` | `{"log": [...]}` (same as summary) | `{"question": "How bad is your pain, 1 to 10?", "mode": "number"}`, or both `null` |
| `POST /api/summary` | `{"log": [{"role": "medic", "text": "..."}]}` | `{"text": "handoff note", "needs_attention": ["chest pain with trouble breathing"]}` |

### Handoff summary

`POST /api/summary` asks Gemini for JSON, and the server turns it into the note. Gemini's reply has these fields:

```json
{"chief_complaint": "chest pain",
 "pain": {"level": "8", "location": "chest"},
 "allergies": "not asked",
 "medications": "denies taking any medication",
 "other_answers": ["trouble breathing"],
 "needs_attention": ["chest pain", "trouble breathing"]}
```

The route returns the note as `text`, which the web page shows, plus the `needs_attention` list on its own:

```
Patient is Deaf and needs an ASL interpreter.

Needs attention (the patient's own answers, not a diagnosis):
- Flagged for attention: chest pain
- Flagged for attention: trouble breathing

Chief complaint: chest pain
Pain level: 8 out of 10
Pain location: chest
Allergies: not asked
Medications: denies taking any medication
Other answers:
- trouble breathing
```

- The first line is always the same. The "Needs attention" section only appears when the list isn't empty.
- `needs_attention` holds answers a clinician should look at first. They restate what the patient confirmed; they are never a diagnosis, a triage level or medical advice.
- Every field uses only what the patient confirmed, and "not asked" for anything the conversation didn't cover.
- With no key, a timeout, an error, or JSON that is invalid or missing a field, `text` is the first line followed by the plain transcript, and `needs_attention` is `[]`.

## Team

- TBD
