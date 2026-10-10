"""Gemini wrapper tests. The real API is never called: either there's no key
(the fallbacks run) or _gemini is replaced with a fake reply."""

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

    def fake(system, prompt, json_output=False):
        calls.append({"system": system, "prompt": prompt, "json_output": json_output})
        return reply

    monkeypatch.setattr(llm, "_gemini", fake)
    return calls


def test_simplify_uses_gemini_reply(monkeypatch):
    calls = fake_gemini(monkeypatch, '{"text": "Is it hard to breathe?", "mode": "yesno"}')
    assert llm.simplify("Are you experiencing dyspnea?") == {"text": "Is it hard to breathe?", "mode": "yesno"}
    assert calls[0]["json_output"] is True
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
