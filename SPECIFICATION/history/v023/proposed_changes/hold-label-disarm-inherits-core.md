---
topic: hold-label-disarm-inherits-core
author: claude-opus-5-5
created_at: 2026-11-10T22:58:30Z
---

## Proposal: This repository carries the hold-label disarm workflow livespec core makes inherited fleet policy

### Target specification files

- SPECIFICATION/non-functional-requirements.md

### Summary

Add one bullet to `## Inherited from livespec` in `non-functional-requirements.md` binding this repository, which carries `auto-enable-merge.yml`, to also carry `disarm-on-hold-label.yml`, citing livespec core for the behaviour rather than restating it.

### Motivation

livespec core's proposal `hold-label-disarm-inherited-policy` (merged as livespec#3162, 16503c72) makes the `auto-enable-merge.yml` / `disarm-on-hold-label.yml` pair inherited fleet policy in livespec `non-functional-requirements.md` §"Shared content sync — copier template", and says a non-template member carries its own copy and cites that section rather than restating it. This repository runs `auto-enable-merge.yml`, so a `do-not-merge` label added after the factory bot armed a pull request leaves auto-merge on, the gap measured on livespec-dev-tooling#4019, #4031 and #4033. No clause in this specification governs auto-merge or hold labels today, which is why the carrier work item livespec-driver-codex-qydez4 has no honest References line. This bullet gives it one.

### Proposed Changes

In `SPECIFICATION/non-functional-requirements.md`, append this bullet to the list under `## Inherited from livespec`:

- Hold-label disarm: because this repository carries `.github/workflows/auto-enable-merge.yml`, it MUST also carry `.github/workflows/disarm-on-hold-label.yml`, byte-identical to livespec's root copy, which turns a pull request's auto-merge off when the `do-not-merge` label is added to it. The behaviour, and the rule that every fleet member carrying `auto-enable-merge.yml` carries it, are livespec's `non-functional-requirements.md` §"Shared content sync — copier template" and are not restated here.

The same revise MUST add `§"Shared content sync — copier template"` to the `livespec` entry of `.livespec.jsonc`'s `external_references` allowlist, in the bare heading form that file requires.

Ordering: this proposal cites a section whose disarm bullet arrives with livespec's own revise of `hold-label-disarm-inherited-policy`. Revise it after that livespec revise has merged, so the cited behaviour exists when this clause ratifies.
