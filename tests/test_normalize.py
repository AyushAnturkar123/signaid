import numpy as np
import pytest

from server.normalize import FEATURE_SIZE, HAND_FEATURES, TWO_HAND_FLAG, features
from tests.conftest import make_hand, mirrored


def test_no_hands_gives_zeros():
    vec = features([])
    assert vec.shape == (FEATURE_SIZE,)
    assert not vec.any()


def test_position_and_size_do_not_matter():
    hand = make_hand(1, noise=0)
    moved = make_hand(1, dx=0.25, dy=-0.2, scale=1.8, noise=0)
    assert np.allclose(features([hand]), features([moved]))


def test_different_shapes_differ():
    assert not np.allclose(features([make_hand(1)]), features([make_hand(2)]), atol=0.1)


def test_one_hand_leaves_second_hand_empty():
    vec = features([make_hand(1)])
    assert not vec[HAND_FEATURES:].any()


def test_two_hands_set_the_flag():
    vec = features([make_hand(1), make_hand(2, dx=0.2, handedness="Left")])
    assert vec[-1] == TWO_HAND_FLAG
    assert vec[HAND_FEATURES:2 * HAND_FEATURES].any()


def test_hand_order_does_not_matter():
    right = make_hand(1, noise=0)
    left = make_hand(2, dx=0.2, handedness="Left", noise=0)
    assert np.allclose(features([right, left]), features([left, right]))


def test_left_handed_mirroring_matches_right_handed():
    hand = make_hand(1, noise=0)
    assert np.allclose(features([hand]), features([mirrored(hand)], left_handed=True))


def test_two_hand_mirroring_matches_right_handed():
    right = make_hand(1, noise=0)
    left = make_hand(2, dx=0.2, handedness="Left", noise=0)
    as_left_hander = [mirrored(right), mirrored(left)]
    assert np.allclose(features([right, left]), features(as_left_hander, left_handed=True))


def test_malformed_points_raise():
    with pytest.raises(ValueError):
        features([{"handedness": "Right", "points": [[0, 0, 0]] * 5}])
