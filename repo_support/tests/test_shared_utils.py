# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from __future__ import annotations

import json
from dataclasses import dataclass

import pytest

from repo_support import shared_utils


@dataclass
class DummyCompleted:
    stdout: str
    stderr: str
    returncode: int


def test_validate_pr_number_valid():
    assert shared_utils.validate_pr_number("123") == 123


def test_validate_pr_number_invalid():
    with pytest.raises(ValueError):
        shared_utils.validate_pr_number("12a")


def test_validate_branch_name_valid():
    assert shared_utils.validate_branch_name("main") == "main"
    assert shared_utils.validate_branch_name("release/1.7.2511") == "release/1.7.2511"
    assert shared_utils.validate_branch_name("staging/2.0.0") == "staging/2.0.0"


def test_validate_branch_name_invalid():
    with pytest.raises(ValueError):
        shared_utils.validate_branch_name("release/")


def test_validate_version_valid():
    assert shared_utils.validate_version("1.7.2511") == "1.7.2511"


def test_validate_version_invalid():
    with pytest.raises(ValueError):
        shared_utils.validate_version("1.7.2511-alpha")


def test_validate_label_valid():
    assert shared_utils.validate_label("backport_1.7.2511") == "backport_1.7.2511"


def test_validate_label_invalid():
    with pytest.raises(ValueError):
        shared_utils.validate_label("bad label")


def test_gh_pr_view_parses_json(monkeypatch: pytest.MonkeyPatch):
    payload = {"number": 123, "title": "Test"}
    captured = {}

    def fake_run(cmd, stdout, stderr, text, check, cwd=None):
        captured["cmd"] = cmd
        return DummyCompleted(stdout=json.dumps(payload), stderr="", returncode=0)

    monkeypatch.setattr(shared_utils.subprocess, "run", fake_run)

    result = shared_utils.gh_pr_view(123, repo="owner/repo")
    assert result == payload
    assert captured["cmd"][0:3] == ["gh", "pr", "view"]
    assert "-R" in captured["cmd"]


def test_gh_pr_list_parses_json(monkeypatch: pytest.MonkeyPatch):
    payload = [{"number": 1}, {"number": 2}]
    captured = {}

    def fake_run(cmd, stdout, stderr, text, check, cwd=None):
        captured["cmd"] = cmd
        return DummyCompleted(stdout=json.dumps(payload), stderr="", returncode=0)

    monkeypatch.setattr(shared_utils.subprocess, "run", fake_run)

    result = shared_utils.gh_pr_list("merged", label="backport_1.7.2511")
    assert result == payload
    assert "--label" in captured["cmd"]


def test_gh_api_query_parses_json(monkeypatch: pytest.MonkeyPatch):
    payload = {"items": []}
    captured = {}

    def fake_run(cmd, stdout, stderr, text, check, cwd=None):
        captured["cmd"] = cmd
        return DummyCompleted(stdout=json.dumps(payload), stderr="", returncode=0)

    monkeypatch.setattr(shared_utils.subprocess, "run", fake_run)

    result = shared_utils.gh_api_query("repos/owner/repo/pulls")
    assert result == payload
    assert captured["cmd"][0:2] == ["gh", "api"]
