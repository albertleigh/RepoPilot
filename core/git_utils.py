"""
Functional-programming-style Git utilities.

All functions are stateless and operate on repository paths.
Results are returned as immutable dataclasses – no exceptions are raised.
"""
from __future__ import annotations

import subprocess
from dataclasses import dataclass
from pathlib import Path


# ------------------------------------------------------------------
# Data types
# ------------------------------------------------------------------

@dataclass(frozen=True)
class GitResult:
    """Immutable result of a git command."""
    success: bool
    command: str
    stdout: str
    stderr: str

    @property
    def output(self) -> str:
        return self.stdout if self.success else self.stderr


@dataclass(frozen=True)
class BranchInfo:
    """Immutable local branch descriptor."""
    name: str
    is_active: bool


@dataclass(frozen=True)
class CommitInfo:
    """Immutable commit descriptor."""
    hash: str
    short_hash: str
    subject: str
    author: str
    date: str  # relative date string


# ------------------------------------------------------------------
# Low-level runner
# ------------------------------------------------------------------

def run_git(repo_path: str | Path, *args: str) -> GitResult:
    """Run a git command in *repo_path* and return a ``GitResult``."""
    cmd = ["git", "-C", str(repo_path), *args]
    cmd_display = " ".join(cmd)
    try:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=30,
        )
        return GitResult(
            success=proc.returncode == 0,
            command=cmd_display,
            stdout=proc.stdout.strip(),
            stderr=proc.stderr.strip(),
        )
    except subprocess.TimeoutExpired:
        return GitResult(
            success=False, command=cmd_display,
            stdout="", stderr="Command timed out after 30 s",
        )
    except FileNotFoundError:
        return GitResult(
            success=False, command=cmd_display,
            stdout="", stderr="git is not installed or not in PATH",
        )


# ------------------------------------------------------------------
# Query helpers
# ------------------------------------------------------------------

def get_branches(repo_path: str | Path) -> list[BranchInfo]:
    """Return local branches.  The active branch has ``is_active=True``."""
    result = run_git(repo_path, "branch", "--list", "--no-color")
    if not result.success:
        return []
    branches: list[BranchInfo] = []
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line:
            continue
        active = line.startswith("* ")
        name = line.lstrip("* ").strip()
        if name.startswith("("):
            name = "HEAD (detached)"
        branches.append(BranchInfo(name=name, is_active=active))
    # Put the active branch first for convenience
    branches.sort(key=lambda b: (not b.is_active, b.name))
    return branches


def get_recent_commits(
    repo_path: str | Path,
    branch: str,
    count: int = 5,
) -> list[CommitInfo]:
    """Return the *count* most recent commits on *branch*."""
    result = run_git(
        repo_path, "log", branch, f"-{count}",
        "--pretty=format:%H%n%h%n%s%n%an%n%ar",
    )
    if not result.success or not result.stdout:
        return []
    lines = result.stdout.split("\n")
    commits: list[CommitInfo] = []
    for i in range(0, len(lines), 5):
        if i + 5 > len(lines):
            break
        commits.append(CommitInfo(
            hash=lines[i],
            short_hash=lines[i + 1],
            subject=lines[i + 2],
            author=lines[i + 3],
            date=lines[i + 4],
        ))
    return commits


# ------------------------------------------------------------------
# Mutation commands
# ------------------------------------------------------------------

def checkout_branch(repo_path: str | Path, branch: str) -> GitResult:
    """Checkout an existing local branch."""
    return run_git(repo_path, "checkout", branch)


def create_branch(
    repo_path: str | Path,
    new_branch: str,
    from_ref: str | None = None,
) -> GitResult:
    """Create and checkout a new branch, optionally from *from_ref*."""
    args = ["checkout", "-b", new_branch]
    if from_ref:
        args.append(from_ref)
    return run_git(repo_path, *args)


def pull_current_branch(repo_path: str | Path) -> GitResult:
    """Pull the current branch from its upstream."""
    return run_git(repo_path, "pull")


def reset_to_commit(
    repo_path: str | Path,
    commit_hash: str,
    mode: str = "hard",
) -> GitResult:
    """Reset to *commit_hash* with ``--hard`` or ``--soft``."""
    if mode not in ("hard", "soft"):
        return GitResult(
            success=False,
            command=f"git reset --{mode} {commit_hash}",
            stdout="",
            stderr=f"Invalid reset mode: {mode!r}. Use 'hard' or 'soft'.",
        )
    return run_git(repo_path, "reset", f"--{mode}", commit_hash)
