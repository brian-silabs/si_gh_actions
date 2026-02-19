# .cicd/flows/static_analysis.py

import subprocess
from pathlib import Path
import fnmatch
import os
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

    if not cmake_build_dir.exists():
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

    sources = [
        str(repo_root / f)
        for f in result.stdout.splitlines()
        if f.endswith((".c", ".cc", ".cpp", ".h", ".hpp"))
        and "autogen" not in f
        and "generated" not in f
    ]

    # --------------------------------------------------
    # 5. clang-tidy
    # --------------------------------------------------
    tidy_output = dist_dir / "clang-tidy.txt"

    with tidy_output.open("w") as f:
        tidy_result = subprocess.run(
            [
                "clang-tidy",
                f"-p={cmake_build_dir}",
                "-checks=bugprone-*,clang-analyzer-*",
                "-warnings-as-errors=*",
            ]
            + sources,
            stdout=f,
            stderr=subprocess.STDOUT,
            check=True,
        )

    if tidy_result.returncode != 0:
        raise SystemExit(tidy_result.returncode)

    # --------------------------------------------------
    # 6. cppcheck (SARIF output)
    # --------------------------------------------------
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
        check=True,
    )

    if cpp_result.returncode != 0:
        raise SystemExit(cpp_result.returncode)
