"""
Project Aegis - Prometheus Metrics Module

Exports the following metrics:
- aegis_zkp_queue_depth: Current size of the ZKP thread pool queue
- aegis_risk_score_histogram: Distribution of risk scores
- aegis_zkp_trigger_rate: Rate of ZKP proof generation
- aegis_transactions_processed_total: Total transactions processed by Python bridge
"""

from prometheus_client import (
    Counter,
    Gauge,
    Histogram,
    start_http_server,
    push_to_gateway,
    CollectorRegistry,
    REGISTRY
)
import threading
import time
import logging
from functools import wraps

logger = logging.getLogger("Metrics")

# =============================================================================
# Metric Definitions
# =============================================================================

# ZKP Queue Depth (Backpressure Indicator)
# This gauge shows how many ZKP tasks are waiting in the queue
ZKP_QUEUE_DEPTH = Gauge(
    'aegis_zkp_queue_depth',
    'Current number of pending ZKP proof generation tasks in the thread pool queue',
    ['node_id']
)

# Risk Score Histogram
# Tracks the distribution of risk scores to answer: "Are we blocking too many people?"
RISK_SCORE_HISTOGRAM = Histogram(
    'aegis_risk_score_histogram',
    'Distribution of risk scores from the Digital Analyst',
    ['reason_code'],
    buckets=(0.1, 0.2, 0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0)
)

# ZKP Trigger Rate (Counter)
# Tracks how often ZKP proofs are actually generated
ZKP_TRIGGERS_TOTAL = Counter(
    'aegis_zkp_triggers_total',
    'Total number of ZKP proofs triggered',
    ['trigger_reason']  # 'high_risk', 'high_value', 'dropped'
)

# Transactions Processed
TRANSACTIONS_PROCESSED = Counter(
    'aegis_bridge_transactions_total',
    'Total transactions processed by the Python AI Bridge'
)

# Risk Blocks Counter
RISK_BLOCKS_TOTAL = Counter(
    'aegis_risk_blocks_total',
    'Total transactions blocked due to high risk score (>0.8)'
)

# Processing Latency
PROCESSING_LATENCY = Histogram(
    'aegis_bridge_processing_seconds',
    'Time spent processing each transaction in the Python bridge',
    buckets=(0.001, 0.005, 0.01, 0.025, 0.05, 0.1, 0.25, 0.5, 1.0)
)


# =============================================================================
# Metric Recording Functions
# =============================================================================

def record_risk_score(score: float, reason_code: str = "RC_CLEAR"):
    """Record a risk score observation for the histogram."""
    RISK_SCORE_HISTOGRAM.labels(reason_code=reason_code).observe(score)


def record_zkp_trigger(reason: str = "high_risk"):
    """Record a ZKP proof trigger event."""
    ZKP_TRIGGERS_TOTAL.labels(trigger_reason=reason).inc()


def record_zkp_dropped():
    """Record when a ZKP proof was dropped due to queue overflow."""
    ZKP_TRIGGERS_TOTAL.labels(trigger_reason="dropped").inc()


def record_transaction():
    """Record a transaction processed."""
    TRANSACTIONS_PROCESSED.inc()


def record_block():
    """Record a transaction that was blocked."""
    RISK_BLOCKS_TOTAL.inc()


def update_zkp_queue_depth(executor, node_id: str = "default"):
    """
    Update the ZKP queue depth gauge from the ThreadPoolExecutor.

    Args:
        executor: concurrent.futures.ThreadPoolExecutor instance
        node_id: Identifier for this node in a distributed setup
    """
    try:
        queue_size = executor._work_queue.qsize()
        ZKP_QUEUE_DEPTH.labels(node_id=node_id).set(queue_size)
    except Exception as e:
        logger.warning(f"Failed to read queue depth: {e}")


# =============================================================================
# Decorator for Automatic Latency Tracking
# =============================================================================

def track_latency(func):
    """Decorator to automatically track function execution time."""
    @wraps(func)
    def wrapper(*args, **kwargs):
        with PROCESSING_LATENCY.time():
            return func(*args, **kwargs)
    return wrapper


# =============================================================================
# Background Metrics Collector
# =============================================================================

class MetricsCollector:
    """
    Background thread that periodically collects metrics from external sources.
    For example, polling the ZKP executor queue depth.
    """

    def __init__(self, zkp_executor=None, node_id: str = "aegis_bridge"):
        self.zkp_executor = zkp_executor
        self.node_id = node_id
        self._running = False
        self._thread = None

    def start(self):
        """Start the background collector."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._collect_loop, daemon=True)
        self._thread.start()
        logger.info("Metrics collector started")

    def stop(self):
        """Stop the background collector."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5)

    def _collect_loop(self):
        """Periodically collect metrics."""
        while self._running:
            try:
                # Update ZKP queue depth
                if self.zkp_executor:
                    update_zkp_queue_depth(self.zkp_executor, self.node_id)
            except Exception as e:
                logger.error(f"Metrics collection error: {e}")

            time.sleep(1)  # Collect every second


# =============================================================================
# Server Startup
# =============================================================================

_server_started = False

def start_metrics_server(port: int = 9091):
    """
    Start the Prometheus HTTP server on the specified port.

    Args:
        port: Port to expose /metrics endpoint (default: 9091)
    """
    global _server_started
    if _server_started:
        logger.warning("Metrics server already started")
        return

    start_http_server(port)
    _server_started = True
    logger.info(f"Prometheus metrics server started on port {port}")


def push_metrics(gateway: str, job: str = "aegis_bridge"):
    """
    Push metrics to a Prometheus PushGateway.

    Args:
        gateway: PushGateway URL (e.g., 'localhost:9091')
        job: Job name for grouping metrics
    """
    try:
        push_to_gateway(gateway, job=job, registry=REGISTRY)
        logger.debug(f"Pushed metrics to {gateway}")
    except Exception as e:
        logger.error(f"Failed to push metrics: {e}")


# =============================================================================
# Convenience: Get Current Metrics as Dict (for Testing)
# =============================================================================

def get_current_metrics() -> dict:
    """
    Get current metric values as a dictionary.
    Useful for testing and debugging.
    """
    return {
        "transactions_total": TRANSACTIONS_PROCESSED._value.get(),
        "blocks_total": RISK_BLOCKS_TOTAL._value.get(),
        "zkp_triggers": {
            label: ZKP_TRIGGERS_TOTAL.labels(trigger_reason=label)._value.get()
            for label in ["high_risk", "high_value", "dropped"]
        }
    }
