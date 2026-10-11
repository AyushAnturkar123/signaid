"""API tests using FastAPI's test client. A temporary samples folder replaces the
real one, so tests never read or change anyone's recordings."""

import json

import pytest
from fastapi.testclient import TestClient

from server import llm, main
from server.classifier import SignClassifier
from tests.conftest import make_hand


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "classifier", SignClassifier(tmp_path))
    return TestClient(main.app)


def record(client, label, shape, n=10, signer="Alice"):
    return client.post("/api/samples", json={
        "label": label,
        "signer": signer,
        "frames": [[make_hand(shape)] for _ in range(n)],
    })


def test_serves_the_web_app(client):
    res = client.get("/")
    assert res.status_code == 200
    assert "<title>SignAid</title>" in res.text


def test_web_files_are_always_rechecked(client):
    # so a git pull + reload never runs stale JavaScript from the browser cache
    assert client.get("/recorder.js").headers["cache-control"] == "no-cache"
    assert client.get("/").headers["cache-control"] == "no-cache"


def test_health_reports_gemini_and_samples(client):
    record(client, "YES", 1, n=4)
    record(client, "NO", 2, n=3, signer="Bob")
    health = client.get("/api/health").json()
    assert health["status"] == "ok"
    assert health["gemini"]["key_set"] is False
    assert health["gemini"]["timeout_seconds"] > 0
    assert health["samples"]["total"] == 7
    assert health["samples"]["signers"] == ["Alice", "Bob"]
    assert health["samples"]["modes"]["yesno"] == {"signs_with_samples": 2, "signs_total": 2, "missing": []}
    assert "PAIN" in health["samples"]["modes"]["free"]["missing"]


def test_modes(client):
    modes = client.get("/api/modes").json()
    assert modes["yesno"] == ["YES", "NO"]
    assert set(modes) == {"yesno", "number", "spelling", "free"}


def test_record_count_and_delete_samples(client):
    res = record(client, "YES", 1, n=10)
    assert res.status_code == 200
    assert res.json() == {"label": "YES", "count": 10}
    record(client, "YES", 1, n=5, signer="Bob")
    assert client.get("/api/samples").json() == {"YES": 15}

    res = client.delete("/api/samples/YES", params={"signer": "Alice"})
    assert res.json() == {"removed": 10}
    assert client.get("/api/samples").json() == {"YES": 5}


@pytest.mark.parametrize("body, message", [
    ({"label": "BANANA", "signer": "Alice", "frames": [[make_hand(1)]]}, "Unknown sign"),
    ({"label": "YES", "signer": "  ", "frames": [[make_hand(1)]]}, "Signer name"),
    ({"label": "YES", "signer": "Alice", "frames": [[]]}, "No frames"),
    ({"label": "YES", "signer": "Alice", "frames": [[{"points": [[0, 0, 0]] * 5}]]}, "21 points"),
])
def test_bad_samples_are_rejected(client, body, message):
    res = client.post("/api/samples", json=body)
    assert res.status_code == 400
    assert message in res.json()["detail"]


def test_simplify(client):
    res = client.post("/api/simplify", json={"text": "Do you feel dizzy?"})
    assert res.json() == {"text": "Do you feel dizzy?", "mode": "yesno"}


def test_answer(client):
    res = client.post("/api/answer", json={"signs": ["7"], "mode": "number", "question": "Pain?"})
    assert res.json() == {"text": "7 out of 10."}


SUMMARY_LOG = {"log": [
    {"role": "medic", "text": "Do you have any allergies?"},
    {"role": "patient", "text": "Yes."},
    {"role": "medic", "text": "What are you allergic to?"},
    {"role": "patient", "text": "PENICILLIN"},
]}
SUMMARY_JSON = {
    "chief_complaint": "not asked",
    "pain": {"level": "not asked", "location": "not asked"},
    "allergies": "penicillin",
    "medications": "not asked",
    "other_answers": [],
    "needs_attention": ["allergy to penicillin"],
}


def fake_gemini(monkeypatch, reply):
    """Replace the Gemini call with a canned reply, so the route never goes online."""
    monkeypatch.setattr(llm, "_gemini", lambda *args, **kwargs: reply)


def test_summary(client):
    # no key in tests, so this is the plain fallback
    res = client.post("/api/summary", json={"log": [{"role": "medic", "text": "Any allergies?"}]})
    assert res.status_code == 200
    assert res.json()["text"].startswith("Patient is Deaf")
    assert res.json()["needs_attention"] == []


def test_summary_returns_text_and_needs_attention(client, monkeypatch):
    fake_gemini(monkeypatch, json.dumps(SUMMARY_JSON))
    res = client.post("/api/summary", json=SUMMARY_LOG)
    assert res.status_code == 200
    body = res.json()
    assert set(body) == {"text", "needs_attention"}
    assert body["needs_attention"] == ["allergy to penicillin"]
    text = body["text"]
    assert text.startswith("Patient is Deaf and needs an ASL interpreter.")
    assert "- Flagged for attention: allergy to penicillin" in text
    assert text.index("Needs attention") < text.index("Chief complaint")
    assert "Allergies: penicillin" in text


def test_summary_without_flags_still_returns_both_fields(client, monkeypatch):
    fake_gemini(monkeypatch, json.dumps({**SUMMARY_JSON, "needs_attention": []}))
    body = client.post("/api/summary", json=SUMMARY_LOG).json()
    assert body["needs_attention"] == []
    assert "attention" not in body["text"].lower()
    assert "Allergies: penicillin" in body["text"]


@pytest.mark.parametrize("reply", [
    "not json at all",
    json.dumps({"chief_complaint": "not asked"}),  # most fields missing
    None,  # Gemini timed out or failed
])
def test_summary_falls_back_to_the_plain_note(client, monkeypatch, reply):
    fake_gemini(monkeypatch, reply)
    res = client.post("/api/summary", json=SUMMARY_LOG)
    assert res.status_code == 200
    body = res.json()
    assert body["text"].startswith("Patient is Deaf and needs an ASL interpreter.\n\nConversation:")
    assert "PATIENT: PENICILLIN" in body["text"]
    assert body["needs_attention"] == []


class FakeClock:
    """Each call moves time forward by `step` seconds, so hold-time tests don't depend on real timing."""

    def __init__(self, step):
        self.now = 0.0
        self.step = step

    def __call__(self):
        self.now += self.step
        return self.now


def test_websocket_accepts_sign_once_after_hold_time(client, monkeypatch):
    monkeypatch.setattr(main, "monotonic", FakeClock(step=0.1))
    record(client, "STOP", 5)
    frame = {"type": "landmarks", "mode": "free", "hands": [make_hand(5)]}
    with client.websocket_connect("/ws/signs") as ws:
        # Frames 1-5: 0.1 s to 0.5 s held, only predictions.
        for _ in range(5):
            ws.send_json(frame)
            prediction = ws.receive_json()
            assert prediction["type"] == "prediction"
            assert prediction["label"] == "STOP"
        # Frame 6: held for 0.5 s since the first frame, so a "sign" event follows.
        ws.send_json(frame)
        assert ws.receive_json()["type"] == "prediction"
        assert ws.receive_json() == {"type": "sign", "label": "STOP", "confidence": 1.0}
        # Still holding: predictions continue, but no second "sign" event.
        for _ in range(3):
            ws.send_json(frame)
            assert ws.receive_json()["type"] == "prediction"
        ws.send_json({"type": "landmarks", "mode": "free", "hands": []})
        assert ws.receive_json()["label"] is None


def test_websocket_no_hands(client):
    with client.websocket_connect("/ws/signs") as ws:
        ws.send_json({"type": "landmarks", "mode": "free", "hands": []})
        assert ws.receive_json() == {"type": "prediction", "label": None, "confidence": 0.0, "distance": None}


def test_websocket_skips_malformed_frame(client):
    record(client, "YES", 1)
    with client.websocket_connect("/ws/signs") as ws:
        ws.send_json({"type": "landmarks", "mode": "yesno", "hands": [{"points": [[0, 0, 0]] * 5}]})
        ws.send_json({"type": "landmarks", "mode": "yesno", "hands": [make_hand(1)]})
        # the bad frame gets no reply; the connection stays open for the good one
        assert ws.receive_json()["label"] == "YES"
