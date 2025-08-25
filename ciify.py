from git import Repo, GitCommandError
import os, shutil, configparser

# ---------- helpers (add once) ----------

def protect_gitmodules():
    """
    Make sure .gitmodules can't be ignored by an over-broad .gitignore.
    """
    if not os.path.exists(".gitignore"):
        return
    with open(".gitignore", "r+", encoding="utf-8") as f:
        content = f.read()
        if "!.gitmodules" not in content.splitlines():
            f.write(("\n" if not content.endswith("\n") else "") + "!.gitmodules\n")
            print("Added '!.gitmodules' to .gitignore for safety.")

def branch_exists(repo, name: str) -> bool:
    return any(h.name == name for h in repo.heads)

def ensure_checked_out(repo, name: str):
    if branch_exists(repo, name):
        repo.git.checkout(name)
    else:
        # create from current HEAD
        b = repo.create_head(name)
        b.checkout()

def has_commit_with_subject(repo, rev: str, subject: str) -> bool:
    """Return True if any commit reachable from `rev` has `subject` as its one-line message."""
    try:
        for c in repo.iter_commits(rev):
            if c.message.splitlines()[0].strip() == subject:
                return True
        return False
    except Exception:
        # rev might not exist yet
        return False

def preclean_submodule_git(path="si_gh_actions/.git"):
    """
    Ensure no nested .git directory exists inside the submodule working tree.
    A proper submodule uses a *file* at si_gh_actions/.git that points to ../.git/modules/si_gh_actions
    """
    if os.path.isdir(path):
        shutil.rmtree(path)
        print("Removed nested si_gh_actions/.git directory (prevent corruption).")

def stage_submodule_and_ci(repo):
    """
    Stage only what we intend:
    - .gitmodules
    - the submodule gitlink (si_gh_actions)
    - copied CI files (.github/**, CHANGELOG.md, VERSION.md, target_info.yaml)
    """
    # keep .gitmodules in the index
    if os.path.exists(".gitmodules"):
        repo.index.add([".gitmodules"])

    # stage submodule path as gitlink (mode 160000)
    repo.git.add("si_gh_actions")

    # Force-stage .gitignore (bypass ignore rules)
    if os.path.exists(".gitignore"):
        repo.git.add("-f", ".gitignore")

    # stage copied CI files
    to_add = [p for p in ("CHANGELOG.md", "VERSION.md", "target_info.yaml") if os.path.exists(p)]
    if to_add:
        repo.index.add(to_add)
    if os.path.isdir(".github"):
        repo.git.add(".github")

def assert_gitlink(repo, path="si_gh_actions"):
    """
    Verify the path is staged as a submodule gitlink (mode 160000).
    """
    try:
        entry = repo.git.ls_files("--stage", path)  # "<mode> <sha> <stage>\tpath"
        mode = entry.split()[0] if entry else ""
        if not mode.startswith("160000"):
            raise RuntimeError(f"{path} is not staged as a gitlink (mode=160000). Got '{mode or 'none'}'.")
    except GitCommandError as e:
        raise RuntimeError(f"Cannot verify gitlink for {path}: {e}")

def commit_if_needed(repo, message):
    if repo.is_dirty(index=True, working_tree=True, untracked_files=True):
        repo.index.commit(message)
        print(f"Commit made: {message}")
    else:
        print("No changes to commit.")

def has_staged_changes(repo):
    try:
        repo.git.diff("--cached", "--quiet")
        return False  # exit 0 → no changes
    except GitCommandError:
        return True   # nonzero → staged changes

def commit_if_staged(repo, message):
    if has_staged_changes(repo):
        repo.index.commit(message)
        print(f"Commit made: {message}")
    else:
        print("No staged changes; skipping commit.")

def copy_files_to_root():
    """
    Function to copy files and directories from 'si_gh_actions/' to the root of the current working directory.
    """
    files_to_copy = [
        "si_gh_actions/CHANGELOG.md",
        "si_gh_actions/VERSION.md",
        "si_gh_actions/.gitignore",
        "si_gh_actions/target_info.yaml",
    ]
    dir_to_copy = "si_gh_actions/.github/"

    # Copy individual files
    for file_path in files_to_copy:
        try:
            if os.path.exists(file_path):
                shutil.copy(file_path, ".")
                print(f"Copied {file_path} to root directory.")
            else:
                print(f"File not found: {file_path}")
        except Exception as e:
            print(f"Error copying {file_path}: {e}")

    # Copy directory recursively
    try:
        if os.path.exists(dir_to_copy):
            shutil.copytree(
                dir_to_copy, os.path.join(".", ".github"), dirs_exist_ok=True
            )
            print(f"Copied {dir_to_copy} to root directory.")
        else:
            print(f"Directory not found: {dir_to_copy}")
    except Exception as e:
        print(f"Error copying directory {dir_to_copy}: {e}")

# ---------- DROP-IN main() ----------

def main():
    repo = Repo(".")

    # --- get onto main (create/rename if needed) ---
    if any(h.name == "main" for h in repo.heads):
        repo.git.checkout("main")
        print("Checked out existing 'main'.")
    else:
        print("No 'main' branch found. Renaming current to 'main'.")
        repo.git.branch("-M", "main")

    # --- submodule hygiene BEFORE staging (your existing helpers) ---
    protect_gitmodules()
    preclean_submodule_git("si_gh_actions/.git")
    try:
        repo.git.submodule("sync", "--recursive")
        repo.git.submodule("update", "--init", "--recursive")
    except GitCommandError as e:
        print(f"Submodule sync/update warning: {e}")

    # --- Only create the Boardful commit if it doesn't already exist on main ---
    if not has_commit_with_subject(repo, "main", "Initial Boardful commit"):
        stage_submodule_and_ci(repo)      # stages .gitmodules, gitlink, any pre-existing files
        assert_gitlink(repo, "si_gh_actions")
        commit_if_staged(repo, "Initial Boardful commit")
    else:
        print("Skip: 'Initial Boardful commit' already exists on main.")

    # --- Ensure dev exists and is checked out ---
    ensure_checked_out(repo, "dev")

    # --- Copy CI files from submodule and commit them (but only once) ---
    # If you want CI files included in the same Boardful commit, move copy_files_to_root()
    # before stage_submodule_and_ci() above. Otherwise keep this as a separate (idempotent) step.
    if not has_commit_with_subject(repo, "dev", "CI: add workflows and metadata"):
        copy_files_to_root()
        stage_submodule_and_ci(repo)
        commit_if_staged(repo, "CI: add workflows and metadata")
    else:
        print("Skip: 'CI: add workflows and metadata' already exists on dev.")

    # --- Only create the Boardless commit if it doesn't already exist on dev ---
    if not has_commit_with_subject(repo, "dev", "Initial Boardless commit"):
        # Old removal of SLCP contents would go here if needed
        stage_submodule_and_ci(repo)      # harmless if no changes; keeps .gitmodules/gitlink staged
        assert_gitlink(repo, "si_gh_actions")
        commit_if_staged(repo, "Initial Boardless commit")
    else:
        print("Skip: 'Initial Boardless commit' already exists on dev.")

if __name__ == "__main__":
    main()
