"""
Push Repository to Remote GitHub
Utility to push the committed local git repository to a remote GitHub repository.
Usage:
    python scripts/push_to_github.py https://github.com/<username>/<repo>.git [branch]
"""
import sys
from pathlib import Path
import dulwich.porcelain as git
from dulwich.repo import Repo

REPO_ROOT = Path(__file__).resolve().parent.parent

def push_to_remote(remote_url: str, branch: str = "main"):
    print(f"Connecting to remote repository: {remote_url}")
    repo = Repo(str(REPO_ROOT))
    try:
        git.remote_add(str(REPO_ROOT), "origin", remote_url)
        print("Added remote 'origin'.")
    except Exception:
        pass  # Remote origin might already exist

    print(f"Pushing branch '{branch}' to origin...")
    try:
        git.push(str(REPO_ROOT), remote_location=remote_url, refspecs=[f"refs/heads/{branch}:refs/heads/{branch}"])
        print("Successfully pushed to remote GitHub repository!")
    except Exception as e:
        print(f"Push notice: {e}")
        print("\nIf authentication is required, you can push using a GitHub Personal Access Token (PAT):")
        print("  python scripts/push_to_github.py https://<PAT>@github.com/<username>/<repo>.git")

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python scripts/push_to_github.py <github_repo_url> [branch]")
        sys.exit(1)
    remote = sys.argv[1]
    ref_branch = sys.argv[2] if len(sys.argv) > 2 else "main"
    push_to_remote(remote, ref_branch)
