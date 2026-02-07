# API Contract: backport_status.py

**Tool**: Backport Status Dashboard  
**Language**: Python 3.11+  
**Status**: New  
**Access Level**: All repository users (read-only)

## CLI Interface

### Command Format

```bash
backport_status.py <version> [--branch BRANCH] [--pr PR_NUMBER] [--format FORMAT] [--repo OWNER/REPO]
```

### Arguments

**Positional**:
- `version` (str, required): Release version to check status for (e.g., `1.7.2511`)
  - Validation: Must match regex `^[0-9.]+$`
  - Tool checks both `release/{version}` and `staging/{version}` by default

**Options**:
- `--branch BRANCH` (str, optional): Filter to specific branch
  - Example: `--branch release/1.7.2511` or `--branch staging/1.7.2511`
  - If omitted: Shows status for both staging and release branches
  - Validation: Must match regex `^(release|staging)/[0-9.]+$`
  
- `--pr PR_NUMBER` (int, optional): Show detailed status for specific PR only
  - Example: `--pr 2680`
  - Validation: Must be integer >= 1
  - Output: Full backport status with links and timeline
  
- `--format FORMAT` (str, optional): Output format
  - Options: `summary` (default), `table`, `json`, `detailed`
  - `summary`: Quick overview with counts
  - `table`: Formatted table view (good for terminals)
  - `json`: Machine-readable JSON (for scripting)
  - `detailed`: Full details with commentary
  
- `--repo OWNER/REPO` (str, optional): Non-standard repository
  - Validation: Must match regex `^[a-zA-Z0-9_-]+/[a-zA-Z0-9_-]+$`
  
- `--help` / `-h` (flag): Show detailed help

---

## Data Contract: Input/Output

### Input Data

**Via CLI Arguments**:
- Version to check (validated)
- Optional branch filter, PR filter, output format
- Optional repository override

**Via GitHub API** (queried by tool):
```json
{
  "backportLabeled": [
    {
      "number": 2567,
      "title": "Fix: Handle edge case",
      "labels": [{"name": "backport_1.7.2511"}],
      "url": "https://github.com/microsoft/openvmm/pull/2567"
    }
  ],
  "backportCompleted": [
    {
      "number": 2345,
      "title": "Refactor: Extract utility",
      "labels": [{"name": "backported_1.7.2511"}],
      "url": "https://github.com/microsoft/openvmm/pull/2345"
    }
  ],
  "cherryPickPRs": [
    {
      "number": 2800,
      "title": "Fix: Handle edge case (cherry-pick from #2567)",
      "state": "open",
      "lastUpdated": "2026-02-06T12:30:00Z",
      "baseBranch": "release/1.7.2511"
    }
  ]
}
```

### Output Data (Default `summary` format)

```
═══════════════════════════════════════════════════════════════
  Backport Status: version 1.7.2511
═══════════════════════════════════════════════════════════════

Target Branches: release/1.7.2511, staging/1.7.2511

📋 PENDING BACKPORT (labeled backport_1.7.2511)
   4 PRs waiting to be cherry-picked:
   • #2567: Fix: Handle edge case (merged 2026-02-01)
   • #2680: Feature: Add worktree support (merged 2026-02-05)
   • #2525: Refactor: Extract utility (merged 2026-01-30)
   • #2450: Docs: Update guide (merged 2026-01-28)

🔄 IN PROGRESS (open cherry-pick PRs)
   2 PRs being reviewed:
   • #2800: cherry-pick from #2567 → release/1.7.2511 (3 hours old, 0 reviews)
   • #2801: cherry-pick from #2680 → release/1.7.2511 (1 hour old, 1 review)

⚠️  BLOCKED (conflicts detected)
   1 PR has merge conflicts:
   • #2525: Blocked in worktree .git/worktrees/backport-temp-20260206T143022Z/
            Conflicted files: src/foo.rs
            Next step: Run analyze-pr-deps --file src/foo.rs --target release/1.7.2511

✅ COMPLETED (labeled backported_1.7.2511)
   3 PRs successfully backported:
   • #2345: Refactor (merged in release/1.7.2511)
   • #2200: Bugfix (merged in release/1.7.2511)
   • #2100: Feature (merged in release/1.7.2511)

───────────────────────────────────────────────────────────────
Summary:
  Pending:     4 PRs
  In Progress: 2 PRs
  Blocked:     1 PR
  Completed:   3 PRs
  ─────────────────
  Total:       10 PRs marked for backport

Status: 70% complete. 2 more PRs need review, 1 blocked (conflict resolution needed)
```

**Detailed Format Output**:
```
──────────────────────────────────────────────────────────────────
PR #2567: Fix: Handle edge case
──────────────────────────────────────────────────────────────────
Backport Status: PENDING (labeled backport_1.7.2511)

Original PR:
  Merged to main: 2026-02-01T10:30:00Z
  Author: @contributor
  Link: https://github.com/microsoft/openvmm/pull/2567

Backport Details:
  Target branches: release/1.7.2511, staging/1.7.2511
  Release branch status: Not yet cherry-picked
  Staging branch status: Not yet cherry-picked

Next Step: Run to create cherry-pick PR:
  gen_cherrypick_prs.py release/1.7.2511 2567
```

**JSON Format Output**:
```json
{
  "version": "1.7.2511",
  "targetBranches": ["release/1.7.2511", "staging/1.7.2511"],
  "generatedAt": "2026-02-06T14:30:00Z",
  "status": {
    "pending": {
      "count": 4,
      "prs": [
        {
          "number": 2567,
          "title": "Fix: Handle edge case",
          "mergedAt": "2026-02-01T10:30:00Z",
          "url": "https://github.com/microsoft/openvmm/pull/2567",
          "backportLabel": "backport_1.7.2511"
        }
      ]
    },
    "inProgress": {
      "count": 2,
      "prs": [
        {
          "originalPR": 2567,
          "cherryPickPR": 2800,
          "state": "open",
          "targetBranch": "release/1.7.2511",
          "createdAt": "2026-02-06T11:30:00Z",
          "url": "https://github.com/microsoft/openvmm/pull/2800"
        }
      ]
    },
    "blocked": {
      "count": 1,
      "prs": [
        {
          "number": 2525,
          "title": "Refactor: Extract utility",
          "worktreePath": ".git/worktrees/backport-temp-20260206T143022Z/",
          "conflictedFiles": ["src/foo.rs"],
          "targetBranch": "release/1.7.2511"
        }
      ]
    },
    "completed": {
      "count": 3,
      "prs": [
        {
          "number": 2345,
          "title": "Refactor",
          "mergedIn": "release/1.7.2511",
          "mergedAt": "2026-02-04T15:00:00Z",
          "backportedLabel": "backported_1.7.2511",
          "url": "https://github.com/microsoft/openvmm/pull/2345"
        }
      ]
    }
  },
  "summary": {
    "total": 10,
    "percentComplete": 30,
    "nextSteps": [
      "Review 2 open cherry-pick PRs",
      "Resolve 1 conflict (analyze-pr-deps for missing prerequisites)",
      "Check 4 pending PRs for cherry-pick"
    ]
  }
}
```

**Return Codes**:
| Code | Meaning |
|------|---------|
| 0 | Status retrieved successfully |
| 1 | Version not found (no PRs labeled for this version) |
| 2 | Invalid arguments |
| 3 | GitHub API error (auth failure, rate limit) |

---

## Behavior Specification

### Phase 1: Input Validation
1. Validate version format matches `^[0-9.]+$`
2. If `--branch` provided: Validate format and existence
3. If `--pr` provided: Validate PR exists

### Phase 2: GitHub API Queries (parallel)
1. **Query PRs with label `backport_{version}`**:
   ```bash
   gh pr list --repo {repo} --state merged --label backport_{version} --json number,title,mergedAt,url
   ```
   → Populates "pending" state

2. **Query PRs with label `backported_{version}`**:
   ```bash
   gh pr list --repo {repo} --state merged --label backported_{version} --json number,title,mergedAt,url
   ```
   → Populates "completed" state

3. **Query open cherry-pick PRs to target branch**:
   ```bash
   gh pr list --repo {repo} --state open --base release/{version}\ 
     --search "cherry-pick from" --json number,title,baseBranch,createdAt,url
   ```
   → Populates "in progress" state

4. **Detect blocked PRs** (worktrees with conflict state):
   ```bash
   ls -la .git/worktrees/ | grep backport-temp
   ```
   → Identify any retained worktrees from conflicts

### Phase 3: Data Correlation
1. Link original PR to cherry-pick PR via "cherry-pick from #XXXX" in cherry-pick PR title
2. Calculate merge order based on `mergedAt` timestamps
3. Detect completion by presence of `backported_` label

### Phase 4: Output Generation
1. Format output according to `--format` flag
2. Include actionable next steps based on state
3. Show performance metrics (% complete, hours spent, reviews pending)

### Phase 5: Return Code
- 0: Success
- 1: No matches found (no PRs with labels for this version)
- 2: Invalid input
- 3: API error

---

## Differences from Other Tools

**Key distinction**: Status tool is **read-only** and **accessible to all users**.

- No branch creation
- No PR creation
- No label modification
- No git write operations
- Pure information service

This makes it ideal for:
- Developers checking if their PR was backported (before asking maintainers)
- Release managers monitoring backport progress
- Contributors understanding current backport workflow status
- Automation/scripting that depends on current state

---

## Testing Strategy

**Unit Tests**:
- Input validation (version format, branch matching, PR numbers)
- Output formatting (summary, table, JSON, detailed)
- State categorization logic
- Performance under load (50+ PRs)

**Integration Tests**:
- Mock GitHub API responses for all four query types
- Real repository integration (against test fork or staging branch)
- Cross-branch querying (both release and staging)
- Blocked query detection (worktree filesystem scan)

**Manual Tests**:
- Run on real repository, verify counts match manual inspection
- Check JSON output parses correctly
- Verify links are clickable in different formats
- Test PR-specific output (`--pr` flag)
- Verify performance (<5 seconds typical)
