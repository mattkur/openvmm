# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from repo_support import backport_status


@dataclass
class DummyCompleted:
    stdout: str
    stderr: str
    returncode: int


def test_extract_original_pr_number_title():
    num = backport_status._extract_original_pr_number(
        "Fix bug (cherry-pick from #2680)", ""
    )
    assert num == 2680


def test_extract_original_pr_number_body():
    num = backport_status._extract_original_pr_number(
        "", "Cherry picked from #123"
    )
    assert num == 123


def test_formatters_output():
    pending = [backport_status.PullRequest(1, "Pending", "https://example/p/1")]
    completed = [backport_status.PullRequest(2, "Done", "https://example/p/2")]
    in_progress = [
        backport_status.CherryPickPR(3, "CP", "https://example/p/3", "release/1.7.2511", 1)
    ]
    conflicts = []

    summary = backport_status._format_summary("1.7.2511", ["release/1.7.2511"], pending, completed, in_progress, conflicts)
    assert "Pending backports: 1" in summary

    table = backport_status._format_table(pending, completed, in_progress, conflicts)
    assert "pending" in table

    detailed = backport_status._format_detailed(pending, completed, in_progress, conflicts)
    assert "Pending backports" in detailed

    data = json.loads(
        backport_status._format_json("1.7.2511", ["release/1.7.2511"], pending, completed, in_progress, conflicts)
    )
    assert data["pending"][0]["number"] == 1


def test_main_invalid_version(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setattr(backport_status.sys, "argv", ["backport_status.py", "bad-version"])
    code = backport_status.main()
    assert code == 2
    assert "Invalid version" in capsys.readouterr().err


def test_main_filters_pr(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setattr(backport_status, "_list_backport_prs", lambda label, repo: [
        backport_status.PullRequest(2680, "A", "u"),
        backport_status.PullRequest(2681, "B", "u"),
    ])
    monkeypatch.setattr(backport_status, "_list_open_cherrypicks", lambda branch, repo: [
        backport_status.CherryPickPR(3000, "CP", "u", branch, 2680)
    ])
    monkeypatch.setattr(backport_status, "_find_conflict_worktrees", lambda repo_root: [])

    monkeypatch.setattr(
        backport_status.sys,
        "argv",
        ["backport_status.py", "1.7.2511", "--pr", "2680"],
    )
    code = backport_status.main()
    output = capsys.readouterr().out
    assert code == 0
    assert "Pending backports: 1" in output


def test_integration_output_formats(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    responses = {
        "backport": [{"number": 2680, "title": "Fix", "url": "u"}],
        "backported": [{"number": 2681, "title": "Done", "url": "u"}],
        "open": [
            {
                "number": 3000,
                "title": "Fix (cherry-pick from #2680)",
                "url": "u",
                "body": "",
            }
        ],
    }

    def fake_run(cmd, stdout, stderr, text, check):
        cmd_str = " ".join(cmd)
        if "--label backport_1.7.2511" in cmd_str:
            payload = responses["backport"]
        elif "--label backported_1.7.2511" in cmd_str:
            payload = responses["backported"]
        elif "--state open" in cmd_str:
            payload = responses["open"]
        else:
            payload = []
        return DummyCompleted(stdout=json.dumps(payload), stderr="", returncode=0)

    monkeypatch.setattr(backport_status.subprocess, "run", fake_run)
    monkeypatch.setattr(backport_status, "_find_conflict_worktrees", lambda repo_root: [])

    for fmt in ("summary", "table", "json", "detailed"):
        monkeypatch.setattr(
            backport_status.sys,
            "argv",
            ["backport_status.py", "1.7.2511", "--format", fmt, "--branch", "release/1.7.2511"],
        )
        code = backport_status.main()
        assert code == 0
        output = capsys.readouterr().out
        assert output


def test_staging_branch_status(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Test T057: Integration test for staging branch status display"""
    responses = {
        "backport": [{"number": 2680, "title": "Fix", "url": "u"}],
        "backported": [{"number": 2681, "title": "Done", "url": "u"}],
        "open": [
            {
                "number": 3000,
                "title": "Fix (cherry-pick from #2680)",
                "url": "u",
                "body": "",
            }
        ],
    }

    def fake_run(cmd, stdout, stderr, text, check):
        cmd_str = " ".join(cmd)
        if "--label backport_1.7.2511" in cmd_str:
            payload = responses["backport"]
        elif "--label backported_1.7.2511" in cmd_str:
            payload = responses["backported"]
        elif "--state open" in cmd_str and "staging/1.7.2511" in cmd_str:
            payload = responses["open"]
        else:
            payload = []
        return DummyCompleted(stdout=json.dumps(payload), stderr="", returncode=0)

    monkeypatch.setattr(backport_status.subprocess, "run", fake_run)
    monkeypatch.setattr(backport_status, "_find_conflict_worktrees", lambda repo_root: [])

    monkeypatch.setattr(
        backport_status.sys,
        "argv",
        ["backport_status.py", "1.7.2511", "--branch", "staging/1.7.2511"],
    )
    code = backport_status.main()
    assert code == 0
    output = capsys.readouterr().out
    assert "staging/1.7.2511" in output
    assert "Pending backports: 1" in output
