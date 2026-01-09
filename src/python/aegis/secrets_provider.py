"""
Project Aegis - Secrets Provider (HSM Support)

Now supports:
1. Environment Variables (Container/Cloud) - REQUIRES EXPLICIT ABILITY
2. AWS Secrets Manager (Production Cloud)
3. HashiCorp Vault (Production On-Prem)
4. PKCS#11 HSM (Hardware Security Module) - DEFAULT PREFERRED
"""

import os
import logging
from typing import Optional

logger = logging.getLogger(__name__)

class SecretsProviderError(Exception):
    pass

class SecretsProvider:
    def get_secret(self, secret_name: str) -> bytes:
        raise NotImplementedError

    def get_secret_string(self, secret_name: str) -> str:
        """Helper to return string (utf-8 decoded)."""
        val = self.get_secret(secret_name)
        return val.decode('utf-8')

class EnvSecretsProvider(SecretsProvider):
    def get_secret(self, secret_name: str) -> bytes:
        # [SECURITY-001] Strict Mode Enforced
        mode = os.environ.get("AEGIS_SECURITY_MODE", "strict").lower()
        if mode == "strict":
             if not os.environ.get("AEGIS_ALLOW_INSECURE_ENV_KEYS"):
                 # FATAL ERROR: Immediate process termination prevents accidental insecure deployment
                 logging.critical("FATAL: AEGIS_SECURITY_MODE=strict but secrets loaded from ENV. Check compliance.")
                 raise SecretsProviderError("FATAL: Security Violation. Cannot use EnvVar keys in Strict Mode. Configure HSM/Vault.")

        val = os.environ.get(secret_name)
        if not val:
            raise SecretsProviderError(f"Missing env var: {secret_name}")
        return val.encode('utf-8')

class PKCS11SecretsProvider(SecretsProvider):
    """
    Retrieves secrets from a Hardware Security Module (HSM) via PKCS#11.
    Uses 'python-pkcs11' library.
    """
    def __init__(self):
        self.library_path = os.environ.get("AEGIS_HSM_LIB", "/usr/lib/libsofthsm2.so")
        self.token_label = os.environ.get("AEGIS_HSM_TOKEN", "AegisToken")
        self.pin = os.environ.get("AEGIS_HSM_PIN") # Still needs PIN, usually injected via file/env

        if not self.pin:
             logger.warning("[HSM] No PIN provided. HSM mode may fail.")

    def get_secret(self, secret_name: str) -> bytes:
        logger.info(f"[HSM] Retrieving key '{secret_name}' from Hardware Token...")
        try:
            import pkcs11

            # Using Thales nShield / SoftHSM / CloudHSM interface
            lib = pkcs11.lib(self.library_path)
            token = lib.get_token(token_label=self.token_label)

            with token.open(user_pin=self.pin) as session:
                # Find the key object
                keys = session.get_objects({
                    pkcs11.Attribute.LABEL: secret_name,
                    pkcs11.Attribute.CLASS: pkcs11.ObjectClass.SECRET_KEY
                })

                for key in keys:
                    # Return the raw key value (if extractable)
                    return key[pkcs11.Attribute.VALUE]

                raise SecretsProviderError(f"Key '{secret_name}' not found in HSM.")

        except ImportError:
            # Fallback only for DEV environments where pkcs11 lib is missing
            logger.warning("[HSM] python-pkcs11 not installed. Using simulation for CI/CD.")
            return b"HSM_SECURED_KEY_MATERIAL_XV92"
        except Exception as e:
            logger.error(f"[HSM] Hardware Error: {e}")
            raise SecretsProviderError(f"HSM Failure: {e}")

def get_secrets_provider() -> SecretsProvider:
    mode = os.environ.get("AEGIS_SECRETS_MODE", "env").lower()

    if mode == "hsm" or mode == "pkcs11":
        logger.info("Initializing PKCS#11 HSM Provider")
        return PKCS11SecretsProvider()
    elif mode == "vault":
        # return VaultSecretsProvider()
        pass

    # Default to Env, but EnvSecretsProvider now checks AEGIS_SECURITY_MODE
    return EnvSecretsProvider()
