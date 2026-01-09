# ADR-001: IPC Mechanism Selection

## Status

Accepted

## Date

2026-01-09

## Context

Project Aegis requires ultra-low latency communication between the C++ HFT core and the Python AI bridge. The C++ core processes payments at >100k TPS and must offload high-risk transactions to Python for ML inference without blocking the hot path.

**Requirements:**
- Latency: <10µs per message (P99)
- Throughput: 50,000+ messages/second sustained
- Reliability: Must handle backpressure without data loss
- Deployment: Must work in containerised (Docker/Kubernetes) environments

**Alternatives Considered:**

| Option | Latency | Throughput | Complexity | Kubernetes Support |
|--------|---------|------------|------------|-------------------|
| gRPC | ~100µs | 10k/s | Medium | ✅ Native |
| HTTP/REST | ~1ms | 1k/s | Low | ✅ Native |
| Redis Pub/Sub | ~50µs | 50k/s | Medium | ✅ Via service |
| Shared Memory | ~1µs | 1M/s | High | ⚠️ Requires /dev/shm |
| **ZeroMQ + Ring Buffer** | ~5µs | 200k/s | Medium | ✅ Via shared volume |
| Unix Domain Sockets | ~10µs | 100k/s | Low | ✅ Native |

## Decision

We chose **ZeroMQ (PUSH/PULL pattern)** combined with a **Lock-Free Ring Buffer** for the following reasons:

1. **Latency**: ZeroMQ IPC transport achieves <5µs latency, meeting our <10µs requirement.

2. **Backpressure Handling**: The lock-free ring buffer provides natural backpressure. When full, the C++ core can either drop messages (with metrics) or block, configurable per deployment.

3. **Decoupling**: ZeroMQ allows the Python bridge to restart independently without crashing the C++ core.

4. **Kubernetes Compatibility**: Works with shared memory volumes (`emptyDir` with `medium: Memory`), unlike raw shared memory which requires `hostPath`.

5. **Industry Standard**: ZeroMQ is widely used in trading systems (Bloomberg, JPMorgan) and has proven reliability.

**Why Not Redis?**
- Redis adds network hop latency (~50µs minimum)
- Requires additional infrastructure (Redis cluster)
- Overkill for single-pod communication

**Why Not gRPC?**
- gRPC's serialisation overhead (~100µs) exceeds our latency budget
- HTTP/2 framing adds unnecessary complexity for simple JSON messages
- gRPC is used for external APIs, not internal IPC

## Consequences

### Positive
- Sub-10µs message passing achieved
- C++ and Python can be developed/tested independently
- Natural backpressure via ring buffer sizing
- Battle-tested library with excellent documentation

### Negative
- Requires shared memory volume in Kubernetes (`emptyDir` with `medium: Memory`)
- Learning curve for developers unfamiliar with ZeroMQ patterns
- Message ordering must be handled carefully (single consumer simplifies this)

### Mitigations
- Documented Kubernetes deployment with shared volume configuration
- Created abstraction layer (`IpcRingBuffer`) to hide ZeroMQ details
- Added Prometheus metrics for queue depth monitoring
