# Quick Start: PR Branch Management Tools

**Target Audience**: Repository maintainers (non-developers)  
**Time to Complete**: 5-15 minutes  
**Complexity**: Beginner-friendly

## Prerequisites

Before using these tools, ensure you have:

- **Git**: Version 2.20+ (for worktree support)
  ```bash
  git --version
  ```

- **GitHub CLI (`gh`)**: Latest version, installed and authenticated
  ```bash
  gh --version
  gh auth status  # Should show you're logged in
  ```

- **Python 3.11+**: Available in your PATH
  ```bash
  python3 --version
  ```

- **Write access** (for cherry-pick/relabel tools): Ability to create branches and PRs
  - Note: `backport_status` tool requires only read access

## Installation

1. **Clone** or **pull latest** from the repository:
   ```bash
   cd /path/to/openvmm
   git fetch origin
   git checkout main  # or your feature branch
   ```

2. **Ensure scripts are executable**:
   ```bash
   chmod +x repo_support/*.py
   ```

3. **Verify setup**:
   ```bash
   python3 repo_support/gen_cherrypick_prs.py --help
   ```

## User Roles

These tools are designed for different user types:

**Any Contributor**: Can run `backport_status` to check the status of ongoing backports (read-only, no permissions needed)

**Users with Write Access**: Can run all tools:
- `backport_status` - View status
- `gen_cherrypick_prs` - Create cherry-pick PRs
- `analyze_pr_deps` - Investigate conflict prerequisites
- `relabel_backported` - Update labels after merges
- `backport_workflow` - Run complete workflow

**Maintainers**: Additionally manage release strategy, label conventions, and staging→release promotion

## Scenario 1: Check Backport Status (5 minutes)

**Anyone can do this** - No special permissions required. Useful for checking if a PR has been backported.

```bash
cd /path/to/openvmm

# Check status of all backports to release/1.7.2511
python3 repo_support/backport_status.py 1.7.2511
```

**Output shows**:
- 5 PRs waiting to be cherry-picked (labeled `backport_1.7.2511`)
- 2 PRs currently in review (open cherry-pick PRs)
- 1 PR blocked due to merge conflict
- 3 PRs already completed (labeled `backported_1.7.2511`)

### Different Output Formats

```bash
# Simple summary (default)
python3 repo_support/backport_status.py 1.7.2511

# Formatted table view (easier to read)
python3 repo_support/backport_status.py 1.7.2511 --format table

# Machine-readable JSON (for scripting)
python3 repo_support/backport_status.py 1.7.2511 --format json | jq '.summary'

# Check specific PR
python3 repo_support/backport_status.py 1.7.2511 --pr 2680
```

---

## Scenario 2: Simple Cherry-Pick Backport (10 minutes)

**Write access required**. You want to backport 5 PRs from main to release/1.7.2511.

### Step 1: Make sure release branch has all PRs labeled
Label merged PRs on main with `backport_1.7.2511`:
- Go to each PR on GitHub
- Add label `backport_1.7.2511`

### Step 2: Run cherry-pick tool
```bash
cd /path/to/openvmm

# Dry-run first (no changes)
python3 repo_support/gen_cherrypick_prs.py release/1.7.2511 \
  --from-backport-label backport_1.7.2511 \
  --dry-run

# Output should show which PRs would be processed
```

### Step 3: Create cherry-pick PRs (for real)
```bash
python3 repo_support/gen_cherrypick_prs.py release/1.7.2511 \
  --from-backport-label backport_1.7.2511
```

**Interactive prompts**:
- Tool will show PRs to be processed
- Prompt: "Create N cherry-pick PRs? [y/n]"
- Tool creates PRs one by one (can watch on GitHub)

### Step 4: Monitor PR merges
Once cherry-pick PRs are created:
- Review each PR on GitHub
- Merge them when ready

### Step 5: Update original PR labels (when ready)
Once backport PRs are merged:
```bash
python3 repo_support/relabel_backported.py 1.7.2511 --update
```

This will:
- Add `backported_1.7.2511` label to original PRs
- Remove `backport_1.7.2511` label
- Add comment with link to backport PR

---

## Scenario 3: Handle Conflicts (15 minutes)

**Write access required**. Your cherry-pick command fails with a conflict.

### Example Error Output
```
ERROR: Cherry-pick conflict detected

PR #2680: Feature: Add worktree support
Conflicted files:
  • src/foo.rs
  • src/bar.rs

Worktree retained at: .git/worktrees/backport-temp-20260206T143022Z/

To investigate: analyze-pr-deps --file src/foo.rs --target release/1.7.2511
```

### Step 1: Understand the conflict
Check if a prerequisite PR is missing:
```bash
python3 repo_support/analyze_pr_deps.py \
  --file src/foo.rs \
  --target release/1.7.2511
```

Output will show which PRs modified that file but aren't backported yet.

### Step 2: Check backport order
Tool suggests: "Backport PR #2567 first, then retry #2680"

### Step 3: Backport the prerequisite
```bash
python3 repo_support/gen_cherrypick_prs.py release/1.7.2511 2567
```

### Step 4: Retry the original
Once prerequisite is merged to release branch:
```bash
python3 repo_support/gen_cherrypick_prs.py release/1.7.2511 2680
```

### Step 5: Cleanup worktree
Once conflict is resolved:
```bash
git worktree remove .git/worktrees/backport-temp-20260206T143022Z/
```

---

## Scenario 4: Full Workflow (Quick) (15 minutes)

**Write access + Maintainer role**. Do everything from start to finish in one command:

```bash
python3 repo_support/backport_workflow.py release/1.7.2511 --finalize
```

This will:
1. **Create cherry-pick PRs** for all PRs labeled `backport_1.7.2511`
2. **Wait for merges** (polls every 30 seconds, up to 30 minutes)
3. **Relabel original PRs** once backports are merged

At each step:
- **Tool prompts** next action
- **You can abort** at any time with `[q]` or `[3]`
- **Conflicts** are detected and reported with next steps

---

## Common Commands Reference

### List all PRs labeled for backport
```bash
gh pr list --state merged --label backport_1.7.2511 --repo microsoft/openvmm
```

### Check if specific PR is already backported
```bash
git log --all --grep="cherry-pick from #2680" release/1.7.2511
```

### Manually create one cherry-pick PR
```bash
python3 repo_support/gen_cherrypick_prs.py release/1.7.2511 2680 2567 2525
```

### Analyze why a specific PR conflicts
```bash
python3 repo_support/analyze_pr_deps.py --pr 2680 --target release/1.7.2511
```

### Check dry-run (see what would happen)
```bash
python3 repo_support/gen_cherrypick_prs.py release/1.7.2511 \
  --from-backport-label backport_1.7.2511 \
  --dry-run
```

---

## Troubleshooting

### Error: "GitHub CLI not authenticated"
**Fix**: Authenticate with GitHub:
```bash
gh auth login
```

### Error: "release/1.7.2511 not found in remote"
**Fix**: Branch doesn't exist. Check spelling:
```bash
git fetch origin
git branch -r | grep release
```

### Error: "Cherry-pick conflict detected"
**Fix**: A prerequisite PR is missing. Use:
```bash
python3 repo_support/analyze_pr_deps.py --file {conflicted_file} --target release/1.7.2511
```

### "Worktree..." directory leftover
**Fix**: Clean it up manually:
```bash
git worktree list  # See all worktrees
git worktree remove .git/worktrees/backport-temp-{timestamp}
```

### Tool runs slowly
- GitHub API rate limiting: Wait a few minutes and retry
- Network issue: Check internet connection
- Large repository: Expect 2-3 seconds per PR

---

## Tips & Best Practices

### ✅ Do This

- **Run `--dry-run` first**: Always preview changes before creating PRs
  ```bash
  gen_cherrypick_prs release/1.7.2511 ... --dry-run
  ```

- **Label PRs promptly**: Label ones you want backported right after merge to main
  - Easier to remember which PRs need backporting
  - Less chance of forgetting any

- **Group by version**: Keep all `backport_1.7.2511` PRs together
  - Makes it easier to batch-process backports

- **Check relabeling**: Verify `backported_X` labels are applied
  ```bash
  gh pr view 2680 --jq '.labels'
  ```

### ❌ Don't Do This

- **Don't use `--force-cleanup` in manual workflows**: You'll lose conflict investigation data
- **Don't force-push release branches**: Cherry-pick PRs might land on old commits
- **Don't manually edit worktrees**: Tools expect clean state; let them cleanup
- **Don't skip relabeling**: Original PRs should show as "backported" for visibility

---

## Getting Help

For each tool, use `--help`:
```bash
python3 repo_support/gen_cherrypick_prs.py --help
python3 repo_support/relabel_backported.py --help
python3 repo_support/analyze_pr_deps.py --help
python3 repo_support/backport_workflow.py --help
```

For more detailed documentation:
- **Branch strategy**: See `Guide/src/dev_guide/pr_management.md`
- **Full API reference**: See `repo_support/README.md`
- **Architecture details**: See `specs/001-pr-branch-tools/`

---

## Example: Complete Backport Session

```bash
# Start: Release manager wants to backport 5 PRs for hotfix

# 1. Navigate to repo
cd /home/user/openvmm

# 2. Fetch latest
git fetch origin

# 3. Preview what would happen
python3 repo_support/gen_cherrypick_prs.py release/1.7.2511 \
  --from-backport-label backport_1.7.2511 \
  --dry-run

# Output shows 5 PRs would be processed
# ✓ Looks good, proceed

# 4. Create cherry-pick PRs (interactive)
python3 repo_support/gen_cherrypick_prs.py release/1.7.2511 \
  --from-backport-label backport_1.7.2511

# Tool prompts: "Create 5 cherry-pick PRs? [y/n]: "
# Type: y
# Tool creates PRs, shows results:
#   ✓ PR #2567 → #2800
#   ✓ PR #2680 → #2801
#   ✓ PR #2525 → conflict (worktree saved)
#   ✓ PR #2345 → #2802
#   ✓ PR #2100 → #2803

# 5. Investigate conflict
python3 repo_support/analyze_pr_deps.py \
  --file src/foo.rs \
  --target release/1.7.2511

# Output shows: PR #2230 modified src/foo.rs but isn't backported yet
# Solution: Backport #2230 first

# 6. Backport prerequisite
python3 repo_support/gen_cherrypick_prs.py release/1.7.2511 2230

# Wait for merge...

# 7. Retry conflicted PR
python3 repo_support/gen_cherrypick_prs.py release/1.7.2511 2525
# This time succeeds ✓

# 8. Clean up
git worktree remove .git/worktrees/backport-temp-*

# 9. Merge all cherry-pick PRs on GitHub (manual or via automation)
# ...wait for all to merge...

# 10. Label completed backports
python3 repo_support/relabel_backported.py 1.7.2511 --update

# Done! All original PRs now have 'backported_1.7.2511' label
```
