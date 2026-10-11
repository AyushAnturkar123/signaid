"""SignAid server: serves the web app, recognizes signs, and talks to Gemini.

Run from the repo root:  uvicorn server.main:app --reload
"""

import logging
from pathlib import Path
from time import monotonic  # module-level so tests can swap in a fake clock

from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from . import llm
from .classifier import SignClassifier
from .signs import ALL_LABELS, CONTROLS, MODES
from .smoothing import Smoother

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("signaid")
# Show SignAid's own messages (e.g. Gemini timing) in the uvicorn terminal.
if not log.handlers:
    _handler = logging.StreamHandler()
    _handler.setFormatter(logging.Formatter("%(levelname)s:     %(name)s - %(message)s"))
    log.addHandler(_handler)
    log.setLevel(logging.INFO)

app = FastAPI(title="SignAid")
classifier = SignClassifier(ROOT / "server" / "data" / "samples")


class Hand(BaseModel):
    handedness: str | None = None
    points: list[list[float]]


class SamplesIn(BaseModel):
    label: str
    signer: str
    left_handed: bool = False
    frames: list[list[Hand]]


class TextIn(BaseModel):
    text: str


class AnswerIn(BaseModel):
    signs: list[str]
    mode: str = "free"
    question: str = ""


class LogEntry(BaseModel):
    role: str
    text: str


class SummaryIn(BaseModel):
    log: list[LogEntry]


@app.websocket("/ws/signs")
async def signs_socket(ws: WebSocket):
    """Browser sends hand landmarks ~15x a second; server replies with a live
    "prediction" for every frame and a "sign" event once a sign is held steadily."""
    await ws.accept()
    smoother = Smoother()
    mode = None
    try:
        while True:
            msg = await ws.receive_json()
            if msg.get("mode") != mode:
                mode = msg.get("mode")
                smoother.reset()
            hands = msg.get("hands") or []
            try:
                label, confidence, distance = classifier.predict(mode, hands, msg.get("left_handed", False))
            except (ValueError, KeyError, TypeError):
                continue  # skip a malformed frame
            await ws.send_json({
                "type": "prediction",
                "label": label,
                "confidence": round(confidence, 2),
                "distance": None if distance is None else round(distance, 2),
            })
            accepted = smoother.update(label, confidence, monotonic(), bool(hands))
            if accepted:
                await ws.send_json({"type": "sign", "label": accepted, "confidence": round(confidence, 2)})
    except WebSocketDisconnect:
        pass


@app.get("/api/health")
def health():
    """Quick pre-demo check: is Gemini set up, and which signs have samples?"""
    counts = classifier.counts()
    modes = {
        mode: {
            "signs_with_samples": sum(1 for label in labels if counts.get(label)),
            "signs_total": len(labels),
            "missing": [label for label in labels if not counts.get(label)],
        }
        for mode, labels in MODES.items()
    }
    controls = {
        "signs_with_samples": sum(1 for label in CONTROLS if counts.get(label)),
        "signs_total": len(CONTROLS),
        "missing": [label for label in CONTROLS if not counts.get(label)],
    }
    return {
        "status": "ok",
        "gemini": {
            "key_set": llm.key_is_set(),
            "model": llm.MODEL,
            "timeout_seconds": llm.TIMEOUT_SECONDS,
            "last_call": llm.last_call,
        },
        "samples": {
            "total": sum(counts.values()),
            "signers": classifier.signers(),
            "modes": modes,
            "controls": controls,
        },
    }


@app.get("/api/controls")
def get_controls():
    return CONTROLS


@app.get("/api/modes")
def get_modes():
    return MODES


@app.get("/api/samples")
def sample_counts():
    return classifier.counts()


@app.post("/api/samples")
def add_samples(body: SamplesIn):
    if body.label not in ALL_LABELS:
        raise HTTPException(400, f"Unknown sign: {body.label}")
    if not body.signer.strip():
        raise HTTPException(400, "Signer name is required")
    frames = [[h.model_dump() for h in hands] for hands in body.frames if hands]
    if not frames:
        raise HTTPException(400, "No frames with hands in them")
    try:
        count = classifier.add(body.label, frames, body.signer.strip(), body.left_handed)
    except ValueError as e:
        raise HTTPException(400, str(e))
    return {"label": body.label, "count": count}


@app.delete("/api/samples/{label}")
def delete_samples(label: str, signer: str | None = None):
    return {"removed": classifier.remove(label, signer)}


@app.post("/api/simplify")
def simplify(body: TextIn):
    return llm.simplify(body.text)


@app.post("/api/answer")
def answer(body: AnswerIn):
    return {"text": llm.answer(body.signs, body.mode, body.question)}


@app.post("/api/summary")
def summary(body: SummaryIn):
    # {"text": handoff note, "needs_attention": [...]}; the web page shows "text".
    return llm.summary_details([e.model_dump() for e in body.log])


class NoCacheStaticFiles(StaticFiles):
    """Make browsers check for a newer file on every load (a cheap 304 if unchanged).

    Without this, after a git pull the browser can keep running old JavaScript
    from its cache, with no sign that anything is out of date.
    """

    async def get_response(self, path, scope):
        response = await super().get_response(path, scope)
        response.headers["Cache-Control"] = "no-cache"
        return response


# Mounted last so the API routes above take priority.
app.mount("/", NoCacheStaticFiles(directory=ROOT / "web", html=True), name="web")
