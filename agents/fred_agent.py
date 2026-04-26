"""
FRED Macro Agent — fetches key macro indicators from the Federal Reserve.

Free API: https://fred.stlouisfed.org/docs/api/api_key.html
Set FRED_API_KEY in your .env and GitHub Secrets.

Data fetched:
  DFF    — Effective Federal Funds Rate
  T10Y2Y — 10Y-2Y Treasury yield spread (recession indicator)
  CPIAUCSL — CPI All Urban Consumers (inflation)
  UNRATE — Unemployment Rate

These provide macro context for weighting signals:
  - Inverted yield curve → recession risk → down-weight bullish signals
  - Rising CPI → Fed more likely to hike → up-weight Fed rate signals
  - Low unemployment → strong economy → different signal baseline
"""
import os
import requests


FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
FRED_API_KEY = os.getenv("FRED_API_KEY")

SERIES = {
    "DFF": "fed_funds_rate",
    "T10Y2Y": "yield_curve",
    "CPIAUCSL": "cpi_yoy",
}


def fetch_series(series_id: str) -> float | None:
    """Fetch the most recent observation for a FRED series."""
    if not FRED_API_KEY:
        return None
    try:
        resp = requests.get(
            FRED_BASE,
            params={
                "series_id": series_id,
                "api_key": FRED_API_KEY,
                "file_type": "json",
                "sort_order": "desc",
                "limit": 2,
            },
            timeout=10,
        )
        if resp.status_code != 200:
            return None

        observations = resp.json().get("observations", [])
        for obs in observations:
            val = obs.get("value", ".")
            if val != ".":
                return round(float(val), 4)
        return None
    except Exception as e:
        print(f"[FRED] Error fetching {series_id}: {e}")
        return None


def compute_macro_context_score(
    yield_curve: float | None,
    fed_funds: float | None,
    cpi: float | None,
) -> float:
    """
    Score 0.0-1.0 representing macro stress level.

    High score = stressed macro environment = signals more meaningful.
    Low score = calm macro = signals may be noise.
    """
    score = 0.0
    components = 0

    if yield_curve is not None:
        # Inverted yield curve (negative) = high stress
        yc_score = max(0.0, min(1.0, (-yield_curve + 0.5) / 2.0))
        score += yc_score
        components += 1

    if fed_funds is not None:
        # Higher rates = more macro sensitivity
        ff_score = min(fed_funds / 6.0, 1.0)
        score += ff_score
        components += 1

    if cpi is not None:
        # High inflation = more macro stress
        cpi_score = min(max(cpi - 2.0, 0.0) / 6.0, 1.0)
        score += cpi_score
        components += 1

    return round(score / components, 4) if components > 0 else 0.5


def run() -> dict:
    """Fetch all macro indicators, store snapshot, return context score."""
    if not FRED_API_KEY:
        print("[FRED] No FRED_API_KEY set — add it to .env and GitHub Secrets")
        return {"macro_context_score": 0.5, "yield_curve": None, "fed_funds_rate": None, "cpi_yoy": None}

    fed_funds = fetch_series("DFF")
    yield_curve = fetch_series("T10Y2Y")
    cpi = fetch_series("CPIAUCSL")

    macro_score = compute_macro_context_score(yield_curve, fed_funds, cpi)

    print(
        f"[FRED] Fed={fed_funds}% | Yield curve={yield_curve}% | "
        f"CPI={cpi}% | macro_score={macro_score:.2f}"
    )

    return {
        "macro_context_score": macro_score,
        "yield_curve": yield_curve,
        "fed_funds_rate": fed_funds,
        "cpi_yoy": cpi,
    }
