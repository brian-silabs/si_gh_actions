FROM debian:bookworm-slim

ENV DEBIAN_FRONTEND=noninteractive

RUN apt-get update && \
    apt-get install -y --no-install-recommends \
        python3 \
        python3-yaml \
        git \
        clang-tidy \
        clang-tools \
        cppcheck \
        unzip \
        bzip2 \
        ca-certificates \
        openssl \
        libgl1 \
        libglib2.0-0 \
        curl && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /workspace
