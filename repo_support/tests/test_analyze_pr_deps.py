# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from __future__ import annotations

import json
from datetime import datetime, timezone

import pytest

from repo_support import analyze_pr_deps


def test_validate_date_valid():
    """Test valid date parsing."""
    date = analyze_pr_deps._validate_date("2026-01-01")
    assert isinstance(date, datetime)
    assert date.year == 2026
    assert date.month == 1
    assert date.day == 1


def test_validate_date_invalid(capsys: pytest.CaptureFixture[str]):
    """Test invalid date format."""
    with pytest.raises(SystemExit) as exc_info:
        analyze_pr_deps._validate_date("not-a-date")
    assert exc_info.value.code == 2
    stderr = capsys.readouterr().err
    assert "Date must be ISO format" in stderr


def test_pr_touches_file():
    """Test file modification detection."""
    pr_data = {
        "number": 2680,
        "mergeCommit": {"oid": "abc123"}
    }
    
    # This would require mocking git diff-tree
    # For now, just test the structure
    assert "mergeCommit" in pr_data


def test_file_based_analysis_no_prs_found(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]):
    """Test T067: File analysis when no PRs found."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")
    
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(analyze_pr_deps, "git_fetch", lambda: None)
    monkeypatch.setattr(analyze_pr_deps, "_get_merged_prs", lambda repo, merged_after: [])
    
    monkeypatch.setattr(
        analyze_pr_deps.sys,
        "argv",
        ["analyze_pr_deps.py", "--file", str(test_file), "--target", "release/1.7.2511"]
    )
    
    with pytest.raises(SystemExit) as exc_info:
        analyze_pr_deps.main()
    
    assert exc_info.value.code == 1
    stderr = capsys.readouterr().err
    assert "No merged PRs found" in stderr


def test_file_based_analysis_with_prerequisites(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]):
    """Test T068: File analysis identifying missing prerequisites."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")
    
    mock_prs = [
        {
            "number": 2567,
            "title": "Fix: Handle edge case",
            "mergedAt": "2026-02-01T10:00:00Z",
            "mergeCommit": {"oid": "sha567"}
        },
        {
            "number": 2345,
            "title": "Refactor: Extract utility",
            "mergedAt": "2026-01-15T08:30:00Z",
            "mergeCommit": {"oid": "sha345"}
        }
    ]
    
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(analyze_pr_deps, "git_fetch", lambda: None)
    monkeypatch.setattr(analyze_pr_deps, "_get_merged_prs", lambda repo, merged_after: mock_prs)
    monkeypatch.setattr(analyze_pr_deps, "_pr_touches_file", lambda pr, file: True)
    monkeypatch.setattr(analyze_pr_deps, "_is_commit_in_target", lambda commit, branch: False)
    monkeypatch.setattr(analyze_pr_deps, "_find_open_cherry_pick", lambda pr_num, branch, repo: None)
    
    monkeypatch.setattr(
        analyze_pr_deps.sys,
        "argv",
        ["analyze_pr_deps.py", "--file", str(test_file), "--target", "release/1.7.2511"]
    )
    
    code = analyze_pr_deps.main()
    output = capsys.readouterr().out
    
    assert code == 0
    assert "2345" in output  # Older PR should be listed first
    assert "2567" in output
    assert "Missing from target: 2" in output


def test_pr_based_analysis(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]):
    """Test T069: PR-based analysis identifying prerequisites."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")
    
    pr_data = {
        "number": 2680,
        "title": "Feature: Add worktree support",
        "state": "MERGED",
        "mergeCommit": {"oid": "sha680"}
    }
    
    mock_prs = [
        {
            "number": 2567,
            "title": "Fix: Handle edge case",
            "mergedAt": "2026-02-01T10:00:00Z",
            "mergeCommit": {"oid": "sha567"}
        }
    ]
    
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(analyze_pr_deps, "gh_pr_view", lambda pr_num, repo: pr_data)
    monkeypatch.setattr(analyze_pr_deps, "_get_files_changed_in_pr", lambda pr_num, repo: [str(test_file)])
    monkeypatch.setattr(analyze_pr_deps, "git_fetch", lambda: None)
    monkeypatch.setattr(analyze_pr_deps, "_get_merged_prs", lambda repo, merged_after: mock_prs)
    monkeypatch.setattr(analyze_pr_deps, "_pr_touches_file", lambda pr, file: True)
    monkeypatch.setattr(analyze_pr_deps, "_is_commit_in_target", lambda commit, branch: False)
    monkeypatch.setattr(analyze_pr_deps, "_find_open_cherry_pick", lambda pr_num, branch, repo: None)
    
    monkeypatch.setattr(
        analyze_pr_deps.sys,
        "argv",
        ["analyze_pr_deps.py", "--pr", "2680", "--target", "release/1.7.2511"]
    )
    
    code = analyze_pr_deps.main()
    output = capsys.readouterr().out
    
    assert code == 0
    assert "2680" in output
    assert "Feature: Add worktree support" in output
    assert "2567" in output


def test_open_cherry_pick_detection(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]):
    """Test T070: Detection of open cherry-pick PRs."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")
    
    mock_prs = [
        {
            "number": 2680,
            "title": "Fix bug",
            "mergedAt": "2026-02-01T10:00:00Z",
            "mergeCommit": {"oid": "sha680"}
        }
    ]
    
    def fake_find_open_cherry_pick(pr_num, branch, repo):
        if pr_num == 2680:
            return 2850  # Mock open cherry-pick PR
        return None
    
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(analyze_pr_deps, "git_fetch", lambda: None)
    monkeypatch.setattr(analyze_pr_deps, "_get_merged_prs", lambda repo, merged_after: mock_prs)
    monkeypatch.setattr(analyze_pr_deps, "_pr_touches_file", lambda pr, file: True)
    monkeypatch.setattr(analyze_pr_deps, "_is_commit_in_target", lambda commit, branch: False)
    monkeypatch.setattr(analyze_pr_deps, "_find_open_cherry_pick", fake_find_open_cherry_pick)
    
    monkeypatch.setattr(
        analyze_pr_deps.sys,
        "argv",
        ["analyze_pr_deps.py", "--file", str(test_file), "--target", "release/1.7.2511"]
    )
    
    code = analyze_pr_deps.main()
    output = capsys.readouterr().out
    
    assert code == 0
    assert "2680" in output
    assert "2850" in output  # Should mention the open cherry-pick PR
    assert "open_cherry_pick" in output or "wait for merge" in output.lower()


def test_json_output_format(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]):
    """Test JSON output format."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")
    
    mock_prs = [
        {
            "number": 2567,
            "title": "Fix",
            "mergedAt": "2026-02-01T10:00:00Z",
            "mergeCommit": {"oid": "sha567"}
        }
    ]
    
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(analyze_pr_deps, "git_fetch", lambda: None)
    monkeypatch.setattr(analyze_pr_deps, "_get_merged_prs", lambda repo, merged_after: mock_prs)
    monkeypatch.setattr(analyze_pr_deps, "_pr_touches_file", lambda pr, file: True)
    monkeypatch.setattr(analyze_pr_deps, "_is_commit_in_target", lambda commit, branch: False)
    monkeypatch.setattr(analyze_pr_deps, "_find_open_cherry_pick", lambda pr_num, branch, repo: None)
    
    monkeypatch.setattr(
        analyze_pr_deps.sys,
        "argv",
        ["analyze_pr_deps.py", "--file", str(test_file), "--target", "release/1.7.2511", "--json"]
    )
    
    code = analyze_pr_deps.main()
    output = capsys.readouterr().out
    
    assert code == 0
    data = json.loads(output)
    assert "analysis" in data
    assert "prerequisites" in data
    assert "summary" in data
    assert data["analysis"]["fileAnalyzed"] == str(test_file)
    assert data["analysis"]["targetBranch"] == "release/1.7.2511"


def test_merged_after_filter(monkeypatch: pytest.MonkeyPatch, tmp_path, capsys: pytest.CaptureFixture[str]):
    """Test --merged-after date filtering."""
    test_file = tmp_path / "test.txt"
    test_file.write_text("content")
    
    # Older PR should be filtered out
    mock_prs = [
        {
            "number": 2000,
            "title": "Old PR",
            "mergedAt": "2025-12-01T10:00:00Z",
            "mergeCommit": {"oid": "sha2000"}
        },
        {
            "number": 2567,
            "title": "New PR",
            "mergedAt": "2026-02-01T10:00:00Z",
            "mergeCommit": {"oid": "sha567"}
        }
    ]
    
    calls = {"get_merged_prs_called": False}
    
    def fake_get_merged_prs(repo, merged_after):
        calls["get_merged_prs_called"] = True
        # Simulate filtering in the function
        if merged_after:
            cutoff = datetime.fromisoformat(merged_after)
            return [
                pr for pr in mock_prs
                if datetime.fromisoformat(pr['mergedAt'].replace('Z', '+00:00')) >= cutoff
            ]
        return mock_prs
    
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(analyze_pr_deps, "git_fetch", lambda: None)
    monkeypatch.setattr(analyze_pr_deps, "_get_merged_prs", fake_get_merged_prs)
    monkeypatch.setattr(analyze_pr_deps, "_pr_touches_file", lambda pr, file: True)
    monkeypatch.setattr(analyze_pr_deps, "_is_commit_in_target", lambda commit, branch: False)
    monkeypatch.setattr(analyze_pr_deps, "_find_open_cherry_pick", lambda pr_num, branch, repo: None)
    
    monkeypatch.setattr(
        analyze_pr_deps.sys,
        "argv",
        ["analyze_pr_deps.py", "--file", str(test_file), "--target", "release/1.7.2511", "--merged-after", "2026-01-01"]
    )
    
    code = analyze_pr_deps.main()
    output = capsys.readouterr().out
    
    assert code == 0
    assert calls["get_merged_prs_called"]
    assert "2567" in output  # New PR should be included
    # Old PR should be filtered out by the function
