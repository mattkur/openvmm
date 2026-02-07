# API Contract: relabel_backported.py

**Tool**: Backport Label Updates  
**Language**: Python 3.11+  
**Status**: Enhancement of existing tool

## CLI Interface

### Command Format

```bash
relabel_backported.py <version> [--update] [--force-update-pr PR_NUMBERS] [--repo OWNER/REPO]
```

### Arguments

**Positional**:
- `version` (str, required): Release version matching backport labels (e.g., `1.7.2511`)
  - Validation: Must match regex `^[0-9.]+$`

**Options**:
- `--update` (flag): Actually apply label changes and comments (default is dry-run)
  - Behavior: Without this flag, tool shows what would change but doesn't apply
  
- `--force-update-pr PR_NUMBERS` (str): Override warnings for specific PRs
  - Example: `--force-update-pr "2680,2567"`
  - Validation: Comma-separated list of PR numbers (no spaces)
  - Use case: When commit title differs from PR title (tool warns), force update anyway
  
- `--repo OWNER/REPO` (str): Non-standard repository
  - Validation: Must match regex `^[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+$`
  
- `--help` / `-h` (flag): Show detailed help

---

## Data Contract: Input/Output

### Input Data

**Via CLI Arguments**:
- Release version to find backport labels for
- Control flags (`--update`, `--force-update-pr`)

**Via GitHub API** (queried by tool):
```json
{
  "pullRequest": {
    "number": 2680,
    "title": "Feature: Add worktree support",
    "labels": [
      {"name": "backport_1.7.2511"}
    ],
    "mergedAt": "2026-02-05T14:30:00Z"
  }
}
```

**Via Git** (verify backport commit exists):
```bash
git log --grep="Cherry-picked from #2680" release/1.7.2511
```

### Output Data

**Stdout (Dry-Run, No Changes)** - Default:
```yaml
dryRun: true
version: "1.7.2511"
results:
  - prNumber: 2680
    action: "add_label"
    newLabel: "backported_1.7.2511"
    oldLabel: "backport_1.7.2511"
    backportPRs: ["#2850"]
    comment: "Backported in #2850"
    
  - prNumber: 2567
    action: "warn_title_mismatch"
    warning: "Commit title 'Fix: edge case (cherry-pick from #2567)' differs from PR title 'Fix: Handle edge case'"
    reason: "Manual conflict resolution or rebase may have changed commit message"
    suggestion: "Review manually or use --force-update-pr 2567 to override"
    
  - prNumber: 2525
    action: "skip"
    reason: "PR is still open on main (not merged yet)"

summary:
  wouldUpdate: 1
  wouldWarn: 1
  wouldSkip: 1
  message: "Run with --update to apply changes"
```

**Stdout (With `--update`)**:
```yaml
dryRun: false
version: "1.7.2511"
appliedChanges:
  - prNumber: 2680
    label: "backported_1.7.2511"
    comment: "Backported in #2850"
    result: "success"
    
  - prNumber: 2567
    label: "skipped"
    reason: "Title mismatch - use --force-update-pr 2567 to override"
    result: "manual_review_needed"

summary:
  updated: 1
  warnings: 1
  skipped: 1
  elapsedSeconds: 18
```

**Return Codes**:
| Code | Meaning |
|------|---------|
| 0 | All PRs checked; no manual action needed (or all updates successful with `--update`) |
| 1 | One or more PRs require manual review (warnings present, no `--force-update-pr` provided) |
| 2 | Invalid arguments or precondition error |
| 3 | GitHub API error |

---

## Behavior Specification

### Phase 1: Input Validation
1. Validate version format matches `^[0-9.]+$`
2. Verify target branches exist: `release/{version}` and/or `staging/{version}`

### Phase 2: PR Discovery
1. Query GitHub for merged PRs with label `backport_{version}`:
   ```bash
   gh pr list --repo {repo} --state merged --label backport_{version} --json number,title,mergedAt,labels
   ```

### Phase 3: Backport Detection
For each PR with `backport_{version}` label:
1. Search for cherry-pick commits referencing the PR in target branch:
   ```bash
   git log --all-match --grep="Cherry-picked from #{pr_number}" release/{version}
   git log --all-match --grep="cherry-pick from #{pr_number}" release/{version}
   ```
2. Extract backport PR number from commit message or branch name
3. If not found: Mark for manual review

### Phase 4: Conflict Detection
1. Compare commit message title with original PR title
2. If mismatch detected: Warn user (may indicate manual conflict resolution)
3. If user provided `--force-update-pr`: Override warning

### Phase 5: Open PR Detection
1. Check if PR is still open on main (not merged)
2. If open: Skip (cannot backport PR that's still being reviewed)

### Phase 6: Apply Changes (if `--update` provided)
1. For each PR marked for update:
   - Add label: `backported_{version}`
   - Remove label: `backport_{version}`
   - Add comment with link to backport PR: `"Backported in #{backport_pr_number}"`

### Phase 7: Summary Output
Display results of all PRs processed

---

## Error Handling

### Pre-execution Errors (Return Code 2)

- Invalid version: "Version must match pattern 'X.Y.Z', got: 'badver'"
- Target branch missing: "release/1.7.2511 not found in repo"

### Warnings (Return Code 1, suggests manual review)

- PR still open: "PR #{number} is still open on main (not merged yet) - skipping"
- Title mismatch: "Commit title differs from PR title - review manually before applying labels"
- No backport found: "No backport commit found for PR #{number} in release/{version}"

### GitHub API Errors (Return Code 3)

- Auth failure: "GitHub CLI not authenticated"
- Rate limit: "GitHub API rate limit exceeded"
- Label not found: "Label 'backport_{version}' not used by any PRs"

---

## Testing Strategy

**Unit Tests**:
- Input validation (version format)
- Label pattern matching
- Commit message parsing for cherry-pick markers
- Title comparison logic

**Integration Tests**:
- Mock GitHub responses for PR listing
- Mock git operations for backport detection
- Test with and without `--update` flag
- Test `--force-update-pr` override behavior
- Test open PR detection

**Manual Tests**:
- Run dry-run on real repository to verify label detection
- Manually merge one backport PR, run tool, verify labels update
