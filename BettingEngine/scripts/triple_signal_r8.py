"""
AFL R8 2026 — Triple Signal Scanner
Finds games where 3 independent research angles all point the same direction:
  1. H2H model EV >= 20%
  2. Rest advantage: team has 7+ days vs opponent on 6 or fewer
  3. Moon phase: within +/-2 days of full or new moon
"""
import datetime, math
from scipy.stats import norm

# ── Moon phase calculator ─────────────────────────────────────────────────
# Known new moon: Jan 6, 2000 (accurate reference)
KNOWN_NEW_MOON = datetime.date(2000, 1, 6)
LUNAR_CYCLE    = 29.530589

def moon_age(dt):
    """Days since last new moon (0=new, ~14.75=full, ~22=last quarter)."""
    return (dt - KNOWN_NEW_MOON).days % LUNAR_CYCLE

def moon_label(age):
    if age < 1.5 or age > 28.0:
        return 'NEW MOON', True, False
    if 13.5 < age < 16.0:
        return 'FULL MOON', False, True
    if age < 7:
        return 'waxing crescent', False, False
    if age < 13.5:
        return 'waxing gibbous', False, False
    if age < 22:
        return 'waning gibbous', False, False
    return 'waning crescent', False, False

def moon_effect(label_str):
    """Per CLAUDE.md research angles."""
    if 'NEW' in label_str:
        return 'AWAY underdogs + LOWER scores'
    if 'FULL' in label_str:
        return 'HOME teams + HIGHER scores'
    return None

# ── R7 last-game dates (for rest calculation) ─────────────────────────────
LAST_GAME = {
    'Western Bulldogs':              datetime.date(2026, 4, 23),  # R7 vs Sydney
    'Sydney Swans':                  datetime.date(2026, 4, 23),
    'Richmond Tigers':               datetime.date(2026, 4, 24),  # R7 vs Melbourne
    'Melbourne Demons':              datetime.date(2026, 4, 24),
    'Hawthorn Hawks':                datetime.date(2026, 4, 25),  # R7 vs Gold Coast
    'Gold Coast Suns':               datetime.date(2026, 4, 25),
    'Essendon Bombers':              datetime.date(2026, 4, 25),  # ANZAC Day
    'Collingwood Magpies':           datetime.date(2026, 4, 25),
    'Port Adelaide Power':           datetime.date(2026, 4, 25),
    'Geelong Cats':                  datetime.date(2026, 4, 25),
    'Fremantle Dockers':             datetime.date(2026, 4, 25),
    'Carlton Blues':                 datetime.date(2026, 4, 25),
    'St Kilda Saints':               datetime.date(2026, 4, 26),  # R7 vs West Coast
    'West Coast Eagles':             datetime.date(2026, 4, 26),
    'Brisbane Lions':                datetime.date(2026, 4, 26),
    'Adelaide Crows':                datetime.date(2026, 4, 26),
    'Greater Western Sydney Giants': datetime.date(2026, 4, 26),
    'North Melbourne Kangaroos':     datetime.date(2026, 4, 26),
}

def rest_days(team, game_date):
    last = LAST_GAME.get(team)
    if last is None:
        return None
    return (game_date - last).days

# ── R8 fixture + model outputs + market odds ───────────────────────────────
GAMES = [
    {
        'home': 'Collingwood Magpies',     'away': 'Hawthorn Hawks',
        'date': datetime.date(2026, 4, 30),
        'rules_h': 0.444,  'ml_h': 0.822,  'rules_m': -5.0,   'ml_m': -3.8,
        'rules_t': 169.6,  'ml_t': 166.4,
        'mkt_home': 3.60,  'mkt_away': 1.30,
        'hcap_line': -21.5, 'hcap_price': 1.91,
        'total_line': 179.5, 'total_price': 1.91,
    },
    {
        'home': 'Western Bulldogs',         'away': 'Fremantle Dockers',
        'date': datetime.date(2026, 5, 1),
        'rules_h': 0.739,  'ml_h': 0.690,  'rules_m': +23.0,  'ml_m': +12.5,
        'rules_t': 183.3,  'ml_t': 152.4,
        'mkt_home': 3.50,  'mkt_away': 1.31,
        'hcap_line': -20.5, 'hcap_price': 1.91,
        'total_line': 183.5, 'total_price': 1.91,
    },
    {
        'home': 'Adelaide Crows',           'away': 'Port Adelaide Power',
        'date': datetime.date(2026, 5, 1),
        'rules_h': 0.879,  'ml_h': 0.812,  'rules_m': +42.2,  'ml_m': +28.2,
        'rules_t': 168.4,  'ml_t': 186.6,
        'mkt_home': None,  'mkt_away': None,
        'hcap_line': -11.5, 'hcap_price': 1.91,
        'total_line': None, 'total_price': None,
    },
    {
        'home': 'Essendon Bombers',         'away': 'Brisbane Lions',
        'date': datetime.date(2026, 5, 2),
        'rules_h': 0.056,  'ml_h': 0.397,  'rules_m': -57.1,  'ml_m': -29.6,
        'rules_t': 169.9,  'ml_t': 160.2,
        'mkt_home': 8.00,  'mkt_away': 1.08,
        'hcap_line': +57.1, 'hcap_price': 1.91,  # Brisbane -43.5 proxy
        'total_line': None, 'total_price': None,
    },
    {
        'home': 'West Coast Eagles',        'away': 'Richmond Tigers',
        'date': datetime.date(2026, 5, 2),
        'rules_h': 0.713,  'ml_h': 0.755,  'rules_m': +20.3,  'ml_m': +17.1,
        'rules_t': 138.9,  'ml_t': 154.4,
        'mkt_home': None,  'mkt_away': 2.90,
        'hcap_line': -15.5, 'hcap_price': None,
        'total_line': None, 'total_price': None,
    },
    {
        'home': 'Geelong Cats',             'away': 'North Melbourne Kangaroos',
        'date': datetime.date(2026, 5, 2),
        'rules_h': 0.929,  'ml_h': 0.676,  'rules_m': +52.9,  'ml_m': +34.3,
        'rules_t': 187.0,  'ml_t': 167.2,
        'mkt_home': 1.20,  'mkt_away': 4.60,
        'hcap_line': -28.5, 'hcap_price': 1.91,
        'total_line': 189.5, 'total_price': 1.91,
    },
    {
        'home': 'Carlton Blues',            'away': 'St Kilda Saints',
        'date': datetime.date(2026, 5, 2),
        'rules_h': 0.633,  'ml_h': 0.660,  'rules_m': +12.2,  'ml_m': +12.1,
        'rules_t': 165.9,  'ml_t': 163.8,
        'mkt_home': 2.80,  'mkt_away': 1.44,
        'hcap_line': -14.5, 'hcap_price': 1.91,  # market has STK -14.5
        'total_line': None, 'total_price': None,
    },
    {
        'home': 'Sydney Swans',             'away': 'Melbourne Demons',
        'date': datetime.date(2026, 5, 3),
        'rules_h': 0.886,  'ml_h': 0.809,  'rules_m': +43.4,  'ml_m': +29.1,
        'rules_t': 188.6,  'ml_t': 177.6,
        'mkt_home': 1.17,  'mkt_away': 5.25,
        'hcap_line': -31.5, 'hcap_price': 1.91,
        'total_line': 188.5, 'total_price': 1.91,
    },
    {
        'home': 'Gold Coast Suns',          'away': 'Greater Western Sydney Giants',
        'date': datetime.date(2026, 5, 3),
        'rules_h': 0.692,  'ml_h': 0.920,  'rules_m': +18.0,  'ml_m': +12.2,
        'rules_t': 182.4,  'ml_t': 152.7,
        'mkt_home': None,  'mkt_away': 3.10,
        'hcap_line': +25.5, 'hcap_price': 1.64,
        'total_line': None, 'total_price': None,
    },
]

W = 100
print()
print('=' * W)
print('  AFL R8 2026 — TRIPLE SIGNAL SCANNER')
print('  Signals: (1) H2H model EV >= 20%  (2) Rest advantage  (3) Moon phase')
print('  Moon ref: Jan 6 2000 new moon. Full moon effect = home+higher scores.')
print('=' * W)

# ── Moon phase table ───────────────────────────────────────────────────────
print()
print('  MOON PHASE — R8 GAME DATES')
print(f'  {"Date":<14} {"Age (days)":>11} {"Phase":<22} {"Effect on game"}')
print('  ' + '-' * 80)
dates_seen = set()
for g in GAMES:
    d = g['date']
    if d in dates_seen:
        continue
    dates_seen.add(d)
    age = moon_age(d)
    label, is_new, is_full = moon_label(age)
    effect = moon_effect(label) or 'no strong signal'
    marker = '  <<<' if (is_new or is_full) else ''
    print(f'  {str(d):<14} {age:>11.1f} {label:<22} {effect}{marker}')

# ── Per-game signal table ──────────────────────────────────────────────────
print()
print('  SIGNAL MATRIX')
print(f'  {"Game":<38} {"Date":<12} {"H Rest":>6} {"A Rest":>6} {"Moon":>13} '
      f'{"H H2H EV":>10} {"A H2H EV":>10} {"Signals"}')
print('  ' + '-' * W)

findings = []

for g in GAMES:
    home = g['home'].split()[-1]
    away = g['away'].split()[-1]
    d    = g['date']

    hr = rest_days(g['home'], d)
    ar = rest_days(g['away'], d)

    age = moon_age(d)
    label, is_new, is_full = moon_label(age)
    phase_short = label.replace(' ', ' ')  # keep compact

    # H2H EV
    rh = g['rules_h']
    ra = 1 - rh
    mh = g['mkt_home']
    ma = g['mkt_away']
    evh = (rh * mh - 1) if mh else None
    eva = (ra * ma - 1) if ma else None
    evh_s = f'{evh:+.0%}' if evh is not None else '   —'
    eva_s = f'{eva:+.0%}' if eva is not None else '   —'

    signals = []

    # Signal 1a: Home H2H EV >= 20%
    home_h2h_edge = evh is not None and evh >= 0.20
    # Signal 1b: Away H2H EV >= 20%
    away_h2h_edge = eva is not None and eva >= 0.20

    # Signal 2: Rest advantage (7+ days vs opponent 6 or fewer)
    home_rest_edge = hr is not None and ar is not None and hr >= 7 and ar <= 6
    away_rest_edge = hr is not None and ar is not None and ar >= 7 and hr <= 6

    # Signal 3: Moon (full moon = home teams, new moon = away underdogs)
    if is_full:
        moon_home_edge = True   # full moon favours home
        moon_away_edge = False
    elif is_new:
        moon_home_edge = False
        moon_away_edge = True   # new moon favours away underdogs
    else:
        moon_home_edge = False
        moon_away_edge = False

    # Count signals per team
    home_signals = sum([home_h2h_edge, home_rest_edge, moon_home_edge])
    away_signals = sum([away_h2h_edge, away_rest_edge, moon_away_edge])

    sig_parts = []
    if home_h2h_edge:   sig_parts.append(f'HOME H2H EV {evh:+.0%}')
    if home_rest_edge:  sig_parts.append(f'HOME rest {hr}d>{ar}d')
    if moon_home_edge:  sig_parts.append(f'FULL MOON->home')
    if away_h2h_edge:   sig_parts.append(f'AWAY H2H EV {eva:+.0%}')
    if away_rest_edge:  sig_parts.append(f'AWAY rest {ar}d>{hr}d')
    if moon_away_edge:  sig_parts.append(f'NEW MOON->away')
    sig_str = ' | '.join(sig_parts) if sig_parts else '—'

    flag = ''
    if home_signals >= 3:
        flag = '  *** TRIPLE HOME'
        findings.append(('HOME', g, home_signals, home_h2h_edge, home_rest_edge, moon_home_edge, evh, hr, ar, age, label))
    elif away_signals >= 3:
        flag = '  *** TRIPLE AWAY'
        findings.append(('AWAY', g, away_signals, away_h2h_edge, away_rest_edge, moon_away_edge, eva, ar, hr, age, label))
    elif home_signals == 2:
        flag = '  ** double home'
        findings.append(('HOME', g, home_signals, home_h2h_edge, home_rest_edge, moon_home_edge, evh, hr, ar, age, label))
    elif away_signals == 2:
        flag = '  ** double away'
        findings.append(('AWAY', g, away_signals, away_h2h_edge, away_rest_edge, moon_away_edge, eva, ar, hr, age, label))

    label_s = label[:13]
    print(f'  {home+" vs "+away:<38} {str(d):<12} {str(hr)+"d":>6} {str(ar)+"d":>6} {label_s:>13} '
          f'{evh_s:>10} {eva_s:>10}{flag}')

# ── Triple + double signal summary ────────────────────────────────────────
triples = [f for f in findings if f[2] >= 3]
doubles = [f for f in findings if f[2] == 2]

print()
print('=' * W)
print('  FINDINGS')
print('=' * W)

if triples:
    for side, g, n, s1, s2, s3, ev_val, rest_team, rest_opp, age, label in triples:
        home_s = g['home'].split()[-1]; away_s = g['away'].split()[-1]
        team = home_s if side == 'HOME' else away_s
        opp  = away_s if side == 'HOME' else home_s
        print(f'''
  *** TRIPLE SIGNAL: {team} ({side})  |  {home_s} vs {away_s}  |  {g["date"]}

      Signal 1 — H2H Model EV:  {"YES" if s1 else "NO"}
        Rules model prob: {g["rules_h"]:.1%} (home) / {1-g["rules_h"]:.1%} (away)
        ML model prob:    {g["ml_h"]:.1%} (home) / {1-g["ml_h"]:.1%} (away)
        Market odds:      home ${g["mkt_home"]} / away ${g["mkt_away"]}
        EV for {team}:   {ev_val:+.1%}

      Signal 2 — Rest Advantage:  {"YES" if s2 else "NO"}
        {team}: {rest_team} days rest
        {opp}:   {rest_opp} days rest
        Advantage: {rest_team - rest_opp:+d} days to {team}

      Signal 3 — Moon Phase:  {"YES" if s3 else "NO"}
        Game date: {g["date"]}  |  Moon age: {age:.1f} days  |  Phase: {label}
        Effect: {"HOME performance boost" if side=="HOME" else "AWAY underdog support"}
''')
else:
    print()
    print('  No clean triple signals found — listing best doubles:')

if doubles and not triples:
    for side, g, n, s1, s2, s3, ev_val, rest_team, rest_opp, age, label in doubles[:3]:
        home_s = g['home'].split()[-1]; away_s = g['away'].split()[-1]
        team = home_s if side == 'HOME' else away_s
        opp  = away_s if side == 'HOME' else home_s
        missing = []
        if not s1: missing.append('no H2H EV >= 20%')
        if not s2: missing.append(f'rest: {team} {rest_team}d vs {opp} {rest_opp}d (no clear edge)')
        if not s3: missing.append(f'moon {label} — no effect')
        print(f'  ** Double: {team} ({side}) — {home_s} vs {away_s} on {g["date"]}')
        print(f'     Signals: {"H2H EV" if s1 else ""} {"Rest" if s2 else ""} {"Moon" if s3 else ""}  |  Missing: {", ".join(missing)}')
        print(f'     H2H EV: {ev_val:+.1%}  |  Rest: {team} {rest_team}d vs {opp} {rest_opp}d  |  Moon: {label} (age {age:.1f}d)')
        print()

print()
print('  Odds from Bet365 web search 2026-05-01. Moon algo: Jan 6 2000 new moon ref.')
print('  ELO stale (R6). Verify R7 results + market odds before acting.')
print('=' * W)
