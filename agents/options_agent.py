"""
Options Flow Agent — placeholder for Unusual Whales integration.

Free alternative: Tradier sandbox (https://developer.tradier.com/)
Paid (recommended): Unusual Whales API (~$50/mo)

For the MVP, this agent returns a score of 0.0 until an API key is configured.
Wire it in once you have a data source.
"""
import os
import requests
from datetime import datetime
from storage.db import get_session
from storage.models import OptionsFlowEvent


UNUSUAL_WHALES_KEY = os.getenv("UNUSUAL_WHALES_KEY")
UNUSUAL_WHALES_URL = "https://api.unusualwhales.com/api"


def fetch_unusual_flow(ticker: str) -> list[dict]:
    """Fetch recent unusual options activity for a ticker."""
    if not UNUSUAL_WHALES_KEY:
        return []

    headers = {"Authorization": f"Bearer {UNUSUAL_WHALES_KEY}"}
    url = f"{UNUSUAL_WHALES_URL}/option-contracts/flow?ticker={ticker}&limit=10"
    resp = requests.get(url, headers=headers, timeout=10)

    if resp.status_code != 200:
        print(f"[Options] Failed to fetch {ticker}: {resp.status_code}")
        return []

    return resp.json().get("data", [])


def compute_flow_score(events: list[dict]) -> float:
    """
    Score 0.0-1.0 based on options flow conviction.

    Higher score = stronger directional signal from options.
    """
    if not events:
        return 0.0

    total_premium = sum(e.get("premium", 0) for e in events)
    bullish = sum(e.get("premium", 0) for e in events if e.get("sentiment") == "bullish")
    bearish = sum(e.get("premium", 0) for e in events if e.get("sentiment") == "bearish")

    if total_premium == 0:
        return 0.0

    # Imbalance ratio: how one-sided is the flow?
    imbalance = abs(bullish - bearish) / total_premium
    return round(min(imbalance, 1.0), 4)


def run(asset_tickers: list[str]) -> dict[str, float]:
    """
    Returns options flow score (0.0-1.0) per asset ticker.
    """
    scores: dict[str, float] = {}
    session = get_session()

    for ticker in asset_tickers:
        events = fetch_unusual_flow(ticker)
        score = compute_flow_score(events)
        scores[ticker] = score

        for e in events:
            flow_event = OptionsFlowEvent(
                ticker=ticker,
                expiry=e.get("expiry"),
                strike=e.get("strike"),
                option_type=e.get("type"),
                premium=e.get("premium"),
                is_sweep=e.get("is_sweep", False),
                sentiment=e.get("sentiment"),
                implied_volatility=e.get("iv"),
            )
            session.add(flow_event)

        if events:
            print(f"[Options] {ticker}: {len(events)} events | score={score:.2f}")
        else:
            print(f"[Options] {ticker}: no data (add UNUSUAL_WHALES_KEY to .env)")

    session.commit()
    session.close()
    return scores
