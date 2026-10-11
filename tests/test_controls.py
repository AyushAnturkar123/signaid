"""Control signs (DONE, CLEAR, DELETE): recognized in every mode, held longer to count."""

import pytest
from fastapi.testclient import TestClient

from scripts import evaluate
from server import main
from server.classifier import SignClassifier
from server.signs import CONTROLS, MODES, labels_for
from server.smoothing import CONTROL_HOLD_SECONDS, HOLD_SECONDS, Smoother
from tests.conftest import make_hand


def two_hands(shape):
    return [make_hand(shape), make_hand(shape + 1, dx=0.25, handedness="Left")]


@pytest.fixture
def clf(tmp_path):
    c = SignClassifier(tmp_path)
    c.add("DONE", [two_hands(40) for _ in range(10)], "Alice")
    c.add("YES", [[make_hand(1)] for _ in range(10)], "Alice")
    c.add("5", [[make_hand(5)] for _ in range(10)], "Alice")
    return c


def test_controls_are_listed_separately_from_modes():
    assert CONTROLS == ["DONE", "CLEAR", "DELETE"]
    for labels in MODES.values():
        assert not set(CONTROLS) & set(labels)
    assert labels_for("yesno") == ["YES", "NO", "DONE", "CLEAR", "DELETE"]


@pytest.mark.parametrize("mode", list(MODES))
def test_control_is_recognized_in_every_mode(clf, mode):
    assert clf.predict(mode, two_hands(40))[0] == "DONE"


def test_answer_signs_still_stay_in_their_own_mode(clf):
    assert clf.predict("number", [make_hand(1)])[0] != "YES"
    assert clf.predict("yesno", [make_hand(5)])[0] != "5"


def hold(smoother, label, seconds, step=0.1):
    """Hold one sign for `seconds`; return the time it was accepted, or None."""
    for i in range(round(seconds / step) + 1):
        t = i * step  # multiply, don't add: adding 0.1 ten times gives 0.9999...
        if smoother.update(label, 1.0, t, True):
            return round(t, 2)
    return None


def test_control_needs_the_longer_hold():
    assert CONTROL_HOLD_SECONDS == 1.0
    assert hold(Smoother(), "DONE", CONTROL_HOLD_SECONDS - 0.1) is None
    assert hold(Smoother(), "DONE", CONTROL_HOLD_SECONDS) == CONTROL_HOLD_SECONDS


def test_answer_sign_keeps_the_short_hold():
    assert hold(Smoother(), "YES", 2.0) == HOLD_SECONDS


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, "classifier", SignClassifier(tmp_path))
    return TestClient(main.app)


@pytest.mark.parametrize("label", CONTROLS)
def test_control_samples_can_be_recorded(client, label):
    res = client.post("/api/samples", json={"label": label, "signer": "Alice", "frames": [two_hands(40)]})
    assert res.status_code == 200
    assert res.json() == {"label": label, "count": 1}


def test_controls_route(client):
    assert client.get("/api/controls").json() == ["DONE", "CLEAR", "DELETE"]


def test_modes_route_has_no_controls(client):
    modes = client.get("/api/modes").json()
    assert set(modes) == {"yesno", "number", "spelling", "free", "location"}
    assert not any(c in labels for labels in modes.values() for c in CONTROLS)


def test_health_reports_missing_controls(client):
    client.post("/api/samples", json={"label": "DONE", "signer": "Alice", "frames": [two_hands(40)]})
    controls = client.get("/api/health").json()["samples"]["controls"]
    assert controls == {"signs_with_samples": 1, "signs_total": 3, "missing": ["CLEAR", "DELETE"]}


def test_websocket_sends_control_in_any_mode(client, monkeypatch):
    clock = iter(i * 0.1 for i in range(1, 100))
    monkeypatch.setattr(main, "monotonic", lambda: next(clock))
    client.post("/api/samples", json={"label": "CLEAR", "signer": "Alice", "frames": [two_hands(40)] * 5})
    frame = {"type": "landmarks", "mode": "spelling", "hands": two_hands(40)}
    with client.websocket_connect("/ws/signs") as ws:
        # Frames 1-10 cover 0.9 s of holding: predictions only.
        for _ in range(10):
            ws.send_json(frame)
            assert ws.receive_json()["label"] == "CLEAR"
        # Frame 11 is held for 1.0 s, so the control is accepted.
        ws.send_json(frame)
        ws.receive_json()
        assert ws.receive_json() == {"type": "sign", "label": "CLEAR", "confidence": 1.0}


def test_evaluation_includes_controls(capsys):
    samples = []
    for signer, quirk in [("Alice", 0.0), ("Bob", 0.01)]:
        for label, shape in [("YES", 1), ("NO", 2)]:
            samples += [{"label": label, "signer": signer, "hands": [make_hand(shape, dx=quirk)]} for _ in range(5)]
        samples += [{"label": "DONE", "signer": signer, "hands": two_hands(40)} for _ in range(5)]
    results, _ = evaluate.evaluate_mode(samples, "yesno")
    assert "DONE" in {r["true"] for r in results}
    evaluate.print_report(samples, ["yesno"], 4.0)
    out = capsys.readouterr().out
    assert "DONE" in out
    assert "Control signs (DONE, CLEAR, DELETE) are checked in every mode." in out
