"""Nearest-neighbor sign classifier. The recorded samples are the model.

A live hand pose is compared with every recorded sample of the current mode,
and the most common label among the K closest samples wins.

Samples are stored as one JSON file per signer (data/samples/<signer>.json), so
teammates can record on their own laptops and merge without git conflicts.
"""

import json
import re
import threading
from collections import Counter
from pathlib import Path

import numpy as np

from .normalize import features
from .signs import MODES

K = 5
# If even the closest sample is further than this, the pose isn't a known sign.
# Predictions include "distance", so watch it live to tune this number.
MAX_DISTANCE = 4.0


def _round_hands(hands):
    return [
        {
            "handedness": h.get("handedness"),
            "points": [[round(c, 4) for c in point] for point in h["points"]],
        }
        for h in hands
    ]


def _file_name(signer):
    return re.sub(r"[^a-z0-9]+", "-", signer.lower()).strip("-") or "unnamed"


class SignClassifier:
    def __init__(self, folder):
        self.folder = Path(folder)
        self.lock = threading.Lock()
        self.samples = []
        for file in sorted(self.folder.glob("*.json")):
            self.samples.extend(json.loads(file.read_text()))
        self._rebuild()

    def _rebuild(self):
        by_mode = {}
        for mode, labels in MODES.items():
            rows = [s for s in self.samples if s["label"] in labels]
            if rows:
                X = np.stack([features(s["hands"], s.get("left_handed", False)) for s in rows])
                y = np.array([s["label"] for s in rows])
                by_mode[mode] = (X, y)
        self.by_mode = by_mode

    def _save(self, signer):
        """Rewrite one signer's file (one sample per line, so git diffs stay readable)."""
        self.folder.mkdir(parents=True, exist_ok=True)
        path = self.folder / f"{_file_name(signer)}.json"
        rows = [s for s in self.samples if _file_name(s["signer"]) == _file_name(signer)]
        if not rows:
            path.unlink(missing_ok=True)
            return
        tmp = path.with_suffix(".tmp")
        tmp.write_text("[\n" + ",\n".join(json.dumps(r) for r in rows) + "\n]\n")
        tmp.replace(path)

    def predict(self, mode, hands, left_handed=False):
        """Return (label, confidence, distance). label is None when nothing matches."""
        if not hands or mode not in self.by_mode:
            return None, 0.0, None
        X, y = self.by_mode[mode]
        dists = np.linalg.norm(X - features(hands, left_handed), axis=1)
        nearest = np.argsort(dists)[:K]
        closest = float(dists[nearest[0]])
        if closest > MAX_DISTANCE:
            return None, 0.0, closest
        label, votes = Counter(y[nearest]).most_common(1)[0]
        return str(label), votes / len(nearest), closest

    def add(self, label, frames, signer, left_handed=False):
        """Save several frames of the same sign. Returns the new count for that label."""
        for hands in frames:
            features(hands, left_handed)  # raises ValueError on malformed landmarks
        with self.lock:
            self.samples.extend(
                {"label": label, "signer": signer, "left_handed": left_handed, "hands": _round_hands(hands)}
                for hands in frames
            )
            self._save(signer)
            self._rebuild()
        return self.counts()[label]

    def remove(self, label, signer=None):
        with self.lock:
            removed = [
                s for s in self.samples
                if s["label"] == label and (signer is None or s["signer"] == signer)
            ]
            removed_ids = {id(s) for s in removed}
            self.samples = [s for s in self.samples if id(s) not in removed_ids]
            for name in {s["signer"] for s in removed}:
                self._save(name)
            self._rebuild()
            return len(removed)

    def counts(self):
        return Counter(s["label"] for s in self.samples)
