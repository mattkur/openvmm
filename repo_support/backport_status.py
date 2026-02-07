#!/usr/bin/env python3

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Backport status dashboard for release/staging branches.

Examples:
  python3 repo_support/backport_status.py 1.7.2511
  python3 repo_support/backport_status.py 1.7.2511 --format table
  python3 repo_support/backport_status.py 1.7.2511 --pr 2680
  python3 repo_support/backport_status.py 1.7.2511 --branch release/1.7.2511
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Iterable

from repo_support.shared_utils import (
    format_actionable_message,
    format_error,
    validate_branch_name,
    validate_pr_number,
    validate_version,
)


@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str
    url: str


@dataclass(frozen=True)
class CherryPickPR:
    number: int
    title: str
    url: str
    base: str
    original_pr: int | None


def _run_gh_json(args: list[str], *, repo: str | None) -> Any:
    cmd = ["gh", *args]
    if repo:
        cmd.extend(["-R", repo])
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr or "gh command failed")
    output = (result.stdout or "").strip()
    if not output:
        return []
    return json.loads(output)


def _list_backport_prs(label: str, repo: str | None) -> list[PullRequest]:
    items = _run_gh_json(
        [
            "pr",
            "list",
            "--state",
            "merged",
            "--base",
            "main",
            "--label",
            label,
            "--limit",
            "1000",
            "--json",
            "number,title,url",
        ],
        repo=repo,
    )
    prs: list[PullRequest] = []
    for item in items:
        prs.append(
            PullRequest(
                number=int(item.get("number")),
                title=str(item.get("title") or "").strip(),
                url=str(item.get("url") or "").strip(),
            )
        )
    return prs


def _list_open_cherrypicks(base_branch: str, repo: str | None) -> list[CherryPickPR]:
    items = _run_gh_json(
        [
            "pr",
            "list",
            "--state",
            "open",
            "--base",
            base_branch,
            "--limit",
            "1000",
            "--json",
            "number,title,url,body",
        ],
        repo=repo,
    )
    prs: list[CherryPickPR] = []
    for item in items:
        title = str(item.get("title") or "").strip()
        body = str(item.get("body") or "").strip()
        original = _extract_original_pr_number(title, body)
        prs.append(
            CherryPickPR(
                number=int(item.get("number")),
                title=title,
                url=str(item.get("url") or "").strip(),
                base=base_branch,
                original_pr=original,
            )
        )
    return prs


def _extract_original_pr_number(title: str, body: str) -> int | None:
    patterns = [
        r"cherry-pick from #(?P<num>\d+)",
        r"cherry picked from #(?P<num>\d+)",
    ]
    for pattern in patterns:
        match = re.search(pattern, title, re.IGNORECASE)
        if match:
            return int(match.group("num"))
        match = re.search(pattern, body, re.IGNORECASE)
        if match:
            return int(match.group("num"))
    return None


def _find_conflict_worktrees(repo_root: Path) -> list[Path]:
    worktrees_dir = repo_root / ".git" / "worktrees"
    if not worktrees_dir.exists():
        return []
    return sorted(
        [path for path in worktrees_dir.iterdir() if path.is_dir() and path.name.startswith("backport-temp-")]
    )


def _format_summary(
    version: str,
    targets: Iterable[str],
    pending: list[PullRequest],
    completed: list[PullRequest],
    in_progress: list[CherryPickPR],
    conflicts: list[Path],
) -> str:
    lines = [
        f"Version: {version}",
        f"Targets: {', '.join(targets)}",
        f"Pending backports: {len(pending)}",
        f"In-progress cherry-picks: {len(in_progress)}",
        f"Completed backports: {len(completed)}",
        f"Conflict worktrees: {len(conflicts)}",
    ]
    return "\n".join(lines)


def _format_table(
    pending: list[PullRequest],
    completed: list[PullRequest],
    in_progress: list[CherryPickPR],
    conflicts: list[Path],
) -> str:
    rows = [
        ("pending", str(len(pending))),
        ("in_progress", str(len(in_progress))),
        ("completed", str(len(completed))),
        ("conflicts", str(len(conflicts))),
    ]
    width = max(len(row[0]) for row in rows)
    return "\n".join(f"{name.ljust(width)}  {count}" for name, count in rows)


def _format_detailed(
    pending: list[PullRequest],
    completed: list[PullRequest],
    in_progress: list[CherryPickPR],
    conflicts: list[Path],
) -> str:
    lines: list[str] = []
    lines.append("Pending backports:")
    lines.extend(_format_pr_list(pending) or ["  (none)"])
    lines.append("In-progress cherry-picks:")
    lines.extend(_format_cherrypick_list(in_progress) or ["  (none)"])
    lines.append("Completed backports:")
    lines.extend(_format_pr_list(completed) or ["  (none)"])
    lines.append("Conflict worktrees:")
    if conflicts:
        lines.extend(f"  {path}" for path in conflicts)
    else:
        lines.append("  (none)")
    return "\n".join(lines)


def _format_pr_list(prs: list[PullRequest]) -> list[str]:
    return [f"  #{pr.number}: {pr.title} ({pr.url})" for pr in prs]


def _format_cherrypick_list(prs: list[CherryPickPR]) -> list[str]:
    lines: list[str] = []
    for pr in prs:
        origin = f" (from #{pr.original_pr})" if pr.original_pr else ""
        lines.append(f"  #{pr.number}: {pr.title} [{pr.base}]{origin} ({pr.url})")
    return lines


def _format_json(
    version: str,
    targets: Iterable[str],
    pending: list[PullRequest],
    completed: list[PullRequest],
    in_progress: list[CherryPickPR],
    conflicts: list[Path],
) -> str:
    data = {
        "version": version,
        "targets": list(targets),
        "pending": [pr.__dict__ for pr in pending],
        "completed": [pr.__dict__ for pr in completed],
        "in_progress": [pr.__dict__ for pr in in_progress],
        "conflicts": [str(path) for path in conflicts],
    }
    return json.dumps(data, indent=2)


def main() -> int:
    parser = argparse.ArgumentParser(description="Show backport status for a release version.")
    parser.add_argument("version", help="Release version (e.g. 1.7.2511)")
    parser.add_argument("--branch", help="Target branch (release/X.Y.Z or staging/X.Y.Z)")
    parser.add_argument("--pr", help="Filter status to a specific original PR number")
    parser.add_argument(
        "--format",
        choices=["summary", "table", "json", "detailed"],
        default="summary",
        help="Output format",
    )
    parser.add_argument("--repo", "-R", default=None, help="Optional owner/repo for GitHub API calls")

    args = parser.parse_args()

    try:
        version = validate_version(args.version)
        targets = [f"release/{version}", f"staging/{version}"]
        if args.branch:
            targets = [validate_branch_name(args.branch)]
        pr_filter = validate_pr_number(args.pr) if args.pr else None
    except ValueError as exc:
        print(format_error(str(exc)), file=sys.stderr)
        return 2

    try:
        pending = _list_backport_prs(f"backport_{version}", args.repo)
        completed = _list_backport_prs(f"backported_{version}", args.repo)
        in_progress: list[CherryPickPR] = []
        for target in targets:
            in_progress.extend(_list_open_cherrypicks(target, args.repo))
    except RuntimeError as exc:
        print(format_error("GitHub API error", details=[str(exc)]), file=sys.stderr)
        return 3

    conflicts = _find_conflict_worktrees(Path.cwd())

    if pr_filter is not None:
        pending = [pr for pr in pending if pr.number == pr_filter]
        completed = [pr for pr in completed if pr.number == pr_filter]
        in_progress = [pr for pr in in_progress if pr.original_pr == pr_filter]

    if not pending and not completed and not in_progress and not conflicts:
        print(
            format_actionable_message(
                "No backport data found.",
                "No matching PRs or worktrees were detected.",
                ["Verify labels exist on merged PRs", "Check the version/branch arguments"],
            )
        )
        return 1

    if args.format == "summary":
        output = _format_summary(version, targets, pending, completed, in_progress, conflicts)
    elif args.format == "table":
        output = _format_table(pending, completed, in_progress, conflicts)
    elif args.format == "json":
        output = _format_json(version, targets, pending, completed, in_progress, conflicts)
    else:
        output = _format_detailed(pending, completed, in_progress, conflicts)

    print(output)
    return 0


if __name__ == "__main__":
    sys.exit(main())
