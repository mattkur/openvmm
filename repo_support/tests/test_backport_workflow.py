# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from __future__ import annotations

import json

import pytest

from repo_support import backport_workflow


def test_extract_version():
    """Test version extraction from branch names."""
    assert backport_workflow._extract_version("release/1.7.2511") == "1.7.2511"
    assert backport_workflow._extract_version("staging/1.7.2511") == "1.7.2511"
    assert backport_workflow._extract_version("main") == "main"


def test_workflow_invalid_branch(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Test workflow with invalid branch name."""
    monkeypatch.setattr(
        backport_workflow.sys,
        "argv",
        ["backport_workflow.py", "invalid-branch"]
    )
    
    code = backport_workflow.main()
    assert code == 2
    stderr = capsys.readouterr().err
    assert "Branch must match" in stderr


def test_workflow_dry_run(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Test T082: Dry-run mode with no side effects."""
    monkeypatch.setattr(
        backport_workflow.sys,
        "argv",
        ["backport_workflow.py", "release/1.7.2511", "--dry-run"]
    )
    
    code = backport_workflow.main()
    output = capsys.readouterr().out
    
    assert code == 1  # No PRs to process in dry-run
    assert "[DRY RUN]" in output
    assert "Would create cherry-pick PRs" in output


def test_finalize_mode_sequencing(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Test T081: Finalize mode automatic execution."""
    # Mock subprocess calls
    call_sequence = []
    
    def fake_subprocess_run(cmd, capture_output=False, text=False, check=False, **kwargs):
        call_sequence.append(cmd[2] if len(cmd) > 2 else cmd[0])
        
        # Mock gen_cherrypick_prs output
        if 'gen_cherrypick_prs' in str(cmd):
            mock_output = json.dumps({
                "results": [
                    {
                        "pr_number": 2680,
                        "status": "success",
                        "cherry_pick_pr": 2800
                    }
                ]
            })
            return type('obj', (object,), {
                'returncode': 0,
                'stdout': mock_output,
                'stderr': ''
            })
        
        # Mock relabel_backported output
        elif 'relabel_backported' in str(cmd):
            return type('obj', (object,), {
                'returncode': 0,
                'stdout': 'Updated 1 PR',
                'stderr': ''
            })
        
        return type('obj', (object,), {'returncode': 0, 'stdout': '', 'stderr': ''})
    
    def fake_check_pr_status(pr_number, repo):
        return {"state": "MERGED", "mergedAt": "2026-02-07T00:00:00Z"}
    
    monkeypatch.setattr(backport_workflow.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(backport_workflow, "_check_pr_merge_status", fake_check_pr_status)
    
    monkeypatch.setattr(
        backport_workflow.sys,
        "argv",
        ["backport_workflow.py", "release/1.7.2511", "--finalize"]
    )
    
    code = backport_workflow.main()
    output = capsys.readouterr().out
    
    assert code == 0
    assert "gen_cherrypick_prs" in call_sequence
    assert "relabel_backported" in call_sequence
    # Verify sequencing: cherry-pick before relabel
    gen_index = next(i for i, cmd in enumerate(call_sequence) if 'gen_cherrypick_prs' in cmd)
    relabel_index = next(i for i, cmd in enumerate(call_sequence) if 'relabel_backported' in cmd)
    assert gen_index < relabel_index


def test_complete_workflow_success(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Test T080: Complete workflow with successful PRs."""
    def fake_subprocess_run(cmd, capture_output=False, text=False, check=False, **kwargs):
        if 'gen_cherrypick_prs' in str(cmd):
            mock_output = json.dumps({
                "results": [
                    {
                        "pr_number": 2680,
                        "status": "success",
                        "cherry_pick_pr": 2800
                    },
                    {
                        "pr_number": 2681,
                        "status": "success",
                        "cherry_pick_pr": 2801
                    }
                ]
            })
            return type('obj', (object,), {
                'returncode': 0,
                'stdout': mock_output,
                'stderr': ''
            })
        
        elif 'relabel_backported' in str(cmd):
            return type('obj', (object,), {
                'returncode': 0,
                'stdout': 'Updated 2 PRs',
                'stderr': ''
            })
        
        return type('obj', (object,), {'returncode': 0, 'stdout': '', 'stderr': ''})
    
    def fake_check_pr_status(pr_number, repo):
        return {"state": "MERGED", "mergedAt": "2026-02-07T00:00:00Z"}
    
    monkeypatch.setattr(backport_workflow.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(backport_workflow, "_check_pr_merge_status", fake_check_pr_status)
    
    monkeypatch.setattr(
        backport_workflow.sys,
        "argv",
        ["backport_workflow.py", "release/1.7.2511", "--finalize"]
    )
    
    code = backport_workflow.main()
    output = capsys.readouterr().out
    
    assert code == 0
    assert "Successful: 2" in output
    assert "Conflicts: 0" in output


def test_workflow_with_conflicts(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Test workflow handling conflicts properly."""
    def fake_subprocess_run(cmd, capture_output=False, text=False, check=False, **kwargs):
        if 'gen_cherrypick_prs' in str(cmd):
            mock_output = json.dumps({
                "results": [
                    {
                        "pr_number": 2680,
                        "status": "success",
                        "cherry_pick_pr": 2800
                    },
                    {
                        "pr_number": 2525,
                        "status": "conflict",
                        "worktree": ".git/worktrees/backport-temp-12345/",
                        "conflicted_files": ["src/foo.rs"]
                    }
                ]
            })
            return type('obj', (object,), {
                'returncode': 3,  # Conflicts detected
                'stdout': mock_output,
                'stderr': ''
            })
        
        return type('obj', (object,), {'returncode': 0, 'stdout': '', 'stderr': ''})
    
    def fake_check_pr_status(pr_number, repo):
        return {"state": "MERGED", "mergedAt": "2026-02-07T00:00:00Z"}
    
    monkeypatch.setattr(backport_workflow.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(backport_workflow, "_check_pr_merge_status", fake_check_pr_status)
    
    monkeypatch.setattr(
        backport_workflow.sys,
        "argv",
        ["backport_workflow.py", "release/1.7.2511", "--finalize"]
    )
    
    code = backport_workflow.main()
    output = capsys.readouterr().out
    
    assert code == 1  # Success with conflicts
    assert "Conflicts: 1" in output
    assert "2525" in output
    assert "analyze-pr-deps" in output.lower()


def test_skip_relabel_flag(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Test --skip-relabel flag behavior."""
    call_sequence = []
    
    def fake_subprocess_run(cmd, capture_output=False, text=False, check=False, **kwargs):
        call_sequence.append(str(cmd))
        
        if 'gen_cherrypick_prs' in str(cmd):
            mock_output = json.dumps({
                "results": [
                    {
                        "pr_number": 2680,
                        "status": "success",
                        "cherry_pick_pr": 2800
                    }
                ]
            })
            return type('obj', (object,), {
                'returncode': 0,
                'stdout': mock_output,
                'stderr': ''
            })
        
        return type('obj', (object,), {'returncode': 0, 'stdout': '', 'stderr': ''})
    
    def fake_check_pr_status(pr_number, repo):
        return {"state": "MERGED", "mergedAt": "2026-02-07T00:00:00Z"}
    
    monkeypatch.setattr(backport_workflow.subprocess, "run", fake_subprocess_run)
    monkeypatch.setattr(backport_workflow, "_check_pr_merge_status", fake_check_pr_status)
    
    monkeypatch.setattr(
        backport_workflow.sys,
        "argv",
        ["backport_workflow.py", "release/1.7.2511", "--finalize", "--skip-relabel"]
    )
    
    code = backport_workflow.main()
    output = capsys.readouterr().out
    
    assert code == 0
    assert "Skipping relabel phase" in output
    # Verify relabel_backported was NOT called
    assert not any('relabel_backported' in call for call in call_sequence)
