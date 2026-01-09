# Project Aegis - Sidecar Deployment
#
# This Dockerfile creates a "Sidecar" container for the Aegis Core.
# It isolates the DPDK/Network complexity from the main Banking App.
#
# Usage:
#   docker build -t aegis-sidecar .
#   docker run --privileged -v /hugepages:/hugepages aegis-sidecar

FROM ubuntu:22.04

# 1. Install Dependencies (DPDK, Python, Libs)
RUN apt-get update && apt-get install -y \
    python3 python3-pip \
    libdpdk-dev dpdk \
    build-essential cmake \
    libgtest-dev \
    libzmq3-dev librdkafka-dev \
    libgmp-dev libssl-dev \
    && rm -rf /var/lib/apt/lists/*

# 2. Setup Hugepages (Runtime requirement, but prep dir here)
RUN mkdir -rho /mnt/huge

# 3. Copy Application
WORKDIR /app
COPY . /app

# 4. Build C++ Core
RUN mkdir -p build && cd build && \
    cmake -DENABLE_AVX512=OFF ../src/cpp && \
    make -j$(nproc) && \
    cp aegis_engine ../aegis_engine && \
    cp zkp_prover ../zkp_prover && \
    cp zkp_verifier ../zkp_verifier

# 5. Install Python Deps
RUN pip3 install -r requirements.txt || true

# 6. Expose gRPC / ZeroMQ Port for the Main Bank App
EXPOSE 5555

# 7. Entrypoint - The Secure Launcher
# Uses the Environment-based secret injection
ENV AEGIS_SECRETS_MODE=env
ENV AEGIS_NET_MODE=socket
# Default to socket for container compatibility, user overrides to 'dpdk' if privileged

CMD ["python3", "src/python/tools/cpp_launcher.py"]
