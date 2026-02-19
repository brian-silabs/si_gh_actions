#!/usr/bin/env python3
"""
CI build driver for Silicon Labs SLC projects.

Goals:
- Deterministic directory layout inside container (/workspace)
- Cache SLT downloads and SLT_HOME installs to avoid redundant work
- Activate toolchain from autogen/pkg.slconf
- Generate + build via slc + cmake presets
- Copy final artifacts into /workspace/dist (missing step in current script)

Default layout:
- repo_root: /workspace
- cache_root: /workspace/.cache
- slt cache: /workspace/.cache/slt/<version>/
- slt_home:  /workspace/.cache/slt/<version>/slt_home
- build_dir: /workspace/cmake_gcc
- dist_dir:  /workspace/dist
"""

from __future__ import annotations

import argparse
import os
import platform
import re
import shutil
import subprocess
import sys
import tarfile
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple
from lib.slt_env import setup_slt_environment
from lib.project import detect_single_slcp, default_project_name_from_slcp

# --------------------------
# Logging / subprocess
# --------------------------


def log(msg: str) -> None:
    print(msg, flush=True)


class CmdError(RuntimeError):
    pass


def run_cmd(
    cmd: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
) -> None:
    cmd_str = " ".join(map(str, cmd))
    log(f"$ {cmd_str}")
    try:
        subprocess.run(
            list(map(str, cmd)),
            cwd=str(cwd) if cwd else None,
            env=env,
            check=True,
        )
    except subprocess.CalledProcessError as e:
        raise CmdError(f"Command failed (exit {e.returncode}): {cmd_str}") from e


def which(exe: str, env: Dict[str, str]) -> Optional[str]:
    # Use shutil.which with provided PATH
    return shutil.which(exe, path=env.get("PATH"))


def require_unix() -> None:
    if platform.system() not in ("Linux", "Darwin"):
        raise RuntimeError("This CI script supports Unix-based systems only.")


# --------------------------
# SLT download/extract
# --------------------------


def slt_zip_name(version: str) -> str:
    sysname = platform.system()
    arch = platform.machine().lower()

    if sysname == "Linux":
        return f"slt-cli-{version}-linux-x64.zip"

    if sysname == "Darwin":
        if arch.startswith("arm"):
            return f"slt-cli-{version}-mac-arm64.zip"
        return f"slt-cli-{version}-mac-x64.zip"

    raise RuntimeError(f"Unsupported OS: {sysname}")


def download_if_needed(url: str, dest: Path) -> None:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and dest.stat().st_size > 0:
        log(f"Using cached download: {dest}")
        return

    log(f"Downloading: {url}")
    with urllib.request.urlopen(url) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def extract_slt(zip_path: Path, extract_to: Path) -> Path:
    extract_to.mkdir(parents=True, exist_ok=True)
    marker = extract_to / ".extracted"
    if marker.exists():
        slt = list(extract_to.glob("**/slt"))
        if slt:
            slt[0].chmod(slt[0].stat().st_mode | 0o111)
            return slt[0]

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_to)

    slt_bins = list(extract_to.glob("**/slt"))
    if not slt_bins:
        raise RuntimeError("SLT binary not found after extraction")

    slt_bin = slt_bins[0]
    slt_bin.chmod(slt_bin.stat().st_mode | 0o111)
    marker.write_text("ok\n")
    return slt_bin


# --------------------------
# Repo / project discovery
# --------------------------


def detect_single_slcp(repo_root: Path) -> Path:
    slcp_files = list(repo_root.glob("**/*.slcp"))
    if not slcp_files:
        raise RuntimeError("No .slcp file found in repository.")
    if len(slcp_files) > 1:
        raise RuntimeError(
            "Multiple .slcp files found; make selection explicit.\n"
            + "\n".join(f"- {p}" for p in slcp_files)
        )
    return slcp_files[0]


def default_project_name_from_slcp(slcp_path: Path) -> str:
    # Common convention: <project_name>.slcp
    return slcp_path.stem


# --------------------------
# SLT tool-path activation from autogen/pkg.slconf
# --------------------------

_TOOL_PATH_SECTION_RE = re.compile(r"^\[core\]\s*$")
_TOOL_PATH_KEY_RE = re.compile(r"^tool-path\s*$")


def parse_tool_paths(slconf: Path) -> List[Path]:
    """
    Parse autogen/pkg.slconf for [core] tool-path entries, returning raw paths.
    Format expected (as in your current script):
      [core]
      tool-path = [
        "..."
        "..."
      ]
    """
    if not slconf.exists():
        raise RuntimeError(f"Missing slconf: {slconf}")

    tool_dirs: List[Path] = []
    inside_core = False
    inside_tool_path = False

    for raw in slconf.read_text().splitlines():
        line = raw.strip()

        if _TOOL_PATH_SECTION_RE.match(line):
            inside_core = True
            inside_tool_path = False
            continue

        if inside_core and _TOOL_PATH_KEY_RE.match(line.split("=")[0].strip()):
            inside_tool_path = True
            continue

        if inside_tool_path:
            if line.startswith("]"):
                break
            if line.startswith('"') and '"' in line[1:]:
                # take content between first pair of quotes
                tool_dirs.append(Path(line.split('"')[1]))

    if not tool_dirs:
        raise RuntimeError(f"No tool-path entries found in {slconf}")

    return tool_dirs


def normalize_tool_paths(tool_dirs: Iterable[Path]) -> List[str]:
    """
    Normalize tool directories into PATH entries.
    Mirrors your existing heuristics, but applies them consistently.
    """
    normalized: List[str] = []
    for p in tool_dirs:
        # slc_cli: slc binary directly in dir
        if (p / "slc").exists():
            normalized.append(str(p))
            continue

        # cmake, python often have bin/
        if (p / "bin").exists():
            normalized.append(str(p / "bin"))
            continue

        # ninja: binary directly in dir
        if (p / "ninja").exists():
            normalized.append(str(p))
            continue

        # java: jre/bin
        jre_bin = p / "jre" / "bin"
        if jre_bin.exists():
            normalized.append(str(jre_bin))
            continue

        normalized.append(str(p))
    return normalized


def prepend_path(env: Dict[str, str], entries: List[str]) -> Dict[str, str]:
    new_env = dict(env)
    old = new_env.get("PATH", "")
    new_env["PATH"] = ":".join(entries) + (":" + old if old else "")
    return new_env


def verify_required_tools(env: Dict[str, str], tools: Sequence[str]) -> None:
    missing = [t for t in tools if not which(t, env)]
    if missing:
        raise RuntimeError(f"Missing required tools in PATH: {', '.join(missing)}")


# --------------------------
# Artifact copy
# --------------------------


def copy_artifacts(build_dir: Path, dist_dir: Path, project_name: str) -> List[Path]:
    """
    Copy build artifacts from:

        <build_dir>/build/base/<project_name>.*

    into:

        <dist_dir>/<project_name>/

    Returns list of copied artifact paths.
    """

    src_dir = build_dir / "build" / "base"
    if not src_dir.exists():
        raise RuntimeError(f"Expected build output directory not found: {src_dir}")

    matches = sorted(src_dir.glob(f"{project_name}.*"))

    if not matches:
        available = ", ".join(p.name for p in sorted(src_dir.iterdir())[:50])
        raise RuntimeError(
            f"No artifacts matching {project_name}.* found in {src_dir}. "
            f"Available files: {available}"
        )

    target_dir = dist_dir / project_name
    target_dir.mkdir(parents=True, exist_ok=True)

    copied: List[Path] = []

    for src in matches:
        dst = target_dir / src.name
        shutil.copy2(src, dst)
        copied.append(dst)

    return copied


# --------------------------
# Artifact packaging
# --------------------------


def package_artifacts(
    build_dir: Path,
    dist_dir: Path,
    project_name: str,
    package_name: str,
) -> Path:
    """
    Collect artifacts from build output and package them.

    Steps:
      1. Copy artifacts from build/base
      2. Create tar.gz archive containing only those artifacts
    """

    copied_files = copy_artifacts(build_dir, dist_dir, project_name)

    package_path = dist_dir / package_name

    with tarfile.open(package_path, "w:gz") as tar:
        for file in copied_files:
            # store under project directory inside archive
            arcname = f"{project_name}/{file.name}"
            tar.add(file, arcname=arcname)

    return package_path


# --------------------------
# Config
# --------------------------


def load_yaml(path: Path) -> dict:
    import yaml  # dependency reruns python3-pip installable; keep minimal usage

    return yaml.safe_load(path.read_text()) or {}


# --------------------------
# run flow
# --------------------------


def run() -> None:
    require_unix()

    repo_root = Path.cwd().resolve()
    cicd_dir = repo_root / ".cicd"
    dist_dir = repo_root / "dist"
    build_dir = repo_root / "cmake_gcc"

    config_path = cicd_dir / "ci_config.yml"
    project_slconf = cicd_dir / "user.slconf"

    if not config_path.exists():
        raise RuntimeError(f"Config not found: {config_path}")

    dist_dir.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------
    # 1. Setup SLT environment (shared library)
    # --------------------------------------------------
    env = setup_slt_environment(repo_root)

    # Optional but recommended for consistency
    os.environ.update(env)

    log(f"Repository root : {repo_root}")
    log(f"Build directory : {build_dir}")
    log(f"Dist directory  : {dist_dir}")

    config = load_yaml(config_path)

    # --------------------------------------------------
    # 2. Git safe.directory + submodules
    # --------------------------------------------------
    run_cmd(
        ["git", "config", "--global", "--add", "safe.directory", str(repo_root)],
        env=env,
    )

    if config.get("submodules", False):
        run_cmd(
            ["git", "submodule", "update", "--init", "--recursive"],
            cwd=repo_root,
            env=env,
        )

    # --------------------------------------------------
    # 3. Detect project
    # --------------------------------------------------
    slcp_path = detect_single_slcp(repo_root)
    project_name = default_project_name_from_slcp(slcp_path)

    log(f"Using SLCP project : {slcp_path}")
    log(f"Project name       : {project_name}")

    # --------------------------------------------------
    # 4. Generate + Build
    # --------------------------------------------------
    run_cmd(
        [
            "slc",
            "generate",
            "--slconf",
            str(project_slconf),
            "-p",
            str(slcp_path),
            "-d",
            str(repo_root),
        ],
        cwd=repo_root,
        env=env,
    )

    if not build_dir.exists():
        raise RuntimeError("cmake_gcc directory not produced by slc generate")

    run_cmd(["cmake", "--preset", "project"], cwd=build_dir, env=env)
    run_cmd(["cmake", "--build", "--preset", "default_config"], cwd=build_dir, env=env)

    # --------------------------------------------------
    # 5. Package artifacts
    # --------------------------------------------------
    package_name = config.get("package", "artifacts.tar.gz")

    package_path = package_artifacts(
        build_dir=build_dir,
        dist_dir=dist_dir,
        project_name=project_name,
        package_name=package_name,
    )

    log(f"Artifacts packaged: {package_path}")
