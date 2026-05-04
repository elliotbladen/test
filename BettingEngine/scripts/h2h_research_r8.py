"""
AFL R8 2026 — H2H Research Matrix
For each game, find historical angles matching this week's exact conditions
(same month, same opponent, same home/away, same moon phase, etc.)
and calculate ROI. Flag any angle with >= 20% ROI and n >= 8 games.
"""
import datetime, math
import pandas as pd
import numpy as np

FEATURES = 'ml/afl/results/features_afl.csv'
MIN_N    = 8      # minimum sample size to report
ROI_THRESHOLD = 0.20

KNOWN_NEW_MOON = datetime.date(2000, 1, 6)
LUNAR_CYCLE    = 29.530589

def moon_age(dt):
    if isinstance(dt, str):
        dt = datetime.date.fromisoformat(dt)
    return (dt - KNOWN_NEW_MOON).days % LUNAR_CYCLE

def is_full_moon(age):
    return 13.0 < age < 16.5

def is_new_moon(age):
    return age < 2.0 or age > 27.5

# ── R8 fixture + conditions ───────────────────────────────────────────────
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

# ── Load & prep data ──────────────────────────────────────────────────────
df = pd.read_csv(FEATURES, low_memory=False)
df['date_dt'] = pd.to_datetime(df['date']).dt.date
df['month']   = pd.to_datetime(df['date']).dt.month
df['moon_age'] = df['date_dt'].apply(moon_age)
df['full_moon'] = df['moon_age'].apply(is_full_moon)
df['new_moon']  = df['moon_age'].apply(is_new_moon)

# Only rows with opening H2H odds
df = df.dropna(subset=['h2h_home_open', 'h2h_away_open', 'home_win'])
df['h2h_home_open'] = pd.to_numeric(df['h2h_home_open'], errors='coerce')
df['h2h_away_open'] = pd.to_numeric(df['h2h_away_open'], errors='coerce')
df['home_win']      = pd.to_numeric(df['home_win'],       errors='coerce')
df = df.dropna(subset=['h2h_home_open', 'h2h_away_open', 'home_win'])

def roi(mask, team_is_home):
    sub = df[mask]
    if len(sub) < MIN_N:
        return None, len(sub)
    if team_is_home:
        r = (sub['home_win'] * sub['h2h_home_open'] - 1).mean()
    else:
        r = ((1 - sub['home_win']) * sub['h2h_away_open'] - 1).mean()
    return round(float(r), 3), len(sub)

def scan_team(team, opponent, game_date, is_home):
    """Return list of (angle_label, roi, n) for all matching angles."""
    month       = game_date.month
    team_rest   = rest(team, game_date)
    opp_rest    = rest(opponent, game_date)
    game_moon   = moon_age(game_date)
    game_full   = is_full_moon(game_moon)
    game_new    = is_new_moon(game_moon)

    # Base mask: team playing in the right role
    if is_home:
        base = (df['home_team'] == team)
    else:
        base = (df['away_team'] == team)

    angles = []

    def check(label, mask):
        r, n = roi(base & mask, is_home)
        if r is not None and r >= ROI_THRESHOLD:
            angles.append((label, r, n))

    # 1. vs this specific opponent
    if is_home:
        check(f'vs {opponent.split()[-1]} (H2H record)',
              df['away_team'] == opponent)
    else:
        check(f'vs {opponent.split()[-1]} (H2H record)',
              df['home_team'] == opponent)

    # 2. In this calendar month
    check(f'Games in month {month} ({datetime.date(2026, month, 1).strftime("%B")})',
          df['month'] == month)

    # 3. Full moon (only if this game IS a full moon)
    if game_full:
        check('Full moon games', df['full_moon'])

    # 4. New moon (only if this game IS a new moon)
    if game_new:
        check('New moon games', df['new_moon'])

    # 5. After 7+ days rest (only if team has 7+ days this week)
    if team_rest and team_rest >= 7:
        check(f'After 7+ days rest',
              df['home_rest_days'] >= 7 if is_home else df['away_rest_days'] >= 7)

    # 6. After 8+ days rest
    if team_rest and team_rest >= 8:
        check(f'After 8+ days rest',
              df['home_rest_days'] >= 8 if is_home else df['away_rest_days'] >= 8)

    # 7. Opponent on short rest (6 days or fewer) — only if opponent IS on short rest
    if opp_rest and opp_rest <= 6:
        check(f'Opp on 6d rest or less',
              df['away_rest_days'] <= 6 if is_home else df['home_rest_days'] <= 6)

    # 8. At home (home-ground advantage angle) — only if is_home
    if is_home:
        check('At home (all games)', pd.Series([True] * len(df), index=df.index))

    # 9. Month + home/away combo
    check(f'{"Home" if is_home else "Away"} in {datetime.date(2026, month, 1).strftime("%B")}',
          df['month'] == month)

    # 10. Full moon + home (only if full moon this week and team is home)
    if game_full and is_home:
        check('Full moon at home', df['full_moon'])

    # 11. Opponent on 6 days rest + full moon (intersection)
    if game_full and opp_rest and opp_rest <= 6:
        opp_short = df['away_rest_days'] <= 6 if is_home else df['home_rest_days'] <= 6
        check('Full moon + opp on short rest', df['full_moon'] & opp_short)

    # Sort by ROI desc, deduplicate by label
    seen = set()
    out = []
    for label, r, n in sorted(angles, key=lambda x: -x[1]):
        if label not in seen:
            seen.add(label)
            out.append((label, r, n))
    return out

# ── Scan all R8 games ─────────────────────────────────────────────────────
print()
print('=' * 80)
print('  AFL R8 2026 — H2H RESEARCH MATRIX')
print(f'  Historical angles matching this week\'s exact conditions')
print(f'  Min sample n={MIN_N}  |  ROI threshold={ROI_THRESHOLD:.0%}  |  Odds: opening H2H')
print('=' * 80)

triples = []

for home_team, away_team, game_date in FIXTURE:
    home_s = home_team.split()[-1]
    away_s = away_team.split()[-1]
    home_rest = rest(home_team, game_date)
    away_rest = rest(away_team, game_date)
    moon      = moon_age(game_date)
    phase     = 'FULL MOON' if is_full_moon(moon) else ('NEW MOON' if is_new_moon(moon) else f'age {moon:.1f}d')

    home_angles = scan_team(home_team, away_team, game_date, is_home=True)
    away_angles = scan_team(away_team, home_team, game_date, is_home=False)

    print(f'\n  {home_s} vs {away_s}  |  {game_date}  |  {phase}  |  rest: {home_s} {home_rest}d / {away_s} {away_rest}d')
    print(f'  {"─"*74}')

    def print_angles(team_s, angles, side):
        if not angles:
            print(f'    {team_s} ({side}): no 20%+ angles found')
            return
        for label, r, n in angles[:5]:
            marker = '  ***' if len(angles) >= 3 and angles.index((label, r, n)) < 3 else ''
            print(f'    {team_s} ({side}):  {label:<42}  ROI {r:+.1%}  n={n}{marker}')

    print_angles(home_s, home_angles, 'HOME')
    print_angles(away_s, away_angles, 'AWAY')

    for side, team_name, angles in [('HOME', home_s, home_angles), ('AWAY', away_s, away_angles)]:
        if len(angles) >= 3:
            triples.append((f'{home_s} vs {away_s}', team_name, side, game_date, angles[:3]))

print()
print('=' * 80)
print('  TRIPLE SIGNAL GAMES  (3+ angles each >= 20% ROI, all conditions match)')
print('=' * 80)
if triples:
    for game, team, side, gdate, angles in triples:
        print(f'\n  *** {game}  →  {team} ({side})')
        for i, (label, r, n) in enumerate(angles, 1):
            print(f'      #{i}  {label:<44}  ROI {r:+.1%}  (n={n})')
else:
    print('\n  No triple signals. Printing best doubles:')
    for home_team, away_team, game_date in FIXTURE:
        home_s = home_team.split()[-1]; away_s = away_team.split()[-1]
        for side, team_name, angles in [
            ('HOME', home_s, scan_team(home_team, away_team, game_date, True)),
            ('AWAY', away_s, scan_team(away_team, home_team, game_date, False)),
        ]:
            if len(angles) == 2:
                print(f'\n  ** {home_s} vs {away_s} — {team_name} ({side})')
                for label, r, n in angles:
                    print(f'     {label:<44}  ROI {r:+.1%}  n={n}')
print()
