# Implementation Plan: PR Branch Management Tools Suite

**Branch**: `001-pr-branch-tools` | **Date**: 2026-02-06 | **Spec**: [specs/001-pr-branch-tools/spec.md](specs/001-pr-branch-tools/spec.md)
**Input**: Feature specification from `/specs/001-pr-branch-tools/spec.md`

**Note**: This template is filled in by the `/speckit.plan` command. See `.specify/templates/commands/plan.md` for the execution workflow.

## Summary

Build a suite of Python-based tools to automate PR backporting workflow across `main`, `release/X.Y.Z`, and `staging/X.Y.Z` branches. Includes:
1. **backport_status.py**: Status dashboard showing pending, in-progress, completed, and blocked backports (accessible to all users)
2. **gen_cherrypick_prs.py**: Automated cherry-pick PR creation with worktree isolation (in progress in PR #2680)
3. **relabel_backported.py**: Updates labels+comments after successful backports (already exists, may require enhancement)
4. **analyze_pr_deps.py**: Identifies missing prerequisites for failed cherry-picks (new tool, accessible to all users)
5. **backport_workflow**: Unified wrapper to guide maintainers through complete backport cycle (new tool)

Technical approach: Use git worktrees for operation isolation, GitHub CLI for API queries, and subprocess for git operations. Status tool queries GitHub API and local git; all other scripts use subprocess for git operations. All scripts accessible to general users (status tool read-only; others require write access). All scripts use standard Python 3.11+ library with no heavy external dependencies.

## Technical Context

**Language/Version**: Python 3.11+ (specified in spec as repository tooling standard)  
**Primary Dependencies**: 
- GitHub CLI (`gh`) for PR operations and GitHub API queries
- Git (built-in system command for branch/cherry-pick/worktree operations)  
- Python 3.11+ standard library: `subprocess`, `json`, `argparse`, `datetime`, `re`, `pathlib`

**Storage**: N/A (repository automation scripts, no persistent data storage)  
**Testing**: pytest with temporary git repositories for integration tests (`repo_support/tests/test_*.py`)  
**Target Platform**: Linux, macOS, Windows (via WSL2 or native Python) - cross-platform via Python + standard tools
**Project Type**: Multi-script tooling (coordinated set of automation scripts vs single monolithic tool)  
**Performance Goals**: 
- Automate repetitive cherry-pick commands (each PR still takes ~10 min including review, but eliminates manual branch creation/PR creation steps)
- Dependency analysis in under 30 seconds for files with 100+ PR modifications
- Tool responses in <5 seconds for typical operations
- Primary value: Avoid mistakes (wrong order, duplicate PRs, missing backports), provide clear conflict resolution guidance

**Constraints**: 
- No platform-specific builds required
- Requires `git` and `gh` CLI installed and authenticated (user responsibility per spec)
- Must not modify main working directory (all cherry-pick via worktrees)
- Every operation reversible with clear cleanup instructions

**Scale/Scope**: 
- 6 tools total (5 core + 1 wrapper): backport_status, gen_cherrypick_prs, relabel_backported, analyze_pr_deps, backport_workflow, plus shared utilities
- ~300-500 LOC per tool (status tool lighter weight)
- Handles 10s of PRs per backport cycle
- Accessible to all users with appropriate permissions

## Constitution Check

*GATE: Must pass before Phase 0 research. Re-check after Phase 1 design.*

All plans MUST include explicit verification for these gates taken from the OpenVMM Constitution:

**✅ Security & Trust Boundaries**
- Input validation: PR numbers and branch names validated via regex patterns to prevent command injection
- All subprocess calls use list arguments (no `shell=True` to prevent shell injection)
- Tools parse GitHub API JSON responses (trusted source) and file paths (user-provided but validated)
- No `unsafe` code needed (Python scripts)
- Validation patterns: `^[0-9]+$` for PR numbers, `^(main|release|staging)/[0-9.]+$` for branch names, `^[a-zA-Z0-9_-]+$` for labels

**✅ Tests**
- **Unit tests**: `repo_support/tests/test_gen_cherrypick_prs.py`, `test_relabel_backported.py`, `test_analyze_pr_deps.py` using pytest
  - Test input validation (invalid PR numbers, malformed branches)
  - Test git operations (merging, cherry-picking mock commits)
  - Test GitHub API interactions (mocked via requests_mock or local fixtures)
  - Execution: `python -m pytest repo_support/tests/ -v`
- **Integration tests**: Temporary git repositories with mock PRs simulating real backport scenarios
  - Test cherry-pick behavior with and without conflicts
  - Test label update accuracy with real filesystem operations
  - Test dependency chain detection across multiple PRs

**✅ Documentation**
- **Module docstrings**: Each script (`gen_cherrypick_prs.py`, `relabel_backported.py`, `analyze_pr_deps.py`, `backport_workflow.py`) includes module-level docstring with usage examples and error codes
- **repo_support/README.md**: Complete prerequisites (git, gh CLI, Python 3.11+), usage examples for each tool, workflow walkthrough, troubleshooting
- **Guide/src/dev_guide/pr_management.md** (new): Conceptual guide to branch strategy, labeling conventions, when to use each tool, conflict resolution workflow
- **Error messages**: Every error condition includes actionable guidance (what went wrong, how to fix)
  - Example: `"Cherry-pick conflict in src/foo.rs. Run: analyze-pr-deps --file src/foo.rs --target release/1.7.2511 to find missing prerequisites. Worktree at: /path/to/worktree/"`

**✅ Build & Cross-Platform**
- No special build steps; Python 3.11+ runs directly via system Python interpreter
- Works on Linux, macOS, Windows (via native Python or WSL2)
- CI integration via `python -m pytest` (existing pytest infrastructure)
- Cross-platform verified during integration testing (temp repos work on all platforms)
- Scripts require `git` and `gh` CLI (user responsibility to install; documented in README)

**✅ Dependency Rationale**
- Primary dependencies: `git`, `gh` CLI (system commands, not packaged)
- Python stdlib only: `subprocess`, `json`, `argparse`, `datetime`, `re`, `pathlib`
- Testing dependencies: `pytest`, `requests_mock` (standard Python dev tools, already in repo)
- Rationale: Automation scripts should be simple and auditable; external deps add maintenance burden and security surface

**✅ Documentation Style** 
- Concise, example-first documentation in scripts and README
- Prioritize copy-pasteable command examples
- Avoid long-form prose; link to Guide for conceptual explanations
- Module docstrings show real command examples with common scenarios

**✅ User Access & Roles**
- Status tool (`backport_status.py`) explicitly read-only, accessible to all users
- Cherry-pick/relabel tools require write permissions to create branches/PRs
- Clear error messages when user lacks required permissions
- Future maintainer-specific features for governance/staging→release workflow
- All documentation clarifies user roles and which tools they can access

## Project Structure

### Documentation (this feature)

```text
specs/001-pr-branch-tools/
├── plan.md              # This file (/speckit.plan command output)
├── research.md          # Phase 0 output (/speckit.plan command)
├── data-model.md        # Phase 1 output (/speckit.plan command)
├── quickstart.md        # Phase 1 output (/speckit.plan command)
├── contracts/           # Phase 1 output (/speckit.plan command) - API/data contracts
└── tasks.md             # Phase 2 output (/speckit.tasks command - NOT created by /speckit.plan)
```

### Source Code (repository root)

```text
repo_support/
├── backport_status.py              # Status dashboard - accessible to all users (NEW)
├── gen_cherrypick_prs.py           # Cherry-pick PR creation (in progress, PR #2680)
├── relabel_backported.py           # Backport label updates (existing, may require enhancement)
├── analyze_pr_deps.py              # Dependency analysis for conflict investigation (NEW)
├── backport_workflow.py            # Unified workflow wrapper (NEW)
├── shared_utils.py                 # Shared utilities: input validation, GitHub API wrappers
├── README.md                       # Complete guide: prerequisites, usage, workflow, troubleshooting
└── tests/
    ├── test_backport_status.py              # Unit tests
    ├── test_gen_cherrypick_prs.py           # Unit + integration tests
    ├── test_relabel_backported.py           # Unit + integration tests
    ├── test_analyze_pr_deps.py              # Unit + integration tests
    └── fixtures/
        └── mock_*.json                      # Mock GitHub API responses for testing

Guide/src/dev_guide/
├── pr_management.md                # NEW: Conceptual guide to PR lifecycle, branch strategy, tooling
└── [existing structure preserved]
```

**Structure Decision**: Multi-script modular design within `repo_support/` with shared utilities. Each tool is independently testable and documented, coordinated by the wrapper script. Status tool provided as read-only information service for all users. This follows repository convention (see existing `relabel_backported.py`) and keeps automation scripts focused and auditable.

## Complexity Tracking

> **Fill ONLY if Constitution Check has violations that must be justified**

| Violation | Why Needed | Simpler Alternative Rejected Because |
|-----------|------------|-------------------------------------|
| [e.g., 4th project] | [current need] | [why 3 projects insufficient] |
| [e.g., Repository pattern] | [specific problem] | [why direct DB access insufficient] |
