"""Try the three Gemini jobs (simplify, answer, summary) against the REAL API.

Unlike the tests, this uses the key in .env and goes online. For each call it prints
the input, the output, the time taken, and whether the offline fallback was used.

Run from the repo root and keep the output next to this script:
    python scripts/try_prompts.py | tee scripts/try_prompts_output.txt
    python scripts/try_prompts.py --pause 0     # no waiting, on a paid key
"""

import argparse
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server import llm  # noqa: E402

# A free key allows about 20 requests a minute; after that Gemini answers 429 and the
# fallback runs. Waiting between calls keeps the whole run under that limit.
DEFAULT_PAUSE_SECONDS = 4.0
pause_seconds = DEFAULT_PAUSE_SECONDS

# 12 things a medic might say: yes/no, pain scale, name and medication, open, and jargon.
QUESTIONS = [
    "Any allergies?",
    "Are you having trouble breathing?",
    "Did you hit your head?",
    "Rate your pain 1 to 10",
    "On a scale of one to ten, how bad is the pain in your chest?",
    "What is your name?",
    "What medications are you currently taking?",
    "What are you allergic to?",
    "Can you tell me what happened?",
    "Where does it hurt?",
    "Any dyspnea or syncope?",
    "Are you experiencing any paresthesia or radiating pain in your left upper extremity?",
]

# 10 signed answers: (signs, answer mode, the question they answer).
ANSWERS = [
    (["YES"], "yesno", "Any allergies?"),
    (["NO"], "yesno", "Are you dizzy?"),
    (["YES"], "yesno", "Do you take any medication?"),
    (["8"], "number", "Rate your pain 1 to 10"),
    (["3"], "number", "How bad is the pain now?"),
    (list("PENICILLIN"), "spelling", "What are you allergic to?"),
    (list("MARIA"), "spelling", "What is your name?"),
    (["PAIN", "WATER"], "free", "What do you need?"),
    (["COLD"], "free", "How are you feeling?"),
    (["HELP", "BATHROOM"], "free", ""),  # the patient starts, no question asked
]

# 3 conversations as the app logs them: (role, text), 6-10 turns each.
CONVERSATIONS = {
    "Chest pain": [
        ("patient", "I'm Deaf. Please speak to me, and I'll answer with signs."),
        ("medic", "Are you having chest pain?"),
        ("patient", "Yes."),
        ("medic", "On a scale of 1 to 10, how bad is the pain?"),
        ("patient", "8 out of 10."),
        ("medic", "Are you having trouble breathing?"),
        ("patient", "Yes."),
        ("medic", "Do you take any medication?"),
        ("patient", "No."),
    ],
    "Allergic reaction": [
        ("patient", "I'm Deaf. Please speak to me, and I'll answer with signs."),
        ("medic", "Do you have any allergies?"),
        ("patient", "Yes."),
        ("medic", "What are you allergic to?"),
        ("patient", "PENICILLIN"),
        ("medic", "Did you take penicillin today?"),
        ("patient", "Yes."),
        ("medic", "Is it hard to breathe?"),
        ("patient", "No."),
        ("medic", "What do you need right now?"),
    ],
    "Fall with head pain": [
        ("patient", "I'm Deaf. Please speak to me, and I'll answer with signs."),
        ("medic", "Did you fall?"),
        ("patient", "Yes."),
        ("medic", "Did you hit your head?"),
        ("patient", "Yes."),
        ("medic", "Rate your pain 1 to 10"),
        ("patient", "6 out of 10."),
        ("medic", "Are you dizzy?"),
        ("patient", "No."),
        ("patient", "Cold water"),
    ],
}


def timed(job, *args):
    """Run one llm job. Returns (output, 'how it went' text for printing)."""
    time.sleep(pause_seconds)
    start = time.perf_counter()
    output = job(*args)
    seconds = time.perf_counter() - start
    result = llm.last_call["result"]
    used = "Gemini" if result == "ok" else f"FALLBACK ({result})"
    return output, f"{seconds:.2f}s, {used}"


def heading(title):
    print(f"\n{'=' * 70}\n{title}\n{'=' * 70}")


def main():
    global pause_seconds
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--pause", type=float, default=DEFAULT_PAUSE_SECONDS,
                        help="seconds to wait before each call (default %(default)s)")
    pause_seconds = parser.parse_args().pause

    print(f"Model: {llm.MODEL}   Timeout: {llm.TIMEOUT_SECONDS:g}s   Key set: {llm.key_is_set()}")
    if not llm.key_is_set():
        print("No GEMINI_API_KEY in .env, so every call below uses the offline fallback.")
    fallbacks = 0
    calls = 0

    heading(f"simplify: {len(QUESTIONS)} medic questions")
    for question in QUESTIONS:
        reply, how = timed(llm.simplify, question)
        calls += 1
        fallbacks += "FALLBACK" in how
        print(f"\nMedic:  {question}")
        print(f"Plain:  {reply['text']}")
        print(f"Mode:   {reply['mode']}   [{how}]")

    heading(f"answer: {len(ANSWERS)} signed answers")
    for signs, mode, question in ANSWERS:
        text, how = timed(llm.answer, signs, mode, question)
        calls += 1
        fallbacks += "FALLBACK" in how
        print(f"\nAsked:  {question or '(nothing, the patient starts)'}")
        print(f"Signs:  {' '.join(signs)}   ({mode} mode)")
        print(f"Spoken: {text}   [{how}]")

    heading(f"summary: {len(CONVERSATIONS)} conversations")
    for title, turns in CONVERSATIONS.items():
        log = [{"role": role, "text": text} for role, text in turns]
        note, how = timed(llm.summary, log)
        calls += 1
        fallbacks += "FALLBACK" in how
        print(f"\n--- {title} ({len(turns)} turns) ---")
        for role, text in turns:
            print(f"  {role.upper()}: {text}")
        print(f"\nHandoff note   [{how}]")
        print("\n".join(f"  | {line}" for line in note.splitlines()))

    heading("Totals")
    print(f"{calls} calls, {calls - fallbacks} answered by Gemini, {fallbacks} used the fallback.")


if __name__ == "__main__":
    main()
