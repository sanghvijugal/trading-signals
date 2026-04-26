"""
Collector — orchestrates all agents and generates signals each pipeline run.
"""
from datetime import datetime
from agents import kalshi_agent, price_agent, news_agent
from agents import polymarket_agent, vix_agent, fred_agent
from pipeline.signal_engine import generate_signal
from pipeline import backtester
from storage.db import get_session
from storage.models import MacroSnapshot


# Map Kalshi series → news topics
SERIES_TO_NEWS_TOPIC = {
    "KXFED": "federal reserve",
    "KXBTC": "bitcoin",
    "KXETH": "ethereum",
    "KXINFL": "inflation",
    "KXUNEMP": "unemployment",
}

# Map Polymarket topics → Kalshi series (for divergence matching)
POLY_TOPIC_TO_SERIES = {
    "federal reserve rate": "KXFED",
    "bitcoin price": "KXBTC",
    "ethereum price": "KXETH",
    "inflation": "KXINFL",
}


def get_series_from_ticker(ticker: str) -> str:
    """Extract series prefix from a ticker like KXBTC-26APR..."""
    return ticker.split("-")[0]


def match_polymarket_prob(
    kalshi_ticker: str,
    polymarket_results: list[dict],
) -> float | None:
    """Find the best matching Polymarket probability for a Kalshi market."""
    series = get_series_from_ticker(kalshi_ticker)
    matching_topic = next(
        (t for t, s in POLY_TOPIC_TO_SERIES.items() if s == series), None
    )
    if not matching_topic:
        return None

    matches = [r for r in polymarket_results if r.get("topic") == matching_topic]
    if not matches:
        return None

    # Use highest-volume match
    best = max(matches, key=lambda r: r.get("volume_24h", 0))
    return best.get("probability")


def run_pipeline():
    print(f"\n{'='*60}")
    print(f"[Pipeline] {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{'='*60}")

    # ── Step 1: Macro context (runs regardless of anomalies) ──────────
    vix_data = vix_agent.run()
    macro_data = fred_agent.run()

    # Store macro snapshot
    session = get_session()
    snap = MacroSnapshot(
        vix=vix_data.get("vix"),
        vix_change_1d=vix_data.get("vix_change_1d"),
        put_call_ratio=vix_data.get("put_call_ratio"),
        yield_curve=macro_data.get("yield_curve"),
        fed_funds_rate=macro_data.get("fed_funds_rate"),
        cpi_yoy=macro_data.get("cpi_yoy"),
    )
    session.add(snap)
    session.commit()
    session.close()

    # ── Step 2: Polymarket (always collect for divergence) ────────────
    polymarket_results = polymarket_agent.run()

    # ── Step 3: Kalshi anomaly detection ──────────────────────────────
    anomalies = kalshi_agent.run()
    print(f"[Pipeline] Kalshi: {len(anomalies)} anomaly(s) detected")

    if not anomalies:
        backtester.run()
        return []

    # ── Step 4: Price data for anomalous assets ───────────────────────
    asset_tickers = list({a["asset"] for a in anomalies})
    prices = price_agent.run(asset_tickers)

    # ── Step 5: News velocity ─────────────────────────────────────────
    news_counts = news_agent.run()

    # ── Step 6: Generate signals ──────────────────────────────────────
    signals = []
    for anomaly in anomalies:
        k_ticker = anomaly["ticker"]
        asset = anomaly["asset"]

        if asset not in prices:
            print(f"[Pipeline] No price data for {asset}, skipping")
            continue

        price_data = prices[asset]
        series = get_series_from_ticker(k_ticker)
        news_topic = SERIES_TO_NEWS_TOPIC.get(series, "")
        news_count = news_counts.get(news_topic, 0)
        poly_prob = match_polymarket_prob(k_ticker, polymarket_results)

        signal = generate_signal(
            kalshi_ticker=k_ticker,
            asset_ticker=asset,
            asset_price=price_data["price"],
            kalshi_z=anomaly["volume_z_score"],
            yes_price=anomaly["yes_price"],
            asset_change_pct=price_data["change_1h_pct"],
            news_count=news_count,
            polymarket_probability=poly_prob,
            vix_score=vix_data.get("vix_score", 0.0),
            macro_context_score=macro_data.get("macro_context_score", 0.5),
        )

        signals.append(signal)
        poly_str = f"{poly_prob:.0%}" if poly_prob is not None else "n/a"
        print(
            f"[Signal] {k_ticker} → {asset} | "
            f"score={signal.final_score:.2f} | dir={signal.direction} | "
            f"confidence={signal.confidence} | kalshi={anomaly['yes_price']:.0f}¢ | poly={poly_str}"
        )

    # ── Step 7: Backtest past signals ─────────────────────────────────
    backtester.run()

    return signals
