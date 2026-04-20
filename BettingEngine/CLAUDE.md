
## `CLAUDE.md`

```md
# Project Overview

This repository is a sports pricing engine starting with **NRL pre-match markets**.

Version 1 focuses on:
- H2H pricing
- handicap pricing
- total points pricing
- bookmaker comparison vs Bet365 and Pinnacle
- EV calculation
- Kelly-based stake suggestions
- terminal output
- spreadsheet export
- logging every model run, signal, and actual bet

This is **not** an autonomous betting agent in V1.
It is decision-support software with human approval.

---

# Product Goal

The goal is to price each NRL round properly, compare our model against bookmaker markets, and identify potentially positive expected value opportunities in a disciplined, auditable way.

The system should help the user think like a professional betting operation:
- build a baseline number
- apply structured adjustments
- compare to market
- calculate EV
- size conservatively
- log everything

---

# Version 1 Scope

## Included
- NRL only
- pre-match only
- H2H
- handicap
- total points
- Bet365 and Pinnacle market comparison
- rules-based and statistical pricing
- quarter Kelly with hard cap
- terminal and spreadsheet output
- logging and auditability

## Excluded
- live betting
- auto-betting
- dashboard/web app
- public SaaS features
- multi-sport support
- black-box machine learning as the primary pricing engine
- autonomous agent actions

---

# Core Engineering Philosophy

## 1. Correctness over cleverness
Prefer transparent, reliable logic over fancy abstractions.

## 2. Explainability over opacity
Every important number must be reproducible and auditable.

## 3. Small modules, clean boundaries
Even if implementation starts monolithic, internal responsibilities should remain separated.

## 4. Preserve all important data
Do not overwrite market snapshots or model outputs.
Store history append-only where possible.

## 5. Human stays in control
Version 1 only recommends and logs.
It does not make autonomous betting decisions.

---

# Pricing Philosophy

The pricing engine uses a **7-tier model**.

## Tier 1
Baseline bookmaker-style pricing:
- ELO
- team strength
- points for/against
- attack/defence
- home advantage
- recent form

Tier 1 creates the baseline expected score and derived market prices.

## Tier 2
Stylistic matchup layer:
- team style interaction
- coach style interaction
- team-vs-team EV history
- coach head-to-head

## Tier 3
Momentum / situational layer:
- bye
- short turnaround
- long turnaround
- off big win
- off big loss
- bounce-back / flat-spot angles

## Tier 4
Venue layer:
- fortress venues
- home/away strength
- venue scoring tendencies
- travel effects

## Tier 5
Injury layer:
- key player outs
- spine disruption
- pack changes
- replacement quality

## Tier 6
Referee layer:
- penalty tendency
- set restart tendency
- game control style
- scoring environment under ref

## Tier 7
Environmental layer:
- weather
- lunar phase research factors

### Moon phase sub-layer
Track games within +/-1 day of:
- full moon
- new moon

Research ideas to support in config/logging:
- full moon may support stronger home crowd/home performance and higher scores
- new moon may support away underdogs and lower scores

Important:
- moon factors are experimental
- moon factors must be bounded
- moon factors must be configurable
- moon factors must be logged separately
- moon factors must never dominate the model in V1

---

# Pricing Mechanics

Use expected points as the central spine.

The model should:
1. estimate baseline home points and away points
2. derive baseline margin and total
3. apply Tier 2–7 adjustments to expected points / margin / total
4. derive final margin and total
5. derive final H2H probabilities and fair odds
6. compare against bookmaker prices

This is preferred over direct probability tweaking because it keeps:
- H2H
- handicap
- totals

coherent with one another.

---

# Decision Rules

## EV formula
Use decimal odds.

`model_probability = 1 / model_odds`

`EV = (model_probability * market_odds) - 1`

## Recommendation eligibility
A signal is only eligible if:
- EV >= 20%
- no hard veto
- data quality acceptable
- odds snapshot current

## Kelly
Use standard decimal Kelly, then apply quarter Kelly in Year 1.

Also apply:
- minimum actionable stake threshold
- hard stake cap

Do not assume full Kelly.

## Confidence
Confidence is separate from EV.
A signal can have:
- high EV, low confidence
- moderate EV, high confidence

---

# Logging Requirements

Every model run must preserve:
- match id
- model version
- baseline home points
- baseline away points
- baseline margin
- baseline total
- each tier adjustment
- final home points
- final away points
- final margin
- final total
- fair H2H odds
- fair handicap line
- fair total line

Every signal must preserve:
- bookmaker
- market type
- selection
- market odds
- model odds
- model probability
- EV
- Kelly outputs
- confidence
- veto flags
- signal label
- timestamp

Every actual bet must be stored separately from the recommendation.

---

# Database Philosophy

The system should use a relational schema.

Key rules:
- one canonical `match_id`
- market snapshots are append-only
- every model run has a `model_version`
- every signal links to a model run
- every actual bet links to a signal

Important tables include:
- teams
- venues
- referees
- matches
- bookmakers
- market_snapshots
- results
- team_stats
- match_context
- model_runs
- model_adjustments
- signals
- bets
- bankroll_log

---

# Coding Preferences

## Language
- Python first

## Style
- keep functions small
- use explicit names
- avoid magic numbers
- prefer config files for thresholds and toggles
- write code that is easy to inspect and test
- avoid unnecessary frameworks early

## Testing
Prioritize tests for:
- EV calculation
- Kelly calculation
- pricing math
- data normalization
- snapshot handling
- adjustment logging

## Config
Thresholds and toggles should live in config where reasonable:
- bookmaker priorities
- EV thresholds
- Kelly fraction
- stake caps
- moon factor enable/disable
- weather thresholds
- veto thresholds

---

# Important Product Context

The long-term vision includes:
- AFL
- EPL
- horse racing
- live betting models
- exchange integrations
- internal syndicate tooling
- subscription software
- possible future AI workflow layers

But do not build for all of that immediately.

Current instruction:
**Build a robust NRL pre-match pricing engine first.**

---

# What Claude should optimize for

When making implementation choices, prefer:
1. clean data flow
2. traceable calculations
3. auditable logs
4. simple architecture
5. future extensibility without premature overengineering

---

# What Claude should avoid

Do not:
- introduce black-box ML as the core engine in V1
- hide pricing logic in overly abstract code
- overwrite historical snapshots
- mix research experiments carelessly into stable production logic
- make moon factors dominant
- assume automation authority that the system does not yet have

---

# Immediate Build Priorities

Prioritize implementation in this order:

1. project skeleton
2. schema
3. spreadsheet importers
4. fixture/results ingestion
5. bookmaker market snapshot ingestion
6. normalization and validation
7. Tier 1 baseline pricing
8. Tier 2–7 adjustment scaffolding
9. EV and Kelly logic
10. terminal + spreadsheet reporting
11. logging and bankroll tracking

---

# Final instruction

This repository is building a serious betting pricing engine, not a toy script.

Implementation should reflect:
- discipline
- transparency
- modular thinking
- auditability
- professional workflow