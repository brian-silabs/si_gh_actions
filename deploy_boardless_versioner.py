import subprocess
import os
import shutil
import yaml


def run_command(command):
    """
    Utility function to run shell commands and return the output.
    """
    result = subprocess.run(command, shell=True, capture_output=True, text=True)
    if result.returncode != 0:
        print(f"Error running command: {command}\n{result.stderr}")
        return None
    return result.stdout.strip()


def copy_files_to_root():
    """
    Function to copy files and directories from 'si_gh_actions/' to the root of the current working directory.
    """
    files_to_copy = [
        "si_gh_actions/CHANGELOG.md",
        "si_gh_actions/VERSION.md",
        "si_gh_actions/.gitignore",
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


def stage_and_commit(commit_message):
    """
    Function to stage untracked and modified files, then create a commit.
    """
    # List and stage untracked files
    untracked_files = run_command("git ls-files --others --exclude-standard")
    if untracked_files:
        print("Staging untracked files:")
        print(untracked_files)
        run_command(f"git add {untracked_files}")

    # List and stage modified files
    modified_files = run_command("git ls-files --modified")
    if modified_files:
        print("Staging modified files:")
        print(modified_files)
        run_command(f"git add {modified_files}")

    # Create a commit
    run_command(f'git commit -m "{commit_message}"')


def cleanup_yaml_and_files():
    """
    Function to clean up .slcp (YAML) and .pintool files.
    """
    # Step 6a: Look for a .slcp file
    slcp_file = None
    for root, _, files in os.walk("."):
        for file in files:
            if file.endswith(".slcp"):
                slcp_file = os.path.join(root, file)
                break
        if slcp_file:
            break

    if slcp_file:
        print(f"Found .slcp file: {slcp_file}")
        with open(slcp_file, "r") as file:
            yaml_data = yaml.safe_load(file)

        # Step 6b and 6c: Remove entries that start with "brd" or "efr32"
        yaml_data = {
            k: v
            for k, v in yaml_data.items()
            if not (k.startswith("brd") or k.startswith("efr32"))
        }

        with open(slcp_file, "w") as file:
            yaml.safe_dump(yaml_data, file)
        print("Updated .slcp file.")

    # Step 6d: Look for a .pintool file and delete it
    pintool_file = None
    for root, _, files in os.walk("."):
        for file in files:
            if file.endswith(".pintool"):
                pintool_file = os.path.join(root, file)
                break
        if pintool_file:
            break

    if pintool_file:
        print(f"Found .pintool file: {pintool_file}. Deleting it.")
        os.remove(pintool_file)
    else:
        print("No .pintool file found.")


def main():
    # Step 1: Print the current branch name
    current_branch = run_command("git branch --show-current")
    print(f"Current branch: {current_branch}")

    # Step 2, 3, 4: Stage files and commit with "Initial Boardful commit"
    stage_and_commit("Initial Boardful commit")
    
    # Extra Step: Copy files and directories to root
    copy_files_to_root()

    # # Step 5: Create a new local branch named "dev" and check out to it
    # run_command("git checkout -b dev")
    # print("Created and switched to branch 'dev'.")

    # # Step 6: Cleanup YAML and .pintool files
    # cleanup_yaml_and_files()

    # # Step 7, 8, 9: Stage files and commit with "Initial Boardless commit"
    # stage_and_commit("Initial Boardless commit")


if __name__ == "__main__":
    main()
