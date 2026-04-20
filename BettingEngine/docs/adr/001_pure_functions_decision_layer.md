# ADR-001: Decision layer is pure functions with no DB access

**Status:** accepted
**Date:** 2026-03-30

## Decision

`decision/ev.py`, `decision/kelly.py`, `decision/veto.py`, and `decision/signals.py`
are pure functions. They receive all data as arguments and never call the database.
`generate_signals()` was explicitly redesigned from its original stub signature of
`(conn, model_run_id, bankroll, config)` to `(prices, snapshots, match, run_validation,
bankroll, config, ...)`.

## Reason

Putting DB access inside the decision layer would create a circular dependency:
the pricing engine feeds the decision layer, and the audit layer reads from both.
A DB call inside `generate_signals` would couple signal generation to connection
state, make the functions untestable in isolation, and force every test to stand up
a real or mocked database. Pure functions are trivially testable with plain dicts.

## Consequences

- All data must be fetched before calling any decision function. The caller
  (`run_pricing`) owns data loading.
- `model_run_id` is `None` in all signals until the caller persists the run and
  backfills it. This is intentional.
- Adding any DB call to the decision layer violates this ADR and requires an
  explicit decision to supersede it.
