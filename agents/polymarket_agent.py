"""
Polymarket Agent — tracks high-volume financial prediction markets.

Strategy: fetch top markets by 24h volume, post-filter by financial keywords.
This avoids the Polymarket API's broken tag/category filtering.

No API key required.
"""
import requests
import numpy as np
from datetime import datetime, timedelta
from storage.db import get_session
from storage.models import PolymarketSnapshot


GAMMA_API = "https://gamma-api.polymarket.com"

# Keywords that identify a financially relevant market
FINANCIAL_KEYWORDS = [
    "fed", "federal reserve", "interest rate", "rate cut", "rate hike", "fomc",
    "bitcoin", "btc", "ethereum", "eth", "crypto",
    "inflation", "cpi", "unemployment", "gdp", "recession",
    "nasdaq", "s&p", "stock market", "oil", "gold",
    "dollar", "treasury", "yield curve", "tariff", "trade war",
]

# Map financial keywords → Kalshi series (for divergence matching)
KEYWORD_TO_SERIES = {
    "fed": "KXFED",
    "federal reserve": "KXFED",
    "interest rate": "KXFED",
    "rate cut": "KXFED",
    "rate hike": "KXFED",
    "fomc": "KXFED",
    "bitcoin": "KXBTC",
    "btc": "KXBTC",
    "ethereum": "KXETH",
    "eth": "KXETH",
    "inflation": "KXINFL",
    "cpi": "KXINFL",
    "unemployment": "KXUNEMP",
}

MIN_VOLUME_24H = 500     # ignore illiquid markets
FETCH_LIMIT = 100        # fetch top N by volume before filtering


def fetch_top_markets() -> list[dict]:
    """Fetch top markets by 24h volume."""
    try:
        resp = requests.get(
            f"{GAMMA_API}/markets",
            params={
                "limit": FETCH_LIMIT,
                "active": "true",
                "closed": "false",
                "order": "volume24hr",
                "ascending": "false",
            },
            timeout=15,
        )
        if resp.status_code != 200:
            print(f"[Polymarket] API error: {resp.status_code}")
            return []
        return resp.json()
    except Exception as e:
        print(f"[Polymarket] Fetch error: {e}")
        return []


def is_financial(question: str) -> str | None:
    """
    Return the matched keyword if this market is financially relevant, else None.
    """
    q = question.lower()
    for kw in FINANCIAL_KEYWORDS:
        if kw in q:
            return kw
    return None


def get_yes_probability(market: dict) -> float:
    """Extract YES probability from market data."""
    prices = market.get("outcomePrices", [])
    outcomes = market.get("outcomes", [])

    # Find the index of "Yes" outcome
    try:
        yes_idx = [o.lower() for o in outcomes].index("yes")
        return float(prices[yes_idx])
    except (ValueError, IndexError):
        pass

    # Fallback: use first price
    try:
        return float(prices[0]) if prices else 0.5
    except (ValueError, TypeError):
        return 0.5


def compute_volume_zscore(condition_id: str, current_volume: float) -> float:
    session = get_session()
    cutoff = datetime.utcnow() - timedelta(hours=2)
    rows = (
        session.query(PolymarketSnapshot.volume_24h)
        .filter(PolymarketSnapshot.condition_id == condition_id)
        .filter(PolymarketSnapshot.captured_at >= cutoff)
        .all()
    )
    session.close()

    volumes = [r[0] for r in rows if r[0] is not None]
    if len(volumes) < 3:
        return 0.0

    mean = np.mean(volumes)
    std = np.std(volumes)
    return 0.0 if std == 0 else float((current_volume - mean) / std)


def run() -> list[dict]:
    """
    Fetch top Polymarket markets, keep only financial ones, store snapshots.
    Returns list of relevant markets with probabilities for divergence scoring.
    """
    all_markets = fetch_top_markets()
    results = []
    session = get_session()
    seen = set()

    for market in all_markets:
        question = market.get("question", "")
        if not question:
            continue

        matched_kw = is_financial(question)
        if not matched_kw:
            continue

        volume_24h = float(market.get("volume24hr") or 0)
        if volume_24h < MIN_VOLUME_24H:
            continue

        condition_id = market.get("conditionId") or market.get("id", "")
        if condition_id in seen:
            continue
        seen.add(condition_id)

        probability = get_yes_probability(market)
        z = compute_volume_zscore(condition_id, volume_24h)
        kalshi_series = KEYWORD_TO_SERIES.get(matched_kw)

        snap = PolymarketSnapshot(
            condition_id=condition_id,
            question=question.encode("ascii", "ignore").decode()[:256],
            outcome="Yes",
            probability=round(probability, 4),
            volume_24h=volume_24h,
            volume_total=float(market.get("volume") or 0),
            volume_z_score=z,
        )
        session.add(snap)

        result = {
            "condition_id": condition_id,
            "question": question[:65],
            "probability": probability,
            "volume_24h": volume_24h,
            "volume_z_score": z,
            "matched_keyword": matched_kw,
            "kalshi_series": kalshi_series,
        }
        results.append(result)

        print(
            f"[Polymarket] {question[:55]}... "
            f"| p={probability:.0%} | vol={volume_24h:,.0f} | series={kalshi_series}"
        )

    session.commit()
    session.close()

    print(f"[Polymarket] {len(results)} financial markets found (from {len(all_markets)} total)")
    return results
