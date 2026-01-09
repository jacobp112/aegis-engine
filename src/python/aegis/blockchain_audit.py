"""
Project Aegis - Immutable Database Ledger
Fixes:
- Replaced file-based JSONL with SQL-based Merkle Chain.
- Uses db_provider for portability (Postgres/SQLite).
"""

import hashlib
import time
import json
import logging
import secrets
from typing import Optional, Dict, Any
from db_provider import get_db_provider, DatabaseProviderError

logger = logging.getLogger(__name__)

GENESIS_HASH = "0" * 64

class DatabaseLedger:
    def __init__(self):
        self.db = get_db_provider()
        self._init_table()

    def _init_table(self):
        # Create a table that enforces chaining
        schema = """
        CREATE TABLE IF NOT EXISTS audit_chain (
            height INTEGER PRIMARY KEY,
            timestamp REAL,
            prev_hash TEXT NOT NULL,
            data_hash TEXT NOT NULL,
            block_hash TEXT NOT NULL,
            payload TEXT,
            node_id TEXT
        );
        CREATE INDEX IF NOT EXISTS idx_chain_hash ON audit_chain(block_hash);
        """
        self.db.execute_script(schema)

    def _get_chain_tip(self):
        """Fetch the last block to link the new one."""
        row = self.db.fetch_one("SELECT * FROM audit_chain ORDER BY height DESC LIMIT 1")
        if not row:
            return {"height": 0, "block_hash": GENESIS_HASH}
        return row

    def compute_hash(self, prev_hash, timestamp, payload):
        """Merkle Linkage: Hash(Prev + Time + Payload)"""
        raw = f"{prev_hash}|{timestamp}|{payload}"
        return hashlib.sha256(raw.encode()).hexdigest()

    def append_entry(self, payload_dict: Dict[str, Any], node_id="NODE_01"):
        """
        Atomically append a new block linked to the previous one.
        Uses a transaction to ensure integrity.
        """
        payload_json = json.dumps(payload_dict, sort_keys=True)

        with self.db.transaction() as conn:
            # 1. Get Tip (Inside transaction for consistency)
            # Note: In high concurrency, we'd need 'SELECT FOR UPDATE' in Postgres
            tip = self._get_chain_tip()
            new_height = tip["height"] + 1
            prev_hash = tip["block_hash"]

            # 2. Compute New Hash
            ts = time.time()
            data_hash = hashlib.sha256(payload_json.encode()).hexdigest()
            block_hash = self.compute_hash(prev_hash, ts, payload_json)

            # 3. Insert
            self.db.execute(
                """
                INSERT INTO audit_chain
                (height, timestamp, prev_hash, data_hash, block_hash, payload, node_id)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (new_height, ts, prev_hash, data_hash, block_hash, payload_json, node_id)
            )

            logger.info(f"[AUDIT] Block {new_height} mined. Hash: {block_hash[:16]}...")
            return block_hash

    def verify_integrity(self):
        """Walk the SQL chain and verify every hash link."""
        rows = self.db.fetch_all("SELECT * FROM audit_chain ORDER BY height ASC")
        if not rows:
            return True

        expected_prev = GENESIS_HASH
        for i, row in enumerate(rows):
            # 1. Check Link
            if row['prev_hash'] != expected_prev:
                logger.error(f"Integrity Broken at Height {row['height']}: Prev Hash Mismatch")
                return False

            # 2. Check Content
            calculated = self.compute_hash(row['prev_hash'], row['timestamp'], row['payload'])
            if calculated != row['block_hash']:
                logger.error(f"Integrity Broken at Height {row['height']}: Content Modified")
                return False

            expected_prev = row['block_hash']

        logger.info(f"[AUDIT] Chain Verified ({len(rows)} blocks). OK.")
        return True

# Singleton
_ledger = None
def get_ledger():
    global _ledger
    if not _ledger:
        _ledger = DatabaseLedger()
    return _ledger

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    l = get_ledger()

    # Demo Data
    l.append_entry({"event": "ZKP_VERIFY", "status": "SUCCESS", "user": "User_A"})
    l.append_entry({"event": "SANCTION_CHECK", "status": "CLEAN", "user": "User_B"})

    l.verify_integrity()
