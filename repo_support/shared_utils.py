# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Shared utilities for PR branch management tools.

This module provides input validation, GitHub CLI wrappers, git helpers, and
error formatting utilities used across repo_support scripts.
"""

from __future__ import annotations

import json
import re
import subprocess
from pathlib import Path
from typing import Any, Iterable


_BRANCH_PATTERN = re.compile(r"^(main|release|staging)/[0-9.]+$|^main$")
_VERSION_PATTERN = re.compile(r"^[0-9.]+$")
_LABEL_PATTERN = re.compile(r"^[a-zA-Z0-9_.-]+$")
_PR_PATTERN = re.compile(r"^[0-9]+$")


def _run_command(cmd: list[str], *, check: bool = True, cwd: str | None = None) -> str:
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        cwd=cwd,
    )
    if check and result.returncode != 0:
        stdout = result.stdout or ""
        stderr = result.stderr or ""
        raise RuntimeError(
            "Command failed ({code}): {cmd}\nSTDOUT:\n{stdout}\nSTDERR:\n{stderr}".format(
                code=result.returncode,
                cmd=" ".join(cmd),
                stdout=stdout,
                stderr=stderr,
            )
        )
    return (result.stdout or "").strip()


def validate_pr_number(pr_number: str) -> int:
    """Validate and normalize a PR number string."""
    value = str(pr_number).strip()
    if not _PR_PATTERN.match(value):
        raise ValueError(f"Invalid PR number: {pr_number}")
    return int(value)


def validate_branch_name(branch_name: str) -> str:
    """Validate a branch name (main, release/X.Y.Z, staging/X.Y.Z)."""
    value = str(branch_name).strip()
    if not _BRANCH_PATTERN.match(value):
        raise ValueError(f"Invalid branch name: {branch_name}")
    return value


def validate_version(version: str) -> str:
    """Validate a release version string (X.Y.Z)."""
    value = str(version).strip()
    if not _VERSION_PATTERN.match(value):
        raise ValueError(f"Invalid version: {version}")
    return value


def validate_label(label: str) -> str:
    """Validate a GitHub label string."""
    value = str(label).strip()
    if not _LABEL_PATTERN.match(value):
        raise ValueError(f"Invalid label: {label}")
    return value


def gh_pr_view(pr_number: int, repo: str | None = None) -> dict[str, Any]:
    """Return PR details via `gh pr view` JSON output."""
    cmd = [
        "gh",
        "pr",
        "view",
        str(pr_number),
        "--json",
        "number,title,body,url,state,mergedAt,mergeCommit,labels,author",
    ]
    if repo:
        cmd.extend(["-R", repo])
    output = _run_command(cmd)
    if not output:
        raise RuntimeError("Empty response from gh pr view")
    return json.loads(output)


def gh_pr_list(state: str, label: str | None = None, repo: str | None = None) -> list[dict[str, Any]]:
    """Return PR list via `gh pr list` JSON output."""
    cmd = [
        "gh",
        "pr",
        "list",
        "--state",
        state,
        "--limit",
        "1000",
        "--json",
        "number,title,body,url,state,mergedAt,mergeCommit,labels,author",
    ]
    if label:
        cmd.extend(["--label", label])
    if repo:
        cmd.extend(["-R", repo])
    output = _run_command(cmd)
    if not output:
        return []
    return json.loads(output)


def gh_api_query(endpoint: str, repo: str | None = None) -> dict[str, Any]:
    """Query GitHub API via `gh api` and return JSON output."""
    cmd = ["gh", "api", endpoint]
    if repo:
        cmd.extend(["-R", repo])
    output = _run_command(cmd)
    if not output:
        raise RuntimeError("Empty response from gh api")
    return json.loads(output)


def git_fetch(remote: str = "origin") -> None:
    """Fetch from a git remote."""
    _run_command(["git", "fetch", remote], check=True)

def git_get_upstream_remote() -> str:
    """Detect the upstream remote name.
    
    Prefers 'upstream' if it exists, falls back to 'origin', or uses the only remote available.
    """
    result = subprocess.run(
        ["git", "remote"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    
    if result.returncode != 0:
        # Default to origin if git remote fails
        return "origin"
    
    remotes = [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
    
    if not remotes:
        return "origin"
    
    # If only one remote, use it
    if len(remotes) == 1:
        return remotes[0]
    
    # Prefer 'upstream' if it exists
    if "upstream" in remotes:
        return "upstream"
    
    # Fall back to 'origin'
    if "origin" in remotes:
        return "origin"
    
    # Use the first remote as last resort
    return remotes[0]

def git_merge_base(commit: str, branch: str) -> bool:
    """Return True if commit is reachable from branch."""
    result = subprocess.run(
        ["git", "merge-base", "--is-ancestor", commit, branch],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return True
    if result.returncode == 1:
        return False
    raise RuntimeError(result.stderr or "git merge-base failed")


def git_worktree_add(path: Path, branch: str) -> None:
    """Add a git worktree at path for branch."""
    _run_command(["git", "worktree", "add", str(path), branch], check=True)


def git_branch_exists(branch: str, remote: str | None = None) -> bool:
    """Check if a branch exists locally or on remote.
    
    If remote is None, auto-detects the upstream remote.
    """
    if remote is None:
        remote = git_get_upstream_remote()
    
    # Try remote first
    result = subprocess.run(
        ["git", "rev-parse", "--verify", f"{remote}/{branch}"],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return True
    
    # Try local
    result = subprocess.run(
        ["git", "rev-parse", "--verify", branch],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    return result.returncode == 0


def git_worktree_remove(path: Path, force: bool = False) -> None:
    """Remove a git worktree at path."""
    cmd = ["git", "worktree", "remove"]
    if force:
        cmd.append("--force")
    cmd.append(str(path))
    _run_command(cmd, check=True)


def format_error(message: str, *, details: Iterable[str] | None = None) -> str:
    """Return a standardized error message string."""
    lines = [f"ERROR: {message}"]
    if details:
        lines.append("Details:")
        lines.extend(f"- {detail}" for detail in details)
    return "\n".join(lines)


def format_conflict_summary(conflicted_files: Iterable[str], worktree_path: Path) -> str:
    """Return a formatted conflict summary message."""
    files = list(conflicted_files)
    lines = ["Cherry-pick conflict detected.", "Conflicted files:"]
    lines.extend(f"- {name}" for name in files)
    lines.append(f"Worktree retained at: {worktree_path}")
    return "\n".join(lines)


def format_actionable_message(what: str, why: str, how: Iterable[str]) -> str:
    """Return a user-facing error string with actionable guidance."""
    lines = [what, "", why, "", "Next steps:"]
    lines.extend(f"- {step}" for step in how)
    return "\n".join(lines)
