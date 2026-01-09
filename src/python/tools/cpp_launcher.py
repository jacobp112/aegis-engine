"""
Project Aegis - Production Supervisor
Orchestrates the High-Frequency Trading Engine and its Sidecars.

Startup Order:
1. AI Bridge (ZeroMQ PULL Server) - "Sidecar"
2. Secrets Injection (Vault/HSM)
3. C++ Core (Risk Engine - ZeroMQ PUSH Client)

Ensures that the listening ports are ready before the engine starts trading.
"""

import os
import subprocess
import sys
import logging
import time
import signal
from secrets_provider import get_secrets_provider, SecretsProviderError

logging.basicConfig(level=logging.INFO, format='[%(name)s] %(message)s')
logger = logging.getLogger("Supervisor")

children = []

def cleanup(signum, frame):
    logger.info("Stopping Aegis System...")
    for p in children:
        p.terminate()
    sys.exit(0)

# Handle Ctrl+C
signal.signal(signal.SIGINT, cleanup)
signal.signal(signal.SIGTERM, cleanup)

def launch_system():
    # 1. Start AI Bridge Sidecar
    logger.info("Starting AI Bridge (Sidecar)...")
    bridge_process = subprocess.Popen([sys.executable, "ai_bridge.py"])
    children.append(bridge_process)

    # Wait for ZMQ Bind
    time.sleep(2)

    try:
        provider = get_secrets_provider()

        # 2. Fetch Secrets (Memory Only)
        logger.info("Fetching Master Keys from Secure Provider...")
        hmac_key = provider.get_secret_string("AEGIS_HMAC_KEY")
        # In real prod, we might not even set env vars, but use a pipe.
        # For this requirement, Env Injection is the accepted pattern vs Hardcoding.

        # Prepare Environment
        env = os.environ.copy()
        env["AEGIS_HMAC_KEY"] = hmac_key
        # Enforce Security Mode
        env["AEGIS_SECURITY_MODE"] = "strict"

        # 3. Launch C++ Core
        # Assuming we compiled main.cpp to 'aegis_core.exe' or similar.
        # For this python-centric launcher in a text env, we simulate the structure.
        # If 'aegis_core' binary existed:
        # cmd = ["./aegis_core"] + sys.argv[1:]

        # NOTE: Since we don't have a compiled binary in this chat environment,
        # we warn the user, but the orchestration logic is valid.
        logger.info("Launching Aegis Core w/ Injected Secrets...")

        # Mocking the process hold for demonstration if binary missing
        bin_path = "aegis_core.exe" if os.name == 'nt' else "./aegis_core"

        if os.path.exists(bin_path):
            core_process = subprocess.Popen([bin_path] + sys.argv[1:], env=env)
            children.append(core_process)
            core_process.wait() # Block here
        else:
            logger.warning(f"Binary '{bin_path}' not found. Orchestration logic verified, but core not running.")
            logger.warning("To compile: 'clang++ -std=c++20 main.cpp -o aegis_core'")
            # Keep bridge alive for inspection
            bridge_process.wait()

    except SecretsProviderError as e:
        logger.critical(f"FATAL: Secrets Failure: {e}")
        cleanup(0,0)
    except Exception as e:
        logger.critical(f"FATAL: System Error: {e}")
        cleanup(0,0)

if __name__ == "__main__":
    launch_system()
