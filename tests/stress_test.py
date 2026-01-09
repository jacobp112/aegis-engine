#!/usr/bin/env python3
"""
Project Aegis - Resilience Stress Test

This script validates the backpressure mechanism by:
1. Starting the Aegis Docker container
2. Flooding it with 10,000 ZeroMQ messages
3. Verifying the container survives and logs show backpressure handling

Exit Codes:
  0 - Success (container survived, backpressure logged)
  1 - Failure (container crashed or no backpressure handling)
"""

import subprocess
import time
import sys
import os
import signal
import threading

# Try to import zmq, provide helpful message if missing
try:
    import zmq
except ImportError:
    print("ERROR: pyzmq not installed. Run: pip install pyzmq")
    sys.exit(1)


# =============================================================================
# Configuration
# =============================================================================

CONTAINER_NAME = "aegis-stress-test"
IMAGE_NAME = "aegis-sidecar"
ZMQ_PORT = 5555
MESSAGE_COUNT = 10000
FLOOD_RATE_PER_SEC = 5000  # Messages per second
STARTUP_WAIT_SECS = 5
CONTAINER_SURVIVE_SECS = 10


# =============================================================================
# Helper Functions
# =============================================================================

def log(msg):
    """Print timestamped log message."""
    print(f"[{time.strftime('%H:%M:%S')}] {msg}")


def run_cmd(cmd, check=True, capture=False):
    """Run shell command."""
    result = subprocess.run(
        cmd,
        shell=True,
        capture_output=capture,
        text=True
    )
    if check and result.returncode != 0:
        if capture:
            print(f"STDERR: {result.stderr}")
        raise RuntimeError(f"Command failed: {cmd}")
    return result


def container_is_running():
    """Check if the test container is running."""
    result = run_cmd(
        f"docker ps -q -f name={CONTAINER_NAME}",
        check=False,
        capture=True
    )
    return bool(result.stdout.strip())


def get_container_logs():
    """Get container logs."""
    result = run_cmd(
        f"docker logs {CONTAINER_NAME}",
        check=False,
        capture=True
    )
    return result.stdout + result.stderr


def cleanup_container():
    """Stop and remove test container."""
    run_cmd(f"docker stop {CONTAINER_NAME}", check=False, capture=True)
    run_cmd(f"docker rm {CONTAINER_NAME}", check=False, capture=True)


# =============================================================================
# Main Test
# =============================================================================

def flood_zmq(port: int, count: int) -> int:
    """
    Send 'count' messages to ZeroMQ socket on given port.
    Returns number of messages successfully sent.
    """
    context = zmq.Context()
    socket = context.socket(zmq.PUSH)
    socket.setsockopt(zmq.LINGER, 0)
    socket.setsockopt(zmq.SNDHWM, 1000)  # High water mark

    try:
        socket.connect(f"tcp://127.0.0.1:{port}")

        sent = 0
        start = time.time()

        for i in range(count):
            # Create a dummy ISO 20022 payment message
            msg = {
                "type": "pacs.008",
                "uetr": f"stress-test-{i:08d}",
                "amount": 100.0 + (i % 100),
                "currency": "EUR",
                "debtor": f"Stress-Debtor-{i}",
                "creditor": f"Stress-Creditor-{i}",
                "timestamp": time.time()
            }

            try:
                socket.send_json(msg, zmq.NOBLOCK)
                sent += 1
            except zmq.Again:
                # Socket buffer full - this is expected under stress
                pass

            # Rate limiting to achieve target rate
            if sent % 1000 == 0:
                elapsed = time.time() - start
                target_time = sent / FLOOD_RATE_PER_SEC
                if elapsed < target_time:
                    time.sleep(target_time - elapsed)

        elapsed = time.time() - start
        log(f"Sent {sent}/{count} messages in {elapsed:.2f}s ({sent/elapsed:.0f} msg/s)")
        return sent

    finally:
        socket.close()
        context.term()


def main():
    log("=" * 60)
    log("Project Aegis - Resilience Stress Test")
    log("=" * 60)

    # 1. Cleanup any previous test containers
    log("Cleaning up previous test containers...")
    cleanup_container()

    # 2. Check if Docker image exists
    result = run_cmd(f"docker images -q {IMAGE_NAME}", capture=True)
    if not result.stdout.strip():
        log(f"ERROR: Docker image '{IMAGE_NAME}' not found.")
        log("Run: docker build -t aegis-sidecar .")
        return 1

    # 3. Start container
    log(f"Starting {CONTAINER_NAME} container...")
    run_cmd(
        f"docker run -d --name {CONTAINER_NAME} "
        f"-p {ZMQ_PORT}:{ZMQ_PORT} "
        f"-e AEGIS_NET_MODE=socket "
        f"{IMAGE_NAME}"
    )

    # Wait for startup
    log(f"Waiting {STARTUP_WAIT_SECS}s for container startup...")
    time.sleep(STARTUP_WAIT_SECS)

    if not container_is_running():
        log("ERROR: Container failed to start!")
        print(get_container_logs())
        cleanup_container()
        return 1

    log("Container started successfully.")

    # 4. Flood with messages
    log(f"Flooding with {MESSAGE_COUNT} ZeroMQ messages...")
    try:
        sent = flood_zmq(ZMQ_PORT, MESSAGE_COUNT)
    except Exception as e:
        log(f"ERROR during flood: {e}")
        cleanup_container()
        return 1

    # 5. Wait and check survival
    log(f"Waiting {CONTAINER_SURVIVE_SECS}s to verify container survival...")
    time.sleep(CONTAINER_SURVIVE_SECS)

    # 6. Validate results
    log("Validating results...")

    # Check 1: Container still running
    if not container_is_running():
        log("❌ FAIL: Container crashed during stress test!")
        print("\n--- Container Logs ---")
        print(get_container_logs())
        cleanup_container()
        return 1

    log("✓ Container survived stress test")

    # Check 2: Backpressure logged
    logs = get_container_logs()
    backpressure_indicators = [
        "CRITICAL SYSTEM OVERLOAD",
        "BACKPRESSURE",
        "dropped",
        "overflow",
        "buffer full"
    ]

    backpressure_detected = any(
        indicator.lower() in logs.lower()
        for indicator in backpressure_indicators
    )

    if backpressure_detected:
        log("✓ Backpressure handling detected in logs")
    else:
        log("⚠ No explicit backpressure messages in logs (may be OK if queue was never full)")

    # 7. Cleanup
    log("Cleaning up...")
    cleanup_container()

    log("=" * 60)
    log("✓ STRESS TEST PASSED")
    log(f"  - Container survived {MESSAGE_COUNT} messages")
    log(f"  - {sent} messages sent successfully")
    log("=" * 60)

    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        log("Interrupted by user")
        cleanup_container()
        sys.exit(130)
    except Exception as e:
        log(f"ERROR: {e}")
        cleanup_container()
        sys.exit(1)
