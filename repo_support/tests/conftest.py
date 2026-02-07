# Copyright (c) Microsoft Corporation.
# Licensed under the MIT License.

from __future__ import annotations

import json
from pathlib import Path

import pytest


@pytest.fixture
def fixtures_dir() -> Path:
    return Path(__file__).parent / "fixtures"


@pytest.fixture
def mock_pr_list(fixtures_dir: Path) -> list[dict[str, object]]:
    with (fixtures_dir / "mock_pr_list.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def mock_pr_view(fixtures_dir: Path) -> dict[str, object]:
    with (fixtures_dir / "mock_pr_view.json").open("r", encoding="utf-8") as handle:
        return json.load(handle)


@pytest.fixture
def temp_git_repo(tmp_path: Path) -> Path:
    """Return a temporary directory intended for git repo setup in tests."""
    return tmp_path
