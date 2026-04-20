# Module Contracts

Standard shapes for the four structures that cross module boundaries most
frequently. Treat these as stable interfaces. Changes require either an ADR
update or an explicit comment explaining the deviation.

---

## RunValidation

Returned by `validation/pre_run.validate_run_inputs()` and
`validation/pre_run.validate_pricing_output()`.
Passed into `decision/signals.generate_signals()` as `run_validation`.
Also passed as `pricing_warnings` (its `.warnings` list) to signal generation.

```
RunValidation
  can_proceed: bool
  errors:   list[{flag: str, message: str}]   blocking — sets can_proceed=False
  warnings: list[{flag: str, message: str}]   non-blocking — run may continue
```

Rules:
- `can_proceed=False` if and only if `errors` is non-empty.
- Every item in both lists has exactly two keys: `flag` (machine-readable code,
  e.g. `'THIN_DATA'`) and `message` (human-readable explanation).
- `validate_pricing_output()` never sets `can_proceed=False` — it only warns.
- Callers check `can_proceed` before running pricing. `run_pricing()` returns
  early with `run_status='failed'` if `can_proceed` is `False`.

---

## Tier Adjustment Output

Returned by every tier function (`compute_matchup_adjustments`,
`compute_situational_adjustments`, etc.) and accumulated by `run_pricing()`.
Each dict in the list becomes one row in `model_adjustments`.

```
list[{
  tier_number:             int     1–7
  tier_name:               str     e.g. 'tier2_matchup'
  adjustment_code:         str     machine key, e.g. 'yardage_territory'
  adjustment_description:  str     human summary
  home_points_delta:       float   positive = home expected score increases
  away_points_delta:       float   positive = away expected score increases
  margin_delta:            float   always home_delta - away_delta
  total_delta:             float   always home_delta + away_delta
  applied_flag:            int     1 = applied, 0 = evaluated but skipped
  _debug:                  dict    full signal-level breakdown (not persisted)
}]
```

Rules:
- `margin_delta` and `total_delta` are derived values. Never set them
  independently of `home_points_delta` / `away_points_delta`.
- `_debug` is for in-process audit only. `log_adjustments()` does not write it.
- An empty list is valid — the tier had no effect or was disabled.
- Tiers never adjust probability or odds directly (see ADR-004).

---

## Pricing Run Result

Returned by `pricing/engine.run_pricing()`.
The caller checks `run_status` before accessing price or signal fields.

```
{
  # always present
  match_id:         int
  model_version:    str
  run_timestamp:    str           ISO UTC datetime
  run_status:       str           'success' | 'partial' | 'failed'
  can_proceed:      bool
  run_validation:   RunValidation
  match:            dict | None
  home_stats:       dict | None
  away_stats:       dict | None
  snapshots:        list
  match_context:    dict | None
  adjustments:      list          tier adjustment dicts
  signals:          list          signal dicts

  # present when run_status != 'failed'
  baseline_home_points:  float
  baseline_away_points:  float
  baseline_margin:       float
  baseline_total:        float
  final_home_points:     float
  final_away_points:     float
  prices:                dict      output of derive_final_prices()
  pricing_validation:    RunValidation
}
```

Rules:
- `run_status='failed'` means pre-run validation blocked execution.
  Price and signal fields are absent. Only identity and validation fields present.
- `run_status='partial'` means pricing ran but `validate_pricing_output()`
  produced non-blocking warnings.
- `model_run_id` is absent. The caller sets it after calling `log_model_run()`.
- `signals[*]['model_run_id']` is `None` until the caller backfills it.

`prices` dict keys (from `derive_final_prices()`):
```
final_margin, final_total,
home_win_probability, away_win_probability,
fair_home_odds, fair_away_odds,
fair_handicap_line, fair_total_line
```

---

## Generated Signal Output

One dict per `(bookmaker, market_type, selection_name)` snapshot.
Returned as a list by `decision/signals.generate_signals()`.
Field names here differ from `signals` table column names —
`audit/model_logger.log_signal()` handles the mapping.

```
{
  # identity
  match_id:              int | None
  model_run_id:          int | None   None until caller persists the run
  model_version:         str
  timestamp:             str          ISO UTC

  # market
  bookmaker_name:        str
  bookmaker_code:        str
  market_type:           str          'h2h' | 'handicap' | 'total'
  selection_name:        str          'home' | 'away' | 'over' | 'under'
  line_value:            float | None  None for h2h

  # prices
  market_odds:           float | None
  model_odds:            float | None
  model_probability:     float | None

  # EV
  ev:                    float | None  decimal form (0.25 = +25% EV)
  ev_percent:            float | None  percent form (25.0 = +25% EV)

  # Kelly / sizing
  raw_kelly:             float | None
  applied_kelly:         float | None
  capped_stake_fraction: float | None
  recommended_stake:     float | None  dollar amount; 0.0 if below minimum

  # decision
  signal_label:          str   'no_bet'|'pass'|'watch'|'recommend_small'|
                               'recommend_medium'|'recommend_strong'
  confidence:            str   'low' | 'medium' | 'high'
  veto:                  bool
  veto_reason:           str | None   populated when veto=True
  soft_veto_reasons:     list[str]    always a list, never None
  manual_review_required: bool        True when label == 'recommend_strong'

  # snapshot linkage
  snapshot_id:           int | None
  snapshot_captured_at:  str | None
  snapshot_age_hours:    float | None
}
```

Rules:
- `ev`, `model_probability`, and Kelly fields are `None` if calculation failed.
  They are never silently set to `0.0` to mask a failure.
- `soft_veto_reasons` is always a list — never `None`. May be empty.
- `veto=True` does not remove the signal from the list. All signals are returned
  so every comparison is auditable. Callers filter by `signal_label` or `veto`.
- Signals with `model_run_id=None` must not be inserted into the `signals` table
  (`log_signal()` will return `None` and log a warning).
