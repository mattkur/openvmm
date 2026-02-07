#!/usr/bin/env python3

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""
Analyze PR dependencies for conflict investigation.

Identifies missing prerequisite PRs when cherry-picks conflict.

Usage:
    # Analyze a specific file
    analyze_pr_deps.py --file src/foo.rs --target release/1.7.2511
    
    # Analyze files changed in a PR
    analyze_pr_deps.py --pr 2680 --target release/1.7.2511
    
    # Filter by merge date
    analyze_pr_deps.py --file src/foo.rs --target release/1.7.2511 --merged-after 2026-01-01
    
    # JSON output
    analyze_pr_deps.py --file src/foo.rs --target release/1.7.2511 --json

Return codes:
    0: Analysis complete (may show prerequisites needed)
    1: File not found in repository
    2: Invalid arguments
    3: GitHub API error
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from shared_utils import (
    format_error,
    gh_pr_list,
    gh_pr_view,
    git_fetch,
    git_merge_base,
    validate_branch_name,
    validate_pr_number,
)


@dataclass
class PrerequisitePR:
    """Represents a prerequisite PR that touched the same files."""
    pr_number: int
    title: str
    merged_at: str
    status: str  # "missing_from_target", "in_target", "open_cherry_pick"
    reason: str
    recommendation: str
    open_cherry_pick_pr: int | None = None


def _parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Analyze PR dependencies for conflict investigation",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    input_group = parser.add_mutually_exclusive_group(required=True)
    input_group.add_argument(
        '--file',
        type=str,
        help='File path to analyze (which PRs modified this file)'
    )
    input_group.add_argument(
        '--pr',
        type=int,
        help='PR number to analyze (find prerequisites for this PR)'
    )
    
    parser.add_argument(
        '--target',
        type=str,
        required=True,
        help='Target branch to check against (e.g., release/1.7.2511)'
    )
    parser.add_argument(
        '--merged-after',
        type=str,
        help='Only consider PRs merged after this date (YYYY-MM-DD)'
    )
    parser.add_argument(
        '--repo',
        type=str,
        help='Repository in OWNER/REPO format (default: current repo)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output in JSON format'
    )
    
    return parser.parse_args()


def _validate_date(date_str: str) -> datetime:
    """Validate and parse ISO date string."""
    try:
        return datetime.fromisoformat(date_str)
    except ValueError:
        print(
            format_error(f"Date must be ISO format 'YYYY-MM-DD', got: '{date_str}'"),
            file=sys.stderr
        )
        sys.exit(2)


def _verify_file_exists(file_path: str) -> bool:
    """Check if file exists in repository."""
    path = Path(file_path)
    return path.exists()


def _get_files_changed_in_pr(pr_number: int, repo: str | None) -> list[str]:
    """Query GitHub for files changed in a PR."""
    try:
        result = subprocess.run(
            ['gh', 'pr', 'view', str(pr_number), '--json', 'files', '--jq', '.files[].path']
            + (['--repo', repo] if repo else []),
            capture_output=True,
            text=True,
            check=True
        )
        return [line.strip() for line in result.stdout.strip().split('\n') if line.strip()]
    except subprocess.CalledProcessError as e:
        print(format_error(f"Failed to get files for PR #{pr_number}: {e.stderr}"), file=sys.stderr)
        sys.exit(3)


def _get_merged_prs(repo: str | None, merged_after: str | None) -> list[dict[str, Any]]:
    """Query all merged PRs to main."""
    try:
        prs = gh_pr_list(state='merged', repo=repo)
        
        if merged_after:
            cutoff = _validate_date(merged_after)
            prs = [
                pr for pr in prs
                if pr.get('mergedAt') and datetime.fromisoformat(pr['mergedAt'].replace('Z', '+00:00')) >= cutoff
            ]
        
        return prs
    except Exception as e:
        print(format_error(f"Failed to query merged PRs: {str(e)}"), file=sys.stderr)
        sys.exit(3)


def _pr_touches_file(pr: dict[str, Any], file_path: str) -> bool:
    """Check if a PR modified the given file."""
    merge_commit = pr.get('mergeCommit', {}).get('oid')
    if not merge_commit:
        return False
    
    try:
        result = subprocess.run(
            ['git', 'diff-tree', '--no-commit-id', '--name-only', '-r', merge_commit],
            capture_output=True,
            text=True,
            check=True
        )
        modified_files = result.stdout.strip().split('\n')
        return file_path in modified_files
    except subprocess.CalledProcessError:
        return False


def _is_commit_in_target(commit_sha: str, target_branch: str) -> bool:
    """Check if commit is an ancestor of target branch."""
    try:
        return git_merge_base(commit_sha, f"origin/{target_branch}")
    except Exception:
        return False


def _find_open_cherry_pick(pr_number: int, target_branch: str, repo: str | None) -> int | None:
    """Search for open cherry-pick PRs mentioning this PR."""
    try:
        result = subprocess.run(
            ['gh', 'pr', 'list', '--state', 'open', '--base', target_branch, '--json', 'number,title,body']
            + (['--repo', repo] if repo else []),
            capture_output=True,
            text=True,
            check=True
        )
        
        prs = json.loads(result.stdout)
        for pr in prs:
            title = pr.get('title', '')
            body = pr.get('body', '')
            if f"#{pr_number}" in title or f"#{pr_number}" in body:
                if "cherry-pick" in title.lower() or "cherry-pick" in body.lower():
                    return pr['number']
        
        return None
    except subprocess.CalledProcessError:
        return None


def _analyze_file(file_path: str, target_branch: str, merged_after: str | None, repo: str | None) -> tuple[list[PrerequisitePR], int]:
    """Analyze which PRs touched a file and are missing from target."""
    if not _verify_file_exists(file_path):
        print(format_error(f"File '{file_path}' does not exist in repository"), file=sys.stderr)
        sys.exit(1)
    
    # Fetch latest
    git_fetch()
    
    # Get all merged PRs
    merged_prs = _get_merged_prs(repo, merged_after)
    
    # Filter PRs that touched this file
    relevant_prs = []
    for pr in merged_prs:
        if _pr_touches_file(pr, file_path):
            relevant_prs.append(pr)
    
    if not relevant_prs:
        print(format_error(f"No merged PRs found that modified '{file_path}'"), file=sys.stderr)
        sys.exit(1)
    
    # Analyze each PR
    prerequisites = []
    for pr in relevant_prs:
        pr_number = pr['number']
        title = pr.get('title', '')
        merged_at = pr.get('mergedAt', '')
        merge_commit = pr.get('mergeCommit', {}).get('oid', '')
        
        if not merge_commit:
            continue
        
        # Check if in target
        if _is_commit_in_target(merge_commit, target_branch):
            status = "in_target"
            reason = f"Already backported to {target_branch}"
            recommendation = ""
        else:
            # Check for open cherry-pick
            open_cp = _find_open_cherry_pick(pr_number, target_branch, repo)
            if open_cp:
                status = "open_cherry_pick"
                reason = f"Cherry-pick PR #{open_cp} is open - wait for merge before backporting other PRs"
                recommendation = f"Wait for #{open_cp} to merge, then backport dependent PRs"
            else:
                status = "missing_from_target"
                reason = f"Merged to main but commit not in {target_branch}"
                recommendation = f"Backport PR #{pr_number} first"
        
        prerequisites.append(PrerequisitePR(
            pr_number=pr_number,
            title=title,
            merged_at=merged_at,
            status=status,
            reason=reason,
            recommendation=recommendation,
            open_cherry_pick_pr=open_cp if status == "open_cherry_pick" else None
        ))
    
    # Sort by merge date (oldest first)
    prerequisites.sort(key=lambda p: p.merged_at)
    
    return prerequisites, len(relevant_prs)


def _analyze_pr(pr_number: int, target_branch: str, repo: str | None) -> tuple[list[str], list[PrerequisitePR], int]:
    """Analyze prerequisites for a specific PR."""
    # Validate PR exists
    pr_data = gh_pr_view(pr_number, repo)
    if not pr_data:
        print(format_error(f"PR #{pr_number} not found"), file=sys.stderr)
        sys.exit(2)
    
    if pr_data.get('state') != 'MERGED':
        print(format_error(f"PR #{pr_number} is not merged to main"), file=sys.stderr)
        sys.exit(2)
    
    # Get files changed in PR
    files = _get_files_changed_in_pr(pr_number, repo)
    
    # Analyze each file
    all_prerequisites: dict[int, PrerequisitePR] = {}
    for file_path in files:
        if not _verify_file_exists(file_path):
            continue
        
        file_prereqs, _ = _analyze_file(file_path, target_branch, None, repo)
        for prereq in file_prereqs:
            if prereq.pr_number not in all_prerequisites:
                all_prerequisites[prereq.pr_number] = prereq
    
    prerequisites = sorted(all_prerequisites.values(), key=lambda p: p.merged_at)
    
    return files, prerequisites, len(all_prerequisites)


def _format_human_output(
    file_path: str | None,
    pr_number: int | None,
    pr_title: str | None,
    target_branch: str,
    files_analyzed: list[str] | None,
    prerequisites: list[PrerequisitePR],
    total_count: int
) -> str:
    """Format human-readable output."""
    lines = []
    
    # Header
    lines.append("=== PR Dependency Analysis ===")
    lines.append("")
    
    if file_path:
        lines.append(f"File analyzed: {file_path}")
    elif pr_number:
        lines.append(f"PR analyzed: #{pr_number}")
        if pr_title:
            lines.append(f"PR title: {pr_title}")
    
    lines.append(f"Target branch: {target_branch}")
    lines.append("")
    
    if files_analyzed:
        lines.append(f"Files modified: {len(files_analyzed)}")
        for f in files_analyzed[:5]:  # Show first 5
            lines.append(f"  - {f}")
        if len(files_analyzed) > 5:
            lines.append(f"  ... and {len(files_analyzed) - 5} more")
        lines.append("")
    
    # Prerequisites
    lines.append(f"Total PRs touching {'file' if file_path else 'files'}: {total_count}")
    
    missing = [p for p in prerequisites if p.status == "missing_from_target"]
    in_target = [p for p in prerequisites if p.status == "in_target"]
    open_cp = [p for p in prerequisites if p.status == "open_cherry_pick"]
    
    lines.append(f"  - Missing from target: {len(missing)}")
    lines.append(f"  - Already backported: {len(in_target)}")
    lines.append(f"  - Pending backport: {len(open_cp)}")
    lines.append("")
    
    if missing or open_cp:
        lines.append("Prerequisites:")
        for prereq in prerequisites:
            if prereq.status in ("missing_from_target", "open_cherry_pick"):
                lines.append(f"  PR #{prereq.pr_number}: {prereq.title}")
                lines.append(f"    Status: {prereq.status}")
                lines.append(f"    Reason: {prereq.reason}")
                if prereq.recommendation:
                    lines.append(f"    Action: {prereq.recommendation}")
                lines.append("")
    
    # Summary
    if missing:
        backport_order = [str(p.pr_number) for p in missing]
        lines.append(f"Suggested backport order: {' → #'.join(['#' + backport_order[0]] + backport_order[1:])}")
    else:
        lines.append("No missing prerequisites - safe to backport!")
    
    return "\n".join(lines)


def _format_json_output(
    file_path: str | None,
    pr_number: int | None,
    pr_title: str | None,
    target_branch: str,
    files_analyzed: list[str] | None,
    prerequisites: list[PrerequisitePR],
    total_count: int
) -> str:
    """Format JSON output."""
    output = {
        "analysis": {
            "targetBranch": target_branch,
        },
        "prerequisites": [
            {
                "prNumber": p.pr_number,
                "title": p.title,
                "mergedAt": p.merged_at,
                "status": p.status,
                "reason": p.reason,
                "recommendation": p.recommendation,
                **({"openCherryPickPR": p.open_cherry_pick_pr} if p.open_cherry_pick_pr else {})
            }
            for p in prerequisites
        ],
        "summary": {
            "totalPRsTouchingFile": total_count,
            "missingFromTarget": len([p for p in prerequisites if p.status == "missing_from_target"]),
            "alreadyBackported": len([p for p in prerequisites if p.status == "in_target"]),
            "pendingBackport": len([p for p in prerequisites if p.status == "open_cherry_pick"]),
            "backportOrder": [p.pr_number for p in prerequisites if p.status == "missing_from_target"],
        }
    }
    
    if file_path:
        output["analysis"]["fileAnalyzed"] = file_path
    elif pr_number:
        output["analysis"]["prAnalyzed"] = pr_number
        if pr_title:
            output["analysis"]["prTitle"] = pr_title
    
    if files_analyzed:
        output["filesModified"] = files_analyzed
        output["summary"]["filesAnalyzed"] = len(files_analyzed)
    
    if output["summary"]["backportOrder"]:
        order_str = " → #".join(['#' + str(n) for n in output["summary"]["backportOrder"]])
        output["summary"]["message"] = f"Backport in order: {order_str} to avoid conflicts"
    
    return json.dumps(output, indent=2)


def main() -> int:
    """Main entry point."""
    args = _parse_args()
    
    # Validate arguments
    if not validate_branch_name(args.target):
        print(
            format_error(f"Branch must match pattern 'release/X.Y.Z' or 'staging/X.Y.Z', got: '{args.target}'"),
            file=sys.stderr
        )
        return 2
    
    if args.pr and not validate_pr_number(str(args.pr)):
        print(format_error(f"Invalid PR number: {args.pr}"), file=sys.stderr)
        return 2
    
    # Perform analysis
    try:
        if args.file:
            prerequisites, total_count = _analyze_file(
                args.file,
                args.target,
                args.merged_after,
                args.repo
            )
            
            if args.json:
                print(_format_json_output(
                    args.file, None, None, args.target, None, prerequisites, total_count
                ))
            else:
                print(_format_human_output(
                    args.file, None, None, args.target, None, prerequisites, total_count
                ))
        
        else:  # args.pr
            files, prerequisites, total_count = _analyze_pr(
                args.pr,
                args.target,
                args.repo
            )
            
            pr_data = gh_pr_view(args.pr, args.repo)
            pr_title = pr_data.get('title', '') if pr_data else None
            
            if args.json:
                print(_format_json_output(
                    None, args.pr, pr_title, args.target, files, prerequisites, total_count
                ))
            else:
                print(_format_human_output(
                    None, args.pr, pr_title, args.target, files, prerequisites, total_count
                ))
        
        return 0
    
    except KeyboardInterrupt:
        print("\nAborted by user", file=sys.stderr)
        return 130


if __name__ == '__main__':
    sys.exit(main())
