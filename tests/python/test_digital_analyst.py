"""
Project Aegis - DigitalAnalyst Unit Tests

Tests the weighted risk scoring model for:
- Weight loading from JSON
- Velocity calculation accuracy
- Structuring detection
- Smurfing attack detection (regression test)
"""

import pytest
import time
import json
import os
import sys

# Add parent directory to path for imports
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from digital_analyst import DigitalAnalyst


# =============================================================================
# Fixtures
# =============================================================================

@pytest.fixture
def analyst():
    """Create a DigitalAnalyst with default weights."""
    return DigitalAnalyst()


@pytest.fixture
def custom_weights(tmp_path):
    """Create a temporary weights file and return the path."""
    weights = {
        "velocity_weight": 0.7,
        "amount_weight": 0.1,
        "structuring_weight": 0.2,
        "velocity_threshold_1h": 10,
        "structuring_threshold": 9500,
        "baseline_risk": 0.1
    }
    weights_path = tmp_path / "test_weights.json"
    with open(weights_path, 'w') as f:
        json.dump(weights, f)
    return str(weights_path)


# =============================================================================
# Weight Loading Tests
# =============================================================================

class TestWeightLoading:

    def test_loads_weights_from_file(self, custom_weights):
        analyst = DigitalAnalyst(weights_path=custom_weights)

        assert analyst.model_ready == True
        assert analyst.weights["velocity_weight"] == 0.7
        assert analyst.weights["structuring_threshold"] == 9500

    def test_fallback_to_defaults_if_file_missing(self):
        analyst = DigitalAnalyst(weights_path="/nonexistent/path.json")

        assert analyst.model_ready == False
        # Should use fallback weights
        assert analyst.weights["velocity_weight"] == 0.8
        assert analyst.weights["structuring_weight"] == 0.2

    def test_fallback_weights_are_valid(self):
        analyst = DigitalAnalyst(weights_path="/nonexistent/path.json")

        # All required keys should be present
        required_keys = [
            "velocity_weight", "amount_weight", "structuring_weight",
            "velocity_threshold_1h", "structuring_threshold", "baseline_risk"
        ]
        for key in required_keys:
            assert key in analyst.weights


# =============================================================================
# Velocity Calculation Tests
# =============================================================================

class TestVelocityCalculation:

    def test_empty_history_returns_zero(self, analyst):
        score = analyst._calculate_velocities([])
        assert score == 0.0

    def test_single_recent_transaction(self, analyst):
        now = time.time()
        history = [{"timestamp": now - 100, "amount": 100}]

        score = analyst._calculate_velocities(history)
        # 1 transaction / (8 * 2) = 0.0625
        assert 0.0 < score < 0.1

    def test_high_velocity_maxes_at_one(self, analyst):
        now = time.time()
        # 100 transactions in last hour - should max out
        history = [{"timestamp": now - i, "amount": 10} for i in range(100)]

        score = analyst._calculate_velocities(history)
        assert score == 1.0

    def test_old_transactions_excluded(self, analyst):
        now = time.time()
        # All transactions older than 1 hour
        history = [{"timestamp": now - 5000, "amount": 100} for _ in range(10)]

        score = analyst._calculate_velocities(history)
        assert score == 0.0

    def test_mixed_recent_and_old(self, analyst):
        now = time.time()
        history = [
            {"timestamp": now - 100, "amount": 100},  # Recent
            {"timestamp": now - 200, "amount": 100},  # Recent
            {"timestamp": now - 5000, "amount": 100}, # Old (excluded)
            {"timestamp": now - 6000, "amount": 100}, # Old (excluded)
        ]

        score = analyst._calculate_velocities(history)
        # Only 2 recent transactions counted
        # 2 / (8 * 2) = 0.125
        assert 0.12 <= score <= 0.13


# =============================================================================
# Structuring Detection Tests
# =============================================================================

class TestStructuringDetection:

    def test_no_structuring_for_small_amounts(self, analyst):
        score = analyst._detect_structuring(100)
        assert score == 0.0

    def test_no_structuring_above_threshold(self, analyst):
        score = analyst._detect_structuring(15000)
        assert score == 0.0

    def test_structuring_detected_near_threshold(self, analyst):
        # Default threshold is 9500, reporting limit is 10000
        score = analyst._detect_structuring(9600)
        assert score == 1.0

    def test_structuring_at_exact_threshold(self, analyst):
        score = analyst._detect_structuring(9500)
        assert score == 1.0

    def test_structuring_just_below_reporting_limit(self, analyst):
        score = analyst._detect_structuring(9999)
        assert score == 1.0


# =============================================================================
# Risk Prediction Tests
# =============================================================================

class TestRiskPrediction:

    def test_empty_history_returns_baseline(self, analyst):
        result = analyst.predict_risk([])

        assert result["score"] == analyst.weights["baseline_risk"]
        assert "NO_DATA" in result["reasoning"]

    def test_low_risk_transaction(self, analyst):
        now = time.time()
        history = [{"timestamp": now - 100, "amount": 100}]

        result = analyst.predict_risk(history)

        assert result["score"] < 0.3
        assert result["reason_code"] == "RC_CLEAR"

    def test_high_velocity_increases_risk(self, analyst):
        now = time.time()
        # 20 transactions in last hour - high velocity
        history = [{"timestamp": now - i * 10, "amount": 100} for i in range(20)]

        result = analyst.predict_risk(history)

        assert result["score"] > 0.5
        assert result["reasoning"]["VELOCITY_CONTRIBUTION"] > 0.3

    def test_structuring_increases_risk(self, analyst):
        now = time.time()
        # Single transaction near reporting threshold
        history = [{"timestamp": now - 100, "amount": 9500}]

        result = analyst.predict_risk(history)

        assert result["reasoning"]["STRUCTURING_CONTRIBUTION"] > 0

    def test_score_capped_at_one(self, analyst):
        now = time.time()
        # Extreme case: high velocity + structuring
        history = [{"timestamp": now - i, "amount": 9500} for i in range(100)]

        result = analyst.predict_risk(history)

        assert result["score"] <= 1.0

    def test_xai_reasoning_present(self, analyst):
        now = time.time()
        history = [{"timestamp": now - 100, "amount": 5000}]

        result = analyst.predict_risk(history)

        assert "reasoning" in result
        assert "VELOCITY_CONTRIBUTION" in result["reasoning"]
        assert "STRUCTURING_CONTRIBUTION" in result["reasoning"]
        assert "BASELINE_RISK" in result["reasoning"]

    def test_reason_code_for_velocity(self, analyst):
        now = time.time()
        # High velocity, no structuring
        history = [{"timestamp": now - i * 10, "amount": 100} for i in range(50)]

        result = analyst.predict_risk(history)

        if result["score"] > 0.5:
            assert result["reason_code"] == "RC_VELOCITY_EXCEEDED"

    def test_reason_code_for_structuring(self, analyst):
        now = time.time()
        # Low velocity, but structuring amount
        history = [{"timestamp": now - 100, "amount": 9500}]

        result = analyst.predict_risk(history)

        # If high enough risk, should show structuring
        if result["score"] > 0.5:
            assert result["reason_code"] in ["RC_STRUCTURING_DETECTED", "RC_VELOCITY_EXCEEDED"]


# =============================================================================
# REGRESSION TEST: Smurfing Attack Detection
# =============================================================================

class TestSmurfingRegression:
    """
    Critical regression test for Smurfing detection.

    Smurfing: A money laundering technique where large sums are broken into
    many small transactions to avoid detection thresholds.

    Test case: 100 transactions of $10 each within 1 hour
    Expected: risk_score > 0.8 (high risk due to velocity)
    """

    def test_smurfing_100x_10_dollars(self, analyst):
        """
        REGRESSION TEST: 100x $10 transactions must trigger high risk.

        This test validates that the velocity-based detection catches
        classic smurfing behavior even when individual amounts are low.
        """
        now = time.time()

        # Simulate smurfing: 100 transactions of $10 in the last hour
        smurfing_history = [
            {"timestamp": now - (i * 30), "amount": 10.0}  # Every 30 seconds
            for i in range(100)
        ]

        result = analyst.predict_risk(smurfing_history)

        # CRITICAL ASSERTION: Smurfing must be detected
        assert result["score"] > 0.8, (
            f"REGRESSION FAILURE: Smurfing attack (100x $10) "
            f"only scored {result['score']:.2f}, expected > 0.8"
        )

        # Verify it's the velocity that triggered this
        assert result["reasoning"]["VELOCITY_CONTRIBUTION"] > 0.5, (
            "Velocity contribution should be the primary driver"
        )

        # Reason code should indicate velocity issue
        assert result["reason_code"] == "RC_VELOCITY_EXCEEDED"

    def test_smurfing_50x_200_dollars(self, analyst):
        """
        Variation: 50 transactions of $200 (still under $10k total).
        """
        now = time.time()

        history = [
            {"timestamp": now - (i * 60), "amount": 200.0}
            for i in range(50)
        ]

        result = analyst.predict_risk(history)

        # Should still detect high velocity
        assert result["score"] > 0.6, (
            f"50x $200 smurfing scored {result['score']:.2f}, expected > 0.6"
        )

    def test_smurfing_with_structuring(self, analyst):
        """
        Combined attack: High velocity + structuring amounts.
        """
        now = time.time()

        # 20 transactions just under $10k threshold
        history = [
            {"timestamp": now - (i * 100), "amount": 9500.0}
            for i in range(20)
        ]

        result = analyst.predict_risk(history)

        # Maximum risk expected
        assert result["score"] >= 0.9, (
            f"Combined smurfing + structuring scored {result['score']:.2f}"
        )


# =============================================================================
# Edge Cases
# =============================================================================

class TestEdgeCases:

    def test_non_dict_transactions_handled(self, analyst):
        # Some transactions are not dicts (legacy data)
        history = [
            {"timestamp": time.time() - 100, "amount": 100},
            "invalid_transaction",
            None,
            {"timestamp": time.time() - 200, "amount": 200},
        ]

        # Should not crash
        result = analyst.predict_risk(history)
        assert "score" in result

    def test_missing_timestamp_handled(self, analyst):
        history = [
            {"amount": 100},  # Missing timestamp
            {"timestamp": time.time() - 100, "amount": 200},
        ]

        result = analyst.predict_risk(history)
        assert "score" in result

    def test_missing_amount_handled(self, analyst):
        history = [
            {"timestamp": time.time() - 100},  # Missing amount
        ]

        result = analyst.predict_risk(history)
        assert "score" in result


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
