"""
Collector — wires all agents together and generates signals.
Called by main.py on a schedule.
"""
from datetime import datetime
from agents import kalshi_agent, price_agent, options_agent, news_agent
from agents.kalshi_agent import KALSHI_TO_ASSET
from pipeline.signal_engine import generate_signal

# Map Kalshi topics to news topics for velocity scoring
KALSHI_TO_NEWS_TOPIC = {
    "KXFED-27APR-T4.25": "federal reserve",
    "KXFED-27APR-T4.00": "federal reserve",
    "KXBTC-26APR2617-T67750": "bitcoin",
}


def run_pipeline():
    print(f"\n{'='*60}")
    print(f"[Pipeline] {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{'='*60}")

    # Step 1: Kalshi — detect volume anomalies
    anomalies = kalshi_agent.run()
    print(f"[Pipeline] Kalshi: {len(anomalies)} anomaly(s) detected")

    if not anomalies:
        print("[Pipeline] No anomalies — nothing to score")
        return []

    # Step 2: Price data for linked assets
    kalshi_tickers = [a["ticker"] for a in anomalies]
    prices = price_agent.run(kalshi_tickers)

    # Step 3: Options flow for linked assets
    asset_tickers = list(prices.keys())
    options_scores = options_agent.run(asset_tickers)

    # Step 4: News velocity
    news_counts = news_agent.run()

    # Step 5: Generate a signal for each anomaly
    signals = []
    for anomaly in anomalies:
        k_ticker = anomaly["ticker"]
        asset = KALSHI_TO_ASSET.get(k_ticker)

        if not asset or asset not in prices:
            print(f"[Pipeline] No price data for {k_ticker} → {asset}, skipping")
            continue

        price_data = prices[asset]
        news_topic = KALSHI_TO_NEWS_TOPIC.get(k_ticker, "")
        news_count = news_counts.get(news_topic, 0)
        options_score = options_scores.get(asset, 0.0)

        signal = generate_signal(
            kalshi_ticker=k_ticker,
            asset_ticker=asset,
            kalshi_z=anomaly["volume_z_score"],
            yes_price=anomaly["yes_price"],
            asset_change_pct=price_data["change_1h_pct"],
            news_count=news_count,
            options_flow_score=options_score,
        )

        signals.append(signal)
        print(
            f"[Signal] {k_ticker} → {asset} | "
            f"score={signal.final_score:.2f} | "
            f"dir={signal.direction} | "
            f"confidence={signal.confidence}"
        )

    return signals
