-- Database Schema for Aegis ZKP Module (No-PII)

CREATE TABLE IF NOT EXISTS identities (
    entity_hash TEXT PRIMARY KEY,  -- SHA-256(Name + Salt)
    salt TEXT NOT NULL,            -- Unique Salt per user
    is_sanctioned BOOLEAN DEFAULT 0,
    risk_level TEXT DEFAULT 'UNKNOWN'
);

CREATE TABLE IF NOT EXISTS verifications (
    proof_hash TEXT PRIMARY KEY,   -- SHA-256(ProofHex)
    entity_hash_ref TEXT,          -- Foreign Key to Identity Hash
    timestamp REAL,
    result TEXT,                   -- 'ACCEPTED' or 'REJECTED'
    FOREIGN KEY(entity_hash_ref) REFERENCES identities(entity_hash)
);
