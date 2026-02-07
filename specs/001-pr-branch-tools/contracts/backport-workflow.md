# API Contract: backport_workflow.py

**Tool**: Unified Backport Workflow Orchestrator  
**Language**: Python 3.11+  
**Status**: New

## CLI Interface

### Command Format

```bash
backport_workflow.py <target_branch> [--finalize] [--dry-run] [--skip-relabel] [--repo OWNER/REPO]
```

### Arguments

**Positional**:
- `target_branch` (str, required): Target branch for backport workflow
  - Example: `release/1.7.2511` or `staging/1.7.2511`
  - Validation: Must match regex `^(release|staging)/[0-9.]+$`

**Options**:
- `--finalize` (flag): Run complete workflow end-to-end
  - Behavior: Automatically detect merge status and run relabeling after PRs merged
  - Use case: Full CI/automation pipeline
  
- `--dry-run` (flag): Show what would be done without making changes
  - Behavior: Displays workflow steps without execution
  
- `--skip-relabel` (flag): Create cherry-pick PRs but don't relabel
  - Behavior: Useful if relabeling should be deferred to later
  
- `--repo OWNER/REPO` (str): Non-standard repository
  
- `--help` / `-h` (flag): Show detailed help

---

## Data Contract: Input/Output

### Output Data

**Interactive Mode** - Step-by-step guidance:
```
═══════════════════════════════════════════════════════════════
  Backport Workflow: release/1.7.2511
═══════════════════════════════════════════════════════════════

This workflow will:
  1. Create cherry-pick PRs for all backport_1.7.2511 labeled PRs
  2. Wait for your confirmation at each step
  3. Optionally relabel PRs after merges are detected

Step 1: Create Cherry-Pick PRs
─────────────────────────────────────────────────────────────────

Found 3 PRs labeled 'backport_1.7.2511':
  • #2567: Fix: Handle edge case
  • #2680: Feature: Add worktree support
  • #2525: Refactor: Extract utility

Creating cherry-pick PRs...

Results:
  ✓ PR #2567 → Cherry-pick PR #2800 created
  ✓ PR #2680 → Cherry-pick PR #2801 created
  ✗ PR #2525 → CONFLICT in src/foo.rs
    Worktree: .git/worktrees/backport-temp-20260206T143022Z/
    Next: analyze-pr-deps --file src/foo.rs --target release/1.7.2511

─────────────────────────────────────────────────────────────────

Step 2: Monitor Merge Status
─────────────────────────────────────────────────────────────────

Pending cherry-pick PRs:
  • #2800: waiting (24 seconds old, 0 reviews)
  • #2801: waiting (7 seconds old, 0 reviews)

Conflict PRs (manual intervention needed):
  • #2525: Conflict in src/foo.rs - see worktree above

What would you like to do?
  [1] Check PR status again (refreshes)
  [2] Proceed to relabeling (if some PRs merged) 
  [3] Abort workflow
  [q] Quit

Enter choice: _
```

**Stdout (`--finalize` mode)**:
```yaml
workflowStatus: "complete"
targetBranch: "release/1.7.2511"
version: "1.7.2511"

phases:
  cherrypick:
    status: "complete"
    created: 2
    conflicts: 1
    skipped: 0
    results:
      - prNumber: 2567
        status: "success"
        cherrypickPR: 2800
      - prNumber: 2680
        status: "success"
        cherrypickPR: 2801
      - prNumber: 2525
        status: "conflict"
        worktree: ".git/worktrees/backport-temp-20260206T143022Z/"
        
  merge_monitoring:
    status: "complete"
    waitedFor: "5 minutes"
    merged:
      - prNumber: 2800
        mergedAt: "2026-02-06T14:35:00Z"
      - prNumber: 2801
        mergedAt: "2026-02-06T14:40:00Z"
    pending:
      - prNumber: 2525
        reason: "manual_conflict_resolution"
        
  relabeling:
    status: "complete"
    updated:
      - prNumber: 2567
        label: "backported_1.7.2511"
      - prNumber: 2680
        label: "backported_1.7.2511"
    skipped:
      - prNumber: 2525
        reason: "not_merged_to_target"

summary:
  totalScheduled: 3
  successful: 2
  needsManualAction: 1
  elapsedTime: "8 minutes"
  nextSteps: ["Resolve conflict for PR #2525", "Re-run workflow for #2525"]
```

**Return Codes**:
| Code | Meaning |
|------|---------|
| 0 | Workflow complete; some or all PRs processed |
| 1 | Workflow aborted by user or waiting for merges (not an error) |
| 2 | Invalid arguments or precondition error |
| 3 | GitHub API or git error during workflow |

---

## Behavior Specification

### Phase 1: Initialization
1. Validate target branch
2. Detect backport version from branch name (e.g., `1.7.2511` from `release/1.7.2511`)
3. Discover all PRs labeled `backport_{version}`
4. Display workflow summary to user

### Phase 2: Cherry-Pick Creation
1. Call `gen_cherrypick_prs.py --from-backport-label backport_{version}` (non-interactive)
2. Display results (created PRs, conflicts, skipped)
3. If conflicts detected: Suggest `analyze-pr-deps` and offer to continue or abort

### Phase 3: Merge Monitoring (if `--finalize` or user requests)
1. Poll GitHub for status of created cherry-pick PRs
   ```bash
   gh pr view {pr_number} --json state, mergedAt
   ```
2. Update user every 30 seconds on merge status
3. Option for user to check again or proceed
4. Wait for all created PRs to merge (timeout: 30 minutes or user abort)

### Phase 4: Relabeling (if `--finalize` or user explicitly requests)
1. Call `relabel_backported.py {version} --update`
2. Display relabeling results
3. Report which original PRs are now marked as backported

### Phase 5: Summary & Cleanup
1. Summarize total PRs processed, successful, conflicts
2. If conflicts remain: Remind user of manual worktree cleanup
3. Provide next steps (retry conflicts, resolve dependencies)

---

## Interactive States

```
┌─ START ──────────────────────────────────────────────┐
│ User runs: backport_workflow.py release/1.7.2511     │
└──────────────────────────────────────────────────────┘
         │
         ▼
┌─ PHASE 1: Cherry-Pick ────────────────────────────────┐
│ Run gen_cherrypick_prs.py                             │
│ Display results (created, conflicts, skipped)         │
│                                                        │
│ Choice: [1] Continue [2] Abort [3] Analyze conflicts  │
└──────────────────────────────────────────────────────┘
         │
         ▼ [1]
┌─ PHASE 2: Monitor Merges ──────────────────────────────┐
│ Poll PR merge status every 30s                        │
│                                                        │
│ Choice: [1] Check again [2] Skip wait, relabel now   │
│         [3] Abort (keep PRs) [4] Abort & cleanup PRs  │
└──────────────────────────────────────────────────────┘
         │
         ▼ [2 or timeout]
┌─ PHASE 3: Relabeling ──────────────────────────────────┐
│ Run relabel_backported.py {version} --update          │
│ Display results                                        │
└──────────────────────────────────────────────────────┘
         │
         ▼
┌─ COMPLETE ────────────────────────────────────────────┐
│ Summary of all phases                                 │
│ Cleanup instructions if needed                        │
└──────────────────────────────────────────────────────┘
```

---

## Error Handling

### Pre-execution Errors (Return Code 2)

- Invalid branch: "Branch must match 'release/X.Y.Z', got: '{branch}'"
- No PRs to process: "No PRs found with label 'backport_1.7.2511'"

### Workflow Errors (Return Code 3)

- GitHub API failure during cherry-pick: Error from `gen_cherrypick_prs.py`
- GitHub API failure during monitoring: "Failed to poll PR status: {error}"
- GitHub API failure during relabeling: Error from `relabel_backported.py`

### User Abort (Return Code 1)

- User chooses [Abort] at any step
- Workflow stops cleanly, outputs current status

---

## Testing Strategy

**Unit Tests**:
- Workflow state transitions
- Version extraction from branch names
- PR filtering (labeled PRs only)

**Integration Tests**:
- Complete workflow with successful cherry-picks
- Workflow with conflicts (early exit suggested)
- `--finalize` mode with automatic merge detection
- `--skip-relabel` flag behavior
- `--dry-run` mode (no side effects)

**Manual Tests**:
- Run interactive workflow, verify prompts at each step
- Verify cherry-pick PRs created correctly
- Verify relabeling completes only for merged PRs
- Test workflow abort scenarios
