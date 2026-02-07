# API Contract: gen_cherrypick_prs.py

**Tool**: Cherry-Pick PR Generation  
**Language**: Python 3.11+  
**Status**: In Progress (PR #2680)

## CLI Interface

### Command Format

```bash
gen_cherrypick_prs.py <target_branch> [--from-backport-label LABEL | pr_numbers [pr_numbers ...]]
                      [--dry-run] [--no-confirm] [--keep-worktree] [--force-cleanup] [--repo OWNER/REPO]
```

### Arguments

**Positional**:
- `target_branch` (str, required): Target branch for cherry-pick PRs (e.g., `release/1.7.2511` or `staging/1.7.2511`)
  - Validation: Must match regex `^(release|staging)/[0-9.]+$`

**PR Selection** (mutually exclusive):
- `--from-backport-label LABEL` (str): Automatically find all merged PRs labeled with LABEL on main and cherry-pick in merge order
  - Example: `--from-backport-label backport_1.7.2511`
  - Validation: Label must match regex `^backport_[0-9.]+$`
  
- `pr_numbers` (list[int], variadic): Explicit list of PR numbers to cherry-pick
  - Example: `2567 2525 2533`
  - Validation: Each must be integer >= 1, must be merged PRs
  - Behavior: Tool will sort by merge date regardless of input order

**Options**:
- `--dry-run` (flag): Show what would be done without making any changes or creating worktrees
  - Output: YAML or JSON summary of PRs that would be processed
  - Side-effect: No changes to git, no worktrees created
  
- `--no-confirm` (flag): Skip interactive confirmation before creating each PR
  - Behavior: Create PRs without prompts (use with caution)
  - Typical use: CI/automation scenarios
  
- `--keep-worktree` (flag): Retain worktree even on successful cherry-pick (for debugging)
  - Behavior: Worktree left in place with cherry-pick branch checked out
  - Responsibility: User must cleanup manually with `git worktree remove`
  
- `--force-cleanup` (flag): Always cleanup worktrees even on conflicts (for CI/automation)
  - Behavior: Removes all temporary worktrees before exiting
  - Side-effect: Loses conflict state for investigation (use carefully)
  
- `--repo OWNER/REPO` (str): Non-standard repository (fork)
  - Example: `--repo mattkur/openvmm` instead of default `microsoft/openvmm`
  - Validation: Must match regex `^[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+$`
  
- `--help` / `-h` (flag): Show detailed help with examples

---

## Data Contract: Input/Output

### Input Data

**Via CLI Arguments**:
- Target branch name (validated)
- PR numbers OR backport label (validated)
- Flags for behavior control

**Via GitHub API** (queried by tool):
```json
{
  "pullRequest": {
    "number": 2680,
    "title": "Feature: Add worktree support",
    "body": "This PR adds...",
    "mergeCommit": {
      "oid": "a1b2c3d4e5f6..."
    },
    "mergedAt": "2026-02-05T14:30:00Z",
    "author": {
      "login": "octocat"
    },
    "labels": [
      {
        "name": "backport_1.7.2511"
      }
    ]
  }
}
```

### Output Data

**Stdout (Normal Case)** - YAML summary:
```yaml
targetBranch: release/1.7.2511
prsToProcess:
  - number: 2567
    title: "Fix: Handle edge case"
    mergedAt: "2026-02-01T10:00:00Z"
    status: "processing"
  - number: 2680
    title: "Feature: Add worktree support"
    mergedAt: "2026-02-05T14:30:00Z"
    status: "processing"

processingResults:
  - prNumber: 2567
    status: "success"
    newPRNumber: 2800
    newPRURL: "https://github.com/microsoft/openvmm/pull/2800"
  - prNumber: 2680
    status: "conflict"
    conflictedFiles:
      - "src/foo.rs"
      - "src/bar.rs"
    worktreePath: "/home/user/openvmm/.git/worktrees/backport-temp-20260206T143022Z"
    nextSteps:
      - "Investigate: analyze-pr-deps --file src/foo.rs --target release/1.7.2511"
      - "Resolve conflicts manually in worktree"
      - "Cleanup: git worktree remove /path/to/worktree"

summary:
  totalRequested: 2
  successful: 1
  conflicts: 1
  skipped: 0
  elapsedSeconds: 42
```

**Stdout (Conflict Case)**:
```
ERROR: Cherry-pick conflict detected

PR #2680: Feature: Add worktree support
Conflicted files:
  • src/foo.rs
  • src/bar.rs

This usually means another PR modified these files but hasn't been backported yet.

Worktree retained at: .git/worktrees/backport-temp-20260206T143022Z/

To investigate:
  analyze-pr-deps --file src/foo.rs --target release/1.7.2511

To cleanup:
  git worktree remove .git/worktrees/backport-temp-20260206T143022Z/
```

**Stdout (Dry-Run)**:
```yaml
dryRun: true
targetBranch: release/1.7.2511
wouldProcess:
  - number: 2567
  - number: 2680
  - number: 2525
message: "Use without --dry-run to actually create cherry-pick PRs"
```

### Return Codes

| Code | Meaning |
|------|---------|
| 0 | All PRs processed successfully (no conflicts) |
| 1 | One or more PRs encountered conflicts (at least one worktree retained) |
| 2 | Invalid arguments or preconditions not met (e.g., target branch doesn't exist) |
| 3 | GitHub API error (auth failure, rate limit, PR not found) |

---

## Behavior Specification

### Phase 1: Validation
1. Validate `target_branch` format and existence in remote
2. Validate PR numbers format (if explicit) or label format (if label-based)
3. Fetch latest target branch from remote: `git fetch origin {target_branch}`

### Phase 2: PR Discovery
1. If `--from-backport-label` provided: Query GitHub for all merged PRs with that label
2. If PR numbers provided: Validate each exists and is merged
3. Sort PRs by `mergedAt` (ascending = oldest first)

### Phase 3: Duplicate Detection
1. For each PR: Check if merge commit already in target branch
   ```bash
   git merge-base --is-ancestor {merge_commit} origin/{target_branch}
   ```
2. If ancestor (already backported): Mark as "skipped", continue
3. Output summary of skipped PRs

### Phase 4: Interactive Confirmation
1. Display summary: "Will create N cherry-pick PRs..."
2. If NOT `--no-confirm`: Prompt "Proceed? [y/n]: "
3. If "n": Exit cleanly with code 0

### Phase 5: Cherry-Pick Loop
For each PR (excluding skipped):
1. **Create worktree** with isolation:
   ```bash
   git worktree add .git/worktrees/backport-temp-{timestamp} origin/{target_branch}
   ```
2. **Cherry-pick commit** in isolated worktree:
   ```bash
   git -C {worktree_path} cherry-pick {merge_commit_oid}
   ```
3. **Conflict detection**:
   - If cherry-pick succeeds: Proceed to PR creation
   - If conflicts detected: Stop, output summary, retain worktree, continue to next PR (or exit if `--force-cleanup`)
4. **Create cherry-pick branch**:
   ```bash
   git -C {worktree_path} checkout -b backport/{target_version}/pr-{pr_number}
   ```
5. **Create PR with gh CLI**:
   ```bash
   gh pr create --repo {repo} \
     --base {target_branch} \
     --head {pr_number} \
     --title "{original_title} (cherry-pick from #{pr_number})" \
     --body "Cherry-picked from #{pr_number}
     
     Original: [Link to original PR]" \
     --draft
   ```
6. **Cleanup**: If success and NOT `--keep-worktree`:
   ```bash
   git worktree remove {worktree_path}
   ```

### Phase 6: Summary Output
1. Aggregate results: successful PRs, conflicts, skipped
2. Output YAML/JSON summary
3. Provide next steps for conflicts (suggest `analyze-pr-deps`)

---

## Error Handling

### Pre-execution Errors (Return Code 2)

- Invalid branch name: "Branch must match pattern 'release/X.Y.Z' or 'staging/X.Y.Z'"
- Target branch doesn't exist: "Branch 'release/1.7.2511' not found in remote"
- Invalid PR number: "PR number must be integer >= 1, got: 'abc'"
- Invalid label: "Label must follow 'backport_X.Y.Z' pattern, got: 'backport-staging'"

### GitHub API Errors (Return Code 3)

- Authentication failure: "GitHub CLI not authenticated. Run: gh auth login"
- Rate limit exceeded: "GitHub API rate limit exceeded. Wait {minutes} minutes and retry"
- PR not found: "PR #{number} not found in repo {repo}"
- PR not merged: "PR #{number} is not merged. Only merged PRs can be backported"

### Cherry-pick Errors (Return Code 1)

- Conflict detected: Output summary with worktree path and next steps
- Empty cherry-pick: "PR #{number} commit already in target branch (skipped)"

---

## Testing Strategy

**Unit Tests** (`repo_support/tests/test_gen_cherrypick_prs.py`):
- Input validation tests (invalid PR numbers, branch names, labels)
- GitHub API mocking (use `requests_mock` to stub API responses)
- Branch name format validation
- Worktree path generation and isolation

**Integration Tests** (temporary test repo scenarios):
- Clean cherry-pick (no conflicts)
- Cherry-pick with conflicts
- Duplicate detection (PR already backported)
- Multiple PRs in correct order handling
- `--dry-run` mode (no side effects)
- `--keep-worktree` flag behavior
- `--force-cleanup` flag behavior

**Manual Tests** (documented in PR description):
- Real repository: Backport 3-5 small PRs to release branch
- Conflict scenario: Attempt backport that will conflict, verify worktree retention
- Verify cherry-pick PRs appear on GitHub with correct title/body
