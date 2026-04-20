# Decision Rules Specification - V1

## Purpose

This document defines how the V1 model turns pricing outputs into betting recommendations.

The decision engine does not create prices.
It interprets prices relative to bookmaker markets.

---

## Core Principle

A bet signal exists only when:
- the model has priced the event
- the available market price is better than the model's fair price
- EV is above threshold
- no veto rule blocks the signal
- data quality is acceptable

---

## Definitions

### Market odds
The currently available bookmaker odds.

### Model odds
The fair odds produced by the pricing engine.

### Model probability
`1 / model_odds`

### EV
Expected value for a $1 stake.

### Confidence
A separate trust score for the signal.
Confidence is not the same as EV.

### Veto
A blocking rule that prevents a recommendation even if EV appears positive.

---

## EV Formula

### Official formula
`EV = (model_probability * market_odds) - 1`

### EV percent
`EV_percent = EV * 100`

### Example
- model odds = 2.40
- market odds = 3.00
- model probability = 1 / 2.40 = 0.4167

EV:
`(0.4167 * 3.00) - 1 = 0.25`

This equals:
`+25% EV`

---

## Recommendation Thresholds

### V1 default thresholds
- **EV < 0%** -> No Bet
- **0% to 9.99%** -> Pass
- **10% to 19.99%** -> Watchlist
- **20% to 29.99%** -> Recommend Small
- **30% to 49.99%** -> Recommend Medium
- **50%+** -> Recommend Strong + Manual Review Flag

### Important rule
A signal must not be recommended just because EV is large.
Large EV may indicate:
- true edge
- stale market
- broken input
- model error

---

## Kelly Staking Logic

## Raw Kelly formula
For decimal odds:

`raw_kelly = ((market_odds - 1) * model_probability - (1 - model_probability)) / (market_odds - 1)`

If raw Kelly is negative:
- stake = 0

---

## V1 Kelly policy

### Year 1 policy
- use **quarter Kelly**
- retain hard cap
- preserve human approval

### Formula
`applied_kelly = raw_kelly * 0.25`

---

## Stake Caps

### V1 proposed rules
- minimum actionable stake: **0.25% bankroll**
- soft review threshold: **1.50% bankroll**
- hard cap: **2.00% bankroll**

### Interpretation
- below 0.25% -> probably too small to matter, usually pass/watch
- 0.25% to 1.50% -> normal actionable stake
- 1.50% to 2.00% -> stronger signal, still reviewed
- above 2.00% -> truncate to cap

---

## Signal Labels

Signals should be stored with one of these labels:

- `no_bet`
- `pass`
- `watch`
- `recommend_small`
- `recommend_medium`
- `recommend_strong`

---

## Confidence Framework

Confidence is separate from EV.

A signal can be:
- high EV, low confidence
- lower EV, high confidence

### V1 confidence inputs
Suggested inputs:
- data completeness
- model stability
- number of adjustment layers triggered
- injury certainty
- bookmaker price freshness
- whether signal is supported by both Bet365 and Pinnacle comparison
- whether edge survives after conservative checks

### Suggested confidence labels
- low
- medium
- high

---

## Veto Rules

A veto blocks or downgrades a signal.

## Hard vetoes
These should normally prevent recommendation:

- missing critical market data
- missing key team/injury data
- stale odds snapshot
- invalid line/odds format
- model run failed integrity checks
- extreme EV anomaly likely caused by bad data
- match status not confirmed as scheduled

## Soft vetoes
These should downgrade or flag the signal:

- late injury uncertainty
- uncertain referee assignment
- severe weather uncertainty
- excessive dependence on experimental adjustment layer
- weak confidence
- only one bookmaker source available
- line movement too volatile or unresolved

---

## Price Freshness Rules

Signals should use current market snapshots.

### V1 rule
A signal should only be generated if:
- odds snapshot is recent enough
- the timestamp is preserved
- bookmaker source is known

Exact freshness thresholds can be set in config.

---

## Multi-Bookmaker Logic

Version 1 uses:
- Bet365
- Pinnacle

### Philosophy
- Bet365 may price early
- Pinnacle is treated as the sharper benchmark
- both should be stored independently
- signals can be generated against either bookmaker
- later logic may prioritize Pinnacle as the sharper market reference

### Suggested V1 behavior
Store and display:
- Bet365 line and odds
- Pinnacle line and odds
- model line and odds

Allow recommendation generation on each separately.

---

## Required Signal Output Fields

Every signal should include:

- match
- market type
- selection
- bookmaker
- market odds
- model odds
- model probability
- EV
- raw Kelly
- applied Kelly
- capped stake fraction
- recommended stake amount
- confidence
- signal label
- veto flag
- veto reason if any
- timestamp
- model version

---

## Human Decision Support

Version 1 is alert-only.

That means:
- model generates recommendation
- human decides whether to place bet
- actual bet is logged separately from recommendation

The system must distinguish between:
- signal generated
- bet placed
- result settled

---

## Settlement and Review Logic

After each match settles, the system should record:

- final score
- market chosen
- stake placed
- odds taken
- result
- PnL
- bankroll update
- closing odds if available
- CLV if available later

This supports future review and model improvement.

---

## Moon Factor Governance

Because moon phase is included as an experimental research factor inside Tier 7, decision logic must treat it carefully.

### Rules
- moon factor cannot by itself justify a recommendation
- moon factor should remain small in V1
- any signal meaningfully influenced by moon factor should be logged clearly
- moon-driven contribution should be reviewable in post-round analysis

This keeps the model disciplined.

---

## Decision Engine Sequence

1. read final model outputs
2. read bookmaker market snapshots
3. compute model probability
4. compute EV
5. compute raw Kelly
6. apply quarter Kelly
7. apply stake caps
8. compute confidence
9. apply veto rules
10. assign signal label
11. log signal
12. display recommendation

---

## Versioning Rule

Every signal must be tied to:
- a specific model version
- a specific model run
- a specific bookmaker snapshot

This is mandatory for accountability.

---

## Future Extensions

Later versions may add:
- dynamic EV thresholds
- bankroll state-aware stake scaling
- CLV-based recommendation filtering
- exchange/liquidity checks
- live market monitoring
- auto-betting with approval rules

Version 1 remains:
- pre-match
- alert-only
- explainable
- auditable