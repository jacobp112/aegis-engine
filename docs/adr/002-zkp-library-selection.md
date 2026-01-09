# ADR-002: ZKP Library Selection

## Status

Accepted

## Date

2026-01-09

## Context

Project Aegis requires Zero-Knowledge Proofs (ZKPs) to provide privacy-preserving compliance verification. The system must prove that a transaction satisfies regulatory requirements (e.g., sender is over 18, has sufficient funds) without revealing the underlying PII.

**Requirements:**
- Proof Generation: <5 seconds (acceptable for high-risk transactions)
- Verification: <100ms (must not block payment flow)
- Proof Size: <1KB (for blockchain anchoring)
- Security: 128-bit security level minimum
- Maturity: Production-ready with audit history

**Alternatives Considered:**

| Library | Proof System | Verification | Proof Size | Trusted Setup | Maturity |
|---------|--------------|--------------|------------|---------------|----------|
| **libsnark** | Groth16 | ~10ms | ~200 bytes | ✅ Required | High |
| bellman | Groth16 | ~10ms | ~200 bytes | ✅ Required | High |
| arkworks | Groth16/Marlin | ~10ms | ~200 bytes | ✅/❌ | Medium |
| Circom/snarkjs | Groth16/PLONK | ~50ms | ~200 bytes | ✅ Required | High |
| STARK (ethSTARK) | FRI | ~5ms | ~50KB | ❌ Transparent | Medium |
| Bulletproofs | IPA | ~100ms | ~700 bytes | ❌ Transparent | High |

## Decision

We chose **libsnark with Groth16** for the following reasons:

1. **Verification Speed**: Groth16 offers the fastest verification (~10ms), critical for payment processing where proof verification occurs on every high-risk transaction.

2. **Proof Size**: At ~200 bytes, Groth16 proofs are compact enough for blockchain anchoring without excessive gas costs.

3. **Maturity**: libsnark has been audited multiple times and is used in production systems (Zcash, Filecoin).

4. **C++ Native**: libsnark is C++, matching our HFT core and avoiding FFI overhead.

5. **Tooling**: Extensive documentation and circuit libraries available.

**Why Not STARKs?**
- Proof sizes (~50KB) are too large for our blockchain anchoring use case
- Verification is fast, but prover time is significantly longer
- Ecosystem is less mature than SNARKs
- **However**: STARKs are post-quantum secure (see Consequences)

**Why Not Bulletproofs?**
- Verification time (~100ms) exceeds our latency budget
- Better suited for range proofs, not general circuits

## Consequences

### Positive
- Sub-100ms proof verification enables real-time screening
- Compact proofs suitable for immutable ledger storage
- Well-documented trusted setup ceremony procedures
- Extensive audit history provides confidence

### Negative
- **Trusted Setup Required**: Must perform secure ceremony (documented in DEPLOYMENT.md)
- **Not Quantum-Safe**: Groth16 relies on elliptic curve cryptography (BN128/BLS12-381) which is vulnerable to quantum attacks
- **"Toxic Waste" Risk**: Compromise of setup randomness allows proof forgery

### Mitigations
- Documented trusted setup ceremony with multi-party computation option
- HSM signing of verification keys
- Attestation documentation for auditors

### Future Roadmap: Post-Quantum Migration

> **Crypto-Agility Notice**: Current ZKP circuits use SNARKs (Groth16 over BN128).
> Transition to **Post-Quantum STARKs** is accelerated to **Q3 2026** to address "Harvest Now,
> Decrypt Later" threats and regulatory pressure against "Trusted Setups".

The migration path:
1. Abstract circuit definitions to be proof-system agnostic
2. Implement STARK backend using ethSTARK or winterfell
3. Run parallel verification during transition period
4. Full cutover once STARK tooling matures

## References

- [Groth16 Paper](https://eprint.iacr.org/2016/260.pdf)
- [libsnark GitHub](https://github.com/scipr-lab/libsnark)
- [Zcash Sapling Audit](https://electriccoin.co/blog/security-audit-results/)
- [NIST Post-Quantum Cryptography](https://csrc.nist.gov/Projects/post-quantum-cryptography)
