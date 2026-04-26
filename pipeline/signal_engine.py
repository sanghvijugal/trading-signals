import numpy as np
from storage.db import get_session
from storage.models import Signal


# Weights — must sum to 1.0
WEIGHTS = {
    "kalshi_spike":          0.20,
    "polymarket_divergence": 0.25,  # primary edge: two markets disagree
    "price_divergence":      0.25,  # prediction vs actual asset move
    "vix":                   0.10,
    "news_velocity":         0.10,
    "macro_context":         0.10,
}


def compute_kalshi_spike_score(z_score: float) -> float:
    return round(float(np.clip(abs(z_score) / 5.0, 0.0, 1.0)), 4)


def compute_polymarket_divergence_score(
    kalshi_yes_price: float,
    polymarket_probability: float | None,
) -> float:
    """
    Key signal: Kalshi and Polymarket disagree on the same event.
    Both express probability 0-1. Large gap = mispricing = edge.
    """
    if polymarket_probability is None:
        return 0.0
    kalshi_prob = kalshi_yes_price / 100.0
    divergence = abs(kalshi_prob - polymarket_probability)
    return round(float(np.clip(divergence / 0.3, 0.0, 1.0)), 4)  # 30% gap = score 1.0


def compute_price_divergence_score(
    yes_price: float,
    asset_change_pct: float,
) -> float:
    """
    Prediction market implied move vs actual asset move.
    High implied probability but asset hasn't moved = divergence.
    """
    implied = yes_price / 100.0
    actual = float(np.clip(abs(asset_change_pct) / 5.0, 0.0, 1.0))
    return round(float(np.clip(abs(implied - actual), 0.0, 1.0)), 4)


def compute_news_velocity_score(news_count: int, baseline: int = 5) -> float:
    if baseline == 0 or news_count <= baseline:
        return 0.0
    return round(float(np.clip((news_count / baseline - 1.0) / 4.0, 0.0, 1.0)), 4)


def determine_direction(
    kalshi_z: float,
    asset_change_pct: float,
    polymarket_prob: float | None,
    kalshi_yes_price: float,
) -> str:
    kalshi_prob = kalshi_yes_price / 100.0

    # If both markets agree price should be higher but asset hasn't moved
    if kalshi_z > 0 and asset_change_pct < 0:
        return "long"
    if kalshi_z < 0 and asset_change_pct > 0:
        return "short"

    # Polymarket consensus as tiebreaker
    if polymarket_prob is not None:
        return "long" if polymarket_prob > 0.5 else "short"

    return "long" if kalshi_prob > 0.5 else "short"


def confidence_label(score: float) -> str:
    if score >= 0.65:
        return "high"
    if score >= 0.40:
        return "medium"
    return "low"


def generate_signal(
    kalshi_ticker: str,
    asset_ticker: str,
    asset_price: float,
    kalshi_z: float,
    yes_price: float,
    asset_change_pct: float,
    news_count: int,
    polymarket_probability: float | None = None,
    vix_score: float = 0.0,
    macro_context_score: float = 0.5,
    trigger_source: str = "kalshi_spike",
) -> Signal:
    kalshi_spike = compute_kalshi_spike_score(kalshi_z)
    poly_div = compute_polymarket_divergence_score(yes_price, polymarket_probability)
    price_div = compute_price_divergence_score(yes_price, asset_change_pct)
    news_vel = compute_news_velocity_score(news_count)

    final_score = (
        WEIGHTS["kalshi_spike"]          * kalshi_spike
        + WEIGHTS["polymarket_divergence"] * poly_div
        + WEIGHTS["price_divergence"]      * price_div
        + WEIGHTS["vix"]                   * vix_score
        + WEIGHTS["news_velocity"]         * news_vel
        + WEIGHTS["macro_context"]         * macro_context_score
    )

    signal = Signal(
        market_ticker=kalshi_ticker,
        asset_ticker=asset_ticker,
        kalshi_spike_score=kalshi_spike,
        polymarket_divergence_score=poly_div,
        price_divergence_score=price_div,
        vix_score=vix_score,
        news_velocity_score=news_vel,
        macro_context_score=macro_context_score,
        options_flow_score=0.0,
        final_score=round(final_score, 4),
        direction=determine_direction(kalshi_z, asset_change_pct, polymarket_probability, yes_price),
        confidence=confidence_label(final_score),
        price_at_signal=asset_price,
        trigger_source=trigger_source,
    )

    session = get_session()
    session.add(signal)
    session.commit()
    session.refresh(signal)  # reload attributes before they expire on close
    session.expunge(signal)  # detach so object stays usable after session closes
    session.close()

    return signal
