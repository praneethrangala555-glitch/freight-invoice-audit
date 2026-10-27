"""
Git helper using dulwich to manage local repository when git.exe is not in PATH.
"""
import os
import sys
from pathlib import Path
import dulwich.porcelain as git
from dulwich.repo import Repo

REPO_ROOT = Path(__file__).resolve().parent.parent

def init_repo():
    git_dir = REPO_ROOT / ".git"
    if not git_dir.exists():
        repo = git.init(str(REPO_ROOT))
        print(f"Initialized empty Git repository at {REPO_ROOT}")
        return repo
    else:
        return Repo(str(REPO_ROOT))

def commit_all(message: str, author: str = "Freight Audit Engine <freight-audit@local>"):
    repo = init_repo()
    git.add(str(REPO_ROOT))
    commit_id = git.commit(str(REPO_ROOT), message=message.encode('utf-8'), author=author.encode('utf-8'))
    print(f"Committed {commit_id.decode('ascii') if isinstance(commit_id, bytes) else commit_id}: {message}")
    return commit_id

def status():
    repo = init_repo()
    st = git.status(str(REPO_ROOT))
    print("Status:", st)
    return st

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "init":
        init_repo()
    elif len(sys.argv) > 2 and sys.argv[1] == "commit":
        commit_all(sys.argv[2])
    else:
        init_repo()
