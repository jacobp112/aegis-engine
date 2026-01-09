"""
Project Aegis - Anchor Service (Checkpointing)

Periodically reads the latest block hash from the audit chain and "anchors" it
to a trusted external immutable storage (simulated here as a WORM log file).
This prevents history rewrites (long-range attacks) on the internal database.

In production, this would write to:
- Public Blockchain (Ethereum/Bitcoin transaction)
- AWS S3 Object Lock (Compliance Mode)
- Transparency Log (Trillian)
"""

import time
import logging
import os
from contextlib import contextmanager

from blockchain_audit import get_ledger

# Configuration
ANCHOR_INTERVAL_SECONDS = 600  # 10 minutes (as requested)
ANCHOR_LOG_FILE = "aegis_anchor_log.txt"

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] [ANCHOR] %(message)s'
)
logger = logging.getLogger("AnchorService")

def write_anchor(block_height: int, block_hash: str):
    """
    Write the anchor checkpoint to WORM storage.
    Format: timestamp | height | hash
    """
    timestamp = time.time()
    entry = f"{timestamp} | Height:{block_height} | Hash:{block_hash}\n"

    # Simulate WORM storage append
    # In production, use boto3 for S3 Object Lock or web3.py for Ethereum
    try:
        with open(ANCHOR_LOG_FILE, "a") as f:
            f.write(entry)
        logger.info(f"Anchored Block #{block_height} to {ANCHOR_LOG_FILE}")
    except Exception as e:
        logger.critical(f"FAILED TO WRITE ANCHOR: {e}")

def run_anchor_service():
    """Main service loop."""
    logger.info("Starting Anchor Service (Interval: 10m)...")

    ledger = get_ledger()

    while True:
        try:
            # 1. Read latest from our internal chain
            # Note: access private method or add public getter in future refactor
            # For now, we trust the ledger singleton provides access
            tip = ledger._get_chain_tip()

            height = tip['height']
            block_hash = tip['block_hash']

            if height > 0:
                # 2. Anchor it
                write_anchor(height, block_hash)
            else:
                logger.debug("Chain empty, skipping anchor.")

        except Exception as e:
            logger.error(f"Error in anchor loop: {e}")

        # 3. Wait
        time.sleep(ANCHOR_INTERVAL_SECONDS)

if __name__ == "__main__":
    # For demo purposes, run once immediately
    logger.info("Anchor Service Started.")
    run_anchor_service()
