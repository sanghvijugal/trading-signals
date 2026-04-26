"""
Polymarket Agent — tracks prediction market probabilities.

Polymarket has 10-100x more volume than Kalshi on financial markets.
No API key required for read-only access.

Primary signal: divergence between Kalshi and Polymarket on the same topic.
If Kalshi says 60% and Polymarket says 40% → one market is wrong → edge.
"""
import requests
import numpy as np
from datetime import datetime, timedelta
from storage.db import get_session
from storage.models import PolymarketSnapshot


GAMMA_API = "https://gamma-api.polymarket.com"

# Topics to track — maps a label to Polymarket search keywords
# Find markets at: https://polymarket.com/markets
TRACKED_TOPICS = [
    "federal reserve rate",
    "bitcoin price",
    "ethereum price",
    "inflation",
    "unemployment",
]

# Minimum 24h volume to consider a market liquid enough
MIN_VOLUME = 1000


def fetch_markets(keyword: str, limit: int = 5) -> list[dict]:
    try:
        resp = requests.get(
            f"{GAMMA_API}/markets",
            params={"q": keyword, "limit": limit, "active": "true", "closed": "false"},
            timeout=10,
        )
        if resp.status_code != 200:
            print(f"[Polymarket] Failed for '{keyword}': {resp.status_code}")
            return []
        return resp.json()
    except Exception as e:
        print(f"[Polymarket] Error fetching '{keyword}': {e}")
        return []


def compute_volume_zscore(condition_id: str, current_volume: float) -> float:
    """Z-score of current 24h volume vs the last hour of history."""
    session = get_session()
    cutoff = datetime.utcnow() - timedelta(hours=1)
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
    if std == 0:
        return 0.0

    return float((current_volume - mean) / std)


def run() -> list[dict]:
    """
    Fetch Polymarket snapshots for all tracked topics.
    Returns list of high-volume markets with their probabilities.
    """
    results = []
    session = get_session()

    for topic in TRACKED_TOPICS:
        markets = fetch_markets(topic)

        for market in markets:
            volume_24h = float(market.get("volume24hr") or market.get("volume") or 0)
            if volume_24h < MIN_VOLUME:
                continue

            condition_id = market.get("conditionId") or market.get("id", "")
            question = market.get("question", "").encode("ascii", "ignore").decode()[:256]

            # Polymarket binary markets have outcomes array
            outcomes = market.get("outcomes", ["Yes", "No"])
            out_prices = market.get("outcomePrices", ["0.5", "0.5"])

            try:
                yes_prob = float(out_prices[0]) if out_prices else 0.5
            except (ValueError, IndexError):
                yes_prob = 0.5

            z = compute_volume_zscore(condition_id, volume_24h)

            snap = PolymarketSnapshot(
                condition_id=condition_id,
                question=question,
                outcome="Yes",
                probability=round(yes_prob, 4),
                volume_24h=volume_24h,
                volume_total=float(market.get("volume") or 0),
                volume_z_score=z,
            )
            session.add(snap)

            results.append({
                "condition_id": condition_id,
                "question": question[:60],
                "probability": yes_prob,
                "volume_24h": volume_24h,
                "volume_z_score": z,
                "topic": topic,
            })

            print(
                f"[Polymarket] {question[:55]}... "
                f"| p={yes_prob:.0%} | vol={volume_24h:.0f} | z={z:.2f}"
            )

    session.commit()
    session.close()
    return results
