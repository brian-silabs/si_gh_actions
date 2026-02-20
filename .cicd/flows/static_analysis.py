# .cicd/flows/static_analysis.py

import subprocess
from pathlib import Path
import os
import json
from lib.slt_env import setup_slt_environment
from lib.project import detect_single_slcp


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


def run() -> None:
    repo_root = Path.cwd().resolve()

    cmake_env_dir = repo_root / "cmake_gcc"
    cmake_build_dir = cmake_env_dir / "build"

    dist_dir = repo_root / "dist" / "static_analysis"

    dist_dir.mkdir(parents=True, exist_ok=True)

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

    if not cmake_env_dir.exists():
        raise RuntimeError("cmake_gcc directory not produced by slc generate")

    # --------------------------------------------------
    # 3. Configure (NO BUILD)
    # --------------------------------------------------
    subprocess.run(
        [
            "cmake",
            "--preset",
            "project",
            "-DCMAKE_EXPORT_COMPILE_COMMANDS=ON",
        ],
        cwd=cmake_env_dir,
        check=True,
    )

    compile_db = cmake_build_dir / "compile_commands.json"
    if not compile_db.exists():
        raise RuntimeError("compile_commands.json not generated.")

    # --------------------------------------------------
    # 4. Collect tracked sources (avoid generated code)
    # --------------------------------------------------
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=True,
    )

    sources = []

    for f in result.stdout.splitlines():
        if not f.endswith((".c", ".cc", ".cpp", ".h", ".hpp")):
            continue

        # Exclude generated and vendor code
        if (
            "autogen/" in f
            or "generated/" in f
            or "simplicity_sdk_" in f
            or "/third_party/" in f
            or "/util/third_party/" in f
            or "config/" in f
        ):
            continue

        sources.append(str(repo_root / f))

    # --------------------------------------------------
    # 5. clang-tidy
    # --------------------------------------------------
    print("\nRunning clang-tidy static analysis...\n")
    tidy_output = dist_dir / "clang-tidy.txt"

    with tidy_output.open("w") as f:
        tidy_result = subprocess.run(
            [
                "clang-tidy",
                f"-p={cmake_build_dir}",
                "-checks=bugprone-*,clang-analyzer-*",
                "-warnings-as-errors=bugprone-*,clang-analyzer-*",
            ]
            + sources,
            stdout=f,
            stderr=subprocess.STDOUT,
            check=False,  # important
        )

    if tidy_result.returncode != 0:
        print("\nStatic analysis (clang-tidy) reported issues.")
        print(f"See report: {tidy_output}\n")

        with tidy_output.open() as f:
            lines = f.readlines()

        warnings = sum(1 for l in lines if "warning:" in l)
        errors = sum(1 for l in lines if "error:" in l)

        print(f"\nclang-tidy summary: {errors} errors, {warnings} warnings")

    # --------------------------------------------------
    # 6. cppcheck (SARIF output)
    # --------------------------------------------------
    print("\nRunning cppcheck static analysis...\n")
    sarif_path = dist_dir / "cppcheck.sarif"

    cpp_result = subprocess.run(
        [
            "cppcheck",
            "--quiet",
            "--error-exitcode=1",
            "--enable=warning,performance,portability",
            "--output-format=sarif",
            f"--output-file={sarif_path}",
            str(repo_root),
        ],
        check=False,  # important
    )

    if cpp_result.returncode != 0:
        print("\nStatic analysis (cppcheck) reported issues.")
        print(f"See report: {sarif_path}\n")

        sarif_errors = 0
        sarif_warnings = 0
        sarif_notes = 0

        if sarif_path.exists():
            with sarif_path.open() as f:
                sarif = json.load(f)

            for run in sarif.get("runs", []):
                for result in run.get("results", []):
                    level = result.get("level", "warning")
                    if level == "error":
                        sarif_errors += 1
                    elif level == "warning":
                        sarif_warnings += 1
                    else:
                        sarif_notes += 1

        print(
            f"\ncppcheck summary: "
            f"{sarif_errors} errors, "
            f"{sarif_warnings} warnings, "
            f"{sarif_notes} notes"
        )

    exit_code = 0

    if tidy_result.returncode != 0:
        exit_code = 1

    if cpp_result.returncode != 0:
        exit_code = 1

    if exit_code != 0:
        print("\nStatic analysis failed.")
        print("Download the CI artifact 'static_analysis' for full reports.\n")
        raise SystemExit(exit_code)
