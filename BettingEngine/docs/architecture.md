# Sports Model Architecture - V1

## Project Purpose

Version 1 is a pre-match NRL pricing engine that:

- prices H2H
- prices handicap
- prices total points
- compares model outputs against bookmaker markets
- calculates EV
- suggests Kelly-based stake sizes
- outputs to terminal and spreadsheet
- logs all model decisions and betting actions

This is not an autonomous betting agent in V1.
It is an explainable, auditable pricing and decision-support engine.

---

## High-Level Architecture

```text
[External Sources]
  - Bet365
  - Pinnacle
  - Results websites
  - Team stats websites
  - Injury/team list websites
  - Weather source
  - Referee source
  - Historical spreadsheets
        |
        v
[Ingestion Layer]
        |
        v
[Validation / Normalization Layer]
        |
        v
[Database / Storage Layer]
        |
        v
[Feature Engineering Layer]
        |
        v
[Pricing Engine]
  - Tier 1 baseline
  - Tier 2-7 adjustments
        |
        v
[Decision Engine]
  - EV
  - confidence
  - veto rules
  - Kelly sizing
        |
        v
[Outputs]
  - terminal report
  - spreadsheet export
  - signal log
  - bankroll log