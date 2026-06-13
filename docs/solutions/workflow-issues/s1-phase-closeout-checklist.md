---
title: S1 phase closeout checklist and AI_USAGE accuracy
date: 2026-06-13
category: workflow-issues
module: project-process
problem_type: workflow_issue
component: development_workflow
severity: medium
applies_when:
  - "Closing a story or phase before starting the next (S1, S2, S6, etc.)"
  - "Updating AI_USAGE.md after implementation or protocol fixes"
  - "Declaring acceptance criteria complete"
tags:
  - closeout
  - ai-usage
  - review-tier
  - smoke-gate
  - s1
  - ce-plan
  - ce-work
---

# S1 phase closeout checklist and AI_USAGE accuracy

## Context

S1 shipped the runtime spine with adversarial review (18 findings), follow-up ACP protocol fixes after smoke failure, and a formal closeout review. `AI_USAGE.md` initially contained stale counts, an incorrect AC scope claim, and an outdated SSE lifecycle narrative. Process gaps (no git baseline, no full `ce-code-review`) were documented during closeout.

Future `/ce-plan`, `/ce-work`, and review sessions should use this checklist before calling a phase closed.

## Guidance

### Phase closeout checklist (required before next phase)

1. **Run tests** — record exact counts (e.g. `16 passed, 1 skipped`), not stale numbers
2. **Run smoke gates** when the phase touches live external protocols (`make smoke-goose` for Goose ACP)
3. **Document review tier used**:
   - Adversarial review only → say so explicitly
   - Full `ce-code-review` → record findings and residuals
   - Formal closeout review → record date and scope
4. **Update `AI_USAGE.md`** with distinct sections for:
   - Original adversarial findings (fixed vs deferred)
   - Follow-up fixes after smoke/protocol drift (separate from original ship)
   - Formal closeout review outcome
   - Deferred items with target phase (S2, S3, S6)
5. **Do not claim broad AC completion** unless verified (e.g. S1 ≠ AC-1 through AC-7)
6. **Manual demo** — run or honestly document status (API + Vite proxy acceptable when visual browser not recorded)
7. **Git baseline** — init repo and commit before next phase when story rules require it

### AI_USAGE.md accuracy rules

| Do | Don't |
|----|-------|
| Map story scope to specific ACs (AC-4, partial AC-3) | Claim "AC-1 through AC-7" for S1 |
| Mark superseded decisions explicitly | Leave outdated fix narratives as current |
| Record exact pytest/smoke results with date | Copy stale validation counts |
| List deferred items with owner phase | Hide open Medium/Low findings |
| Note missing review tiers | Imply full code review ran when only adversarial ran |

### Review tier expectations

| Tier | When | S1 status |
|------|------|-----------|
| Adversarial review | Post-implementation bug hunt | Done — 18 findings |
| Formal closeout review | After protocol fixes, before next phase | Done — 2026-06-13 |
| `ce-code-review` | Sensitive/large diffs, pre-PR | **Not run** |
| Human PR review | Submission | **Not run** |

Adversarial + closeout is sufficient to **start S2** but not equivalent to full code review.

## Why This Matters

Without closeout discipline, the next phase inherits stale docs, false AC claims, and undiscovered protocol drift. `AI_USAGE.md` is the audit trail for hiring/submission — inaccuracies undermine trust. Smoke gates catch integration assumptions that mocks miss.

## When to Apply

- End of every story (S1–S6)
- After any live-protocol fix (like Goose ACP drift)
- Before `/ce-plan` or `/ce-work` for the next story
- When updating `AI_USAGE.md` status to Complete

## Examples

**Incorrect S1 completion claim:**

> All S1 acceptance criteria implemented (BUILD_SPEC §10 AC-1 through AC-7)

**Correct:**

> S1 delivers AC-4 smoke gate, partial AC-3 tests, runtime spine, schema/seed foundation; AC-7 fresh-clone verification deferred to S6

**Correct superseded decision note:**

> Superseded (2026-06-13): single outer SSE for full lifecycle — replaced by sync initialize POST + scoped SSE streams per Goose 1.37.0 re-probe

## S1 deferred items (carry to later phases)

| Item | Target phase |
|------|----------------|
| Wire `TaskInput.extensions` → `mcpServers` | S2+ |
| Map `tool_call` names (not `unknown`) | S2 early hygiene |
| Persist `channels` on agent create | Before S3 |
| Frame replay test (`test_acp_adapter.py` intent) | Before S6 / AC-3 |
| ACP retry policy | Later |
| Structured logging | Later |
| Copy-to-clipboard in browser runner | Later |
| Sanitize `system_prompt` in preamble | Optional |
| Fresh-clone AC-7 verification | S6 |

## Related

- `docs/solutions/integration-issues/goose-acp-protocol-and-sse-s1.md` — technical ACP/SSE/smoke learnings
- `AI_USAGE.md` — S1 entry (updated 2026-06-13 closeout)
- `_bmad-output/planning-artifacts/stories.md` — story scope and hour caps
