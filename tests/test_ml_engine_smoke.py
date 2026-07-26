"""
Smoke test for the ML/Adaptation Layer.

Run directly:

    python tests/test_ml_engine_smoke.py
"""

from __future__ import annotations

import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from atlas_trader.ml import OnlineTradeModel, extract_features_from_setup, classify_loss_cause


def fake_voting_result(macro_bias, cs_bias, tech_bias, confidence):
    return {
        "confidence_score": confidence,
        "components": {
            "macro": {"bias": macro_bias, "weight": 0.25},
            "currency_strength": {"bias": cs_bias, "weight": 0.25},
            "technical": {"bias": tech_bias, "weight": 0.50},
        },
    }


def test_model_learns_from_repeated_outcomes():
    """A feature that's consistently associated with wins should end up with a positive weight."""
    model = OnlineTradeModel()

    strong_setup = fake_voting_result(60, 50, 80, 70)
    strong_features = extract_features_from_setup(strong_setup)

    weak_setup = fake_voting_result(-60, -50, -80, 70)
    weak_features = extract_features_from_setup(weak_setup)

    # Strong (positive-bias) setups win; weak (negative-bias) setups lose.
    for _ in range(50):
        model.update(strong_features, won=True)
        model.update(weak_features, won=False)

    print("Learned weights after 100 updates:", model.weights, "bias:", model.bias)

    assert model.trades_seen == 100
    # Positive-bias features should now push predictions toward a win...
    assert model.predict_win_probability(strong_features) > 0.6
    # ...and negative-bias features toward a loss.
    assert model.predict_win_probability(weak_features) < 0.4


def test_save_and_load_roundtrip():
    model = OnlineTradeModel()
    model.update({"macro_bias": 10, "currency_strength_bias": 5, "technical_bias": 20, "confidence_score": 50}, won=True)

    with tempfile.TemporaryDirectory() as tmp_dir:
        path = Path(tmp_dir) / "model.json"
        model.save(path)
        loaded = OnlineTradeModel.load(path)

    assert loaded.trades_seen == model.trades_seen
    assert loaded.weights == model.weights


def test_loss_cause_classification():
    # Technical had by far the strongest weighted push toward "long", and it lost.
    voting_result = fake_voting_result(macro_bias=10, cs_bias=5, tech_bias=90, confidence=65)
    cause = classify_loss_cause(voting_result, direction="long")
    print("Loss cause:", cause)
    assert cause == "technical_misread"

    # Nothing agreed with "short" here (all biases were positive/long-leaning) -> unclear.
    cause_unclear = classify_loss_cause(voting_result, direction="short")
    assert cause_unclear == "unclear_no_component_agreed_with_direction"


if __name__ == "__main__":
    test_model_learns_from_repeated_outcomes()
    test_save_and_load_roundtrip()
    test_loss_cause_classification()
    print("ML/Adaptation Layer smoke test passed.")
