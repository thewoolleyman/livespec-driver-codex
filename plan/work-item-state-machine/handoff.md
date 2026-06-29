# Handoff — work-item-state-machine (L2 migration, livespec-driver-codex)

**Thread:** `plan/work-item-state-machine/` · **Ledger anchor:** epic
`livespec-driver-codex-kuhp5a` (`livespec-driver-codex` beads tenant) ·
**Fleet anchor (PROSE ref):** `livespec-35s3zo` (livespec core tenant —
NEVER a typed cross-tenant `depends_on`, which would dangle and pollute
the `blocked:dependency` derivation; per decision 41/45).

> Status is **derived from the ledger**, never stored here. To read it:
> ```bash
> with-livespec-env.sh bd -C /data/projects/livespec-driver-codex children livespec-driver-codex-kuhp5a --json
> ```
> (`with-livespec-env.sh` injects the fleet tenant password; probe-only,
> never echo it.)

## ✅ STATUS: L2 MIGRATION COMPLETE (2026-06-29)

This is the **thin L2 migration track** for the fleet-wide
work-item-lifecycle epic (anchored on `livespec-35s3zo`; design of record
`/data/projects/livespec/plan/work-item-state-machine/research/`,
decisions 1–46). Per decision 42 (`Driver → orchestrator = zero deps`)
this repo carries **no work-item schema**, so the migration is a **pure
tenant data migration** — no repo code/spec change — formalized here for
the record (decision 46; slice-plan `04-slice-plan.md` §"L2 — migration").

The L1a release `livespec-orchestrator-beads-fabro` **v0.3.0** (which ships
`rebalance-ranks` + the 5 custom statuses + the rank schema) is the gate
this track consumed. This Driver repo has **no orchestrator version pin to
bump** — the orchestrator is registered host-wide as a Codex plugin (per
`.claude/CLAUDE.md` §"Codex dogfooding") and is already at v0.3.0; the
migration was applied through that v0.3.0 tooling.

### What landed (the two mandated data actions + formalization)

1. **Registered the 5 custom lifecycle statuses** (decision 36) on the
   `livespec-driver-codex` tenant, via the orchestrator's
   `store.register_custom_statuses` →
   `bd config set status.custom "backlog,pending-approval,ready:active,active:wip,acceptance:wip"`.
   The other two livespec states reuse beads built-ins: `blocked`
   (name-matched) and `done`→`closed` (the one adapter name-mapping).
   **Verified:** `bd config get status.custom` returns the CSV above.

2. **Backfilled the required `rank` field** (decision 39) via the
   orchestrator's `rebalance-ranks` **legacy-seed** primitive
   (`commands/rebalance_ranks.legacy_seed`, seeded by
   `priority → captured_at → id`). The tenant held **0 work-items** at
   migration time, so the backfill is a **verified zero-item no-op**
   (`legacy_seed([]) == []`). Every item filed from here on carries a real,
   non-sentinel `rank` natively (the bottom-sentinel `~` only ever surfaces
   for superseded historical lines lacking `rank` — of which there are
   none here).

3. **Formalized in the ledger** (this thread anchors a beads `epic`;
   children file through the one consented store-writer, never a direct
   cross-plane write — `plan` prose §"Anchor a ledger epic"):
   - **Epic** `livespec-driver-codex-kuhp5a` — `type=epic`, `status=backlog`,
     `rank=a0`. The thread's status anchor; prose-linked to `livespec-35s3zo`.
   - **Work-item** `livespec-driver-codex-47mj3h` — `type=chore`,
     `status=backlog`, `rank=a1`; a **parent-child child** of the epic
     (`bd children` → 1 child). Records the migration; prose-linked to
     `livespec-35s3zo`. Filed under the **new v0.3.0 schema** (custom
     status via the 2-step `bd create`→`bd update --status`; `rank` in
     `metadata.rank`) — so this very record dogfoods the migrated shape.

### Verification evidence (2026-06-29)

```
$ bd -C /data/projects/livespec-driver-codex config get status.custom
backlog,pending-approval,ready:active,active:wip,acceptance:wip

$ bd -C /data/projects/livespec-driver-codex list --status all --json   # 2 items
  livespec-driver-codex-kuhp5a | status=backlog | type=epic   (rank a0, non-sentinel)
  livespec-driver-codex-47mj3h | status=backlog | type=chore  (rank a1, non-sentinel)

$ bd -C /data/projects/livespec-driver-codex children livespec-driver-codex-kuhp5a --json
  child count: 1 → livespec-driver-codex-47mj3h
```

The orchestrator read path (`materialize_work_items(read_work_items(...))`)
round-trips both records with real non-sentinel ranks, confirming
`metadata.rank` persistence under the migrated schema.

## Autonomy posture

The design is LOCKED (decisions 1–46). This thin track **AUTO-PROCEEDS** —
it does not pause for maintainer approval. Discipline applied:
worktree → PR → rebase-merge; `mise exec -- git`; never `--no-verify`;
secrets probe-only (the fleet `with-livespec-env.sh` 1Password wrapper
injects `BEADS_DOLT_PASSWORD`; the value is never echoed or committed).
Halt + report only on a genuine blocker.

## Discovered drift (NON-blocking — flagged for the family-infra phase)

This repo's `.livespec.jsonc` and `.claude/CLAUDE.md` still describe the
beads tenant connection block as **DEFERRED / "NOT yet provisioned,"** but
the tenant **is** live and provisioned: `.beads/config.yaml` is committed
(server-mode, tenant `livespec-driver-codex` on `127.0.0.1:3307`, a real
`project_id` in `metadata.json`), and it responds to `bd`. The migration
was therefore applied through the committed `.beads/config.yaml` + the
fleet wrapper, NOT through a `.livespec.jsonc` `connection` block.

Consequence: the orchestrator CLIs that resolve via
`.livespec.jsonc` (`next`, `list-work-items`, `doctor`, `rebalance-ranks`
`main`) cannot yet operate this tenant (they raise
`ConnectionPrefixMissingError`). The sibling **livespec-driver-claude**
already carries the full `connection` block (prefix == tenant == database
== server_user == repo name). **Recommended reconciliation** (the deferred
family-infra phase, NOT this thin migration track): add the
`livespec-orchestrator-beads-fabro.connection` block to
`.livespec.jsonc` mirroring driver-claude, and refresh the stale
"DEFERRED" comments. Kept out of this PR to honor the explicit deferral
boundary and keep the migration capture minimal.

## Next action (MAINTAINER-OWNED)

The data migration is done and verified; nothing remains to implement on
this track. The maintainer may, at their discretion, **accept and close**
the work-item + epic (the acceptance valve, decision 9/34 — `ai-then-human`
by default) and archive this thread to `plan/archive/` on epic close
(`plan` prose §"Archive on epic close"). Closing the epic is the thread's
terminal transition; until then this open epic is the durable anchor for
the record.
