
## `docs/pricing_logic.md`

```md
# Pricing Logic Specification - V1

## Purpose

This document defines how the V1 NRL pricing engine constructs fair prices for:

- H2H
- handicap
- total points

The pricing engine uses a 7-tier structure.

### Core philosophy
- Tier 1 creates the baseline number
- Tiers 2 to 7 adjust the baseline
- final prices are derived only after adjustments are applied
- every adjustment must be bounded, explainable, and logged

---

## Core Pricing Strategy

The system should not directly guess odds from intuition.

Instead it should:

1. estimate expected home points
2. estimate expected away points
3. derive expected margin
4. derive expected total
5. convert those into market prices/lines
6. compare with bookmaker markets

This keeps:
- H2H
- handicap
- totals

connected to the same mathematical spine.

---

## Primary Outputs

For each match, the model should generate:

### H2H
- home win probability
- away win probability
- fair home odds
- fair away odds

### Handicap
- expected margin
- fair handicap line
- probabilities against key market lines if needed

### Totals
- expected total score
- fair total line
- over/under view at market line

---

## Tier Structure

## Tier 1 - Baseline Bookmaker-Style Layer

### Purpose
This is the foundational rating layer.
It should reflect the normal way bookmakers broadly price games before special adjustments.

### Initial inputs
- ELO / power rating
- points for average
- points against average
- attack rating
- defence rating
- home advantage
- recent form
- opponent-adjusted form if available
- baseline league scoring environment

### Outputs
- baseline expected home points
- baseline expected away points
- baseline margin
- baseline total
- baseline H2H odds
- baseline handicap
- baseline total line

### Notes
Tier 1 should carry most of the model’s core intelligence in V1.

---

## Tier 2 - Stylistic Matchup Layer

### Purpose
Capture how teams interact stylistically, beyond raw ratings.

### Example variables
- team style profile
- coach style profile
- pace tendencies
- defensive structure
- attack shape
- team-vs-team EV record
- coach head-to-head
- coach has "the wood" on opponent
- matchup archetype flags

### Example logic
- fast/expansive team vs compressed defensive team
- structured team vs chaotic offload team
- coach historically strong against a certain system

### V1 implementation
- mostly rules-based
- semi-manual where needed
- strongly bounded

---

## Tier 3 - Momentum / Situational Layer

### Purpose
Capture short-term scheduling and situational effects.

### Example variables
- off a bye
- short turnaround
- long turnaround
- off a big win
- off a big loss
- bounce-back spot
- flat-spot risk
- travel sequence fatigue
- consecutive away matches

### Example adjustment types
- add/subtract expected points
- add/subtract margin bias
- add/subtract total scoring environment

### Governance
This layer must be controlled carefully to avoid narrative overfitting.

---

## Tier 4 - Venue Layer

### Purpose
Adjust for place-specific performance.

### Example variables
- home vs away strength
- venue fortress effect
- away weakness
- venue-specific scoring tendencies
- travel burden
- specific opponent at specific venue
- stadium size / field feel if relevant

### Typical effects
- home edge
- away disadvantage
- lower or higher total environment

---

## Tier 5 - Injury Layer

### Purpose
Convert player absences into team-level adjustments.

### Example variables
- fullback out
- halfback out
- five-eighth out
- hooker out
- multiple spine outs
- key pack outs
- replacement quality drop

### V1 implementation
Start role-based rather than player-level market values.

Examples:
- elite playmaker out
- key spine disruption
- pack downgrade
- multiple same-unit absences

### Future direction
- player value tables
- replacement-level models
- late-team-list automation

---

## Tier 6 - Referee Layer

### Purpose
Capture officiating tendencies that affect game flow and scoring.

### Example variables
- referee assigned
- penalty count tendency
- six-again tendency
- sin-bin frequency
- stop-start vs flowing profile
- historical totals under referee
- style interaction with referee type

### Main impact
- strongest on totals
- moderate on handicap
- limited but possible effect on H2H

---

## Tier 7 - Environmental Layer

### Purpose
Capture non-team external conditions affecting scoring or home/away performance.

### Tier 7 contains two sub-layers:
- weather
- lunar phase

This tier should be treated as a **research-driven adjustment layer**, not a blind truth layer.

---

### Tier 7A - Weather

#### Example variables
- rain flag
- rain intensity
- wind speed
- humidity
- temperature
- wet/dry surface
- severe weather category

#### Typical effects
- rain can suppress scoring
- strong wind can affect kicking and totals
- good dry conditions may support higher scoring

#### Main markets affected
- totals first
- handicap second
- H2H only in stronger cases

---

### Tier 7B - Lunar Phase

#### Purpose
Support research-based moon phase hypotheses as configurable factors.

#### Research hypotheses to track
- games played within +/-1 day of a **full moon**
  - possible higher scores
  - possible stronger home crowd/home team effect

- games played within +/-1 day of a **new moon**
  - possible lower scores
  - possible stronger away underdog performance

These are not to be treated as proven facts by default.
They should be implemented as:
- explicit flags
- small bounded adjustments
- fully logged adjustments
- reviewable over time

#### Variables
- moon_phase_category
  - full_moon_window
  - new_moon_window
  - neither

- within_plus_minus_one_day_flag
- full_moon_flag
- new_moon_flag

#### Example adjustment style
- full moon:
  - slight positive to home intensity/home performance
  - slight increase to total scoring environment

- new moon:
  - slight reduction to total scoring environment
  - slight away-underdog support flag

#### Governance
Moon factors must:
- be toggleable in config
- remain small in V1
- always be logged separately
- be reviewable for actual forward performance

---

## Adjustment Framework

## Recommended adjustment method
Use point-based adjustments first.

### Process
1. Tier 1 produces baseline home and away expected points
2. Tiers 2-7 apply deltas to expected points and/or margin/total
3. Final expected points produce:
   - final margin
   - final total
   - final H2H probabilities
   - fair handicap
   - fair total line

This is preferred to direct probability tweaking because it keeps all three markets coherent.

---

## Adjustment Governance Rules

Every adjustment must be:

- named
- logged
- bounded
- configurable
- explainable

### Example logged adjustment
- Tier 3: bye_factor = +1.0 home points
- Tier 5: away_playmaker_out = -2.2 away points
- Tier 7: full_moon_total = +1.3 total points

---

## Suggested V1 Adjustment Strength Philosophy

### Tier 1
Carries the majority of model intelligence.

### Tiers 2-7
Provide bounded overlays.

V1 should remain grounded, so the baseline should dominate unless there is a strong reason otherwise.

---

## Sequence of Pricing

1. compute Tier 1 baseline
2. apply Tier 2 stylistic adjustments
3. apply Tier 3 situational adjustments
4. apply Tier 4 venue adjustments
5. apply Tier 5 injury adjustments
6. apply Tier 6 referee adjustments
7. apply Tier 7 environment adjustments
8. compute final expected points
9. derive final margin and total
10. derive final H2H probabilities and fair odds
11. compare against Bet365 and Pinnacle

---

## Required Stored Outputs

For every model run, store:

- baseline home points
- baseline away points
- baseline margin
- baseline total
- each tier adjustment
- final home points
- final away points
- final margin
- final total
- final fair odds
- model version

This is mandatory for explainability and review.

---

## Future Evolution

Later versions may include:
- ML-assisted parameter tuning
- automatic matchup classification
- player-level injury values
- team-style clustering
- more granular market simulations
- live price movement integration
- multi-sport pricing logic

Version 1 should remain:
- clean
- statistical
- rules-based
- explainable