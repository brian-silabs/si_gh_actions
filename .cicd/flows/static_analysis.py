# .cicd/flows/static_analysis.py

import subprocess
from pathlib import Path
import fnmatch
import os


REPO = Path("/workspace")
DIST = REPO / "dist" / "static_analysis"
BUILD = REPO / "build"


EXCLUDES = [
    "**/autogen/**",
    "**/generated/**",
    "**/slc_generated/**",
    "**/build/**",
]


def run_cmd(cmd, cwd=None):
    result = subprocess.run(cmd, cwd=cwd, text=True)
    if result.returncode != 0:
        raise SystemExit(result.returncode)


def git_tracked_sources():
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=REPO,
        capture_output=True,
        text=True,
        check=True,
    )

    files = []
    for line in result.stdout.splitlines():
        if any(fnmatch.fnmatch(line, pat) for pat in EXCLUDES):
            continue
        if line.endswith((".c", ".cpp", ".cc", ".h", ".hpp")):
            files.append(str(REPO / line))

    return files


def run():
    DIST.mkdir(parents=True, exist_ok=True)

    compile_db = BUILD / "compile_commands.json"
    if not compile_db.exists():
        raise RuntimeError("Missing compile_commands.json. Enable in build flow.")

    sources = git_tracked_sources()

    # -------- clang-tidy --------
    tidy_out = DIST / "clang-tidy.txt"

    cmd = [
        "clang-tidy",
        f"-p={BUILD}",
        "-checks=bugprone-*,clang-analyzer-*",
        "-warnings-as-errors=*",
    ] + sources

    with tidy_out.open("w") as f:
        result = subprocess.run(cmd, stdout=f, stderr=subprocess.STDOUT)

    if result.returncode != 0:
        raise SystemExit(result.returncode)

    # -------- cppcheck (SARIF) --------
    sarif = DIST / "cppcheck.sarif"

    cmd = [
        "cppcheck",
        "--quiet",
        "--error-exitcode=1",
        "--enable=warning,performance,portability",
        "--output-format=sarif",
        f"--output-file={sarif}",
        str(REPO),
    ]

    result = subprocess.run(cmd)

    if result.returncode != 0:
        raise SystemExit(result.returncode)
