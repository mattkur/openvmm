# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import pytest

from repo_support import gen_cherrypick_prs


def _mock_pr(number: int, merged_at: str, sha: str) -> dict[str, object]:
    return {
        "number": number,
        "title": f"PR {number}",
        "body": "Body",
        "url": f"https://example/pr/{number}",
        "state": "MERGED",
        "mergedAt": merged_at,
        "mergeCommit": {"oid": sha},
    }


def test_parse_pr_numbers():
    numbers = gen_cherrypick_prs._parse_pr_numbers(["#123", "https://github.com/x/y/pull/456"])
    assert numbers == [123, 456]


def test_worktree_path_generation(tmp_path: Path):
    path = gen_cherrypick_prs._worktree_path(tmp_path, "20260207T120000Z")
    assert path == tmp_path / ".git" / "worktrees" / "backport-temp-20260207T120000Z"


def test_dry_run_sorted_by_merged_at(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    pr1 = _mock_pr(1, "2026-02-01T00:00:00Z", "abc1234")
    pr2 = _mock_pr(2, "2026-02-02T00:00:00Z", "def5678")

    def fake_pr_view(pr_number: int, repo: str | None):
        return pr2 if pr_number == 2 else pr1

    monkeypatch.setattr(gen_cherrypick_prs, "_gh_pr_view", fake_pr_view)
    monkeypatch.setattr(gen_cherrypick_prs, "_git_fetch", lambda remote="origin": None)

    monkeypatch.setattr(
        gen_cherrypick_prs.sys,
        "argv",
        ["gen_cherrypick_prs.py", "release/1.7.2511", "2", "1", "--dry-run"],
    )
    code = gen_cherrypick_prs.main()
    output = capsys.readouterr().out
    assert code == 0
    assert "Would process #1" in output
    assert output.index("Would process #1") < output.index("Would process #2")


def test_duplicate_detection_skips(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    pr = _mock_pr(1, "2026-02-01T00:00:00Z", "abc1234")
    monkeypatch.setattr(gen_cherrypick_prs, "_gh_pr_view", lambda pr_number, repo: pr)
    monkeypatch.setattr(gen_cherrypick_prs, "_git_fetch", lambda remote="origin": None)
    monkeypatch.setattr(gen_cherrypick_prs, "git_merge_base", lambda commit, branch: True)

    monkeypatch.setattr(
        gen_cherrypick_prs.sys,
        "argv",
        ["gen_cherrypick_prs.py", "release/1.7.2511", "1"],
    )
    code = gen_cherrypick_prs.main()
    output = capsys.readouterr().out
    assert code == 0
    assert "skipped" in output


def test_integration_clean_cherrypick(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    pr = _mock_pr(1, "2026-02-01T00:00:00Z", "abc1234")
    repo_root = tmp_path
    (repo_root / ".git" / "worktrees").mkdir(parents=True)

    monkeypatch.setattr(gen_cherrypick_prs, "_gh_pr_view", lambda pr_number, repo: pr)
    monkeypatch.setattr(gen_cherrypick_prs, "_git_fetch", lambda remote="origin": None)
    monkeypatch.setattr(gen_cherrypick_prs, "git_merge_base", lambda commit, branch: False)
    monkeypatch.setattr(gen_cherrypick_prs, "git_worktree_add", lambda path, branch: path.mkdir(parents=True, exist_ok=True))
    monkeypatch.setattr(gen_cherrypick_prs, "_git_checkout_new_branch", lambda path, branch, base: None)
    monkeypatch.setattr(gen_cherrypick_prs, "_git_cherrypick", lambda path, commit: None)
    monkeypatch.setattr(gen_cherrypick_prs, "_git_push", lambda path, branch: None)
    monkeypatch.setattr(gen_cherrypick_prs, "_gh_pr_create", lambda repo, base, head, title, body: "https://example/pr/100")
    monkeypatch.setattr(gen_cherrypick_prs, "git_worktree_remove", lambda path, force=False: None)

    monkeypatch.chdir(repo_root)
    monkeypatch.setattr(
        gen_cherrypick_prs.sys,
        "argv",
        ["gen_cherrypick_prs.py", "release/1.7.2511", "1", "--no-confirm"],
    )
    code = gen_cherrypick_prs.main()
    output = capsys.readouterr().out
    assert code == 0
    assert "cherry_pick_pr" in output


def test_integration_conflict_retains_worktree(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    pr = _mock_pr(1, "2026-02-01T00:00:00Z", "abc1234")
    repo_root = tmp_path
    (repo_root / ".git" / "worktrees").mkdir(parents=True)

    monkeypatch.setattr(gen_cherrypick_prs, "_gh_pr_view", lambda pr_number, repo: pr)
    monkeypatch.setattr(gen_cherrypick_prs, "_git_fetch", lambda remote="origin": None)
    monkeypatch.setattr(gen_cherrypick_prs, "git_merge_base", lambda commit, branch: False)
    monkeypatch.setattr(gen_cherrypick_prs, "git_worktree_add", lambda path, branch: path.mkdir(parents=True, exist_ok=True))
    monkeypatch.setattr(gen_cherrypick_prs, "_git_checkout_new_branch", lambda path, branch, base: None)
    monkeypatch.setattr(gen_cherrypick_prs, "_git_cherrypick", lambda path, commit: (_ for _ in ()).throw(RuntimeError("conflict")))
    monkeypatch.setattr(gen_cherrypick_prs, "_git_conflicted_files", lambda path: ["src/foo.rs"])

    removed = {"called": False}

    def fake_remove(path, force=False):
        removed["called"] = True

    monkeypatch.setattr(gen_cherrypick_prs, "git_worktree_remove", fake_remove)

    monkeypatch.chdir(repo_root)
    monkeypatch.setattr(
        gen_cherrypick_prs.sys,
        "argv",
        ["gen_cherrypick_prs.py", "release/1.7.2511", "1", "--no-confirm"],
    )
    code = gen_cherrypick_prs.main()
    stderr = capsys.readouterr().err
    assert code == 3
    assert "Cherry-pick conflict detected" in stderr
    assert removed["called"] is False


def test_dry_run_no_side_effects(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    pr = _mock_pr(1, "2026-02-01T00:00:00Z", "abc1234")
    monkeypatch.setattr(gen_cherrypick_prs, "_gh_pr_view", lambda pr_number, repo: pr)
    monkeypatch.setattr(gen_cherrypick_prs, "_git_fetch", lambda remote="origin": None)
    monkeypatch.setattr(gen_cherrypick_prs, "git_worktree_add", lambda path, branch: (_ for _ in ()).throw(AssertionError()))

    monkeypatch.setattr(
        gen_cherrypick_prs.sys,
        "argv",
        ["gen_cherrypick_prs.py", "release/1.7.2511", "1", "--dry-run"],
    )
    code = gen_cherrypick_prs.main()
    output = capsys.readouterr().out
    assert code == 0
    assert "--dry-run" in output


def test_staging_branch_cherrypick(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Test T055: Integration test for staging branch cherry-pick"""
    pr = _mock_pr(1, "2026-02-01T00:00:00Z", "abc1234")
    repo_root = tmp_path
    (repo_root / ".git" / "worktrees").mkdir(parents=True)

    monkeypatch.setattr(gen_cherrypick_prs, "_gh_pr_view", lambda pr_number, repo: pr)
    monkeypatch.setattr(gen_cherrypick_prs, "_git_fetch", lambda remote="origin": None)
    monkeypatch.setattr(gen_cherrypick_prs, "git_merge_base", lambda commit, branch: False)
    monkeypatch.setattr(gen_cherrypick_prs, "git_worktree_add", lambda path, branch: path.mkdir(parents=True, exist_ok=True))
    monkeypatch.setattr(gen_cherrypick_prs, "_git_checkout_new_branch", lambda path, branch, base: None)
    monkeypatch.setattr(gen_cherrypick_prs, "_git_cherrypick", lambda path, commit: None)
    monkeypatch.setattr(gen_cherrypick_prs, "_git_push", lambda path, branch: None)
    
    pr_created = {"target": None}
    def fake_pr_create(repo, base, head, title, body):
        pr_created["target"] = base
        return "https://example/pr/100"
    
    monkeypatch.setattr(gen_cherrypick_prs, "_gh_pr_create", fake_pr_create)
    monkeypatch.setattr(gen_cherrypick_prs, "git_worktree_remove", lambda path, force=False: None)

    monkeypatch.chdir(repo_root)
    monkeypatch.setattr(
        gen_cherrypick_prs.sys,
        "argv",
        ["gen_cherrypick_prs.py", "staging/1.7.2511", "1", "--no-confirm"],
    )
    code = gen_cherrypick_prs.main()
    output = capsys.readouterr().out
    assert code == 0
    assert "cherry_pick_pr" in output
    assert pr_created["target"] == "staging/1.7.2511"
