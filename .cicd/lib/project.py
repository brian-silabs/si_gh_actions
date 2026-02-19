from pathlib import Path


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
    return slcp_path.stem
