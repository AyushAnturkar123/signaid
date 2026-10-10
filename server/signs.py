"""Sign vocabulary, grouped by recognition mode. See "Sign list" in the README."""

MODES = {
    "yesno": ["YES", "NO"],
    "number": [str(n) for n in range(1, 11)],
    # J and Z need motion, so they are typed on the on-screen keyboard instead.
    "spelling": list("ABCDEFGHIKLMNOPQRSTUVWXY"),
    # YES and NO are here too, so the patient can answer yes or no at any time.
    "free": ["YES", "NO", "PAIN", "HELP", "WATER", "FOOD", "BATHROOM", "COLD", "STOP", "PHONE"],
}

ALL_LABELS = {label for labels in MODES.values() for label in labels}
