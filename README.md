# Project Aegis

**Enterprise-Grade KYC/AML Compliance Engine**

A high-frequency, ultra-low latency compliance screening engine designed for real-time payment processing in banking and financial services environments.

---

## Table of Contents

1. [Overview](#overview)
2. [Architecture](#architecture)
3. [Prerequisites](#prerequisites)
4. [Repository Structure](#repository-structure)
5. [Building from Source](#building-from-source)
6. [Development Setup](#development-setup)
7. [Testing](#testing)
8. [Configuration](#configuration)
9. [API Reference](#api-reference)
10. [Contributing](#contributing)

---

## Overview

Project Aegis is a hybrid C++/Python compliance engine that provides:

- **Sub-microsecond Latency**: C++ HFT core with AVX-512 optimisations
- **Real-time Risk Scoring**: ML-based behavioural analysis with explainable AI (XAI)
- **Zero-Knowledge Proofs**: Privacy-preserving verification without exposing PII
- **ISO 20022 Compliance**: Native support for `pacs.008` and related message formats
- **Enterprise Integration**: Kafka ingress, gRPC/Protobuf APIs, HSM key management

### Key Features

| Feature | Description |
|---------|-------------|
| **Lock-Free Ring Buffers** | Wait-free producer/consumer queues for HFT workloads |
| **ZKP Privacy Layer** | zk-SNARK proofs using libsnark for privacy-preserving compliance |
| **Consortium Ledger** | Anonymised risk signal sharing between institutions |
| **Prometheus Metrics** | Full-stack observability with Grafana dashboards |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│                        External Systems                               │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │
│  │   Kafka     │  │   gRPC      │  │   HSM       │  │  Sanctions  │  │
│  │   Broker    │  │   Clients   │  │   (PKCS#11) │  │   Lists     │  │
│  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  │
└─────────┼────────────────┼────────────────┼────────────────┼─────────┘
          │                │                │                │
          ▼                ▼                ▼                ▼
┌─────────────────────────────────────────────────────────────────────┐
│                        AEGIS CORE (C++)                              │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │  kafka_ingress.hpp  │  main.cpp  │  risk_engine.hpp  │  HFT    │ │
│  │  ─────────────────  │ ──────────  │ ───────────────── │  Core   │ │
│  │  Kafka Consumer     │ Orchestrator│ Fast Risk Engine  │         │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                              │ ZeroMQ (IPC)                          │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                    AI BRIDGE (Python)                            │ │
│  │  ai_bridge.py  │  digital_analyst.py  │  consortium_node.py     │ │
│  │  ──────────────│ ─────────────────────│ ───────────────────     │ │
│  │  ZMQ Receiver  │ ML Risk Inference    │ ZKP Broadcasting        │ │
│  └─────────────────────────────────────────────────────────────────┘ │
│                              │                                       │
│                              ▼                                       │
│  ┌─────────────────────────────────────────────────────────────────┐ │
│  │                    ZKP LAYER (C++)                               │ │
│  │  zkp_prover.cpp  │  zkp_verifier.cpp  │  zkp_circuits.hpp       │ │
│  └─────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────┘
                              │
                              ▼
                    ┌─────────────────┐
                    │  SQLite/ZKP DB  │
                    │  (No PII Stored)│
                    └─────────────────┘
```

### Component Overview

| Component | Language | Purpose |
|-----------|----------|---------|
| `main.cpp` | C++ | HFT matching engine core with DPDK support |
| `ai_bridge.py` | Python | ML inference and consortium coordination |
| `digital_analyst.py` | Python | Behavioural risk scoring with XAI |
| `zkp_prover.cpp` | C++ | zk-SNARK proof generation |
| `zkp_verifier.cpp` | C++ | Zero-knowledge proof verification |
| `consortium_node.py` | Python | Anonymised risk signal broadcasting |

### Threat Model & Trust Boundaries

Aegis operates with clearly defined trust boundaries:

| Category | Status | Details |
|----------|--------|----------|
| **Trusted** | ✅ | HSM (key storage), C++ Core memory (assumes root access is restricted) |
| **Semi-Trusted** | ⚠️ | Python Bridge (treated as "Advisor" only; C++ enforces final blocks) |
| **Untrusted** | ❌ | Network (TLS required), External APIs (sanctions lists, consortium peers) |

**Privacy Guarantees**:
- PII is **never** written to disk unencrypted
- ZKP proofs store *validity*, not *data*
- Audit logs contain masked identifiers only (e.g., `AB****`)
- The ZKP database contains cryptographic commitments, not plaintext

**Attack Surface**:
| Vector | Mitigation |
|--------|------------|
| Network MITM | Mandatory TLS 1.3 for all external connections |
| Memory Extraction | C++ core uses secure memory wiping; no PII in Python heap |
| Key Compromise | HSM-backed keys with PKCS#11; keys never leave hardware |
| Model Poisoning | Model weights signed and verified on load |
| Proof Forgery | ZKP trusted setup ceremony with toxic waste destruction |

### Crypto-Agility Roadmap

> **Post-Quantum Notice**: Current ZKP circuits use SNARKs (Groth16 over BN128/BLS12-381 curves), which are **not quantum-safe**. Transition to Post-Quantum STARKs is planned for 2027 to address "Harvest Now, Decrypt Later" threats from quantum computing advances.

| Timeline | Milestone |
|----------|-----------|
| **2026 Q4** | Abstract circuit definitions to be proof-system agnostic |
| **2027 Q2** | Implement STARK backend (ethSTARK/winterfell) |
| **2027 Q3** | Parallel verification (SNARK + STARK) for transition |
| **2028 Q1** | Full STARK cutover; deprecate SNARK circuits |

See [ADR-002: ZKP Library Selection](docs/adr/002-zkp-library-selection.md) for detailed rationale.

---

## Prerequisites

### System Requirements

| Component | Minimum | Recommended |
|-----------|---------|-------------|
| **OS** | Linux (kernel 4.4+) | Ubuntu 22.04 LTS |
| **CPU** | x86_64 with AVX2 | Skylake-X+ (AVX-512) |
| **RAM** | 8 GB | 32 GB |
| **NIC** | Standard Ethernet | Mellanox ConnectX-4+ (DPDK) |

### Build Dependencies

**C++ Core:**
```bash
# Ubuntu/Debian
sudo apt-get install -y \
    build-essential cmake pkg-config \
    libdpdk-dev dpdk \
    libzmq3-dev librdkafka-dev \
    libgmp-dev libssl-dev \
    libgtest-dev
```

**Python Bridge:**
```bash
# Python 3.10+
pip install -r requirements.txt
```

**ZKP Libraries** (libsnark + dependencies):
```bash
# See https://github.com/scipr-lab/libsnark for installation
sudo apt-get install libprocps-dev
git clone https://github.com/scipr-lab/libsnark.git
cd libsnark && mkdir build && cd build
cmake -DWITH_SUPERCOP=OFF ..
make && sudo make install
```

---

## Repository Structure

```
project-aegis/
├── README.md                    # Developer documentation
├── DEPLOYMENT.md                # Operations guide
├── CI_CD.md                     # Pipeline documentation
├── LICENSE                      # Proprietary licence
├── requirements.txt             # Python runtime dependencies
├── requirements-dev.txt         # Python dev/test dependencies
│
├── src/
│   ├── cpp/                     # C++ HFT Core
│   │   ├── main.cpp             # Engine entry point
│   │   ├── hft_core.hpp         # Lock-free ring buffers
│   │   ├── risk_engine.hpp      # Fast risk evaluation
│   │   ├── kafka_ingress.hpp    # Kafka consumer
│   │   ├── metrics.hpp          # Prometheus metrics
│   │   ├── telemetry.hpp        # OpenTelemetry
│   │   ├── rules_loader.hpp     # Dynamic rules hot-reload
│   │   └── CMakeLists.txt       # CMake configuration
│   │
│   ├── zkp/                     # Zero-Knowledge Proofs
│   │   ├── zkp_prover.cpp       # zk-SNARK prover
│   │   ├── zkp_verifier.cpp     # zk-SNARK verifier
│   │   ├── zkp_circuits.hpp     # Circuit definitions
│   │   └── trusted_setup.cpp    # Trusted setup ceremony
│   │
│   └── python/
│       ├── aegis/               # Core Python package
│       │   ├── __init__.py
│       │   ├── ai_bridge.py     # ZMQ bridge (ML inference)
│       │   ├── digital_analyst.py  # Behavioural risk scoring
│       │   ├── consortium_node.py  # ZKP broadcasting
│       │   ├── secrets_provider.py # HSM/Vault abstraction
│       │   └── ...              # Other modules
│       │
│       └── tools/               # CLI utilities
│           ├── dashboard.py     # Streamlit UI
│           ├── cpp_launcher.py  # C++ core launcher
│           └── train_*.py       # Model training scripts
│
├── proto/                       # Protocol Buffers
│   └── aegis.proto              # gRPC API definitions
│
├── config/                      # Configuration
│   ├── model_weights.json       # ML model weights
│   └── zkp_db_schema.sql        # Database schema
│
├── deploy/                      # Deployment
│   ├── Dockerfile               # Container build
│   ├── docker-compose.yml       # Development stack
│   └── docker-compose.monitoring.yml
│
├── monitoring/                  # Observability
│   ├── prometheus.yaml
│   ├── alerts.yaml
│   ├── alertmanager.yaml
│   └── grafana-dashboard.json
│
├── tests/                       # Test suites
│   ├── cpp/                     # GTest unit tests
│   ├── python/                  # pytest suite
│   └── stress_test.py
│
└── docs/                        # Documentation
    ├── adr/                     # Architectural Decision Records
    └── COMPILATION.md           # DPDK build guide
```

---

## Building from Source

### C++ Core (CMake)

```bash
# Clone and navigate to the repository
cd project-aegis

# Create build directory
mkdir -p build && cd build

# Configure (auto-detects AVX-512)
cmake -DBUILD_TESTS=ON ..

# Build all targets
make -j$(nproc)

# Run tests
ctest --output-on-failure
```

#### Build Options

| Option | Default | Description |
|--------|---------|-------------|
| `ENABLE_AVX512` | AUTO | Enable AVX-512 SIMD optimisations |
| `BUILD_TESTS` | OFF | Build GTest test suite |
| `ENABLE_ASAN` | OFF | Enable AddressSanitizer |

### Python Components

```bash
# Create virtual environment
python3 -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -r requirements-dev.txt

# Generate Protobuf stubs (if modifying .proto)
python -m grpc_tools.protoc -I. --python_out=. --grpc_python_out=. aegis.proto
```

---

## Development Setup

### Quick Start (Docker)

```bash
# Start the full development stack
docker-compose up --build

# Access the dashboard
open http://localhost:8501
```

### Local Development

1. **Start the C++ core** (requires Kafka or use replay mode):
   ```bash
   ./build/aegis_engine --replay-mode sample_transactions.log
   ```

2. **Start the Python bridge**:
   ```bash
   python ai_bridge.py
   ```

3. **Start the dashboard**:
   ```bash
   streamlit run dashboard.py --server.port 8501
   ```

### IDE Configuration

**VS Code** (recommended `.vscode/settings.json`):
```json
{
    "python.defaultInterpreterPath": ".venv/bin/python",
    "C_Cpp.default.configurationProvider": "ms-vscode.cmake-tools",
    "cmake.buildDirectory": "${workspaceFolder}/build"
}
```

---

## Testing

### C++ Tests (GTest)

```bash
cd build
cmake -DBUILD_TESTS=ON ..
make aegis_tests
./aegis_tests  # or: ctest --output-on-failure
```

### Python Tests (pytest)

```bash
# Run all tests with coverage
pytest tests/python/ -v --cov=. --cov-report=html

# Run specific test file
pytest tests/python/test_digital_analyst.py -v

# Run in parallel (faster)
pytest tests/python/ -n auto
```

### Stress Testing

```bash
# Requires Docker
python tests/stress_test.py --duration 60 --rate 10000
```

---

## Configuration

### Environment Variables

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `AEGIS_SECRETS_MODE` | No | `env` | Secrets backend: `env`, `hsm`, `vault` |
| `AEGIS_SECURITY_MODE` | No | `strict` | Security mode: `strict`, `permissive` |
| `AEGIS_HSM_LIB` | For HSM | `/usr/lib/libsofthsm2.so` | PKCS#11 library path |
| `AEGIS_HSM_TOKEN` | For HSM | `AegisToken` | HSM token label |
| `AEGIS_HSM_PIN` | For HSM | - | HSM PIN |
| `AEGIS_NET_MODE` | No | `socket` | Network mode: `socket`, `dpdk` |

### Model Weights

The risk engine loads model weights from `model_weights.json`:

```json
{
    "velocity_weight": 0.4,
    "amount_weight": 0.3,
    "geo_weight": 0.2,
    "time_weight": 0.1
}
```

---

## API Reference

### gRPC API (aegis.proto)

**ScreenTransaction** — Real-time payment screening:

```protobuf
rpc ScreenTransaction (ScreeningRequest) returns (ScreeningResponse) {}
```

**Request** (ISO 20022 aligned):
```protobuf
message ScreeningRequest {
  string msg_id = 1;
  PaymentInfo pmt_inf = 2;
  Debtor debtor = 3;
  Creditor creditor = 4;
  string risk_context = 5;  // "CROSS_BORDER", "DOMESTIC"
}
```

**Response**:
```protobuf
message ScreeningResponse {
  string msg_id = 1;
  string status = 2;          // "CLEAR", "BLOCK", "INVESTIGATE"
  string reason_code = 3;
  repeated MatchDetail matches = 4;
  double latency_ns = 5;
  map<string, float> risk_factors = 6;  // XAI breakdown
}
```

### Internal IPC (ZeroMQ)

The C++ core pushes high-risk transactions to the Python bridge via ZeroMQ PUSH/PULL:

```json
{
    "debtor": "ACME Corp",
    "amount": 50000.00,
    "uetr": "550e8400-e29b-41d4-a716-446655440000"
}
```

### Regulatory Audit API

For compliance and regulatory enquiries, Aegis provides a reconstructible transaction history:

```protobuf
// RPC for Regulatory Audit
rpc GetTransactionAudit (AuditRequest) returns (AuditProof) {}

message AuditRequest {
  string uetr = 1;                    // Transaction ID (ISO 20022 UETR)
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

This API enables auditors to:
- Reconstruct any historical decision
- Verify the model version used at decision time
- Validate cryptographic proofs of compliance
- Confirm timestamp integrity via HSM signatures

---

## Contributing

### Code Style

- **C++**: Follow Google C++ Style Guide, use `clang-format`
- **Python**: PEP 8 enforced via `ruff` and `black`

```bash
# Format Python code
black .
ruff check . --fix

# C++ formatting (if clang-format configured)
clang-format -i *.cpp *.hpp
```

### Pull Request Checklist

- [ ] All tests pass (`ctest` and `pytest`)
- [ ] New features include tests
- [ ] Documentation updated
- [ ] No secrets or PII in commits
- [ ] Changelog updated

### Branch Naming

- `feature/` — New features
- `fix/` — Bug fixes
- `refactor/` — Code refactoring
- `docs/` — Documentation only

---

## Licence

This project is proprietary software. See [LICENSE](LICENSE) for terms.

---

## Contact

For support or enquiries, contact the Aegis development team.
