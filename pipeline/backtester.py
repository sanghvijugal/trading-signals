"""
Backtester — fills in outcome columns on past signals.

Runs at the end of each pipeline cycle.
For every signal where price_1h_later is NULL and enough time has passed,
fetches the current asset price and computes the return.
"""
import yfinance as yf
from datetime import datetime, timedelta
from storage.db import get_session
from storage.models import Signal


def fetch_current_price(ticker: str) -> float | None:
    try:
        t = yf.Ticker(ticker)
        hist = t.history(period="1d", interval="5m")
        if hist.empty:
            return None
        return float(hist.iloc[-1]["Close"])
    except Exception as e:
        print(f"[Backtest] Failed to fetch price for {ticker}: {e}")
        return None


def pct_return(entry: float, exit_price: float) -> float:
    if entry == 0:
        return 0.0
    return round((exit_price - entry) / entry * 100, 4)


def run():
    """Fill in outcome columns for signals old enough to have results."""
    session = get_session()
    now = datetime.utcnow()

    signals = session.query(Signal).filter(Signal.price_at_signal.isnot(None)).all()
    updated = 0

    for signal in signals:
        age = now - signal.generated_at
        price_entry = signal.price_at_signal

        if price_entry is None or price_entry == 0:
            continue

        current_price = fetch_current_price(signal.asset_ticker) if signal.asset_ticker else None
        if current_price is None:
            continue

        changed = False

        if signal.price_1h_later is None and age >= timedelta(hours=1):
            signal.price_1h_later = current_price
            signal.outcome_1h = pct_return(price_entry, current_price)
            changed = True

        if signal.price_4h_later is None and age >= timedelta(hours=4):
            signal.price_4h_later = current_price
            signal.outcome_4h = pct_return(price_entry, current_price)
            changed = True

        if signal.price_24h_later is None and age >= timedelta(hours=24):
            signal.price_24h_later = current_price
            signal.outcome_24h = pct_return(price_entry, current_price)
            changed = True

        if changed:
            updated += 1

    session.commit()
    session.close()

    if updated:
        print(f"[Backtest] Updated outcomes for {updated} signal(s)")
    else:
        print("[Backtest] No signals ready for outcome update yet")
