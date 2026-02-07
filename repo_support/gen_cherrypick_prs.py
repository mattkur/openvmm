#!/usr/bin/env python3

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""Create cherry-pick PRs for merged PRs on main.

Examples:
  python3 repo_support/gen_cherrypick_prs.py release/1.7.2511 2680 2681
  python3 repo_support/gen_cherrypick_prs.py release/1.7.2511 --from-backport-label
  python3 repo_support/gen_cherrypick_prs.py staging/1.7.2511 --dry-run
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from repo_support.shared_utils import (
    format_actionable_message,
    format_conflict_summary,
    format_error,
    git_get_upstream_remote,
    git_merge_base,
    git_worktree_add,
    git_worktree_remove,
    validate_branch_name,
    validate_pr_number,
)


@dataclass(frozen=True)
class PullRequest:
    number: int
    title: str
    body: str
    url: str
    merged_at: datetime
    merge_sha: str


@dataclass(frozen=True)
class Result:
    pr_number: int
    status: str
    message: str
    worktree_path: str | None = None
    branch: str | None = None
    cherry_pick_pr_url: str | None = None


def _run_command(cmd: list[str], *, cwd: Path | None = None) -> str:
    result = subprocess.run(
        cmd,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        check=False,
        cwd=str(cwd) if cwd else None,
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


def _parse_pr_numbers(items: list[str]) -> list[int]:
    numbers: list[int] = []
    for item in items:
        text = item.strip()
        match = re.search(r"/pull/(\d+)", text)
        if match:
            numbers.append(validate_pr_number(match.group(1)))
            continue
        match = re.search(r"(\d+)$", text.lstrip("#"))
        if not match:
            raise ValueError(f"Invalid PR reference: {item}")
        numbers.append(validate_pr_number(match.group(1)))
    seen: set[int] = set()
    deduped: list[int] = []
    for number in numbers:
        if number not in seen:
            deduped.append(number)
            seen.add(number)
    return deduped


def _parse_github_datetime(value: str) -> datetime:
    if value.endswith("Z"):
        value = value[:-1] + "+00:00"
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _extract_merge_sha(prj: dict[str, Any]) -> str:
    merge_commit = prj.get("mergeCommit")
    if isinstance(merge_commit, str):
        return merge_commit.strip()
    if isinstance(merge_commit, dict):
        for key in ("oid", "sha", "id"):
            value = merge_commit.get(key)
            if isinstance(value, str) and value.strip():
                return value.strip()
    return ""


def _gh_pr_view(pr_number: int, repo: str | None) -> dict[str, Any]:
    cmd = [
        "gh",
        "pr",
        "view",
        str(pr_number),
        "--json",
        "number,title,body,url,state,mergedAt,mergeCommit",
    ]
    if repo:
        cmd.extend(["-R", repo])
    output = _run_command(cmd)
    if not output:
        raise RuntimeError("Empty response from gh pr view")
    return json.loads(output)


def _gh_pr_list_by_label(label: str, repo: str | None) -> list[dict[str, Any]]:
    cmd = [
        "gh",
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
        "number,title,body,url,state,mergedAt,mergeCommit",
    ]
    if repo:
        cmd.extend(["-R", repo])
    output = _run_command(cmd)
    if not output:
        return []
    return json.loads(output)


def _git_fetch(remote: str = "origin") -> None:
    _run_command(["git", "fetch", remote])


def _git_checkout_new_branch(worktree_path: Path, branch: str, base: str) -> None:
    _run_command(["git", "-C", str(worktree_path), "checkout", "-b", branch, base])


def _git_cherrypick(worktree_path: Path, commit: str) -> None:
    _run_command(["git", "-C", str(worktree_path), "cherry-pick", commit])


def _git_conflicted_files(worktree_path: Path) -> list[str]:
    output = _run_command(
        ["git", "-C", str(worktree_path), "diff", "--name-only", "--diff-filter=U"]
    )
    return [line.strip() for line in output.splitlines() if line.strip()]


def _git_push(worktree_path: Path, branch: str, remote: str = "origin") -> None:
    _run_command(["git", "-C", str(worktree_path), "push", "-u", remote, branch])


def _gh_pr_create(repo: str | None, base: str, head: str, title: str, body: str) -> str:
    cmd = ["gh", "pr", "create", "--base", base, "--head", head, "--title", title, "--body", body]
    if repo:
        cmd.extend(["-R", repo])
    return _run_command(cmd)


def _branch_for_pr(version: str, pr_number: int) -> str:
    sanitized = version.replace(".", "-")
    return f"backport/{sanitized}/pr-{pr_number}"


def _worktree_path(repo_root: Path, timestamp: str) -> Path:
    return repo_root / ".git" / "worktrees" / f"backport-temp-{timestamp}"


def _format_yaml_summary(summary: dict[str, Any]) -> str:
    lines: list[str] = []

    def scalar(value: Any) -> str:
        if isinstance(value, bool):
            return "true" if value else "false"
        if isinstance(value, (int, float)):
            return str(value)
        return json.dumps(str(value))

    def emit(key: str, value: Any, indent: int) -> None:
        prefix = "  " * indent
        if isinstance(value, dict):
            lines.append(f"{prefix}{key}:")
            for sub_key, sub_val in value.items():
                emit(sub_key, sub_val, indent + 1)
            return
        if isinstance(value, list):
            lines.append(f"{prefix}{key}:")
            for item in value:
                if isinstance(item, dict):
                    lines.append(f"{prefix}  -")
                    for sub_key, sub_val in item.items():
                        emit(sub_key, sub_val, indent + 2)
                else:
                    lines.append(f"{prefix}  - {scalar(item)}")
            return
        lines.append(f"{prefix}{key}: {scalar(value)}")

    for summary_key, summary_value in summary.items():
        emit(summary_key, summary_value, 0)
    return "\n".join(lines)


def _summarize_results(target_branch: str, results: list[Result]) -> str:
    summary = {
        "target_branch": target_branch,
        "total": len(results),
        "created": sum(1 for result in results if result.status == "success"),
        "skipped": sum(1 for result in results if result.status == "skipped"),
        "conflicts": sum(1 for result in results if result.status == "conflict"),
        "errors": sum(1 for result in results if result.status == "error"),
        "results": [
            {
                "pr": result.pr_number,
                "status": result.status,
                "message": result.message,
                "branch": result.branch or "",
                "worktree": result.worktree_path or "",
                "cherry_pick_pr": result.cherry_pick_pr_url or "",
            }
            for result in results
        ],
    }
    return _format_yaml_summary(summary)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create cherry-pick PRs for merged PRs, using isolated worktrees."
    )
    parser.add_argument("target_branch", help="Target branch (release/X.Y.Z or staging/X.Y.Z)")
    parser.add_argument("prs", nargs="*", help="PR numbers or URLs")
    parser.add_argument(
        "--from-backport-label",
        action="store_true",
        help="Discover PRs from backport_<version> label on main",
    )
    parser.add_argument("--dry-run", action="store_true", help="Show planned actions without side effects")
    parser.add_argument("--no-confirm", action="store_true", help="Skip interactive confirmation prompts")
    parser.add_argument("--keep-worktree", action="store_true", help="Keep worktree after success")
    parser.add_argument("--force-cleanup", action="store_true", help="Remove worktree even after conflicts")
    parser.add_argument("--repo", "-R", default=None, help="Optional owner/repo for GitHub API calls")
    parser.add_argument(
        "--remote",
        default=None,
        help="Git remote to use (auto-detected if not specified: upstream > origin)",
    )

    args = parser.parse_args()

    try:
        target_branch = validate_branch_name(args.target_branch)
        match = re.match(r"^(release|staging)/(.*)$", target_branch)
        if not match:
            raise ValueError(f"Invalid target branch: {target_branch}")
        version = match.group(2)
        pr_numbers = _parse_pr_numbers(args.prs) if args.prs else []
        if not args.from_backport_label and not pr_numbers:
            raise ValueError("Provide PR numbers or use --from-backport-label")
    except ValueError as exc:
        print(format_error(str(exc)), file=sys.stderr)
        return 2

    remote = args.remote if args.remote else git_get_upstream_remote()

    try:
        _git_fetch(remote)
    except RuntimeError as exc:
        print(format_error(f"Failed to fetch {remote}", details=[str(exc)]), file=sys.stderr)
        return 3

    prs: list[PullRequest] = []

    try:
        if args.from_backport_label:
            label = f"backport_{version}"
            labeled = _gh_pr_list_by_label(label, args.repo)
            for item in labeled:
                pr_number = validate_pr_number(item.get("number"))
                full = _gh_pr_view(pr_number, args.repo)
                state = str(full.get("state") or "").upper()
                if state != "MERGED":
                    continue
                merged_at_raw = str(full.get("mergedAt") or "")
                if not merged_at_raw:
                    raise RuntimeError(f"PR #{pr_number} missing mergedAt")
                merge_sha = _extract_merge_sha(full)
                if not merge_sha:
                    raise RuntimeError(f"PR #{pr_number} missing merge commit")
                prs.append(
                    PullRequest(
                        number=pr_number,
                        title=str(full.get("title") or "").strip(),
                        body=str(full.get("body") or "").strip(),
                        url=str(full.get("url") or "").strip(),
                        merged_at=_parse_github_datetime(merged_at_raw),
                        merge_sha=merge_sha,
                    )
                )
        else:
            for pr_number in pr_numbers:
                full = _gh_pr_view(pr_number, args.repo)
                state = str(full.get("state") or "").upper()
                if state != "MERGED":
                    raise RuntimeError(f"PR #{pr_number} is not merged (state={state})")
                merged_at_raw = str(full.get("mergedAt") or "")
                if not merged_at_raw:
                    raise RuntimeError(f"PR #{pr_number} missing mergedAt")
                merge_sha = _extract_merge_sha(full)
                if not merge_sha:
                    raise RuntimeError(f"PR #{pr_number} missing merge commit")
                prs.append(
                    PullRequest(
                        number=pr_number,
                        title=str(full.get("title") or "").strip(),
                        body=str(full.get("body") or "").strip(),
                        url=str(full.get("url") or "").strip(),
                        merged_at=_parse_github_datetime(merged_at_raw),
                        merge_sha=merge_sha,
                    )
                )
    except RuntimeError as exc:
        print(format_error("GitHub API error", details=[str(exc)]), file=sys.stderr)
        return 3

    prs.sort(key=lambda pr: pr.merged_at)

    results: list[Result] = []

    if args.dry_run:
        print("--dry-run set; no changes will be made.")
        for pr in prs:
            branch = _branch_for_pr(version, pr.number)
            print(f"Would process #{pr.number}: {pr.title} -> {branch}")
        return 0

    repo_root = Path.cwd()

    for pr in prs:
        try:
            if git_merge_base(pr.merge_sha, f"{remote}/{target_branch}"):
                results.append(
                    Result(
                        pr_number=pr.number,
                        status="skipped",
                        message="Merge commit already in target branch",
                    )
                )
                continue
        except RuntimeError as exc:
            results.append(
                Result(pr_number=pr.number, status="error", message=f"merge-base failed: {exc}")
            )
            break

        timestamp = datetime.now(tz=timezone.utc).strftime("%Y%m%dT%H%M%SZ")
        worktree_path = _worktree_path(repo_root, timestamp)
        branch = _branch_for_pr(version, pr.number)

        try:
            git_worktree_add(worktree_path, f"{remote}/{target_branch}")
            _git_checkout_new_branch(worktree_path, branch, f"{remote}/{target_branch}")
        except RuntimeError as exc:
            results.append(
                Result(
                    pr_number=pr.number,
                    status="error",
                    message=f"Failed to create worktree: {exc}",
                    worktree_path=str(worktree_path),
                    branch=branch,
                )
            )
            break

        try:
            _git_cherrypick(worktree_path, pr.merge_sha)
        except RuntimeError:
            conflicted_files = _git_conflicted_files(worktree_path)
            summary = format_conflict_summary(conflicted_files, worktree_path)
            print(summary, file=sys.stderr)
            print(
                format_actionable_message(
                    "Cherry-pick conflict detected.",
                    "Conflicts require prerequisite analysis.",
                    [
                        f"Run: python3 -m repo_support.analyze_pr_deps --file {conflicted_files[0] if conflicted_files else '<file>'} --target {target_branch}",
                        f"Worktree retained at {worktree_path}",
                        f"Cleanup: git worktree remove {worktree_path}",
                    ],
                ),
                file=sys.stderr,
            )
            if args.force_cleanup:
                git_worktree_remove(worktree_path, force=True)
            results.append(
                Result(
                    pr_number=pr.number,
                    status="conflict",
                    message="Cherry-pick conflict",
                    worktree_path=str(worktree_path),
                    branch=branch,
                )
            )
            break

        try:
            _git_push(worktree_path, branch, remote)
            pr_title = f"{pr.title} (cherry-pick from #{pr.number})"
            pr_body = f"Cherry-picked from #{pr.number}\n\nOriginal PR: {pr.url}\n"
            if not args.no_confirm:
                answer = input(f"Create cherry-pick PR for #{pr.number}? [y/N] ").strip().lower()
                if answer not in ("y", "yes"):
                    results.append(
                        Result(
                            pr_number=pr.number,
                            status="skipped",
                            message="User skipped PR creation",
                            worktree_path=str(worktree_path),
                            branch=branch,
                        )
                    )
                    if not args.keep_worktree:
                        git_worktree_remove(worktree_path, force=False)
                    continue
            pr_url = _gh_pr_create(args.repo, target_branch, branch, pr_title, pr_body)
            results.append(
                Result(
                    pr_number=pr.number,
                    status="success",
                    message="Cherry-pick PR created",
                    worktree_path=str(worktree_path),
                    branch=branch,
                    cherry_pick_pr_url=pr_url,
                )
            )
        except RuntimeError as exc:
            results.append(
                Result(
                    pr_number=pr.number,
                    status="error",
                    message=f"Failed to create PR: {exc}",
                    worktree_path=str(worktree_path),
                    branch=branch,
                )
            )
            break
        finally:
            if not args.keep_worktree:
                try:
                    git_worktree_remove(worktree_path, force=False)
                except RuntimeError:
                    pass

    print(_summarize_results(target_branch, results))

    if any(result.status in ("conflict", "error") for result in results):
        return 3
    if not results:
        print(
            format_actionable_message(
                "No PRs processed.",
                "No eligible merged PRs were discovered.",
                ["Check labels and PR numbers", "Verify branch and repo arguments"],
            )
        )
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
