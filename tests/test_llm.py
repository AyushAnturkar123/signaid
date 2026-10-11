"""Gemini wrapper tests. The real API is never called: either there's no key
(the fallbacks run) or _gemini is replaced with a fake reply."""

import json
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


SUMMARY_JSON = {
    "chief_complaint": "chest pain",
    "pain": {"level": "8", "location": "chest"},
    "allergies": "not asked",
    "medications": "denied",
    "other_answers": ["trouble breathing"],
    "needs_attention": ["chest pain with trouble breathing"],
}
LOG = [{"role": "medic", "text": "Are you having chest pain?"}, {"role": "patient", "text": "Yes."}]


def test_summary_turns_gemini_json_into_a_note(monkeypatch):
    calls = fake_gemini(monkeypatch, json.dumps(SUMMARY_JSON))
    details = llm.summary_details(LOG)
    lines = details["text"].splitlines()
    assert lines[0] == "Patient is Deaf and needs an ASL interpreter."
    assert lines[2].startswith("Needs attention")
    assert lines[3] == "- Flagged for attention: chest pain with trouble breathing"
    # the flagged answers come before the rest of the note
    assert details["text"].index("Needs attention") < details["text"].index("Chief complaint")
    assert "Pain level: 8 out of 10" in lines
    assert "Pain location: chest" in lines
    assert "- trouble breathing" in lines
    assert details["needs_attention"] == ["chest pain with trouble breathing"]
    assert llm.summary(LOG) == details["text"]
    assert calls[0]["json_output"] is True
    assert "MEDIC: Are you having chest pain?" in calls[0]["prompt"]


def test_summary_without_flags_has_no_attention_section(monkeypatch):
    fake_gemini(monkeypatch, json.dumps({**SUMMARY_JSON, "needs_attention": [], "other_answers": []}))
    details = llm.summary_details(LOG)
    assert "attention" not in details["text"].lower()
    assert "Other answers: not asked" in details["text"]
    assert details["needs_attention"] == []


def test_summary_accepts_a_number_for_the_pain_level(monkeypatch):
    fake_gemini(monkeypatch, json.dumps({**SUMMARY_JSON, "pain": {"level": 8, "location": "chest"}}))
    assert "Pain level: 8 out of 10" in llm.summary(LOG)


@pytest.mark.parametrize("reply", [
    "not json at all",
    '["a", "list"]',
    "null",
    json.dumps({k: v for k, v in SUMMARY_JSON.items() if k != "allergies"}),  # missing field
    json.dumps({**SUMMARY_JSON, "pain": "8 out of 10"}),  # pain isn't {level, location}
    json.dumps({**SUMMARY_JSON, "pain": {"level": "8"}}),  # missing location
    json.dumps({**SUMMARY_JSON, "needs_attention": "chest pain"}),  # not a list
    json.dumps({**SUMMARY_JSON, "other_answers": [{"a": 1}]}),  # list of the wrong thing
    json.dumps({**SUMMARY_JSON, "chief_complaint": ""}),  # empty field
])
def test_summary_falls_back_on_bad_gemini_reply(monkeypatch, reply):
    fake_gemini(monkeypatch, reply)
    details = llm.summary_details(LOG)
    assert details["text"].startswith("Patient is Deaf and needs an ASL interpreter.\n\nConversation:")
    assert "PATIENT: Yes." in details["text"]
    assert details["needs_attention"] == []


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


def test_slow_summary_times_out_and_falls_back(monkeypatch, fake_key):
    monkeypatch.setattr(llm, "TIMEOUT_SECONDS", 0.2)
    monkeypatch.setattr(llm, "_call", lambda *args: time.sleep(1) or json.dumps(SUMMARY_JSON))
    start = time.perf_counter()
    details = llm.summary_details(LOG)
    assert time.perf_counter() - start < 0.6  # didn't wait for the slow call
    assert details["text"].startswith("Patient is Deaf and needs an ASL interpreter.\n\nConversation:")
    assert "PATIENT: Yes." in details["text"]
    assert details["needs_attention"] == []
    assert llm.last_call["task"] == "summary"
    assert llm.last_call["result"] == "timeout"


def test_summary_error_falls_back(monkeypatch, fake_key):
    def broken(*args):
        raise ConnectionError("no internet")

    monkeypatch.setattr(llm, "_call", broken)
    details = llm.summary_details(LOG)
    assert details["text"].startswith("Patient is Deaf and needs an ASL interpreter.\n\nConversation:")
    assert details["needs_attention"] == []


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


def test_http_deadline_meets_geminis_minimum(monkeypatch):
    # Gemini rejects deadlines under 10 s, which made every call fail with the 5 s app limit.
    monkeypatch.setattr(llm, "TIMEOUT_SECONDS", 5)
    assert llm._http_timeout_ms() == 10_000
    monkeypatch.setattr(llm, "TIMEOUT_SECONDS", 15)
    assert llm._http_timeout_ms() == 15_000


# --- Follow-up questions

def turn(role, text):
    return {"role": role, "text": text}


def test_follow_up_fallback_asks_pain_level():
    log = [turn("medic", "What's wrong?"), turn("patient", "I have pain.")]
    assert llm.follow_up(log) == {"question": "How bad is your pain, 1 to 10?", "mode": "number"}


def test_follow_up_fallback_asks_where_after_pain_level():
    log = [turn("medic", "How bad is the pain, 1 to 10?"), turn("patient", "I have pain, 8 out of 10.")]
    assert llm.follow_up(log) == {"question": "Where is the pain?", "mode": "location"}


def test_follow_up_fallback_stops_once_pain_location_is_known():
    log = [
        turn("patient", "I have pain."),
        turn("signaid", "How bad is your pain, 1 to 10?"), turn("patient", "8 out of 10."),
        turn("signaid", "Where is the pain?"), turn("patient", "The pain is in my chest."),
    ]
    # No more pain details: SignAid moves on to the closing question.
    assert llm.follow_up(log) == {"question": llm.CLOSING_QUESTION, "mode": "yesno"}


@pytest.mark.parametrize("text", ["Where does it hurt?", "Where is the pain?", "Where do you have pain?"])
def test_guess_mode_where_pain_is_location(text):
    assert llm._guess_mode(text) == "location"


@pytest.mark.parametrize("signs, expected", [
    (["CHEST"], "The pain is in my chest."),
    (["HEAD", "LEGS"], "The pain is in my head and my legs."),
])
def test_answer_fallback_for_pain_location(signs, expected):
    assert llm.answer(signs, "location") == expected


def test_prompts_know_the_pain_location_signs():
    for prompt in (llm.SIMPLIFY_SYSTEM, llm.FOLLOW_UP_SYSTEM):
        assert '"location"' in prompt
        assert "CHEST, HEAD, LEGS" in prompt
    assert "CHEST = my chest" in llm.ANSWER_SYSTEM


def test_follow_up_accepts_location_mode_from_gemini(monkeypatch):
    fake_gemini(monkeypatch, '{"question": "Where is the pain?", "mode": "location"}')
    assert llm.follow_up([turn("patient", "My pain is 8 out of 10.")]) == {"question": "Where is the pain?", "mode": "location"}


def test_no_follow_up_after_a_question():
    assert llm.follow_up([turn("patient", "I have pain."), turn("medic", "Where?")]) == llm.NO_FOLLOW_UP
    assert llm.follow_up([]) == llm.NO_FOLLOW_UP


def test_follow_ups_stop_after_three_in_a_row(monkeypatch):
    calls = fake_gemini(monkeypatch, '{"question": "Did it start suddenly?", "mode": "yesno"}')
    log = [turn("medic", "What's wrong?"), turn("patient", "I have pain.")]
    for q in ["How bad?", "Is it your chest?", "Is it sharp?"]:
        log += [turn("signaid", q), turn("patient", "Yes.")]
    # After 3 follow-ups, no more details, only the closing question.
    assert llm.follow_up(log) == {"question": llm.CLOSING_QUESTION, "mode": "yesno"}
    assert calls == []  # stopped before asking Gemini
    # A new medic question starts a fresh count.
    log += [turn("medic", "Any allergies?"), turn("patient", "Yes.")]
    assert llm.follow_up(log)["question"] == "Did it start suddenly?"


def test_follow_up_uses_gemini(monkeypatch):
    calls = fake_gemini(monkeypatch, '{"question": "Is the pain in your chest?", "mode": "yesno"}')
    log = [turn("patient", "My pain is 8 out of 10.")]
    assert llm.follow_up(log) == {"question": "Is the pain in your chest?", "mode": "yesno"}
    assert calls[0]["task"] == "follow_up"
    assert calls[0]["json_output"] is True
    assert "PATIENT: My pain is 8 out of 10." in calls[0]["prompt"]


def test_pain_steps_come_first_without_asking_gemini(monkeypatch):
    calls = fake_gemini(monkeypatch, '{"question": "Where is the pain?", "mode": "location"}')
    log = [turn("patient", "I have pain and I need water.")]
    assert llm.follow_up(log) == {"question": "How bad is your pain, 1 to 10?", "mode": "number"}
    log += [turn("signaid", "How bad is your pain, 1 to 10?"), turn("patient", "9 out of 10.")]
    assert llm.follow_up(log) == {"question": "Where is the pain?", "mode": "location"}
    assert calls == []  # the pain steps never wait on Gemini


@pytest.mark.parametrize("text", [
    "I do not have chest pain.",  # a NO to a pain question
    "No pain.",
    "My pain is 8 out of 10.",  # level already given
])
def test_no_pain_level_question_when_denied_or_already_given(monkeypatch, text):
    fake_gemini(monkeypatch, '{"question": null, "mode": null}')
    assert llm.follow_up([turn("patient", text)]) == llm.NO_FOLLOW_UP


def test_gemini_saying_no_follow_up_is_respected(monkeypatch):
    fake_gemini(monkeypatch, '{"question": null, "mode": null}')
    assert llm.follow_up([turn("medic", "Are you cold?"), turn("patient", "Yes.")]) == llm.NO_FOLLOW_UP


def test_repeated_follow_up_is_dropped(monkeypatch):
    fake_gemini(monkeypatch, '{"question": "Is the pain in your chest?", "mode": "yesno"}')
    log = [turn("signaid", "Is the pain in your chest?"), turn("patient", "No.")]
    assert llm.follow_up(log)["question"] == llm.CLOSING_QUESTION  # not the repeat


@pytest.mark.parametrize("reply", ["not json", '{"question": "Where?", "mode": "banana"}', '["a list"]'])
def test_bad_gemini_follow_up_uses_fallback(monkeypatch, reply, caplog):
    fake_gemini(monkeypatch, reply)
    assert llm.follow_up([turn("medic", "Any allergies?"), turn("patient", "Yes.")]) == llm.NO_FOLLOW_UP
    assert "invalid follow-up" in caplog.text



# --- "Any other symptoms?" rounds

def pain_round():
    return [
        turn("patient", "I have pain."),
        turn("signaid", "How bad is your pain, 1 to 10?"), turn("patient", "8 out of 10."),
        turn("signaid", "Where is the pain?"), turn("patient", "The pain is in my chest."),
    ]


def test_closing_question_after_follow_ups_end(monkeypatch):
    fake_gemini(monkeypatch, '{"question": null, "mode": null}')
    assert llm.follow_up(pain_round()) == {"question": llm.CLOSING_QUESTION, "mode": "yesno"}


@pytest.mark.parametrize("answer", ["Yes.", "Yes, I have other symptoms."])
def test_yes_to_other_symptoms_starts_a_new_round(answer):
    log = pain_round() + [turn("signaid", llm.CLOSING_QUESTION), turn("patient", answer)]
    assert llm.follow_up(log) == {"question": llm.NEXT_SYMPTOM_QUESTION, "mode": "free", "new_round": True}


@pytest.mark.parametrize("answer", ["No.", "I do not have any other symptoms.", "No, I don't."])
def test_no_to_other_symptoms_ends_the_interview(answer):
    log = pain_round() + [turn("signaid", llm.CLOSING_QUESTION), turn("patient", answer)]
    assert llm.follow_up(log) == llm.INTERVIEW_DONE
    assert llm.INTERVIEW_DONE["done"] is True


def test_new_round_gets_fresh_follow_ups():
    log = pain_round() + [
        turn("signaid", llm.CLOSING_QUESTION), turn("patient", "Yes."),
        turn("signaid", llm.NEXT_SYMPTOM_QUESTION), turn("patient", "I have pain."),
    ]
    # The count restarts with the new symptom, so the pain steps run again.
    assert llm._follow_ups_in_a_row(log) == 0
    assert llm.follow_up(log) == {"question": "How bad is your pain, 1 to 10?", "mode": "number"}


def test_next_symptom_with_nothing_to_ask_goes_straight_to_closing(monkeypatch):
    fake_gemini(monkeypatch, '{"question": null, "mode": null}')
    log = pain_round() + [
        turn("signaid", llm.CLOSING_QUESTION), turn("patient", "Yes."),
        turn("signaid", llm.NEXT_SYMPTOM_QUESTION), turn("patient", "I am cold."),
    ]
    assert llm.follow_up(log) == {"question": llm.CLOSING_QUESTION, "mode": "yesno"}


def test_no_closing_question_when_the_medic_leads(monkeypatch):
    fake_gemini(monkeypatch, '{"question": null, "mode": null}')
    log = [turn("medic", "Are you dizzy?"), turn("patient", "I am not dizzy.")]
    assert llm.follow_up(log) == llm.NO_FOLLOW_UP


def test_follow_up_prompt_leaves_other_symptoms_to_the_app():
    assert "other symptoms" in llm.FOLLOW_UP_SYSTEM



# --- The opening question

INTRO = turn("patient", "I'm Deaf. Please speak to me, and I'll answer with signs.")


def test_opening_question():
    assert llm.OPENING == {"question": "What symptoms do you have?", "mode": "free"}
    assert llm.OPENING_QUESTION in llm.ROUND_START_QUESTIONS


def test_full_round_after_the_opening_question(monkeypatch):
    fake_gemini(monkeypatch, '{"question": "Did it start suddenly?", "mode": "yesno"}')
    log = [INTRO, turn("signaid", llm.OPENING_QUESTION), turn("patient", "I have pain.")]
    assert llm.follow_up(log)["question"] == "How bad is your pain, 1 to 10?"
    log += [turn("signaid", "How bad is your pain, 1 to 10?"), turn("patient", "8 out of 10.")]
    assert llm.follow_up(log)["question"] == "Where is the pain?"
    log += [turn("signaid", "Where is the pain?"), turn("patient", "The pain is in my chest.")]
    # The opening question doesn't use up a follow-up, so Gemini still gets the third one.
    assert llm.follow_up(log)["question"] == "Did it start suddenly?"
    log += [turn("signaid", "Did it start suddenly?"), turn("patient", "Yes.")]
    assert llm.follow_up(log)["question"] == llm.CLOSING_QUESTION


def test_symptom_with_nothing_to_ask_goes_to_closing(monkeypatch):
    fake_gemini(monkeypatch, '{"question": null, "mode": null}')
    log = [INTRO, turn("signaid", llm.OPENING_QUESTION), turn("patient", "I am cold.")]
    assert llm.follow_up(log) == {"question": llm.CLOSING_QUESTION, "mode": "yesno"}


def test_medic_question_takes_over_from_the_opening(monkeypatch):
    fake_gemini(monkeypatch, '{"question": null, "mode": null}')
    log = [INTRO, turn("signaid", llm.OPENING_QUESTION), turn("medic", "Are you dizzy?"), turn("patient", "No.")]
    assert llm.follow_up(log) == llm.NO_FOLLOW_UP
