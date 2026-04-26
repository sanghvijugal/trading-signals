"""
VIX Agent — tracks market fear and options sentiment.

Data sources (all free via yfinance):
  ^VIX   — CBOE Volatility Index (fear gauge)
  ^VXN   — Nasdaq Volatility Index
  ^VVIX  — Volatility of VIX (fear of fear)

Put/call ratio via CBOE free data feed.

Signal logic:
  - VIX spike → fear increasing → options market pricing in risk
  - If VIX spikes but prediction markets haven't moved → divergence → edge
  - VIX > 30 = high fear (down-weight bullish signals)
  - VIX < 15 = complacency (up-weight contrarian signals)
"""
import requests
import yfinance as yf
import numpy as np
from datetime import datetime
from storage.db import get_session
from storage.models import MacroSnapshot


VIX_TICKER = "^VIX"
CBOE_PC_URL = "https://cdn.cboe.com/api/global/us_indices/daily_prices/PC_TOTAL.csv"


def fetch_vix() -> dict | None:
    try:
        vix = yf.Ticker(VIX_TICKER)
        hist = vix.history(period="5d", interval="1d")
        if hist.empty:
            return None

        latest = float(hist.iloc[-1]["Close"])
        prev = float(hist.iloc[-2]["Close"]) if len(hist) >= 2 else latest
        change_1d = (latest - prev) / prev * 100

        return {"vix": round(latest, 2), "vix_change_1d": round(change_1d, 2)}
    except Exception as e:
        print(f"[VIX] Failed to fetch VIX: {e}")
        return None


def fetch_put_call_ratio() -> float | None:
    """Fetch CBOE total put/call ratio from free CBOE data feed."""
    try:
        resp = requests.get(CBOE_PC_URL, timeout=10)
        if resp.status_code != 200:
            return None

        lines = resp.text.strip().split("\n")
        # Last line has latest data: date,pc_ratio
        if len(lines) < 2:
            return None

        last = lines[-1].split(",")
        return round(float(last[1]), 3)
    except Exception as e:
        print(f"[VIX] Failed to fetch put/call ratio: {e}")
        return None


def compute_vix_score(vix: float, vix_change: float, put_call: float | None = None) -> float:
    """
    Score 0.0-1.0 representing how much fear is in the market.

    Components:
      - VIX level:       VIX < 15 = calm (0.0), VIX > 45 = extreme fear (1.0)
      - VIX spike:       rapid day-over-day move amplifies signal
      - Put/call ratio:  > 1.2 = fear, < 0.7 = complacency

    High score = high fear = prediction markets may lag reality.
    """
    level_score = float(np.clip((vix - 15) / (45 - 15), 0.0, 1.0))
    spike_score = float(np.clip(abs(vix_change) / 20.0, 0.0, 1.0))

    if put_call is not None:
        # 0.7 = complacent (0.0), 1.5 = high fear (1.0)
        pc_score = float(np.clip((put_call - 0.7) / (1.5 - 0.7), 0.0, 1.0))
        return round(0.5 * level_score + 0.3 * spike_score + 0.2 * pc_score, 4)

    return round(0.6 * level_score + 0.4 * spike_score, 4)


def run() -> dict:
    """Fetch VIX and put/call ratio, store snapshot, return scores."""
    vix_data = fetch_vix()
    put_call = fetch_put_call_ratio()

    vix = vix_data["vix"] if vix_data else None
    vix_change = vix_data["vix_change_1d"] if vix_data else None
    vix_score = compute_vix_score(vix, vix_change, put_call) if vix else 0.0

    print(
        f"[VIX] VIX={vix} ({vix_change:+.1f}% 1d) | "
        f"P/C ratio={put_call} | score={vix_score:.2f}"
        if vix else "[VIX] No data available"
    )

    return {
        "vix": vix,
        "vix_change_1d": vix_change,
        "put_call_ratio": put_call,
        "vix_score": vix_score,
    }
