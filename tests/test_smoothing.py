from server.smoothing import HOLD_SECONDS, MIN_CONFIDENCE, Smoother


def run(smoother, frames):
    """frames: list of (time, label, confidence, hands_present). Returns accepted labels with times."""
    return [(t, out) for t, label, conf, hands in frames if (out := smoother.update(label, conf, t, hands))]


def test_accepts_after_hold_time_not_before():
    s = Smoother()
    assert s.update("YES", 1.0, 0.0, True) is None
    assert s.update("YES", 1.0, HOLD_SECONDS - 0.01, True) is None
    assert s.update("YES", 1.0, HOLD_SECONDS, True) == "YES"


def test_accepts_only_once_while_held():
    accepted = run(Smoother(), [(t / 10, "YES", 1.0, True) for t in range(30)])
    assert [label for _, label in accepted] == ["YES"]


def test_dropping_hand_allows_same_sign_again():
    s = Smoother()
    frames = [(t / 10, "YES", 1.0, True) for t in range(7)]
    frames += [(0.8, None, 0.0, False)]  # hand lowered
    frames += [(0.9 + t / 10, "YES", 1.0, True) for t in range(7)]
    assert [label for _, label in run(s, frames)] == ["YES", "YES"]


def test_low_confidence_is_ignored():
    frames = [(t / 10, "YES", MIN_CONFIDENCE - 0.1, True) for t in range(20)]
    assert run(Smoother(), frames) == []


def test_brief_uncertain_frame_does_not_cause_a_repeat():
    frames = [(t / 10, "YES", 1.0, True) for t in range(7)]
    frames += [(0.75, None, 0.0, True)]  # hand still visible, pose briefly unclear
    frames += [(0.8 + t / 10, "YES", 1.0, True) for t in range(10)]
    assert [label for _, label in run(Smoother(), frames)] == ["YES"]


def test_switching_signs_restarts_the_timer():
    s = Smoother()
    frames = [(t / 10, "YES", 1.0, True) for t in range(7)]
    frames += [(0.7 + t / 10, "NO", 1.0, True) for t in range(7)]
    accepted = run(s, frames)
    assert [label for _, label in accepted] == ["YES", "NO"]
    assert accepted[1][0] >= 0.7 + HOLD_SECONDS


def test_reset_clears_state():
    s = Smoother()
    run(s, [(t / 10, "YES", 1.0, True) for t in range(7)])
    s.reset()
    assert [label for _, label in run(s, [(1 + t / 10, "YES", 1.0, True) for t in range(7)])] == ["YES"]
