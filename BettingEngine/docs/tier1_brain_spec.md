# Tier 1 Brain Specification - V1

## Purpose

This document defines the **Tier 1 base betting brain** for the NRL pricing engine.

Tier 1 is the **foundational pricing layer**.
It is not the place for advanced situational angles, emotional narratives, weather, referee effects, or moon-phase logic.

Tier 1 should answer the basic bookmaker-style question:

**What should this game look like before special adjustments?**

It should produce:
- expected home points
- expected away points
- expected margin
- expected total
- fair H2H odds
- fair handicap line
- fair total line

---

## Tier 1 Role

Tier 1 is the **base engine**.

It should be:
- simple
- explainable
- stable
- tunable
- auditable

Tier 1 is not meant to capture every edge.
It is meant to create the best possible **base number** before Tier 2–7 adjustments.

---

## Tier 1 Core Structure

Tier 1 starts from:

- **home attack vs away defence**
- **away attack vs home defence**

Then it uses:
- league scoring baseline
- team-specific scoring/conceding tendencies
- season-long quality
- recent form
- team-specific home advantage

From that it derives:
- expected home points
- expected away points
- expected margin
- expected total
- H2H fair odds
- fair handicap line
- fair total line

---

## Core Tier 1 Beliefs

## 1. Attack vs Defence is the starting point
The model should begin with the scoring matchup:

- home expected points should begin from **home attack vs away defence**
- away expected points should begin from **away attack vs home defence**

This is the mathematical spine of Tier 1.

---

## 2. Use a mixed scoring baseline
Expected scores should not come from team numbers alone.

They should start from:
- a **league-wide scoring baseline**
- then be shifted by **team-specific attack/defence tendencies**

The model should think:

**What does a normal NRL game look like, and how do these two teams bend that up or down?**

---

## 3. Season-long quality matters
Season-long quality should be a major part of the base number.

It should be driven mainly by:
- wins/losses
- ladder position

This reflects:
- class
- standards
- winning culture
- long-term mentality

However:
- points
- margins

should quietly help correct misleading ladder positions.

So the model should:
- respect ladder position and winning
- but not be blind to deceptive records

---

## 4. Recent form matters
Recent form should be included in Tier 1.

### Recent form window
- use **last 5 games**

### Recent form should be a blend of:
- wins/losses
- scoring
- conceding
- margins

Recent form reflects:
- confidence
- current condition
- sharpness
- momentum

The model should not ignore recent form, but should not become overreactive either.

---

## 5. Class and confidence are roughly balanced
When season-long quality and recent form conflict:

- neither should fully dominate
- season-long quality is the deeper anchor
- recent form is the current pulse

### Interpretation
- class is more permanent
- confidence can materially move performance

So Tier 1 should treat them as **roughly balanced**, not all one way.

---

## 6. Hot form should move the number
If recent form looks clearly real, Tier 1 should move meaningfully.

But:
- it must not fully override long-term class
- its effect must be bounded
- its effect must be configurable

---

## 7. Attack rating
Attack rating should be based on:
- season-long scoring
- recent scoring

### V1 practical proxy
- points scored

### Conceptual note
Attack is understood as more than just points scored, but V1 uses points scored as the practical proxy.

Later versions may add richer attacking proxies.

---

## 8. Defence rating
Defence rating should be based on:
- season-long conceding
- recent conceding

### V1 practical proxy
- points conceded

### Conceptual note
Defence is understood as more than just points conceded, but V1 uses points conceded as the practical proxy.

Later versions may add richer defensive proxies.

---

## 9. Attack and defence are roughly equal overall
Tier 1 should treat attack and defence as broadly equal in importance.

However:

### Direct conflict rule
When there is direct tension between strong attack and strong defence,  
**defence gets a slight edge**.

This reflects the view that:
- defence is a little more stable
- attack can be more streaky
- defence can better control game shape

---

## 10. Team-specific home advantage
Home advantage should be:
- team-specific from the start
- not flat across the whole league

Some teams have stronger home environments than others.

### Rule
Each team should have its own home advantage value.

### Constraint
This value must be:
- capped
- adjustable later
- not allowed to become absurd due to noisy data

---

## 11. Totals uncertainty rule
When Tier 1 is uncertain, it should lean slightly toward:
- lower scoring
- more conservative totals

This is only a slight bias, not a heavy one.

This reflects:
- defence slightly trusted over attack in conflict
- uncertainty should not automatically create optimism

---

## 12. Close-call class rule
When the base number is close and Tier 1 is uncertain, it should lean slightly toward:
- the better class team
- the better favourite
- the better winning culture

This is only a slight lean, not a hard override.

---

## Behaviour Rules for Form Interpretation

## 13. Blowout rule
- blowout wins are mostly neutral
- blowout losses matter a bit more

Reason:
- big wins can flatter
- big losses often expose weakness
- negative signals are stronger than positive hype

---

## 14. Narrow-loss rule
A narrow loss to a strong team can be mildly positive,
but **only if broader form supports it**.

The model should not romanticize losing.

---

## 15. Ugly-win rule
Ugly wins are neutral by default.

Then:
- slightly positive if the team is broadly winning
- slightly negative if the team is broadly struggling

This makes ugly wins context-dependent.

---

## 16. Narrow-win vs weak-team rule
A narrow win against a weak team is:
- neutral

The model should note it, but not overread it.

---

## 17. Low-scoring winning rule
If a team is winning but not scoring much:

- acceptable if defence is elite
- mild warning if attack is weak and defence is not clearly dominant

The model should ask:
**why are they winning?**

---

## 18. High-scoring but leaky rule
If a team is scoring well but leaking points:

- slight warning

Reason:
- attack is real
- but leaking points is dangerous long term
- leaky teams can flatter to deceive

---

## What Does NOT Belong in Tier 1

The following do **not** belong in Tier 1:

- bye effects
- short turnaround
- long turnaround
- travel fatigue spots
- emotional bounce-back spots
- coach head-to-head
- stylistic quirks
- referee effects
- weather effects
- moon-phase effects
- manual narrative conviction spots

These belong later in the model.

---

## What Belongs in Tier 3 Instead

### Tier 3 situational layer should eventually include:
- off a bye
- short turnaround
- long turnaround
- travel compression
- bounce-back spots
- flat spots
- momentum/scheduling context

### Current belief
- off a bye / extra rest = mild positive
- short turnaround = mild negative

But these are:
- capped
- adjustable
- situational
- not Tier 1

---

## Required Adjustable Knobs

The Tier 1 implementation must be malleable.

These should be designed as configurable parameters later:

- season quality weight
- recent form weight
- attack rating weight
- defence rating weight
- team-specific home advantage values
- home advantage cap
- recent form cap
- recent form sensitivity
- totals conservative-bias strength
- close-call class lean
- defence-over-attack conflict lean
- blowout loss sensitivity
- ugly-win adjustment sensitivity
- narrow-loss mild-positive sensitivity
- leaky-team warning sensitivity

These do not all need full numeric tuning in V1,
but the architecture should expect them to become adjustable.

---

## Tier 1 Design Principles

Tier 1 should be:

### 1. Stable
Do not overreact to small samples.

### 2. Responsive
Do not ignore genuine current form.

### 3. Explainable
Every part of the number must be understandable.

### 4. Bounded
No single component should dominate wildly.

### 5. Tuneable
The model must be easy to refine later.

---

## Implementation Guidance for Claude

Claude is allowed to build:
- scaffolding
- clear function structure
- placeholder formulas
- comments
- audit-friendly code structure

Claude is not allowed yet to:
- invent advanced weights without approval
- implement Tier 2–7 logic
- implement EV/Kelly logic
- implement live features
- invent black-box ML behavior

The purpose of the next implementation step is to build the **Tier 1 structure**, not to finalize the full model math.

---

## Summary

Tier 1 is the model’s base football brain.

It believes:
- class matters
- confidence matters
- defence is slightly more trustworthy than attack in conflict
- not all wins are equal
- not all losses are equal
- home advantage differs by team
- uncertainty should lean slightly conservative
- the better class team deserves a slight edge in close calls

This is the starting identity of the NRL pricing engine.