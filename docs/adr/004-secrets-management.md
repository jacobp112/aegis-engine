# ADR-004: Secrets Management Architecture

## Status

Accepted

## Date

2026-01-09

## Context

Project Aegis handles cryptographic keys for ZKP operations and HSM-backed signing. In banking environments, secrets management is heavily regulated (PCI-DSS, SOC2). We needed a flexible architecture that supports:

1. **Development**: Simple setup for local development
2. **CI/CD**: Secure injection for automated testing
3. **Production**: HSM-backed key storage (regulatory requirement)

**Requirements:**
- No hardcoded secrets in source code
- Production keys must never exist in plaintext on disk
- Support for HSM (Hardware Security Modules) via PKCS#11
- Graceful fallback for development (with explicit opt-in)
- Audit trail for key access

**Alternatives Considered:**

| Option | Dev Experience | Security | Compliance |
|--------|---------------|----------|------------|
| Environment Variables | ✅ Easy | ❌ Logged, Leaked | ❌ Fails audit |
| Config Files | ✅ Easy | ❌ On disk | ❌ Fails audit |
| HashiCorp Vault | ⚠️ Complex | ✅ Excellent | ✅ Compliant |
| AWS Secrets Manager | ⚠️ Cloud-only | ✅ Excellent | ✅ Compliant |
| **HSM + Provider Pattern** | ⚠️ Complex | ✅ Excellent | ✅ Compliant |

## Decision

We implemented a **Secrets Provider Pattern** with multiple backends:

```python
class SecretsProvider:
    def get_secret(self, secret_name: str) -> bytes:
        raise NotImplementedError

class EnvSecretsProvider(SecretsProvider):
    # Development only - requires explicit opt-in

class PKCS11SecretsProvider(SecretsProvider):
    # Production - HSM-backed

class VaultSecretsProvider(SecretsProvider):
    # Cloud production - HashiCorp Vault
```

**Selection Logic:**
```python
def get_secrets_provider() -> SecretsProvider:
    mode = os.environ.get("AEGIS_SECRETS_MODE", "env")

    if mode in ("hsm", "pkcs11"):
        return PKCS11SecretsProvider()
    elif mode == "vault":
        return VaultSecretsProvider()
    else:
        return EnvSecretsProvider()  # Development only
```

**Security Mode Enforcement:**

| Mode | Environment Keys Allowed | Use Case |
|------|-------------------------|----------|
| `strict` (default) | ❌ Fatal error | Production |
| `permissive` | ⚠️ Warning only | Development |

Production deployments **must** use HSM or Vault. Attempting to use environment variables in strict mode causes immediate process termination:

```python
if mode == "strict" and not os.environ.get("AEGIS_ALLOW_INSECURE_ENV_KEYS"):
    raise SecurityError("FATAL: Cannot use EnvVar keys in Strict Mode")
```

## Consequences

### Positive
- Clear separation between development and production security posture
- HSM integration ensures keys never exist in plaintext
- Audit-friendly: key access logged via HSM audit trail
- Flexible: supports multiple backends without code changes

### Negative
- Increased complexity for local development
- HSM setup requires specialised knowledge
- Testing requires mocking the secrets provider

### Mitigations
- Development mode with environment variables (explicit opt-in)
- Comprehensive HSM setup documentation in DEPLOYMENT.md
- CI uses mock HSM (SoftHSM2) for testing
- Secrets provider abstraction simplifies mocking

## Production Configuration

```bash
# Production environment (Kubernetes)
AEGIS_SECRETS_MODE=hsm
AEGIS_SECURITY_MODE=strict
AEGIS_HSM_LIB=/usr/lib/libnshield.so
AEGIS_HSM_TOKEN=AegisProductionToken
AEGIS_HSM_PIN_FILE=/run/secrets/hsm_pin
```

## References

- [PKCS#11 Specification](https://docs.oasis-open.org/pkcs11/pkcs11-base/v2.40/pkcs11-base-v2.40.html)
- [PCI-DSS Key Management Requirements](https://www.pcisecuritystandards.org/)
- [HashiCorp Vault Architecture](https://www.vaultproject.io/docs/internals/architecture)
