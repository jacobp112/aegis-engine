"""
Project Aegis - ZKP Database Module (No-PII Architecture)

Uses db_provider abstraction for database-agnostic operations.
Supports both SQLite (dev) and PostgreSQL (production).
"""

import hashlib
import time
import os
import secrets
import logging

from db_provider import get_db_provider, DatabaseProviderError

logger = logging.getLogger(__name__)

SCHEMA_FILE = "zkp_db_schema.sql"

# Cached DB provider instance
_db = None

def _get_db():
    """Get the database provider instance."""
    global _db
    if _db is None:
        _db = get_db_provider()
    return _db


def init_db():
    """Initialize the database schema if needed."""
    db = _get_db()

    # Check if tables exist
    try:
        result = db.fetch_one("SELECT 1 FROM identities LIMIT 1")
        logger.debug("[DB] Tables already exist")
        return
    except Exception:
        pass  # Tables don't exist, create them

    logger.info("[DB] Initializing No-PII Database...")

    if os.path.exists(SCHEMA_FILE):
        with open(SCHEMA_FILE, "r") as f:
            db.execute_script(f.read())
        logger.info("[DB] Schema loaded from file")
    else:
        # Inline schema for when file is not available
        db.execute_script("""
            CREATE TABLE IF NOT EXISTS identities (
                entity_hash TEXT PRIMARY KEY,
                salt TEXT NOT NULL,
                is_sanctioned INTEGER DEFAULT 0,
                created_at REAL
            );

            CREATE TABLE IF NOT EXISTS verifications (
                proof_hash TEXT PRIMARY KEY,
                entity_hash_ref TEXT,
                timestamp REAL,
                result TEXT
            );
        """)
        logger.info("[DB] Schema created inline")


def hash_entity(name, salt=None):
    """
    Create a secure hash of entity name with salt.

    Args:
        name: Entity name to hash
        salt: Optional salt (generated if not provided)

    Returns:
        Tuple of (hash_hex, salt)
    """
    if not salt:
        salt = secrets.token_hex(16)

    # Secure Hash: SHA-256(Name + Salt)
    # In production, use Argon2 or scrypt for password-like data
    hasher = hashlib.sha256()
    hasher.update((name + salt).encode('utf-8'))
    return hasher.hexdigest(), salt


def register_entity(name, is_sanctioned=False):
    """
    Registers an entity WITHOUT storing the name. Only stores Hash + Salt.

    Args:
        name: Entity name (NOT stored)
        is_sanctioned: Whether entity is sanctioned

    Returns:
        The Salt (User must keep this safe!)
    """
    db = _get_db()

    # Create a fresh salt
    entity_hash, salt = hash_entity(name)

    try:
        db.execute(
            "INSERT INTO identities (entity_hash, salt, is_sanctioned, created_at) VALUES (?, ?, ?, ?)",
            (entity_hash, salt, int(is_sanctioned), time.time())
        )
        logger.info(f"[DB] Registered Hash: {entity_hash[:8]}... (Sanctioned={is_sanctioned})")
    except Exception as e:
        if "UNIQUE" in str(e) or "IntegrityError" in str(e):
            logger.warning(f"[DB] Entity already registered.")
        else:
            raise

    return salt


def check_entity_status(name, salt):
    """
    Checks status by re-hashing Name + Salt.
    The DB *cannot* do this without the Name, which it doesn't have.

    Args:
        name: Entity name
        salt: Salt from registration

    Returns:
        Dict with 'found' and 'is_sanctioned' keys
    """
    db = _get_db()

    target_hash, _ = hash_entity(name, salt)

    row = db.fetch_one(
        "SELECT is_sanctioned FROM identities WHERE entity_hash=?",
        (target_hash,)
    )

    if row:
        return {"found": True, "is_sanctioned": bool(row['is_sanctioned'])}
    return {"found": False}


def log_verification(proof_hex, entity_hash_ref, result):
    """
    Log a ZKP verification to the immutable audit trail.

    Args:
        proof_hex: The proof hex string
        entity_hash_ref: Reference to entity hash
        result: Verification result
    """
    db = _get_db()

    proof_hash = hashlib.sha256(proof_hex.encode()).hexdigest()

    try:
        db.execute(
            "INSERT INTO verifications (proof_hash, entity_hash_ref, timestamp, result) VALUES (?, ?, ?, ?)",
            (proof_hash, entity_hash_ref, time.time(), result)
        )
        logger.info(f"[DB] Immutable Verification Logged. ProofHash={proof_hash[:8]}...")
    except Exception as e:
        if "UNIQUE" in str(e) or "IntegrityError" in str(e):
            logger.debug(f"[DB] Verification already logged (idempotent)")
        else:
            raise


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)

    init_db()

    # Demo Registration
    user_salt = register_entity("John Doe", is_sanctioned=False)
    sanctioned_salt = register_entity("Evil Corp", is_sanctioned=True)

    print(f"John's Salt: {user_salt}")

    # Verify lookup works
    status = check_entity_status("John Doe", user_salt)
    print(f"John's Status: {status}")
