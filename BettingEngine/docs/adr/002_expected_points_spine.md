# ADR-002: All markets derived from a shared expected-points spine

**Status:** accepted
**Date:** 2026-03-30

## Decision

H2H odds, handicap line, and total line are all derived from the same
`(final_home_points, final_away_points)` pair via a single call to
`derive_final_prices()`. No market is priced independently.

## Reason

Pricing markets separately produces internal inconsistencies: a model could
simultaneously show the home team as a heavy H2H favourite while offering an
away-friendly handicap line. Using a shared spine guarantees that if expected
home points rise, home H2H shortens, the home handicap improves, and the total
increases — all in proportion. This is how professional pricing operations work.
It also means all three markets can be audited against the same underlying number.

## Consequences

- You cannot adjust the total without also affecting implied H2H probability.
  This is intentional, not a limitation.
- Tier adjustments must be expressed as `home_points_delta` / `away_points_delta`.
  A tier cannot adjust odds or margins directly (see ADR-004).
- `derive_final_prices()` is the single source of truth for all market prices.
  It must not be called more than once per run.
