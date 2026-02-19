#!/usr/bin/env python3

import sys
import importlib


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit("Usage: ci_run_flow.py <flow>")

    flow_name = sys.argv[1]

    try:
        module = importlib.import_module(f"flows.{flow_name}")
    except ModuleNotFoundError as e:
        raise RuntimeError(f"Unknown flow: {flow_name}") from e

    if not hasattr(module, "run"):
        raise RuntimeError(
            f"Flow '{flow_name}' does not define required run() function"
        )

    module.run()


if __name__ == "__main__":
    main()
