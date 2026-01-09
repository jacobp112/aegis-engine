import hmac
import hashlib
import json
import base64
import time
import os
import logging

logger = logging.getLogger(__name__)

# Secrets Management - Load key from secure provider
def _load_master_key() -> bytes:
    """Load master license key from secrets provider or fallback to legacy."""
    try:
        from secrets_provider import get_secrets_provider
        return get_secrets_provider().get_secret("AEGIS_MASTER_LICENSE_KEY")
    except Exception as e:
        # Fallback for backwards compatibility (DEV ONLY - will warn)
        legacy_key = os.environ.get("AEGIS_MASTER_LICENSE_KEY")
        if legacy_key:
            logger.warning("Using legacy AEGIS_MASTER_LICENSE_KEY env var. Migrate to secrets_provider.")
            return legacy_key.encode()
        logger.error(f"Failed to load master license key: {e}")
        raise RuntimeError("AEGIS_MASTER_LICENSE_KEY not configured. See secrets_provider.py.")

MASTER_LICENSE_KEY = _load_master_key()

class LicenseManager:
    def __init__(self):
        # Default to CORE if no key present
        self.current_tier = "CORE"
        self.capabilities = self.get_tier_defaults("CORE")

    def get_tier_defaults(self, tier):
        """Returns capabilities dict for a given tier."""
        defaults = {
            "CORE": {
                "max_tps": 100,
                "features": ["basic_scoring"],
                "support_level": "standard",
                "price_mo": 10000
            },
            "PRIME": {
                "max_tps": -1, # Unlimited
                "features": ["basic_scoring", "analyst", "zkp", "consortium"],
                "support_level": "dedicated",
                "price_mo": 20000
            },
            "SOVEREIGN": {
                "max_tps": -1,
                "features": ["all", "source_escrow"],
                "support_level": "engineer_on_call",
                "price_mo": "custom"
            }
        }
        return defaults.get(tier, defaults["CORE"])

    def generate_license_key(self, client_name, tier, expiry_epoch):
        """
        Creates a signed license key string.
        Format: Base64(JsonPayload).Base64(Signature)
        """
        payload = {
            "client": client_name,
            "tier": tier,
            "exp": expiry_epoch,
            "capabilities": self.get_tier_defaults(tier)
        }

        json_str = json.dumps(payload)
        b64_payload = base64.urlsafe_b64encode(json_str.encode()).decode()

        # Sign
        sig = hmac.new(MASTER_LICENSE_KEY, b64_payload.encode(), hashlib.sha256).hexdigest()

        return f"{b64_payload}.{sig}"

    def load_license(self, license_key):
        """Parses and verifies a license key."""
        try:
            if not license_key: raise ValueError("Empty Key")

            parts = license_key.split(".")
            if len(parts) != 2: raise ValueError("Invalid Format")

            b64_payload, sig = parts

            # Verify Sig
            expected_sig = hmac.new(MASTER_LICENSE_KEY, b64_payload.encode(), hashlib.sha256).hexdigest()
            if not hmac.compare_digest(sig, expected_sig):
                raise ValueError("Invalid Signature - Tampering Detected")

            # Parse Payload
            json_str = base64.urlsafe_b64decode(b64_payload).decode()
            payload = json.loads(json_str)

            # Check Expiry
            if payload["exp"] < time.time():
                raise ValueError(f"License Expired on {time.ctime(payload['exp'])}")

            self.current_tier = payload["tier"]
            self.capabilities = payload["capabilities"]
            print(f"[LICENSE] Loaded {self.current_tier} License for {payload['client']}. MaxTPS={self.capabilities['max_tps']}")
            return True

        except Exception as e:
            print(f"[LICENSE] Error: {e}. Reverting to CORE limits.")
            self.current_tier = "CORE"
            self.capabilities = self.get_tier_defaults("CORE")
            return False

# Usage Demo
if __name__ == "__main__":
    lm = LicenseManager()

    # 1. Generate a PRIME Key
    key = lm.generate_license_key("FinTech Corp", "PRIME", time.time() + 31536000) # 1 Year
    print(f"Generated Key: {key}\n")

    # 2. Verify it
    lm.load_license(key)
