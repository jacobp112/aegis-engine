class RulesEngine:
    def __init__(self):
        # Configuration per jurisdiction
        self.configs = {
            "UK": {
                "risk_threshold": 6.0,
                "gambling_sensitivity": "HIGH",
                "gdpr_masking": True,
                "required_checks": ["UKGC", "CompaniesHouse", "VoterRoll"]
            },
            "EU": {
                "risk_threshold": 5.0,
                "gambling_sensitivity": "MEDIUM",
                "gdpr_masking": True,
                "required_checks": ["EUID", "SanctionsMap"]
            },
            "US": {
                "risk_threshold": 7.0,
                "gambling_sensitivity": "LOW",
                "gdpr_masking": False,  # US often requires full PII sharing for FinCEN
                "required_checks": ["OFAC", "FinCEN", "SSN_Trace"]
            }
        }

    def get_policy(self, jurisdiction):
        policy = self.configs.get(jurisdiction, self.configs["UK"])
        return policy

    def evaluate_risk(self, base_score, jurisdiction, risk_factors):
        """
        Adjusts risk score based on jurisdictional rules.
        """
        policy = self.get_policy(jurisdiction)
        final_score = base_score

        # Gambling adjustment
        if "Gambling" in risk_factors:
            if policy["gambling_sensitivity"] == "HIGH":
                final_score += 3.0
            elif policy["gambling_sensitivity"] == "MEDIUM":
                final_score += 1.5

        return final_score, final_score > policy["risk_threshold"]

# Demo Usage
if __name__ == "__main__":
    engine = RulesEngine()

    print("--- US Policy Check ---")
    score, is_high = engine.evaluate_risk(5.0, "US", ["Gambling"])
    print(f"US: Score {score}, Blocked? {is_high}")

    print("\n--- UK Policy Check ---")
    score, is_high = engine.evaluate_risk(5.0, "UK", ["Gambling"])
    print(f"UK: Score {score}, Blocked? {is_high}")
