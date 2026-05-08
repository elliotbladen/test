# BetMATE Scout and Auditor Strategy

Date: 2026-05-08

## Product Direction

BetMATE should not try to be Sportsbet. Sportsbet owns bet placement, wallet UX, same-game multis, promos, and account depth.

BetMATE's lane is:

> Odds comparison plus decision intelligence for Australian punters.

The product should feel like:

> Oddschecker meets a sharp betting analyst, built for Australia.

The first audience target is not mass-market scale. The realistic early win is a tight community:

- 2,000-5,000 monthly users
- 300-800 logged-in users
- 100-250 tipping comp entrants
- 50-150 users checking NRL/AFL odds each round
- 20-50 serious community regulars

The public habit to own:

> Before you bet NRL or AFL, check BetMATE.

## Baz

Baz is the betting brain / betting model / betting engine interface.

Logged-in free users may receive a limited version of Baz:

- capped questions or replies
- reduced "juice" compared with paid users later
- useful enough to become a habit, but not the full betting engine

Baz should explain:

- value
- model lean
- odds movement
- whether a game is a bet, lean, pass, or wait
- why the information matters

## Scout

Scout is the next major AI agent after Baz.

Scout's job:

> Scan the changing information around every game and only report the material changes.

Scout is the information hunter, not the betting brain.

Scout should scan 7-8 streams:

- odds movement
- team lists
- injuries/suspensions
- weather
- referee/umpire appointments
- rest/travel spots
- recent form/context
- public/market sentiment

Scout should not dump every stat. It should report only what matters:

- Major
- Watch
- No issue

Example Scout output:

```text
Scout Watch
- Major: Halfback ruled out, line moved from -6.5 to -3.5.
- Watch: Rain forecast has strengthened, total dropped 2 points.
- No issue: Referee profile normal.

Conclusion: This game has changed materially since open. Do not treat the original price as current truth.
```

This is also the content engine for social posts/Twitter/X.

Scout can generate short posts such as:

```text
NRL Scout Watch:
Storm line has moved 2 points since open after team news. Total also drifting down with rain forecast. This is no longer the same market that opened Monday.
```

Scout makes BetMATE feel alive because it constantly watches what changed.

## Auditor

Auditor is the data-quality and fact-checking agent.

This is critical because:

1. the betting engine may consume this information
2. real people will view the website and make decisions from it

Auditor should not make betting calls. It checks whether facts are reliable before they become confident site/model data.

Auditor verifies:

- fixture date/time
- teams
- venue
- bookmaker odds
- opening/closing movement
- team list changes
- injury/suspension status
- referee/umpire appointment
- weather location
- model output freshness
- source timestamp

Confidence states:

- verified
- unverified
- stale
- conflict
- manual_override
- do_not_use

The betting engine should only consume `verified` or approved `manual_override` data.

The website can show softer unverified wording, but should never present uncertain claims as fact.

## Data Control Room

Before adding more flashy AI, BetMATE needs a data-quality layer.

Internal name:

> BetMATE Data Control Room

Core pieces:

- source registry
- freshness checks
- conflict detection
- confidence labels
- manual overrides
- admin review queue
- audit history
- "used by model" flag

Public version can be simple:

```text
Verified 12:04 PM · 2 sources checked
```

Structured version for the engine:

```json
{
  "field": "referee",
  "value": "Adam Gee",
  "status": "verified",
  "sources": ["nrl_official"],
  "fetched_at": "2026-05-08T12:04:00+10:00",
  "model_safe": true
}
```

## Auditor Workflow

If Scout finds something:

```text
Player X is out.
```

Auditor checks:

- official team list
- club report
- article/source timestamp
- source reliability

If clean:

```text
Verified team news: Player X ruled out.
```

If weak:

```text
Unconfirmed report: Player X may miss.
```

If conflicting:

```text
Player X status unclear. Official team list still names him; one report says he may miss.
```

Auditor creates a Data Issue:

```text
Game: Broncos vs Storm
Field: Team news
Problem: Scout says Player X is out, but official team list says named.
Severity: High
Status: Needs review
Source A: article, 9:14am
Source B: official team list, 4:05pm
Suggested action: Do not publish as confirmed. Show as unverified.
```

High-severity issues should alert the admin/human first.

Recheck cadence:

- high severity: every 10-15 minutes
- medium severity: hourly
- low severity: next data refresh

Issue statuses:

- open
- rechecking
- resolved
- needs_human
- suppressed

## Correction Workflow

AI should not silently overwrite critical betting information.

For bad live data:

- Auditor can downgrade confidence
- hide the claim from Baz's confident summary
- mark field as unverified/conflict/do_not_use

For confirmed fixes:

- admin/human approves correction
- corrected data is saved with audit trail

Example:

```text
Corrected by: Elliot
Reason: Official NRL team list confirmed
Old value: Player X out
New value: Player X named
Source: nrl.com team list
Time: 4:18pm
```

## Bug Workflow

If Auditor sees repeated bad data, it should create a technical bug issue.

Example:

```text
Bug suspected:
Source parser is reading "may be ruled out" as "ruled out".
Affected games: 4
Parser: nrl_news_flags.py
Recommended fix: classify speculative language separately.
```

Engineering flow:

1. Auditor detects bad data.
2. Creates Data Issue.
3. If repeated, creates Bug Issue.
4. Human reviews.
5. Engineer/Fixer patches scraper/parser/model logic.
6. Auditor reruns historical check to confirm the bug is gone.

## Tipping Comp Notes

A tipping comp fits the product because it gives normal punters a reason to return.

Recommended positioning:

> Beat Baz: $1,000 Footy Tipping Challenge

For 250 entrants and a $1,000 prize pool:

- Season winner: $500
- Runner-up: $250
- Third: $100
- Best single round: $100
- Beat Baz season bonus: $50

Important: if cash prizes are offered in Australia, competition/promotion rules should be checked before launch.

## Statistical Note

If a model or picker is truly 65%, one person in a 1,000-person tipping pool hitting 70% over a normal season is not surprising.

Approximate binomial result:

- 50 games: at least one of 1,000 hitting 70%+ is effectively certain
- 100 games: effectively certain
- 200 games: effectively certain
- 300 games: effectively certain
- 400 games: still effectively certain

To make 70% genuinely rare among 1,000 people:

- about 900 games: roughly 50% chance someone hits it
- about 1,200 games: roughly 10%
- about 1,330 games: roughly 5%
- about 1,600 games: roughly 1%

Therefore BetMATE should show:

- season rank for fun
- long-term verified edge for credibility
- CLV/value score to separate skill from variance

## Surface Speed / Grass Length Idea

Commercial tier:

> Paid feature.

This should sit behind the paid product because it is specialist intelligence, not basic odds comparison. Free users can see simple weather/venue notes, but the actual Surface Watch signal should be paid.

Question raised:

> How easy would it be to determine the blade length of the pitch/grass at football stadiums?

Answer:

Exact live blade length per stadium is hard unless the league, venue, club, or ground staff publish it.

Useful pitch/ground-speed intelligence is much more achievable.

Easy to track:

- regulation grass-height ranges
- normal expected cut height by sport/venue type
- weather
- recent stadium usage
- turf type if known
- complaints/media reports
- photos/video where available
- club/venue/ground-staff updates

Hard to verify:

- exact live grass length such as "31mm today"
- consistent NRL/AFL venue-by-venue grass height
- automated measurement without official data or someone at the ground

Known reference ranges from discussion:

- Premier League grass must not exceed around 27mm and must be consistent across the surface.
- UEFA natural grass is generally not to exceed around 30mm.
- General football pitch guidance often sits around 25-35mm.
- Rugby league guidance is often longer, roughly 30-50mm.

Recommended BetMATE feature:

> Surface Watch

Do not publish exact grass height unless sourced. Instead publish a Scout signal:

```text
Surface Watch
- Grass height: regulation expected
- Watering: unknown
- Weather: heavy rain forecast
- Venue: historically slower when wet
- Recent usage: 2 events in 5 days
- Signal: Likely slower surface
```

Auditor confidence states for surface info:

- verified exact measurement
- expected regulation range
- unverified report
- likely slow/fast surface
- do_not_use

Example gold-standard wording:

```text
Verified: UEFA measured the pitch at 26mm, within regulation.
```

Example safe wording when exact data is unavailable:

```text
Likely slower surface due to rain forecast and recent venue usage. No verified grass-height measurement available.
```

This is an advanced Scout feature, not core launch work. It could become useful for totals, unders, ball movement, fatigue, and game tempo once the core data-quality layer is reliable.

Free vs paid split:

- Free: basic weather, venue, and fixture context.
- Paid: Surface Watch, surface-speed signal, verified/unverified grass-length notes, recent venue usage, watering/ground-condition watch, and betting impact summary.
