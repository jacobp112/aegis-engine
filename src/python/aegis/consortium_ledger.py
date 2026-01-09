"""
Project Aegis - Consortium Ledger (Enterprise Abstraction)
Supports Strategy Pattern for DLT (Corda, Fabric) vs File (Dev).
"""

import json
import time
import abc
import os
import logging

logger = logging.getLogger(__name__)

# --- LEDGER INTERFACE ---
class LedgerProvider(abc.ABC):
    @abc.abstractmethod
    def write_signal(self, data: dict):
        pass

    @abc.abstractmethod
    def read_signals(self, consortium_id: str) -> list:
        pass

# --- IMPLEMENTATION: FILESYSTEM (DEV) ---
class FileSystemLedger(LedgerProvider):
    def __init__(self, filepath="network_signals.jsonl"):
        self.filepath = filepath

    def write_signal(self, data: dict):
        with open(self.filepath, "a") as f:
            f.write(json.dumps(data) + "\n")

    def read_signals(self, consortium_id: str) -> list:
        results = []
        if not os.path.exists(self.filepath): return []
        with open(self.filepath, "r") as f:
            for line in f:
                try:
                    rec = json.loads(line)
                    if rec.get("consortium_id") == consortium_id:
                        results.append(rec)
                except: pass
        return results

# --- IMPLEMENTATION: R3 CORDA (PROD STUB) ---
class CordaRpcLedger(LedgerProvider):
    def __init__(self, node_url, rpc_user, rpc_pass):
        self.node_url = node_url
        logger.info(f"[CORDA] Connected to Node {node_url}")

    def write_signal(self, data: dict):
        logger.info(f"[CORDA] Flow 'SubmitRiskSignal' triggered with {data['consortium_id']}")
        # client.startFlow(SubmitRiskSignal, data)

    def read_signals(self, consortium_id: str) -> list:
        logger.info(f"[CORDA] Vault Query for {consortium_id}")
        return []

# --- FACTORY ---
class ConsortiumLedger:
    def __init__(self):
        mode = os.environ.get("AEGIS_LEDGER_MODE", "file").lower()
        if mode == "corda":
            self.provider = CordaRpcLedger("localhost:10002", "user1", "test")
        else:
            self.provider = FileSystemLedger()

    def write_signal(self, data):
        self.provider.write_signal(data)

    def read_signals(self, cid):
        return self.provider.read_signals(cid)
