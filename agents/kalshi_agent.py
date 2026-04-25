import requests
import numpy as np
from datetime import datetime, timedelta
from config import KALSHI_API_KEY, KALSHI_BASE_URL, ANOMALY_THRESHOLD, ZSCORE_WINDOW
from storage.db import get_session
from storage.models import KalshiSnapshot


HEADERS = {
    "Authorization": f"Bearer {KALSHI_API_KEY}",
    "Content-Type": "application/json",
}

# Map Kalshi market tickers → related tradeable asset ticker
# Find live tickers at: https://kalshi.com/markets
KALSHI_TO_ASSET = {
    # Fed rate markets — long-lived (expire Apr 2027), moderate volume
    "KXFED-27APR-T4.25": "TLT",    # Fed above 4.25%? → Treasury ETF
    "KXFED-27APR-T4.00": "TLT",    # Fed above 4.00%? → Treasury ETF
    # BTC daily — highest volume, but expires daily → update ticker each morning
    "KXBTC-26APR2617-T67750": "BTC-USD",  # BTC above $67,750 at 5pm today
}

TRACKED_MARKETS = list(KALSHI_TO_ASSET.keys())


def fetch_market(ticker: str) -> dict | None:
    url = f"{KALSHI_BASE_URL}/markets/{ticker}"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    if resp.status_code != 200:
        print(f"[Kalshi] Failed to fetch {ticker}: {resp.status_code} {resp.text[:100]}")
        return None
    return resp.json().get("market")


def compute_volume_zscore(ticker: str, current_volume: int) -> float:
    """Z-score of current volume vs the last ZSCORE_WINDOW minutes of history."""
    session = get_session()
    cutoff = datetime.utcnow() - timedelta(minutes=ZSCORE_WINDOW)
    rows = (
        session.query(KalshiSnapshot.volume_24h)
        .filter(KalshiSnapshot.market_ticker == ticker)
        .filter(KalshiSnapshot.captured_at >= cutoff)
        .all()
    )
    session.close()

    volumes = [r[0] for r in rows if r[0] is not None]
    if len(volumes) < 5:
        return 0.0  # not enough history yet — will stabilize after ~25 min

    mean = np.mean(volumes)
    std = np.std(volumes)
    if std == 0:
        return 0.0

    return float((current_volume - mean) / std)


def run() -> list[dict]:
    """
    Fetch all tracked markets, store snapshots, return anomalies.

    Returns a list of dicts for markets where volume z-score >= ANOMALY_THRESHOLD.
    """
    anomalies = []
    session = get_session()

    for ticker in TRACKED_MARKETS:
        data = fetch_market(ticker)
        if data is None:
            continue

        yes_price = float(data.get("yes_ask_dollars") or data.get("last_price_dollars") or 0) * 100
        no_price = float(data.get("no_ask_dollars") or 0) * 100
        last_price = float(data.get("last_price_dollars") or 0) * 100
        volume = int(float(data.get("volume_24h_fp") or data.get("volume_fp") or 0))
        open_interest = int(float(data.get("open_interest_fp") or 0))
        z = compute_volume_zscore(ticker, volume)

        snapshot = KalshiSnapshot(
            market_ticker=ticker,
            market_title=data.get("title"),
            yes_price=yes_price,
            no_price=no_price,
            volume_24h=volume,
            open_interest=open_interest,
            last_price=last_price,
            volume_z_score=z,
        )
        session.add(snapshot)

        print(f"[Kalshi] {ticker} | yes={yes_price:.1f}¢ | vol={volume} | z={z:.2f}")

        if abs(z) >= ANOMALY_THRESHOLD:
            anomalies.append({
                "ticker": ticker,
                "yes_price": yes_price,
                "volume": volume,
                "volume_z_score": z,
                "direction": "spike_up" if z > 0 else "spike_down",
            })
            print(f"[Kalshi] Anomaly detected: {ticker} z={z:.2f}")

    session.commit()
    session.close()
    return anomalies
