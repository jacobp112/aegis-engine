# Compilation Instructions for Project Aegis Matching Engine

## Prerequisites
- **OS**: Linux (kernel 4.4+) - *Note: Windows DPDK support exists but Linux is preferred for extreme low latency.*
- **Hardware**: NIC supporting DPDK (Mellanox ConnectX-4+, Intel X710/XL710), CPU with AVX-512F support (Skylake-X or newer).
- **Libraries**: DPDK (Data Plane Development Kit) 20.11 LTS or newer.

## Compilation Support
You need `pkg-config` to locate DPDK libraries and `gcc` or `clang` with AVX-512 support enabled.

### Makefile
Save the following as `Makefile` in the same directory as `main.cpp`.

```makefile
# Makefile for Project Aegis
PKGCONF ?= pkg-config

# Build using pkg-config variables if possible
ifneq ($(shell $(PKGCONF) --exists libdpdk && echo 0),0)
$(error "no installation of DPDK found")
endif

PC_FILE := $(shell $(PKGCONF) --path libdpdk)
CFLAGS += -O3 $(shell $(PKGCONF) --cflags libdpdk)
CFLAGS += -march=native -mavx512f -D_GNU_SOURCE -std=c++20
LDFLAGS = $(shell $(PKGCONF) --libs libdpdk)

# Explicitly link against math or pthread if needed (DPDK usually handles this)
LDFLAGS += -lstdc++

SRC = main.cpp
TARGET = aegis-engine

all: $(TARGET)

$(TARGET): $(SRC)
	$(CC) $(CFLAGS) $(SRC) -o $@ $(LDFLAGS)

clean:
	rm -f $(TARGET)
```

## Running the Engine
1.  **Allocate Hugepages**:
    ```bash
    echo 1024 > /sys/kernel/mm/hugepages/hugepages-2048kB/nr_hugepages
    ```
2.  **Bind NIC to DPDK-compatible driver** (e.g., `vfio-pci` or `uio_pci_generic`):
    ```bash
    dpdk-devbind.py --bind=vfio-pci 0000:01:00.0
    ```
3.  **Run the application**:
    ```bash
    # -l 1 uses core 1. -n 4 uses 4 memory channels.
    sudo ./aegis-engine -l 1 -n 4
    ```

## Verification of Optimizations
- **AVX-512**: Inspect assembly output `objdump -d aegis-engine | grep zmm` to verify ZMM registers are used.
- **Zero-Copy**: The code uses `rte_pktmbuf_mtod` which gives a direct pointer to the NIC's DMA ring buffer.
- **Polling Mode**: The `lcore_main` loop uses `rte_eth_rx_burst` in a tight `while(1)` loop, avoiding OS interrupts.
