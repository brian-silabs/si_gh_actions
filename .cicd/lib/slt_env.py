from __future__ import annotations

import os
import platform
import shutil
import subprocess
import urllib.request
import zipfile
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence


# --------------------------------------------------
# Generic helpers
# --------------------------------------------------


def run_cmd(
    cmd: Sequence[str],
    *,
    cwd: Optional[Path] = None,
    env: Optional[Dict[str, str]] = None,
) -> None:
    subprocess.run(
        list(map(str, cmd)),
        cwd=str(cwd) if cwd else None,
        env=env,
        check=True,
    )


def which(exe: str, env: Dict[str, str]) -> Optional[str]:
    return shutil.which(exe, path=env.get("PATH"))


def verify_required_tools(env: Dict[str, str], tools: Sequence[str]) -> None:
    missing = [t for t in tools if not which(t, env)]
    if missing:
        raise RuntimeError(f"Missing required tools in PATH: {', '.join(missing)}")


# --------------------------------------------------
# SLT download
# --------------------------------------------------


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
        return

    with urllib.request.urlopen(url) as r, open(dest, "wb") as f:
        shutil.copyfileobj(r, f)


def extract_slt(zip_path: Path, extract_to: Path) -> Path:
    extract_to.mkdir(parents=True, exist_ok=True)
    marker = extract_to / ".extracted"

    if marker.exists():
        slt_bins = list(extract_to.glob("**/slt"))
        if slt_bins:
            slt_bins[0].chmod(slt_bins[0].stat().st_mode | 0o111)
            return slt_bins[0]

    with zipfile.ZipFile(zip_path, "r") as z:
        z.extractall(extract_to)

    slt_bins = list(extract_to.glob("**/slt"))
    if not slt_bins:
        raise RuntimeError("SLT binary not found after extraction")

    slt_bin = slt_bins[0]
    slt_bin.chmod(slt_bin.stat().st_mode | 0o111)
    marker.write_text("ok\n")

    return slt_bin


# --------------------------------------------------
# Tool path activation
# --------------------------------------------------


def parse_tool_paths(slconf: Path) -> List[Path]:
    if not slconf.exists():
        raise RuntimeError(f"Missing slconf: {slconf}")

    tool_dirs: List[Path] = []
    inside_core = False
    inside_tool_path = False

    for raw in slconf.read_text().splitlines():
        line = raw.strip()

        if line == "[core]":
            inside_core = True
            continue

        if inside_core and line.startswith("tool-path"):
            inside_tool_path = True
            continue

        if inside_tool_path:
            if line.startswith("]"):
                break
            if line.startswith('"'):
                tool_dirs.append(Path(line.split('"')[1]))

    if not tool_dirs:
        raise RuntimeError(f"No tool-path entries found in {slconf}")

    return tool_dirs


def normalize_tool_paths(tool_dirs: Iterable[Path]) -> List[str]:
    normalized: List[str] = []

    for p in tool_dirs:
        if (p / "slc").exists():
            normalized.append(str(p))
            continue

        if (p / "bin").exists():
            normalized.append(str(p / "bin"))
            continue

        if (p / "ninja").exists():
            normalized.append(str(p))
            continue

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


# --------------------------------------------------
# Public API
# --------------------------------------------------


def setup_slt_environment(repo_root: Path) -> Dict[str, str]:
    slt_version = "1.1.0"
    slt_base_url = "https://www.silabs.com/documents/public/software"

    cicd_dir = repo_root / ".cicd"
    cache_root = repo_root / ".cache" / "slt_cli"
    recipe_path = cicd_dir / "pkg.slt"
    autogen_slconf = cicd_dir / "autogen" / "pkg.slconf"

    cache_root.mkdir(parents=True, exist_ok=True)
    (cicd_dir / "autogen").mkdir(parents=True, exist_ok=True)

    zip_name = slt_zip_name(slt_version)
    zip_path = cache_root / zip_name
    extract_root = cache_root / slt_version

    url = f"{slt_base_url.rstrip('/')}/{zip_name}"
    download_if_needed(url, zip_path)
    slt_bin = extract_slt(zip_path, extract_root)

    env0 = dict(os.environ)

    run_cmd(
        [str(slt_bin), "install", "-f", str(recipe_path)],
        cwd=cicd_dir,
        env=env0,
    )

    tool_dirs = parse_tool_paths(autogen_slconf)
    normalized = normalize_tool_paths(tool_dirs)
    env = prepend_path(env0, normalized)

    verify_required_tools(env, ["cmake", "ninja", "slc"])

    return env
