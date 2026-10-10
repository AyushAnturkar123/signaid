"""Sign vocabulary, grouped by recognition mode. See "Sign list" in the README."""

MODES = {
    "yesno": ["YES", "NO"],
    "number": [str(n) for n in range(1, 11)],
    # J and Z need motion, so they are typed on the on-screen keyboard instead.
    "spelling": list("ABCDEFGHIKLMNOPQRSTUVWXY"),
    # YES and NO are here too, so the patient can answer yes or no at any time.
    "free": ["YES", "NO", "PAIN", "HELP", "WATER", "FOOD", "BATHROOM", "COLD", "STOP", "PHONE"],
}

# Control signs work in every mode, so the patient can run the app without touching it.
# They're two-hand gestures, so they never clash with one-hand letters and numbers.
# Kept out of MODES, which drives the frontend's tabs and tap-to-answer buttons.
CONTROLS = ["DONE", "CLEAR", "DELETE"]


def labels_for(mode):
    """Every sign the classifier listens for in a mode: its answer signs plus the controls."""
    return MODES[mode] + CONTROLS


ALL_LABELS = {label for labels in MODES.values() for label in labels} | set(CONTROLS)
