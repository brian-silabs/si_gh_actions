FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 \
        python3-yaml \
        git \
        clang-tidy \
        clang-tools \
        unzip \
        bzip2 \
        ca-certificates \
        openssl \
        libgl1 \
        libglib2.0-0 \
        build-essential \
        cmake \
        curl && \
    rm -rf /var/lib/apt/lists/*

RUN git clone https://github.com/danmar/cppcheck.git /tmp/cppcheck \
        && cd /tmp/cppcheck \
        && git fetch --tags \
        && git checkout $(git describe --tags $(git rev-list --tags --max-count=1)) \
        && cmake -S . -B build \
        && cmake --build build -j$(nproc) \
        && cmake --install build \
        && rm -rf /tmp/cppcheck
 
RUN apt-get remove -y --no-install-recommends \
        build-essential \
        cmake && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
