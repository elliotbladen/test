# Tier 2 Yardage Specification - V1

## Purpose

This document defines the first Tier 2 matchup bucket for the NRL pricing engine:

**Yardage / territory / ruck-momentum**

Tier 2 does not replace Tier 1.
Tier 2 refines Tier 1 by asking:

**Which team is more likely to win the field-position and momentum battle in this specific matchup?**

This bucket should be:
- data-driven
- bounded
- auditable
- configurable
- meaningful, but not dominant

---

## Tier 2 Role

Tier 1 answers:
- who is the better team?
- who is in better form?
- what should the game look like at a base level?

Tier 2 answers:
- how do these two teams interact?
- which team’s style is likely to pressure the other?
- where does the matchup itself create an edge?

The first Tier 2 bucket focuses on:
- field position
- yardage
- ruck momentum
- territorial pressure

---

## Tier 2 Priority Order

The approved Tier 2 build order is:

1. **Yardage / territory / ruck-momentum**
2. Defensive system / discipline
3. Attacking shape / scoring-actions
4. Coach H2H overlay
5. Team-vs-team history overlay

This document only covers the first bucket.

---

## Core Question

The yardage bucket should answer:

**Which team is more likely to win the territory battle and impose its preferred momentum profile?**

This includes:
- who gets on the front foot
- who starts sets better
- who exits cleaner
- who wins the long-field battle
- who creates quicker play-the-ball or better ruck moments
- who forces the opponent into poor field position

---

## Data Philosophy

This bucket should be **mostly data-driven**.

It should not rely primarily on:
- gut feel
- narrative
- “they look tougher”
- manual physicality opinions

It should be built from measurable signals.

---

## Core Signals

The yardage bucket should start with these signals:

### 1. Run metres / metres after contact
Purpose:
Measure basic carry dominance and post-contact strength.

Why it matters:
- builds field position
- bends defensive lines
- creates momentum
- improves kick launch points
- wears teams down over time

This is the strongest signal in the bucket.

---

### 2. Completion / errors / discipline
Purpose:
Measure how well a team preserves field position and avoids self-sabotage.

Why it matters:
- poor completion wastes yardage
- errors hand over field position
- poor discipline gives away territory cheaply
- good teams preserve pressure

This should be a major signal.

---

### 3. Kick metres / kicking control
Purpose:
Measure territorial control through kicking.

Why it matters:
- long kicking flips field
- controlled kicking protects weak exits
- good kicking supports territorial dominance
- poor kicking hands away field position

This should be a meaningful but secondary signal.

---

### 4. Ruck-speed / play-the-ball momentum proxies
Purpose:
Measure how often a team creates faster momentum and shape opportunities.

Why it matters:
- faster ruck moments can generate line breaks
- more momentum can improve shape and field position
- strong ruck control can stress defensive reloads

This should be included as a smaller overlay because public data may be less stable or less direct.

---

## Initial Signal Weighting Philosophy

The initial weighting philosophy should be:

1. **Run metres / metres after contact** — biggest weight
2. **Completion / errors / discipline** — second
3. **Kick metres / kicking control** — third
4. **Ruck-speed / play-the-ball proxies** — fourth, smaller

This is the approved Tier 2 starting philosophy.
Weights should remain configurable later.

---

## What the Bucket Should Do

If Team A has the yardage/territory edge, this bucket should:

- **raise Team A expected points**
- **lower Team B expected points**

So the yardage bucket should affect both sides of the score.

### Why
Better yardage does not just help your own attack.
It also:
- worsens the opponent’s set starts
- reduces their clean-ball opportunities
- makes them work off poor field position
- creates fatigue and defensive pressure

---

## Market Impact

The yardage bucket should affect all three markets:

- H2H
- handicap
- totals

But the strongest impact should be:

1. **H2H**
2. **handicap**
3. **totals**

Totals should still move, but less than match winner / line effects.

---

## Strength of Effect

This bucket is approved as a:

**small-to-moderate overlay**

Meaning:
- it should matter
- it should move the number meaningfully when the edge is clear
- it should not casually dominate Tier 1

Tier 1 remains the base truth.
Tier 2 refines that truth.

---

## Cap Philosophy

The yardage bucket must have:

- a **hard cap**
- the cap must be **adjustable later**

This is mandatory.

Reason:
- prevents noisy data from creating oversized moves
- keeps Tier 2 disciplined
- makes tuning safer later

---

## Adjustment Style

The yardage bucket should produce an adjustment that is:

- logged separately
- capped
- decomposable by signal
- visible in the audit trail

### Example structure
For each match, the bucket should output:

- yardage_bucket_score
- run_metres_component
- completion_component
- kicking_component
- ruck_component
- capped_yardage_adjustment_home_points
- capped_yardage_adjustment_away_points

This is the minimum audit structure.

---

## Directional Logic

### If Team A has the yardage edge:
- home points go up if Team A is home
- away points go down if Team B is away

### If Team B has the yardage edge:
- away points go up
- home points go down

The adjustment should be symmetric and zero-sum in spirit, but it does not need to be perfectly mathematically symmetric if later tuning suggests otherwise.

---

## What Does NOT Belong in This Bucket

This bucket should not include:

- coach H2H
- team-vs-team history
- referee effects
- weather
- moon phase
- injuries
- bye/turnaround
- emotional/narrative spots
- edge-attack shape
- defensive-system patterning

Those belong in other Tier 2 buckets or later tiers.

---

## Data Source Plan

### First-wave practical sources
Use realistic and accessible sources first:

- official/public NRL team stats
- Fox Sports Lab-style team stats
- historical spreadsheets
- Rugby League Project for history/backbone data

### Premium upgrade later
Long-term, this bucket can be improved with:
- Stats Perform / Opta-grade data
- better ruck-speed and territorial datasets
- better possession / field-position event feeds

The architecture should support better data later without changing the bucket’s conceptual role.

---

## Initial Configurable Knobs

The architecture should expect these knobs to exist later:

- yardage_bucket_enabled
- yardage_bucket_max_points_swing
- yardage_run_metres_weight
- yardage_completion_weight
- yardage_kick_weight
- yardage_ruck_weight
- yardage_signal_normalisation_method
- yardage_min_sample_size
- yardage_confidence_threshold

These do not all need full numeric tuning in V1,
but the code structure should anticipate them.

---

## Design Principles

This bucket should be:

### 1. Measurable
Use data we can actually source.

### 2. Bounded
No runaway style adjustments.

### 3. Transparent
We should always be able to see why it moved the number.

### 4. Tuneable
Weights and cap must be easy to adjust later.

### 5. Layered
It should sit on top of Tier 1, not replace it.

---

## Implementation Guidance for Claude

Claude is allowed to build:
- scaffolding
- data structures
- signal computation stubs
- config keys
- bucket-level adjustment plumbing
- audit logging structure

Claude is not allowed yet to:
- implement the other Tier 2 buckets
- implement coach H2H overlay
- implement team-vs-team history overlay
- implement EV/Kelly
- implement scraping/live features
- invent strong weights without approval

The purpose of the next implementation step is to build the **Tier 2 yardage structure**, not to finalize full calibration.

---

## Summary

The Tier 2 yardage bucket is the first matchup overlay.

It believes:
- field position matters
- yardage matters
- ball security and kicking matter
- ruck momentum matters
- these effects are measurable
- these effects should move the number, but only within controlled bounds

This is the first Tier 2 layer because it is the most foundational matchup bucket in NRL.