# Architecture Decision Records

Decisions that are load-bearing, non-obvious, or likely to be revisited.
Each record fits on one screen. New ADRs go at the bottom with the next number.

- [ADR-001](001_pure_functions_decision_layer.md) — Decision layer is pure functions with no DB access
- [ADR-002](002_expected_points_spine.md) — All markets derived from a shared expected-points spine
- [ADR-003](003_snapshots_append_only.md) — Market snapshots are append-only
- [ADR-004](004_point_based_deltas.md) — Tier adjustments are point-based deltas, not probability tweaks
- [ADR-005](005_run_pricing_no_db_writes.md) — run_pricing() does not write to the database
