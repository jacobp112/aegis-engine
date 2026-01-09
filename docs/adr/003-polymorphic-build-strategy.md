# ADR-003: Polymorphic Build Strategy

## Status

Accepted

## Date

2026-01-09

## Context

Project Aegis must deploy across heterogeneous infrastructure:

1. **Cloud VMs** (AWS EC2, Azure VMs): Standard x86_64, no AVX-512
2. **Bare-Metal HFT Servers**: Intel Skylake-X or newer with AVX-512
3. **Development Machines**: Mixed architectures (Intel, AMD, Apple Silicon via emulation)

The C++ core uses SIMD intrinsics for performance-critical paths (risk scoring, hash computation). We needed a strategy to support all targets without maintaining separate codebases.

**Requirements:**
- Single codebase for all deployment targets
- Optimal performance on high-end hardware (AVX-512)
- Graceful fallback on commodity hardware
- CI/CD must validate all configurations

**Alternatives Considered:**

| Option | Pros | Cons |
|--------|------|------|
| Runtime CPU Detection | Single binary | Complex, runtime overhead |
| **Compile-Time Flags** | Optimal codegen, simple | Multiple binaries |
| Fat Binary (Multi-Arch) | Single artifact | Large binary, complex tooling |
| Separate Repositories | Clean separation | Maintenance nightmare |

## Decision

We chose **Compile-Time Polymorphism** via CMake flags:

```cmake
option(ENABLE_AVX512 "Enable AVX-512 optimisations" AUTO)

if(ENABLE_AVX512)
    add_compile_options(-mavx512f -march=native)
    add_definitions(-DAEGIS_ENTERPRISE_MODE)
else()
    add_compile_options(-O3)
    add_definitions(-DAEGIS_STANDARD_MODE)
endif()
```

**Build Editions:**

| Edition | Flag | Target | Performance |
|---------|------|--------|-------------|
| Standard | `-DENABLE_AVX512=OFF` | Cloud, Dev, CI | Baseline |
| Enterprise | `-DENABLE_AVX512=ON` | HFT Production | +40% throughput |

**Container Strategy:**
- Two container image tags: `latest` (Standard) and `latest-enterprise`
- CI builds and tests both configurations in matrix
- Deployment selects image based on node capabilities

## Consequences

### Positive
- Optimal codegen for each target (no runtime dispatch overhead)
- CI validates both paths, preventing "works on my machine" issues
- Clear documentation of hardware requirements per edition
- Customers can choose edition based on infrastructure

### Negative
- Two container images to manage
- Must ensure feature parity between editions
- Developers must test changes against both configurations

### Mitigations
- CI matrix builds both editions on every PR
- Shared test suite runs against both binaries
- Documentation clearly states which features require Enterprise

## Implementation Details

### CMake Auto-Detection

```cmake
if(ENABLE_AVX512 STREQUAL "AUTO")
    include(CheckCXXCompilerFlag)
    check_cxx_compiler_flag("-mavx512f" AVX512_SUPPORTED)
    if(AVX512_SUPPORTED)
        set(ENABLE_AVX512 ON)
        message(STATUS "[Aegis] AVX-512 detected. Building Enterprise Edition.")
    else()
        set(ENABLE_AVX512 OFF)
        message(STATUS "[Aegis] AVX-512 NOT detected. Building Standard Edition.")
    endif()
endif()
```

### Verification

After build, verify AVX-512 instructions are present:

```bash
objdump -d aegis_engine | grep 'zmm' | wc -l
# Enterprise: Should show >100 ZMM register uses
# Standard: Should show 0
```

## References

- [Intel AVX-512 Programming Guide](https://www.intel.com/content/www/us/en/developer/articles/technical/intel-avx-512-instructions.html)
- [CMake Feature Detection](https://cmake.org/cmake/help/latest/module/CheckCXXCompilerFlag.html)
