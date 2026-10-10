"""Gemini wrapper tests. The real API is never called: either there's no key
(the fallbacks run) or _gemini is replaced with a fake reply."""

import logging
import time

import pytest

from server import llm


@pytest.mark.parametrize("text, mode", [
    ("Are you having trouble breathing?", "yesno"),
    ("Do you have any allergies?", "yesno"),
    ("Is this your first time?", "yesno"),
    ("On a scale of 1 to 10, how bad is the pain?", "number"),
    ("How much pain are you in?", "number"),
    ("Rate your pain", "number"),
    ("What is your name?", "spelling"),
    ("Which medication do you take?", "spelling"),
    ("Tell me what happened", "free"),
])
def test_guess_mode(text, mode):
    assert llm._guess_mode(text) == mode


def test_simplify_without_key_passes_text_through():
    assert llm.simplify("Are you dizzy?") == {"text": "Are you dizzy?", "mode": "yesno"}


@pytest.mark.parametrize("signs, mode, expected", [
    (["YES"], "yesno", "Yes."),
    (["NO"], "yesno", "No."),
    (["8"], "number", "8 out of 10."),
    (["P", "E", "N"], "spelling", "PEN"),
    (["PAIN", "HELP"], "free", "Pain help"),
])
def test_answer_fallback(signs, mode, expected):
    assert llm.answer(signs, mode) == expected


def test_summary_fallback_includes_transcript():
    text = llm.summary([
        {"role": "medic", "text": "Any allergies?"},
        {"role": "patient", "text": "Yes."},
    ])
    assert text.startswith("Patient is Deaf and needs an ASL interpreter.")
    assert "MEDIC: Any allergies?" in text
    assert "PATIENT: Yes." in text


def test_summary_fallback_with_empty_log():
    assert "(empty)" in llm.summary([])


def fake_gemini(monkeypatch, reply):
    calls = []

    def fake(system, prompt, json_output=False, task="gemini"):
        calls.append({"system": system, "prompt": prompt, "json_output": json_output, "task": task})
        return reply

    monkeypatch.setattr(llm, "_gemini", fake)
    return calls


def test_simplify_uses_gemini_reply(monkeypatch):
    calls = fake_gemini(monkeypatch, '{"text": "Is it hard to breathe?", "mode": "yesno"}')
    assert llm.simplify("Are you experiencing dyspnea?") == {"text": "Is it hard to breathe?", "mode": "yesno"}
    assert calls[0]["json_output"] is True
    assert calls[0]["task"] == "simplify"
    assert "dyspnea" in calls[0]["prompt"]


@pytest.mark.parametrize("reply", [
    "not json at all",
    '{"text": "Hi", "mode": "banana"}',  # mode that doesn't exist
    '{"mode": "yesno"}',  # missing text
    '["a", "list"]',
])
def test_simplify_falls_back_on_bad_gemini_reply(monkeypatch, reply):
    fake_gemini(monkeypatch, reply)
    assert llm.simplify("Are you dizzy?") == {"text": "Are you dizzy?", "mode": "yesno"}


def test_answer_uses_gemini_reply(monkeypatch):
    calls = fake_gemini(monkeypatch, "My pain is an 8 out of 10.")
    assert llm.answer(["8"], "number", "How bad is the pain?") == "My pain is an 8 out of 10."
    assert "How bad is the pain?" in calls[0]["prompt"]
    assert "Signs: 8" in calls[0]["prompt"]


def test_gemini_returns_none_without_key():
    assert llm._gemini("system", "prompt") is None


# --- Time limit and logging. _call (the real API request) is replaced, so nothing goes online.

@pytest.fixture
def fake_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key-not-real")


def test_slow_gemini_times_out_and_falls_back(monkeypatch, fake_key, caplog):
    monkeypatch.setattr(llm, "TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(llm, "_call", lambda *args: time.sleep(1) or "too late")
    start = time.perf_counter()
    assert llm.answer(["YES"], "yesno") == "Yes."
    assert time.perf_counter() - start < 0.6  # didn't wait for the slow call
    assert llm.last_call["task"] == "answer"
    assert llm.last_call["result"] == "timeout"
    assert "timeout" in caplog.text and "fallback" in caplog.text


def test_gemini_error_falls_back(monkeypatch, fake_key, caplog):
    def broken(*args):
        raise ConnectionError("no internet")

    monkeypatch.setattr(llm, "_call", broken)
    assert llm.simplify("Are you cold?") == {"text": "Are you cold?", "mode": "yesno"}
    assert llm.last_call["result"].startswith("error: ConnectionError")
    assert "no internet" in caplog.text


def test_empty_gemini_reply_falls_back(monkeypatch, fake_key):
    monkeypatch.setattr(llm, "_call", lambda *args: None)
    assert llm.answer(["8"], "number") == "8 out of 10."
    assert llm.last_call["result"] == "empty reply"


def test_successful_call_is_timed_and_logged(monkeypatch, fake_key, caplog):
    caplog.set_level(logging.INFO, logger="signaid.llm")
    monkeypatch.setattr(llm, "_call", lambda *args: "Yes, I'm cold.")
    assert llm.answer(["YES"], "yesno", "Are you cold?") == "Yes, I'm cold."
    assert llm.last_call["result"] == "ok"
    assert llm.last_call["seconds"] is not None
    assert "Gemini answer ok" in caplog.text


def test_no_key_is_recorded():
    llm.answer(["YES"], "yesno")
    assert llm.last_call["result"] == "no key"
