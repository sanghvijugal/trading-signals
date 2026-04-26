from sqlalchemy import Column, Integer, Float, String, DateTime, Boolean, Text
from sqlalchemy.orm import declarative_base
from datetime import datetime

Base = declarative_base()


class KalshiSnapshot(Base):
    """Raw Kalshi market data captured every N minutes."""
    __tablename__ = "kalshi_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    market_ticker = Column(String(64), nullable=False, index=True)
    market_title = Column(String(256))
    yes_price = Column(Float)           # 0-100 cents = implied probability
    no_price = Column(Float)
    volume_24h = Column(Integer)
    open_interest = Column(Integer)
    last_price = Column(Float)
    volume_z_score = Column(Float)


class PolymarketSnapshot(Base):
    """Raw Polymarket data captured every N minutes."""
    __tablename__ = "polymarket_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    condition_id = Column(String(128), nullable=False, index=True)
    question = Column(String(512))
    outcome = Column(String(64))        # e.g. "Yes" or "No"
    probability = Column(Float)         # 0.0 to 1.0
    volume_24h = Column(Float)
    volume_total = Column(Float)
    volume_z_score = Column(Float)


class PriceSnapshot(Base):
    """Spot/futures price for a related asset."""
    __tablename__ = "price_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ticker = Column(String(16), nullable=False, index=True)
    price = Column(Float, nullable=False)
    volume = Column(Integer)
    change_1h_pct = Column(Float)
    change_24h_pct = Column(Float)


class MacroSnapshot(Base):
    """VIX, put/call ratio, and FRED macro indicators."""
    __tablename__ = "macro_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    vix = Column(Float)                 # CBOE VIX
    vix_change_1d = Column(Float)       # 1-day % change in VIX
    put_call_ratio = Column(Float)      # CBOE total put/call ratio
    yield_curve = Column(Float)         # 10Y - 2Y spread (bps)
    fed_funds_rate = Column(Float)      # Current effective fed funds rate
    cpi_yoy = Column(Float)             # Latest CPI year-over-year %


class OptionsFlowEvent(Base):
    """A single unusual options trade."""
    __tablename__ = "options_flow_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ticker = Column(String(16), nullable=False, index=True)
    expiry = Column(String(16))
    strike = Column(Float)
    option_type = Column(String(4))
    premium = Column(Float)
    is_sweep = Column(Boolean)
    sentiment = Column(String(8))
    implied_volatility = Column(Float)


class NewsEvent(Base):
    """A news hit for a tracked topic."""
    __tablename__ = "news_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    topic = Column(String(128), nullable=False, index=True)
    headline = Column(Text)
    source = Column(String(64))
    sentiment_score = Column(Float)


class Signal(Base):
    """A computed trading signal."""
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    market_ticker = Column(String(64), nullable=False, index=True)
    asset_ticker = Column(String(16))

    # Component scores (each 0.0 to 1.0)
    kalshi_spike_score = Column(Float)
    polymarket_divergence_score = Column(Float)  # kalshi vs polymarket
    options_flow_score = Column(Float)
    price_divergence_score = Column(Float)       # prediction vs actual price
    vix_score = Column(Float)
    news_velocity_score = Column(Float)
    macro_context_score = Column(Float)

    final_score = Column(Float, nullable=False)
    direction = Column(String(8))
    confidence = Column(String(8))

    # Backtesting columns (filled in later)
    price_at_signal = Column(Float)
    price_1h_later = Column(Float)
    price_4h_later = Column(Float)
    price_24h_later = Column(Float)
    outcome_1h = Column(Float)
    outcome_4h = Column(Float)
    outcome_24h = Column(Float)
