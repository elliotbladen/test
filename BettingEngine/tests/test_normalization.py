# tests/test_normalization.py

import pandas as pd

from normalization.normalizers import (
    normalize_bookmaker_code,
    normalize_date,
    normalize_datetime,
    normalize_market_type,
    normalize_odds_decimal,
    normalize_selection_name,
    normalize_team_name,
    normalize_venue_name,
)
from normalization.validators import (
    validate_odds_dataframe,
    validate_odds_decimal,
    validate_probability,
    validate_results_dataframe,
)


def test_normalize_team_name_alias():
    assert normalize_team_name("Canterbury Bulldogs") == "Canterbury-Bankstown Bulldogs"
    assert normalize_team_name("Warriors") == "New Zealand Warriors"


def test_normalize_venue_alias():
    assert normalize_venue_name("Ocean Protect Stadium") == "Sharks Stadium"
    assert normalize_venue_name("GIO Stadium") == "GIO Stadium Canberra"


def test_normalize_market_selection_and_bookmaker():
    assert normalize_market_type("Moneyline") == "h2h"
    assert normalize_market_type("spread") == "handicap"
    assert normalize_selection_name("H") == "home"
    assert normalize_selection_name("U") == "under"
    assert normalize_bookmaker_code("Bet 365") == "bet365"


def test_normalize_date_and_odds():
    assert normalize_date("30/04/2026") == "2026-04-30"
    assert normalize_odds_decimal("1.91") == 1.91


def test_normalize_datetime_accepts_common_iso_shapes():
    assert normalize_datetime("2026-04-30 19:30") == "2026-04-30 19:30:00"
    assert normalize_datetime("2026-04-30T19:30:15") == "2026-04-30 19:30:15"


def test_validate_odds_decimal_rejects_invalid_values():
    assert validate_odds_decimal("1.01")[0]
    valid, errors = validate_odds_decimal("1.00")
    assert not valid
    assert "odds_decimal must be > 1.0" in errors


def test_validate_probability_bounds():
    assert validate_probability(1.0)[0]
    assert not validate_probability(0.0)[0]
    assert not validate_probability(-0.01)[0]
    assert not validate_probability(1.01)[0]


def test_validate_results_dataframe_reports_missing_columns():
    df = pd.DataFrame([{"season": 2026}])
    report = validate_results_dataframe(df)
    assert report["error_count"] == 1
    assert "duplicate_count" in report


def test_validate_odds_dataframe_reports_duplicates():
    df = pd.DataFrame([
        {
            "season": 2026,
            "round": 1,
            "match_date": "2026-03-01",
            "home_team": "Panthers",
            "away_team": "Broncos",
            "bookmaker": "Bet365",
            "market_type": "h2h",
            "selection": "home",
            "odds": "1.80",
        },
        {
            "season": 2026,
            "round": 1,
            "match_date": "2026-03-01",
            "home_team": "Panthers",
            "away_team": "Broncos",
            "bookmaker": "Bet365",
            "market_type": "h2h",
            "selection": "home",
            "odds": "1.82",
        },
    ])
    report = validate_odds_dataframe(df)
    assert report["error_count"] == 0
    assert report["duplicate_count"] == 2
