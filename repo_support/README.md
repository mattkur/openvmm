# PR Branch Management Tools

Automation tools for managing backport workflows across `main`, `staging/X.Y.Z`, and `release/X.Y.Z` branches in the OpenVMM repository.

## Prerequisites

- **Python 3.11+**: Required for running all scripts
- **GitHub CLI (`gh`)**: Authentication and API access
  - Install: [https://cli.github.com/](https://cli.github.com/)
  - Authenticate: `gh auth login`
- **Git**: Standard git operations
- **Git Remote Setup**: Tools auto-detect your upstream remote
  - Prefers a remote named `upstream` if it exists
  - Falls back to `origin`
  - Works with any single remote
- **Permissions**: 
  - Read-only tools (status, analyze): Any user with repo read access
  - Cherry-pick tool: Fork push access (pushes to your fork, opens PRs)
  - Relabel tool: Write access to `microsoft/openvmm` (label management)

## Quick Start

**Note**: All tools can be run either as Python modules (`python3 -m repo_support.tool_name`) or directly as executables (`./repo_support/tool_name.py` or just `tool_name.py` if in the repo_support directory).

### 1. Check Backport Status

View pending, in-progress, and completed backports for a version:

```bash
# As module
python3 -m repo_support.backport_status 1.7.2511

# As executable
./repo_support/backport_status.py 1.7.2511

# From repo_support directory
cd repo_support && ./backport_status.py 1.7.2511
```

Output formats: `summary` (default), `table`, `json`, `detailed`

### 2. Create Cherry-Pick PRs

Automatically create cherry-pick PRs from labeled PRs on main:

```bash
# From label
python3 -m repo_support.gen_cherrypick_prs release/1.7.2511 --from-backport-label backport_1.7.2511

# From specific PRs
python3 -m repo_support.gen_cherrypick_prs release/1.7.2511 2680 2681 2682
```

**Features**:
- Worktree isolation (doesn't modify main working directory)
- Correct merge order (respects dependency chains)
- Conflict detection and clear error messages
- Duplicate detection (skips already-backported PRs)

### 3. Analyze Conflicts

When cherry-picks conflict, identify missing prerequisite PRs:

```bash
# Analyze a specific file
python3 -m repo_support.analyze_pr_deps --file src/foo.rs --target release/1.7.2511

# Analyze all files in a PR
python3 -m repo_support.analyze_pr_deps --pr 2680 --target release/1.7.2511
```

Shows:
- Which PRs also modified the conflicted files
- Which of those PRs are missing from the target branch
- Suggested backport order

### 4. Relabel After Merges

Update labels from `backport_X` to `backported_X` after successful backports:

```bash
# Dry run (shows what would change)
python3 -m repo_support.relabel_backported 1.7.2511

# Apply changes
python3 -m repo_support.relabel_backported 1.7.2511 --update
```

### 5. Unified Workflow (All Steps)

Run the complete backport workflow interactively or automatically:

```bash
# Interactive (step-by-step with prompts)
python3 -m repo_support.backport_workflow release/1.7.2511

# Finalize (automatic, no prompts)
python3 -m repo_support.backport_workflow release/1.7.2511 --finalize
```

---

## Complete Workflow Walkthrough

### Scenario: Backporting to `release/1.7.2511`

**Prerequisites**: Ensure the target branch exists on the upstream remote (you don't need a local copy):
```bash
# Tools auto-detect your upstream remote (prefers 'upstream', falls back to 'origin')
# Check your remote setup
git remote -v

# If creating a new release branch from main
git push upstream main:release/1.7.2511
# Or: git push origin main:release/1.7.2511

# Or from a specific commit
git push upstream abc1234:refs/heads/release/1.7.2511

# Verify it exists
git ls-remote upstream release/1.7.2511
```

1. **Label PRs on main** with `backport_1.7.2511`
   ```bash
   gh pr edit 2680 --add-label backport_1.7.2511
   gh pr edit 2681 --add-label backport_1.7.2511
   ```

2. **Check current status**
   ```bash
   python3 -m repo_support.backport_status 1.7.2511
   ```
   
   Output shows: pending PRs, already backported, open cherry-picks, conflicts

3. **Create cherry-pick PRs**
   ```bash
   python3 -m repo_support.gen_cherrypick_prs release/1.7.2511 --from-backport-label backport_1.7.2511
   ```
   
   **If successful**: Cherry-pick PRs created and pushed to your fork
   
   **If conflicts**: See worktree path, analyze with step 4

4. **Analyze conflicts** (if needed)
   ```bash
   python3 -m repo_support.analyze_pr_deps --file src/conflicted_file.rs --target release/1.7.2511
   ```
   
   Shows missing prerequisite PRs and suggested backport order

5. **Wait for cherry-pick PRs to be reviewed and merged**
   - Reviewers check cherry-picks
   - Merges happen to `release/1.7.2511`

6. **Relabel completed backports**
   ```bash
   # Check what would be relabeled
   python3 -m repo_support.relabel_backported 1.7.2511
   
   # Apply updates
   python3 -m repo_support.relabel_backported 1.7.2511 --update
   ```

7. **Verify completion**
   ```bash
   python3 -m repo_support.backport_status 1.7.2511
   ```
   
   All PRs should now show as `backported_1.7.2511`

---

## Tool Reference

**Running Tools**: Each tool can be run in two ways:
1. **As a Python module**: `python3 -m repo_support.tool_name` (works from any directory)
2. **As an executable**: `./repo_support/tool_name.py` (from repo root) or `./tool_name.py` (from repo_support directory)

All examples below use the module syntax, but you can substitute with direct execution.

### backport_status.py

Read-only status dashboard for backport tracking.

```bash
python3 -m repo_support.backport_status <version> [options]

Options:
  --branch BRANCH      Target branch (detects from version if omitted)
  --pr PR_NUMBER       Filter to specific PR
  --format FORMAT      Output format: summary|table|json|detailed
  --repo OWNER/REPO    Non-standard repository
```

**Example**: `python3 -m repo_support.backport_status 1.7.2511 --format table`

### gen_cherrypick_prs.py

Create cherry-pick PRs with worktree isolation.

```bash
python3 -m repo_support.gen_cherrypick_prs <target_branch> [pr_numbers...] [options]

Options:
  --from-backport-label LABEL  Discover PRs from label (e.g., backport_1.7.2511)
  --dry-run                    Show what would be done
  --no-confirm                 Skip interactive confirmation
  --keep-worktree              Keep worktrees after success
  --force-cleanup              Remove worktrees even on conflict
  --repo OWNER/REPO            Non-standard repository
```

**Examples**:
- From label: `python3 -m repo_support.gen_cherrypick_prs release/1.7.2511 --from-backport-label backport_1.7.2511`
- Specific PRs: `python3 -m repo_support.gen_cherrypick_prs release/1.7.2511 2680 2681`
- Dry run: `python3 -m repo_support.gen_cherrypick_prs release/1.7.2511 2680 --dry-run`

### analyze_pr_deps.py

Identify missing prerequisite PRs causing conflicts.

```bash
python3 -m repo_support.analyze_pr_deps (--file FILE | --pr PR) --target BRANCH [options]

Options:
  --file FILE              Analyze this file
  --pr PR_NUMBER           Analyze files in this PR
  --target BRANCH          Target branch (required)
  --merged-after DATE      Only consider PRs after YYYY-MM-DD
  --json                   JSON output
  --repo OWNER/REPO        Non-standard repository
```

**Examples**:
- File analysis: `python3 -m repo_support.analyze_pr_deps --file src/foo.rs --target release/1.7.2511`
- PR analysis: `python3 -m repo_support.analyze_pr_deps --pr 2680 --target release/1.7.2511`
- Recent changes: `python3 -m repo_support.analyze_pr_deps --file src/foo.rs --target release/1.7.2511 --merged-after 2026-01-01`

### relabel_backported.py

Update labels after successful backports.

```bash
python3 -m repo_support.relabel_backported <version> [options]

Options:
  --update                    Apply label changes (default: dry-run)
  --force-update-pr PR,...    Force update even if title mismatch
  --json                      JSON output
  --repo OWNER/REPO           Non-standard repository
```

**Examples**:
- Dry run: `python3 -m repo_support.relabel_backported 1.7.2511`
- Apply: `python3 -m repo_support.relabel_backported 1.7.2511 --update`

**Note**: The tool automatically searches both `release/X.Y.Z` and `staging/X.Y.Z` branches for backported commits.

### backport_workflow.py

Unified workflow orchestrator (combines all tools).

```bash
python3 -m repo_support.backport_workflow <target_branch> [options]

Options:
  --finalize           Run complete workflow automatically
  --dry-run            Show workflow without executing
  --skip-relabel       Create cherry-picks but don't relabel
  --repo OWNER/REPO    Non-standard repository
```

**Examples**:
- Interactive: `python3 -m repo_support.backport_workflow release/1.7.2511`
- Automated: `python3 -m repo_support.backport_workflow release/1.7.2511 --finalize`
- Preview: `python3 -m repo_support.backport_workflow release/1.7.2511 --dry-run`

---

## Troubleshooting

### "How do I run these tools?"

**Option 1 - As Python modules** (works from anywhere):
```bash
python3 -m repo_support.backport_status 1.7.2511
python3 -m repo_support.gen_cherrypick_prs release/1.7.2511 2680
python3 -m repo_support.analyze_pr_deps --file src/foo.rs --target release/1.7.2511
python3 -m repo_support.relabel_backported 1.7.2511
python3 -m repo_support.backport_workflow release/1.7.2511
```

**Option 2 - As executables** (from repo root):
```bash
./repo_support/backport_status.py 1.7.2511
./repo_support/gen_cherrypick_prs.py release/1.7.2511 2680
./repo_support/analyze_pr_deps.py --file src/foo.rs --target release/1.7.2511
./repo_support/relabel_backported.py 1.7.2511
./repo_support/backport_workflow.py release/1.7.2511
```

**Option 3 - From the repo_support directory**:
```bash
cd repo_support
./backport_status.py 1.7.2511
./gen_cherrypick_prs.py release/1.7.2511 2680
# etc.
```

### "GitHub CLI not authenticated"
```bash
gh auth login
# Follow prompts to authenticate
```

### "Target branch does not exist" or "Not a valid object name"
The target branch (e.g., `release/1.7.2511`) needs to exist on the upstream remote. You don't need a local copy.

**Note**: The tools auto-detect your upstream remote (prefers `upstream`, falls back to `origin`, or uses your only remote).

**To create a new release branch on remote**:
```bash
# Check your remotes
git remote -v

# Create from current main (use your upstream remote name)
git push upstream main:release/1.7.2511
# Or: git push origin main:release/1.7.2511

# Or create from a specific commit
git push upstream abc1234:refs/heads/release/1.7.2511

# Verify it was created
git ls-remote upstream release/1.7.2511
```

**For staging branches**:
```bash
# Create staging branch from main
git push upstream main:staging/1.7.2511
```

**Note**: The cherry-pick tools work directly with `{remote}/{branch}` using git worktrees, so you never need to check out the target branch locally.

### "Cherry-pick conflict detected"
1. Note the worktree path from error message
2. Run: `python3 -m repo_support.analyze_pr_deps --file <conflicted_file> --target <branch>`
3. Backport missing prerequisite PRs first
4. OR manually resolve in worktree:
   ```bash
   cd .git/worktrees/backport-temp-<timestamp>
   # Resolve conflicts
   git add .
   git cherry-pick --continue
   git push
   gh pr create --base <target_branch> --title "..."
   ```

### "PR already in target branch"
The PR's merge commit is already an ancestor of the target branch. This usually means:
- The PR was already backported (check for `backported_X` label)
- The commits were manually cherry-picked without creating a PR
- The target branch includes all main commits (e.g., just after a release merge)

No action needed - tool will skip automatically.

### "Title mismatch detected"
The cherry-pick commit title doesn't exactly match the original PR title. This can happen if:
- PR title was edited after merging
- Manual cherry-pick with different title

To proceed: `python3 -m repo_support.relabel_backported <version> --update --force-update-pr <pr_number>`

### Worktree cleanup after conflicts
```bash
# List worktrees
git worktree list

# Remove specific worktree
git worktree remove .git/worktrees/backport-temp-<timestamp>

# Force remove if needed
git worktree remove --force .git/worktrees/backport-temp-<timestamp>
```

### Performance issues
- **Slow dependency analysis**: Use `--merged-after` to limit PR search window
  ```bash
  python3 -m repo_support.analyze_pr_deps --file src/foo.rs --target release/1.7.2511 --merged-after 2026-01-01
  ```

- **GitHub API rate limits**: Wait 1 hour or authenticate with a token that has higher limits

---

## Design Principles

1. **Safety**: Worktree isolation, dry-run modes, clear error messages
2. **Transparency**: JSON output options, detailed status reporting
3. **Accessibility**: Status/analysis tools read-only (no special permissions)
4. **Correctness**: Respects merge order, detects duplicates, validates input
5. **Actionability**: Every error includes "what to do next"

---

## Testing

Run the test suite:

```bash
# All tests
python3 -m pytest repo_support/tests/ -v

# Specific tool tests
python3 -m pytest repo_support/tests/test_gen_cherrypick_prs.py -v
python3 -m pytest repo_support/tests/test_relabel_backported.py -v
python3 -m pytest repo_support/tests/test_backport_status.py -v
python3 -m pytest repo_support/tests/test_analyze_pr_deps.py -v
python3 -m pytest repo_support/tests/test_backport_workflow.py -v
```

---

## Further Reading

- **Conceptual Guide**: `Guide/src/dev_guide/pr_management.md` - Branch strategy, labeling conventions, when to use each tool
- **Contracts**: `specs/001-pr-branch-tools/contracts/` - Detailed API specifications
- **Specification**: `specs/001-pr-branch-tools/spec.md` - Feature requirements and acceptance criteria

---

## Contributing

When modifying these tools:
1. Follow existing code patterns and error handling
2. Update tests in `repo_support/tests/`
3. Update this README if CLI changes
4. Run `python3 -m pytest` before committing
5. Use security best practices (no `shell=True`, validate all input)
