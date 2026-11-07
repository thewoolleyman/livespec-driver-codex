---
topic: codex-curated-marketplace-exclusion
author: claude:codex-plugin-hook-path-regression
created_at: 2026-11-07T14:14:34Z
---

## Proposal: Exclude Codex-curated marketplaces from hook-cache coverage

### Target specification files

- SPECIFICATION/contracts.md
- SPECIFICATION/non-functional-requirements.md

### Summary

Redefine which plugins the hook-cache reconciler and observer cover so that a plugin from a Codex-curated marketplace (a local marketplace whose resolved source lies inside the Codex bundled-marketplace directory or the Codex runtime cache) is excluded, because the ChatGPT app now registers configuration entries for its own curated marketplaces and entry existence no longer separates host-registered marketplaces from Codex-curated ones. Local marketplaces outside those directories stay covered and keep the full release-verification rule. The same proposal amends the covered-set example sentence and the two enumerations of required mock-cache test coverage so nothing is left contradicting or omitting the new rule.

### Motivation

This change fixes work item livespec-driver-codex-hbi and is filed under plan livespec-3rfjga (livespec repo, plan codex-plugin-hook-path-regression).

On 2026-11-06, on the host chads-macbook-pro, running the ChatGPT desktop app 26.1007.71326 and Driver plugin 0.12.1, `mise exec -- just ensure-codex-plugins` exited 1. The only failures were `openai-bundled/{browser,chrome,unified-computer-use}: unverified hook .codex-plugin/plugin.json:{Interrupt,SubagentStop,Stop} (release tag cannot be identified for this marketplace)`. The ChatGPT app now writes its own Codex configuration entries: a `[marketplaces.openai-bundled]` entry with `source_type = "local"` and `source = "~/.codex/.tmp/bundled-marketplaces/openai-bundled"`, and an `openai-primary-runtime` entry, also local, under `~/.cache/codex-runtimes/`.

The contract defines a covered plugin by the existence of a `[marketplaces.<name>]` entry and says that this is how Codex-curated caches are excluded. Because the app now registers entries for its own curated marketplaces, those plugins became covered, and the trust-continuity rule (a plugin with no identifiable release tag is reported and never trusted) failed provisioning. That refusal is the specified behaviour; what no longer matches its intent is the exclusion criterion. The fix keeps the refusal and replaces the criterion with one based on where a local marketplace's source actually lives.

A real counter-example on the development host must stay covered: `[marketplaces.honeycomb-plugins]` with `source_type = "local"` and `source = "/home/ubuntu/.claude/plugins/marketplaces/honeycomb-plugins"` is a third-party local marketplace outside any Codex-managed directory, and it is correctly reported as unverified today. The new criterion keys on the resolved source path rather than on `source_type = "local"` alone, so that marketplace remains covered and keeps being reported.

### Proposed Changes

### Amendment 1 — the covered-plugin definition

In `SPECIFICATION/contracts.md`, replace this exact text (verbatim, including its line breaks):

```text
A cache directory whose marketplace has no
such entry is not a covered plugin; this is how caches that Codex
manages from its own curated sources are excluded.
```

with:

```text
A cache directory whose marketplace has no such entry is not a covered plugin. Neither is a plugin whose marketplace is **Codex-curated**: its Codex configuration entry declares a local source (`source_type = "local"`) whose resolved path lies inside a directory that Codex or the ChatGPT app creates and populates itself, namely the bundled-marketplace directory under the Codex home (`$CODEX_HOME/.tmp/bundled-marketplaces/`, where the Codex home is `CODEX_HOME` when set and `~/.codex` otherwise) and the Codex runtime cache (`codex-runtimes/` under the user's cache directory). The ChatGPT app registers such entries itself, for example `openai-bundled` and `openai-primary-runtime`, so the existence of an entry no longer separates the marketplaces a host registered from the ones Codex curates; the location of a local source does. The Driver MUST resolve a local source path before classifying it, expanding `~` and following symbolic links. These directories are a property of Codex's own layout, not a list of plugins, so the covered set itself remains derived from measured state as required below. Codex's own hook-trust interface governs a Codex-curated plugin's hooks: the Driver MUST NOT trust, verify, repair, disable or remove them, and their presence MUST NOT fail provisioning or observer health. A local marketplace whose resolved source lies outside those directories remains covered, and the release-verification rule for hook trust below applies to it in full.
```

This is in §"Codex hook-cache compatibility", the paragraph that begins "The Driver MUST provide a cache-independent host reconciler".

### Amendment 2 — the covered-set example (drift sweep)

The same paragraph says the set includes non-livespec plugins from "registered marketplaces". After Amendment 1, a Codex-curated marketplace is also registered but is not covered, so the sentence would be left overbroad.

In `SPECIFICATION/contracts.md`, replace this exact text (verbatim, including its line breaks):

```text
The set includes non-livespec plugins from registered
marketplaces, for example a third-party plugin that ships
`bash`-invoked hooks.
```

with:

```text
The set includes non-livespec plugins from registered marketplaces that are not Codex-curated, for example a third-party plugin that ships `bash`-invoked hooks, including one installed from a local marketplace whose resolved source lies outside the Codex-curated directories.
```

### Amendment 3 — required test coverage, Enforcement suite (drift sweep)

The `check-dev-tooling` bullet in §"Enforcement suite" enumerates what the mock-cache integration test MUST cover. Without an addition, the new exclusion and its local-outside counter-case would be unrequired by the enforced test list.

In `SPECIFICATION/non-functional-requirements.md`, replace this exact text (verbatim, including its line breaks):

```text
  which that setting is not enabled reported. The real transition test
  MUST also verify that Codex treats each retained hook as trusted after
  reconciliation.
```

with:

```text
  which that setting is not enabled reported. The real transition test
  MUST also verify that Codex treats each retained hook as trusted after
  reconciliation.
  The mock-cache integration test MUST also cover the Codex-curated exclusion: a plugin whose marketplace's local source resolves inside the Codex bundled-marketplace directory or the Codex runtime cache, including through `~` expansion or a symbolic link, is neither reconciled, trusted, nor reported, and does not fail provisioning or observer health, while a plugin from a local marketplace whose resolved source lies outside those directories remains covered and, with no identifiable release tag, is reported and never trusted.
```

### Amendment 4 — required test coverage, Test discipline (drift sweep)

§"Test discipline" repeats the same enumeration in prose; it is amended in lockstep with Amendment 3 so the two lists stay identical.

In `SPECIFICATION/non-functional-requirements.md`, replace this exact text (verbatim, including its line breaks):

```text
untrusted, a host on which that setting is not enabled reported. The
real transition test MUST also verify that Codex treats each retained
hook as trusted after reconciliation.
```

with:

```text
untrusted, a host on which that setting is not enabled reported. The
real transition test MUST also verify that Codex treats each retained
hook as trusted after reconciliation.
The mock-cache integration test MUST also cover the Codex-curated exclusion: a plugin whose marketplace's local source resolves inside the Codex bundled-marketplace directory or the Codex runtime cache, including through `~` expansion or a symbolic link, is neither reconciled, trusted, nor reported, and does not fail provisioning or observer health, while a plugin from a local marketplace whose resolved source lies outside those directories remains covered and, with no identifiable release tag, is reported and never trusted.
```

### Drift-sweep dispositions where no amendment is needed

- `SPECIFICATION/contracts.md` §"Hook bundle", the trust-model paragraph ("For every covered plugin, the Driver's own payload included, ..."): it relies on the term "covered plugin" and inherits the new definition; no change needed. Every later rule in §"Codex hook-cache compatibility" (trust continuity, release verification, fail-closed fallback, per-plugin state and health, supervision) is scoped to covered plugins and therefore no longer reaches Codex-curated plugins without edit. The Driver's own payload is installed from the `livespec-driver-codex` marketplace, which is not Codex-curated, so "The Driver's own payload remains a covered plugin" still holds.
- `SPECIFICATION/constraints.md` §"Forbidden patterns": every hook-cache entry is scoped to a covered plugin. The entry forbidding alias changes "outside a covered plugin's own `<cache>/<marketplace>/<plugin>/` directory" now also forbids touching Codex-curated plugin directories, which agrees with the new MUST NOT. No change needed; the new prohibition is stated once, in the contract, rather than duplicated.
- `SPECIFICATION/scenarios.md`: the four hook-cache scenarios (the Driver cache update, any covered plugin's cache update, unchanged hooks after a content change, and the not-safely-re-established scenario that reports provisioning failure for a plugin with no identifiable release tag) all speak of covered plugins and remain true under the new definition. A dedicated Codex-curated exclusion scenario would add a `## ` heading; it is not needed for consistency, so none is added, and the required test coverage is carried by Amendments 3 and 4 instead.
- `SPECIFICATION/spec.md` and `SPECIFICATION/README.md`: no statement about covered plugins, marketplace entries, or hook trust; no change needed.

No `## ` heading is added, removed, or renamed by this proposal, so `tests/heading-coverage.json` needs no co-edit.
