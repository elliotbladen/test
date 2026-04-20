# Sports Model

A professional sports pricing engine starting with **NRL pre-match markets**.

Version 1 focuses on:

- pricing **H2H**
- pricing **handicap**
- pricing **total points**
- comparing model prices against **Bet365** and **Pinnacle**
- calculating **EV**
- suggesting **Kelly-based stake sizing**
- outputting to **terminal** and **spreadsheet**
- logging every model run, signal, and actual bet decision

This is **not** an autonomous betting agent in V1.  
It is a disciplined, explainable, auditable **pricing and decision-support engine**.

---

## Long-Term Vision

This project is the first step toward a much larger sports modeling platform.

Long-term possibilities include:

- AFL pricing
- EPL pricing
- horse racing win/place pricing
- live betting models
- exchange integration
- internal syndicate tooling
- subscription software
- bettor evaluation / prop-style systems
- future AI-assisted workflow layers

The long-term inspiration is professional-grade betting infrastructure.

But Version 1 is intentionally narrow:

**NRL only. Pre-match only. One sport done properly first.**

---

## Version 1 Scope

### Included
- NRL only
- pre-match only
- H2H markets
- handicap markets
- total points markets
- comparison vs Bet365 and Pinnacle
- rules-based and statistical pricing
- EV calculations
- quarter-Kelly stake sizing
- terminal output
- spreadsheet export
- logging and audit trail
- human approval before any actual bet

### Excluded
- live betting
- auto-betting
- dashboard/web app
- public subscription access
- autonomous agent actions
- black-box machine learning as the main pricing engine
- multi-sport support in V1

---

## Core Philosophy

### 1. Explainability first
Every model output must be traceable.

The system must preserve:
- baseline numbers
- each tier adjustment
- final numbers
- bookmaker comparison
- EV
- Kelly stake logic
- final recommendation

### 2. Tiered pricing, not one-shot guessing
The model uses a **7-tier framework**:

1. baseline bookmaker-style pricing  
2. stylistic matchup layer  
3. momentum / situational layer  
4. venue layer  
5. injury layer  
6. referee layer  
7. environmental layer (weather + lunar phase research factors)

### 3. Tier 1 creates the number
Tier 1 builds the base expected score.

Tiers 2–7 apply bounded, logged adjustments.

### 4. Human in control
Version 1 only recommends and logs.
It does not place bets automatically.

### 5. Data discipline matters
Bad data kills betting models faster than bad math.

---

## Pricing Overview

The model should estimate:

- expected home points
- expected away points
- expected margin
- expected total

Then derive:

- fair H2H odds
- fair handicap line
- fair total line

Then compare against bookmaker markets.

This keeps H2H, handicap, and totals connected to the same mathematical spine.

---

## EV and Staking

### EV formula
For decimal odds:

`EV = (model_probability * market_odds) - 1`

Where:

`model_probability = 1 / model_odds`

### Trigger
Version 1 recommendation eligibility requires:

- EV >= 20%
- acceptable data quality
- no hard veto
- current market snapshot

### Kelly
Version 1 uses:

- **quarter Kelly**
- with a hard cap

This is a compounding system, but with conservative protection in Year 1.

---

## Moon Phase Logic

Moon phase is included inside Tier 7 as an **experimental research factor**.

The model can track:

- **full moon +/-1 day**
  - possible higher scores
  - possible stronger home crowd/home performance

- **new moon +/-1 day**
  - possible lower scores
  - possible stronger away underdog performance

These are not treated as proven truths by default.
They are:

- configurable
- bounded
- logged separately
- reviewable over time

Moon factors must never be allowed to dominate the model on their own in V1.

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