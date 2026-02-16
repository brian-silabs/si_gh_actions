#!/usr/bin/env python3

"""
ciify.py

Deploy si_gh_actions CI infrastructure into a target repository.

Actions:
  - Copy .cicd directory
  - Copy .github directory
  - Merge .gitignore entries safely

Usage:
    python3 ciify.py /path/to/target/repo
"""

import argparse
import shutil
from pathlib import Path
from typing import Set


# ------------------------------------------------------------
# Utilities
# ------------------------------------------------------------


def log(msg: str) -> None:
    print(msg, flush=True)


def require_dir(path: Path, description: str) -> None:
    if not path.exists() or not path.is_dir():
        raise RuntimeError(f"{description} not found: {path}")


# ------------------------------------------------------------
# Directory deployment
# ------------------------------------------------------------


def deploy_directory(source_repo: Path, target_repo: Path, name: str) -> None:
    src = source_repo / name
    dst = target_repo / name

    if not src.exists():
        log(f"{name} not present in CI repo — skipping")
        return

    if dst.exists():
        log(f"Updating existing {name}")
        shutil.rmtree(dst)

    log(f"Copying {name} → {dst}")
    shutil.copytree(src, dst)


# ------------------------------------------------------------
# .gitignore merge
# ------------------------------------------------------------


def read_gitignore(path: Path) -> Set[str]:
    if not path.exists():
        return set()

    lines = set()
    for line in path.read_text().splitlines():
        stripped = line.strip()
        if stripped:
            lines.add(stripped)
    return lines


def merge_gitignore(source_repo: Path, target_repo: Path) -> None:
    src_gitignore = source_repo / ".gitignore"
    dst_gitignore = target_repo / ".gitignore"

    if not src_gitignore.exists():
        log("No .gitignore in CI repo — skipping merge")
        return

    log("Merging .gitignore")

    src_lines = read_gitignore(src_gitignore)
    dst_lines = read_gitignore(dst_gitignore)

    merged = sorted(dst_lines | src_lines)

    dst_gitignore.write_text("\n".join(merged) + "\n")


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(description="Deploy si_gh_actions into a repo")
    parser.add_argument(
        "target_repo",
        help="Path to repository where CI should be installed",
    )

    args = parser.parse_args()

    source_repo = Path(__file__).resolve().parent
    target_repo = Path(args.target_repo).resolve()

    require_dir(target_repo, "Target repository")

    log(f"Source repo : {source_repo}")
    log(f"Target repo : {target_repo}")

    # Deploy infrastructure directories
    deploy_directory(source_repo, target_repo, ".cicd")
    deploy_directory(source_repo, target_repo, ".github")

    # Merge ignore rules
    merge_gitignore(source_repo, target_repo)

    log("CI deployment completed successfully.")


if __name__ == "__main__":
    main()
