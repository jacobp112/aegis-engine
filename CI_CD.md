# Project Aegis — CI/CD Pipeline Documentation

**Continuous Integration & Deployment Architecture**

This document explains the build, test, and deployment pipeline for Project Aegis, including the polymorphic build strategy that supports multiple deployment targets.

---

## Table of Contents

1. [Pipeline Overview](#pipeline-overview)
2. [Matrix Build Strategy](#matrix-build-strategy)
3. [Build Jobs](#build-jobs)
4. [Test Jobs](#test-jobs)
5. [Security Jobs](#security-jobs)
6. [Deployment Pipeline](#deployment-pipeline)
7. [Branch Strategy](#branch-strategy)
8. [Artifact Management](#artifact-management)

---

## Pipeline Overview

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                            CI/CD PIPELINE                                    │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  ┌─────────┐    ┌─────────────────────────────────────────────────────┐     │
│  │  Push   │───►│                  MATRIX BUILD                        │     │
│  │  / PR   │    │  ┌─────────────┐  ┌─────────────┐  ┌─────────────┐  │     │
│  └─────────┘    │  │  Standard   │  │  Enterprise │  │   ARM64     │  │     │
│                 │  │  (Cloud)    │  │  (AVX-512)  │  │  (Future)   │  │     │
│                 │  └──────┬──────┘  └──────┬──────┘  └──────┬──────┘  │     │
│                 └─────────┼────────────────┼────────────────┼─────────┘     │
│                           │                │                │               │
│                           ▼                ▼                ▼               │
│                 ┌─────────────────────────────────────────────────────┐     │
│                 │                   TEST SUITE                         │     │
│                 │  ┌──────────┐  ┌──────────┐  ┌──────────┐           │     │
│                 │  │  Unit    │  │  Stress  │  │  ZKP     │           │     │
│                 │  │  Tests   │  │  Test    │  │  Verify  │           │     │
│                 │  └──────────┘  └──────────┘  └──────────┘           │     │
│                 └─────────────────────────────────────────────────────┘     │
│                                        │                                     │
│                                        ▼                                     │
│                 ┌─────────────────────────────────────────────────────┐     │
│                 │                SECURITY GATES                        │     │
│                 │  ┌──────────┐  ┌──────────┐  ┌──────────┐           │     │
│                 │  │  SAST    │  │  Secrets │  │  License │           │     │
│                 │  │  Scan    │  │  Scan    │  │  Check   │           │     │
│                 │  └──────────┘  └──────────┘  └──────────┘           │     │
│                 └─────────────────────────────────────────────────────┘     │
│                                        │                                     │
│                                        ▼                                     │
│                 ┌─────────────────────────────────────────────────────┐     │
│                 │              DEPLOY (main branch only)               │     │
│                 │  ┌──────────┐  ┌──────────┐  ┌──────────┐           │     │
│                 │  │  Build   │  │  Push to │  │  Deploy  │           │     │
│                 │  │  Image   │  │  Registry│  │  Staging │           │     │
│                 │  └──────────┘  └──────────┘  └──────────┘           │     │
│                 └─────────────────────────────────────────────────────┘     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

---

## Matrix Build Strategy

Aegis uses a **Polymorphic Build Matrix** to validate compatibility across multiple deployment targets. This ensures the same codebase works on cloud VMs (no AVX-512) and bare-metal HFT servers (with AVX-512).

### Build Matrix

| Job Name | Runs On | CMake Flags | Purpose |
|----------|---------|-------------|---------|
| **Build: Standard** | `ubuntu-latest` | `-DENABLE_AVX512=OFF` | Verifies Cloud/Dev compatibility |
| **Build: Enterprise** | Self-Hosted (AVX-512) | `-DENABLE_AVX512=ON` | Verifies HFT intrinsics & assembly |
| **Build: Debug** | `ubuntu-latest` | `-DENABLE_ASAN=ON` | Memory safety validation |

### Test Matrix

| Job Name | Runs On | Command | Purpose |
|----------|---------|---------|---------|
| **Test: Unit (C++)** | `ubuntu-latest` | `ctest` | GTest unit tests for core components |
| **Test: Unit (Python)** | `ubuntu-latest` | `pytest` | pytest suite for Python bridge |
| **Test: Smurfing** | `ubuntu-latest` | `pytest tests/python/test_smurfing.py` | Regression test for `model_weights.json` tuning |
| **Test: Stress** | `ubuntu-latest` | `docker-compose` | Floods 10k messages to prove backpressure stability |
| **Test: Integration** | `ubuntu-latest` | `docker-compose up` | End-to-end flow validation |

### Security Matrix

| Job Name | Runs On | Tool | Purpose |
|----------|---------|------|---------|
| **Security: ZKP** | `ubuntu-latest` | `zkp_verifier` | Round-trip check of Prover/Verifier artifacts |
| **Security: SAST** | `ubuntu-latest` | `semgrep` | Static application security testing |
| **Security: Secrets** | `ubuntu-latest` | `gitleaks` | Detect hardcoded secrets |
| **Security: Dependencies** | `ubuntu-latest` | `pip-audit`, `trivy` | Vulnerability scanning |

---

## Build Jobs

### Standard Build (Cloud Compatible)

```yaml
build-standard:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Install Dependencies
      run: |
        sudo apt-get update
        sudo apt-get install -y \
          build-essential cmake pkg-config \
          libzmq3-dev librdkafka-dev \
          libgmp-dev libssl-dev

    - name: Configure (Standard Edition)
      run: |
        mkdir -p build && cd build
        cmake -DENABLE_AVX512=OFF -DBUILD_TESTS=ON ../src/cpp

    - name: Build
      run: cmake --build build -j$(nproc)

    - name: Sanitize Build Directory
      run: |
        find build -name "*:*" -prune -exec rm -rf {} +

    - name: Upload Artifacts
      uses: actions/upload-artifact@v4
      with:
        name: aegis-standard
        path: build/
        include-hidden-files: true
```

### Enterprise Build (AVX-512)

```yaml
build-enterprise:
  runs-on: [self-hosted, avx512]  # Requires AVX-512 capable runner
  steps:
    - uses: actions/checkout@v4

    - name: Configure (Enterprise Edition)
      run: |
        mkdir -p build && cd build
        cmake -DENABLE_AVX512=ON -DBUILD_TESTS=ON ..

    - name: Build
      run: cmake --build build -j$(nproc)

    - name: Verify AVX-512 Instructions
      run: |
        objdump -d build/aegis_engine | grep -q 'zmm' || \
          (echo "ERROR: No AVX-512 instructions found!" && exit 1)

    - name: Upload Artifacts
      uses: actions/upload-artifact@v4
      with:
        name: aegis-enterprise
        path: build/
```

---

## Test Jobs

### Unit Tests

```yaml
test-unit:
  needs: [build-standard]
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Download Build Artifacts
      uses: actions/download-artifact@v4
      with:
        name: aegis-standard
        path: build/

    - name: Run C++ Tests
      run: |
        cd build
        ctest -R "^Aegis\." --output-on-failure

    - name: Run Python Tests
      run: |
        pip install -r requirements-dev.txt
        pytest tests/python/ -v --cov=. --cov-report=xml

    - name: Upload Coverage
      uses: codecov/codecov-action@v4
      with:
        files: coverage.xml
```

### Stress Test

```yaml
test-stress:
  needs: [build-standard]
  runs-on: ubuntu-latest
  services:
    kafka:
      image: confluentinc/cp-kafka:7.0.0
      ports:
        - 9092:9092
  steps:
    - uses: actions/checkout@v4

    - name: Start Aegis Stack
      run: |
        # Build image using the correct Dockerfile path
        docker build -f deploy/Dockerfile -t aegis-sidecar .

        # Start services using the deployment compose file
        docker-compose -f deploy/docker-compose.yml up -d

    - name: Run Stress Test
      run: |
        python tests/stress_test.py \
          --duration 60 \
          --rate 10000 \
          --assert-no-drops

    - name: Collect Metrics
      if: always()
      run: |
        curl http://localhost:9090/metrics > stress_metrics.txt
        curl http://localhost:9091/metrics >> stress_metrics.txt

    - name: Upload Results
      uses: actions/upload-artifact@v4
      with:
        name: stress-test-results
        path: stress_metrics.txt
```

### Smurfing Regression Test

```yaml
test-smurfing:
  needs: [build-standard]
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Install Dependencies
      run: pip install -r requirements-dev.txt

    - name: Run Smurfing Detection Tests
      run: |
        pytest tests/python/test_smurfing.py -v \
          --tb=short \
          -x  # Stop on first failure

    - name: Validate Model Weights
      run: |
        python -c "
        import json
        weights = json.load(open('model_weights.json'))
        assert 'velocity_weight' in weights, 'Missing velocity_weight'
        assert sum(weights.values()) == 1.0, 'Weights must sum to 1.0'
        print('Model weights validated successfully')
        "
```

---

## Security Jobs

### ZKP Verification

```yaml
security-zkp:
  needs: [build-standard]
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Download Build Artifacts
      uses: actions/download-artifact@v4
      with:
        name: aegis-standard
        path: build/

    - name: Run ZKP Round-Trip Test
      run: |
        # 1. Trusted Setup (Generates pk.bin and vk.bin)
        ./build/zkp_prover setup build/pk.bin build/vk.bin

        # 2. Generate Proof (User: 2000, Current: 2024, Threshold: 18) -> Valid
        # Output is the proof string, save it to a file
        ./build/zkp_prover build/pk.bin 2024 18 2000 > proof.txt

        # 3. Verify Proof
        # Verifier expects the PROOF STRING as the first argument, not a file path
        PROOF_STR=$(cat proof.txt)
        ./build/zkp_verifier "$PROOF_STR" 2024 18 build/vk.bin

        echo "ZKP round-trip verification PASSED"
```

### SAST Scanning

```yaml
security-sast:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Run Semgrep
      uses: returntocorp/semgrep-action@v1
      with:
        config: >-
          p/security-audit
          p/secrets
          p/python
          p/cpp

    - name: Run Gitleaks
      uses: gitleaks/gitleaks-action@v2
      env:
        GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### Dependency Scanning

```yaml
security-deps:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Python Dependency Audit
      run: |
        pip install pip-audit
        pip-audit -r requirements.txt

    - name: Container Scan (Trivy)
      uses: aquasecurity/trivy-action@master
      with:
        image-ref: aegis-sidecar:latest
        format: 'table'
        exit-code: '1'
        severity: 'CRITICAL,HIGH'
```

---

## Deployment Pipeline

### Container Build & Push

```yaml
deploy:
  needs: [test-unit, test-stress, security-sast, security-zkp]
  if: github.ref == 'refs/heads/main'
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4

    - name: Set up Docker Buildx
      uses: docker/setup-buildx-action@v3

    - name: Login to Container Registry
      uses: docker/login-action@v3
      with:
        registry: ghcr.io
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}

    - name: Build and Push (Standard)
      uses: docker/build-push-action@v5
      with:
        push: true
        tags: |
          ghcr.io/${{ github.repository }}/aegis-sidecar:${{ github.sha }}
          ghcr.io/${{ github.repository }}/aegis-sidecar:latest
        build-args: |
          ENABLE_AVX512=OFF

    - name: Build and Push (Enterprise)
      uses: docker/build-push-action@v5
      with:
        push: true
        tags: |
          ghcr.io/${{ github.repository }}/aegis-sidecar:${{ github.sha }}-enterprise
        build-args: |
          ENABLE_AVX512=ON
```

### Staging Deployment

```yaml
deploy-staging:
  needs: [deploy]
  if: github.ref == 'refs/heads/main'
  runs-on: ubuntu-latest
  environment: staging
  steps:
    - name: Deploy to Staging
      uses: azure/k8s-deploy@v4
      with:
        namespace: aegis-staging
        manifests: |
          k8s/staging/
        images: |
          ghcr.io/${{ github.repository }}/aegis-sidecar:${{ github.sha }}
```

---

## Branch Strategy

| Branch | Purpose | CI Behaviour |
|--------|---------|--------------|
| `main` | Production-ready code | Full pipeline + deploy to staging |
| `develop` | Integration branch | Full pipeline, no deployment |
| `feature/*` | New features | Build + unit tests only |
| `fix/*` | Bug fixes | Build + unit tests only |
| `release/*` | Release candidates | Full pipeline + deploy to staging |

### Merge Requirements

All merges to `main` require:
- ✅ All CI jobs passing
- ✅ Code review approval (2 reviewers)
- ✅ No unresolved security findings
- ✅ Coverage threshold met (≥80%)

---

## Artifact Management

### Build Artifacts

| Artifact | Retention | Purpose |
|----------|-----------|---------|
| `aegis-standard` | 30 days | Cloud-compatible binary |
| `aegis-enterprise` | 30 days | AVX-512 optimised binary |
| `stress-test-results` | 90 days | Performance regression tracking |
| `coverage-reports` | 90 days | Code coverage history |

### Container Images

| Tag Pattern | Description |
|-------------|-------------|
| `latest` | Most recent `main` build |
| `<sha>` | Specific commit build |
| `<sha>-enterprise` | Enterprise edition (AVX-512) |
| `v1.2.3` | Release version |

### Release Artifacts

For each release, the following are published:
- Signed container images
- SHA-256 checksums
- SBOM (Software Bill of Materials)
- ZKP key checksums (verification only, not the keys)

---

## Local Pipeline Execution

Developers can run the full pipeline locally using `act`:

```bash
# Install act (GitHub Actions local runner)
brew install act  # macOS
# or: curl https://raw.githubusercontent.com/nektos/act/master/install.sh | sudo bash

# Run the full pipeline
act -j build-standard
act -j test-unit
act -j security-sast

# Run all jobs
act push
```

---

## Troubleshooting

### Common CI Failures

| Error | Cause | Fix |
|-------|-------|-----|
| `No AVX-512 instructions found` | Wrong runner or flags | Ensure `ENABLE_AVX512=ON` and self-hosted runner |
| `ZKP verification failed` | Mismatched proving/verification keys | Re-run trusted setup or check key checksums |
| `Stress test: drops detected` | Backpressure issue | Review ring buffer sizing and ZKP queue depth |
| `pip-audit: vulnerabilities found` | Outdated dependencies | Update `requirements.txt` and re-run |

---

## Document History

| Version | Date | Author | Changes |
|---------|------|--------|---------|
| 1.0 | 2026-01-09 | Aegis Team | Initial release |
