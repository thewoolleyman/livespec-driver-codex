# SPECIFICATION/history

Each `livespec:revise` pass snapshots the accepted spec state into a new
`vNNN/` directory here, giving the spec an append-only revision history.
`livespec:prune-history` collapses old snapshots into a pruned-marker
once they are no longer needed.

The initial seed snapshot is recorded under `v001/`.
