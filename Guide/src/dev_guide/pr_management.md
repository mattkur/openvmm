# Pull Request Branch Management

This guide explains OpenVMM's branch strategy, labeling conventions, and automation tools for managing backports across release branches.

## Branch Strategy

OpenVMM uses a three-tier branch strategy:

```
main (development)
  ↓ cherry-pick
staging/X.Y.Z (pre-release testing)
  ↓ promotion
release/X.Y.Z (stable releases)
```

### Branch Roles

- **`main`**: Active development, all new features and fixes land here first
- **`staging/X.Y.Z`**: Pre-release validation, receives selective backports for testing before release
- **`release/X.Y.Z`**: Production releases, only critical fixes backported

### Version Numbering

Version format: `MAJOR.MINOR.BUILD`

Example: `1.7.2511`
- `1`: Major version
- `7`: Minor version  
- `2511`: Build number (often derived from date/CI run)

## Labeling Conventions

### Backport Labels

PRs merged to `main` can be labeled for backporting:

| Label | Meaning | Target Branch |
|-------|---------|---------------|
| `backport_1.7.2511` | Scheduled for backport | `staging/1.7.2511` or `release/1.7.2511` |
| `backported_1.7.2511` | Successfully backported | (informational) |

**Workflow**:
1. Maintainer adds `backport_X.Y.Z` to merged PR on main
2. Tools create cherry-pick PRs to target branch
3. Cherry-pick PRs are reviewed and merged
4. Original PR relabeled `backport_X.Y.Z` → `backported_X.Y.Z`

### When to Backport

**Release branches** (`release/X.Y.Z`):
- Critical bug fixes affecting production users
- Security patches
- Performance regressions
- Data loss or corruption fixes

**Staging branches** (`staging/X.Y.Z`):
- All release branch candidates (for testing before promotion)
- Feature completions for upcoming release
- Non-critical bug fixes
- Documentation updates

**Do not backport**:
- Breaking API changes
- Large refactors
- Experimental features
- Changes that don't apply to the target version

## Automation Tools

Five tools automate the backport workflow. Use them in sequence or independently.

**Important**: All tools work directly with remote branches (e.g., `upstream/release/X.Y.Z`, `origin/staging/X.Y.Z`) using git worktrees. The tools auto-detect your upstream remote (preferring `upstream`, falling back to `origin`, or using your only remote). You never need to check out target branches locally - they only need to exist on the remote.

### 1. Status Dashboard (`backport_status.py`)

**Purpose**: View current backport status for any version

**Access**: Read-only, any user

**When to use**:
- Check what PRs are pending backport
- See which cherry-picks are in progress
- Verify backport completion

**Example**:
```bash
python3 -m repo_support.backport_status 1.7.2511
```

Output shows:
- Pending: PRs labeled `backport_1.7.2511` not yet cherry-picked
- In Progress: Open cherry-pick PRs to target branch
- Completed: PRs labeled `backported_1.7.2511`
- Conflicts: Retained worktrees from failed cherry-picks

### 2. Cherry-Pick Tool (`gen_cherrypick_prs.py`)

**Purpose**: Create cherry-pick PRs automatically with correct ordering

**Access**: Requires fork push access (pushes to your fork, opens PRs)

**When to use**:
- Creating backport PRs from labeled PRs on main
- Creating backport PRs for specific PR numbers

**Key features**:
- **Worktree isolation**: Never modifies main working directory
- **Merge order preservation**: Cherry-picks in correct dependency order
- **Duplicate detection**: Skips PRs already in target
- **Conflict detection**: Stops on conflict, preserves worktree for investigation

**Example**:
```bash
# All PRs with label
python3 -m repo_support.gen_cherrypick_prs release/1.7.2511 --from-backport-label backport_1.7.2511

# Specific PRs
python3 -m repo_support.gen_cherrypick_prs release/1.7.2511 2680 2681 2682
```

**On conflict**:
- Tool stops immediately
- Worktree path printed to console
- Main working directory untouched
- Use `analyze_pr_deps.py` to find missing prerequisites

### 3. Dependency Analysis (`analyze_pr_deps.py`)

**Purpose**: Investigate why cherry-picks conflict

**Access**: Read-only, any user

**When to use**:
- Cherry-pick conflicts occur
- Need to understand file modification history
- Planning backport order for dependent changes

**How it works**:
1. Identifies all PRs that modified the same file(s)
2. Checks which are missing from target branch
3. Suggests backport order based on merge dates

**Example**:
```bash
# Analyze a specific file
python3 -m repo_support.analyze_pr_deps --file src/foo.rs --target release/1.7.2511

# Analyze all files in a PR
python3 -m repo_support.analyze_pr_deps --pr 2680 --target release/1.7.2511
```

Output shows:
- Which PRs touched the same files
- Which PRs are missing from target
- Suggested backport order
- Any open cherry-pick PRs

### 4. Relabeling Tool (`relabel_backported.py`)

**Purpose**: Update labels after successful backports

**Access**: Requires upstream write access (modifies labels on `microsoft/openvmm`)

**When to use**:
- After cherry-pick PRs are merged to target branch
- To mark backport workflow as complete

**How it works**:
1. Finds all PRs labeled `backport_X.Y.Z`
2. Searches target branch for cherry-pick commits
3. Updates labels: `backport_X.Y.Z` → `backported_X.Y.Z`
4. Adds comment linking to cherry-pick PR

**Example**:
```bash
# Dry run (shows what would change)
python3 -m repo_support.relabel_backported 1.7.2511

# Apply updates
python3 -m repo_support.relabel_backported 1.7.2511 --update

# Specific branch
python3 -m repo_support.relabel_backported 1.7.2511 --branch staging/1.7.2511 --update
```

**Safety**:
- Default mode is dry-run (preview changes)
- Title mismatch detection (warns if PR title differs from commit title)
- Skips PRs not yet merged

### 5. Workflow Wrapper (`backport_workflow.py`)

**Purpose**: Guide through complete backport workflow

**Access**: Same permissions as underlying tools (fork push + optional upstream write)

**When to use**:
- First time backporting
- Want step-by-step guidance
- Automating complete workflow end-to-end

**Modes**:

**Interactive** (default):
```bash
python3 -m repo_support.backport_workflow release/1.7.2511
```
- Prompts at each phase
- Shows status of cherry-pick PRs
- Waits for user confirmation before relabeling

**Finalize** (automatic):
```bash
python3 -m repo_support.backport_workflow release/1.7.2511 --finalize
```
- Runs all phases automatically
- Polls for cherry-pick PR merges
- Relabels when all PRs merged

**Phases**:
1. Create cherry-pick PRs
2. Monitor merge status
3. Relabel completed backports

## Conflict Resolution Workflow

When cherry-picks conflict, follow this process:

### Step 1: Identify Cause
```bash
python3 -m repo_support.analyze_pr_deps --file <conflicted_file> --target <branch>
```

Output shows:
- Which PRs modified the same file
- Which are missing from target
- Suggested backport order

### Step 2: Backport Prerequisites

If missing PRs identified:
```bash
# Label missing prerequisites for backport
gh pr edit <missing_pr_number> --add-label backport_X.Y.Z

# Create cherry-picks for prerequisites
python3 -m repo_support.gen_cherrypick_prs <target_branch> <missing_pr_numbers>
```

Wait for prerequisite cherry-picks to merge, then retry original PR.

### Step 3: Manual Resolution (if needed)

If no clear prerequisites or conflicts remain after backporting them:

1. **Keep the worktree**: Tool automatically retains conflicted worktrees
   ```bash
   cd .git/worktrees/backport-temp-<timestamp>
   ```

2. **Resolve conflicts**:
   ```bash
   # Edit conflicted files
   git status  # Shows conflicted files
   # ... make edits ...
   git add <resolved_files>
   git cherry-pick --continue
   ```

3. **Push and create PR**:
   ```bash
   git push
   gh pr create --base <target_branch> --title "<title> (cherry-pick from #<pr>)"
   ```

4. **Clean up**:
   ```bash
   cd ../../../  # Back to repo root
   git worktree remove .git/worktrees/backport-temp-<timestamp>
   ```

## Best Practices

### For Maintainers

1. **Label early**: Add `backport_X.Y.Z` when merging to main (while context is fresh)
2. **Batch backports**: Collect several PRs, then backport together (respects dependencies)
3. **Use status dashboard**: Check for pending backports regularly
4. **Test cherry-picks**: Cherry-pick PRs should be tested like any other PR
5. **Document conflicts**: When resolving conflicts, add comment explaining resolution
6. **Remote branches only**: Target branches only need to exist on upstream remote (auto-detected) - no local checkout required

### For Contributors

1. **Write portable code**: Avoid assumptions about surrounding code state
2. **Self-contained changes**: Minimize dependencies on recent changes
3. **Document prerequisites**: Mention in PR description if depends on other PRs
4. **Test on target**: If targeting backport, test against target branch locally

### For Reviewers

1. **Check for backport labels**: Remind authors to label if fix should be backported
2. **Review cherry-picks quickly**: Backports are often time-sensitive
3. **Verify clean apply**: Ensure cherry-pick has no unexpected changes
4. **Check title match**: Cherry-pick PR title should match original

## Common Scenarios

### Scenario 1: Backporting a Bug Fix to Release

```bash
# 1. Check current status
python3 -m repo_support.backport_status 1.7.2511

# 2. Label the fix PR on main
gh pr edit 2680 --add-label backport_1.7.2511

# 3. Create cherry-pick
python3 -m repo_support.gen_cherrypick_prs release/1.7.2511 --from-backport-label backport_1.7.2511

# 4. Wait for cherry-pick PR to be reviewed and merged

# 5. Relabel after merge
python3 -m repo_support.relabel_backported 1.7.2511 --update
```

### Scenario 2: Backporting Multiple Related PRs

```bash
# 1. Label all related PRs
gh pr edit 2680 --add-label backport_1.7.2511
gh pr edit 2681 --add-label backport_1.7.2511
gh pr edit 2682 --add-label backport_1.7.2511

# 2. Create cherry-picks (tool handles ordering)
python3 -m repo_support.gen_cherrypick_prs release/1.7.2511 --from-backport-label backport_1.7.2511

# 3. Tool preserves merge order automatically
```

### Scenario 3: Investigating a Conflict

```bash
# 1. Cherry-pick fails with conflict
python3 -m repo_support.gen_cherrypick_prs release/1.7.2511 2680
# Error: Conflict in src/foo.rs
# Worktree: .git/worktrees/backport-temp-20260207T120000Z

# 2. Analyze the file
python3 -m repo_support.analyze_pr_deps --file src/foo.rs --target release/1.7.2511
# Output: PR #2567 modified src/foo.rs but not in release/1.7.2511

# 3. Backport prerequisite first
python3 -m repo_support.gen_cherrypick_prs release/1.7.2511 2567

# 4. Retry original after prerequisite merges
python3 -m repo_support.gen_cherrypick_prs release/1.7.2511 2680
```

### Scenario 4: Staging to Release Promotion

```bash
# 1. Test in staging
python3 -m repo_support.gen_cherrypick_prs staging/1.7.2511 --from-backport-label backport_1.7.2511
# Cherry-picks merged, tested in staging

# 2. Promote to release (create release/1.7.2511 from staging/1.7.2511 on remote)
# Tools auto-detect your upstream remote (upstream, origin, etc.)
git push upstream staging/1.7.2511:release/1.7.2511

# 3. Relabel for release (automatically searches both staging and release branches)
python3 -m repo_support.relabel_backported 1.7.2511 --update
```

## Tool Selection Guide

**Quick reference for "which tool do I use?"**:

| Goal | Tool | Why |
|------|------|-----|
| "What's pending for backport?" | `backport_status` | Read-only status view |
| "Create cherry-pick PRs" | `gen_cherrypick_prs` | Automated PR creation |
| "Why did this conflict?" | `analyze_pr_deps` | Dependency investigation |
| "Mark PRs as backported" | `relabel_backported` | Label updates |
| "Guide me through everything" | `backport_workflow` | Step-by-step orchestration |

## Security Considerations

All tools follow strict security practices:

- **Input validation**: PR numbers, branch names, versions validated via regex
- **No shell injection**: All subprocess calls use list arguments (no `shell=True`)
- **GitHub API trusted**: Only parses JSON from authenticated GitHub CLI
- **File path validation**: User-provided paths validated before use
- **Error messages safe**: No sensitive data in error output

Maintainers and contributors can review the tools' source code in `repo_support/` to verify security properties.

## Performance

Expected performance for typical operations:

- **Status check**: < 5 seconds (queries GitHub API)
- **Cherry-pick creation**: ~30 seconds per PR (git operations + PR creation)
- **Dependency analysis**: < 30 seconds for files with <100 PR modifications
- **Relabeling**: ~10 seconds (queries commits + updates labels)

Use `--merged-after` flag on `analyze_pr_deps` to speed up analysis by limiting search window.

## See Also

- **README**: `repo_support/README.md` - CLI reference and troubleshooting
- **Specification**: `specs/001-pr-branch-tools/spec.md` - Original feature requirements
- **Contracts**: `specs/001-pr-branch-tools/contracts/` - API specifications
- **Tests**: `repo_support/tests/` - Unit and integration tests
