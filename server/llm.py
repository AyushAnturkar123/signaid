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
        _client = genai.Client(api_key=key, http_options=types.HttpOptions(timeout=int(TIMEOUT_SECONDS * 1000)))
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


SIMPLIFY_SYSTEM = """You help a Deaf patient understand a medic during a medical emergency.
Rewrite the medic's words as one short, plain-English question or statement:
at most 15 words, no medical jargon, easy to read quickly.
Then choose how the patient should answer:
- "yesno" for yes/no questions
- "number" for pain level or any 1-10 scale question
- "spelling" when asking for a name, medication, or allergy
- "free" for anything else
Reply only with JSON: {"text": "...", "mode": "..."}"""

YESNO_START = re.compile(
    r"^(are|is|do|does|did|have|has|can|could|will|would|were|was|should|any)\b", re.I
)


def _guess_mode(text):
    lower = text.lower()
    if re.search(r"\b(scale|rate|1 to 10|one to ten|how bad|how much pain)\b", lower):
        return "number"
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
Use only the information in the signs. Never add symptoms, details, or guesses.
Numbers answering a pain question are a pain level out of 10.
Letters are a spelled word; keep the spelling exactly.
Reply with the sentence only."""


def _fallback_answer(signs, mode):
    if mode == "spelling":
        return "".join(signs)
    if mode == "number" and signs:
        return f"{signs[-1]} out of 10."
    if mode == "yesno" and signs:
        return signs[-1].capitalize() + "."
    return " ".join(signs).capitalize()


def answer(signs, mode, question=""):
    """Patient's confirmed signs -> a sentence for the medic."""
    prompt = f"Medic asked: {question or '(nothing yet)'}\nAnswer mode: {mode}\nSigns: {' '.join(signs)}"
    return _gemini(ANSWER_SYSTEM, prompt, task="answer") or _fallback_answer(signs, mode)


SUMMARY_SYSTEM = """Write a brief handoff note for emergency room staff from a conversation
between a medic and a Deaf patient.
Use only facts the patient confirmed. Never guess or add anything.
Always start with: "Patient is Deaf and needs an ASL interpreter."
Then list, one per line: chief complaint, pain level and location, allergies,
medications, other answers. Write "not asked" for anything missing.
Plain text, short lines."""


def summary(log_entries):
    """Conversation log [{"role": "medic"|"patient", "text": ...}] -> handoff note."""
    transcript = "\n".join(f"{e['role'].upper()}: {e['text']}" for e in log_entries)
    reply = _gemini(SUMMARY_SYSTEM, transcript or "(no conversation yet)", task="summary")
    if reply:
        return reply
    return "Patient is Deaf and needs an ASL interpreter.\n\nConversation:\n" + (transcript or "(empty)")
