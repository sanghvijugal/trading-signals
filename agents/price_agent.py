import yfinance as yf
from datetime import datetime
from storage.db import get_session
from storage.models import PriceSnapshot
from agents.kalshi_agent import KALSHI_TO_ASSET


def fetch_price(ticker: str) -> dict | None:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="2d", interval="1h")
        if hist.empty:
            print(f"[Price] No data returned for {ticker}")
            return None

        latest = hist.iloc[-1]
        prev_1h = hist.iloc[-2]["Close"] if len(hist) >= 2 else latest["Close"]
        prev_24h = hist.iloc[-25]["Close"] if len(hist) >= 25 else hist.iloc[0]["Close"]

        return {
            "ticker": ticker,
            "price": round(float(latest["Close"]), 4),
            "volume": int(latest["Volume"]),
            "change_1h_pct": round((latest["Close"] - prev_1h) / prev_1h * 100, 4),
            "change_24h_pct": round((latest["Close"] - prev_24h) / prev_24h * 100, 4),
        }
    except Exception as e:
        print(f"[Price] Failed to fetch {ticker}: {e}")
        return None


def run(kalshi_tickers: list[str]) -> dict[str, dict]:
    """
    Fetch prices for assets linked to the given Kalshi market tickers.

    Returns a dict of asset_ticker -> price data.
    """
    results = {}
    session = get_session()

    # Deduplicate asset tickers
    asset_tickers = list({KALSHI_TO_ASSET[t] for t in kalshi_tickers if t in KALSHI_TO_ASSET})

    for asset in asset_tickers:
        data = fetch_price(asset)
        if data is None:
            continue

        snap = PriceSnapshot(**data)
        session.add(snap)
        results[asset] = data
        print(f"[Price] {asset}: ${data['price']} | 1h={data['change_1h_pct']:+.2f}%")

    session.commit()
    session.close()
    return results
