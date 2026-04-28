#!/usr/bin/env python3
"""
ml/afl/game_log.py

AFL feature engineering pipeline.
Parses OddsPortal AFL xlsx, builds ELO walk-forward,
computes rest/travel/form/venue features, outputs a flat CSV
ready for model training.

OUTPUT: ml/afl/results/features_afl.csv

SPLIT:
    season <= 2023  →  split = 'train'
    season == 2024  →  split = 'validate'
    season == 2025  →  split = 'test'
    season >= 2026  →  split = 'deploy'  (no targets)

USAGE
-----
    python3 ml/afl/game_log.py
    python3 ml/afl/game_log.py --xlsx /path/to/afl.xlsx
"""

import argparse
import csv
import math
from datetime import datetime, timedelta
from pathlib import Path

import openpyxl

# ---------------------------------------------------------------------------
# Paths
# ---------------------------------------------------------------------------
ROOT    = Path(__file__).resolve().parent.parent.parent
XLSX    = Path.home() / 'Downloads' / 'afl (2) (1).xlsx'
OUT_CSV = ROOT / 'ml' / 'afl' / 'results' / 'features_afl.csv'

# ---------------------------------------------------------------------------
# Team name mapping  (OddsPortal short → canonical)
# ---------------------------------------------------------------------------
TEAM_MAP = {
    'Adelaide':         'Adelaide Crows',
    'Brisbane':         'Brisbane Lions',
    'Carlton':          'Carlton Blues',
    'Collingwood':      'Collingwood Magpies',
    'Essendon':         'Essendon Bombers',
    'Fremantle':        'Fremantle Dockers',
    'GWS Giants':       'Greater Western Sydney Giants',
    'Geelong':          'Geelong Cats',
    'Gold Coast':       'Gold Coast Suns',
    'Hawthorn':         'Hawthorn Hawks',
    'Melbourne':        'Melbourne Demons',
    'North Melbourne':  'North Melbourne Kangaroos',
    'Port Adelaide':    'Port Adelaide Power',
    'Richmond':         'Richmond Tigers',
    'St Kilda':         'St Kilda Saints',
    'Sydney':           'Sydney Swans',
    'West Coast':       'West Coast Eagles',
    'Western Bulldogs': 'Western Bulldogs',
}

# ---------------------------------------------------------------------------
# Team home-base lat/lng  (from seed_afl_teams.py)
# ---------------------------------------------------------------------------
HOME_BASE = {
    'Adelaide Crows':               (-34.9285, 138.6007),
    'Brisbane Lions':               (-27.4698, 153.0251),
    'Carlton Blues':                (-37.8136, 144.9631),
    'Collingwood Magpies':          (-37.8136, 144.9631),
    'Essendon Bombers':             (-37.8136, 144.9631),
    'Fremantle Dockers':            (-31.9505, 115.8605),
    'Greater Western Sydney Giants':(-33.8688, 151.2093),
    'Geelong Cats':                 (-38.1499, 144.3617),
    'Gold Coast Suns':              (-28.0167, 153.4000),
    'Hawthorn Hawks':               (-37.8136, 144.9631),
    'Melbourne Demons':             (-37.8136, 144.9631),
    'North Melbourne Kangaroos':    (-37.8136, 144.9631),
    'Port Adelaide Power':          (-34.9285, 138.6007),
    'Richmond Tigers':              (-37.8136, 144.9631),
    'St Kilda Saints':              (-37.8136, 144.9631),
    'Sydney Swans':                 (-33.8688, 151.2093),
    'West Coast Eagles':            (-31.9505, 115.8605),
    'Western Bulldogs':             (-37.8136, 144.9631),
}

# ---------------------------------------------------------------------------
# Venue lat/lng  (all venues seen in OddsPortal data)
# ---------------------------------------------------------------------------
VENUE_COORDS = {
    'MCG':                    (-37.8200, 144.9834),
    'Marvel Stadium':         (-37.8165, 144.9476),
    'Marvl':                  (-37.8165, 144.9476),   # typo in source data
    'Adelaide Oval':          (-34.9158, 138.5963),
    'AAMI Stadium':           (-34.8898, 138.5009),   # old West Lakes/AAMI
    'Optus Stadium':          (-31.9510, 115.8883),
    'Domain Stadium':         (-31.9510, 115.8350),   # old Subiaco Oval
    'GMHBA Stadium':          (-38.1554, 144.3550),
    'Gabba':                  (-27.4858, 153.0381),
    'ENGIE Stadium':          (-33.8474, 151.0046),   # GWS home
    'Accor Stadium':          (-33.8469, 151.0637),   # Stadium Australia, Homebush
    'SCG':                    (-33.8914, 151.2246),
    'People First Stadium':   (-28.0034, 153.3946),
    'UTAS Stadium':           (-41.4305, 147.1386),
    'Blundestone Arena':      (-42.8821, 147.3272),
    'Norwood Oval':           (-34.9212, 138.6280),
    'Traeger Park':           (-23.6980, 133.8807),
    'TIO Traeger Park':       (-23.6980, 133.8807),
    'TIO Stadium':            (-12.4500, 130.9000),   # Darwin
    'Mars Stadium':           (-37.5472, 143.8405),   # Ballarat
    'Cazaly\'s Stadium':      (-16.9186, 145.7781),   # Cairns
    'Manuka Oval':            (-35.3196, 149.1400),   # Canberra
    'Barossa Park':           (-34.5368, 138.9745),   # Tanunda SA
    'Adelaide Hills':         (-34.9285, 138.6007),   # approximate — same as Adelaide
    'Hands Oval':             (-34.1707, 140.7487),   # Renmark SA
    'Blacktown Park':         (-33.7688, 150.9078),   # Sydney west
    'Riverway Stadium':       (-19.2590, 146.8130),   # Townsville
    'Westpac Stadium':        (-41.2765, 174.7862),   # Wellington NZ
    'Ninja Stadium':          (-27.4858, 153.0381),   # Gabba rename — treat as Brisbane
    'Jiangwan Sports Centre': ( 31.3244, 121.5054),   # Shanghai China (rare)
}

# ---------------------------------------------------------------------------
# ELO config (AFL-calibrated — The Arc / lazappi parameters)
# ---------------------------------------------------------------------------
ELO_BASE          = 1500.0
ELO_K_REGULAR     = 62.0     # standard AFL regular season K (The Arc / lazappi)
ELO_K_FINALS      = 72.0     # finals K — higher stakes, ratings update more
ELO_K_EARLY       = 82.0     # first 4 rounds of each season — off-season uncertainty
POINTS_PER_ELO    = 0.13     # 100 ELO pts → ~13 pt margin
ELO_MEAN_REVERT   = 0.25     # season-start reversion toward 1500 (25% pull-back)
HOME_ADV_ELO      = 65.0     # home advantage in ELO pts (8.5 pts / 0.13 ≈ 65); The Arc ≈ 72

# ---------------------------------------------------------------------------
# Form config
# ---------------------------------------------------------------------------
FORM_GAMES       = 5         # look-back window
BLOWOUT_PTS      = 40        # AFL blowout threshold

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------

def haversine_km(lat1, lng1, lat2, lng2) -> float:
    """Great-circle distance in km between two lat/lng pairs."""
    R = 6371.0
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi  = math.radians(lat2 - lat1)
    dlam  = math.radians(lng2 - lng1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlam / 2) ** 2
    return R * 2 * math.asin(math.sqrt(a))


def travel_km(team: str, venue: str) -> float:
    """Distance team travels to reach venue, 0 if home venue."""
    home_lat, home_lng = HOME_BASE.get(team, (None, None))
    if home_lat is None:
        return 0.0
    coords = VENUE_COORDS.get(venue)
    if coords is None:
        return 0.0
    return haversine_km(home_lat, home_lng, coords[0], coords[1])


def elo_expected_win(home_elo: float, away_elo: float) -> float:
    """Expected home win probability given ELO ratings (includes home field advantage)."""
    diff = (home_elo + HOME_ADV_ELO) - away_elo
    return 1.0 / (1.0 + 10 ** (-diff / 400.0))


def get_k(season_game_num: int, is_final: bool) -> float:
    """
    Return K-factor for this game.
    - Finals:        K=72  (higher stakes)
    - Rounds 1-4:    K=82  (early season uncertainty, off-season changes)
    - Rounds 5+:     K=62  (standard AFL regular season)
    season_game_num = number of games played by this team in the current season
    before this match (0-indexed, so 0 = first game of season).
    """
    if is_final:
        return ELO_K_FINALS
    if season_game_num < 4:
        return ELO_K_EARLY
    return ELO_K_REGULAR


def update_elo(home_elo: float, away_elo: float,
               home_score: int, away_score: int,
               home_season_games: int, away_season_games: int,
               is_final: bool = False) -> tuple:
    """Return (new_home_elo, new_away_elo) after one game."""
    expected = elo_expected_win(home_elo, away_elo)
    margin   = home_score - away_score

    # outcome from home team perspective: 1=win, 0.5=draw, 0=loss
    if margin > 0:
        outcome = 1.0
    elif margin < 0:
        outcome = 0.0
    else:
        outcome = 0.5

    # Margin multiplier — larger margin = bigger ELO swing (capped at 1.5×)
    # AFL median margin ~30 pts; normalise on that
    margin_factor = min(abs(margin) / 30.0, 1.5)

    # Use average of home/away K (they may be in different season-game positions)
    k = (get_k(home_season_games, is_final) + get_k(away_season_games, is_final)) / 2.0

    delta = k * margin_factor * (outcome - expected)
    return home_elo + delta, away_elo - delta


def _safe(val, default=None):
    """Return val if not None and not empty string, else default."""
    if val is None or val == '':
        return default
    return val


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

def load_rows(xlsx_path: Path) -> list:
    """Load all data rows from xlsx, sorted oldest-first."""
    wb   = openpyxl.load_workbook(xlsx_path, read_only=True, data_only=True)
    ws   = wb.active
    rows = list(ws.iter_rows(values_only=True))
    # row 0 = freeform header, row 1 = column names, rows 2+ = data
    data = []
    for r in rows[2:]:
        date_val = r[0]
        if not date_val or not isinstance(date_val, datetime):
            continue
        data.append(r)
    # sort ascending by date, then kick-off time
    data.sort(key=lambda r: (r[0], r[1] or datetime.min.time()))
    return data


def build_features(xlsx_path: Path) -> list[dict]:
    """Parse xlsx, walk-forward, return list of feature dicts."""
    rows = load_rows(xlsx_path)
    print(f'Loaded {len(rows)} games from {xlsx_path.name}')

    # State: ELO, last game date, form buffer, last active season
    elo:          dict[str, float]       = {}
    last_date:    dict[str, datetime]    = {}
    last_season:  dict[str, int]         = {}    # for season-start mean reversion
    season_games: dict[str, int]         = {}    # team → games played in current season (for K selection)
    form:         dict[str, list[dict]]  = {}    # team → list of recent game results

    # Venue accumulators for venue-level features
    venue_totals:   dict[str, list[int]] = {}    # venue → list of combined scores
    venue_results:  dict[str, list[int]] = {}    # venue → list of 1 (home win) / 0

    records = []

    for idx, r in enumerate(rows):
        date:        datetime = r[0]
        home_op:     str      = r[2]
        away_op:     str      = r[3]
        venue_name:  str      = r[4] or ''
        home_score:  int      = r[5]
        away_score:  int      = r[6]
        is_final:    bool     = bool(r[7])

        # map team names
        home = TEAM_MAP.get(home_op, home_op)
        away = TEAM_MAP.get(away_op, away_op)
        season = date.year

        # ── ELO pre-match (with season-start mean reversion) ─────────────
        for team in (home, away):
            if last_season.get(team, season) < season:
                # new season: pull ELO 25% back toward 1500 and reset season game count
                prev = elo.get(team, ELO_BASE)
                elo[team] = prev + ELO_MEAN_REVERT * (ELO_BASE - prev)
                season_games[team] = 0

        home_elo_pre = elo.get(home, ELO_BASE)
        away_elo_pre = elo.get(away, ELO_BASE)
        elo_diff     = home_elo_pre - away_elo_pre
        elo_win_prob = elo_expected_win(home_elo_pre, away_elo_pre)

        # ── Rest days ────────────────────────────────────────────────────
        def rest_days(team: str) -> int:
            last = last_date.get(team)
            if last is None:
                return 21   # no prior game → treat as long rest
            delta = (date - last).days
            return min(delta, 21)   # cap at 21

        home_rest = rest_days(home)
        away_rest = rest_days(away)
        rest_diff = home_rest - away_rest

        # ── Travel ───────────────────────────────────────────────────────
        home_travel = travel_km(home, venue_name)
        away_travel = travel_km(away, venue_name)
        travel_diff = home_travel - away_travel  # negative = home travels more

        # ── Form (last FORM_GAMES) ────────────────────────────────────────
        def get_form(team: str) -> dict:
            games = form.get(team, [])[-FORM_GAMES:]
            if not games:
                return {'win_pct': 0.5, 'avg_margin': 0.0, 'last_margin': 0.0,
                        'form_games': 0, 'off_big_win': 0, 'off_big_loss': 0,
                        'win_streak': 0, 'loss_streak': 0}
            wins      = sum(g['win'] for g in games)
            margins   = [g['margin'] for g in games]
            last_g    = games[-1]
            # streak
            wstreak   = 0
            lstreak   = 0
            for g in reversed(games):
                if g['win']:
                    if lstreak == 0:
                        wstreak += 1
                    else:
                        break
                else:
                    if wstreak == 0:
                        lstreak += 1
                    else:
                        break
            return {
                'win_pct':     wins / len(games),
                'avg_margin':  sum(margins) / len(margins),
                'last_margin': last_g['margin'],
                'form_games':  len(games),
                'off_big_win': 1 if last_g['margin'] >= BLOWOUT_PTS else 0,
                'off_big_loss': 1 if last_g['margin'] <= -BLOWOUT_PTS else 0,
                'win_streak':  wstreak,
                'loss_streak': lstreak,
            }

        home_form = get_form(home)
        away_form = get_form(away)

        # ── Venue features (pre-game stats from prior games at venue) ─────
        venue_tot_list = venue_totals.get(venue_name, [])
        venue_res_list = venue_results.get(venue_name, [])
        venue_avg_total    = (sum(venue_tot_list) / len(venue_tot_list)) if venue_tot_list else None
        venue_home_win_pct = (sum(venue_res_list) / len(venue_res_list)) if venue_res_list else None
        venue_games        = len(venue_tot_list)

        # ── Market data (from OddsPortal) ────────────────────────────────
        # H2H
        h2h_home_open  = _safe(r[15])
        h2h_away_open  = _safe(r[19])
        h2h_home_close = _safe(r[18])
        h2h_away_close = _safe(r[22])
        # market implied home prob (opening)
        if h2h_home_open and h2h_away_open:
            raw_home_prob = 1.0 / h2h_home_open
            raw_away_prob = 1.0 / h2h_away_open
            margin_sum    = raw_home_prob + raw_away_prob
            mkt_home_prob_open = raw_home_prob / margin_sum
        else:
            mkt_home_prob_open = None

        # Handicap (home line = number of points home gives away)
        home_line_open  = _safe(r[23])   # e.g. -6.5 means home favoured by 6.5
        home_line_close = _safe(r[26])
        total_open      = _safe(r[39])
        total_close     = _safe(r[42])

        # ── Targets ──────────────────────────────────────────────────────
        has_result  = (home_score is not None and away_score is not None)
        home_margin = (home_score - away_score) if has_result else None
        total_score = (home_score + away_score) if has_result else None
        home_win    = (1 if home_margin > 0 else 0) if has_result else None

        # ── Build record ──────────────────────────────────────────────────
        rec = {
            # Identifiers
            'season':           season,
            'date':             date.strftime('%Y-%m-%d'),
            'home_team':        home,
            'away_team':        away,
            'venue':            venue_name,
            'is_final':         int(is_final),
            'split':            ('train'    if season <= 2023
                                 else 'validate' if season == 2024
                                 else 'test'     if season == 2025
                                 else 'deploy'),

            # ELO
            'home_elo':         round(home_elo_pre, 2),
            'away_elo':         round(away_elo_pre, 2),
            'elo_diff':         round(elo_diff, 2),
            'elo_win_prob':     round(elo_win_prob, 4),

            # Rest
            'home_rest_days':   home_rest,
            'away_rest_days':   away_rest,
            'rest_diff':        rest_diff,

            # Travel
            'home_travel_km':   round(home_travel, 1),
            'away_travel_km':   round(away_travel, 1),
            'travel_diff_km':   round(travel_diff, 1),

            # Home form
            'home_win_pct':           round(home_form['win_pct'], 3),
            'home_avg_margin':        round(home_form['avg_margin'], 2),
            'home_last_margin':       home_form['last_margin'],
            'home_form_games':        home_form['form_games'],
            'home_off_big_win':       home_form['off_big_win'],
            'home_off_big_loss':      home_form['off_big_loss'],
            'home_win_streak':        home_form['win_streak'],
            'home_loss_streak':       home_form['loss_streak'],

            # Away form
            'away_win_pct':           round(away_form['win_pct'], 3),
            'away_avg_margin':        round(away_form['avg_margin'], 2),
            'away_last_margin':       away_form['last_margin'],
            'away_form_games':        away_form['form_games'],
            'away_off_big_win':       away_form['off_big_win'],
            'away_off_big_loss':      away_form['off_big_loss'],
            'away_win_streak':        away_form['win_streak'],
            'away_loss_streak':       away_form['loss_streak'],

            # Form differentials
            'form_win_pct_diff':     round(home_form['win_pct'] - away_form['win_pct'], 3),
            'form_margin_diff':      round(home_form['avg_margin'] - away_form['avg_margin'], 2),

            # Venue
            'venue_games':           venue_games,
            'venue_avg_total':       round(venue_avg_total, 1) if venue_avg_total else '',
            'venue_home_win_pct':    round(venue_home_win_pct, 3) if venue_home_win_pct else '',

            # Market data
            'h2h_home_open':         h2h_home_open   if h2h_home_open  else '',
            'h2h_away_open':         h2h_away_open   if h2h_away_open  else '',
            'h2h_home_close':        h2h_home_close  if h2h_home_close else '',
            'h2h_away_close':        h2h_away_close  if h2h_away_close else '',
            'mkt_home_prob_open':    round(mkt_home_prob_open, 4) if mkt_home_prob_open else '',
            'home_line_open':        home_line_open  if home_line_open  is not None else '',
            'home_line_close':       home_line_close if home_line_close is not None else '',
            'total_open':            total_open      if total_open  is not None else '',
            'total_close':           total_close     if total_close is not None else '',

            # Targets
            'home_score':    home_score if has_result else '',
            'away_score':    away_score if has_result else '',
            'home_margin':   home_margin if has_result else '',
            'total_score':   total_score if has_result else '',
            'home_win':      home_win    if has_result else '',
        }

        records.append(rec)

        # ── Update state (only if result exists) ──────────────────────────
        if has_result:
            home_sg = season_games.get(home, 0)
            away_sg = season_games.get(away, 0)
            new_home_elo, new_away_elo = update_elo(
                home_elo_pre, away_elo_pre, home_score, away_score,
                home_sg, away_sg, is_final=is_final)
            elo[home] = new_home_elo
            elo[away] = new_away_elo

            season_games[home] = home_sg + 1
            season_games[away] = away_sg + 1

            last_date[home]   = date
            last_date[away]   = date
            last_season[home] = season
            last_season[away] = season

            # update form buffers
            form.setdefault(home, []).append({
                'win':    home_margin > 0,
                'margin': home_margin,
            })
            form.setdefault(away, []).append({
                'win':    away_score > home_score,
                'margin': away_score - home_score,
            })

            # update venue accumulators
            venue_totals.setdefault(venue_name, []).append(total_score)
            venue_results.setdefault(venue_name, []).append(1 if home_margin > 0 else 0)

    return records


def save_csv(records: list[dict], out: Path):
    out.parent.mkdir(parents=True, exist_ok=True)
    if not records:
        print('No records to save.')
        return
    fieldnames = list(records[0].keys())
    with open(out, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(records)
    print(f'Saved {len(records)} rows → {out}')


def print_summary(records: list[dict]):
    from collections import Counter
    splits = Counter(r['split'] for r in records)
    seasons = Counter(r['season'] for r in records)
    print()
    print('=== Feature Summary ===')
    print(f'Total games: {len(records)}')
    print(f'Splits: {dict(splits)}')
    print()
    print('Games per season:')
    for yr in sorted(seasons):
        print(f'  {yr}: {seasons[yr]}')

    # spot-check ELO range
    elos = [r['home_elo'] for r in records] + [r['away_elo'] for r in records]
    print(f'\nELO range: {min(elos):.0f} – {max(elos):.0f}')

    # feature completeness
    records_with_result = [r for r in records if r['home_margin'] != '']
    print(f'Games with result: {len(records_with_result)}')

    records_with_odds = [r for r in records if r['h2h_home_open'] != '']
    print(f'Games with H2H open odds: {len(records_with_odds)}')

    records_with_line = [r for r in records if r['home_line_open'] != '']
    print(f'Games with handicap line: {len(records_with_line)}')

    records_with_total = [r for r in records if r['total_open'] != '']
    print(f'Games with total line: {len(records_with_total)}')

    # sample ELO top/bottom teams at end
    print()
    print('Sample final ELO snapshot (all teams from last game in each):')
    final_elos: dict[str, float] = {}
    for r in records:
        if r['home_margin'] != '':
            # ELO shown is pre-game; we can't recover post-game easily from CSV
            # Just show the most recent pre-game ELO as approximation
            final_elos[r['home_team']] = r['home_elo']
            final_elos[r['away_team']] = r['away_elo']
    for team, rating in sorted(final_elos.items(), key=lambda x: -x[1]):
        print(f'  {team:<35} {rating:.0f}')


def main():
    parser = argparse.ArgumentParser(description='AFL feature engineering pipeline')
    parser.add_argument('--xlsx', default=str(XLSX), help='Path to OddsPortal AFL xlsx')
    parser.add_argument('--out',  default=str(OUT_CSV), help='Output CSV path')
    args = parser.parse_args()

    xlsx_path = Path(args.xlsx)
    out_path  = Path(args.out)

    if not xlsx_path.exists():
        print(f'ERROR: xlsx not found: {xlsx_path}')
        return

    records = build_features(xlsx_path)
    save_csv(records, out_path)
    print_summary(records)


if __name__ == '__main__':
    main()
