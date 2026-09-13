# Configuration and migration history

`pairwise_matrix_registry.json` preserves the original human method records byte-for-byte at migration. The active optional review command now reads/writes this location. Older approvals lack the current context/method binding and cannot silently authorize a new method. Updating a record retains its prior version in `_history`.

`dataset_migration_history.json` preserves superseded mapping annotations and an existing source retrieval timestamp. It is an input to the reproducible integrity migration, not model input or operating-control evidence. The prior lineage-based links are historical claims, not current coverage conclusions.

Baseline facts live in `calibrated_v0_2/`; future case state and answer patches belong in `runs/`. Neither a human method record nor a migration note is included in the runtime dataset manifest.
