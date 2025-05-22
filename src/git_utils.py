from __future__ import annotations

import datetime as dt
import subprocess
from pathlib import Path

RUN_ID_FMT = "%Y%m%d-%H%M%S"


def new_branch(repo_root: Path) -> str:
    run_id = dt.datetime.utcnow().strftime(RUN_ID_FMT)
    branch = f"feature/run-{run_id}"
    subprocess.check_call(["git", "-C", str(repo_root), "checkout", "-b", branch])
    return branch


def commit_all(repo_root: Path, message: str) -> str:
    subprocess.check_call(["git", "-C", str(repo_root), "add", "."])
    subprocess.check_call(["git", "-C", str(repo_root), "commit", "-m", message])
    sha = subprocess.check_output(["git", "-C", str(repo_root), "rev-parse", "HEAD"], text=True).strip()
    return sha
