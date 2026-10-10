"""Gemini calls for the conversation. Each function falls back to a simple
non-AI answer when there is no API key or the request fails, so the app keeps
working offline (e.g. in an ambulance with no signal)."""

import json
import logging
import os
import re

from dotenv import load_dotenv

from .signs import MODES

load_dotenv()
log = logging.getLogger("signaid.llm")

MODEL = os.getenv("GEMINI_MODEL", "gemini-flash-latest")
_client = None


def _gemini(system, prompt, json_output=False):
    """Return Gemini's text reply, or None if Gemini isn't available."""
    global _client
    key = os.getenv("GEMINI_API_KEY")
    if not key:
        return None
    try:
        from google import genai
        from google.genai import types

        if _client is None:
            _client = genai.Client(api_key=key)
        config = types.GenerateContentConfig(
            system_instruction=system,
            temperature=0.2,
            response_mime_type="application/json" if json_output else "text/plain",
        )
        reply = _client.models.generate_content(model=MODEL, contents=prompt, config=config)
        return (reply.text or "").strip() or None
    except Exception:
        log.exception("Gemini request failed, using fallback")
        return None


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
    reply = _gemini(SIMPLIFY_SYSTEM, f"Medic said: {text}", json_output=True)
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
    return _gemini(ANSWER_SYSTEM, prompt) or _fallback_answer(signs, mode)


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
    reply = _gemini(SUMMARY_SYSTEM, transcript or "(no conversation yet)")
    if reply:
        return reply
    return "Patient is Deaf and needs an ASL interpreter.\n\nConversation:\n" + (transcript or "(empty)")
