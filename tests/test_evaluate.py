"""Tests for scripts/evaluate.py using fake signers."""

import math

import numpy as np
import pytest

from scripts import evaluate
from server.classifier import SignClassifier
from tests.conftest import make_hand

SIGNERS = ["Alice", "Bob", "Cara"]


def fake_samples(shapes, signers=SIGNERS, n=8):
    """shapes: {label: shape number}. Each signer gets a small personal quirk."""
    samples = []
    for i, signer in enumerate(signers):
        quirk = np.random.default_rng(100 + i).normal(0, 0.01, (21, 3))
        for label, shape in shapes.items():
            for _ in range(n):
                hand = make_hand(shape, dx=np.random.uniform(-0.1, 0.1), noise=0.003)
                hand["points"] = (np.array(hand["points"]) + quirk).tolist()
                samples.append({"label": label, "signer": signer, "left_handed": False, "hands": [hand]})
    return samples


def test_leave_one_signer_out_tests_every_sample():
    samples = fake_samples({"YES": 1, "NO": 2})
    results, method = evaluate.evaluate_mode(samples, "yesno")
    assert method == evaluate.LEAVE_ONE_OUT
    assert len(results) == len(samples)
    assert {r["signer"] for r in results} == set(SIGNERS)


def test_distinct_signs_score_well():
    samples = fake_samples({"YES": 1, "NO": 2})
    results, _ = evaluate.evaluate_mode(samples, "yesno")
    summary = evaluate.summarize(results, ["YES", "NO"], max_distance=math.inf)
    assert summary["per_sign"]["YES"]["accuracy"] == 1.0
    assert summary["per_sign"]["NO"]["accuracy"] == 1.0
    assert set(summary["per_signer"]) == set(SIGNERS)


def test_identical_signs_are_flagged_as_confused():
    samples = fake_samples({"7": 8, "8": 8})  # same hand shape for both
    results, _ = evaluate.evaluate_mode(samples, "number")
    summary = evaluate.summarize(results, ["7", "8"], max_distance=math.inf)
    assert summary["per_sign"]["7"]["accuracy"] < evaluate.TARGET_ACCURACY
    assert "8" in summary["per_sign"]["7"]["mistaken_for"]


def test_strict_cutoff_rejects_everything():
    samples = fake_samples({"YES": 1, "NO": 2})
    results, _ = evaluate.evaluate_mode(samples, "yesno")
    summary = evaluate.summarize(results, ["YES", "NO"], max_distance=0.0)
    assert summary["accuracy"] == 0.0
    assert summary["per_sign"]["YES"]["rejected"] == 1.0


def test_single_signer_splits_earlier_and_later_samples():
    samples = fake_samples({"YES": 1, "NO": 2}, signers=["Alice"], n=10)
    results, method = evaluate.evaluate_mode(samples, "yesno")
    assert method != evaluate.LEAVE_ONE_OUT
    assert len(results) == 6  # 3 later samples of each sign (70% used for training)


def test_mode_without_samples():
    assert evaluate.evaluate_mode(fake_samples({"YES": 1}), "free") == ([], None)


def test_suggested_cutoff_accepts_nearly_all_correct_signs():
    samples = fake_samples({"YES": 1, "NO": 2})
    results, _ = evaluate.evaluate_mode(samples, "yesno")
    suggestion = evaluate.suggest_max_distance(results)
    correct = [r["distance"] for r in results if r["predicted"] == r["true"]]
    assert suggestion >= np.quantile(correct, evaluate.ACCEPT_SHARE)
    assert evaluate.suggest_max_distance([]) is None


def test_report_with_one_signer_gives_no_cutoff(capsys):
    evaluate.print_report(fake_samples({"YES": 1, "NO": 2}, signers=["Alice"]), ["yesno"], 4.0)
    out = capsys.readouterr().out
    assert "optimistic" in out
    assert "No MAX_DISTANCE suggestion yet" in out


def test_report_flags_weak_signs_and_suggests_cutoff(capsys):
    samples = fake_samples({"YES": 1, "NO": 2, "7": 8, "8": 8})
    evaluate.print_report(samples, ["yesno", "number"], 4.0)
    out = capsys.readouterr().out
    assert "Signs below 90%: 7 (number), 8 (number)" in out
    assert "Suggested MAX_DISTANCE:" in out
    assert "Signs with no samples:" in out


def test_in_memory_classifier_never_writes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    clf = SignClassifier.from_samples(fake_samples({"YES": 1}, signers=["Alice"]))
    assert clf.predict("yesno", [make_hand(1)])[0] == "YES"
    assert not list(tmp_path.iterdir())


def test_infinite_cutoff_never_rejects():
    clf = SignClassifier.from_samples(fake_samples({"YES": 1}, signers=["Alice"]))
    assert clf.predict("yesno", [make_hand(99)])[0] is None
    assert clf.predict("yesno", [make_hand(99)], max_distance=math.inf)[0] == "YES"
