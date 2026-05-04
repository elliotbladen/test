# Betmate Round Import

This adapter keeps Betmate as the data collector and keeps the pricing engine math unchanged.

## Flow

```text
Betmate round folder
  -> betmate_ingest adapter
  -> data/import/betmate/r<round>_<season>/ staging audit
  -> data/import/injuries_r<round>.json
  -> data/import/referees_r<round>.csv
  -> data/import/emotional_r<round>.json
  -> existing loaders and scripts/prepare_round.py
```

## Commands

Stage Betmate data only:

```bash
python scripts/betmate_import_round.py \
  --season 2026 \
  --round 11 \
  --betmate-root /path/to/betmate/exports
```

Stage Betmate data and run pricing:

```bash
python scripts/price_from_betmate.py \
  --season 2026 \
  --round 11 \
  --betmate-root /path/to/betmate/exports \
  --skip-weather
```

Automatic current/next round pricing:

```bash
python scripts/betmate_auto_price.py
```

This reads `config/betmate_automation.yaml`, infers the current/next NRL round from the `matches` table, then calls `scripts/price_from_betmate.py`.

Use `--round-dir` instead of `--betmate-root` when you already know the exact round folder.

Use `--dry-run` to generate files and run existing loaders/pricing without DB writes.

Use `--strict` to stop before pricing if validation reports errors.

`price_from_betmate.py` also runs a freshness preflight before it imports or prices. Use `--skip-preflight` only when intentionally overriding stale-data protection.

## Monday Automation

1. Set the Betmate export root:

```yaml
# config/betmate_automation.yaml
betmate:
  root: "/path/to/betmate/exports"
```

You can also leave the config blank and provide `BETMATE_ROOT` in the environment.

2. Test the automatic runner:

```bash
python scripts/betmate_auto_price.py --dry-run
```

3. Install the macOS LaunchAgent for Monday 7:03pm:

```bash
python scripts/install_betmate_launchd.py --load
```

The LaunchAgent runs:

```text
scripts/betmate_auto_price.py --config config/betmate_automation.yaml
```

Before pricing, the scheduled runner checks:

- Betmate manifests exist for injuries/suspensions, referees, emotional flags, and historical odds.
- Betmate files are within the max ages in `config/betmate_automation.yaml`.
- Referees are for the target engine round when `require_target_round.referees` is true.
- Previous round results are final in the engine DB.
- `team_stats` and `team_stats.elo_rating` exist for the target round's expected `as_of_date`.

If any required check fails, pricing is not run. The program prints exactly what is stale or missing and writes a JSON report:

```text
logs/betmate/preflight_r<round>_<season>.json
```

Logs are written to:

```text
logs/betmate/launchd.out.log
logs/betmate/launchd.err.log
```

Uninstall:

```bash
python scripts/install_betmate_launchd.py --uninstall
```

## File Discovery

The adapter searches the chosen Betmate round folder recursively for supported `.json`, `.csv`, `.xlsx`, and `.xls` files.

It classifies files by filename:

- injuries/suspensions/absences -> T5 injury JSON
- referees/officials -> T6 referee CSV
- emotional/context/human/milestone/narrative -> T7 emotional JSON

Other files are recorded in the manifest but are not fed into pricing unless a mapper is added for them.

## Staging Output

Each run writes:

```text
data/import/betmate/r11_2026/
  injuries.json
  referees.csv
  emotional.json
  validation_report.json
  manifest.json
```

The engine-ready files are also written to:

```text
data/import/injuries_r11.json
data/import/referees_r11.csv
data/import/emotional_r11.json
```

## Expected Betmate Columns

The importer accepts common aliases.

Injuries:

- `team` / `club`
- `player` / `player_name`
- `role` / `position`
- `importance_tier` / `tier` / `importance` / `quality`
- `status`
- `absence_type` / `type` / `category`
- `notes` / `details` / `reason`

Referees:

- `home_team` / `home`
- `away_team` / `away`
- `referee` / `ref` / `official`

Emotional:

- `team` / `club`
- `flag_type` / `flag` / `type` / `category` / `factor`
- `flag_strength` / `strength` / `severity`
- `player_name` / `player`
- `notes` / `details` / `description`

Unknown emotional flag types are ignored because the existing engine only supports the configured T7 flags.
