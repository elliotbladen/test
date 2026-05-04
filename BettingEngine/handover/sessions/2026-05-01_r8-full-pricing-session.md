# 2026-05-01 — AFL R8 Full Pricing Session (ELOs Fixed + T5/T6 Updated + All Markets)
**Agent:** Claude (claude-sonnet-4-6)
**Round context:** AFL Official Round 8 2026 (April 30 – May 3)

---

## What was done

### 1. ELOs fixed — features_afl.csv rebuilt from scratch
- Previous session had ELOs stale by 2 rounds (features_afl.csv only went to April 12, AFL R6)
- User provided updated xlsx: `c:\Users\ElliotBladen\Downloads\afl (3).xlsx`
- Ran `ml/afl/game_log.py --xlsx "c:/Users/ElliotBladen/Downloads/afl (3).xlsx"`
- Rebuilt features_afl.csv from 2009–2026 with ELOs current through AFL R7 (April 23–26)
- New row count: 3,416 (was 3,398 — 18 new games added: AFL R7 + AFL R7 ANZAC round)
- **IMPORTANT:** features_afl.csv has a Windows-1252 smart apostrophe in "Cazaly's Stadium"
  Fixed by adding `encoding='latin-1'` to `pd.read_csv(FEATURES)` in `prepare_afl_round.py` (line ~760)

### Round numbering clarification (IMPORTANT for Codex)
AFL Official round numbers differ from AFL Tables:
- AFL Official R7 = April 23–26 (ANZAC round: Collingwood beat Essendon 137-60, Brisbane beat Adelaide 127-75 etc.)
- AFL Official R8 = April 30 – May 3 (the round being priced this session)
- AFL Tables website numbers these as R8 and R9 respectively — DO NOT use AFL Tables round numbers
- Our codebase uses OFFICIAL AFL round numbers throughout (FIXTURE key 8 = April 30–May 3) ✓

**Post-R7 ELO snapshot:**
| Team | ELO |
|------|-----|
| Brisbane Lions | 1751 |
| Hawthorn Hawks | 1722 |
| Geelong Cats | 1676 |
| Sydney Swans | 1674 |
| Western Bulldogs | 1632 |
| Fremantle Dockers | 1629 |
| Adelaide Crows | 1628 |
| Collingwood Magpies | 1610 |
| Gold Coast Suns | 1595 |
| GWS Giants | 1538 |
| Port Adelaide Power | 1405 |
| Melbourne Demons | 1399 |
| St Kilda Saints | 1397 |
| North Melbourne | 1367 |
| Carlton Blues | 1359 |
| Essendon Bombers | 1296 |
| West Coast Eagles | 1172 |
| Richmond Tigers | 1150 |

### 2. T5 Injuries — full comprehensive scrape (AFL.com.au, April 28)
- Old INJURIES[8] was a shallow 8-team list from the previous session
- Replaced with comprehensive INJURIES[8] covering all 18 teams
- Source: AFL.com.au injury list scraped 2026-04-28
- Key absences this round:
  - **Connor Rozee** (Port Adelaide) — hamstring 9-11w — elite midfielder, season-defining loss
  - **Errol Gulden** (Sydney) — shoulder 3 months — elite midfielder
  - **Sean Darcy** (Fremantle) — calf 3-5w — main ruck, spine disruption
  - **Sam Darcy** (Bulldogs) — ACL, season — ongoing
  - **Tom Green** (GWS) — knee, season — ongoing
  - **Jack Viney** (Melbourne) — achilles TBC — monitor
  - **Harry McKay** (Carlton) — concussion test — monitor (elite key forward)
  - **Josh Kelly** (GWS) — hip TBC — monitor
  - **Lance Collard** (St Kilda) — suspended to R13

### 3. T6 Emotional flags — updated for R8
Replaced shallow previous entry with:
- **Adelaide Crows**: rivalry_derby MAJOR (first Showdown of 2026) + shame_blowout MINOR (off 52-pt Brisbane loss)
- **Port Adelaide Power**: rivalry_derby MAJOR (first Showdown of 2026)
- **Essendon Bombers**: shame_blowout MAJOR (ANZAC Day 77-pt humiliation vs Collingwood, 60-137)

### 4. Rules engine T1-T7 run
Command: `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe scripts/prepare_afl_round.py --season 2026 --round 8`

**R8 pricing output (T1-T7 Rules):**
| Game | Fair Margin | Fair Total | Home Odds | Away Odds |
|------|-------------|------------|-----------|-----------|
| Magpies vs Hawks | Hawks -5.4 | 175.0 | 2.27 | 1.79 |
| Bulldogs vs Dockers | Bulldogs -9.1 | 172.5 | 1.67 | 2.50 |
| **Crows vs Power** | **Crows -55.7** | 168.0 | 1.06 | 16.42 |
| Bombers vs Lions | Lions -44.1 | 179.0 | 9.07 | 1.12 |
| Eagles vs Tigers | Eagles -19.9 | 137.0 | 1.41 | 3.44 |
| Cats vs Kangaroos | Cats -62.3 | 188.0 | 1.04 | 23.92 |
| Blues vs Saints | Blues -6.4 | 171.0 | 1.75 | 2.33 |
| **Swans vs Demons** | **Swans -56.8** | **203.0** | 1.06 | 17.45 |
| Suns vs Giants | Suns -18.6 | 173.5 | 1.43 | 3.31 |

Notable T5 impacts:
- Crows vs Power: T5 = +8.0 (Rozee/Powell-Pepper/Lukosius all out for Port)
- Bulldogs vs Dockers: T5 = -3.83 (both rucks out Bulldogs side, Fremantle also missing ruck)
- Blues vs Saints: T5 = -2.18 (McKay test + Motlop out)
- Swans vs Demons: total 203.0 driven by SCG fortress + high scoring both sides + injury-weakened Melbourne defence

### 5. ML Shadow run
Runs automatically as part of prepare_afl_round.py. Key divergences:
| Game | Rules Mrg | ML Mrg | Gap | Flag |
|------|-----------|--------|-----|------|
| Magpies vs Hawks | Hawks -5 | **Collingwood +5** | 10.7pt | OPPOSITE SIDES |
| Bulldogs vs Dockers | Bulldogs -9 | **Fremantle +6** | 14.9pt | OPPOSITE SIDES |
| **Bombers vs Lions** | Lions -44 | Lions -15 | 29.6pt | ML much softer on Brisbane |
| Cats vs Kangaroos | Cats -62 | Cats -42 | 20.8pt | ML less extreme |
| Blues vs Saints | Blues -6 | Blues -1 | near coinflip | ML cautious |
| Swans vs Demons | Swans -57 | Swans -39 | 18pt | totals: 203 vs 170 |

- DB: 9 rows stored in `afl_shadow_predictions` (season=2026, round=8)
- Output saved: `results/r8_afl_2026.txt`

### 6. Research matrices run (H2H, Handicap, Totals)

**H2H matrix (20% threshold):** `scripts/h2h_research_r8.py`
- **TRIPLE SIGNAL: Adelaide Crows (HOME)** vs Port Adelaide
  - vs Port H2H record: +53.2% ROI (n=12)
  - Full moon games: +26.2% ROI (n=21)
  - Full moon at home: +26.2% ROI (n=21)
  - Note: angles 2+3 are correlated (same 21 games). Two independent signals.

**Handicap matrix (20% threshold):** `scripts/handicap_research_r8.py`
- No triple signals
- Adelaide Crows covering vs Port (line): +43.2% ROI (n=12) — strongest single
- Geelong covering in May: +24.1% (n=20) — correlated double only

**Totals matrix (20% threshold):** `scripts/totals_research_r8.py`
- **TRIPLE SIGNAL: West Coast vs Richmond → UNDER** (conflicted)
  - Eagles vs Tigers all time: OVER +43.2% (n=8) — small sample
  - Eagles at home full moon: UNDER +24.1% (n=20)
  - Tigers in May: UNDER +21.5% (n=22)
  - 2/3 angles say UNDER but highest ROI says OVER — treat with caution
- Notable singles: Gold Coast Suns in May OVER +43.2% (n=24)

**10% threshold scan — Bulldogs and Carlton specifically:**
- **Bulldogs H2H full moon: +21.1% (n=19)** — genuine signal, also backs into handicap at +10.6%
- **Bulldogs H2H in May: +13.5% (n=22)** — secondary support
- Carlton H2H in May: +11.6% (n=25) — weak, no handicap support
- Carlton handicap: nothing at 10%+

---

## Current state

| Component | Status |
|-----------|--------|
| features_afl.csv | ✅ Current through AFL R7 (April 23–26) |
| AFL R8 injuries | ✅ Comprehensive (18 teams, scraped April 28) |
| AFL R8 emotional flags | ✅ Showdown major + Essendon shame_blowout |
| AFL R8 rules pricing | ✅ `results/r8_afl_2026.txt` |
| AFL R8 ML shadow | ✅ Embedded in prepare_afl_round.py output, DB stored |
| Research matrices | ✅ H2H / Handicap / Totals scripts in `scripts/` |
| EV matrix vs market | ❌ NOT DONE — need market odds to build |

---

## Watch out for

- **encoding='latin-1'** must be used when reading features_afl.csv (smart apostrophe in Cazaly's Stadium)
- **Python env:** ALWAYS use `.venv/Scripts/python.exe` — python3.14 has no numpy/pandas
- **Harry McKay (Carlton)** — concussion test, if confirmed OUT the Carlton -6.4 line softens significantly
- **ML shadow totals bias correction +14.6pts** is still large — 2026 scoring running high vs 2009-2023 training data
- **Collingwood vs Hawthorn already played** (drew 93-93, April 30) — models disagreed (rules: Hawks, ML: Magpies). Draw was between both models.
- **Research matrix scripts** (h2h/handicap/totals) are hardcoded to R8 fixture and R7_LAST dates — need updating for R9

---

## Signals summary for R8

| Signal | Market | Edge | Confidence |
|--------|--------|------|------------|
| **Adelaide Crows** vs Port | H2H + Line | Triple signal H2H + Line historical | Highest |
| **Bulldogs** vs Fremantle | H2H | Full moon +21.1% (n=19) | Moderate |
| **West Coast UNDER** vs Richmond | Totals | 2/3 angles (conflicted) | Low-moderate |
| Carlton vs St Kilda | H2H | May +11.6% (n=25) only | Weak |

---

## Next session should

1. **Build EV matrix for R8** — scrape Bet365 lines for all 9 games and calculate EV vs model prices
2. **Ingest R8 results** after games complete (May 1–3) into features_afl.csv
3. **Build actuals ingestion** — fill `afl_shadow_predictions.actual_*` columns post-round
4. **NRL R9 backfill** to `ml_shadow_predictions`: `PYTHONIOENCODING=utf-8 .venv/Scripts/python.exe ml/run_r9_shadow.py --season 2026 --round 9`
5. **Generalise research matrix scripts** — parameterise by round instead of hardcoding R8 fixture
6. **Fix West Coast T4 fortress** (-3.0 applied to home team — check if this is correct or a data bug)
7. **Update features_afl.csv** after R8 results are known — rebuild from updated xlsx
