# Data Model: PR Branch Management Tools

**Phase**: 1 (Design) | **Status**: Complete | **Date**: 2026-02-06

## User Roles & Access Patterns

### General Users (Read-Only Access)

- **backport_status.py**: View-only access to all backport information
- Operations: Only query GitHub API and local git
- No modifications to branches, PRs, or labels

### Users with Write Access

- **backport_status.py**: Same as general users (read-only)
- **gen_cherrypick_prs.py**: Create cherry-pick PRs and branches
- **analyze_pr_deps.py**: Query PRs and dependencies (read-only analysis)
- **relabel_backported.py**: Modify labels on merged PRs
- **backport_workflow.py**: Orchestrate full workflow

### Maintainers (Governance Role)

Additionally responsible for:
- Release strategy and branch management
- Label convention definitions
- Staging→release promotion decisions
- Conflict resolution policy documentation

## Core Entities

### 1. PullRequest
**Represents**: A GitHub PR on the main branch to be backported

**Fields**:
- `number` (int, required): GitHub PR number (e.g., 2680)
- `title` (str, required): Original PR title from main branch
- `body` (str, required): Original PR description
- `mergeCommit` (str, required): Merge commit SHA from main branch
- `mergedAt` (datetime, required): Merge timestamp (for ordering)
- `labels` (list[str], optional): GitHub labels on PR
- `author` (str, required): GitHub username of PR author

**Validation Rules**:
- `number` must match regex `^[0-9]+$`
- `mergeCommit` must be valid git SHA (length >= 7)
- `mergedAt` must be ISO 8601 datetime
- Only merged PRs are valid (state must be "merged")

**Source**: GitHub API via `gh pr view {pr_number} --json`

---

### 2. Branch
**Represents**: Git branch (main, release/X.Y.Z, or staging/X.Y.Z)

**Fields**:
- `name` (str, required): Full branch name (e.g., "main", "release/1.7.2511")
- `type` (enum: "main" | "release" | "staging", required): Branch category
- `version` (str, required if type != "main"): Release version (e.g., "1.7.2511")
- `latestCommit` (str, required): Current HEAD commit SHA
- `lastSync` (datetime, optional): When branch was last fetched locally

**Validation Rules**:
- `name` matches regex `^(main|release|staging)/[0-9.]+$` or `^main$`
- `version` matches regex `^[0-9.]+$` when type != "main"
- `latestCommit` must be valid git SHA
- Must exist in repository

**Source**: Git operations (`git rev-parse origin/{branch}`)

---

### 3. BackportLabel
**Represents**: GitHub label indicating a PR needs backporting (e.g., "backport_1.7.2511")

**Fields**:
- `pattern` (str, required): Label format "backport_{version}" (e.g., "backport_1.7.2511")
- `version` (str, required): Extracted version (e.g., "1.7.2511")
- `targetBranches` (list[Branch], required): Both `release/{version}` and `staging/{version}` (dynamically determined by CLI argument)

**Validation Rules**:
- Label matches regex `^backport_[0-9.]+$`
- Version extracted from label must be valid semver-like pattern `^[0-9.]+$`

**Source**: GitHub label on merged PRs

---

### 4. CherrryPickOperation
**Represents**: Single attempt to cherry-pick one PR to a target branch

**Fields**:
- `id` (str): Unique timestamp-based ID for traceability (e.g., "backport-1.7.2511-2680-20260206T143022Z")
- `sourcePR` (PullRequest, required): Original PR to cherry-pick
- `targetBranch` (Branch, required): Target (release or staging)
- `worktreePath` (str, required): Path to isolated git worktree (e.g., ".git/worktrees/backport-temp-20260206T143022Z/")
- `cherryPickBranch` (str, required): Cherry-pick branch name in worktree (e.g., "backport/1-7-2511/pr-2680")
- `status` (enum: "pending" | "success" | "conflict" | "skipped", required): Current state
- `conflictedFiles` (list[str], optional): Filenames with conflicts (if status="conflict")
- `createdAt` (datetime, required): When operation started
- `completedAt` (datetime, optional): When operation finished

**Validation Rules**:
- `id` format: `backport-{version}-{pr_number}-{timestamp}`
- `worktreePath` must be under `.git/worktrees/`
- `status` transitions: pending → (success | conflict | skipped) [one-way]
- `conflictedFiles` only populated when status="conflict"

**State Transitions**:
```
pending ──→ success (cherry-pick succeeded, PR created)
        ├─→ conflict (cherry-pick hit conflicts, worktree retained)
        └─→ skipped (PR already backported, no action needed)
```

---

### 5. BackportPR
**Represents**: New PR created on release/staging branch to merge cherry-picked changes

**Fields**:
- `number` (int, required): New PR number on target branch
- `title` (str, required): Cherry-pick PR title (original PR title + cherry-pick reference)
- `body` (str, required): Cherry-pick PR body (original body + "Cherry-picked from #{original_pr_number}")
- `targetBranch` (Branch, required): Target branch (release or staging)
- `cherryPickCommit` (str, required): Commit SHA of cherry-picked changes
- `sourceOperation` (CherryPickOperation, required): Reference to operation that created it
- `status` (enum: "draft" | "open" | "merged" | "closed", required): PR state
- `createdAt` (datetime, required): When PR was created
- `mergedAt` (datetime, optional): When PR was merged

**Validation Rules**:
- `number` must be integer >= 1
- `title` must include reference to source PR (e.g., "Feature: foo (cherry-pick from #2680)")
- Body must include cherry-pick marker comment
- `targetBranch` type must be "release" or "staging"

**Source**: Created by gen_cherrypick_prs.py via `gh pr create`

---

### 6. BackportLabel_Applied
**Represents**: Tracking that a PR has been marked for backport

**Fields**:
- `pr` (PullRequest, required): PR marked for backport
- `label` (BackportLabel, required): Backport label applied
- `appliedAt` (datetime, required): When label was added
- `appliedBy` (str, required): GitHub user who added the label

**Validation Rules**:
- `pr` must be merged
- `label` must follow backport pattern

---

### 7. CompletionLabel
**Represents**: Label applied after successful backport (e.g., "backported_1.7.2511")

**Fields**:
- `pattern` (str, required): Label format "backported_{version}"
- `version` (str, required): Extracted version
- `appliedTo` (PullRequest, required): Original PR now marked as backported
- `backportPR` (BackportPR, required): PR that completed the backport
- `appliedAt` (datetime, required): When label was added
- `appliedBy` (str, required): User/tool that applied label

**Validation Rules**:
- Label matches regex `^backported_[0-9.]+$`
- `backportPR` must be merged to target branch
- Cannot apply completion label until backport PR is merged

---

### 8. FileDependency
**Represents**: Dependency relationship between PRs based on file modifications

**Field**:
- `file` (str, required): File path (e.g., "src/foo.rs")
- `pr1` (PullRequest, required): First PR that modified file
- `pr2` (PullRequest, required): Second PR that also modified file
- `pr1MergedAt` (datetime, required): When PR1 was merged
- `pr2MergedAt` (datetime, required): When PR2 was merged
- `pr1InTarget` (bool, required): Whether PR1's commit is in target branch
- `pr2InTarget` (bool, required): Whether PR2's commit is in target branch

**Validation Rules**:
- Both PRs must be merged to main
- At least one PR must be missing from target (for dependency analysis)
- File path must exist in repository

**Usage**: Used by analyze_pr_deps.py to identify prerequisite PRs

---

### 9. DependencyChain
**Represents**: Ordered sequence of PRs that must be backported together

**Fields**:
- `prs` (list[PullRequest], required): PRs in backport order
- `reason` (str, required): Why they must be together (e.g., "all modify src/foo.rs")
- `orderedBy` (str, required): Field used for ordering (e.g., "mergedAt")

**Validation Rules**:
- All PRs in chain touch same file(s) or have explicit dependency
- PRs ordered by merge date (oldest first)
- At least 2 PRs in valid chain

---

## State Diagrams

### PR Lifecycle

```
main branch       │  release/staging branch
────────────────┼─────────────────────
[Merged PR]      │
    ↓            │
[backport_X added]   │
    ↓            │
[gen_cherrypick_prs triggered]
    ├─→ [Cherry-pick created] → [Cherry-pick PR #N] → [Merged] → [backported_X added]
    ├─→ [Conflict detected] ──→ [Worktree retained for investigation]
    └─→ [Skip: already backported]
```

### Cherry-Pick Operation States

```
[CherryPickOperation: pending]
   ├─(git worktree add)──────→ [worktree created]
   ├─(git cherry-pick)────────→ SUCCESS: [create PR, delete worktree]
   │                          │   └─→ [status=success]
   │
   ├──────────────────────────→ CONFLICT: [retain worktree, output summary]
   │                              └─→ [status=conflict]
   │
   └──────────────────────────→ SKIP: [PR already merged to target]
                                  └─→ [status=skipped]
```

## Relationships

**Ownership/References**:
- CherryPickOperation owns a Worktree
- CherryPickOperation references SourcePR and TargetBranch
- BackportPR references CherryPickOperation that created it
- BackportLabel_Applied references PullRequest and BackportLabel
- CompletionLabel references original PullRequest and BackportPR
- FileDependency links two PRs by file modifications

**Cardinality**:
- 1 PullRequest → 0..N CherryPickOperation (can retry)
- 1 CherryPickOperation → 0..1 BackportPR (only success creates PR)
- 1 PullRequest → 1 BackportLabel_Applied (when marked for backport)
- 1 PullRequest → 0..1 CompletionLabel (when backport complete)
- 1 File → N FileDependency (tracked by multiple PRs)

## Constraints & Invariants

**Mutual Exclusivity**:
- CherryPickOperation status is singular (pending, success, conflict, or skipped)
- PullRequest cannot be on both main and release (exclusive branches)

**Ordering**:
- BackportLabel must apply before CherryPickOperation
- CompletionLabel applies only after BackportPR is merged
- CherryPickOperations must respect DependencyChain order

**Immutability**:
- PullRequest.mergeCommit never changes (immutable once merged)
- BackportLabel application date is immutable
- CherryPickOperation timestamps are immutable

**Referential Integrity**:
- BackportPR.sourceOperation must reference valid CherryPickOperation
- CompletionLabel.backportPR must reference merged BackportPR
- FileDependency must reference real merged PRs in main
