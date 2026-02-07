# Feature Specification: PR Branch Management Tools Suite

**Feature Branch**: `001-pr-branch-tools`  
**Created**: 2026-02-06  
**Status**: Draft  
**Input**: User description: "I want to build a suite of tools to help manage PRs across `main`, `release/` and `staging/` branches. We already have one of these (checked in to main in `repo_support`) that handles labeling PRs after they've been backported (see relabel_backported). I am, in this branch, adding a tool to do the cherry picking (see gen_cherry_pick prs). There's already some comments in PR 2680 with ideas. But, help me take this to completion."

## Implementation Language Preferences

The repository prefers the following defaults unless a clear justification is provided:

- **Mainline code:** Rust (stable, specify minimal supported toolchain in the plan).
- **Tooling & automation scripts:** Python 3.11+ (use virtualenv, `pip` or `venv`). Use shell or PowerShell only when platform constraints require them.

**Justification for Python**: These are automation/repository maintenance scripts that interact heavily with git and GitHub CLI. Python is the standard for such tooling in this repository (see existing `repo_support/relabel_backported.py`). Rust would add unnecessary complexity for scripts that primarily orchestrate external tools.

### Documentation Requirements

All PR branch management tools MUST include:

- **README in repo_support/**: Usage examples, prerequisites (git, gh CLI), and workflow descriptions
- **Guide updates**: Add `Guide/src/dev_guide/pr_management.md` explaining the complete PR lifecycle across branches
- **Script docstrings**: Each Python script MUST have module-level docstrings with usage examples
- **Error messages**: All error conditions MUST include actionable guidance (what went wrong, how to fix it)

Documentation Style: Focus on copy-pasteable command examples. Keep conceptual explanations in the Guide, detailed usage in script `--help` output.

## User Scenarios & Testing *(mandatory)*

### User Story 1 - Automated Cherry-Pick PR Creation (Priority: P1)

A repository maintainer needs to backport multiple merged PRs from `main` to a `release/X.Y.Z` branch in the correct merge order, creating separate cherry-pick PRs for each original PR.

**Why this priority**: This is the core workflow that blocks releases. Currently being implemented in PR #2680 as `gen_cherrypick_prs.py`. Must be completed first.

**Independent Test**: Can be fully tested by running the tool against a test repository with labeled PRs and verifying that cherry-pick PRs are created in merge order with correct references.

**Acceptance Scenarios**:

1. **Given** a release branch `release/1.7.2511` and 5 merged PRs labeled `backport_1.7.2511` on main, **When** maintainer runs `gen_cherrypick_prs.py release/1.7.2511 --from-backport-label backport_1.7.2511`, **Then** the tool creates 5 cherry-pick PRs in merge order, each with correct title/body references, all operations isolated in temporary worktrees
2. **Given** a list of specific PR numbers (e.g., 2567, 2525, 2533), **When** maintainer runs `gen_cherrypick_prs.py release/1.7.2511 2567 2525 2533`, **Then** the tool processes them in merge order regardless of command-line order
3. **Given** a cherry-pick operation encounters merge conflicts on PR #2680, **When** the conflict is detected, **Then** the tool stops immediately, retains worktree, outputs clear summary including: conflicting files, worktree path, suggestion to run `analyze_pr_deps.py --pr 2680 --target release/1.7.2511`, and does NOT create a PR
4. **Given** a PR has already been backported, **When** the tool is re-run, **Then** it detects the existing backport PR and skips the PR with a status message
5. **Given** maintainer wants to preview changes, **When** run with `--dry-run`, **Then** tool shows what PRs would be processed without making any changes or creating worktrees

---

### User Story 2 - Automated PR Relabeling After Backport (Priority: P2)

After cherry-pick PRs are merged to a release branch, a maintainer needs to update the original PRs on `main` to reflect successful backporting by changing labels from `backport_X` to `backported_X` and adding completion comments.

**Why this priority**: This automation prevents manual tracking errors and provides visibility into backport status. Already exists as `relabel_backported.py` but may need enhancements.

**Independent Test**: Can be independently tested by creating test PRs with `backport_X` labels, manually creating backport PR commits, then verifying the relabeling tool updates labels and comments correctly.

**Acceptance Scenarios**:

1. **Given** PRs labeled `backport_1.7.2511` that have commits in `release/1.7.2511` referencing them, **When** maintainer runs `relabel_backported.py 1.7.2511 --update`, **Then** the tool adds `backported_1.7.2511` label, removes `backport_1.7.2511`, and comments with backport PR link
2. **Given** a backport commit title doesn't exactly match the original PR title, **When** running the tool, **Then** it warns about potential mismatch but allows `--force-update-pr` override
3. **Given** a PR labeled for backport is still open (not merged to main), **When** running the tool, **Then** it reports the PR as "not completed in main" and skips it

---

### User Story 3 - Staging Branch Support (Priority: P1-MVP)

Repository maintainers need to manage PR backports to `staging/X.Y.Z` branches as part of the closed-source ingestion workflow. Staging branches receive cherry-picks first; after shiproom approval, changes move from staging to release branches.

**Why this priority**: Staging is part of the release gating workflow (main → staging/X.Y.Z → release/X.Y.Z) and is required for the closed-source ingestion workflow. All tools MUST support staging branches as part of the MVP since staging is the primary target for most backport operations.

**Independent Test**: Can be tested independently by running existing cherry-pick and relabeling tools against `staging/X.Y.Z` branches using same label convention (e.g., `backport_1.7.2511`).

**Acceptance Scenarios**:

1. **Given** a staging branch `staging/1.7.2511` and PRs labeled `backport_1.7.2511` on main, **When** maintainer runs `gen_cherrypick_prs.py staging/1.7.2511 --from-backport-label backport_1.7.2511`, **Then** cherry-pick PRs are created targeting the staging branch
2. **Given** backported PRs on staging branches, **When** maintainer runs the relabeling tool, **Then** staging backports are detected and relabeled with `backported_1.7.2511` label

---

### User Story 4 - PR Dependency Analysis for Conflict Investigation (Priority: P4)

When a cherry-pick fails due to conflicts, maintainers need to understand why. The tool should identify prerequisite PRs that modified the same files but haven't been backported yet, helping maintainers understand the dependency chain.

**Why this priority**: Reduces time spent manually investigating conflicts. Helps maintainers identify missing prerequisite PRs or PRs still in review. Critical for understanding "why did this conflict?" and "what needs to backport first?"

**Independent Test**: Can be tested by analyzing a file with known modification history and verifying the tool correctly identifies PRs touching that file, filtering by target branch presence.

**Acceptance Scenarios**:

1. **Given** a conflict in file `src/foo.rs` during cherry-pick of PR #2680 to `release/1.7.2511`, **When** maintainer runs `analyze_pr_deps.py --file src/foo.rs --target release/1.7.2511`, **Then** tool lists all merged PRs in main that touched `src/foo.rs` but are NOT in `release/1.7.2511`, ordered by merge date
2. **Given** PR #2680 has a conflict and PR #2567 touched the same files, **When** maintainer runs `analyze_pr_deps.py --pr 2680 --target release/1.7.2511`, **Then** tool identifies #2567 as potential missing prerequisite if not backported
3. **Given** PR #2680 depends on #2567 which has an open cherry-pick PR to release branch, **When** running dependency analysis, **Then** tool warns "Prerequisite PR #2567 has open cherry-pick PR #2700 - wait for merge before backporting #2680"
4. **Given** a file path and target branch, **When** maintainer runs `analyze_pr_deps.py --file src/foo.rs --target release/1.7.2511 --merged-after 2026-01-01`, **Then** tool lists all PRs modified that file in main since the date, excluding those already in target branch

---

### User Story 5 - Backport Status Dashboard (Priority: P2)

Any user (maintainer or contributor) needs to quickly understand the current status of backports to a release branch: which PRs are pending backport, which have been backported, which are blocked by conflicts.

**Why this priority**: Provides visibility into ongoing backport efforts and prevents duplicate work. Helps any team member answer "is PR #2680 backported yet?" without diving into labels or PRs.

**Independent Test**: Can be tested by checking status output matches actual labels and cherry-pick PR presence in repository.

**Acceptance Scenarios**:

1. **Given** a release version (e.g., `1.7.2511`), **When** user runs `backport_status 1.7.2511`, **Then** tool displays summary showing: (a) PRs labeled `backport_1.7.2511` (pending backport), (b) PRs labeled `backported_1.7.2511` (completed backport), (c) Open cherry-pick PRs to `release/1.7.2511`, (d) Backport PRs with conflicts (worktrees retained)
2. **Given** a maintainer reviewing backport progress, **When** running the status tool, **Then** output shows count of pending, in-progress, completed, and blocked backports with links to relevant PRs
3. **Given** a user wants to know specific PR backport status, **When** running `backport_status 1.7.2511 --pr 2680`, **Then** tool shows: original PR details, backport label status, cherry-pick PR link (if exists), completion status
4. **Given** status command run on repository with mixed staging/release backports, **When** running with `--branch release/1.7.2511`, **Then** tool filters to that specific target branch only

---

### User Story 6 - Unified Workflow Wrapper (Priority: P5)

Maintainers need a single entry point that guides them through the complete backport workflow: cherry-picking PRs, verifying merges, and updating labels.

**Why this priority**: Reduces cognitive load and training requirements, but the underlying tools must work independently first.

**Independent Test**: Can be tested by running the wrapper tool and verifying it correctly sequences the individual tools (cherry-pick → wait for merges → relabel).

**Acceptance Scenarios**:

1. **Given** a maintainer wants to backport PRs to `release/1.7.2511`, **When** running `backport_workflow.py release/1.7.2511`, **Then** the tool runs cherry-pick creation, provides status, and optionally runs relabeling after confirmation
2. **Given** cherry-pick PRs are created but not yet merged, **When** running the workflow tool, **Then** it detects pending PRs and suggests waiting or checking PR statuses
3. **Given** all cherry-pick PRs are merged, **When** running the workflow tool with `--finalize`, **Then** it runs the relabeling tool to update original PR statuses

---

### Edge Cases

- **Conflict Resolution**: What happens when a cherry-pick has merge conflicts? Tool MUST stop immediately, retain worktree with conflict state, provide clear summary including: conflict files, worktree path, suggested next steps (run `analyze_pr_deps.py` to find missing prerequisites), and manual cleanup instructions. User's main worktree remains untouched.
- **Missing Prerequisites**: What if conflict is due to missing dependent PR? Dependency analysis tool identifies prerequisite PRs that haven't been backported. Tool suggests backport order or waiting for in-flight PRs.
- **Multiple Backport Attempts**: How does system handle re-running for the same release? Tool MUST detect existing backport PRs and skip/report them
- **Fork vs Upstream**: How does tool handle forked repositories? Tool MUST support both `--repo OWNER/REPO` and auto-detection from git remotes
- **Partial Completion**: What happens if some PRs succeed and others fail? Tool MUST provide clear summary of completed vs failed PRs, cleanup successful worktrees, optionally retain failed worktree, suggest running dependency analysis on conflicts
- **Stale Branches**: How does system handle when release branch is outdated? Tool MUST fetch latest before cherry-picking
- **Invalid PR Numbers**: What happens with non-existent or non-merged PRs? Tool MUST validate PR state before attempting cherry-pick
- **Label Mismatches**: What if backport commit title differs from original? Relabeling tool MUST warn and allow override via flag
- **Concurrent Execution**: What happens if tool is run multiple times simultaneously? Worktree isolation with timestamp-based naming prevents conflicts; each run gets separate worktree
- **Circular Dependencies**: What if dependency analysis finds circular file modification patterns? Tool reports all PRs in the cycle; maintainer must manually determine safe backport order or backport as a group

## Requirements *(mandatory)*

### Functional Requirements

#### Cherry-Pick Tool (gen_cherrypick_prs.py)

- **FR-001**: Tool MUST create one cherry-pick PR per original merged PR
- **FR-002**: Tool MUST process PRs in merge order on `main` determined by the first-parent commit order of `main` (i.e., the order commits appear in `git rev-list --first-parent <main>`). If ordering is ambiguous/unavailable, the tool SHOULD print a warning and proceed using `mergedAt` and then PR number as tiebreakers.
- **FR-003**: Tool MUST fetch the latest target branch (`release/X.Y.Z` or `staging/X.Y.Z`) before creating cherry-pick branches
- **FR-004**: Tool MUST detect existing backport PRs and skip duplicates
- **FR-005**: Tool MUST stop immediately on cherry-pick conflicts without creating PRs
- **FR-006**: Tool MUST support both explicit PR number lists and automatic label-based discovery
- **FR-007**: Tool MUST preserve original PR title and body with added cherry-pick reference
- **FR-008**: Tool MUST support `--dry-run` mode showing what would be done without making changes
- **FR-009**: Tool MUST require interactive confirmation by default before creating each PR. Tool MUST support `--no-confirm` flag to skip confirmation for CI/automation scenarios
- **FR-010**: Tool MUST handle forked repositories with separate base/push remotes
- **FR-023**: Tool MUST use git worktrees to isolate all cherry-pick operations from main working directory
- **FR-024**: Tool MUST automatically cleanup temporary worktrees on successful completion; retain on conflicts/errors with clear instructions
- **FR-025**: Tool MUST support `--keep-worktree` flag to retain worktree even on success (for debugging/inspection)
- **FR-026**: Tool MUST support `--force-cleanup` flag to cleanup worktree even on conflicts (for CI/automation scenarios)
- **FR-027**: Tool MUST provide clear path and cleanup instructions when worktree is retained after failure

#### Relabeling Tool (relabel_backported.py)

- **FR-011**: Tool MUST identify PRs with `backport_X` labels that have been backported to `release/X`
- **FR-012**: Tool MUST update labels from `backport_X` to `backported_X` on successful backports
- **FR-013**: Tool MUST add comment to original PR with link to backport PR
- **FR-014**: Tool MUST detect commit references by PR number, URL, or title
- **FR-015**: Tool MUST warn when commit title doesn't match original PR title
- **FR-016**: Tool MUST support `--force-update-pr` to override warnings for specific PRs
- **FR-017**: Tool MUST run in dry-run mode by default (require `--update` flag for actual changes)

#### Staging Branch Support

- **FR-018**: Tools MUST support `staging/X.Y.Z` branches using same workflows as `release/X.Y.Z` branches (staging is pre-release gating step in closed-source ingestion)
- **FR-019**: Tools MUST use same label convention for both staging and release branches (e.g., `backport_1.7.2511` applies to both `staging/1.7.2511` and `release/1.7.2511`; target branch specified via command-line argument)

#### Dependency Analysis Tool (analyze_pr_deps.py)

- **FR-028**: Tool MUST identify all merged PRs in main that modified a given file but are NOT present in target branch
- **FR-029**: Tool MUST order results by merge date (oldest first) to show potential prerequisite order
- **FR-030**: Tool MUST detect when a prerequisite PR has an open cherry-pick PR and warn user to wait
- **FR-031**: Tool MUST support filtering by date range (e.g., `--merged-after YYYY-MM-DD`) to focus on recent changes
- **FR-032**: Tool MUST accept either `--file <path>` or `--pr <number>` as input (for file-based or PR-based analysis)
- **FR-033**: Tool MUST detect original merge commit presence in target branch using git ancestry checks (not just label scanning). Note: checks whether the original merge commit from `main` (or its cherry-pick equivalent) is reachable from the target branch
- **FR-034**: Tool MUST output actionable recommendations: "Backport PR #X first" or "Wait for cherry-pick PR #Y to merge"

#### Backport Status Tool (backport_status)

- **FR-035**: Tool MUST display counts and lists of PRs in each backport state: pending (labeled `backport_X`), completed (labeled `backported_X`), in-progress (open cherry-pick PRs), blocked (conflicts detected)
- **FR-036**: Tool MUST accept version (e.g., `1.7.2511`) and optionally `--branch` to filter by specific target
- **FR-037**: Tool MUST support `--pr {number}` to show backport status of specific PR
- **FR-038**: Status and dependency analysis tools MUST be accessible to any repository user with read access (read-only operations, no special permissions required). Cherry-pick and relabel tools have separate permission requirements (see User Roles section)
- **FR-039**: Tool MUST include links to original PRs, cherry-pick PRs, and Label pages
- **FR-040**: Tool MUST run in under 5 seconds for typical repositories

#### Workflow Wrapper (backport_workflow.py)

- **FR-020**: Wrapper MUST sequence cherry-pick → status check → relabeling
- **FR-021**: Wrapper MUST detect incomplete cherry-pick PRs and warn before relabeling
- **FR-022**: Wrapper MUST provide progress summary at each stage

### Output Formats

- **FR-041**: All tools MUST print a human-readable summary to stdout by default.
- **FR-042**: All tools MUST support a `--json` flag that emits a stable, machine-readable JSON object (intended for scripting and tests). The exact JSON schema can evolve, but fields SHOULD be added in a backwards-compatible way.

### Constitution Compliance

**Security & Trust Boundaries**: 
- These are repository automation scripts that rely on GitHub API and git as authoritative sources, but treat their outputs as external/untrusted inputs for robustness. Tools MUST defensively validate/parse responses and emit actionable errors on unexpected/malformed data (no crashes/panics).
- Input validation: PR numbers, branch names, and label patterns MUST be validated against safe patterns (no command injection via subprocess calls)
- All subprocess calls use list arguments (not shell=True) to prevent injection attacks
- No `unsafe` Rust code required (Python scripts)

**Testing**: 
- Unit tests for each tool in `repo_support/tests/test_*.py`
- Integration tests using temporary git repositories with mock PRs
- Manual testing checklist in PR description for real repository scenarios
- Tests run via `python -m pytest repo_support/tests/`

**Documentation**: 
- Module-level docstrings with usage examples in each script
- README in `repo_support/` with complete workflow guide
- Guide page at `Guide/src/dev_guide/pr_management.md`
- Each tool MUST have `--help` with examples

**Build/Cross-platform**: 
- Python 3.11+ required (specify in README)
- Requires `git` and `gh` CLI installed and authenticated
- Works on Linux, macOS, Windows (via WSL2 or native Python)
- No platform-specific build steps required

### Key Entities

- **Original PR**: A merged PR on `main` branch that needs backporting
- **Original Merge Commit**: The squash-merge commit on `main` created when the original PR was merged. Identified by `mergeCommit.oid` from the GitHub API. This is the commit that gets cherry-picked onto the target branch.
- **Cherry-Pick Commit**: The new commit created on the target branch as a result of cherry-picking the original merge commit. Has a different OID than the original merge commit.
- **Backport Label**: GitHub label (e.g., `backport_1.7.2511`) indicating target release/staging branch
- **Cherry-Pick Branch**: Temporary branch created from release branch containing the cherry-pick commit
- **Cherry-Pick PR**: New PR created from cherry-pick branch targeting release/staging branch
- **Backport Commit**: Commit in release/staging branch that references original PR (synonym for cherry-pick commit after PR merge)
- **Completion Label**: GitHub label (e.g., `backported_1.7.2511`) indicating successful backport
- **Prerequisite PR**: A PR that modified the same files as target PR but hasn't been backported to target branch (potential cause of conflicts)
- **Dependency Chain**: Ordered sequence of PRs that must be backported together or in specific order due to file modifications
- **Worktree**: Isolated git working directory in `.git/worktrees/` used for cherry-pick operations

## Success Criteria *(mandatory)*

### Measurable Outcomes

- **SC-001**: Tools automate repetitive cherry-pick steps (branch creation, PR creation, label updates) reducing manual command entry and avoiding order mistakes
- **SC-002**: Cherry-pick tool detects and skips 100% of already-backported PRs without errors
- **SC-003**: Tool stops immediately on first conflict with clear summary, preventing creation of conflicted PRs
- **SC-004**: Relabeling tool correctly updates labels and comments for 95%+ of backported PRs without manual intervention
- **SC-005**: All tools provide actionable error messages that allow maintainers to resolve issues without code inspection
- **SC-006**: Workflow wrapper reduces number of commands from 6+ to 2 or fewer for complete backport cycle
- **SC-007**: Tools work correctly with both upstream repository and forked repositories (cross-repo PRs)
- **SC-008**: Dependency analysis tool identifies missing prerequisite PRs in under 30 seconds for files with 100+ PR modifications
- **SC-009**: Main worktree remains untouched during cherry-pick operations (100% isolation via worktrees)
- **SC-010**: When conflicts occur, maintainers can identify root cause (missing prerequisites) in under 5 minutes using analyze_pr_deps

## Clarifications

### Session 2026-02-06

- Q: Working Directory Isolation Strategy - How should the tool isolate cherry-pick operations from active development work? → A: Git Worktrees (Option B) - Tool uses `git worktree add` to create isolated workspace in `.git/worktrees/backport-temp-<timestamp>/` for all cherry-pick operations, allowing dev to continue working in main worktree uninterrupted
- Q: Post-Execution State Management - What should tool do with temporary worktrees after completion? → A: Option B with user control flags - Auto-cleanup on success, retain on failure with instructions. Add `--keep-worktree` flag (never cleanup for debugging) and `--force-cleanup` flag (always cleanup even on conflict for CI/automation)
- Q: Branch Naming for Staging vs Release - Should branch naming differentiate between staging and release targets? → A: Keep uniform naming - Use same pattern `{prefix}/{sanitized-target}/pr-{number}` for both (simple, consistent, scriptable)
- Q: Manual Conflict Resolution Workflow - Should tool help resume after manual conflict resolution? → A: No resume support (Option A modified) - Tool errors out with clear summary of conflict, paths to worktree, and suggestions. User resolves manually. Separate dependency analysis tool will help users understand why conflicts occur (missing prerequisite PRs).
- Q: Label Convention for Staging vs Release - Do staging and release branches use different labels? → A: No - Same label `backport_X.Y.Z` applies to both `staging/X.Y.Z` and `release/X.Y.Z`. Maintainer specifies target branch explicitly via command-line argument (not inferred from label).
- Q: User Access & Roles - Should all users be able to run these tools? → A: Yes - All tools accessible to any repository user with basic git/gh CLI access. Status tool requires only read permissions. Cherry-pick tool requires write access (to create branches/PRs). Relabeling tool requires write access. Staging→release promotion workflow is maintainer-specific (future workflow wrapper enhancement).

## User Roles & Permission Model

### Any User (Read Access to Repository)

Users with read access to `microsoft/openvmm` can:

- **Run**: `backport_status` - View current backport status across all branches (read-only, no write access needed)
- **Run**: `analyze_pr_deps` - Analyze prerequisites for any file or PR (read-only, queries git history and GitHub API)

### Contributors (Fork Write Access)

Users who can push to their own fork of `microsoft/openvmm` can:

- **Run**: `gen_cherrypick_prs` - Create cherry-pick PRs. The tool pushes a cherry-pick branch to the user's fork and opens a PR targeting `microsoft/openvmm` release/staging branches. Requires: push access to own fork, ability to open PRs to upstream.

### Maintainers (Write Access to `microsoft/openvmm`)

Users with write access to the `microsoft/openvmm` repository can additionally:

- **Run**: `relabel_backported.py` - Update labels on merged PRs in `microsoft/openvmm` (requires: label management permission on the upstream repo)

### Maintainers (Admin/Triage Access)

Maintainers additionally control:

- **Release gating**: Approve or promote `staging/X.Y.Z` → `release/X.Y.Z` (policy governance)
- **Label strategy**: Define which labels apply to which branches (future config system)
- **Concurrent backport coordination**: Manage overlapping backport efforts across multiple versions
- **Conflict resolution policy**: Document prerequisites and manual resolution steps
- **Tooling governance**: Update shared utilities, error message standards, documentation

**Maintainer-specific workflows**: Future updates may include maintainer-only commands for promotion and policy management. For now, all technical tools are user-accessible; governance decisions are made offline.

## Assumptions

1. **GitHub CLI**: Users have `gh` CLI installed and authenticated
2. **Git Configuration**: Local git repository has correct remotes configured (`upstream` for base, `origin` for fork)
3. **Permissions**: Users have appropriate access for their role (read for status/analysis, fork push for cherry-pick, upstream write for relabel)
4. **Label Conventions**: Repository follows single label convention `backport_X.Y.Z` and `backported_X.Y.Z` for both release and staging branches; target branch is specified explicitly via command-line argument
5. **Squash Merges**: PRs are squash-merged (tool relies on `mergeCommit.oid` from GitHub API)
6. **Working Directory Isolation**: Tool uses git worktrees to isolate operations (does NOT require clean working tree in main worktree)

## Dependencies

- Existing tool: `repo_support/relabel_backported.py` (will be enhanced/refactored as needed)
- In-progress PR #2680: `repo_support/gen_cherrypick_prs.py` (will be completed and merged with worktree isolation)
- New tool: `repo_support/analyze_pr_deps.py` (will be created for dependency analysis)
- GitHub CLI (`gh`) for PR operations and queries
- Git for branch, cherry-pick, and worktree operations
- Python 3.11+ with standard library (subprocess, json, argparse, datetime, re)

## Documentation Plan

### Required Documentation

1. **repo_support/README.md**: Complete guide to all branch management tools
   - Prerequisites and setup (git, gh CLI, Python 3.11+)
   - Usage examples for each tool (gen_cherrypick_prs, relabel_backported, analyze_pr_deps)
   - Complete workflow walkthrough (including conflict resolution with dependency analysis)
   - Troubleshooting common issues

2. **Guide/src/dev_guide/pr_management.md**: Conceptual guide to PR lifecycle
   - Branch strategy (main → staging/X.Y.Z → release/X.Y.Z)
   - Labeling conventions (backport_X, backported_X, staging variants)
   - When to use which tool (cherry-pick automation, dependency analysis, relabeling)
   - Manual vs automated workflows
   - Handling conflicts: using analyze_pr_deps to find missing prerequisites

3. **Script docstrings**: Module-level documentation in each .py file
   - Purpose and scope
   - Command-line examples with common scenarios
   - Return codes and error handling
   - Worktree isolation and cleanup behavior

4. **PR description template**: Standard template for backport PRs
   - Reference to original PR
   - Changes from clean cherry-pick (or conflict resolution notes)
   - Testing notes
   - Prerequisite PR references (if applicable)

All documentation will be included in the implementation PR. Missing documentation will block PR merge per OpenVMM Constitution.

## Future Enhancements (Post-MVP)

- **API Resilience**: Add retry logic with exponential backoff for transient GitHub API failures and 429 rate-limit responses. Not required for MVP since tools run interactively and users can simply re-run on transient failures.
