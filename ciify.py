#!/usr/bin/env python3

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


def detect_default_target(source_repo: Path) -> Path:
    """
    Default deployment target is parent directory.
    Expected layout:

        project/
            .ci/   ← this repo

    So target = parent(.ci)
    """
    parent = source_repo.parent

    if not (parent / ".git").exists():
        raise RuntimeError(
            "Parent directory does not look like a git repository.\n"
            "Run ciify.py from a submodule inside a project repo "
            "or specify target explicitly."
        )

    return parent


# ------------------------------------------------------------
# Directory deployment
# ------------------------------------------------------------


def deploy_directory(source_repo: Path, target_repo: Path, name: str) -> None:
    src = source_repo / name
    dst = target_repo / name

    if not src.exists():
        log(f"{name} not present — skipping")
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

    return {line.strip() for line in path.read_text().splitlines() if line.strip()}


def merge_gitignore(source_repo: Path, target_repo: Path) -> None:
    src_gitignore = source_repo / ".gitignore"
    dst_gitignore = target_repo / ".gitignore"

    if not src_gitignore.exists():
        log("No .gitignore in CI repo — skipping merge")
        return

    log("Merging .gitignore")

    merged = sorted(read_gitignore(src_gitignore) | read_gitignore(dst_gitignore))

    dst_gitignore.write_text("\n".join(merged) + "\n")


# ------------------------------------------------------------
# Main
# ------------------------------------------------------------


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Deploy si_gh_actions into project repo"
    )
    parser.add_argument(
        "target_repo",
        nargs="?",
        help="Optional target repo (defaults to parent directory)",
    )

    args = parser.parse_args()

    source_repo = Path(__file__).resolve().parent

    if args.target_repo:
        target_repo = Path(args.target_repo).resolve()
    else:
        target_repo = detect_default_target(source_repo)

    require_dir(target_repo, "Target repository")

    log(f"Source repo : {source_repo}")
    log(f"Target repo : {target_repo}")

    deploy_directory(source_repo, target_repo, ".cicd")
    deploy_directory(source_repo, target_repo, ".github")

    merge_gitignore(source_repo, target_repo)

    log("CI deployment completed successfully.")


if __name__ == "__main__":
    main()
