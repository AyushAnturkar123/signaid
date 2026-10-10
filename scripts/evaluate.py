"""How well does the classifier recognize signs from someone it has never seen?

Leaves one signer out at a time: builds the classifier from everyone else's
samples, tests it on the person left out, and repeats for each signer. That's
the situation in a real demo, where the patient (or a judge) never recorded samples.

Run from the repo root:
    python scripts/evaluate.py
    python scripts/evaluate.py --mode number          # one mode only
    python scripts/evaluate.py --max-distance 3.0     # try a different cutoff
"""

import argparse
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from server import classifier as classifier_module  # noqa: E402
from server.classifier import SignClassifier  # noqa: E402
from server.signs import MODES  # noqa: E402

TARGET_ACCURACY = 0.90
# The suggested cutoff accepts this share of real signs from new people. It's high
# because one rejected frame restarts the 0.5 s hold timer in smoothing.py.
ACCEPT_SHARE = 0.99
SAFETY_MARGIN = 1.1
SAME_SIGNER_TRAIN_SHARE = 0.7
LEAVE_ONE_OUT = "leave one signer out"


def load_samples(folder):
    samples = []
    for file in sorted(Path(folder).glob("*.json")):
        samples.extend(json.loads(file.read_text()))
    return samples


def _test(train, test, mode):
    """Predict every test sample with a classifier built from train, without any cutoff."""
    clf = SignClassifier.from_samples(train)
    results = []
    for s in test:
        label, _, distance = clf.predict(mode, s["hands"], s.get("left_handed", False), max_distance=math.inf)
        results.append({"true": s["label"], "predicted": label, "distance": distance, "signer": s["signer"]})
    return results


def _split_by_order(samples):
    """For a single signer: train on each sign's earlier samples, test on the later ones."""
    by_label = defaultdict(list)
    for s in samples:
        by_label[s["label"]].append(s)
    train, test = [], []
    for rows in by_label.values():
        cut = max(1, int(len(rows) * SAME_SIGNER_TRAIN_SHARE))
        train += rows[:cut]
        test += rows[cut:]
    return train, test


def evaluate_mode(samples, mode):
    """Return the raw test results for one mode, and which method was used."""
    labels = MODES[mode]
    rows = [s for s in samples if s["label"] in labels]
    signers = sorted({s["signer"] for s in rows})
    if not rows:
        return [], None
    if len(signers) >= 2:
        results = []
        for signer in signers:
            train = [s for s in rows if s["signer"] != signer]
            test = [s for s in rows if s["signer"] == signer]
            results += _test(train, test, mode)
        return results, LEAVE_ONE_OUT
    train, test = _split_by_order(rows)
    return _test(train, test, mode), "same signer, later samples (optimistic: only one person recorded)"


def summarize(results, labels, max_distance):
    """Per-sign accuracy, rejections and confusions at a given cutoff."""
    per_sign = {}
    for label in labels:
        rows = [r for r in results if r["true"] == label]
        if not rows:
            continue
        accepted = [r for r in rows if r["distance"] is not None and r["distance"] <= max_distance]
        correct = sum(1 for r in accepted if r["predicted"] == label)
        mistakes = Counter(r["predicted"] for r in accepted if r["predicted"] != label)
        per_sign[label] = {
            "tested": len(rows),
            "accuracy": correct / len(rows),
            "rejected": (len(rows) - len(accepted)) / len(rows),
            "mistaken_for": {k: v / len(rows) for k, v in mistakes.most_common()},
        }
    per_signer = {}
    for signer in sorted({r["signer"] for r in results}):
        rows = [r for r in results if r["signer"] == signer]
        good = sum(1 for r in rows if r["predicted"] == r["true"] and r["distance"] is not None and r["distance"] <= max_distance)
        per_signer[signer] = good / len(rows)
    total_correct = sum(p["accuracy"] * p["tested"] for p in per_sign.values())
    total = sum(p["tested"] for p in per_sign.values())
    return {
        "accuracy": total_correct / total if total else 0.0,
        "per_sign": per_sign,
        "per_signer": per_signer,
    }


def suggest_max_distance(all_results):
    """A cutoff that accepts ACCEPT_SHARE of correctly recognized signs from new people."""
    distances = [r["distance"] for r in all_results if r["predicted"] == r["true"] and r["distance"] is not None]
    if not distances:
        return None
    return math.ceil(float(np.quantile(distances, ACCEPT_SHARE)) * SAFETY_MARGIN * 10) / 10


def other_mode_rejection(samples, max_distance):
    """Share of poses from *other* modes that each mode rejects. A rough check that the
    cutoff isn't so loose that any hand pose gets recognized as something."""
    out = {}
    for mode, labels in MODES.items():
        own = [s for s in samples if s["label"] in labels]
        others = [s for s in samples if s["label"] not in labels]
        if not own or not others:
            continue
        clf = SignClassifier.from_samples(own)
        rejected = sum(
            1 for s in others
            if clf.predict(mode, s["hands"], s.get("left_handed", False), max_distance=max_distance)[0] is None
        )
        out[mode] = rejected / len(others)
    return out


def pct(x):
    return f"{x * 100:.0f}%"


def print_report(samples, modes, max_distance):
    signers = sorted({s["signer"] for s in samples})
    print(f"SignAid evaluation: {len(samples)} samples from {len(signers)} signer(s): {', '.join(signers) or 'none'}")
    print(f"Cutoff (MAX_DISTANCE): {max_distance}    Target: {pct(TARGET_ACCURACY)} per sign\n")

    cross_signer_results, weak, missing = [], [], []
    for mode in modes:
        labels = MODES[mode]
        results, method = evaluate_mode(samples, mode)
        missing += [l for l in labels if not any(s["label"] == l for s in samples)]
        if not results:
            print(f"== {mode.upper()} ==  no samples yet\n")
            continue
        if method == LEAVE_ONE_OUT:
            cross_signer_results += results
        summary = summarize(results, labels, max_distance)
        print(f"== {mode.upper()} ==  overall {pct(summary['accuracy'])}   ({method})")
        print(f"   {'sign':<10}{'tested':>7}{'correct':>9}{'rejected':>10}   mistaken for")
        for label, p in summary["per_sign"].items():
            flag = "!!" if p["accuracy"] < TARGET_ACCURACY else "  "
            if flag == "!!":
                weak.append(f"{label} ({mode})")
            confusions = ", ".join(f"{k} {pct(v)}" for k, v in p["mistaken_for"].items() if v >= 0.02)
            print(f"{flag} {label:<10}{p['tested']:>7}{pct(p['accuracy']):>9}{pct(p['rejected']):>10}   {confusions}")
        if len(summary["per_signer"]) > 1:
            by_signer = ", ".join(f"{k} {pct(v)}" for k, v in summary["per_signer"].items())
            print(f"   by signer (tested on them, trained on the others): {by_signer}")
        print()

    print("== SUMMARY ==")
    if len(signers) < 2:
        print("Only one signer: these numbers are optimistic. Record a second person for a real test.")
    print(f"Signs below {pct(TARGET_ACCURACY)}: {', '.join(weak) if weak else 'none'}")
    if missing:
        print(f"Signs with no samples: {', '.join(missing)}")

    suggestion = suggest_max_distance(cross_signer_results)
    if suggestion is None:
        print("\nNo MAX_DISTANCE suggestion yet: it needs samples from at least 2 signers.")
        print("   (One person's samples all look alike, so a cutoff learned from them would reject everyone else.)")
    else:
        print(f"\nSuggested MAX_DISTANCE: {suggestion}  (current {classifier_module.MAX_DISTANCE})")
        print(f"   accepts about {pct(ACCEPT_SHARE)} of correctly recognized signs from new people, plus a {pct(SAFETY_MARGIN - 1)} margin.")
        rejection = other_mode_rejection(samples, suggestion)
        if rejection:
            text = ", ".join(f"{m} {pct(v)}" for m, v in rejection.items())
            print(f"   at that cutoff, poses from other modes are rejected: {text}  (higher is better)")
        print("   Try it with --max-distance, then set it in server/classifier.py.")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--samples", default=ROOT / "server" / "data" / "samples", help="folder of sample files")
    parser.add_argument("--mode", choices=list(MODES), help="only evaluate this mode")
    parser.add_argument("--max-distance", type=float, default=classifier_module.MAX_DISTANCE,
                        help="cutoff to evaluate with (default: the current MAX_DISTANCE)")
    args = parser.parse_args()

    samples = load_samples(args.samples)
    if not samples:
        print(f"No samples found in {args.samples}. Record some with the 'Record signs' panel first.")
        return
    print_report(samples, [args.mode] if args.mode else list(MODES), args.max_distance)


if __name__ == "__main__":
    main()
