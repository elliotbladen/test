"""
Track odds movements between the latest two intraday snapshot times.

Reads:
  data/odds_snapshots/YYYY/YYYY-MM-DD.csv

Writes:
  data/odds_movements/YYYY/YYYY-MM-DD.csv
  data/odds_movements/latest.csv
"""

from __future__ import annotations

import argparse
import csv
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SNAP_DIR = ROOT / "data" / "odds_snapshots"
MOVE_DIR = ROOT / "data" / "odds_movements"

FIELDNAMES = [
    "detected_date",
    "detected_time",
    "from_snapshot_time",
    "to_snapshot_time",
    "sport",
    "game_id",
    "home_team",
    "away_team",
    "commence_time",
    "bookmaker",
    "market",
    "outcome",
    "point",
    "old_price",
    "new_price",
    "change",
    "change_pct",
    "direction",
]


def movement_key(row: dict[str, str]) -> tuple[str, ...]:
    return (
        row["to_snapshot_time"],
        row["sport"],
        row["game_id"],
        row["bookmaker"],
        row["market"],
        row["outcome"],
        row.get("point", ""),
    )


def price_key(row: dict[str, str]) -> tuple[str, ...]:
    return (
        row["sport"],
        row["game_id"],
        row["bookmaker"],
        row["market"],
        row["outcome"],
        row.get("point", ""),
    )


def read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as fh:
        return list(csv.DictReader(fh))


def write_rows(path: Path, rows: list[dict[str, str]], append: bool) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    mode = "a" if append and path.exists() else "w"
    with path.open(mode, newline="", encoding="utf-8") as fh:
        writer = csv.DictWriter(fh, fieldnames=FIELDNAMES)
        if mode == "w":
            writer.writeheader()
        writer.writerows(rows)


def existing_keys(path: Path) -> set[tuple[str, ...]]:
    if not path.exists():
        return set()
    return {movement_key(row) for row in read_rows(path)}


def latest_two_times(rows: list[dict[str, str]]) -> tuple[str, str] | None:
    times = sorted({row["snapshot_time"] for row in rows if row.get("snapshot_time")})
    if len(times) < 2:
        return None
    return times[-2], times[-1]


def detect_movements(
    snapshot_rows: list[dict[str, str]],
    from_time: str,
    to_time: str,
    min_pct: float,
) -> list[dict[str, str]]:
    old_rows = {
        price_key(row): row
        for row in snapshot_rows
        if row.get("snapshot_time") == from_time and row.get("price")
    }
    new_rows = [
        row
        for row in snapshot_rows
        if row.get("snapshot_time") == to_time and row.get("price")
    ]

    now = datetime.now(timezone.utc)
    detected_date = now.strftime("%Y-%m-%d")
    detected_time = now.strftime("%H:%M:%S")
    movements: list[dict[str, str]] = []

    for new in new_rows:
        old = old_rows.get(price_key(new))
        if not old:
            continue

        old_price = float(old["price"])
        new_price = float(new["price"])
        if old_price <= 0 or old_price == new_price:
            continue

        change = new_price - old_price
        change_pct = (change / old_price) * 100
        if abs(change_pct) < min_pct:
            continue

        movements.append(
            {
                "detected_date": detected_date,
                "detected_time": detected_time,
                "from_snapshot_time": from_time,
                "to_snapshot_time": to_time,
                "sport": new["sport"],
                "game_id": new["game_id"],
                "home_team": new["home_team"],
                "away_team": new["away_team"],
                "commence_time": new["commence_time"],
                "bookmaker": new["bookmaker"],
                "market": new["market"],
                "outcome": new["outcome"],
                "point": new.get("point", ""),
                "old_price": f"{old_price:.4f}",
                "new_price": f"{new_price:.4f}",
                "change": f"{change:.4f}",
                "change_pct": f"{change_pct:.2f}",
                "direction": "up" if change > 0 else "down",
            }
        )

    return sorted(movements, key=lambda row: abs(float(row["change_pct"])), reverse=True)


def main() -> None:
    parser = argparse.ArgumentParser(description="Track odds movements between snapshot pulls.")
    parser.add_argument("--date", default=None, help="Snapshot date YYYY-MM-DD. Default: today UTC.")
    parser.add_argument("--min-pct", type=float, default=0.0, help="Only write changes at/above this percent.")
    args = parser.parse_args()

    target_date = args.date or datetime.now(timezone.utc).strftime("%Y-%m-%d")
    year = target_date[:4]
    snapshot_path = SNAP_DIR / year / f"{target_date}.csv"
    movement_path = MOVE_DIR / year / f"{target_date}.csv"
    latest_path = MOVE_DIR / "latest.csv"

    if not snapshot_path.exists():
        print(f"No snapshot file found: {snapshot_path}")
        return

    snapshot_rows = read_rows(snapshot_path)
    times = latest_two_times(snapshot_rows)
    if not times:
        print(f"Need at least two snapshot times in {snapshot_path}; found fewer than two.")
        return

    from_time, to_time = times
    movements = detect_movements(snapshot_rows, from_time, to_time, args.min_pct)
    seen = existing_keys(movement_path)
    new_movements = [row for row in movements if movement_key(row) not in seen]

    write_rows(movement_path, new_movements, append=True)
    write_rows(latest_path, movements, append=False)

    print(f"Compared {from_time} -> {to_time}")
    print(f"Detected movements: {len(movements)}")
    print(f"New movement rows written: {len(new_movements)}")
    print(f"Wrote {movement_path}")
    print(f"Updated {latest_path}")


if __name__ == "__main__":
    main()
