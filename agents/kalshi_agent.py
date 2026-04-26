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

# Long-lived series to always track (don't expire daily)
PERSISTENT_SERIES = {
    "KXFED": "TLT",      # Fed rate decisions → Treasury ETF
    "KXINFL": "TIP",     # Inflation markets → TIPS ETF
    "KXUNEMP": "SPY",    # Unemployment → SPY
}

# Daily series — auto-refreshed each run to highest-volume open market
DAILY_SERIES = {
    "KXBTC": "BTC-USD",
    "KXETH": "ETH-USD",
}

# Minimum 24h volume to track a market
MIN_VOLUME = 10


def fetch_market(ticker: str) -> dict | None:
    url = f"{KALSHI_BASE_URL}/markets/{ticker}"
    resp = requests.get(url, headers=HEADERS, timeout=10)
    if resp.status_code != 200:
        print(f"[Kalshi] Failed to fetch {ticker}: {resp.status_code}")
        return None
    return resp.json().get("market")


def find_best_market(series_ticker: str) -> dict | None:
    """Find the highest-volume open market for a given series."""
    resp = requests.get(
        f"{KALSHI_BASE_URL}/markets",
        headers=HEADERS,
        params={"series_ticker": series_ticker, "status": "open", "limit": 20},
        timeout=10,
    )
    if resp.status_code != 200:
        return None

    markets = resp.json().get("markets", [])
    if not markets:
        return None

    # Pick highest 24h volume
    best = max(markets, key=lambda m: float(m.get("volume_24h_fp") or 0))
    vol = float(best.get("volume_24h_fp") or 0)
    if vol < MIN_VOLUME:
        return None

    return best


def find_best_persistent_markets(series_ticker: str, limit: int = 3) -> list[dict]:
    """Find top markets by volume for a long-lived series."""
    resp = requests.get(
        f"{KALSHI_BASE_URL}/markets",
        headers=HEADERS,
        params={"series_ticker": series_ticker, "status": "open", "limit": 20},
        timeout=10,
    )
    if resp.status_code != 200:
        return []

    markets = resp.json().get("markets", [])
    markets.sort(key=lambda m: float(m.get("volume_24h_fp") or 0), reverse=True)
    return markets[:limit]


def build_market_map() -> dict[str, str]:
    """
    Dynamically build ticker → asset map each run.
    Persistent series: top 3 by volume.
    Daily series: single highest-volume market.
    """
    market_map: dict[str, str] = {}

    for series, asset in PERSISTENT_SERIES.items():
        for m in find_best_persistent_markets(series):
            ticker = m.get("ticker", "")
            vol = float(m.get("volume_24h_fp") or 0)
            if ticker and vol >= MIN_VOLUME:
                market_map[ticker] = asset

    for series, asset in DAILY_SERIES.items():
        best = find_best_market(series)
        if best:
            ticker = best.get("ticker", "")
            if ticker:
                market_map[ticker] = asset
                print(f"[Kalshi] Auto-selected {series}: {ticker} (vol={float(best.get('volume_24h_fp',0)):.0f})")

    return market_map


# Global cache so we don't re-query on every call within the same run
_MARKET_MAP: dict[str, str] = {}


def get_market_map() -> dict[str, str]:
    global _MARKET_MAP
    if not _MARKET_MAP:
        _MARKET_MAP = build_market_map()
    return _MARKET_MAP


def compute_volume_zscore(ticker: str, current_volume: int) -> float:
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
        return 0.0

    mean = np.mean(volumes)
    std = np.std(volumes)
    if std == 0:
        return 0.0

    return float((current_volume - mean) / std)


def run() -> dict:
    """
    Fetch all tracked markets, store snapshots.

    Returns:
        {
            "all":       [...every market snapshot...],
            "anomalies": [...markets with z-score >= ANOMALY_THRESHOLD...]
        }
    """
    global _MARKET_MAP
    _MARKET_MAP = {}  # reset each run to auto-refresh daily tickers

    market_map = get_market_map()
    if not market_map:
        print("[Kalshi] No markets found — check API key and series tickers")
        return {"all": [], "anomalies": []}

    all_markets = []
    anomalies = []
    session = get_session()

    for ticker, asset in market_map.items():
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

        market_dict = {
            "ticker": ticker,
            "asset": asset,
            "yes_price": yes_price,
            "volume": volume,
            "volume_z_score": z,
            "series": get_series_from_ticker(ticker),
        }
        all_markets.append(market_dict)

        print(f"[Kalshi] {ticker} | yes={yes_price:.1f}¢ | vol={volume} | z={z:.2f}")

        if abs(z) >= ANOMALY_THRESHOLD:
            anomalies.append(market_dict)
            print(f"[Kalshi] *** Spike: {ticker} z={z:.2f} ***")

    session.commit()
    session.close()
    return {"all": all_markets, "anomalies": anomalies}


def get_series_from_ticker(ticker: str) -> str:
    return ticker.split("-")[0]
