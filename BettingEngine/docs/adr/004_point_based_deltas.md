# ADR-004: Tier adjustments are point-based deltas, not probability tweaks

**Status:** accepted
**Date:** 2026-03-30

## Decision

Every tier function returns a list of adjustment dicts containing
`home_points_delta` and `away_points_delta`. Tiers never adjust win probability,
fair odds, or market lines directly. The engine accumulates all deltas onto the
Tier 1 baseline and calls `derive_final_prices()` once at the end.

## Reason

Point-based deltas are auditable in a way that probability tweaks are not.
A delta of `home_points_delta = +1.5` from the yardage bucket is self-explanatory;
a probability nudge of `+0.03` is not. Deltas also compose additively, which makes
it easy to verify that the sum of all tier adjustments produces the expected final
score. If tiers adjusted probability directly, small rounding differences would
accumulate in ways that are hard to trace. The point-based approach also keeps all
three markets consistent with each other automatically (via ADR-002).

## Consequences

- Each tier adjustment is one row in `model_adjustments` with explicit
  `home_points_delta`, `away_points_delta`, `margin_delta`, and `total_delta`.
  The full adjustment chain is always auditable.
- `margin_delta` and `total_delta` are always derived values:
  `margin_delta = home_delta - away_delta`, `total_delta = home_delta + away_delta`.
  They are stored for convenience but must never be set independently.
- A tier that wants to affect only the total (e.g. weather suppresses scoring
  for both teams equally) sets equal and opposite deltas:
  `home_points_delta = -X`, `away_points_delta = -X`.
- `_debug` fields in adjustment dicts are for in-process audit only and are
  not written to the database.
