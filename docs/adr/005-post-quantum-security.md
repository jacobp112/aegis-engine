# ADR-005: Post-Quantum Security Strategy

## Status

Accepted

## Date

2026-01-09

## Context

Financial data has a long shelf life (10+ years). Data encrypted today with classical algorithms (RSA, ECC) is vulnerable to "Harvest Now, Decrypt Later" attacks by future quantum computers. To mitigate this risk, Project Aegis must implement a **Hybrid Encryption** strategy that combines battle-tested classical algorithms with NIST-standardized Post-Quantum Cryptography (PQC).

## Decision

We will implement **Hybrid Encryption** for both Data-at-Rest and Data-in-Transit immediately, rather than waiting for a full migration.

### 1. Transport Layer (TLS)
We will enable **Hybrid Key Exchange** (X25519 + Kyber768) for all internal ZMQ and external HTTP traffic.
- **Mechanism**: Use OpenSSL 3.2+ or equivalent libraries supporting `X25519Kyber768Draft00`.
- **Fallback**: Clients strictly enforcing classical algorithms will be rejected for high-value channels.

### 2. Data Encryption (ZKP & Storage)
- **Primary**: Continue using `AES-256-GCM` for symmetric encryption (Quantum-Resistant).
- **Key Encapsulation (KEM)**: For exchanging symmetric keys, we will use a hybrid of **ECDH (Secp256k1)** and **CRYSTALS-Kyber**.
- **Signatures**: Digital signatures for transaction authorization will migrate to a hybrid of **ECDSA** and **Dilithium/Sphincs+**.

## Consequences

### Positive
- **Future Proofing**: Data captured today remains secure against future quantum decryption.
- **Compliance**: Meets emerging banking standards (e.g., CNSA 2.0 timeline).
- **Defense in Depth**: If the PQC algorithm has a flaw, the classical algorithm still protects the data.

### Negative
- **Performance Overhead**: Larger key sizes and slightly slower handshakes.
- **Complexity**: Key management becomes more complex (managing two sets of keys).

## Roadmap

- **Phase 1 (Now)**: Implement Hybrid TLS for all internal IPC.
- **Phase 2 (Q2 2026)**: Upgrade `eu_id_wallet.py` to support hybrid signatures.
- **Phase 3 (Q3 2026)**: Full STARK migration (ADR-002) to remove elliptic curve dependencies entirely from the ZKP layer.
