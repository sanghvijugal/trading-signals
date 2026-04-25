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
    # Derived
    volume_z_score = Column(Float)      # computed at insert time


class PriceSnapshot(Base):
    """Spot/futures price for a related asset (e.g. SPY, BTC, oil)."""
    __tablename__ = "price_snapshots"

    id = Column(Integer, primary_key=True, autoincrement=True)
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ticker = Column(String(16), nullable=False, index=True)
    price = Column(Float, nullable=False)
    volume = Column(Integer)
    change_1h_pct = Column(Float)
    change_24h_pct = Column(Float)


class OptionsFlowEvent(Base):
    """A single unusual options trade (sweep, block, etc.)."""
    __tablename__ = "options_flow_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    ticker = Column(String(16), nullable=False, index=True)
    expiry = Column(String(16))
    strike = Column(Float)
    option_type = Column(String(4))     # "call" or "put"
    premium = Column(Float)             # total dollar value
    is_sweep = Column(Boolean)
    sentiment = Column(String(8))       # "bullish" / "bearish"
    implied_volatility = Column(Float)


class NewsEvent(Base):
    """A news hit for a tracked topic."""
    __tablename__ = "news_events"

    id = Column(Integer, primary_key=True, autoincrement=True)
    captured_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    topic = Column(String(128), nullable=False, index=True)
    headline = Column(Text)
    source = Column(String(64))
    sentiment_score = Column(Float)     # -1.0 to +1.0


class Signal(Base):
    """A computed trading signal ready for review or execution."""
    __tablename__ = "signals"

    id = Column(Integer, primary_key=True, autoincrement=True)
    generated_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    market_ticker = Column(String(64), nullable=False, index=True)
    asset_ticker = Column(String(16))

    # Component scores (each 0.0 to 1.0)
    kalshi_spike_score = Column(Float)
    options_flow_score = Column(Float)
    divergence_score = Column(Float)
    news_velocity_score = Column(Float)

    # Final weighted score
    final_score = Column(Float, nullable=False)
    direction = Column(String(8))       # "long" or "short"
    confidence = Column(String(8))      # "low" / "medium" / "high"

    # For backtesting (filled in later by a separate job)
    price_at_signal = Column(Float)
    price_1h_later = Column(Float)
    price_4h_later = Column(Float)
    price_24h_later = Column(Float)
    outcome_1h = Column(Float)          # % return
    outcome_4h = Column(Float)
    outcome_24h = Column(Float)
