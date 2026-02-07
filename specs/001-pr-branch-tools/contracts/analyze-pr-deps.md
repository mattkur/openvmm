# API Contract: analyze_pr_deps.py

**Tool**: Dependency Analysis for Conflict Investigation  
**Language**: Python 3.11+  
**Status**: New

## CLI Interface

### Command Format

```bash
analyze_pr_deps.py --file FILE --target BRANCH [--merged-after DATE] [--repo OWNER/REPO]
# OR
analyze_pr_deps.py --pr PR_NUMBER --target BRANCH [--repo OWNER/REPO]
```

### Arguments

**Input Selection** (mutually exclusive):
- `--file FILE` (str): Analyze which PRs modified this file
  - Example: `--file src/foo.rs`
  - Validation: File path must exist in repository
  
- `--pr PR_NUMBER` (int): Analyze which PRs are prerequisites for this PR
  - Example: `--pr 2680`
  - Validation: Must be integer >= 1, PR must exist

**Required**:
- `--target BRANCH` (str): Check against this target branch
  - Example: `--target release/1.7.2511`
  - Validation: Must match regex `^(release|staging)/[0-9.]+$`

**Options**:
- `--merged-after DATE` (str): Only consider PRs merged after this date
  - Format: `YYYY-MM-DD` (ISO format)
  - Example: `--merged-after 2026-01-01`
  - Use case: Focus on recent changes affecting the file
  
- `--repo OWNER/REPO` (str): Non-standard repository
  - Validation: Must match regex `^[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+$`
  
- `--help` / `-h` (flag): Show detailed help

---

## Data Contract: Input/Output

### Input Data

**Via CLI Arguments**:
- File path or PR number (one or the other)
- Target branch
- Optional date filter

**Via GitHub API & Git** (queried by tool):
- All merged PRs to main that touched the file
- Timestamps of those PRs
- Which PRs are already in the target branch

### Output Data

**Stdout (File-Based Analysis)**:
```yaml
analysis:
  fileAnalyzed: "src/foo.rs"
  targetBranch: "release/1.7.2511"
  
prerequisites:
  - prNumber: 2567
    title: "Fix: Handle edge case"
    mergedAt: "2026-02-01T10:00:00Z"
    status: "missing_from_target"
    reason: "Merged to main but commit not in release/1.7.2511"
    recommendation: "Backport PR #2567 first"
    
  - prNumber: 2345
    title: "Refactor: Extract utility function"
    mergedAt: "2026-01-15T08:30:00Z"
    status: "missing_from_target"
    reason: "Merged to main but commit not in release/1.7.2511"
    recommendation: "Backport PR #2345 first"
    
  - prNumber: 2100
    title: "Add dependency"
    mergedAt: "2026-01-10T14:00:00Z"
    status: "in_target"
    reason: "Already backported to release/1.7.2511"
    
  - prNumber: 2680
    title: "Add worktree support (cherry-pick from #2680)"
    mergedAt: "2026-02-05T14:30:00Z"
    status: "open_cherry_pick"
    openCherryPickPR: 2850
    reason: "Cherry-pick PR #2850 is open - wait for merge before backporting other PRs"
    recommendation: "Wait for #2850 to merge, then backport dependent PRs"

summary:
  totalPRsTouchingFile: 4
  missingFromTarget: 2
  alreadyBackported: 1
  pendingBackport: 1
  backportOrder: ["2345", "2567", "2680"]
  message: "Backport in order: #2345 → #2567 → #2680 to avoid conflicts"
```

**Stdout (PR-Based Analysis)**:
```yaml
analysis:
  prAnalyzed: 2680
  prTitle: "Feature: Add worktree support"
  targetBranch: "release/1.7.2511"
  
filesModified:
  - "src/foo.rs"
  - "src/bar.rs"
  - "tests/test_foo.rs"
  
prerequisites:
  # Lists all PRs that touched same files but aren't in target
  - prNumber: 2567
    status: "missing_from_target"
    # ... (same as file-based analysis)

summary:
  filesAnalyzed: 3
  totalPrerequisites: 2
  backportOrder: ["2345", "2567", "2680"]
```

**Return Codes**:
| Code | Meaning |
|------|---------|
| 0 | Analysis complete; output provided (may show prerequisites needed) |
| 1 | File not found in repository |
| 2 | Invalid arguments |
| 3 | GitHub API error |

---

## Behavior Specification

### Phase 1: Input Validation
1. Validate `--target` branch format and existence
2. If `--file`: Verify file exists in repository
3. If `--pr`: Verify PR exists and is merged to main
4. If `--merged-after`: Parse as ISO date

### Phase 2: File Identification
- **If `--file` provided**: Use directly
- **If `--pr` provided**: Query GitHub for files changed in PR:
  ```bash
  gh pr view {pr_number} --json files --jq '.files[].path'
  ```

### Phase 3: PR Discovery
1. Query all merged PRs to main:
   ```bash
   gh pr list --state merged --json number,mergedAt,title
   ```
2. Filter by merge date if `--merged-after` provided
3. For each PR: Check if it modified the target file(s)
   ```bash
   git diff-tree --no-commit-id --name-only -r {merge_commit} | grep {file}
   ```

### Phase 4: Presence in Target
For each PR that modified the file:
1. Get merge commit SHA
2. Check if commit is ancestor of target branch:
   ```bash
   git merge-base --is-ancestor {commit_sha} origin/{target_branch}
   ```
3. If yes: Mark as "in_target"
4. If no: Mark as "missing_from_target"

### Phase 5: Open Cherry-Pick Detection
For each missing PR:
1. Search for open cherry-pick PRs to target branch:
   ```bash
   gh pr list --state open --base {target_branch} --search "cherry-pick from #{pr_number}"
   ```
2. If found: Mark as "open_cherry_pick" with PR number

### Phase 6: Ordering & Output
1. Sort missing PRs by merge date (oldest first)
2. This is the suggested backport order
3. Include warnings for open cherry-picks
4. Generate summary with recommendations

---

## Error Handling

### Pre-execution Errors (Return Code 2)

- Invalid branch: "Branch must match pattern 'release/X.Y.Z', got: '{branch}'"
- Invalid date: "Date must be ISO format 'YYYY-MM-DD', got: '{date}'"
- PR not found: "PR #{number} not found"
- PR not merged: "PR #{number} is not merged to main"

### Data Errors (Return Code 1)

- File not found: "File 'src/foo.rs' does not exist in repository"
- No PRs touch file: "No merged PRs found that modified '{file}'"

### GitHub API Errors (Return Code 3)

- Auth failure: "GitHub CLI not authenticated"
- Rate limit: "GitHub API rate limit exceeded"

---

## Testing Strategy

**Unit Tests**:
- Input validation (branch format, date parsing, file existence)
- Commit ancestry detection logic
- PR filtering and sorting
- Open cherry-pick detection

**Integration Tests**:
- Mock GitHub API responses (PR lists, files changed)
- Mock git operations (commit ancestry)
- Multiple PRs modifying same file
- No prerequisites case (file only in one merged PR)
- Open cherry-pick scenario
- Date filtering

**Manual Tests**:
- Analyze a file known to be touched by multiple PRs
- Verify correct backport order is suggested
- Test with open cherry-pick PR in target
- Verify recommendations are actionable
