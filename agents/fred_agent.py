"""
FRED Macro Agent — fetches key macro indicators from the Federal Reserve.

Free API: https://fred.stlouisfed.org/docs/api/api_key.html
Set FRED_API_KEY in your .env and GitHub Secrets.

Signal inputs (real-time enough to matter):
  DFF    — Effective Federal Funds Rate (daily)
  T10Y2Y — 10Y-2Y Treasury yield spread (daily)

Display only (monthly, already priced in by the time we see it):
  CPIAUCSL — CPI index level (shown on dashboard but not used in scoring)
"""
import os
import requests


FRED_BASE = "https://api.stlouisfed.org/fred/series/observations"
FRED_API_KEY = os.getenv("FRED_API_KEY")


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
) -> float:
    """
    Score 0.0-1.0 representing macro stress level.
    Based on yield curve + fed funds rate only — both update daily.

    High score = stressed macro = signals more meaningful
    Low score  = calm macro    = signals may be noise
    """
    score = 0.0
    components = 0

    if yield_curve is not None:
        # Inverted yield curve (negative) = high stress
        # 0.53% spread → low stress; -0.5% → high stress
        yc_score = max(0.0, min(1.0, (-yield_curve + 0.5) / 2.0))
        score += yc_score
        components += 1

    if fed_funds is not None:
        # Higher rates = tighter conditions = more signal sensitivity
        # 3.64% → score ~0.61; 0% → 0.0; 6%+ → 1.0
        ff_score = min(fed_funds / 6.0, 1.0)
        score += ff_score
        components += 1

    return round(score / components, 4) if components > 0 else 0.5


def run() -> dict:
    """Fetch macro indicators, return context score."""
    if not FRED_API_KEY:
        print("[FRED] No FRED_API_KEY — defaulting macro_context_score to 0.5")
        return {"macro_context_score": 0.5, "yield_curve": None, "fed_funds_rate": None, "cpi_yoy": None}

    fed_funds = fetch_series("DFF")
    yield_curve = fetch_series("T10Y2Y")
    cpi = fetch_series("CPIAUCSL")   # fetched for display only, not scoring

    macro_score = compute_macro_context_score(yield_curve, fed_funds)

    print(
        f"[FRED] Fed={fed_funds}% | Yield curve={yield_curve}% | "
        f"CPI index={cpi} (display only) | macro_score={macro_score:.2f}"
    )

    return {
        "macro_context_score": macro_score,
        "yield_curve": yield_curve,
        "fed_funds_rate": fed_funds,
        "cpi_yoy": cpi,  # stored for dashboard display, not used in scoring
    }
