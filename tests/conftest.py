"""Shared test helpers. Tests use fake hands, so no camera is needed."""

import numpy as np
import pytest


def make_hand(shape, dx=0.0, dy=0.0, scale=1.0, handedness="Right", noise=0.002):
    """A fake MediaPipe hand: 21 [x, y, z] points.

    The same `shape` number always gives the same hand shape. dx/dy move it around
    the frame and scale makes it bigger or smaller, like moving nearer the camera.
    The wrist-to-middle-knuckle size is fixed at a realistic 0.15 (before scaling).
    """
    rng = np.random.default_rng(shape)
    offsets = rng.uniform(-0.15, 0.15, (21, 3))
    offsets[0] = 0.0  # wrist
    offsets[9] = [0.0, -0.15, 0.0]  # middle knuckle
    points = np.array([0.5 + dx, 0.6 + dy, 0.0]) + offsets * scale
    points += np.random.default_rng().normal(0, noise, points.shape)
    return {"handedness": handedness, "points": points.tolist()}


def mirrored(hand):
    """The same hand as seen from a left-handed signer."""
    swap = {"Left": "Right", "Right": "Left"}
    return {
        "handedness": swap[hand["handedness"]],
        "points": [[1.0 - x, y, z] for x, y, z in hand["points"]],
    }


@pytest.fixture(autouse=True)
def no_gemini(monkeypatch):
    """Never call the real Gemini API in tests, even if .env has a key."""
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
