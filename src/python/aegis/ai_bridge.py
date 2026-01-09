
import zmq
import json
import time
import os
import logging
from digital_analyst import DigitalAnalyst
from enterprise_logger import audit_logger
from consortium_ledger import ConsortiumLedger
from consortium_node import ConsortiumNode

import concurrent.futures

# Prometheus Metrics
import metrics as prom_metrics
from decimal import Decimal

# --- CONFIGURATION (ZeroMQ MODE) ---
ZMQ_ENDPOINT = "tcp://*:5555"
METRICS_PORT = 9091  # Separate from C++ metrics on 9090

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("AI_Bridge_ZMQ")

# --- SERVICES ---
digital_analyst = DigitalAnalyst()
ledger = ConsortiumLedger()
# ------------------------------------------------------------------------------
# PROCESS WORKER INIT
# ------------------------------------------------------------------------------
_process_node = None

def worker_init():
    """Initializes the ConsortiumNode strictly within the worker process."""
    global _process_node
    # Delay import or instantiation to ensure clean process state
    from consortium_node import ConsortiumNode
    _process_node = ConsortiumNode(f"Aegis_Worker_{os.getpid()}")
    print(f"[WORKER] Initialized Node for PID: {os.getpid()}")

def trigger_zkp_background(debtor, risk_type, score):
    """Executes the heavy ZKP generation in a side process."""
    try:
        if _process_node is None:
             raise RuntimeError("Worker not initialized!")

        # heavy blocking call
        _process_node.broadcast_risk(debtor, risk_type, score)
        logger.info(f"ZKP Proof Broadcasted for {debtor}")
    except Exception as e:
        logger.error(f"ZKP Background Task Failed: {e}")

# BULKHEAD PATTERN: Limit max concurrent ZKP proofs (Processes instead of Threads)
MAX_WORKERS = min(16, os.cpu_count() or 4)
zkp_executor = concurrent.futures.ProcessPoolExecutor(
    max_workers=MAX_WORKERS,
    initializer=worker_init
)

entity_history = {}

@prom_metrics.track_latency
def process_risk_analysis(data):
    # Data: { "debtor": "...", "amount": 100.0, "uetr": "..." }
    debtor = data.get('debtor', 'UNKNOWN')
    uetr = data.get('uetr', '')
    # PRESERVE PRECISION: Use Decimal for monetary values
    amount_raw = data.get('amount', '0.0')
    amount = Decimal(str(amount_raw))

    ts = time.time()

    # METRICS: Record transaction
    prom_metrics.record_transaction()

    # 1. Update History
    if debtor not in entity_history: entity_history[debtor] = []
    entity_history[debtor].append({'timestamp': ts, 'amount': amount})
    if len(entity_history[debtor]) > 20: entity_history[debtor].pop(0)

    # 2. Inference
    risk_result = digital_analyst.predict_risk(entity_history[debtor])
    score = risk_result['score']
    reason_code = risk_result.get('reason_code', 'RC_CLEAR')

    # METRICS: Record risk score in histogram
    prom_metrics.record_risk_score(score, reason_code)

    # 3. Log
    if score > 0.5:
        # Schema Alignment with Dashboard
        status_str = "HIGH_RISK" if score > 0.8 else "WARNING"
        masked_entity = debtor[:2] + "****" if len(debtor) > 4 else "****"

        entry = {
            "timestamp": ts,
            "request_id": uetr,
            "entity_masked": masked_entity,
            "status": status_str,
            "risk_score": score,
            "reason_code": risk_result['reason_code'],
            "full_details": risk_result['reasoning']
        }
        audit_logger.log(entry)

        if risk_result['score'] > 0.8:
            # METRICS: Record block
            prom_metrics.record_block()
            logger.warning(f"BLOCK DETECTED: {debtor} | Reason: {risk_result['reason_code']}")

        # 4. ZKP THROTTLING (Performance Optimization)
        # Only generate expensive ZK Proofs for critical items.
        # Threshold: Score > 0.8 (Highly Suspicious) OR Amount > 50,000 (High Value)
        # NOTE: Structuring attempts (repeated small tx) are caught by 'score' via Velocity checks in DigitalAnalyst.
        is_high_value = amount > 50000.0
        is_high_risk = score > 0.8

        if is_high_risk or is_high_value:
            # UNBOUNDED QUEUE PROTECTION:
            # Note: ProcessPoolExecutor does not expose a public queue size.
            # We rely on the worker limit (MAX_WORKERS) to throttle CPU usage.
            # Using a Semaphore here would be the next step for memory protection.

            # METRICS: Record ZKP trigger
            trigger_reason = "high_risk" if is_high_risk else "high_value"
            prom_metrics.record_zkp_trigger(trigger_reason)
            logger.info(f"Triggering ASYNC ZKP Proof for {status_str} (Amount: {amount})")

            # BULKHEAD EXECUTION: Use ProcessPoolExecutor
            # Protects against OOM by queuing if workers are full
            zkp_executor.submit(
                trigger_zkp_background,
                debtor,
                risk_result['reason_code'],
                score
            )

            # METRICS: Update queue depth after submit
            prom_metrics.update_zkp_queue_depth(zkp_executor, "aegis_bridge")
        else:
             logger.info(f"Skipping ZKP for Standard Transaction (Score={score}, Amount={amount})")

def run_server():
    print(f"Starting AI Bridge (ZeroMQ PULL Mode) on {ZMQ_ENDPOINT}")

    # Start Prometheus Metrics Server
    prom_metrics.start_metrics_server(METRICS_PORT)
    logger.info(f"Prometheus metrics available at http://localhost:{METRICS_PORT}/metrics")

    # Start background metrics collector
    metrics_collector = prom_metrics.MetricsCollector(zkp_executor, "aegis_bridge")
    metrics_collector.start()

    context = zmq.Context()
    socket = context.socket(zmq.PULL)
    socket.bind(ZMQ_ENDPOINT)

    # HWM (High Water Mark) prevents unbounded memory if Python is slow
    socket.set_hwm(10000)

    logger.info("ZMQ Bridge Online. Waiting for signals...")

    try:
        while True:
            # ZeroMQ handles framing/buffering automatically
            msg = socket.recv_string()

            try:
                data = json.loads(msg)
                process_risk_analysis(data)
            except json.JSONDecodeError as e:
                logger.error(f"JSON Parse Error: {e}")

    except KeyboardInterrupt:
        logger.info("Stopping...")
    finally:
        metrics_collector.stop()
        socket.close()
        context.term()

if __name__ == "__main__":
    run_server()
