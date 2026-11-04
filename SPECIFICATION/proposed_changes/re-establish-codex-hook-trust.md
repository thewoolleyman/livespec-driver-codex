---
topic: re-establish-codex-hook-trust
author: claude:codex-plugin-hook-path-regression
created_at: 2026-11-04T01:02:22Z
---

## Proposal: Concurrent-write integrity of the host's Codex configuration

### Target specification files

- SPECIFICATION/contracts.md

### Summary

Require every Driver write of Codex trust state into the host's Codex configuration file to be serialized against other Driver writers, atomically replaced, and computed from a fresh read taken while serialized, and to fail loudly rather than write when that cannot be done.

### Motivation

The trust-continuity contract (v015, codex-hook-trust-continuity) lets the Driver re-establish Codex hook trust by writing Codex's trust records, but says nothing about how that shared file is written. Review of the implementation (livespec-driver-codex draft PR #967, work-item livespec-driver-codex-b5rhjf, regroomed from v52m6a) found a blocking defect: the observer and ensure-codex-plugins both read, modify and write ~/.codex/config.toml, which Codex itself also writes, with no serialization and no atomic replacement. Two concurrent reconciles can overwrite each other's trust records, losing trust and so turning a PreToolUse guard off (an untrusted guard fails open), and an interrupted write can truncate the operator's whole Codex configuration. The item's rework note requires the fix, but the Dispatcher's spec-change-tier check (2026-11-04T00:05Z) held b5rhjf because ## Hook bundle does not state it, naming topic re-establish-codex-hook-trust. This proposal states the externally visible invariants (serialized writers, atomic replacement, fresh read under serialization, loud refusal otherwise) and leaves the mechanism (for example an advisory lock on a sibling file plus a same-directory temporary file and rename) to the implementation, consistent with the mechanism-neutral framing of the surrounding paragraph.

### Proposed Changes

Insert one paragraph into SPECIFICATION/contracts.md section ## Hook bundle, immediately after the paragraph that ends 'Trust that an operator grants through Codex's own review interface is not governed by this contract.' and before the paragraph beginning '`ensure-codex-plugins` and the observer's health report MUST report'. No heading is added, removed or renamed, so tests/heading-coverage.json needs no change.

```diff
--- a/SPECIFICATION/contracts.md
+++ b/SPECIFICATION/contracts.md
@@ -458,6 +458,25 @@
 failure naming the plugin. Trust that an operator grants through Codex's
 own review interface is not governed by this contract.
 
+Writing the host's Codex configuration. Codex records hook trust in the
+host's Codex configuration file, which Codex itself also writes and which
+more than one Driver process (the reconciler run by `ensure-codex-plugins`
+and the one run by the observer) may write at the same time. Every write of
+trust state into that file by the reconciler, the observer, or
+`ensure-codex-plugins` MUST preserve the file's integrity:
+(a) the Driver's writers MUST be serialized with one another, so that two
+concurrent reconciles can never each read the file and then overwrite the
+trust records the other wrote; (b) each write MUST replace the file
+atomically, so that an interrupted write leaves either the complete prior
+file or the complete new file, never a truncated or partially written one;
+and (c) each write MUST be computed from the file's contents as read while
+serialized, immediately before the replacement, so that it carries forward
+every setting it does not intend to change, including an edit Codex made
+after the writer's own earlier read. A writer that cannot meet these
+conditions within a bounded wait MUST NOT write trust state and MUST report
+the failure loudly, as a provisioning or observer failure naming the
+plugin, exactly as an unrecognized trust-record format is reported.
+
 `ensure-codex-plugins` and the observer's health report MUST report a
 covered plugin whose hooks are installed but not trusted by Codex
 loudly, as a failure, naming the plugin and each untrusted hook, and
```
