#!/bin/bash
set -e

docker build -t zigbee-ci ./.cicd

docker run --rm \
  -v $(pwd):/workspace \
  -w /workspace \
  zigbee-ci \
  bash -c "
    python3 .cicd/ci_run_flow.py
  "
