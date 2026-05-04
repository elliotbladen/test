"""
AFL R8 2026 — Totals Research Matrix
For each game, find historical angles matching this week's exact conditions
and calculate ROI on OVER and UNDER at fixed 1.91.
Flag any angle with >= 20% ROI and n >= 8 games.

over_result  = total_score > total_open
under_result = total_score < total_open
"""
import datetime
import pandas as pd

FEATURES      = 'ml/afl/results/features_afl.csv'
MIN_N         = 8
ROI_THRESHOLD = 0.20
LINE_PRICE    = 1.91

KNOWN_NEW_MOON = datetime.date(2000, 1, 6)
LUNAR_CYCLE    = 29.530589

def moon_age(dt):
    if isinstance(dt, str):
        dt = datetime.date.fromisoformat(dt)
    return (dt - KNOWN_NEW_MOON).days % LUNAR_CYCLE

def is_full_moon(age): return 13.0 < age < 16.5
def is_new_moon(age):  return age < 2.0 or age > 27.5

# ── R8 rest days ──────────────────────────────────────────────────────────────
R7_LAST = {
    'Western Bulldogs':              datetime.date(2026, 4, 23),
    'Sydney Swans':                  datetime.date(2026, 4, 23),
    'Richmond Tigers':               datetime.date(2026, 4, 24),
    'Melbourne Demons':              datetime.date(2026, 4, 24),
    'Hawthorn Hawks':                datetime.date(2026, 4, 25),
    'Gold Coast Suns':               datetime.date(2026, 4, 25),
    'Essendon Bombers':              datetime.date(2026, 4, 25),
    'Collingwood Magpies':           datetime.date(2026, 4, 25),
    'Port Adelaide Power':           datetime.date(2026, 4, 25),
    'Geelong Cats':                  datetime.date(2026, 4, 25),
    'Fremantle Dockers':             datetime.date(2026, 4, 25),
    'Carlton Blues':                 datetime.date(2026, 4, 25),
    'St Kilda Saints':               datetime.date(2026, 4, 26),
    'West Coast Eagles':             datetime.date(2026, 4, 26),
    'Brisbane Lions':                datetime.date(2026, 4, 26),
    'Adelaide Crows':                datetime.date(2026, 4, 26),
    'Greater Western Sydney Giants': datetime.date(2026, 4, 26),
    'North Melbourne Kangaroos':     datetime.date(2026, 4, 26),
}

FIXTURE = [
    ('Collingwood Magpies',           'Hawthorn Hawks',                datetime.date(2026, 4, 30)),
    ('Western Bulldogs',              'Fremantle Dockers',             datetime.date(2026, 5, 1)),
    ('Adelaide Crows',                'Port Adelaide Power',           datetime.date(2026, 5, 1)),
    ('Essendon Bombers',              'Brisbane Lions',                datetime.date(2026, 5, 2)),
    ('West Coast Eagles',             'Richmond Tigers',               datetime.date(2026, 5, 2)),
    ('Geelong Cats',                  'North Melbourne Kangaroos',     datetime.date(2026, 5, 2)),
    ('Carlton Blues',                 'St Kilda Saints',               datetime.date(2026, 5, 2)),
    ('Sydney Swans',                  'Melbourne Demons',              datetime.date(2026, 5, 3)),
    ('Gold Coast Suns',               'Greater Western Sydney Giants', datetime.date(2026, 5, 3)),
]

def rest(team, game_date):
    last = R7_LAST.get(team)
    return (game_date - last).days if last else None

# ── Load & prep ───────────────────────────────────────────────────────────────
df = pd.read_csv(FEATURES, low_memory=False)
df['date_dt']   = pd.to_datetime(df['date']).dt.date
df['month']     = pd.to_datetime(df['date']).dt.month
df['moon_age']  = df['date_dt'].apply(moon_age)
df['full_moon'] = df['moon_age'].apply(is_full_moon)
df['new_moon']  = df['moon_age'].apply(is_new_moon)

df['total_open']  = pd.to_numeric(df['total_open'],  errors='coerce')
df['total_score'] = pd.to_numeric(df['total_score'], errors='coerce')
df = df.dropna(subset=['total_open', 'total_score'])

df['over_result']  = df['total_score'] > df['total_open']
df['under_result'] = df['total_score'] < df['total_open']

def roi(mask, bet):
    """bet: 'over' or 'under'"""
    sub = df[mask]
    if len(sub) < MIN_N:
        return None, None, len(sub)
    over_r  = (sub['over_result']  * LINE_PRICE - 1).mean()
    under_r = (sub['under_result'] * LINE_PRICE - 1).mean()
    if bet == 'over':
        return round(float(over_r), 3), 'OVER', len(sub)
    else:
        return round(float(under_r), 3), 'UNDER', len(sub)

def best_roi(mask):
    """Return best direction (over/under) if either >= threshold."""
    sub = df[mask]
    if len(sub) < MIN_N:
        return None, None, len(sub)
    over_r  = float((sub['over_result']  * LINE_PRICE - 1).mean())
    under_r = float((sub['under_result'] * LINE_PRICE - 1).mean())
    if over_r >= ROI_THRESHOLD and over_r >= under_r:
        return round(over_r, 3), 'OVER', len(sub)
    if under_r >= ROI_THRESHOLD:
        return round(under_r, 3), 'UNDER', len(sub)
    return None, None, len(sub)

def scan_game(home_team, away_team, game_date):
    """Return list of (angle_label, roi, direction, n) for the GAME (not per-team)."""
    month      = game_date.month
    home_rest  = rest(home_team, game_date)
    away_rest  = rest(away_team, game_date)
    game_moon  = moon_age(game_date)
    game_full  = is_full_moon(game_moon)
    game_new   = is_new_moon(game_moon)

    home_s = home_team.split()[-1]
    away_s = away_team.split()[-1]

    angles = []

    def check(label, mask):
        r, direction, n = best_roi(mask)
        if r is not None:
            angles.append((label, r, direction, n))

    # 1. This specific matchup
    check(f'{home_s} vs {away_s} (all time)',
          (df['home_team'] == home_team) & (df['away_team'] == away_team))

    # 2. All games involving home team (home or away)
    home_involved = (df['home_team'] == home_team) | (df['away_team'] == home_team)
    check(f'Games involving {home_s}', home_involved)

    # 3. All games involving away team
    away_involved = (df['home_team'] == away_team) | (df['away_team'] == away_team)
    check(f'Games involving {away_s}', away_involved)

    # 4. This month
    check(f'Games in {datetime.date(2026, month, 1).strftime("%B")}',
          df['month'] == month)

    # 5. Full moon (only if this game IS full moon)
    if game_full:
        check('Full moon games', df['full_moon'])

    # 6. New moon (only if this game IS new moon)
    if game_new:
        check('New moon games', df['new_moon'])

    # 7. Home team in this month
    check(f'{home_s} in {datetime.date(2026, month, 1).strftime("%B")}',
          (df['home_team'] == home_team) & (df['month'] == month))

    # 8. Away team in this month
    check(f'{away_s} in {datetime.date(2026, month, 1).strftime("%B")}',
          (df['away_team'] == away_team) & (df['month'] == month))

    # 9. Home team on this rest (only if ≥ 7d)
    if home_rest and home_rest >= 7:
        check(f'{home_s} after 7+ days rest',
              (df['home_team'] == home_team) & (df['home_rest_days'] >= 7))

    # 10. Away team on this rest (only if ≥ 7d)
    if away_rest and away_rest >= 7:
        check(f'{away_s} after 7+ days rest',
              (df['away_team'] == away_team) & (df['away_rest_days'] >= 7))

    # 11. Full moon in this month (intersection)
    if game_full:
        check(f'Full moon in {datetime.date(2026, month, 1).strftime("%B")}',
              df['full_moon'] & (df['month'] == month))

    # 12. Home team at home on full moon
    if game_full:
        check(f'{home_s} at home full moon',
              (df['home_team'] == home_team) & df['full_moon'])

    # dedup by label, sort by ROI
    seen = set(); out = []
    for label, r, direction, n in sorted(angles, key=lambda x: -x[1]):
        if label not in seen:
            seen.add(label)
            out.append((label, r, direction, n))
    return out

# ── Print ─────────────────────────────────────────────────────────────────────
print()
print('=' * 80)
print('  AFL R8 2026 — TOTALS RESEARCH MATRIX')
print(f'  Historical angles matching this week\'s exact conditions')
print(f'  Min sample n={MIN_N}  |  ROI threshold={ROI_THRESHOLD:.0%}  |  Line price: {LINE_PRICE}')
print('=' * 80)

triples = []

for home_team, away_team, game_date in FIXTURE:
    home_s    = home_team.split()[-1]
    away_s    = away_team.split()[-1]
    home_rest_d = rest(home_team, game_date)
    away_rest_d = rest(away_team, game_date)
    moon      = moon_age(game_date)
    phase     = 'FULL MOON' if is_full_moon(moon) else ('NEW MOON' if is_new_moon(moon) else f'age {moon:.1f}d')

    angles = scan_game(home_team, away_team, game_date)

    print(f'\n  {home_s} vs {away_s}  |  {game_date}  |  {phase}  |  rest: {home_s} {home_rest_d}d / {away_s} {away_rest_d}d')
    print(f'  {"─"*74}')

    if not angles:
        print(f'    No 20%+ angles found')
    else:
        for label, r, direction, n in angles[:6]:
            marker = '  ***' if len(angles) >= 3 and angles.index((label, r, direction, n)) < 3 else ''
            print(f'    {label:<44}  {direction:<5}  ROI {r:+.1%}  n={n}{marker}')

    if len(angles) >= 3:
        triples.append((f'{home_s} vs {away_s}', game_date, angles[:3]))

print()
print('=' * 80)
print('  TRIPLE SIGNAL GAMES  (3+ angles each >= 20% ROI, all conditions match)')
print('=' * 80)
if triples:
    for game, gdate, angles in triples:
        # Determine consensus direction
        directions = [a[2] for a in angles]
        consensus = 'OVER' if directions.count('OVER') >= 2 else 'UNDER'
        print(f'\n  *** {game}  →  {consensus}')
        for i, (label, r, direction, n) in enumerate(angles, 1):
            print(f'      #{i}  {label:<44}  {direction:<5}  ROI {r:+.1%}  (n={n})')
else:
    print('\n  No triple signals. Printing best doubles:')
    for home_team, away_team, game_date in FIXTURE:
        home_s = home_team.split()[-1]; away_s = away_team.split()[-1]
        angles = scan_game(home_team, away_team, game_date)
        if len(angles) == 2:
            print(f'\n  ** {home_s} vs {away_s}')
            for label, r, direction, n in angles:
                print(f'     {label:<44}  {direction:<5}  ROI {r:+.1%}  n={n}')
print()
