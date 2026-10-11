"""Try SignAid's follow-up questions with the REAL Gemini key and check them against the rules.

Each scenario starts a conversation, then answers every follow-up the way a patient would, and
checks: the expected answer mode, at most 12 words, no repeated question, no diagnosis words,
and that SignAid stops by itself (never more than 3 follow-ups in a row).

Run from the repo root (needs GEMINI_API_KEY in .env):
    python scripts/try_followups.py
"""

import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from server import llm  # noqa: E402

INTRO = {"role": "patient", "text": "I'm Deaf. Please speak to me, and I'll answer with signs."}
DIAGNOSIS_WORDS = re.compile(
    r"heart attack|stroke|diagnos|infection|fracture|concussion|anaphyla|likely|might be|could be|"
    r"you should|go to|call 911|take (?:a|your|some)",
    re.I,
)

# name, opening turns, how the patient answers each follow-up (in order), expected mode of the
# first follow-up (None = SignAid should not ask anything)
SCENARIOS = [
    ("Patient signs PAIN", [{"role": "patient", "text": "I have pain."}],
     ["My pain is 8 out of 10.", "Yes.", "Yes."], "number"),
    ("Pain with level already given", [
        {"role": "medic", "text": "How bad is your pain, 1 to 10?"},
        {"role": "patient", "text": "My pain is 7 out of 10."}],
     ["No.", "Yes.", "No."], "yesno"),
    ("Yes to allergies", [
        {"role": "medic", "text": "Any allergies?"}, {"role": "patient", "text": "Yes."}],
     ["PENICILLIN"], "spelling"),
    ("Yes to medication", [
        {"role": "medic", "text": "Do you take any medication?"}, {"role": "patient", "text": "Yes."}],
     ["INSULIN"], "spelling"),
    ("Patient signs HELP", [{"role": "patient", "text": "I need help."}],
     ["I have pain.", "My pain is 6 out of 10."], "any"),
    ("No to a yes/no question", [
        {"role": "medic", "text": "Are you dizzy?"}, {"role": "patient", "text": "I am not dizzy."}],
     [], None),
    ("Name spelled", [
        {"role": "medic", "text": "What is your name?"}, {"role": "patient", "text": "My name is Maria."}],
     [], None),
    ("Only the opening line", [], [], None),
    ("Pain and water together", [{"role": "patient", "text": "I have pain and I need water."}],
     ["My pain is 9 out of 10.", "Yes.", "No."], "number"),
]


def run(name, opening, answers, expected_mode):
    log = [INTRO] + opening
    problems, asked = [], []
    for step in range(llm.MAX_FOLLOW_UPS + 1):
        result = llm.follow_up(log)
        call = dict(llm.last_call)
        q, mode = result["question"], result["mode"]
        if step == 0:
            if expected_mode is None and q:
                problems.append("asked a follow-up when none was needed")
            if expected_mode not in (None, "any") and mode != expected_mode:
                problems.append(f"first follow-up mode {mode}, expected {expected_mode}")
            if expected_mode not in (None,) and not q:
                problems.append("no follow-up, but one was expected")
        if call.get("result") not in ("ok", None):
            problems.append(f"Gemini {call.get('result')}")
        if not q:
            print(f"   (stops)  [{call.get('result')}, {call.get('seconds')}s]")
            break
        print(f"   SignAid asks [{mode}]: {q}  [{call.get('result')}, {call.get('seconds')}s]")
        if len(q.split()) > 12:
            problems.append(f"over 12 words: {q!r}")
        if q.strip().lower() in asked:
            problems.append(f"repeated: {q!r}")
        if DIAGNOSIS_WORDS.search(q):
            problems.append(f"diagnosis/advice words: {q!r}")
        asked.append(q.strip().lower())
        log.append({"role": llm.FOLLOW_UP_ROLE, "text": q})
        if step >= len(answers):
            break  # the scenario has no more answers to give
        print(f"   Patient: {answers[step]}")
        log.append({"role": "patient", "text": answers[step]})
    if len(asked) > llm.MAX_FOLLOW_UPS:
        problems.append("more than 3 follow-ups in a row")
    return problems


def main():
    if not llm.key_is_set():
        print("No GEMINI_API_KEY in .env: this script tests the real Gemini.")
        return
    print(f"Model: {llm.MODEL}   App timeout: {llm.TIMEOUT_SECONDS}s\n")
    failed = 0
    for name, opening, answers, expected in SCENARIOS:
        print(f"== {name}")
        for turn in opening:
            print(f"   {turn['role'].capitalize()}: {turn['text']}")
        problems = run(name, opening, answers, expected)
        if problems:
            failed += 1
            for p in problems:
                print(f"   !! {p}")
        else:
            print("   ok")
        print()
    print(f"{len(SCENARIOS) - failed}/{len(SCENARIOS)} scenarios passed every check.")


if __name__ == "__main__":
    main()
