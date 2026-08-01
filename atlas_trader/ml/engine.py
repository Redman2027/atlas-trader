"""
ML/Adaptation Layer.

Two responsibilities:

1. An online-learning model that updates incrementally after each
   closed trade, predicting win probability from the exact same
   component biases the Voting Engine already computed. No black box:
   the model's inputs are the same explainable numbers already in the
   feature_snapshot, and its weights can be printed at any time to see
   exactly how much influence each module currently has.

2. Auto loss-cause classification: on a losing trade, identifies which
   module's signal most strongly agreed with the (wrong) trade
   direction — that module is the most likely source of the misread.

The online model is a simple logistic regression trained via
stochastic gradient descent, updated one trade at a time. No external
ML library required — kept dependency-free, consistent with the rest
of the codebase, and better suited to low trade volume than a
batch-trained deep model would be.
"""

from __future__ import annotations

import json
import math
from pathlib import Path

DEFAULT_MODEL_PATH = Path(__file__).resolve().parents[2] / "data" / "ml_model_state.json"

FEATURE_NAMES = ["macro_bias", "currency_strength_bias", "technical_bias", "confidence_score"]
LEARNING_RATE = 0.05


def _sigmoid(x: float) -> float:
    try:
        return 1.0 / (1.0 + math.exp(-x))
    except OverflowError:
        return 0.0 if x < 0 else 1.0


class OnlineTradeModel:
    """Incrementally-trained logistic regression predicting P(win) for a setup.

    Weights start at zero (fully neutral — 50/50 prediction) and update
    by a small step after every closed trade.
    """

    def __init__(self, weights: dict | None = None, bias: float = 0.0, trades_seen: int = 0):
        self.weights = weights or {name: 0.0 for name in FEATURE_NAMES}
        self.bias = bias
        self.trades_seen = trades_seen

    def predict_win_probability(self, features: dict) -> float:
        z = self.bias + sum(
            self.weights[name] * features.get(name, 0.0) for name in FEATURE_NAMES
        )
        return _sigmoid(z)

    def update(self, features: dict, won: bool, learning_rate: float = LEARNING_RATE) -> None:
        """One step of online SGD given the actual outcome (True = win)."""
        prediction = self.predict_win_probability(features)
        target = 1.0 if won else 0.0
        error = target - prediction  # positive if the model was too pessimistic

        for name in FEATURE_NAMES:
            gradient = error * features.get(name, 0.0)
            self.weights[name] += learning_rate * gradient

        self.bias += learning_rate * error
        self.trades_seen += 1

    def to_dict(self) -> dict:
        return {"weights": self.weights, "bias": self.bias, "trades_seen": self.trades_seen}

    @classmethod
    def from_dict(cls, data: dict) -> "OnlineTradeModel":
        return cls(weights=data["weights"], bias=data["bias"], trades_seen=data["trades_seen"])

    def save(self, path: Path | str = DEFAULT_MODEL_PATH) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w") as f:
            json.dump(self.to_dict(), f, indent=2)

    @classmethod
    def load(cls, path: Path | str = DEFAULT_MODEL_PATH) -> "OnlineTradeModel":
        path = Path(path)
        if not path.exists():
            return cls()
        with open(path, "r") as f:
            return cls.from_dict(json.load(f))


def extract_features_from_setup(voting_result: dict) -> dict:
    """Pull the model's feature vector out of a Voting Engine `score_setup()` result."""
    components = voting_result["components"]
    return {
        "macro_bias": components["macro"]["bias"],
        "currency_strength_bias": components["currency_strength"]["bias"],
        "technical_bias": components["technical"]["bias"],
        "confidence_score": voting_result["confidence_score"],
    }


def classify_loss_cause(voting_result: dict, direction: str) -> str:
    """Identify which module's signal most strongly agreed with a losing trade's direction.

    That module contributed the most conviction toward a direction
    that turned out wrong, making it the most likely source of the
    misread. Returns a string like "technical_misread" or
    "macro_misread" for the Journal's `loss_cause` field.
    """
    sign = 1 if direction == "long" else -1
    components = voting_result["components"]

    candidates = []
    for name, comp in components.items():
        bias = comp["bias"]
        if (bias * sign) > 0:  # agreed with the trade's direction
            candidates.append((name, abs(bias)))

    if not candidates:
        return "unclear_no_component_agreed_with_direction"

    candidates.sort(key=lambda pair: pair[1], reverse=True)
    top_module = candidates[0][0]
    return f"{top_module}_misread"
