# ADR-005: run_pricing() does not write to the database

**Status:** accepted
**Date:** 2026-03-30

## Decision

`run_pricing()` returns a result dict and performs no database writes.
The caller — currently the not-yet-implemented `run.py` — is responsible for
persisting the model run, adjustments, signals, and bankroll state by calling
the audit layer after receiving the result.

## Reason

Mixing computation and persistence in one function creates partial-write failure
modes: if the run completes but signal logging fails mid-loop, the database
contains a model run with missing signals, and there is no clean way to recover.
Separating the two means the computation is always complete before any write
begins. It also keeps `run_pricing()` testable without a writable database —
an in-memory SQLite with read-only fixtures is sufficient to exercise the full
pricing pipeline.

## Consequences

- `model_run_id` is `None` in all signal dicts returned by `run_pricing()`.
  The caller sets it on each signal after calling `log_model_run()`.
- The caller is responsible for the write transaction. If it crashes between
  `log_model_run()` and `log_signal()`, the run exists in the DB without signals.
  This is a known and accepted risk for V1 — the run can be re-executed cleanly.
- Any DB write added directly to `run_pricing()` violates this ADR and requires
  an explicit decision to supersede it.
