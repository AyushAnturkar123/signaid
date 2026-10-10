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
from .signs import ALL_LABELS, MODES
from .smoothing import Smoother

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger("signaid")

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
    return {"text": llm.summary([e.model_dump() for e in body.log])}


# Mounted last so the API routes above take priority.
app.mount("/", StaticFiles(directory=ROOT / "web", html=True), name="web")
