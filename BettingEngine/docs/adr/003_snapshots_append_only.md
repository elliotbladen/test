# ADR-003: Market snapshots are append-only

**Status:** accepted
**Date:** 2026-03-30

## Decision

The `market_snapshots` table is never updated or deduplicated. Every captured price
is a new row. `get_latest_snapshots_for_match()` uses a `MAX(captured_at)` subquery
to surface the most recent price per `(bookmaker, market_type, selection_name)`.
There is no upsert logic on this table.

## Reason

Price history has permanent audit value. Closing Line Value (CLV) analysis —
comparing the price taken against the closing price — requires the full price
movement history to be intact. An upsert that overwrites the opening price with
the closing price destroys this. Append-only also makes ingestion idempotent in
one direction: re-importing the same snapshot just adds a duplicate row, which
the `MAX(captured_at)` query handles safely.

## Consequences

- The table grows continuously. This is expected and acceptable for V1 volumes.
- Callers must always go through `get_latest_snapshots_for_match()` to get current
  prices — never query `market_snapshots` directly for the "current" price.
- Any code that attempts an UPDATE or upsert on `market_snapshots` is a bug.
- Duplicate snapshots (same bookmaker/market/odds captured twice) are harmless
  but produce redundant rows. A deduplication view can be added later if needed.
