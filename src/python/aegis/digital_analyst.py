"""
Project Aegis - Digital Analyst (XAI Enhanced)
Uses heuristics and weighted inference for risk analysis.
Loads weights from 'model_weights.json' to satisfy Model Validation requirements.
"""

import numpy as np
import logging
import json
import os
import time
from decimal import Decimal

logger = logging.getLogger(__name__)

class DigitalAnalyst:
    def __init__(self, weights_path="model_weights.json"):
        self.weights_path = weights_path
        self.weights = self._load_weights()
        self.model_ready = True if self.weights else False

        if self.model_ready:
            logger.info(f"Digital Analyst Risk Model Loaded. Configuration: {self.weights}")
        else:
            logger.warning("Digital Analyst: Running in fallback mode (Default Weights).")
            # Default fallback weights if file missing
            self.weights = {
                "velocity_weight": 0.8,
                "amount_weight": 0.1,
                "structuring_weight": 0.2,
                "velocity_threshold_1h": 8,
                "structuring_threshold": 9500,
                "baseline_risk": 0.1
            }

    def _load_weights(self):
        try:
            if os.path.exists(self.weights_path):
                with open(self.weights_path, 'r') as f:
                    return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load model weights: {e}")
        return None

    def _calculate_velocities(self, transaction_history):
        """
        Calculates transaction velocity (frequency) in the last hour.
        Returns a normalized score (0.0 to 1.0).
        """
        if not transaction_history:
            return 0.0

        now = time.time()
        time_window = 3600  # 1 hour

        # Count transactions in the last hour
        # Assumes transaction_history contains dicts with 'timestamp'
        recent_txns = [
            t for t in transaction_history
            if isinstance(t, dict) and (now - t.get('timestamp', 0)) < time_window
        ]

        count = len(recent_txns)
        threshold = self.weights.get("velocity_threshold_1h", 5)

        # Calculate risk: linear increase up to 2x threshold
        # If count > 2 * threshold, risk is maxed at 1.0
        raw_score = count / (threshold * 2)
        return min(raw_score, 1.0)

    def _detect_structuring(self, amount):
        """
        Detects 'structuring' (amounts just below reporting thresholds).
        """
        threshold = Decimal(str(self.weights.get("structuring_threshold", 9000)))
        # Risk if amount is between threshold and 10,000 (typical reporting limit)
        if amount >= threshold and amount < 10000:
            return 1.0 # High likelihood of structuring
        return 0.0

    def predict_risk(self, transaction_history):
        """
        Analyzes transaction patterns to predict risk using loaded weights.
        Returns:
            dict: { 'score': float, 'reasoning': dict }
        """
        if not transaction_history:
            return {"score": self.weights["baseline_risk"], "reasoning": {"NO_DATA": 1.0}}

        # Get latest transaction details
        last_txn = transaction_history[-1]
        raw_val = last_txn.get('amount', 0.0) if isinstance(last_txn, dict) else 0.0
        amount = Decimal(str(raw_val))

        # 1. Calculate Feature Vectors
        velocity_score = self._calculate_velocities(transaction_history)
        structuring_score = self._detect_structuring(amount)

        # 2. Apply Model Weights
        w_velocity = self.weights.get("velocity_weight", 0.6)
        w_structuring = self.weights.get("structuring_weight", 0.25)
        baseline = self.weights.get("baseline_risk", 0.05)

        # Linear Combination (Simple Perceptron-like inference)
        total_risk = baseline + (velocity_score * w_velocity) + (structuring_score * w_structuring)

        # 3. XAI Attribution (Explainability)
        risk_reasoning = {
            "VELOCITY_CONTRIBUTION": round(velocity_score * w_velocity, 3),
            "STRUCTURING_CONTRIBUTION": round(structuring_score * w_structuring, 3),
            "BASELINE_RISK": baseline
        }

        # 4. Reason Code Generation (Standardized)
        reason_code = "RC_CLEAR"
        if total_risk > 0.5:
             # Determine primary driver
             if (velocity_score * w_velocity) > (structuring_score * w_structuring):
                 reason_code = "RC_VELOCITY_EXCEEDED"
             elif structuring_score > 0:
                 reason_code = "RC_STRUCTURING_DETECTED"
             else:
                 reason_code = "RC_BASELINE_RISK"

        return {
            "score": round(min(total_risk, 1.0), 4),
            "reason_code": reason_code,
            "reasoning": risk_reasoning
        }
