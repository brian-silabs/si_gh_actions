import sys

from flows import (
    run_build,
    run_static_analysis,
    run_unit_tests,
    run_integration_tests,
    run_coverage,
    run_security,
    run_smoke,
    run_regression,
)

FLOWS = {
    "build": run_build,
    "static_analysis": run_static_analysis,
    "unit_tests": run_unit_tests,
    "integration_tests": run_integration_tests,
    "coverage": run_coverage,
    "security": run_security,
    "smoke": run_smoke,
    "regression": run_regression,
}


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: ci_run_flow.py <flow>")

    flow = sys.argv[1]

    if flow not in FLOWS:
        raise RuntimeError(f"Unknown flow: {flow}")

    FLOWS[flow]()


if __name__ == "__main__":
    main()