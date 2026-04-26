"""
Collector — orchestrates all agents and generates signals each pipeline run.

Signal triggers (any one fires a signal):
  1. kalshi_spike     — Kalshi volume z-score >= ANOMALY_THRESHOLD
  2. polymarket_spike — Polymarket volume z-score >= ANOMALY_THRESHOLD
  3. divergence       — |kalshi_prob - polymarket_prob| >= DIVERGENCE_THRESHOLD
"""
from datetime import datetime
from config import DIVERGENCE_THRESHOLD
from agents import kalshi_agent, price_agent, news_agent
from agents import polymarket_agent, vix_agent, fred_agent
from agents import alert_agent
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
    "KXWTI": "oil",
    "KXTARIFFRATEEU": "tariff EU",
    "KXTARIFFRATEPRC": "tariff China",
}


def _get_series(ticker: str) -> str:
    return ticker.split("-")[0]


def _match_poly(series: str, poly_all: list[dict]) -> dict | None:
    """Return highest-volume Polymarket result matching this Kalshi series."""
    matches = [r for r in poly_all if r.get("kalshi_series") == series]
    if not matches:
        return None
    return max(matches, key=lambda r: r.get("volume_24h", 0))


def _build_candidate_map(
    kalshi_all: list[dict],
    kalshi_anomalies: list[dict],
    poly_all: list[dict],
    poly_anomalies: list[dict],
) -> dict[str, dict]:
    """
    Build a map of kalshi_ticker → candidate info for every market that
    should fire a signal this run.

    A market qualifies if:
      - Its Kalshi z-score >= threshold  (kalshi_spike), OR
      - Its matched Polymarket z-score >= threshold  (polymarket_spike), OR
      - |kalshi_prob - polymarket_prob| >= DIVERGENCE_THRESHOLD  (divergence)
    """
    candidates: dict[str, dict] = {}

    # Index all Kalshi markets by ticker
    kalshi_by_ticker = {m["ticker"]: m for m in kalshi_all}

    # Index Kalshi anomaly tickers for fast lookup
    kalshi_anomaly_tickers = {m["ticker"] for m in kalshi_anomalies}

    # Index Polymarket anomaly series for fast lookup
    poly_anomaly_series = {r.get("kalshi_series") for r in poly_anomalies if r.get("kalshi_series")}

    for ticker, k_market in kalshi_by_ticker.items():
        series = _get_series(ticker)
        poly_match = _match_poly(series, poly_all)

        is_kalshi_spike = ticker in kalshi_anomaly_tickers
        is_poly_spike = series in poly_anomaly_series

        # Divergence check
        kalshi_prob = k_market["yes_price"] / 100.0
        poly_prob = poly_match["probability"] if poly_match else None
        divergence = abs(kalshi_prob - poly_prob) if poly_prob is not None else 0.0
        is_divergence = divergence >= DIVERGENCE_THRESHOLD

        if not (is_kalshi_spike or is_poly_spike or is_divergence):
            continue

        # Determine trigger source (priority: divergence > kalshi > polymarket)
        if is_divergence:
            trigger = "divergence"
        elif is_kalshi_spike:
            trigger = "kalshi_spike"
        else:
            trigger = "polymarket_spike"

        candidates[ticker] = {
            "ticker": ticker,
            "asset": k_market["asset"],
            "series": series,
            "kalshi_z": k_market["volume_z_score"],
            "yes_price": k_market["yes_price"],
            "poly_prob": poly_prob,
            "poly_z": poly_match["volume_z_score"] if poly_match else 0.0,
            "divergence": divergence,
            "trigger": trigger,
        }

        flags = []
        if is_kalshi_spike:
            flags.append(f"kalshi_z={k_market['volume_z_score']:.2f}")
        if is_poly_spike:
            flags.append(f"poly_z={poly_match['volume_z_score']:.2f}")
        if is_divergence:
            flags.append(f"divergence={divergence:.0%}")
        print(f"[Pipeline] Candidate: {ticker} | trigger={trigger} | {' | '.join(flags)}")

    return candidates


def run_pipeline() -> list:
    print(f"\n{'='*60}")
    print(f"[Pipeline] {datetime.utcnow().strftime('%Y-%m-%d %H:%M:%S')} UTC")
    print(f"{'='*60}")

    # ── Step 1: Macro context ─────────────────────────────────────────
    vix_data = vix_agent.run()
    macro_data = fred_agent.run()

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

    # ── Step 2: Both markets (always collect) ─────────────────────────
    poly_result = polymarket_agent.run()
    poly_all: list[dict] = poly_result.get("all", [])
    poly_anomalies: list[dict] = poly_result.get("anomalies", [])

    kalshi_result = kalshi_agent.run()
    kalshi_all: list[dict] = kalshi_result.get("all", [])
    kalshi_anomalies: list[dict] = kalshi_result.get("anomalies", [])

    print(
        f"[Pipeline] Kalshi: {len(kalshi_all)} markets, {len(kalshi_anomalies)} spike(s) | "
        f"Polymarket: {len(poly_all)} markets, {len(poly_anomalies)} spike(s)"
    )

    # ── Step 3: Build candidate set across all 3 trigger types ───────
    candidates = _build_candidate_map(kalshi_all, kalshi_anomalies, poly_all, poly_anomalies)

    if not candidates:
        print("[Pipeline] No signals triggered this run")
        backtester.run()
        return []

    # ── Step 4: Price data for all candidate assets ───────────────────
    asset_tickers = list({c["asset"] for c in candidates.values()})
    prices = price_agent.run(asset_tickers)

    # ── Step 5: News velocity ─────────────────────────────────────────
    news_counts = news_agent.run()

    # ── Step 6: Generate signals ──────────────────────────────────────
    signals = []
    for ticker, cand in candidates.items():
        asset = cand["asset"]

        if asset not in prices:
            print(f"[Pipeline] No price data for {asset}, skipping {ticker}")
            continue

        price_data = prices[asset]
        news_topic = SERIES_TO_NEWS_TOPIC.get(cand["series"], "")
        news_count = news_counts.get(news_topic, 0)

        signal = generate_signal(
            kalshi_ticker=ticker,
            asset_ticker=asset,
            asset_price=price_data["price"],
            kalshi_z=cand["kalshi_z"],
            yes_price=cand["yes_price"],
            asset_change_pct=price_data["change_1h_pct"],
            news_count=news_count,
            polymarket_probability=cand["poly_prob"],
            vix_score=vix_data.get("vix_score", 0.0),
            macro_context_score=macro_data.get("macro_context_score", 0.5),
            trigger_source=cand["trigger"],
        )

        signals.append(signal)
        poly_str = f"{cand['poly_prob']:.0%}" if cand["poly_prob"] is not None else "n/a"
        print(
            f"[Signal] {ticker} → {asset} | "
            f"score={signal.final_score:.2f} | dir={signal.direction} | "
            f"conf={signal.confidence} | trigger={cand['trigger']} | "
            f"kalshi={cand['yes_price']:.0f}¢ | poly={poly_str}"
        )
        alert_agent.send_alert(signal)

    # ── Step 7: Backtest past signals ─────────────────────────────────
    backtester.run()

    return signals
