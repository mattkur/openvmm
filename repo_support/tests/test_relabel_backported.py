# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from __future__ import annotations

import pytest

from repo_support import relabel_backported


def test_parse_force_update_prs():
    values = relabel_backported._parse_force_update_prs(["2680,2567", "3000"])
    assert values == {2680, 2567, 3000}


def test_title_matches_commit():
    commit_line = "abc123 Fix bug in parser (#2680)"
    assert relabel_backported._title_matches_commit("Fix bug in parser", commit_line)
    assert not relabel_backported._title_matches_commit("Different title", commit_line)


def test_main_warns_on_title_mismatch(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setattr(
        relabel_backported,
        "_gh_pr_list",
        lambda label, repo: [{"number": 2680, "title": "Fix bug", "url": "u", "state": "MERGED"}],
    )
    monkeypatch.setattr(
        relabel_backported,
        "_git_log_for_pr",
        lambda version, pr_number, title: ["abc123 Different title (#3000)"]
    )

    monkeypatch.setattr(
        relabel_backported.sys,
        "argv",
        ["relabel_backported.py", "1.7.2511"],
    )

    code = relabel_backported.main()
    output = capsys.readouterr().out
    assert code == 1
    assert "warn_title_mismatch" in output


def test_main_update_calls(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setattr(
        relabel_backported,
        "_gh_pr_list",
        lambda label, repo: [{"number": 2680, "title": "Fix bug", "url": "u", "state": "MERGED"}],
    )
    monkeypatch.setattr(
        relabel_backported,
        "_git_log_for_pr",
        lambda version, pr_number, title: ["abc123 Fix bug (#3000)"]
    )

    calls = {"comment": 0, "edit": 0}

    def fake_comment(pr_number, body, repo):
        calls["comment"] += 1

    def fake_edit(pr_number, add_label, remove_label, repo):
        calls["edit"] += 1

    monkeypatch.setattr(relabel_backported, "_gh_pr_comment", fake_comment)
    monkeypatch.setattr(relabel_backported, "_gh_pr_edit", fake_edit)

    monkeypatch.setattr(
        relabel_backported.sys,
        "argv",
        ["relabel_backported.py", "1.7.2511", "--update"],
    )

    code = relabel_backported.main()
    output = capsys.readouterr().out
    assert code == 0
    assert calls["comment"] == 1
    assert calls["edit"] == 1
    assert "dryRun: false" in output


def test_main_skips_open_pr(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    monkeypatch.setattr(
        relabel_backported,
        "_gh_pr_list",
        lambda label, repo: [{"number": 1111, "title": "Open", "url": "u", "state": "OPEN"}],
    )

    monkeypatch.setattr(
        relabel_backported.sys,
        "argv",
        ["relabel_backported.py", "1.7.2511"],
    )

    code = relabel_backported.main()
    output = capsys.readouterr().out
    assert code == 0
    assert "skip" in output


def test_staging_branch_relabeling(monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]):
    """Test T056: Integration test for staging branch relabeling"""
    monkeypatch.setattr(
        relabel_backported,
        "_gh_pr_list",
        lambda label, repo: [{"number": 2680, "title": "Fix bug", "url": "u", "state": "MERGED"}],
    )
    monkeypatch.setattr(
        relabel_backported,
        "_git_log_for_pr",
        lambda version, pr_number, title: ["abc123 Fix bug (#3000)"]
    )

    calls = {"comment": 0, "edit": 0}

    def fake_comment(pr_number, body, repo):
        calls["comment"] += 1
        assert "staging/1.7.2511" in body

    def fake_edit(pr_number, add_label, remove_label, repo):
        calls["edit"] += 1
        assert add_label == "backported_1.7.2511"
        assert remove_label == "backport_1.7.2511"

    monkeypatch.setattr(relabel_backported, "_gh_pr_comment", fake_comment)
    monkeypatch.setattr(relabel_backported, "_gh_pr_edit", fake_edit)

    monkeypatch.setattr(
        relabel_backported.sys,
        "argv",
        ["relabel_backported.py", "1.7.2511", "--update", "--branch", "staging/1.7.2511"],
    )

    code = relabel_backported.main()
    output = capsys.readouterr().out
    assert code == 0
    assert calls["comment"] == 1
    assert calls["edit"] == 1
