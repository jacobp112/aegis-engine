# Project Aegis — Operational Deployment Guide

**For DevOps Engineers and Site Reliability Engineers**

This guide covers production deployment, infrastructure configuration, monitoring setup, and operational runbooks for Project Aegis.

---

## Table of Contents

1. [Deployment Architecture](#deployment-architecture)
2. [Infrastructure Requirements](#infrastructure-requirements)
3. [Container Deployment](#container-deployment)
4. [Kubernetes Deployment](#kubernetes-deployment)
5. [Secrets Management](#secrets-management)
6. [Monitoring & Observability](#monitoring--observability)
7. [Alerting](#alerting)
8. [Scaling & Performance](#scaling--performance)
9. [Backup & Recovery](#backup--recovery)
10. [Operational Runbooks](#operational-runbooks)
11. [Troubleshooting](#troubleshooting)

---

## Deployment Architecture

### Sidecar Pattern

Aegis deploys as a **sidecar container** alongside your banking application, providing isolation between the DPDK/network complexity and your core services.

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           Kubernetes Pod                                 │
│  ┌─────────────────────────────┐  ┌─────────────────────────────────┐   │
│  │      Banking App            │  │       Aegis Sidecar             │   │
│  │      (Your Service)         │◄─┤  ┌─────────────────────────┐    │   │
│  │                             │  │  │    aegis-core (C++)     │    │   │
│  │   gRPC/REST ───────────────►│──┤  │    Port: 5555 (ZMQ)     │    │   │
│  │                             │  │  │    Port: 9090 (Metrics) │    │   │
│  └─────────────────────────────┘  │  └────────────┬────────────┘    │   │
│                                   │               │ Shared Memory   │   │
│                                   │  ┌────────────▼────────────┐    │   │
│                                   │  │   aegis-brain (Python)  │    │   │
│                                   │  │   Port: 9091 (Metrics)  │    │   │
│                                   │  └─────────────────────────┘    │   │
│                                   └─────────────────────────────────┘   │
│                                                                          │
│  Volumes: /dev/shm (shared memory), /hugepages (optional DPDK)          │
└─────────────────────────────────────────────────────────────────────────┘
```

### Network Topology

```
                                    ┌──────────────────┐
                                    │   Kafka Cluster  │
                                    │  (transactions)  │
                                    └────────┬─────────┘
                                             │
        ┌────────────────────────────────────┼────────────────────────────────────┐
        │                                    │                                     │
        ▼                                    ▼                                     ▼
┌───────────────┐                   ┌───────────────┐                     ┌───────────────┐
│   Aegis Pod   │                   │   Aegis Pod   │                     │   Aegis Pod   │
│   (Zone A)    │◄─────────────────►│   (Zone B)    │◄───────────────────►│   (Zone C)    │
│               │    Consortium      │               │    Consortium        │               │
│               │    ZKP Signals     │               │    ZKP Signals       │               │
└───────┬───────┘                   └───────┬───────┘                     └───────┬───────┘
        │                                    │                                     │
        ▼                                    ▼                                     ▼
┌───────────────┐                   ┌───────────────┐                     ┌───────────────┐
│  Prometheus   │◄──────────────────┤  Prometheus   │────────────────────►│  Prometheus   │
│   (Federated) │                   │   (Central)   │                     │  (Federated)  │
└───────────────┘                   └───────────────┘                     └───────────────┘
```

---

## Infrastructure Requirements

### Hardware Specifications

| Tier | CPU | RAM | Storage | NIC | Use Case |
|------|-----|-----|---------|-----|----------|
| **Standard** | 4 vCPU (AVX2) | 8 GB | 50 GB SSD | 1 Gbps | Development, Testing |
| **Enterprise** | 8 vCPU (AVX-512) | 32 GB | 100 GB NVMe | 10 Gbps | Production (Cloud) |
| **Ultra-Low Latency** | 16 Core (Skylake-X) | 64 GB | 500 GB NVMe | Mellanox 25 Gbps | HFT Production |

### Operating System

- **Recommended**: Ubuntu 22.04 LTS (kernel 5.15+)
- **Minimum**: Any Linux with kernel 4.4+ and glibc 2.31+

### Hugepages Configuration (DPDK Mode)

For production DPDK deployments, configure hugepages:

```bash
# /etc/sysctl.conf
vm.nr_hugepages = 1024
vm.hugetlb_shm_group = 1000

# Mount hugepages
mkdir -p /mnt/huge
mount -t hugetlbfs nodev /mnt/huge -o pagesize=2M
```

---

## Container Deployment

### Building the Container Image

```bash
# Build with standard optimisations
docker build -t aegis-sidecar:latest .

# Build with build args for custom configuration
docker build \
    --build-arg ENABLE_AVX512=OFF \
    -t aegis-sidecar:cloud .
```

### Running with Docker Compose

**Development Stack:**
```bash
docker-compose up -d
```

**Production with Monitoring:**
```bash
docker-compose -f docker-compose.yml -f docker-compose.monitoring.yml up -d
```

### Docker Compose Services

| Service | Image | Ports | Purpose |
|---------|-------|-------|---------|
| `aegis-core` | `aegis-sidecar` | 5555 (ZMQ) | C++ HFT engine |
| `aegis-brain` | `aegis-sidecar` | 9091 (metrics) | Python ML bridge |
| `aegis-pkyc` | `aegis-sidecar` | - | Perpetual KYC feed |
| `aegis-dashboard` | `aegis-sidecar` | 8501 | Streamlit UI |
| `prometheus` | `prom/prometheus` | 9092 | Metrics collection |
| `grafana` | `grafana/grafana` | 3000 | Visualisation |
| `alertmanager` | `prom/alertmanager` | 9093 | Alert routing |

### Environment Variables Reference

```yaml
# docker-compose.yml environment section
environment:
  # Secrets Management
  AEGIS_SECRETS_MODE: "hsm"         # env, hsm, vault
  AEGIS_SECURITY_MODE: "strict"     # strict, permissive

  # HSM Configuration (if AEGIS_SECRETS_MODE=hsm)
  AEGIS_HSM_LIB: "/usr/lib/libsofthsm2.so"
  AEGIS_HSM_TOKEN: "AegisToken"
  AEGIS_HSM_PIN_FILE: "/run/secrets/hsm_pin"

  # Network Mode
  AEGIS_NET_MODE: "socket"          # socket, dpdk

  # Kafka Configuration
  KAFKA_BOOTSTRAP_SERVERS: "kafka-broker:9092"
  KAFKA_TOPIC: "transactions.euro.v1"
  KAFKA_CONSUMER_GROUP: "aegis-screening"

  # Telemetry
  OTEL_EXPORTER_ENDPOINT: "jaeger:6831"
```

---

## Kubernetes Deployment

### Namespace Setup

```bash
kubectl create namespace aegis
kubectl label namespace aegis istio-injection=enabled  # If using Istio
```

### Helm Chart Values

Create `values-production.yaml`:

```yaml
# Aegis Helm Chart Values - Production

replicaCount: 3

image:
  repository: your-registry/aegis-sidecar
  tag: "1.0.0"
  pullPolicy: IfNotPresent

resources:
  core:
    requests:
      cpu: "2"
      memory: "4Gi"
    limits:
      cpu: "4"
      memory: "8Gi"
  bridge:
    requests:
      cpu: "1"
      memory: "2Gi"
    limits:
      cpu: "2"
      memory: "4Gi"

# Shared memory volume (required for IPC)
volumes:
  sharedMemory:
    enabled: true
    sizeLimit: "256Mi"

# HSM Integration
hsm:
  enabled: true
  library: "/usr/lib/libsofthsm2.so"
  tokenLabel: "AegisToken"
  pinSecret: "aegis-hsm-pin"

# Kafka Configuration
kafka:
  bootstrapServers: "kafka.kafka.svc.cluster.local:9092"
  topic: "transactions.euro.v1"
  consumerGroup: "aegis-screening"

# Monitoring
metrics:
  enabled: true
  serviceMonitor:
    enabled: true
    interval: 15s

# Pod Disruption Budget
podDisruptionBudget:
  minAvailable: 2

# Affinity for spreading across zones
affinity:
  podAntiAffinity:
    preferredDuringSchedulingIgnoredDuringExecution:
      - weight: 100
        podAffinityTerm:
          topologyKey: topology.kubernetes.io/zone
```

### Deploy with Helm

```bash
helm install aegis ./charts/aegis \
    -n aegis \
    -f values-production.yaml
```

### Kubernetes Secrets

```bash
# Create HSM PIN secret
kubectl create secret generic aegis-hsm-pin \
    -n aegis \
    --from-file=pin=/path/to/hsm-pin.txt

# Create Kafka credentials (if SASL enabled)
kubectl create secret generic aegis-kafka-creds \
    -n aegis \
    --from-literal=username=aegis-service \
    --from-literal=password=$(cat /path/to/kafka-password)
```

### Service Mesh Configuration (Istio)

```yaml
# VirtualService for traffic management
apiVersion: networking.istio.io/v1beta1
kind: VirtualService
metadata:
  name: aegis
  namespace: aegis
spec:
  hosts:
    - aegis.aegis.svc.cluster.local
  http:
    - route:
        - destination:
            host: aegis
            port:
              number: 5555
      timeout: 100ms
      retries:
        attempts: 3
        perTryTimeout: 30ms
```

---

## Secrets Management

### HSM Integration (PKCS#11)

Aegis supports Hardware Security Modules via PKCS#11:

**Supported HSMs:**
- Thales nShield
- AWS CloudHSM
- Azure Dedicated HSM
- SoftHSM2 (development/testing only)

**Configuration:**
```bash
# Environment variables
export AEGIS_SECRETS_MODE=hsm
export AEGIS_HSM_LIB=/usr/lib/libnshield.so
export AEGIS_HSM_TOKEN=AegisProductionToken
export AEGIS_HSM_PIN_FILE=/run/secrets/hsm_pin
```

### HashiCorp Vault Integration

```bash
# Configure Vault mode
export AEGIS_SECRETS_MODE=vault
export VAULT_ADDR=https://vault.internal:8200
export VAULT_TOKEN_FILE=/run/secrets/vault_token
export VAULT_SECRET_PATH=secret/data/aegis/keys
```

### Security Mode Enforcement

| Mode | Behaviour |
|------|-----------|
| `strict` | Fails immediately if secrets loaded from environment variables |
| `permissive` | Allows environment variables with warning (development only) |

> **Warning**: Never use `permissive` mode in production. The `strict` mode is enforced by default and requires HSM or Vault.

---

## Monitoring & Observability

### Prometheus Metrics

**C++ Core (Port 9090):**
| Metric | Type | Description |
|--------|------|-------------|
| `aegis_transactions_total` | Counter | Total transactions processed |
| `aegis_risk_blocks_total` | Counter | Transactions blocked |
| `aegis_drops_total` | Counter | Dropped due to backpressure |
| `aegis_ingress_tps` | Gauge | Current transactions per second |
| `aegis_ring_buffer_usage` | Gauge | Ring buffer utilisation % |

**Python Bridge (Port 9091):**
| Metric | Type | Description |
|--------|------|-------------|
| `aegis_zkp_queue_depth` | Gauge | Pending ZKP proof requests |
| `aegis_zkp_triggers_total` | Counter | ZKP proofs generated |
| `aegis_zkp_dropped_total` | Counter | ZKP requests dropped (overload) |
| `aegis_risk_score_histogram` | Histogram | Distribution of risk scores |
| `aegis_bridge_processing_seconds` | Histogram | Processing latency |

### Deploying the Monitoring Stack

```bash
# Deploy Prometheus, Grafana, Alertmanager
docker-compose -f docker-compose.monitoring.yml up -d

# Access Grafana
open http://localhost:3000
# Default credentials: admin / aegis_secure_password
```

### Grafana Dashboard

Import the pre-built dashboard from `monitoring/grafana-dashboard.json`:

1. Navigate to Grafana → Dashboards → Import
2. Upload `grafana-dashboard.json`
3. Select Prometheus data source

**Dashboard Panels:**
- Transactions Per Second (TPS)
- Risk Score Distribution
- Block Rate
- ZKP Queue Depth
- Latency Percentiles (p50, p95, p99)
- Error Rate

### OpenTelemetry Tracing

Aegis exports traces to Jaeger-compatible backends:

```bash
# Configure telemetry endpoint
export OTEL_EXPORTER_ENDPOINT=jaeger:6831

# Deploy Jaeger (development)
docker run -d \
    -p 16686:16686 \
    -p 6831:6831/udp \
    jaegertracing/all-in-one:latest
```

---

## Alerting

### Alert Rules

The following alerts are pre-configured in `monitoring/alerts.yaml`:

| Alert | Severity | Condition | Description |
|-------|----------|-----------|-------------|
| `AegisHighBlockRate` | warning | block_rate > 10% for 5m | Unusually high transaction blocks |
| `AegisHighLatency` | warning | p99 > 10ms for 5m | Processing latency degraded |
| `AegisDropsDetected` | critical | drops > 0 for 1m | Backpressure causing data loss |
| `AegisZKPQueueFull` | critical | queue > 5000 | ZKP subsystem overloaded |
| `AegisProcessDown` | critical | up == 0 for 30s | Aegis process not responding |

### Alertmanager Configuration

Edit `monitoring/alertmanager.yaml`:

```yaml
global:
  smtp_smarthost: 'smtp.internal:587'
  smtp_from: 'aegis-alerts@yourbank.com'

route:
  group_by: ['alertname', 'severity']
  group_wait: 30s
  group_interval: 5m
  repeat_interval: 4h
  receiver: 'ops-team'
  routes:
    - match:
        severity: critical
      receiver: 'pagerduty'

receivers:
  - name: 'ops-team'
    email_configs:
      - to: 'sre-team@yourbank.com'

  - name: 'pagerduty'
    pagerduty_configs:
      - service_key: '<YOUR_PAGERDUTY_KEY>'
```

---

## Scaling & Performance

### Horizontal Scaling

Aegis scales horizontally via Kafka consumer groups:

```yaml
# Increase replicas
helm upgrade aegis ./charts/aegis \
    -n aegis \
    --set replicaCount=5
```

Each replica joins the same Kafka consumer group, automatically partitioning workload.

### Vertical Scaling

For ultra-low latency, optimise single-node performance:

1. **CPU Pinning**: Bind C++ core to dedicated CPU cores
2. **NUMA Awareness**: Allocate memory on same NUMA node as NIC
3. **Hugepages**: Enable 2MB or 1GB hugepages for DPDK
4. **Kernel Tuning**: Disable CPU frequency scaling, enable `performance` governor

```bash
# CPU pinning example (core 2-3 for Aegis)
taskset -c 2-3 ./aegis_engine

# Kernel parameters (/etc/sysctl.conf)
net.core.rmem_max = 134217728
net.core.wmem_max = 134217728
net.ipv4.tcp_rmem = 4096 87380 134217728
net.ipv4.tcp_wmem = 4096 87380 134217728
```

### Performance Benchmarks

| Configuration | TPS | Latency (p99) |
|--------------|-----|---------------|
| Standard (Docker) | 50,000 | 2ms |
| Enterprise (K8s) | 200,000 | 500µs |
| Ultra-Low Latency (DPDK) | 1,000,000+ | <100µs |

---

## Backup & Recovery

### ZKP Database Backup

The ZKP database contains cryptographic audit trails (no PII):

```bash
# Backup SQLite database
sqlite3 /app/aegis_zkp.db ".backup /backup/aegis_zkp_$(date +%Y%m%d).db"

# Verify backup integrity
sqlite3 /backup/aegis_zkp_*.db "PRAGMA integrity_check;"
```

### Audit Log Archival

```bash
# Archive JSONL audit logs
gzip /app/aegis_audit.jsonl
aws s3 cp /app/aegis_audit.jsonl.gz s3://aegis-audit-archive/$(date +%Y/%m/%d)/

# Rotate logs
mv /app/aegis_audit.jsonl /app/aegis_audit.jsonl.bak
touch /app/aegis_audit.jsonl
```

### Disaster Recovery

| Component | RPO | RTO | Strategy |
|-----------|-----|-----|----------|
| Configuration | 0 | 5 min | GitOps (ArgoCD) |
| ZKP Database | 1 hour | 15 min | Hourly snapshots to S3 |
| Model Weights | 0 | 5 min | Version controlled in Git |
| Audit Logs | 0 | Async | Real-time streaming to SIEM |

---

## Operational Runbooks

### Runbook: High Block Rate Alert

**Symptoms**: `AegisHighBlockRate` alert triggered

**Investigation:**
1. Check Grafana dashboard for block rate trend
2. Examine recent risk score distribution
3. Review audit logs for blocked entities

```bash
# Check recent blocks
grep '"status": "BLOCK"' /app/aegis_audit.jsonl | tail -20 | jq .

# Check if sanctions list was recently updated
grep "Sanctions" /var/log/aegis/aegis.log | tail -10
```

**Resolution:**
- If legitimate spike: Document and acknowledge
- If false positives: Review model weights, consider retraining
- If attack: Engage security team

---

### Runbook: ZKP Queue Full

**Symptoms**: `AegisZKPQueueFull` alert triggered

**Immediate Actions:**
1. Scale Python bridge replicas
2. Increase ZKP worker pool size

```bash
# Increase ZKP thread pool (runtime)
export AEGIS_ZKP_WORKERS=100

# Scale bridge pods (Kubernetes)
kubectl scale deployment aegis-brain -n aegis --replicas=5
```

**Root Cause Analysis:**
- Check for sudden transaction volume spike
- Review ZKP proof generation latency
- Verify consortium network connectivity

---

### Runbook: Process Restart

**Graceful Restart:**
```bash
# Kubernetes rolling restart
kubectl rollout restart deployment/aegis-core -n aegis
kubectl rollout restart deployment/aegis-brain -n aegis

# Docker Compose
docker-compose restart aegis-core aegis-brain
```

**Emergency Stop (Data Loss Risk):**
```bash
# Force kill (last resort)
docker-compose kill aegis-core

# Check for pending transactions
docker-compose logs aegis-core | grep "PENDING"
```

---

### Runbook: Model Update Deployment

```bash
# 1. Validate new model weights
python -c "import json; json.load(open('model_weights_new.json'))"

# 2. Backup current weights
cp model_weights.json model_weights.json.bak

# 3. Deploy new weights (hot reload)
cp model_weights_new.json model_weights.json

# 4. Verify hot reload occurred
docker-compose logs aegis-core | grep "Rules Reloaded"

# 5. Monitor for anomalies (15 min)
# Watch Grafana for risk score distribution changes
```

---

### Runbook: ZKP Trusted Setup Ceremony

> **Critical Security Operation**: This ceremony **must** be performed before the first production deployment. If the "toxic waste" (randomness) from this setup isn't destroyed, an administrator could forge fake proofs.

**Auditor Question**: "Who generated the keys, and how do we know they didn't keep the backdoor?"

**Prerequisites:**
- Air-gapped machine (no network connectivity)
- Security Officer present
- HSM for key signing
- Secure disposal equipment (degausser or shredder)

**Procedure:**

1.  **Air-Gapped Generation**:
    Run `trusted_setup` on a machine physically disconnected from the network.
    ```bash
    # On air-gapped machine
    ./build/trusted_setup --interactive --output /secure/zkp_keys/
    ```

2.  **Entropy Collection**:
    Use the `trusted_setup` interactive mode to collect randomness (mouse movements, keyboard input, hardware RNG).
    ```bash
    # The tool will prompt for entropy sources
    # Minimum 256 bits of entropy required
    ```

3.  **Artifact Generation**:
    The ceremony produces two key files:
    - `proving_key.bin` — Used by prover (large, ~50MB)
    - `verification_key.bin` — Used by verifier (small, ~1KB)

4.  **Artifact Verification & Signing**:
    The output keys must be signed by the Security Officer using HSM.
    ```bash
    # Sign with HSM-backed key
    pkcs11-tool --module $AEGIS_HSM_LIB \
        --sign --mechanism SHA256-RSA-PKCS \
        --input-file /secure/zkp_keys/verification_key.bin \
        --output-file /secure/zkp_keys/verification_key.sig

    # Record ceremony metadata
    echo "Ceremony Date: $(date -u +%Y-%m-%dT%H:%M:%SZ)" > /secure/zkp_keys/ceremony_log.txt
    echo "Operator: $(whoami)" >> /secure/zkp_keys/ceremony_log.txt
    sha256sum /secure/zkp_keys/*.bin >> /secure/zkp_keys/ceremony_log.txt
    ```

5.  **Toxic Waste Destruction**:
    ```bash
    # Securely wipe the randomness file (7-pass overwrite + zero)
    shred -u -z -n 7 /tmp/entropy.bin
    shred -u -z -n 7 /tmp/tau.bin
    shred -u -z -n 7 /tmp/alpha.bin
    shred -u -z -n 7 /tmp/beta.bin

    # Verify deletion
    ls -la /tmp/*.bin  # Should show "No such file"
    ```

6.  **Physical Media Destruction**:
    - If using USB drives: physically destroy with shredder
    - If using HDDs: degauss and shred
    - Document destruction with photographs

7.  **Distribution**:
    Copy *only* the signed keys to the production container:
    ```bash
    # Transfer via secure channel (USB, never network)
    cp /secure/zkp_keys/proving_key.bin /app/zkp/
    cp /secure/zkp_keys/verification_key.bin /app/zkp/
    cp /secure/zkp_keys/verification_key.sig /app/zkp/
    ```

8.  **Verification on Deployment**:
    ```bash
    # Verify signature on startup
    pkcs11-tool --module $AEGIS_HSM_LIB \
        --verify --mechanism SHA256-RSA-PKCS \
        --input-file /app/zkp/verification_key.bin \
        --signature-file /app/zkp/verification_key.sig
    ```

**Ceremony Attestation Document**:
Create a signed attestation documenting:
- Date/time of ceremony
- Names of all participants
- Serial numbers of destroyed media
- SHA-256 hashes of generated keys
- Photographs of media destruction

---

### Runbook: Regulatory Export (Transaction Reconstruction)

**Purpose**: Regulators require a "reconstructible history" of any transaction to prove why it was blocked, even 6+ months after the event.

**Use Case**: Responding to regulatory enquiry: *"Show me the complete decision trail for UETR 550e8400-e29b-41d4-a716-446655440000"*

**Export Command (CLI)**:
```bash
# Export full audit proof for a specific transaction
python -m aegis.regulatory_export \
    --uetr "550e8400-e29b-41d4-a716-446655440000" \
    --output /exports/audit_proof.json \
    --include-zkp
```

**Export via gRPC API**:
```protobuf
// RPC for Regulatory Audit
rpc GetTransactionAudit (AuditRequest) returns (AuditProof) {}

message AuditRequest {
  string uetr = 1;                    // Transaction ID
  bool include_zkp_proof = 2;         // Include cryptographic proof
  bool include_model_snapshot = 3;    // Include model weights used
}

message AuditProof {
  string uetr = 1;
  string decision = 2;                // "CLEAR", "BLOCK", "INVESTIGATE"
  string reason_code = 3;             // ISO reason code
  string model_version_hash = 4;      // SHA-256 of model weights active at decision time
  bytes zkp_proof = 5;                // The cryptographic proof of the decision
  string timestamp_signature = 6;     // HSM signature of the timestamp
  map<string, float> risk_factors = 7; // XAI breakdown at decision time
  string sanctions_list_version = 8;  // Version of sanctions data used
}
```

**Output Format**:
```json
{
  "uetr": "550e8400-e29b-41d4-a716-446655440000",
  "decision": "BLOCK",
  "reason_code": "RC_VELOCITY_EXCEEDED",
  "timestamp": "2026-01-09T15:04:05Z",
  "model_version_hash": "sha256:a3f2b8c1...",
  "risk_factors": {
    "VELOCITY": 0.92,
    "AMOUNT": 0.45,
    "GEO": 0.12
  },
  "zkp_proof_b64": "eyJwaV9hIjogWzEyMzQ1Li4.",
  "hsm_timestamp_signature": "MEUCIQDx...",
  "sanctions_list_version": "OFAC-SDN-2026-01-08"
}
```

**Retention Policy**:
| Data Type | Retention | Storage |
|-----------|-----------|----------|
| Audit Logs (JSONL) | 7 years | S3 Glacier |
| ZKP Proofs | 7 years | SQLite + S3 |
| Model Snapshots | 7 years | Git LFS |

---

## Troubleshooting

### Common Issues

#### Issue: "ZMQ Connection Refused"

**Cause**: Python bridge not ready when C++ core starts

**Solution**:
```yaml
# docker-compose.yml
aegis-brain:
  depends_on:
    aegis-core:
      condition: service_started
  healthcheck:
    test: ["CMD", "python", "-c", "import zmq"]
    interval: 5s
    retries: 3
```

#### Issue: "HSM Failure: Token not found"

**Cause**: HSM not initialised or wrong token label

**Solution**:
```bash
# List available tokens
pkcs11-tool --module $AEGIS_HSM_LIB --list-slots

# Initialise token (development)
softhsm2-util --init-token --slot 0 --label AegisToken
```

#### Issue: "FATAL: Security Violation"

**Cause**: Trying to load secrets from environment variables in strict mode

**Solution**:
- Configure HSM or Vault backend
- Or (development only): `export AEGIS_SECURITY_MODE=permissive`

#### Issue: High Memory Usage

**Cause**: ZKP proof accumulation or ring buffer overflow

**Solution**:
```bash
# Check ZKP queue
curl http://localhost:9091/metrics | grep zkp_queue

# Reduce ZKP retention
export AEGIS_ZKP_RETENTION_HOURS=24

# Restart to clear buffers
docker-compose restart aegis-brain
```

### Log Locations

| Component | Log Path | Format |
|-----------|----------|--------|
| C++ Core | stdout/stderr | Plain text |
| Python Bridge | stdout/stderr | Structured JSON |
| Audit Trail | `/app/aegis_audit.jsonl` | JSONL |
| ZKP Proofs | SQLite DB | Binary |

### Debug Mode

```bash
# Enable verbose logging
export AEGIS_LOG_LEVEL=DEBUG

# C++ core debug (recompile required)
cmake -DCMAKE_BUILD_TYPE=Debug ..
```

---

## Appendix: Port Reference

| Port | Protocol | Service | Description |
|------|----------|---------|-------------|
| 5555 | TCP (ZMQ) | aegis-core | IPC between C++ and Python |
| 8501 | HTTP | aegis-dashboard | Streamlit UI |
| 9090 | HTTP | aegis-core | Prometheus metrics |
| 9091 | HTTP | aegis-brain | Prometheus metrics |
| 9092 | HTTP | prometheus | Prometheus UI (remapped) |
| 9093 | HTTP | alertmanager | Alertmanager UI |
| 3000 | HTTP | grafana | Grafana UI |
| 6831 | UDP | telemetry | Jaeger agent |

---

## Appendix: Health Checks

```bash
# C++ Core health (ZMQ ping)
python -c "import zmq; ctx=zmq.Context(); s=ctx.socket(zmq.REQ); s.connect('tcp://localhost:5555'); print('OK')"

# Python Bridge health (HTTP)
curl -f http://localhost:9091/metrics || exit 1

# Full stack health
curl -f http://localhost:8501/healthz || exit 1
```

---

## Security Hardening Checklist (Production)

Before "Go-Live", verify the following security controls are in place:

### Container Security

- [ ] **Non-Root User**: Container runs as non-root user (UID 1000)
  ```yaml
  securityContext:
    runAsUser: 1000
    runAsGroup: 1000
    runAsNonRoot: true
  ```

- [ ] **Read-Only Root Filesystem**: Enabled in Kubernetes/Docker
  ```yaml
  securityContext:
    readOnlyRootFilesystem: true
  ```

- [ ] **Capabilities Dropped**: All capabilities dropped, add back only what's needed
  ```yaml
  securityContext:
    capabilities:
      drop:
        - ALL
      add:
        - NET_ADMIN  # Only if using DPDK
  ```

- [ ] **No Privilege Escalation**: Disabled
  ```yaml
  securityContext:
    allowPrivilegeEscalation: false
  ```

### Network Policy

- [ ] **Default Deny Egress**: Block all outbound traffic by default
  ```yaml
  apiVersion: networking.k8s.io/v1
  kind: NetworkPolicy
  metadata:
    name: aegis-egress
  spec:
    podSelector:
      matchLabels:
        app: aegis
    policyTypes:
      - Egress
    egress:
      - to:
          - podSelector:
              matchLabels:
                app: kafka
      - to:
          - podSelector:
              matchLabels:
                app: hsm-proxy
  ```

- [ ] **mTLS Enabled**: All gRPC/ZMQ channels use mutual TLS
- [ ] **Ingress Restricted**: Only allow traffic from known banking app pods

### Memory Protection

- [ ] **Swap Disabled**: Prevents latency spikes and key leakage to disk
  ```bash
  # Verify swap is off
  free -h | grep -i swap  # Should show 0

  # Disable permanently
  sudo swapoff -a
  sudo sed -i '/swap/d' /etc/fstab
  ```

- [ ] **vm.max_map_count Locked**: Set appropriately for Elasticsearch/DPDK
  ```bash
  sysctl vm.max_map_count=262144
  ```

- [ ] **Core Dumps Disabled**: Prevent secrets leaking to disk
  ```bash
  ulimit -c 0
  echo 'kernel.core_pattern=|/bin/false' >> /etc/sysctl.conf
  ```

### ZKP Hygiene

- [ ] **Trusted Setup Completed**: Ceremony performed and documented
- [ ] **Toxic Waste Destroyed**: Verified with attestation document
- [ ] **Proving Key Checksum**: Matches the signed release artifact
  ```bash
  sha256sum /app/zkp/proving_key.bin
  # Compare with signed checksum in release notes
  ```
- [ ] **Verification Key Signed**: HSM signature verified on startup

### Secrets Management

- [ ] **HSM Mode Enabled**: `AEGIS_SECRETS_MODE=hsm`
- [ ] **Strict Security Mode**: `AEGIS_SECURITY_MODE=strict`
- [ ] **No Environment Secrets**: Keys never passed via env vars in production
- [ ] **Pin Secure**: HSM PIN loaded from file, not environment

### Audit & Compliance

- [ ] **Audit Logging Enabled**: All decisions logged to `aegis_audit.jsonl`
- [ ] **Log Shipping Configured**: Logs streaming to SIEM in real-time
- [ ] **Retention Policy Applied**: 7-year retention for regulatory compliance
- [ ] **Regulatory Export Tested**: `GetTransactionAudit` API verified working

### Monitoring & Alerting

- [ ] **Prometheus Scraping**: Both ports 9090 and 9091 being scraped
- [ ] **Grafana Dashboards**: Imported and data flowing
- [ ] **Alertmanager Configured**: PagerDuty/email routes tested
- [ ] **Critical Alerts Enabled**: `AegisDropsDetected`, `AegisZKPQueueFull`

### Pre-Flight Verification

Run the following commands to verify the deployment:

```bash
# 1. Verify container security context
kubectl get pod -n aegis -o jsonpath='{.items[0].spec.securityContext}'

# 2. Verify network policies
kubectl get networkpolicy -n aegis

# 3. Verify HSM connectivity
kubectl exec -n aegis deploy/aegis-core -- \
  pkcs11-tool --module $AEGIS_HSM_LIB --list-slots

# 4. Verify ZKP keys
kubectl exec -n aegis deploy/aegis-core -- \
  sha256sum /app/zkp/proving_key.bin /app/zkp/verification_key.bin

# 5. Verify metrics endpoints
curl -s http://aegis-core:9090/metrics | head -5
curl -s http://aegis-brain:9091/metrics | head -5

# 6. Run smoke test
kubectl exec -n aegis deploy/aegis-core -- \
  ./aegis_engine --self-test
```

### Sign-Off

| Check | Verified By | Date |
|-------|-------------|------|
| Container Security | | |
| Network Policy | | |
| Memory Protection | | |
| ZKP Hygiene | | |
| Secrets Management | | |
| Audit & Compliance | | |
| Monitoring & Alerting | | |

**Production Deployment Approved**: ______________________ Date: ______________

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-09 | Aegis Team | Initial release |

---

## Support

For operational support:
- **Slack**: #aegis-ops
- **PagerDuty**: Aegis SRE Team
- **Documentation**: Internal wiki
