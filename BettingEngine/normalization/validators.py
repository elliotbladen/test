from __future__ import annotations


def validate_odds_decimal(value) -> tuple[bool, list[str]]:
    errors = []
    try:
        odds = float(value)
    except (TypeError, ValueError):
        return False, ["odds_decimal must be numeric"]
    if odds <= 1.0:
        errors.append("odds_decimal must be > 1.0")
    return not errors, errors


def validate_probability(value) -> tuple[bool, list[str]]:
    errors = []
    try:
        probability = float(value)
    except (TypeError, ValueError):
        return False, ["probability must be numeric"]
    if probability <= 0.0 or probability > 1.0:
        errors.append("probability must be > 0.0 and <= 1.0")
    return not errors, errors


def validate_result(result: dict) -> tuple[bool, list[str]]:
    errors = []
    for key in ("match_id", "home_score", "away_score", "total_score", "margin"):
        if result.get(key) is None:
            errors.append(f"{key} is required")
    if result.get("home_score", 0) < 0 or result.get("away_score", 0) < 0:
        errors.append("scores must be non-negative")
    return not errors, errors


def validate_market_snapshot(snapshot: dict) -> tuple[bool, list[str]]:
    errors = []
    for key in ("match_id", "bookmaker_id", "captured_at", "market_type", "selection_name", "odds_decimal"):
        if snapshot.get(key) is None:
            errors.append(f"{key} is required")
    if snapshot.get("market_type") not in {"h2h", "handicap", "total"}:
        errors.append(f"unsupported market_type={snapshot.get('market_type')!r}")
    if snapshot.get("selection_name") not in {"home", "away", "over", "under"}:
        errors.append(f"unsupported selection_name={snapshot.get('selection_name')!r}")
    odds = snapshot.get("odds_decimal")
    if odds is not None:
        is_valid_odds, odds_errors = validate_odds_decimal(odds)
        if not is_valid_odds:
            errors.extend(odds_errors)
    return not errors, errors


def _validate_dataframe(df, required: set[str], duplicate_subset: list[str]) -> dict:
    errors = []
    warnings = []
    missing = sorted(required - set(df.columns))
    if missing:
        errors.append({"row": None, "field": "columns", "message": f"missing columns: {missing}"})

    duplicate_count = 0
    if not missing and duplicate_subset:
        duplicate_mask = df.duplicated(subset=duplicate_subset, keep=False)
        duplicate_count = int(duplicate_mask.sum())
        for idx in df.index[duplicate_mask]:
            warnings.append({
                "row": int(idx) + 2,
                "field": "duplicate",
                "message": f"duplicate key across columns: {duplicate_subset}",
            })

    return {
        "error_count": len(errors),
        "warning_count": len(warnings),
        "duplicate_count": duplicate_count,
        "errors": errors,
        "warnings": warnings,
    }


def validate_results_dataframe(df) -> dict:
    return _validate_dataframe(
        df,
        {"season", "round", "match_date", "home_team", "away_team", "venue", "home_score", "away_score"},
        ["season", "round", "home_team", "away_team"],
    )


def validate_odds_dataframe(df) -> dict:
    return _validate_dataframe(
        df,
        {"season", "round", "match_date", "home_team", "away_team", "bookmaker", "market_type", "selection", "odds"},
        ["season", "round", "home_team", "away_team", "bookmaker", "market_type", "selection"],
    )


def format_validation_report(validation: dict, filepath: str) -> str:
    lines = [
        f"Validation report for {filepath}: "
        f"{validation.get('error_count', 0)} error(s), {validation.get('warning_count', 0)} warning(s)"
    ]
    for item in validation.get("errors", []):
        lines.append(f"ERROR row={item.get('row')} field={item.get('field')}: {item.get('message')}")
    for item in validation.get("warnings", []):
        lines.append(f"WARNING row={item.get('row')} field={item.get('field')}: {item.get('message')}")
    return "\n".join(lines)
