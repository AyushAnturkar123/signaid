"""Turn MediaPipe hand landmarks into one fixed-length list of numbers.

Only the shape of the hands should matter, not where they are in the frame or how
close they are to the camera, so each hand is measured from its own wrist and
scaled by its own size.
"""

import numpy as np

WRIST = 0
MIDDLE_KNUCKLE = 9
INDEX_KNUCKLE, RING_KNUCKLE, PINKY_KNUCKLE = 5, 13, 17
# Wrist to each knuckle, and across the palm. These bones don't bend, so their
# length only depends on hand size and distance from the camera.
PALM_SEGMENTS = [
    (WRIST, INDEX_KNUCKLE),
    (WRIST, MIDDLE_KNUCKLE),
    (WRIST, RING_KNUCKLE),
    (WRIST, PINKY_KNUCKLE),
    (INDEX_KNUCKLE, PINKY_KNUCKLE),
]
POINTS_PER_HAND = 21
HAND_FEATURES = POINTS_PER_HAND * 3
# Large enough that one-hand and two-hand signs never match each other.
TWO_HAND_FLAG = 3.0

# Layout: dominant hand (63), other hand (63), other wrist relative to the
# dominant wrist (3), two-hand flag (1). A missing hand is all zeros.
FEATURE_SIZE = HAND_FEATURES * 2 + 3 + 1


def _points(hand):
    points = np.asarray(hand["points"], dtype=float)
    if points.shape != (POINTS_PER_HAND, 3):
        raise ValueError(f"expected 21 points of [x, y, z], got shape {points.shape}")
    return points


def _scale(points):
    """How big the hand is, so near and far hands can be compared.

    Averages several palm lengths in 3D (wrist to each knuckle, plus the palm's
    width). A single line seen flat by the camera shrinks when the hand points at
    the camera, like a pencil pointed at you; 3D lengths stay the same however
    the hand is turned.
    """
    size = np.mean([np.linalg.norm(points[a] - points[b]) for a, b in PALM_SEGMENTS])
    return size if size > 1e-6 else 1.0


def _mirror(hand):
    """Flip a left-handed signer's hand so it looks like a right-handed one."""
    swap = {"Left": "Right", "Right": "Left"}
    handedness = hand.get("handedness")
    return {
        "handedness": swap.get(handedness, handedness),
        "points": [[1.0 - x, y, z] for x, y, z in hand["points"]],
    }


def _order(hands):
    """Return (dominant, other). A single hand is always treated as the dominant one."""
    if len(hands) == 1:
        return hands[0], None
    first, second = hands
    if second.get("handedness") == "Right" and first.get("handedness") != "Right":
        return second, first
    return first, second


def features(hands, left_handed=False):
    vec = np.zeros(FEATURE_SIZE)
    if not hands:
        return vec
    if left_handed:
        hands = [_mirror(h) for h in hands]

    dominant, other = _order(hands[:2])
    dom = _points(dominant)
    dom_scale = _scale(dom)
    vec[:HAND_FEATURES] = ((dom - dom[WRIST]) / dom_scale).ravel()

    if other is not None:
        oth = _points(other)
        vec[HAND_FEATURES:2 * HAND_FEATURES] = ((oth - oth[WRIST]) / _scale(oth)).ravel()
        vec[2 * HAND_FEATURES:2 * HAND_FEATURES + 3] = (oth[WRIST] - dom[WRIST]) / dom_scale
        vec[-1] = TWO_HAND_FLAG
    return vec
