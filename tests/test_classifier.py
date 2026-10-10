import json

import pytest

from server.classifier import SignClassifier
from tests.conftest import make_hand, mirrored


def frames(shape, n=10, **kwargs):
    return [[make_hand(shape, **kwargs)] for _ in range(n)]


@pytest.fixture
def clf(tmp_path):
    c = SignClassifier(tmp_path)
    c.add("YES", frames(1), "Alice")
    c.add("NO", frames(2), "Alice")
    return c


def test_predicts_the_right_sign(clf):
    label, confidence, _ = clf.predict("yesno", [make_hand(1)])
    assert label == "YES"
    assert confidence == 1.0
    assert clf.predict("yesno", [make_hand(2)])[0] == "NO"


def test_recognizes_sign_anywhere_in_frame(clf):
    assert clf.predict("yesno", [make_hand(1, dx=0.3, scale=1.5)])[0] == "YES"


def test_unknown_pose_is_rejected(clf):
    label, confidence, distance = clf.predict("yesno", [make_hand(99)])
    assert label is None
    assert confidence == 0.0
    assert distance is not None


def test_only_compares_within_mode(clf):
    # YES/NO samples exist, but none for "number" mode
    assert clf.predict("number", [make_hand(1)])[0] is None


def test_yes_and_no_also_work_in_free_mode(clf):
    assert clf.predict("free", [make_hand(1)])[0] == "YES"


def test_no_hands_predicts_nothing(clf):
    assert clf.predict("yesno", []) == (None, 0.0, None)


def test_two_hand_sign(tmp_path):
    c = SignClassifier(tmp_path)
    c.add("HELP", [[make_hand(3), make_hand(4, dx=0.2, handedness="Left")] for _ in range(10)], "Alice")
    c.add("PAIN", frames(3), "Alice")  # same dominant hand shape, but one hand
    assert c.predict("free", [make_hand(3), make_hand(4, dx=0.2, handedness="Left")])[0] == "HELP"
    assert c.predict("free", [make_hand(3)])[0] == "PAIN"


def test_left_handed_signer_matches_right_handed_samples(clf):
    assert clf.predict("yesno", [mirrored(make_hand(1))], left_handed=True)[0] == "YES"


def test_saves_one_file_per_signer(tmp_path):
    c = SignClassifier(tmp_path)
    c.add("YES", frames(1, n=3), "Alice")
    c.add("YES", frames(1, n=2), "Bob Smith")
    assert sorted(p.name for p in tmp_path.glob("*.json")) == ["alice.json", "bob-smith.json"]
    assert len(json.loads((tmp_path / "bob-smith.json").read_text())) == 2


def test_samples_survive_restart(tmp_path):
    c = SignClassifier(tmp_path)
    c.add("YES", frames(1, n=4), "Alice")
    c.add("NO", frames(2, n=3), "Bob")
    reloaded = SignClassifier(tmp_path)
    assert reloaded.counts() == {"YES": 4, "NO": 3}
    assert reloaded.predict("yesno", [make_hand(2)])[0] == "NO"


def test_add_returns_running_total(tmp_path):
    c = SignClassifier(tmp_path)
    assert c.add("YES", frames(1, n=3), "Alice") == 3
    assert c.add("YES", frames(1, n=2), "Bob") == 5


def test_remove_only_that_signer(tmp_path):
    c = SignClassifier(tmp_path)
    c.add("YES", frames(1, n=3), "Alice")
    c.add("YES", frames(1, n=2), "Bob")
    assert c.remove("YES", "Alice") == 3
    assert c.counts() == {"YES": 2}
    assert not (tmp_path / "alice.json").exists()  # empty file is deleted
    assert (tmp_path / "bob.json").exists()


def test_removed_sign_is_no_longer_predicted(clf):
    clf.remove("YES")
    assert clf.predict("yesno", [make_hand(1)])[0] != "YES"


def test_malformed_frame_saves_nothing(tmp_path):
    c = SignClassifier(tmp_path)
    bad = [[{"handedness": "Right", "points": [[0, 0, 0]] * 5}]]
    with pytest.raises(ValueError):
        c.add("YES", frames(1, n=2) + bad, "Alice")
    assert c.counts() == {}
    assert not list(tmp_path.glob("*.json"))
