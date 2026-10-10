"""Only accept a sign once it has been held steadily, so the output doesn't flicker."""

HOLD_SECONDS = 0.5
MIN_CONFIDENCE = 0.6


class Smoother:
    def __init__(self):
        self.reset()

    def reset(self):
        self.candidate = None
        self.since = 0.0
        self.last_accepted = None

    def update(self, label, confidence, now, hands_present):
        """Return the label the moment it has been held long enough, otherwise None.

        Each sign is accepted once. To repeat the same sign (e.g. a double letter),
        lower the hand or switch to another sign first.
        """
        if not hands_present:
            self.candidate = None
            self.last_accepted = None
            return None
        if label is None or confidence < MIN_CONFIDENCE:
            self.candidate = None
            return None
        if label != self.candidate:
            self.candidate = label
            self.since = now
            return None
        if label != self.last_accepted and now - self.since >= HOLD_SECONDS:
            self.last_accepted = label
            return label
        return None
