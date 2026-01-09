
import hashlib
import hmac
import os
import logging
import json
from enum import Enum

logger = logging.getLogger(__name__)

class HSMSigner:
    """
    Abstracts Hardware Security Module operations.
    In real env, this uses pkcs11 calls.
    In demo env, it mimics a secure element using an external key file.
    """
    def __init__(self, key_label="EU_ID_WALLET_MASTER_KEY"):
        self.key_label = key_label
        self.mode = os.environ.get("AEGIS_HSM_MODE", "simulated")
        self._sim_key = None

        if self.mode == "simulated":
            self._load_sim_key()

    def _load_sim_key(self):
        # SECURITY CRITICAL: Never hardcode keys.
        # Load from a secure path injected by the orchestrator (Kubernetes Secret Mount)
        key_path = os.environ.get("AEGIS_SIM_KEY_PATH", "secure_element.key")

        if not os.path.exists(key_path):
            # Generate one if missing (First Run / Setup) but warn heavily
            logger.warning(f"[HSM] Key file {key_path} missing. GENERATING NEW RANDOM KEY.")
            with open(key_path, "wb") as f:
                f.write(os.urandom(32))

        with open(key_path, "rb") as f:
            self._sim_key = f.read()

    def sign_hmac(self, data_bytes: bytes) -> str:
        """
        Signs data using the Master Key INSIDE the HSM.
        Returns hex digest.
        """
        if self.mode == "pkcs11":
            return self._sign_pkcs11(data_bytes)
        else:
            return self._sign_simulated(data_bytes)

    def _sign_simulated(self, data_bytes):
        if not self._sim_key:
            raise RuntimeError("HSM Not Initialized")
        h = hmac.new(self._sim_key, data_bytes, hashlib.sha256)
        return h.hexdigest()

    def _sign_pkcs11(self, data_bytes):
        # Placeholder for real PKCS11 logic
        # user_pin = os.environ["AEGIS_HSM_PIN"]
        # session = pkcs11.open(..., user_pin)
        # key = session.find_key(label=self.key_label)
        # return key.sign(data_bytes, mechanism=pkcs11.Mechanism.SHA256_HMAC)
        raise NotImplementedError("PKCS11 Mode requires hardware config")

class EU_ID_Wallet:
    def __init__(self):
        # Key is now managed by HSMSigner, not stored in this class instance.
        self.signer = HSMSigner()

    def derive_consortium_id(self, user_pii):
        """
        Derives ID using HSM-based uniqueness.
        """
        # Canonical string: "LASTNAME|FIRSTNAME|YYYY-MM-DD|ISO3"
        canonical_pii = f"{user_pii['last']}|{user_pii['first']}|{user_pii['dob']}|{user_pii['nat']}"

        # Delegate to HSM
        consortium_id = self.signer.sign_hmac(canonical_pii.encode())

        return consortium_id

# Demo usage
if __name__ == "__main__":
    wallet = EU_ID_Wallet()
    user = {"first": "John", "last": "Doe", "dob": "1980-01-01", "nat": "GBR"}
    cid = wallet.derive_consortium_id(user)
    print(f"PII: {user}")
    print(f"Consortium ID (HSM-Derived): {cid}")
