# .cicd/flows/security.py

import json
import os
import subprocess
from pathlib import Path
from typing import Tuple
from lib.slt_env import setup_slt_environment
from lib.project import detect_single_slcp

# --------------------------------------------------
# Helpers
# --------------------------------------------------


def run_cmd(cmd, cwd=None) -> Tuple[int, str]:
    """
    Run command and capture stdout+stderr.
    Never raises.
    """
    p = subprocess.run(
        cmd,
        cwd=cwd,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=False,
    )
    return p.returncode, p.stdout


def which(exe: str) -> bool:
    from shutil import which as _which

    return _which(exe) is not None


def detect_sbom(sbom_dir: Path) -> Path:
    """
    Prefer SPDX JSON, fallback to CycloneDX JSON.
    """
    spdx_json = sbom_dir / "spdx_bom.spdx.json"
    cyclonedx_json = sbom_dir / "cyclonedx_bom.json"

    if spdx_json.exists():
        return spdx_json

    if cyclonedx_json.exists():
        return cyclonedx_json

    raise RuntimeError(
        f"No supported SBOM found in {sbom_dir} "
        "(expected spdx_bom.spdx.json or cyclonedx_bom.json)"
    )


# --------------------------------------------------
# Vulnerability parsing
# --------------------------------------------------


def count_trivy_high_critical(report: Path) -> int:
    if not report.exists():
        return 0

    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except Exception:
        return 0

    total = 0

    for result in data.get("Results", []) or []:
        for vuln in result.get("Vulnerabilities") or []:
            sev = (vuln.get("Severity") or "").upper()
            if sev in ("HIGH", "CRITICAL"):
                total += 1

    return total


def count_grype_high_critical(report: Path) -> int:
    if not report.exists():
        return 0

    try:
        data = json.loads(report.read_text(encoding="utf-8"))
    except Exception:
        return 0

    total = 0

    for match in data.get("matches", []) or []:
        vuln = match.get("vulnerability", {})
        sev = (vuln.get("severity") or "").upper()
        if sev in ("HIGH", "CRITICAL"):
            total += 1

    return total


# --------------------------------------------------
# Main flow entry
# --------------------------------------------------


def run() -> None:
    repo_root = Path.cwd().resolve()
    dist_dir = repo_root / "dist" / "security"
    sbom_dir = repo_root / "autogen" / "sbom"

    dist_dir.mkdir(parents=True, exist_ok=True)

    print("Running SBOM-based security scan...\n")

    # --------------------------------------------------
    # 1. Tool validation
    # --------------------------------------------------

    if not which("trivy"):
        raise RuntimeError("Missing required tool: trivy")

    if not which("grype"):
        raise RuntimeError("Missing required tool: grype")

    # --------------------------------------------------
    # 1. Setup SLT environment
    # --------------------------------------------------
    env = setup_slt_environment(repo_root)

    # Make tools globally visible for this process
    os.environ.update(env)

    dist_dir.mkdir(parents=True, exist_ok=True)

    subprocess.run(
        ["git", "config", "--global", "--add", "safe.directory", str(repo_root)],
        check=True,
    )

    # --------------------------------------------------
    # 2. Generate project via SLC
    # --------------------------------------------------
    slcp_path = detect_single_slcp(repo_root)

    subprocess.run(
        [
            "slc",
            "generate",
            "--slconf",
            str(repo_root / ".cicd/user.slconf"),
            "-p",
            str(slcp_path),
            "-d",
            str(repo_root),
        ],
        cwd=repo_root,
        check=True,
    )

    # --------------------------------------------------
    # 2. Detect SBOM
    # --------------------------------------------------

    if not sbom_dir.exists():
        raise RuntimeError(f"SBOM directory not found: {sbom_dir}")

    sbom_file = detect_sbom(sbom_dir)
    print(f"Using SBOM: {sbom_file}\n")

    # --------------------------------------------------
    # 3. Trivy SBOM scan
    # --------------------------------------------------

    trivy_report = dist_dir / "trivy_sbom.json"

    print("Running Trivy (SBOM mode)...")

    rc, output = run_cmd(
        [
            "trivy",
            "sbom",
            "--format",
            "json",
            "--output",
            str(trivy_report),
            "--quiet",
            "--exit-code",
            "0",  # never fail pipeline
            str(sbom_file),
        ],
        cwd=repo_root,
    )

    print(output)

    if rc != 0:
        print("Trivy execution error (non-fatal).")

    # --------------------------------------------------
    # 4. Grype SBOM scan
    # --------------------------------------------------

    grype_report = dist_dir / "grype_sbom.json"

    print("Running Grype (SBOM mode)...")

    rc, output = run_cmd(
        [
            "grype",
            f"sbom:{sbom_file}",
            "-o",
            "json",
        ],
        cwd=repo_root,
    )

    # Write JSON manually (grype prints to stdout)
    grype_report.write_text(output, encoding="utf-8")

    if rc != 0:
        print("Grype execution error (non-fatal).")

    # --------------------------------------------------
    # 5. HIGH / CRITICAL summary (visibility only)
    # --------------------------------------------------

    trivy_count = count_trivy_high_critical(trivy_report)
    grype_count = count_grype_high_critical(grype_report)

    print("\n===================================================")
    print("SBOM Vulnerability Summary (HIGH / CRITICAL)")
    print("---------------------------------------------------")
    print(f"Trivy HIGH/CRITICAL : {trivy_count}")
    print(f"Grype HIGH/CRITICAL : {grype_count}")
    print("---------------------------------------------------")

    if trivy_count > 0 or grype_count > 0:
        print("::warning::HIGH/CRITICAL vulnerabilities detected (visibility only)")
    else:
        print("No HIGH/CRITICAL vulnerabilities detected.")

    print("===================================================\n")

    # --------------------------------------------------
    # 6. Structured summary artifact
    # --------------------------------------------------

    summary = {
        "sbom_file": str(sbom_file),
        "trivy_report": str(trivy_report),
        "grype_report": str(grype_report),
        "trivy_high_critical": trivy_count,
        "grype_high_critical": grype_count,
    }

    summary_path = dist_dir / "security_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")

    print("Security scan completed (non-blocking).")
