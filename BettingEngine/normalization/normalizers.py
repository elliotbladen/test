from __future__ import annotations

from datetime import datetime


_NRL_TEAM_ALIASES = {
    "Bulldogs": "Canterbury-Bankstown Bulldogs",
    "Canterbury Bulldogs": "Canterbury-Bankstown Bulldogs",
    "Canterbury-Bankstown Bulldogs": "Canterbury-Bankstown Bulldogs",
    "Cronulla Sharks": "Cronulla-Sutherland Sharks",
    "Cronulla Sutherland Sharks": "Cronulla-Sutherland Sharks",
    "Cronulla-Sutherland Sharks": "Cronulla-Sutherland Sharks",
    "Manly Sea Eagles": "Manly-Warringah Sea Eagles",
    "Manly Warringah Sea Eagles": "Manly-Warringah Sea Eagles",
    "Manly-Warringah Sea Eagles": "Manly-Warringah Sea Eagles",
    "New Zealand Warriors": "New Zealand Warriors",
    "Warriors": "New Zealand Warriors",
    "North QLD Cowboys": "North Queensland Cowboys",
    "North Queensland Cowboys": "North Queensland Cowboys",
    "St George Dragons": "St. George Illawarra Dragons",
    "St George Illawarra Dragons": "St. George Illawarra Dragons",
    "St. George Illawarra Dragons": "St. George Illawarra Dragons",
}

_NRL_VENUE_ALIASES = {
    "4 Pines Park (Brookvale Oval)": "4 Pines Park",
    "Apollo Projects Stadium": "One NZ Stadium Christchurch",
    "BlueBet Stadium (Penrith)": "BlueBet Stadium",
    "Cbus Super Stadium (Robina)": "Cbus Super Stadium",
    "GIO Stadium": "GIO Stadium Canberra",
    "Go Media Stadium (Mt Smart Stadium)": "Go Media Stadium",
    "Hnry Stadium": "Sky Stadium",
    "McDonald Jones Stadium (Newcastle)": "McDonald Jones Stadium",
    "Ocean Protect Stadium": "Sharks Stadium",
    "PointsBet Stadium": "Sharks Stadium",
    "Queensland Country Bank Stadium (Townsville)": "Queensland Country Bank Stadium",
    "Suncorp Stadium (Lang Park)": "Suncorp Stadium",
    "polytec Stadium": "Polytec Stadium",
}

_MARKET_ALIASES = {
    "head_to_head": "h2h",
    "head-to-head": "h2h",
    "moneyline": "h2h",
    "line": "handicap",
    "spread": "handicap",
    "totals": "total",
    "over_under": "total",
}

_SELECTION_ALIASES = {
    "h": "home",
    "a": "away",
    "o": "over",
    "u": "under",
}

_BOOKMAKER_ALIASES = {
    "bet365": "bet365",
    "bet 365": "bet365",
    "pinnacle": "pinnacle",
    "bluebet": "bluebet",
    "blue bet": "bluebet",
}


def normalize_team_name(value: str) -> str:
    raw = str(value or "").strip()
    return _NRL_TEAM_ALIASES.get(raw, raw)


def normalize_venue_name(value: str) -> str:
    raw = str(value or "").strip()
    return _NRL_VENUE_ALIASES.get(raw, raw)


def normalize_market_type(value: str) -> str:
    raw = str(value or "").strip().lower()
    return _MARKET_ALIASES.get(raw, raw)


def normalize_selection_name(value: str) -> str:
    raw = str(value or "").strip().lower()
    return _SELECTION_ALIASES.get(raw, raw)


def normalize_bookmaker_code(value: str) -> str:
    raw = str(value or "").strip().lower()
    return _BOOKMAKER_ALIASES.get(raw, raw.replace(" ", "_"))


def normalize_date(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("date is blank")
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%m/%d/%Y"):
        try:
            return datetime.strptime(raw[:10], fmt).date().isoformat()
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw.replace("T", " ")).date().isoformat()
    except ValueError as exc:
        raise ValueError(f"invalid date: {value!r}") from exc


def normalize_datetime(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        raise ValueError("datetime is blank")
    raw = raw.replace("T", " ")
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            width = len(datetime.now().strftime(fmt))
            return datetime.strptime(raw[:width], fmt).isoformat(sep=" ")
        except ValueError:
            pass
    try:
        return datetime.fromisoformat(raw).isoformat(sep=" ")
    except ValueError as exc:
        raise ValueError(f"invalid datetime: {value!r}") from exc


def normalize_odds_decimal(value) -> float:
    odds = float(value)
    if odds <= 1.0:
        raise ValueError(f"decimal odds must be > 1.0, got {odds}")
    return odds
