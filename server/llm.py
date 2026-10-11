"""Gemini calls for the conversation. Each function falls back to a simple
non-AI answer when there is no API key or the request fails, so the app keeps
working offline (e.g. in an ambulance with no signal)."""

import json
import logging
import os
import re
import time
from concurrent.futures import ThreadPoolExecutor
from concurrent.futures import TimeoutError as FutureTimeout

from dotenv import load_dotenv

from .signs import MODES

load_dotenv()
log = logging.getLogger("signaid.llm")

MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
# A demo can't wait on a slow network: after this many seconds, use the fallback.
TIMEOUT_SECONDS = float(os.getenv("GEMINI_TIMEOUT_SECONDS", "5"))
# Gemini rejects any request deadline under 10 s ("Minimum allowed deadline is 10s"), so the
# HTTP request itself always gets at least that. The app still stops waiting after
# TIMEOUT_SECONDS (see _gemini) and uses the fallback, so a slow call never freezes the demo.
MIN_HTTP_TIMEOUT_SECONDS = 10


def _http_timeout_ms():
    return int(max(TIMEOUT_SECONDS, MIN_HTTP_TIMEOUT_SECONDS) * 1000)

_client = None
_pool = ThreadPoolExecutor(max_workers=4, thread_name_prefix="gemini")
# The most recent Gemini call, reported by GET /api/health.
last_call = {"task": None, "result": None, "seconds": None}


def key_is_set():
    return bool(os.getenv("GEMINI_API_KEY"))


def _call(key, system, prompt, json_output):
    """The actual API request. Runs on a worker thread so it can be timed out."""
    global _client
    from google import genai
    from google.genai import types

    if _client is None:
        # The HTTP timeout stops the request itself; the deadline in _gemini
        # guarantees the app stops waiting even if the request hangs in a retry or DNS.
        _client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=_http_timeout_ms()))
    config = types.GenerateContentConfig(
        system_instruction=system,
        temperature=0.2,
        response_mime_type="application/json" if json_output else "text/plain",
    )
    reply = _client.models.generate_content(model=MODEL, contents=prompt, config=config)
    return (reply.text or "").strip() or None


def _gemini(system, prompt, json_output=False, task="gemini"):
    """Return Gemini's text reply, or None if Gemini isn't available, fails, or is too slow."""
    if not key_is_set():
        _record(task, "no key", None)
        return None
    start = time.perf_counter()
    future = _pool.submit(_call, os.getenv("GEMINI_API_KEY"), system, prompt, json_output)
    try:
        text = future.result(timeout=TIMEOUT_SECONDS)
    except FutureTimeout:
        _record(task, "timeout", time.perf_counter() - start)
        return None
    except Exception as e:
        _record(task, f"error: {type(e).__name__}: {e}"[:200], time.perf_counter() - start)
        return None
    _record(task, "ok" if text else "empty reply", time.perf_counter() - start)
    return text


def _record(task, result, seconds):
    last_call.update(task=task, result=result, seconds=None if seconds is None else round(seconds, 2))
    took = "" if seconds is None else f" in {seconds:.2f}s"
    if result == "ok":
        log.info("Gemini %s ok%s", task, took)
    else:
        log.warning("Gemini %s: %s%s, using offline fallback", task, result, took)


# The signs the patient can answer with in Free mode, besides YES and NO.
_FREE_SIGNS = ", ".join(sign for sign in MODES["free"] if sign not in MODES["yesno"])
# Where the pain is: CHEST, HEAD, LEGS (two-hand gestures made up for SignAid).
_LOCATION_SIGNS = ", ".join(MODES["location"])
LOCATION_PHRASES = {"CHEST": "my chest", "HEAD": "my head", "LEGS": "my legs"}

SIMPLIFY_SYSTEM = f"""You help a Deaf patient understand a medic during a medical emergency.

Rewrite the medic's words as one short, plain-English question or statement.
- At most 15 words, easy to read quickly.
- No medical jargon. Use everyday words: "dyspnea" is trouble breathing, "syncope" is fainting.
- Keep the meaning exactly. Never add, drop or narrow anything: "Any allergies?" asks about
  every kind of allergy, not only medicines.
- If the medic's words are already short and plain, keep them as they are.

Then choose the mode: how the patient can answer. The patient answers only with hand signs.
Go down this list and pick the first mode whose signs can give the answer:
- "yesno": the answer is yes or no. This covers questions starting with "Any", "Do you",
  "Are you", "Did you" or "Is it", even when a yes would lead to a follow-up question.
- "number": the answer is a number from 1 to 10, such as a pain level.
- "location": the question asks where the pain or hurt is. The patient answers with one of
  these signs: {_LOCATION_SIGNS}. For example "Where does it hurt?".
- "free": the answer is one of these signs: {_FREE_SIGNS}. For example "What do you need?".
  Also use it for statements that need no answer.
- "spelling": the answer needs any other word, which the patient spells letter by letter:
  a name, a medication, an allergy, or what happened.

Reply only with JSON: {{"text": "...", "mode": "..."}}"""

YESNO_START = re.compile(
    r"^(are|is|do|does|did|have|has|can|could|will|would|were|was|should|any)\b", re.I
)


def _guess_mode(text):
    lower = text.lower()
    if re.search(r"\b(scale|rate|1 to 10|one to ten|how bad|how much pain)\b", lower):
        return "number"
    if re.search(r"\bwhere\b", lower) and re.search(r"\b(pain|hurt|hurts|ache)\b", lower):
        return "location"
    if re.search(r"\b(name|spell|allergic to what|what medication|which medication)\b", lower):
        return "spelling"
    if YESNO_START.match(lower.strip()):
        return "yesno"
    return "free"


def simplify(text):
    """Medic's words -> {"text": plain version, "mode": how the patient answers}."""
    reply = _gemini(SIMPLIFY_SYSTEM, f"Medic said: {text}", json_output=True, task="simplify")
    if reply:
        try:
            data = json.loads(reply)
            if data.get("text") and data.get("mode") in MODES:
                return {"text": data["text"], "mode": data["mode"]}
        except (json.JSONDecodeError, AttributeError):
            log.warning("Gemini returned invalid JSON: %r", reply)
    return {"text": text, "mode": _guess_mode(text)}


ANSWER_SYSTEM = """You turn a Deaf patient's signed answer into one short first-person
sentence that is read aloud to a medic.

Say only what the signs say. Never add a symptom, cause, time, place, amount or guess, and
never connect two signs into a new idea.

How to read the signs depends on the answer mode:
- yesno: YES or NO answers the medic's question. Say "Yes." or "No.", or restate the question
  as a statement using only the question's own words: "Are you dizzy?" + NO is "I am not dizzy."
- number: the number answers the medic's question. For a pain or scale question it is a level
  out of 10: "My pain is 8 out of 10."
- spelling: the letters spell one word. Keep every letter in order and never correct the
  spelling. Use the question to frame it: "What is your name?" + M A R I A is "My name is Maria."
- free: each sign is a separate statement with exactly this meaning:
  PAIN = I have pain. HELP = I need help. WATER = I need water. FOOD = I need food.
  BATHROOM = I need the bathroom. COLD = I am cold. STOP = Please stop. PHONE = I need a phone.
  YES = Yes. NO = No.
  Join several signs with "and" and leave each meaning unchanged:
  PAIN WATER is "I have pain and I need water."
  HELP BATHROOM is "I need help and I need the bathroom."

- location: each sign is where the pain is: CHEST = my chest, HEAD = my head, LEGS = my legs.
  CHEST is "The pain is in my chest." CHEST HEAD is "The pain is in my chest and my head."

If the medic asked nothing, just say what the signs mean.
Reply with the sentence only."""


def _fallback_answer(signs, mode):
    if mode == "spelling":
        return "".join(signs)
    if mode == "number" and signs:
        return f"{signs[-1]} out of 10."
    if mode == "yesno" and signs:
        return signs[-1].capitalize() + "."
    if mode == "location" and signs:
        return "The pain is in " + " and ".join(LOCATION_PHRASES.get(s, s.lower()) for s in signs) + "."
    return " ".join(signs).capitalize()


def answer(signs, mode, question=""):
    """Patient's confirmed signs -> a sentence for the medic."""
    prompt = f"Medic asked: {question or '(nothing yet)'}\nAnswer mode: {mode}\nSigns: {' '.join(signs)}"
    return _gemini(ANSWER_SYSTEM, prompt, task="answer") or _fallback_answer(signs, mode)


SUMMARY_SYSTEM = """Fill in a handoff note for emergency room staff from a conversation
between a medic and a Deaf patient who answers in signs. Some questions come from SIGNAID, the
app asking short follow-up questions; treat them exactly like the medic's questions.

Reply only with JSON in exactly this shape:
{"chief_complaint": "...",
 "pain": {"level": "...", "location": "..."},
 "allergies": "...",
 "medications": "...",
 "other_answers": ["..."],
 "needs_attention": ["..."]}

Rules for every field:
- Use only facts the patient confirmed: something the patient said, or a medic question the
  patient answered. A yes confirms it. A no denies it: write "denies ..." in plain words,
  e.g. "denies taking any medication", "denies dizziness".
- A medic question with no answer from the patient confirms nothing. Leave it out.
- Never diagnose, interpret or guess a cause. Write what was said, not what it might mean.
- Write "not asked" for anything the conversation doesn't cover. "pain.level" is the number
  from 1 to 10 the patient gave, or "not asked". "pain.location" is the body part named in a
  pain question the patient said yes to (yes to "chest pain?" is "chest"), or "not asked".
- The patient's opening line about being Deaf is not an answer. Don't repeat it.
- "other_answers": confirmed or denied facts that fit no other field, one short phrase each.
  Use [] if there are none.

"needs_attention" lists the confirmed answers a clinician should look at first, such as chest
pain with trouble breathing, a sudden severe headache, a head injury, or an allergy.
- Each item restates the patient's own answers in a few plain words, e.g. "chest pain with
  trouble breathing" or "allergy to penicillin".
- Never write a diagnosis, a possible condition, a triage level, an urgency word or medical
  advice. Do not say what the answers might mean or what staff should do.
- Use [] if nothing stands out. Never list a denied or unanswered item."""

INTERPRETER_LINE = "Patient is Deaf and needs an ASL interpreter."
NOT_ASKED = "not asked"


def _text(value):
    """A non-empty string field from Gemini's JSON. Anything else is an invalid reply."""
    if isinstance(value, bool) or not isinstance(value, (str, int)):
        raise ValueError(f"expected text, got {value!r}")
    text = str(value).strip()
    if not text:
        raise ValueError("empty text")
    return text


def _text_list(value):
    if not isinstance(value, list):
        raise ValueError(f"expected a list, got {value!r}")
    return [_text(item) for item in value]


def _format_summary(data):
    """Gemini's JSON -> (readable note, needs_attention list). Raises if a field is missing or wrong."""
    complaint = _text(data["chief_complaint"])
    level = _text(data["pain"]["level"])
    location = _text(data["pain"]["location"])
    allergies = _text(data["allergies"])
    medications = _text(data["medications"])
    others = _text_list(data["other_answers"])
    # The note adds "Flagged for attention" itself, so drop it if Gemini wrote it too.
    attention = [re.sub(r"^flagged for attention:?\s*", "", item, flags=re.I) for item in _text_list(data["needs_attention"])]
    attention = [item for item in attention if item]

    lines = [INTERPRETER_LINE, ""]
    if attention:
        lines.append("Needs attention (the patient's own answers, not a diagnosis):")
        lines += [f"- Flagged for attention: {item}" for item in attention]
        lines.append("")
    lines += [
        f"Chief complaint: {complaint}",
        f"Pain level: {level} out of 10" if level.isdigit() else f"Pain level: {level}",
        f"Pain location: {location}",
        f"Allergies: {allergies}",
        f"Medications: {medications}",
    ]
    if others:
        lines.append("Other answers:")
        lines += [f"- {item}" for item in others]
    else:
        lines.append(f"Other answers: {NOT_ASKED}")
    return "\n".join(lines), attention


def summary_details(log_entries):
    """Conversation log -> {"text": handoff note, "needs_attention": [answers to look at first]}.

    The plain fallback (interpreter line + transcript, nothing flagged) is used when Gemini
    isn't available or its JSON is invalid or incomplete.
    """
    transcript = "\n".join(f"{e['role'].upper()}: {e['text']}" for e in log_entries)
    reply = _gemini(SUMMARY_SYSTEM, transcript or "(no conversation yet)", json_output=True, task="summary")
    if reply:
        try:
            text, attention = _format_summary(json.loads(reply))
            return {"text": text, "needs_attention": attention}
        except (json.JSONDecodeError, KeyError, TypeError, ValueError):
            log.warning("Gemini returned an invalid summary: %r", reply)
    text = f"{INTERPRETER_LINE}\n\nConversation:\n" + (transcript or "(empty)")
    return {"text": text, "needs_attention": []}


def summary(log_entries):
    """Conversation log [{"role": "medic"|"patient", "text": ...}] -> handoff note."""
    return summary_details(log_entries)["text"]


# --- Follow-up questions -------------------------------------------------------------------
# After the patient answers, SignAid can ask one short follow-up on screen (e.g. PAIN -> "How bad
# is your pain, 1 to 10?" in Number mode). They're logged with role "signaid".

FOLLOW_UP_ROLE = "signaid"
# Then SignAid stops and waits for the medic, so it never turns into an endless interview.
MAX_FOLLOW_UPS = 3

# When SignAid's follow-ups for a symptom are finished, it asks about other symptoms. YES starts a
# new round for the next symptom; NO ends the interview and the app opens the handoff summary.
CLOSING_QUESTION = "Do you have any other symptoms?"
NEXT_SYMPTOM_QUESTION = "What other symptom do you have?"
# Asked right after the patient's opening line, without waiting for the medic.
OPENING_QUESTION = "What symptoms do you have?"
OPENING = {"question": OPENING_QUESTION, "mode": "free"}
# Each of these starts a symptom round: follow-ups are counted, and pain steps scoped, from there.
ROUND_START_QUESTIONS = {OPENING_QUESTION, NEXT_SYMPTOM_QUESTION}

FOLLOW_UP_SYSTEM = f"""You are SignAid, an app that helps a Deaf patient talk with a medic in a
medical emergency. The patient answers only with hand signs. Questions come from the MEDIC or
from you (SIGNAID). After the patient's latest answer, decide whether ONE short follow-up
question would fill in a missing detail about what the patient just said.

Follow up on the patient's problem one detail at a time, for example:
- pain: how bad it is (1 to 10), then "Where is the pain?" in "location" mode, then
  "Did it start suddenly?"
- yes to having allergies: "What are you allergic to?"
- yes to taking medication: "What medication do you take?"
- HELP: "What do you need help with?"

Rules:
- Ask only about the patient's latest answer. Never repeat or rephrase a question that is already
  in the conversation, and never ask for a detail the patient already gave.
- At most 12 words, plain everyday words.
- Never diagnose, suggest a cause, give advice or tell anyone what to do.
- Never ask whether the patient has other symptoms; the app asks that itself.
- If nothing important is missing, or the latest answer leaves nothing to follow up on (such as
  "No." to a yes/no question, or the patient's opening line about being Deaf), reply with null.

Choose how the patient can answer:
- "yesno": the answer is yes or no.
- "number": the answer is a number from 1 to 10.
- "location": where the pain is, one of these signs: {_LOCATION_SIGNS}.
- "free": the answer is one of these signs: {_FREE_SIGNS}.
- "spelling": the answer is any other word, spelled letter by letter.

Reply only with JSON: {{"question": "...", "mode": "..."}} or {{"question": null, "mode": null}}"""

PAIN_LEVEL_QUESTION = re.compile(r"1 to 10|how bad|how much pain|pain level|rate", re.I)
WHERE_QUESTION = re.compile(r"\bwhere\b", re.I)
NEGATION = re.compile(r"\b(no|not|don't|do not|without|denies)\b", re.I)
PAIN_LEVEL_GIVEN = re.compile(r"\b([1-9]|10) out of 10\b", re.I)
NO_FOLLOW_UP = {"question": None, "mode": None}
# The patient said they have no other symptoms: the app opens the handoff summary.
INTERVIEW_DONE = {"question": None, "mode": None, "done": True}


def _questions(log_entries):
    return [e["text"] for e in log_entries if e["role"] != "patient"]


def _follow_ups_in_a_row(log_entries):
    """SignAid follow-ups since the medic last spoke or the current symptom round started
    (the round's opening question itself doesn't count)."""
    count = 0
    for e in reversed(log_entries):
        if e["role"] == "medic":
            break
        if e["role"] == FOLLOW_UP_ROLE:
            if e["text"] in ROUND_START_QUESTIONS:
                break
            count += 1
    return count


def _signaid_is_leading(log_entries):
    """True if SignAid asked something since the medic last spoke."""
    for e in reversed(log_entries):
        if e["role"] == "medic":
            return False
        if e["role"] == FOLLOW_UP_ROLE:
            return True
    return False


def _current_round(log_entries):
    """The entries since the current symptom round started (after "What other symptom...")."""
    for i in range(len(log_entries) - 1, -1, -1):
        e = log_entries[i]
        if e["role"] == FOLLOW_UP_ROLE and e["text"] in ROUND_START_QUESTIONS:
            return log_entries[i:]
    return log_entries


def _last_question(log_entries):
    return next((e for e in reversed(log_entries) if e["role"] != "patient"), None)


def _is_yes(text):
    """A patient answer to the closing question: "Yes." / "Yes, I have other symptoms." vs "No." """
    text = text.strip().lower()
    return bool(re.match(r"yes\b", text)) and not NEGATION.search(text)


def _pain_follow_up(log_entries):
    """The pain steps, always in this order: PAIN -> pain level (Number) -> where (Pain location).

    A fixed rule rather than Gemini, so the order is guaranteed and it works offline. Only the
    current symptom round counts, so a second pain gets its own level and location.
    """
    questions = _questions(_current_round(log_entries))
    latest = log_entries[-1]["text"]
    if (
        re.search(r"\bpain\b", latest, re.I)
        and not NEGATION.search(latest)  # "I do not have chest pain" isn't pain to ask about
        and not PAIN_LEVEL_GIVEN.search(latest)  # the patient already gave the level
        and not any(PAIN_LEVEL_QUESTION.search(q) for q in questions)
    ):
        return {"question": "How bad is your pain, 1 to 10?", "mode": "number"}
    # Just answered the pain level, and nobody has asked where yet.
    if questions and PAIN_LEVEL_QUESTION.search(questions[-1]) and not any(
        WHERE_QUESTION.search(q) for q in questions
    ):
        return {"question": "Where is the pain?", "mode": "location"}
    return NO_FOLLOW_UP


def _fallback_follow_up(log_entries):
    """Without Gemini, only the pain steps are asked."""
    return _pain_follow_up(log_entries)


def follow_up(log_entries):
    """Conversation log -> {"question": str, "mode": str}, both None when nothing is needed, or
    INTERVIEW_DONE once the patient says they have no other symptoms."""
    if not log_entries or log_entries[-1]["role"] != "patient":
        return NO_FOLLOW_UP
    last = _last_question(log_entries)
    if last and last["role"] == FOLLOW_UP_ROLE and last["text"] == CLOSING_QUESTION:
        if _is_yes(log_entries[-1]["text"]):
            return {"question": NEXT_SYMPTOM_QUESTION, "mode": "free", "new_round": True}
        return INTERVIEW_DONE
    chain = _follow_ups_in_a_row(log_entries)
    if chain < MAX_FOLLOW_UPS:
        question = _detail_follow_up(log_entries)
        if question["question"]:
            return question
    # SignAid's own questions about this symptom are finished: ask about other symptoms.
    # Only when SignAid is leading; when the medic is asking, SignAid doesn't interrupt.
    if _signaid_is_leading(log_entries):
        return {"question": CLOSING_QUESTION, "mode": "yesno"}
    return NO_FOLLOW_UP


def _detail_follow_up(log_entries):
    """One follow-up about the patient's latest answer: the pain steps first, then Gemini."""
    pain = _pain_follow_up(log_entries)
    if pain["question"]:
        return pain
    transcript = "\n".join(f"{e['role'].upper()}: {e['text']}" for e in log_entries)
    reply = _gemini(FOLLOW_UP_SYSTEM, transcript, json_output=True, task="follow_up")
    if reply:
        try:
            data = json.loads(reply)
            question, mode = data.get("question"), data.get("mode")
            if question is None:
                return NO_FOLLOW_UP
            question = str(question).strip()
            asked = {q.strip().lower() for q in _questions(log_entries)}
            if question.lower() in asked:
                return NO_FOLLOW_UP  # never ask the same thing twice
            if question and mode in MODES:
                return {"question": question, "mode": mode}
        except (json.JSONDecodeError, AttributeError):
            pass
        log.warning("Gemini returned an invalid follow-up: %r", reply)
    return _fallback_follow_up(log_entries)
