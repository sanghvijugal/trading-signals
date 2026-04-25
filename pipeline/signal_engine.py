import numpy as np
from datetime import datetime
from storage.db import get_session
from storage.models import Signal
from config import WEIGHTS


def compute_kalshi_spike_score(z_score: float) -> float:
    """Map z-score magnitude to 0-1. Capped at z=5 for stability."""
    return round(min(abs(z_score) / 5.0, 1.0), 4)


def compute_divergence_score(yes_price: float, asset_change_pct: float) -> float:
    """
    Primary signal: prediction market vs actual asset move.

    yes_price   : Kalshi YES price in cents (0-100) = implied probability
    asset_change: 1h % change in the related asset

    Logic:
    - If market says 80% chance but asset barely moved → high divergence → edge
    - If market says 50% and asset moved 5% → no divergence → noise
    """
    implied_probability = yes_price / 100.0
    # Normalize asset move: assume 5% = full conviction (1.0)
    actual_move = min(abs(asset_change_pct) / 5.0, 1.0)

    divergence = abs(implied_probability - actual_move)
    return round(float(np.clip(divergence, 0.0, 1.0)), 4)


def compute_news_velocity_score(news_count: int, baseline: int = 5) -> float:
    """
    How much faster is news arriving vs the baseline?

    A 5x spike = score of 1.0. Below baseline = 0.0.
    """
    if baseline == 0 or news_count <= baseline:
        return 0.0
    ratio = news_count / baseline
    return round(float(np.clip((ratio - 1.0) / 4.0, 0.0, 1.0)), 4)


def determine_direction(kalshi_z: float, asset_change_pct: float) -> str:
    """
    If Kalshi YES spikes and asset hasn't followed → go long (asset will catch up).
    If Kalshi NO spikes and asset is up → go short (asset will correct).
    """
    if kalshi_z > 0 and asset_change_pct < 0:
        return "long"
    if kalshi_z < 0 and asset_change_pct > 0:
        return "short"
    # Default: follow the Kalshi spike direction
    return "long" if kalshi_z > 0 else "short"


def confidence_label(score: float) -> str:
    if score >= 0.70:
        return "high"
    if score >= 0.45:
        return "medium"
    return "low"


def generate_signal(
    kalshi_ticker: str,
    asset_ticker: str,
    kalshi_z: float,
    yes_price: float,
    asset_change_pct: float,
    news_count: int,
    options_flow_score: float = 0.0,
) -> Signal:
    kalshi_spike = compute_kalshi_spike_score(kalshi_z)
    divergence = compute_divergence_score(yes_price, asset_change_pct)
    news_vel = compute_news_velocity_score(news_count)

    final_score = (
        WEIGHTS["kalshi_spike"] * kalshi_spike
        + WEIGHTS["options_flow"] * options_flow_score
        + WEIGHTS["divergence"] * divergence
        + WEIGHTS["news_velocity"] * news_vel
    )

    signal = Signal(
        market_ticker=kalshi_ticker,
        asset_ticker=asset_ticker,
        kalshi_spike_score=kalshi_spike,
        options_flow_score=options_flow_score,
        divergence_score=divergence,
        news_velocity_score=news_vel,
        final_score=round(final_score, 4),
        direction=determine_direction(kalshi_z, asset_change_pct),
        confidence=confidence_label(final_score),
    )

    session = get_session()
    session.add(signal)
    session.commit()
    session.close()

    return signal
