#!/usr/bin/env python3
from __future__ import annotations

import argparse
import sqlite3
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
import yaml


ROOT = Path(__file__).resolve().parent.parent
DEFAULT_XLSX = Path.home() / "Downloads" / "afl (7).xlsx"
TEAMS_DOWN = ["Melbourne", "Fremantle", "Collingwood", "St Kilda"]
TEAMS_UP = ["West Coast", "North Melbourne", "Brisbane", "Sydney", "Gold Coast"]


def main() -> None:
    parser = argparse.ArgumentParser(description="Persist AFL market-intelligence movement profiles.")
    parser.add_argument("--xlsx", type=Path, default=DEFAULT_XLSX)
    parser.add_argument("--settings", default="config/settings.yaml")
    args = parser.parse_args()

    settings = yaml.safe_load(open(ROOT / args.settings))
    conn = sqlite3.connect(ROOT / settings["database"]["path"])
    conn.row_factory = sqlite3.Row

    rows = build_profiles(args.xlsx)
    for row in rows:
        upsert_profile(conn, row)
    conn.commit()
    conn.close()
    print(f"Saved {len(rows)} AFL market-intel profiles.")


def load_games(path: Path) -> pd.DataFrame:
    df = pd.read_excel(path, sheet_name="Data", header=None)
    rows = []
    for _, raw in df.iterrows():
        d = raw.iloc[0]
        if not hasattr(d, "year"):
            continue
        home = str(raw.iloc[2])
        away = str(raw.iloc[3])
        hs = raw.iloc[5]
        aw = raw.iloc[6]
        total_open = raw.iloc[39] if pd.notna(raw.iloc[39]) else None
        total_close = raw.iloc[42] if pd.notna(raw.iloc[42]) else None
        over_odds = raw.iloc[46] if len(raw) > 46 else None
        under_odds = raw.iloc[50] if len(raw) > 50 else None
        h2h_home_open = raw.iloc[15] if len(raw) > 15 else None
        h2h_home_close = raw.iloc[18] if len(raw) > 18 else None
        h2h_away_open = raw.iloc[19] if len(raw) > 19 else None
        h2h_away_close = raw.iloc[22] if len(raw) > 22 else None
        rows.append(
            {
                "date": pd.Timestamp(d),
                "season": pd.Timestamp(d).year,
                "home": home,
                "away": away,
                "home_score": pd.to_numeric(hs, errors="coerce"),
                "away_score": pd.to_numeric(aw, errors="coerce"),
                "total_open": pd.to_numeric(total_open, errors="coerce"),
                "total_close": pd.to_numeric(total_close, errors="coerce"),
                "over_odds": pd.to_numeric(over_odds, errors="coerce"),
                "under_odds": pd.to_numeric(under_odds, errors="coerce"),
                "h2h_home_open": pd.to_numeric(h2h_home_open, errors="coerce"),
                "h2h_home_close": pd.to_numeric(h2h_home_close, errors="coerce"),
                "h2h_away_open": pd.to_numeric(h2h_away_open, errors="coerce"),
                "h2h_away_close": pd.to_numeric(h2h_away_close, errors="coerce"),
            }
        )
    return pd.DataFrame(rows)


def build_profiles(path: Path) -> list[dict]:
    games = load_games(path)
    profiles = []
    profiles.extend(total_profiles(games, path, TEAMS_DOWN, "drift_down", "under"))
    profiles.extend(total_profiles(games, path, TEAMS_UP, "drift_up", "over"))
    profiles.extend(h2h_firm_profiles(games, path))
    return profiles


def total_profiles(games: pd.DataFrame, path: Path, teams: list[str], direction: str, selection: str) -> list[dict]:
    rows = []
    for team in teams:
        for era, mask in eras(games).items():
            sample = games[mask].dropna(subset=["home_score", "away_score", "total_open", "total_close"])
            if direction == "drift_down":
                sample = sample[sample["total_close"] < sample["total_open"]].dropna(subset=["under_odds"])
            else:
                sample = sample[sample["total_close"] > sample["total_open"]].dropna(subset=["over_odds"])
            sample = sample[(sample["home"] == team) | (sample["away"] == team)]
            if sample.empty:
                continue
            actual_total = sample["home_score"] + sample["away_score"]
            if selection == "under":
                wins = actual_total < sample["total_close"]
                odds = sample["under_odds"]
            else:
                wins = actual_total > sample["total_close"]
                odds = sample["over_odds"]
            pushes = actual_total == sample["total_close"]
            profit = (wins * (odds - 1) + (~wins & ~pushes) * -1).sum()
            rows.append(profile_row("AFL", "total", f"{team} total {direction}", team, era, direction, selection, sample, wins, pushes, odds, profit, path, (sample["total_close"] - sample["total_open"]).mean()))
    return rows


def h2h_firm_profiles(games: pd.DataFrame, path: Path) -> list[dict]:
    records = []
    for _, g in games.dropna(subset=["home_score", "away_score"]).iterrows():
        home_win = g["home_score"] > g["away_score"]
        for side in ("home", "away"):
            team = g[side]
            op = g[f"h2h_{side}_open"]
            cl = g[f"h2h_{side}_close"]
            if pd.isna(op) or pd.isna(cl) or op <= 1 or cl <= 1 or cl >= op:
                continue
            won = home_win if side == "home" else not home_win
            records.append({"date": g["date"], "season": g["season"], "team": team, "close": cl, "won": won, "move": (1 / cl) - (1 / op)})
    df = pd.DataFrame(records)
    rows = []
    for team, team_df in df.groupby("team"):
        for era, mask in eras(team_df).items():
            sample = team_df[mask]
            if sample.empty:
                continue
            wins = sample["won"]
            pushes = pd.Series([False] * len(sample), index=sample.index)
            odds = sample["close"]
            profit = (wins * (odds - 1) + (~wins) * -1).sum()
            rows.append(profile_row("AFL", "h2h", f"{team} H2H firm", team, era, "firm", "team", sample, wins, pushes, odds, profit, path, sample["move"].mean() * 100))
    return rows


def eras(df: pd.DataFrame) -> dict[str, pd.Series]:
    return {
        "pre_recent_2013_2021": df["season"] < 2022,
        "recent_2022_plus": df["season"] >= 2022,
        "all_available": df["season"] >= 0,
    }


def profile_row(sport, market_type, profile_name, team, era, direction, selection, sample, wins, pushes, odds, profit, path, avg_move):
    bets = len(sample)
    win_count = int(wins.sum())
    push_count = int(pushes.sum())
    losses = bets - win_count - push_count
    hit_rate = win_count / bets
    avg_odds = float(odds.mean())
    breakeven = float((1 / odds).mean())
    return {
        "sport": sport,
        "market_type": market_type,
        "profile_name": profile_name,
        "team_name": team,
        "era": era,
        "move_direction": direction,
        "bet_selection": selection,
        "sample_start": str(sample["date"].min().date()),
        "sample_end": str(sample["date"].max().date()),
        "bets": bets,
        "wins": win_count,
        "losses": losses,
        "pushes": push_count,
        "hit_rate": hit_rate,
        "avg_odds": avg_odds,
        "breakeven_rate": breakeven,
        "edge_pp": (hit_rate - breakeven) * 100,
        "profit_1u": float(profit),
        "roi": float(profit / bets),
        "avg_move": float(avg_move),
        "notes": "Generated from open-to-close AFL market movement research.",
        "source_file": str(path),
        "calculated_at": datetime.now(timezone.utc).isoformat(),
    }


def upsert_profile(conn: sqlite3.Connection, row: dict) -> None:
    cols = list(row.keys())
    placeholders = ",".join("?" for _ in cols)
    updates = ",".join(f"{c}=excluded.{c}" for c in cols if c != "profile_id")
    conn.execute(
        f"""
        INSERT INTO market_intel_profiles ({",".join(cols)})
        VALUES ({placeholders})
        ON CONFLICT(sport, market_type, profile_name, team_name, era, move_direction, bet_selection)
        DO UPDATE SET {updates}
        """,
        [row[c] for c in cols],
    )


if __name__ == "__main__":
    main()

