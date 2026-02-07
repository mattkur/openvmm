#!/usr/bin/env python3

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Relabel backported PRs from backport_X to backported_X.

Scans both release/X.Y.Z and staging/X.Y.Z branches for backported commits.

Examples:
  python3 repo_support/relabel_backported.py 1.7.2511
  python3 repo_support/relabel_backported.py 1.7.2511 --update
  python3 repo_support/relabel_backported.py 1.7.2511 --force-update-pr 2680,2567
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from typing import Any, Iterable

from repo_support.shared_utils import (
    format_actionable_message,
    format_error,
    validate_label,
    validate_pr_number,
    validate_version,
)


@dataclass(frozen=True)
class RelabelResult:
    pr_number: int
    action: str
    message: str
    backport_pr: str | None = None


def _run_command(cmd: list[str]) -> str:
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
    )
    if result.returncode != 0:
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


def _parse_force_update_prs(raw: list[str] | None) -> set[int]:
    if not raw:
        return set()
    values: set[int] = set()
    for item in raw:
        for piece in item.split(","):
            piece = piece.strip()
            if not piece:
                continue
            values.add(validate_pr_number(piece))
    return values


def _gh_pr_list(label: str, repo: str | None) -> list[dict[str, Any]]:
    cmd = [
        "gh",
        "pr",
        "list",
        "--limit",
        "10000",
        "--base",
        "main",
        "--state",
        "all",
        "--label",
        label,
        "--json",
        "title,url,number,state",
    ]
    if repo:
        cmd.extend(["-R", repo])
    output = _run_command(cmd)
    if not output:
        return []
    return json.loads(output)


def _git_log_for_pr(branches: list[str], pr_number: int, title: str) -> list[str]:
    """Search git log in multiple branches for PR references."""
    title_for_regex = re.escape(re.sub(r" (\(#\d+\))+$", "", title))
    pattern = (
        rf"(#{pr_number}\b)|(github.com/microsoft/openvmm/pull/{pr_number}\b)|({title_for_regex})"
    )
    commits: list[str] = []
    for branch in branches:
        try:
            cmd = [
                "git",
                "log",
                branch,
                "--oneline",
                "-E",
                f"--grep={pattern}",
            ]
            output = _run_command(cmd)
            lines = [line for line in output.splitlines() if line.strip()]
            commits.extend(lines)
        except RuntimeError:
            # Branch might not exist; continue checking other branches
            continue
    return commits


def _commit_subject(commit_line: str) -> str:
    parts = commit_line.split(" ", 1)
    if len(parts) == 2:
        return parts[1]
    return ""


def _title_matches_commit(title: str, commit_line: str) -> bool:
    base_title = re.sub(r" (\(#\d+\))+$", "", title)
    subject = _commit_subject(commit_line)
    return base_title in subject


def _extract_backport_pr(commit_line: str, original_pr: int) -> str | None:
    matches = re.findall(r"#([0-9]+)", commit_line)
    if not matches:
        return None
    backport_pr = matches[-1]
    if backport_pr == str(original_pr):
        return None
    return backport_pr


def _gh_pr_comment(pr_number: int, body: str, repo: str | None) -> None:
    cmd = ["gh", "pr", "comment", str(pr_number), "-b", body]
    if repo:
        cmd.extend(["-R", repo])
    _run_command(cmd)


def _gh_pr_edit(pr_number: int, add_label: str, remove_label: str, repo: str | None) -> None:
    cmd = [
        "gh",
        "pr",
        "edit",
        str(pr_number),
        "--add-label",
        add_label,
        "--remove-label",
        remove_label,
    ]
    if repo:
        cmd.extend(["-R", repo])
    _run_command(cmd)


def _format_yaml_summary(dry_run: bool, version: str, results: list[RelabelResult]) -> str:
    warnings = sum(1 for result in results if result.action.startswith("warn"))
    skipped = sum(1 for result in results if result.action == "skip")
    updates = sum(1 for result in results if result.action == "update")
    lines: list[str] = []

    def scalar(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        return json.dumps(str(value))

    lines.append(f"dryRun: {scalar(dry_run)}")
    lines.append(f"version: {scalar(version)}")
    lines.append("results:")
    for result in results:
        lines.append("  - prNumber: {0}".format(result.pr_number))
        lines.append("    action: {0}".format(scalar(result.action)))
        lines.append("    message: {0}".format(scalar(result.message)))
        if result.backport_pr:
            lines.append("    backportPR: {0}".format(scalar(result.backport_pr)))
    lines.append("summary:")
    lines.append(f"  wouldUpdate: {updates}")
    lines.append(f"  wouldWarn: {warnings}")
    lines.append(f"  wouldSkip: {skipped}")
    if dry_run:
        lines.append("  message: \"Run with --update to apply changes\"")
    return "\n".join(lines)


def main() -> int:
    parser = argparse.ArgumentParser(description="Relabel backported PRs for a release version.")
    parser.add_argument("version", help="Release version to scan (e.g. 1.7.2511)")
    parser.add_argument("--update", action="store_true", help="Apply label updates and comments")
    parser.add_argument(
        "--force-update-pr",
        action="append",
        help="Comma-separated PR numbers to update even if titles mismatch",
    )
    parser.add_argument("--repo", "-R", default=None, help="Optional owner/repo for GitHub API calls")

    args = parser.parse_args()

    try:
        version = validate_version(args.version)
        label = validate_label(f"backport_{version}")
        completed_label = validate_label(f"backported_{version}")
        force_update = _parse_force_update_prs(args.force_update_pr)
    except ValueError as exc:
        print(format_error(str(exc)), file=sys.stderr)
        return 2

    try:
        prs = _gh_pr_list(label, args.repo)
    except RuntimeError as exc:
        print(format_error("GitHub API error", details=[str(exc)]), file=sys.stderr)
        return 3

    if not prs:
        print(
            format_actionable_message(
                "No backport labels found.",
                f"No PRs found with label {label}.",
                ["Verify the version and labels", "Confirm gh is authenticated"],
            )
        )
        return 1

    results: list[RelabelResult] = []
    warnings_present = False

    for pr in prs:
        pr_number = validate_pr_number(pr.get("number"))
        title = str(pr.get("title") or "").strip()
        url = str(pr.get("url") or "").strip()
        state = str(pr.get("state") or "").upper()

        if state != "MERGED":
            results.append(
                RelabelResult(
                    pr_number=pr_number,
                    action="skip",
                    message=f"PR still open on main: {url}",
                )
            )
            continue

        # Check both release and staging branches
        branches = [f"origin/release/{version}", f"origin/staging/{version}"]
        try:
            commits = _git_log_for_pr(branches, pr_number, title)
        except RuntimeError as exc:
            print(format_error("Git error", details=[str(exc)]), file=sys.stderr)
            return 3

        if not commits:
            warnings_present = True
            results.append(
                RelabelResult(
                    pr_number=pr_number,
                    action="warn_no_backport",
                    message="No backport commit found in target branch",
                )
            )
            continue

        backport_pr: str | None = None
        title_mismatch = False
        for commit in commits:
            if not _title_matches_commit(title, commit):
                title_mismatch = True
            candidate = _extract_backport_pr(commit, pr_number)
            if candidate:
                backport_pr = candidate

        if title_mismatch and pr_number not in force_update:
            warnings_present = True
            results.append(
                RelabelResult(
                    pr_number=pr_number,
                    action="warn_title_mismatch",
                    message="Commit title differs from PR title; use --force-update-pr to override",
                    backport_pr=backport_pr,
                )
            )
            continue

        if not backport_pr:
            warnings_present = True
            results.append(
                RelabelResult(
                    pr_number=pr_number,
                    action="warn_backport_pr_missing",
                    message="Backport PR number not detected in commit message",
                )
            )
            continue

        comment = (
            f"Backported to [release/{version}](https://github.com/microsoft/openvmm/tree/release/{version}) "
            f"in #{backport_pr}"
        )
        if args.update:
            try:
                _gh_pr_comment(pr_number, comment, args.repo)
                _gh_pr_edit(pr_number, completed_label, label, args.repo)
            except RuntimeError as exc:
                print(format_error("GitHub API error", details=[str(exc)]), file=sys.stderr)
                return 3
            results.append(
                RelabelResult(
                    pr_number=pr_number,
                    action="update",
                    message="Labels updated",
                    backport_pr=backport_pr,
                )
            )
        else:
            results.append(
                RelabelResult(
                    pr_number=pr_number,
                    action="update",
                    message="Would update labels",
                    backport_pr=backport_pr,
                )
            )

    print(_format_yaml_summary(not args.update, version, results))

    if warnings_present:
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
