# Tasks: PR Branch Management Tools Suite

**Input**: Design documents from `/specs/001-pr-branch-tools/`
**Prerequisites**: plan.md, spec.md, research.md, data-model.md, contracts/

**Tests**: This feature includes unit tests and integration tests per the Constitution Check. Tests MUST be implemented alongside each tool to verify security boundaries, input validation, and cross-platform behavior.

**Organization**: Tasks are grouped by user story to enable independent implementation and testing of each story.

---

## Implementation Status (2026-02-07)

**Release gate**: This feature is considered complete and ready for review. All implementation phases are complete including documentation.

**Completed Phases**: 
- ✅ Phase 1: Setup (4/4 tasks)
- ✅ Phase 2: Foundational (7/7 tasks) 
- ✅ Phase 3: User Story 5 - Status Dashboard (10/10 tasks)
- ✅ Phase 4: User Story 1 - Cherry-Pick Tool (16/16 tasks)
- ✅ Phase 5: User Story 2 - Relabeling (13/13 tasks)
- ✅ Phase 6: User Story 3 - Staging Support (7/7 tasks)
- ✅ Phase 7: User Story 4 - Dependency Analysis (13/13 tasks)
- ✅ Phase 8: User Story 6 - Workflow Wrapper (12/12 tasks)
- ✅ Phase 9: Polish & Documentation (10/10 tasks)

**Implementation Complete**: All 92 tasks completed (92/92)

**Tools Implemented**:
- `repo_support/shared_utils.py` - Common validation and helpers
- `repo_support/backport_status.py` - Status dashboard (read-only)
- `repo_support/gen_cherrypick_prs.py` - Cherry-pick PR creation with worktrees
- `repo_support/relabel_backported.py` - Label updates after backporting
- `repo_support/analyze_pr_deps.py` - Dependency analysis for conflicts
- `repo_support/backport_workflow.py` - Unified workflow orchestrator

**Documentation**:
- `repo_support/README.md` - Complete tool reference and troubleshooting
- `Guide/src/dev_guide/pr_management.md` - Conceptual guide and workflows
- All tools include comprehensive `--help` output and module docstrings

**Next Steps**:
1. Manual testing with real repository PRs and branches
2. Performance validation with production data
3. Final code review and polish
4. Integration into CI/CD workflows (if desired)

---

## Format: `- [ ] [ID] [P?] [Story] Description`

- **[P]**: Can run in parallel (different files, no dependencies)  
- **[Story]**: Which user story this task belongs to (e.g., US1, US2, US5)  
- Include exact file paths in descriptions

## Path Conventions

All tools located in `repo_support/` following repository convention. Tests in `repo_support/tests/`. Guide documentation in `Guide/src/dev_guide/`.

---

## Phase 1: Setup (Shared Infrastructure)

**Purpose**: Project initialization and shared utilities

- [X] T001 Create directory structure: `repo_support/tests/` and `repo_support/tests/fixtures/`
- [X] T002 [P] Create `repo_support/shared_utils.py` with stub functions for input validation, GitHub API helpers, and subprocess wrappers
- [X] T003 [P] Create `repo_support/tests/conftest.py` with pytest fixtures for mock GitHub API responses and temporary git repositories
- [X] T004 [P] Add mock GitHub API response fixtures in `repo_support/tests/fixtures/mock_pr_list.json`, `mock_pr_view.json`

---

## Phase 2: Foundational (Blocking Prerequisites)

**Purpose**: Core shared utilities that ALL tools depend on

**⚠️ CRITICAL**: No user story work can begin until this phase is complete

- [X] T005 Implement input validation functions in `repo_support/shared_utils.py`: `validate_pr_number()`, `validate_branch_name()`, `validate_version()`, `validate_label()`
- [X] T006 [P] Implement GitHub API wrapper functions in `repo_support/shared_utils.py`: `gh_pr_view()`, `gh_pr_list()`, `gh_api_query()`
- [X] T007 [P] Implement git subprocess helpers in `repo_support/shared_utils.py`: `git_fetch()`, `git_merge_base()`, `git_worktree_add()`, `git_worktree_remove()`
- [X] T008 [P] Implement error formatting utilities in `repo_support/shared_utils.py`: `format_error()`, `format_conflict_summary()`, `format_actionable_message()`
- [X] T009 Write unit tests for input validation in `repo_support/tests/test_shared_utils.py` (validate_pr_number, validate_branch_name, validate_version, validate_label)
- [X] T010 Write unit tests for GitHub API wrappers in `repo_support/tests/test_shared_utils.py` (mock gh CLI responses)
- [X] T011 Perform Constitution Check: verify Security/Trust (input validation complete), Tests (pytest configured), Documentation plan (README, Guide page outlined), and no `unsafe` code (Python scripts)

**Checkpoint**: Foundation ready - user story implementation can now begin in parallel

---

## Phase 3: User Story 5 - Backport Status Dashboard (Priority: P2) 🎯 GOOD STARTING POINT

**Goal**: Provide read-only visibility into backport status for all repository users

**Independent Test**: Run tool against repository with labeled PRs, verify output matches manual label/PR inspection

**Why start here**: Read-only tool, no complex git operations, no worktrees, accessible to all users, provides immediate value

### Implementation for User Story 5

- [X] T012 [P] [US5] Create `repo_support/backport_status.py` with CLI argument parsing (`version`, `--branch`, `--pr`, `--format`, `--repo`)
- [X] T013 [US5] Implement GitHub API queries in `backport_status.py`: query PRs with `backport_{version}` label, query PRs with `backported_{version}` label
- [X] T014 [US5] Implement GitHub API query for open cherry-pick PRs to target branches in `backport_status.py`
- [X] T015 [US5] Implement worktree detection logic in `backport_status.py`: scan `.git/worktrees/` for conflict-retained worktrees
- [X] T016 [US5] Implement data correlation logic in `backport_status.py`: link original PR to cherry-pick PR via title matching
- [X] T017 [US5] Implement output formatters in `backport_status.py`: `format_summary()`, `format_table()`, `format_json()`, `format_detailed()`
- [X] T018 [US5] Add error handling and return codes (0: success, 1: no matches, 2: invalid input, 3: API error)
- [X] T019 [US5] Add module-level docstring with usage examples to `backport_status.py`
- [X] T020 Write unit tests for `backport_status.py` in `repo_support/tests/test_backport_status.py` (input validation, output formatting, data correlation)
- [X] T021 Write integration test for `backport_status.py` in `repo_support/tests/test_backport_status.py` (mock GitHub API responses, verify all output formats)

**Checkpoint**: Users can now check backport status for any release version

---

## Phase 4: User Story 1 - Automated Cherry-Pick PR Creation (Priority: P1) 🎯 MVP CORE

**Goal**: Automate cherry-pick PR creation with worktree isolation, correct merge order, and conflict detection

**Independent Test**: Run tool with labeled PRs, verify cherry-pick PRs created in merge order with correct titles/bodies, no main worktree modifications

**Why P1**: Core workflow that enables all other backport tools

### Implementation for User Story 1

- [X] T022 [P] [US1] Create `repo_support/gen_cherrypick_prs.py` with CLI argument parsing (`target_branch`, `--from-backport-label`, `pr_numbers`, `--dry-run`, `--no-confirm`, `--keep-worktree`, `--force-cleanup`, `--repo`)
- [X] T023 [US1] Implement PR discovery logic in `gen_cherrypick_prs.py`: label-based query OR explicit PR list, order by merge order on `main` derived from git history (first-parent ordering). If ordering is ambiguous/unavailable, warn and proceed using `mergedAt` and then PR number as a tiebreaker.
- [X] T024 [US1] Implement duplicate detection in `gen_cherrypick_prs.py`: check if merge commit already in target branch using `git merge-base --is-ancestor`
- [X] T025 [US1] Implement worktree creation in `gen_cherrypick_prs.py`: `git worktree add .git/worktrees/backport-temp-{timestamp} origin/{target_branch}`
- [X] T026 [US1] Implement cherry-pick operation in `gen_cherrypick_prs.py`: `git -C {worktree_path} cherry-pick {merge_commit}` with conflict detection
- [X] T027 [US1] Implement conflict handling in `gen_cherrypick_prs.py`: stop immediately, output clear summary (conflicted files, worktree path, suggest analyze_pr_deps.py), retain worktree
- [X] T028 [US1] Implement PR creation in `gen_cherrypick_prs.py`: `gh pr create` with title "{original_title} (cherry-pick from #{pr_number})", body with original PR link
- [X] T029 [US1] Implement worktree cleanup in `gen_cherrypick_prs.py`: auto-cleanup on success (unless `--keep-worktree`), retain on conflict (unless `--force-cleanup`)
- [X] T030 [US1] Implement interactive confirmation prompts in `gen_cherrypick_prs.py` (skip with `--no-confirm`)
- [X] T031 [US1] Implement `--dry-run` mode in `gen_cherrypick_prs.py`: show what would be done without creating worktrees or PRs
- [X] T032 [US1] Add comprehensive error handling and JSON summary output (`--json`) to `gen_cherrypick_prs.py`
- [X] T033 [US1] Add module-level docstring with usage examples to `gen_cherrypick_prs.py`
- [X] T034 Write unit tests for `gen_cherrypick_prs.py` in `repo_support/tests/test_gen_cherrypick_prs.py` (input validation, PR sorting, duplicate detection, worktree path generation)
- [X] T035 Write integration test for clean cherry-pick in `repo_support/tests/test_gen_cherrypick_prs.py` (temporary git repo, mock GitHub API, verify PR creation)
- [X] T036 Write integration test for conflict scenario in `repo_support/tests/test_gen_cherrypick_prs.py` (verify worktree retained, clear error message, main worktree untouched)
- [X] T037 Write integration test for `--dry-run` mode in `repo_support/tests/test_gen_cherrypick_prs.py` (verify no side effects)

**Checkpoint**: Maintainers can now create cherry-pick PRs automatically with worktree isolation and conflict detection

---

## Phase 5: User Story 2 - Automated PR Relabeling After Backport (Priority: P2)

**Goal**: Update original PR labels from `backport_X` to `backported_X` after successful backporting

**Independent Test**: Manually create backport commit, run tool, verify labels updated and comments added

**Why P2**: Completes backport workflow, provides visibility into completion status

### Implementation for User Story 2

- [X] T038 [P] [US2] Enhance `repo_support/relabel_backported.py` with CLI argument parsing (`version`, `--update`, `--force-update-pr`, `--repo`) if not already present
- [X] T039 [US2] Implement PR discovery in `relabel_backported.py`: query merged PRs with `backport_{version}` label
- [X] T040 [US2] Implement backport detection in `relabel_backported.py`: search git log for "cherry-pick from #{pr_number}" in target branch commits
- [X] T041 [US2] Implement title mismatch detection in `relabel_backported.py`: compare commit title with original PR title, warn if different
- [X] T042 [US2] Implement open PR detection in `relabel_backported.py`: skip PRs that are still open on main (not merged yet)
- [X] T043 [US2] Implement label updates in `relabel_backported.py`: add `backported_{version}`, remove `backport_{version}`, add comment with backport PR link (only when `--update` flag provided)
- [X] T044 [US2] Implement `--force-update-pr` override in `relabel_backported.py` for title mismatches
- [X] T045 [US2] Add dry-run mode (default) and JSON summary output (`--json`) to `relabel_backported.py`
- [X] T046 [US2] Add comprehensive error handling and return codes to `relabel_backported.py`
- [X] T047 [US2] Add/update module-level docstring with usage examples in `relabel_backported.py`
- [X] T048 Write unit tests for `relabel_backported.py` in `repo_support/tests/test_relabel_backported.py` (version format validation, title comparison logic, label pattern matching)
- [X] T049 Write integration test for `relabel_backported.py` in `repo_support/tests/test_relabel_backported.py` (mock GitHub API, mock git log output, verify label updates)
- [X] T050 Write integration test for title mismatch warning in `repo_support/tests/test_relabel_backported.py` (verify warning issued, no update without --force-update-pr)

**Checkpoint**: Backport workflow now complete end-to-end (cherry-pick → merge → relabel)

---

## Phase 6: User Story 3 - Staging Branch Support (Priority: P1-MVP)

**Goal**: Extend all tools to support `staging/X.Y.Z` branches using same label convention

**Independent Test**: Run cherry-pick and relabel tools with `staging/1.7.2511` target, verify correct behavior

**Why MVP**: Staging is the primary target for most backport operations in the closed-source ingestion workflow (main → staging → release). All tools must support staging branches before deployment.

### Implementation for User Story 3

- [X] T051 [P] [US3] Update branch validation in `shared_utils.py`: accept both `release/X.Y.Z` and `staging/X.Y.Z` patterns
- [X] T052 [P] [US3] Update `gen_cherrypick_prs.py`: verify works with `staging/` target branches (may already work, add explicit test)
- [X] T053 [P] [US3] Update `relabel_backported.py`: detect backports in `staging/` branches alongside `release/` branches
- [X] T054 [P] [US3] Update `backport_status.py`: query both `release/X.Y.Z` and `staging/X.Y.Z` branches for given version
- [X] T055 [US3] Write integration test for staging branch cherry-pick in `repo_support/tests/test_gen_cherrypick_prs.py`
- [X] T056 [US3] Write integration test for staging branch relabeling in `repo_support/tests/test_relabel_backported.py`
- [X] T057 [US3] Write integration test for staging branch status display in `repo_support/tests/test_backport_status.py`

**Checkpoint**: All tools now support staging branches for pre-release validation workflow

---

## Phase 7: User Story 4 - PR Dependency Analysis for Conflict Investigation (Priority: P4)

**Goal**: Help users understand why cherry-picks conflict by identifying missing prerequisite PRs

**Independent Test**: Analyze file with known modification history, verify tool correctly identifies PRs touching file and filters by target branch presence

**Why P4**: Critical for conflict resolution, reduces manual investigation time

### Implementation for User Story 4

- [X] T058 [P] [US4] Create `repo_support/analyze_pr_deps.py` with CLI argument parsing (`--file`, `--pr`, `--target`, `--merged-after`, `--repo`)
- [X] T059 [US4] Implement file identification logic in `analyze_pr_deps.py`: if `--pr` provided, query GitHub for files changed in PR
- [X] T060 [US4] Implement PR discovery in `analyze_pr_deps.py`: query all merged PRs to main, filter by merge date if `--merged-after` provided
- [X] T061 [US4] Implement file modification detection in `analyze_pr_deps.py`: for each PR, check if it modified target file(s) using `git diff-tree`
- [X] T062 [US4] Implement target branch presence check in `analyze_pr_deps.py`: use `git merge-base --is-ancestor` to check if PR commit in target branch
- [X] T063 [US4] Implement open cherry-pick detection in `analyze_pr_deps.py`: search for open PRs to target branch mentioning each missing PR
- [X] T064 [US4] Implement ordering and output in `analyze_pr_deps.py`: sort missing PRs by merge date (oldest first), provide recommendations, and support JSON output via `--json`
- [X] T065 [US4] Add comprehensive error handling and return codes to `analyze_pr_deps.py`
- [X] T066 [US4] Add module-level docstring with usage examples to `analyze_pr_deps.py`
- [X] T067 Write unit tests for `analyze_pr_deps.py` in `repo_support/tests/test_analyze_pr_deps.py` (input validation, commit ancestry detection, PR filtering and sorting)
- [X] T068 Write integration test for file-based analysis in `repo_support/tests/test_analyze_pr_deps.py` (multiple PRs modifying same file, correct identification of missing prerequisites)
- [X] T069 Write integration test for PR-based analysis in `repo_support/tests/test_analyze_pr_deps.py` (analyze files changed in specific PR, identify prerequisites)
- [X] T070 Write integration test for open cherry-pick detection in `repo_support/tests/test_analyze_pr_deps.py` (verify warning when prerequisite has pending cherry-pick PR)

**Checkpoint**: Users can now quickly identify missing prerequisites when cherry-picks conflict

---

## Phase 8: User Story 6 - Unified Workflow Wrapper (Priority: P5)

**Goal**: Single entry point that guides maintainers through complete backport workflow

**Independent Test**: Run wrapper tool, verify it correctly sequences cherry-pick → monitoring → relabeling

**Why P5**: Nice-to-have convenience wrapper, but underlying tools must work independently first

### Implementation for User Story 6

- [X] T071 [P] [US6] Create `repo_support/backport_workflow.py` with CLI argument parsing (`target_branch`, `--finalize`, `--dry-run`, `--skip-relabel`, `--repo`)
- [X] T072 [US6] Implement workflow phase 1 in `backport_workflow.py`: call `gen_cherrypick_prs.py` subprocess, capture results
- [X] T073 [US6] Implement workflow phase 2 in `backport_workflow.py`: poll cherry-pick PR merge status (30-second intervals, 30-minute max timeout or user abort)
- [X] T074 [US6] Implement workflow phase 3 in `backport_workflow.py`: call `relabel_backported.py` subprocess after PRs merged
- [X] T075 [US6] Implement interactive prompts in `backport_workflow.py`: display state transitions, allow user to check status/abort/proceed
- [X] T076 [US6] Implement `--finalize` mode in `backport_workflow.py`: automatic workflow execution without manual prompts
- [X] T077 [US6] Implement conflict and partial completion handling in `backport_workflow.py`: detect failed cherry-picks, suggest analyze_pr_deps.py
- [X] T078 [US6] Add comprehensive error handling and summary output to `backport_workflow.py`
- [X] T079 [US6] Add module-level docstring with usage examples to `backport_workflow.py`
- [X] T080 Write unit tests for `backport_workflow.py` in `repo_support/tests/test_backport_workflow.py` (workflow state transitions, subprocess call logic)
- [X] T081 Write integration test for complete workflow in `repo_support/tests/test_backport_workflow.py` (mock all tool subprocesses, verify sequencing)
- [X] T082 Write integration test for `--finalize` mode in `repo_support/tests/test_backport_workflow.py` (verify automatic execution without prompts)

**Checkpoint**: Maintainers can now run complete backport workflow with single command

---

## Phase 9: Polish & Cross-Cutting Concerns

**Purpose**: Documentation, cross-tool improvements, and final validation

- [X] T083 [P] Create `repo_support/README.md` with prerequisites (git, gh CLI, Python 3.11+), usage examples for each tool, complete workflow walkthrough, troubleshooting common issues
- [X] T084 [P] Create `Guide/src/dev_guide/pr_management.md` with conceptual guide to branch strategy (main → staging → release), labeling conventions, when to use each tool, conflict resolution workflow
- [X] T085 [P] Update all tool scripts to ensure every error message includes actionable guidance (what went wrong, how to fix it)
- [X] T086 [P] Add `--help` output with examples to all tools (gen_cherrypick_prs, relabel_backported, analyze_pr_deps, backport_status, backport_workflow)
- [X] T087 [P] Verify all subprocess calls use list arguments (no `shell=True`) for security in all tools
- [X] T088 [P] Add performance test: verify dependency analysis completes in <30 seconds for file with 100+ PR modifications
- [X] T089 [P] Add performance test: verify status tool completes in <5 seconds for typical repositories
- [X] T090 Run quickstart.md validation: manually test all scenarios in quickstart.md against real or test repository
- [X] T091 Code review and refactoring: consistent error handling, consistent output formatting, shared code extraction to shared_utils.py
- [X] T092 Final Constitution Check: Security (input validation complete, no shell injection), Tests (pytest runs all tests successfully), Documentation (README + Guide page complete), Cross-platform (verify on Linux, test on macOS/Windows via WSL2 if available)

---

## Dependencies & Execution Order

### Phase Dependencies

- **Setup (Phase 1)**: No dependencies - can start immediately
- **Foundational (Phase 2)**: Depends on Setup completion - BLOCKS all user stories
- **User Stories (Phase 3-8)**: All depend on Foundational phase completion
  - User stories CAN proceed in parallel (if staffed)
  - OR sequentially in suggested order: US5 → US1 → US2 → US3 → US4 → US6
- **Polish (Phase 9)**: Depends on desired user stories being complete

### User Story Dependencies

- **User Story 5 (Status Dashboard, P2)**: Can start after Foundational - Good starting point, read-only, no complex git ops
- **User Story 1 (Cherry-Pick, P1)**: Can start after Foundational - Core workflow, independent
- **User Story 2 (Relabeling, P2)**: Can start after Foundational - Works with US1 but independently testable
- **User Story 3 (Staging Support, P3)**: Extends US1/US2/US5 - Requires those tools to exist but adds minimal code
- **User Story 4 (Dependency Analysis, P4)**: Can start after Foundational - Independent conflict investigation tool
- **User Story 6 (Workflow Wrapper, P5)**: Should start after US1 and US2 exist - Orchestrates those tools

### Within Each User Story

- Shared utilities (Phase 2) before any tool implementation
- Tool CLI and core logic before tests
- Tests verify behavior matches contract specifications
- Documentation after tool is functional

### Parallel Opportunities

- **Phase 1 Setup**: All tasks marked [P] can run in parallel
- **Phase 2 Foundational**: All validation and helper functions marked [P] can run in parallel
- **Phase 3-8 User Stories**: Different user stories can be worked on in parallel by different team members once Phase 2 is complete
- **Phase 9 Polish**: Most documentation and validation tasks marked [P] can run in parallel

---

## Parallel Example: Multiple User Stories

```bash
# After Phase 2 (Foundational) completes, launch all user stories in parallel:

Developer A: Phase 3 (US5 - Status Dashboard)
Developer B: Phase 4 (US1 - Cherry-Pick Tool)
Developer C: Phase 7 (US4 - Dependency Analysis)

# These are independent and can proceed simultaneously
```

---

## Implementation Strategy

### MVP First (Status + Cherry-Pick Only)

1. Complete Phase 1: Setup
2. Complete Phase 2: Foundational (CRITICAL - blocks all stories)
3. Complete Phase 3: User Story 5 (Status Dashboard) - Quick win, high visibility
4. Complete Phase 4: User Story 1 (Cherry-Pick Tool) - Core workflow
5. **STOP and VALIDATE**: Test cherry-pick workflow end-to-end
6. Deploy/demo if ready

### Incremental Delivery

1. Complete Setup + Foundational → Foundation ready
2. Add User Story 5 (Status) → Users can check backport status (immediate value!)
3. Add User Story 1 (Cherry-Pick) → Contributors can create backport PRs automatically
4. Add User Story 2 (Relabeling) → Complete backport workflow
5. Add User Story 3 (Staging) → MVP complete: staging + release branches supported
6. Add User Story 4 (Dependency Analysis) → Conflict investigation support
7. Add User Story 6 (Workflow Wrapper) → Convenience orchestration

Stories 1-5 constitute the MVP. Stories 6-7 are post-MVP enhancements.

### Suggested MVP Scope

**Minimum Viable Product**: Phase 1 + Phase 2 + Phase 3 (Status) + Phase 4 (Cherry-Pick) + Phase 5 (Relabeling) + Phase 6 (Staging Support)

This provides:
- Visibility into backport status (any user can check)
- Automated cherry-pick PR creation (contributors via fork)
- Conflict detection with clear guidance
- Worktree isolation (safe to run during active development)
- Label updates after successful backports (maintainers)
- Staging branch support for the closed-source ingestion workflow (main → staging → release)

Then iterate with additional user stories (Dependency Analysis, Workflow Wrapper) based on maintainer feedback.

---

## Notes

- **Tests NOT optional**: Per Constitution Check, unit tests and integration tests MUST be implemented for security-critical input validation and cross-platform behavior
- **[P] tasks**: Different files, no dependencies - can run in parallel
- **[Story] label**: Maps task to specific user story for traceability
- **Each user story independently testable**: Verify story works on its own before moving to next
- **Commit strategy**: Commit after each task or small logical group, verify tests pass
- **Avoid**: Vague tasks, same-file conflicts, cross-story dependencies that break independence
- **Documentation concise**: Prioritize runnable examples and short rationale notes, avoid long-form prose
- **User roles**: Status/analysis tools accessible to all users (read-only); cherry-pick via fork (contributors); relabel requires upstream write access (maintainers)
