# Research & Clarifications: PR Branch Management Tools

**Phase**: 0 (Research) | **Status**: Complete | **Date**: 2026-02-06

## Research Summary

All major technical decisions and unknowns have been resolved in the feature specification. This document consolidates key architectural decisions made during specification phase.

## Key Technical Decisions

### 1. Working Directory Isolation Strategy

**Decision**: Git Worktrees (`.git/worktrees/backport-temp-<timestamp>/`)

**Rationale**:
- Allows developer to continue work in main working directory uninterrupted during cherry-pick operations
- Native git feature (no external dependencies needed)
- Provides complete isolation: separate branch state, index, working tree
- Clean cleanup available via `git worktree remove`

**Alternatives Considered**:
- Shallow clones to temp directory: Higher resource usage, slower
- Stashing changes + switching branches: Risky (accidental loss of work), not truly isolated

**Implementation Details**:
- Create worktree: `git worktree add .git/worktrees/backport-temp-{timestamp} {target-branch}`
- Cherry-pick in worktree: `git -C {worktree_path} cherry-pick {commit_hash}`
- Auto-cleanup on success: `git worktree remove {worktree_path}`
- Retain on failure with instructions for manual cleanup

### 2. Post-Execution State Management (Worktree Cleanup)

**Decision**: Auto-cleanup on success with user control flags

**Rationale**:
- Default behavior: Auto-cleanup prevents disk clutter for typical clean backports
- Debugging needs: `--keep-worktree` flag allows retention for investigation
- CI/automation: `--force-cleanup` flag enables automation scenarios without manual intervention

**Implementation Details**:
```
Success (no conflicts):
  - Delete worktree automatically  
  - Inform user of cleanup

Failure (conflicts detected):
  - Retain worktree with conflict state
  - Output clear summary: conflicted files, worktree path
  - Provide suggestion: "Run analyze-pr-deps --file {file} to find missing prerequisites"
  - Instruction for manual cleanup: "To cleanup: git worktree remove {path}"

Flags:
  --keep-worktree: Never cleanup (for debugging)
  --force-cleanup: Always cleanup even on conflict (for CI)
```

### 3. Branch Naming Convention for Staging vs Release

**Decision**: Uniform naming pattern for both staging and release branches

**Rationale**:
- Simpler naming: `{prefix}/{sanitized-target}/pr-{number}` works for both
- Target branch specified explicitly via command-line (not inferred from label)
- Consistent with repository conventions

**Pattern**: `backport/{release-version}/pr-{pr-number}`
- Example: `backport/1.7.2511/pr-2680` (works for both `release/1.7.2511` and `staging/1.7.2511`)
- Sanitization: Replace `.` with `-` in version for safe branch names: `1.7.2511` → `1-7-2511`

**Label Convention**:
- Same label applies to both staging and release: `backport_1.7.2511` (target branch specified via CLI)
- Completion label: `backported_1.7.2511`

### 4. Manual Conflict Resolution Workflow

**Decision**: Tool errors out; dependency analysis tool helps understand why

**Rationale**:
- Conflicts require human judgment about prerequisite ordering
- Providing clear error summary + path to investigation tools is better than attempting resumption
- Separate analysis tool focuses on its concern: "what changed these files and in what order?"

**Workflow**:
1. Cherry-pick encounters conflict → Tool stops, outputs summary
2. User runs `analyze-pr-deps` to understand missing prerequisites
3. User manually resolves OR adjusts backport order
4. Worktree retained for manual testing if needed
5. Manual cleanup when done

### 5. Label Convention for Staging vs Release

**Decision**: Single label convention `backport_X.Y.Z` applies to both staging and release branches

**Rationale**:
- Simpler labeling: Maintainers don't need separate `backport_staging` labels
- Target branch explicitly specified: CLI argument determines whether backport targets staging or release
- More flexible: Same PR can be backported to both branches in different operations

**Implementation Detail**:
```bash
# Same label, different target branches:
gen_cherrypick_prs.py release/1.7.2511 --from-backport-label backport_1.7.2511
gen_cherrypick_prs.py staging/1.7.2511 --from-backport-label backport_1.7.2511

# Both target the same `backport_1.7.2511` label but create PRs to different branches
```

## Documentation & Best Practices

### Input Validation Patterns

All tools must validate user inputs to prevent command injection:

```python
# PR number validation
import re
if not re.match(r'^[0-9]+$', pr_number):
    raise ValueError(f"Invalid PR number: {pr_number}")

# Branch name validation
if not re.match(r'^(main|release|staging)/[0-9.]+$', branch_name):
    raise ValueError(f"Invalid branch name: {branch_name}")

# Label validation
if not re.match(r'^[a-zA-Z0-9_-]+$', label):
    raise ValueError(f"Invalid label: {label}")

# All subprocess calls must use list arguments (no shell=True)
subprocess.run(['git', 'cherry-pick', commit_hash], check=True, cwd=worktree)
```

### Error Message Format

All error messages must include:
1. What went wrong (clear, specific)
2. Why it happened (brief context)
3. How to fix it (actionable guidance)

Example:
```
ERROR: Cherry-pick conflict detected in src/foo.rs

This usually means another PR (not yet backported) modified the same file.

Next steps:
1. Identify missing prerequisites: 
   analyze-pr-deps --file src/foo.rs --target release/1.7.2511
2. Backport missing PRs first, then retry this one
3. Manual investigation: Worktree retained at /path/to/worktree/

To cleanup the worktree: git worktree remove /path/to/worktree/
```

### GitHub API Integration

- Use `gh` CLI for all GitHub API operations (avoids managing tokens locally)
- Parse JSON output: `-q` flag for filtering, `--json` for structured output
- Error handling: Capture exit codes to distinguish auth errors, network issues, not-found

Example patterns:
```bash
# Get PR merge commit
gh pr view {pr_number} --json mergeCommit --jq '.mergeCommit.oid'

# List PRs with label
gh pr list --state merged --label {label} --json number,title,mergedAt --jq '.'

# Check if commit in branch
git merge-base --is-ancestor {commit} {branch} && echo "exists" || echo "not found"
```

## No Unresolved NEEDS CLARIFICATION

All major unknowns from the specification have been addressed:
- ✅ Working directory isolation strategy
- ✅ Post-execution state management (worktree cleanup)  
- ✅ Branch naming for staging vs release
- ✅ Manual conflict resolution workflow
- ✅ Label convention for staging vs release
- ✅ User roles and access patterns (status tool read-only, other tools require write access)

## User Access & Permission Model

**Key Decision**: Status dashboard accessible to all users; other tools for users with write access.

**Rationale**:
- Provides visibility to all team members (can anyone answer "is PR #2680 backported yet?")
- Cherry-pick/relabel tools require write permissions (expected constraint)
- Maintainer-specific workflows for staging→release promotion (future enhancement)
- Reduces confusion: no hidden processes, transparent backport status for all

**Implementation**:
- `backport_status.py`: Read-only GitHub API queries, zero git write operations
- Other tools: Check for write permissions, fail gracefully with actionable message if insufficient access
- Future: May add maintainer-only config tool for governance

Specification is ready for Phase 1 (Design & Contracts).

---

## Implementation Notes (2026-02-07)

### Completed Phases

**Phase 1-2 (Setup + Foundational)**: ✅ Complete
- Created shared_utils.py with input validation, GitHub API wrappers, git helpers
- All validation functions written with regex patterns
- 29 tests passing across all implemented tools

**Phase 3 (US5 - Status Dashboard)**: ✅ Complete
- backport_status.py: Read-only tool for checking backport status
- Supports multiple output formats (summary, table, json, detailed)
- Accessible to all users, no write permissions required

**Phase 4 (US1 - Cherry-Pick Tool)**: ✅ Complete
- gen_cherrypick_prs.py: Automated cherry-pick with worktree isolation
- Refactored to use YAML summary output
- Conflict detection and worktree retention for investigation

**Phase 5 (US2 - Relabeling)**: ✅ Complete
- relabel_backported.py: Updates labels after successful backports
- Dry-run by default, --update flag to apply changes
- Title mismatch detection with --force-update-pr override

### Key Implementation Decisions

**Label Validation Pattern Fix**:
- Initial pattern: `^[a-zA-Z0-9_-]+$` (rejected dots)
- Fixed pattern: `^[a-zA-Z0-9_.-]+$` (allows `backport_1.7.2511`)
- Discovered during test execution when `validate_label("backport_1.7.2511")` failed

**Test Infrastructure**:
- pytest configured in virtual environment
- All tools follow same test pattern: unit tests + integration-style tests
- Mock GitHub API responses using pytest monkeypatch
- 29 tests total, all passing in ~0.08s

### Remaining Work

**Phase 6 (US3 - Staging Support)**: Not started
- Update branch validation to handle staging/* branches
- Extend all tools to detect backports in both release/ and staging/
- Integration tests for staging branch workflows

**Phase 7 (US4 - Dependency Analysis)**: Not started
- analyze_pr_deps.py: Investigate why cherry-picks conflict
- File-based and PR-based analysis modes
- Identify missing prerequisite PRs by file modification history

**Phase 8 (US6 - Workflow Wrapper)**: Not started
- backport_workflow.py: Orchestrate complete backport cycle
- Sequential execution: cherry-pick → wait for merges → relabel
- Interactive prompts with abort/continue options

**Phase 9 (Polish)**: Not started
- README.md and Guide/src/dev_guide/pr_management.md
- Cross-tool consistency (error messages, output formatting)
- Performance testing and final constitution check

### Next Session Priorities

1. Phase 6 (Staging Support): Minimal code changes, high value
2. Phase 7 (Dependency Analysis): New tool, most complex remaining work
3. Phases 8-9: Orchestration and documentation
