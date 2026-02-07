#!/usr/bin/env python3

# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

"""
Unified backport workflow orchestrator.

Guides maintainers through the complete backport workflow:
1. Create cherry-pick PRs
2. Monitor merge status
3. Relabel completed backports

Usage:
    # Interactive mode (step-by-step)
    backport_workflow.py release/1.7.2511
    
    # Automatic mode (finalize all steps)
    backport_workflow.py release/1.7.2511 --finalize
    
    # Create cherry-picks but skip relabeling
    backport_workflow.py release/1.7.2511 --skip-relabel
    
    # Dry run (show what would happen)
    backport_workflow.py release/1.7.2511 --dry-run

Return codes:
    0: Workflow complete
    1: Workflow aborted by user or waiting for merges
    2: Invalid arguments
    3: GitHub API or git error
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
import time
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from shared_utils import format_error, validate_branch_name, git_branch_exists, git_fetch, git_get_upstream_remote


@dataclass
class CherryPickResult:
    """Result of a cherry-pick operation."""
    pr_number: int
    status: str  # "success", "conflict", "skipped"
    cherrypick_pr: int | None = None
    worktree: str | None = None
    error_msg: str | None = None


@dataclass
class WorkflowState:
    """Tracks the current state of the workflow."""
    target_branch: str
    version: str
    cherrypick_results: list[CherryPickResult]
    start_time: datetime
    finalize_mode: bool
    skip_relabel: bool
    dry_run: bool


def _parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(
        description="Unified backport workflow orchestrator",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    
    parser.add_argument(
        'target_branch',
        type=str,
        help='Target branch for backport (e.g., release/1.7.2511)'
    )
    parser.add_argument(
        '--finalize',
        action='store_true',
        help='Run complete workflow end-to-end without prompts'
    )
    parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Show what would be done without making changes'
    )
    parser.add_argument(
        '--skip-relabel',
        action='store_true',
        help='Create cherry-pick PRs but skip relabeling'
    )
    parser.add_argument(
        '--repo',
        type=str,
        help='Repository in OWNER/REPO format (default: current repo)'
    )
    
    return parser.parse_args()


def _extract_version(branch: str) -> str:
    """Extract version from branch name."""
    # release/1.7.2511 -> 1.7.2511
    # staging/1.7.2511 -> 1.7.2511
    parts = branch.split('/')
    if len(parts) >= 2:
        return parts[1]
    return branch


def _print_header(title: str):
    """Print a formatted section header."""
    print()
    print("═" * 70)
    print(f"  {title}")
    print("═" * 70)
    print()


def _print_section(title: str):
    """Print a formatted subsection."""
    print()
    print(title)
    print("─" * 70)
    print()


def _run_cherrypick_phase(state: WorkflowState, repo: str | None, remote: str) -> bool:
    """Phase 1: Create cherry-pick PRs."""
    _print_section(f"Step 1: Create Cherry-Pick PRs for {state.target_branch}")
    
    if state.dry_run:
        print(f"[DRY RUN] Would create cherry-pick PRs from label backport_{state.version}")
        print("[DRY RUN] No PRs will be created")
        return True
    
    # Call gen_cherrypick_prs.py
    print(f"Discovering PRs labeled 'backport_{state.version}' and creating cherry-picks...")
    print("This may take a moment...\n")
    
    cmd = [
        'python3', '-m', 'repo_support.gen_cherrypick_prs',
        state.target_branch,
        '--from-backport-label',
        '--no-confirm',
        '--remote',
        remote
    ]
    if repo:
        cmd.extend(['--repo', repo])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=False
        )
        
        if result.returncode not in (0, 3):  # 0=success, 3=conflicts
            print(format_error(f"Cherry-pick tool failed: {result.stderr}"), file=sys.stderr)
            return False
        
        # Parse output (YAML-like format)
        output = result.stdout
        stderr_output = result.stderr
        
        # Display stderr (conflict messages) first if present
        if stderr_output:
            print(stderr_output, file=sys.stderr)
        
        # Display the summary
        print(output)
        
        # Parse the YAML-like output to extract PR information
        # Format: results:\n  -\n    pr: 2680\n    status: conflict\n    ...
        
        in_results = False
        current_pr = None
        current_status = None
        current_worktree = None
        
        for line in output.split('\n'):
            if line.strip() == 'results:':
                in_results = True
                continue
            
            if in_results:
                # Check for a new result entry (starts with "  -")
                if line.startswith('  -'):
                    # Save previous PR if exists
                    if current_pr is not None:
                        state.cherrypick_results.append(CherryPickResult(
                            pr_number=current_pr,
                            status=current_status or 'unknown',
                            worktree=current_worktree
                        ))
                    # Reset for new entry
                    current_pr = None
                    current_status = None
                    current_worktree = None
                    continue
                
                # Parse fields
                pr_match = re.match(r'\s+pr:\s*(\d+)', line)
                if pr_match:
                    current_pr = int(pr_match.group(1))
                
                status_match = re.match(r'\s+status:\s*"?(\w+)"?', line)
                if status_match:
                    current_status = status_match.group(1)
                
                worktree_match = re.match(r'\s+worktree:\s*"([^"]*)"', line)
                if worktree_match:
                    worktree_path = worktree_match.group(1)
                    if worktree_path:
                        current_worktree = worktree_path
        
        # Save last PR
        if current_pr is not None:
            state.cherrypick_results.append(CherryPickResult(
                pr_number=current_pr,
                status=current_status or 'unknown',
                worktree=current_worktree
            ))
        
        # Fallback if parsing failed
        if not state.cherrypick_results:
            if result.returncode == 0:
                # Success but no results parsed - assume something worked
                print("Note: Could not parse PR details from output")
                return True
            elif result.returncode == 3:
                print("Note: Could not parse PR details from output")
                state.cherrypick_results.append(CherryPickResult(
                    pr_number=0,
                    status='conflict',
                    worktree='See output above'
                ))
        
        if not state.cherrypick_results:
            print("No PRs to process.")
            return False
        
        print()
        conflicts = [r for r in state.cherrypick_results if r.status == 'conflict']
        if conflicts:
            print(f"⚠ {len(conflicts)} PR(s) have conflicts and need manual resolution")
            print()
        
        return True
    
    except Exception as e:
        print(format_error(f"Failed to run cherry-pick tool: {str(e)}"), file=sys.stderr)
        return False


def _check_pr_merge_status(pr_number: int, repo: str | None) -> dict[str, Any] | None:
    """Check if a PR is merged."""
    try:
        cmd = ['gh', 'pr', 'view', str(pr_number), '--json', 'state,mergedAt,isDraft']
        if repo:
            cmd.extend(['--repo', repo])
        
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        return json.loads(result.stdout)
    except Exception:
        return None


def _monitor_merge_phase(state: WorkflowState, repo: str | None) -> bool:
    """Phase 2: Monitor PR merge status."""
    _print_section("Step 2: Monitor Merge Status")
    
    if state.dry_run:
        print("[DRY RUN] Would monitor merge status of created PRs")
        return True
    
    # Get PRs that were successfully created
    created_prs = [r for r in state.cherrypick_results if r.status == 'success' and r.cherrypick_pr]
    
    if not created_prs:
        print("No cherry-pick PRs were created successfully.")
        return True
    
    if state.finalize_mode:
        print("Monitoring merge status (finalize mode, will auto-continue)...")
        print("Checking every 30 seconds (timeout: 30 minutes)\\n")
        timeout = 30 * 60  # 30 minutes
        start = time.time()
        
        while time.time() - start < timeout:
            all_merged = True
            for result in created_prs:
                pr_status = _check_pr_merge_status(result.cherrypick_pr, repo)
                if pr_status and pr_status.get('state') != 'MERGED':
                    all_merged = False
                    break
            
            if all_merged:
                print("\nAll cherry-pick PRs have been merged!")
                return True
            
            print(".", end="", flush=True)
            time.sleep(30)
        
        print("\n\nTimeout waiting for PRs to merge. Proceeding anyway...")
        return True
    
    else:
        # Interactive mode
        while True:
            print("\nPending cherry-pick PRs:")
            for result in created_prs:
                pr_status = _check_pr_merge_status(result.cherrypick_pr, repo)
                if pr_status:
                    state_str = pr_status.get('state', 'UNKNOWN')
                    merged_at = pr_status.get('mergedAt', '')
                    if state_str == 'MERGED':
                        print(f"  ✓ #{result.cherrypick_pr}: MERGED at {merged_at}")
                    else:
                        print(f"  • #{result.cherrypick_pr}: {state_str}")
                else:
                    print(f"  • #{result.cherrypick_pr}: (checking...)")
            
            print("\nWhat would you like to do?")
            print("  [1] Check PR status again")
            print("  [2] Proceed to relabeling")
            print("  [3] Abort workflow")
            print("  [q] Quit")
            
            choice = input("\nEnter choice: ").strip().lower()
            
            if choice == '1':
                continue
            elif choice == '2':
                return True
            elif choice in ('3', 'q'):
                print("\nWorkflow aborted by user.")
                return False
            else:
                print("Invalid choice. Please try again.")


def _relabel_phase(state: WorkflowState, repo: str | None) -> bool:
    """Phase 3: Relabel backported PRs."""
    if state.skip_relabel:
        print("\nSkipping relabel phase (--skip-relabel flag)")
        return True
    
    _print_section("Step 3: Relabeling Completed Backports")
    
    if state.dry_run:
        print(f"[DRY RUN] Would run relabel_backported.py {state.version} --update")
        return True
    
    print(f"Checking for successfully backported PRs and updating labels...")
    print("This may take a moment...\\n")
    
    # Call relabel_backported.py
    cmd = [
        'python3', '-m', 'repo_support.relabel_backported',
        state.version,
        '--update'
    ]
    if repo:
        cmd.extend(['--repo', repo])
    
    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            check=True
        )
        
        print(result.stdout)
        return True
    
    except subprocess.CalledProcessError as e:
        print(format_error(f"Relabeling failed: {e.stderr}"), file=sys.stderr)
        return False


def _print_summary(state: WorkflowState):
    """Print workflow summary."""
    _print_section("Workflow Summary")
    
    elapsed = datetime.now() - state.start_time
    minutes = int(elapsed.total_seconds() / 60)
    
    successful = [r for r in state.cherrypick_results if r.status == 'success']
    conflicts = [r for r in state.cherrypick_results if r.status == 'conflict']
    skipped = [r for r in state.cherrypick_results if r.status == 'skipped']
    
    print(f"Target branch: {state.target_branch}")
    print(f"Version: {state.version}")
    print(f"Elapsed time: {minutes} minute(s)")
    print()
    print(f"Total PRs processed: {len(state.cherrypick_results)}")
    print(f"  ✓ Successful: {len(successful)}")
    print(f"  ✗ Conflicts: {len(conflicts)}")
    print(f"  ○ Skipped: {len(skipped)}")
    print()
    
    if conflicts:
        print("PRs needing manual resolution:")
        for result in conflicts:
            print(f"  • PR #{result.pr_number}")
            if result.worktree:
                print(f"    Worktree: {result.worktree}")
        print()
        print("Next steps:")
        print("  1. Resolve conflicts in the worktrees listed above")
        print("  2. Run: python3 -m repo_support.analyze_pr_deps --file <file> --target", state.target_branch)
        print("  3. Re-run this workflow for remaining PRs")


def main() -> int:
    """Main entry point."""
    args = _parse_args()
    
    # Validate arguments
    if not validate_branch_name(args.target_branch):
        print(
            format_error(f"Branch must match 'release/X.Y.Z' or 'staging/X.Y.Z', got: '{args.target_branch}'"),
            file=sys.stderr
        )
        return 2
    
    # Detect upstream remote (needed for all code paths)
    upstream = git_get_upstream_remote()
    print(f"Using remote: {upstream}")
    
    # Check if target branch exists (unless dry-run)
    if not args.dry_run:
        print("Checking target branch existence...")
        try:
            git_fetch(upstream)
            if not git_branch_exists(args.target_branch, remote=upstream):
                print(
                    format_error(
                        f"Target branch '{args.target_branch}' does not exist on remote '{upstream}'",
                        details=[
                            f"The branch '{upstream}/{args.target_branch}' was not found",
                            "",
                            "To create it on the remote:",
                            f"  git push {upstream} main:{args.target_branch}",
                            "",
                            "Or create from a specific commit:",
                            f"  git push {upstream} <commit-sha>:refs/heads/{args.target_branch}",
                            "",
                            "Note: You don't need a local copy - the tools work with remote branches directly"
                        ]
                    ),
                    file=sys.stderr
                )
                return 2
        except Exception as e:
            print(format_error(f"Failed to check branch existence: {str(e)}"), file=sys.stderr)
            return 3
        print(f"✓ Target branch '{upstream}/{args.target_branch}' exists\n")
    
    # Initialize workflow state
    version = _extract_version(args.target_branch)
    state = WorkflowState(
        target_branch=args.target_branch,
        version=version,
        cherrypick_results=[],
        start_time=datetime.now(),
        finalize_mode=args.finalize,
        skip_relabel=args.skip_relabel,
        dry_run=args.dry_run
    )
    
    # Print workflow header
    mode = "DRY RUN" if args.dry_run else ("FINALIZE" if args.finalize else "INTERACTIVE")
    _print_header(f"Backport Workflow: {args.target_branch} [{mode}]")
    
    if not args.dry_run:
        print("This workflow will:")
        print(f"  1. Create cherry-pick PRs for all backport_{version} labeled PRs")
        if not args.finalize:
            print("  2. Wait for your confirmation at each step")
        if not args.skip_relabel:
            print("  3. Relabel PRs after cherry-picks are merged")
        print()
    
    # Phase 1: Create cherry-pick PRs
    if not _run_cherrypick_phase(state, args.repo, upstream):
        print("\nWorkflow stopped after cherry-pick phase.")
        return 1
    
    # Phase 2: Monitor merges (if not dry-run)
    if not args.dry_run:
        if not _monitor_merge_phase(state, args.repo):
            print("\nWorkflow aborted during merge monitoring.")
            _print_summary(state)
            return 1
    
    # Phase 3: Relabel (if not dry-run and not skip-relabel)
    if not args.dry_run:
        if not _relabel_phase(state, args.repo):
            print("\nWorkflow failed during relabeling.")
            _print_summary(state)
            return 3
    
    # Print summary
    _print_summary(state)
    
    conflicts = [r for r in state.cherrypick_results if r.status == 'conflict']
    if conflicts:
        return 1  # Success with conflicts
    return 0  # Complete success


if __name__ == '__main__':
    sys.exit(main())
