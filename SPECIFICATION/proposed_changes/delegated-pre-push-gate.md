---
topic: delegated-pre-push-gate
author: claude:delegated-gate-fleet-rollout
created_at: 2026-10-26T23:28:33Z
---

## Proposal: The repository MAY delegate its pre-push gate to the fleet's remote executor

### Target specification files

- SPECIFICATION/non-functional-requirements.md
- SPECIFICATION/scenarios.md

### Summary

Ratify delegating this repository's pre-push gate to the fleet enforcement suite's remote executor (the k3s gate cluster). The opt-in is version-controlled. A host without the executor credential, such as a factory sandbox, gates locally and says so. A delegating host's pre-push runs the delegation client in place of the aggregate, and an absent verdict refuses the push rather than falling back. Delegation changes WHERE `just check` runs, never WHAT it verifies. The clause adopts, by citation, livespec's Delegated gate execution contract and livespec-dev-tooling's client contract, in the same terms livespec-overseer (v069), livespec-driver-claude (v014) and livespec-runtime (v032) ratified.

### Motivation

Plan delegated-gate-fleet-rollout (livespec-dev-tooling epic livespec-dev-tooling-mvalxq) brought every livespec repository into scope under the maintainer direction of 2026-10-24: enable the delegated pre-push gate on every livespec repo. On 2026-10-26 the maintainer also directed maxing out the Kubernetes capacity. This repository's spec currently says `just check` runs locally, in pre-push and in CI, and that every gate is wired into pre-push via lefthook. An opt-in carrier would therefore implement behaviour the spec does not permit, and the launch-time DoD screen refused livespec's carrier for exactly that reason until livespec ratified a clause (livespec-bwzu5t). The precondition the coordinator set on 2026-10-25 is already met: the check recipe reads SKIP_TARGETS (PR #854).

### Proposed Changes

In SPECIFICATION/non-functional-requirements.md §"Enforcement suite", the paragraph "Every gate is wired into both pre-commit/pre-push (via lefthook) and CI (via the per-target matrix in `.github/workflows/ci.yml`), so the same suite runs in every context." MUST be followed by:

> Where the repository has delegated its pre-push gate per the next paragraph, a pre-push from a delegating host obtains the same `just check` aggregate's verdict from the remote executor against the pushed tree instead of running it on the pushing host, save the checks the delegation contract places on the pushing host, and except where an explicit local run has already authorized the tree. This changes WHERE the aggregate runs and MUST NOT change WHAT it verifies.
>
> The repository MAY delegate its pre-push gate to the remote executor of the fleet enforcement suite's delegation client (livespec-dev-tooling §"Delegated pre-push gate"). When it does, it MUST conform to the delegation contract livespec ratifies in §"Enforcement-suite invocation", clause **Delegated gate execution**. For this repository that means:
>
> - Delegation MUST be opted in by the repository's version-controlled configuration. It MUST be withdrawn only by a change to that configuration, never per push or per host. The gate MUST remain runnable on the pushing host by an explicit act whether or not delegation is opted in.
> - A push MUST delegate only from a host that holds the credential authorizing it to submit to the executor. A host that holds none, such as a factory sandbox, MUST run the repository's gate recipe on that host without delegation, and MUST report that it gated locally.
> - The pre-push path for a delegating host MUST run the delegation client in place of the aggregate, and MUST have no branch from the client's result to a local run of the gate. An absent verdict MUST refuse the push.
> - A check that reads an authorization held outside the tree MUST run on the pushing host with that host's own credentials, not in the executor, and its result MUST join the delegated verdict, so an authorization the executor cannot read is never treated as granted.
> - The check recipe MUST read the fleet's recognised skip variable, `SKIP_TARGETS`, so the members the delegation contract places on the pushing host are left out of the executor's run. A run that skipped any member MUST NOT write the green token.

In SPECIFICATION/scenarios.md a new scenario MUST be added:

```
## Scenario: a delegating host's push gates on the remote executor and refuses on no verdict

Given this repository's version-controlled configuration opts it in to delegating its pre-push gate

And the pushing host holds the credential to submit to the remote executor

When a git push of a new tree runs the pre-push gate

Then the pre-push path MUST run the delegation client instead of running `just check` on the pushing host

And the push MUST complete only on a passing verdict from the executor

And the push MUST be refused when the executor returns no verdict
```

The revise that accepts this MUST, in the same change, add `tests/heading-coverage.json` coverage for the new scenario heading. A spec-first `TODO` row naming the owed test's tier and THIS repository's own carrier work item, is acceptable. The same change MUST also add `livespec-dev-tooling: ["§\"Delegated pre-push gate\""]` and `livespec: ["§\"Enforcement-suite invocation\""]` to `.livespec.jsonc` `external_references`, in the bare heading form, so doctor-no-cross-spec-reference admits both citations.
