import sys
import os

# Allow running from the project root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
from storage.db import get_session, init_db
from storage.models import Signal, KalshiSnapshot, PriceSnapshot

st.set_page_config(page_title="Signal Dashboard", layout="wide")
st.title("Cross-Market Anomaly Signals")

init_db()
session = get_session()

# ── Signals Table ──────────────────────────────────────────────────────────────
st.subheader("Recent Signals")
signals = session.query(Signal).order_by(Signal.generated_at.desc()).limit(50).all()

if signals:
    rows = [{
        "Time (UTC)": s.generated_at.strftime("%Y-%m-%d %H:%M"),
        "Kalshi Market": s.market_ticker,
        "Asset": s.asset_ticker,
        "Score": round(s.final_score, 3),
        "Direction": s.direction,
        "Confidence": s.confidence,
        "Kalshi Spike": round(s.kalshi_spike_score or 0, 3),
        "Divergence": round(s.divergence_score or 0, 3),
        "News Velocity": round(s.news_velocity_score or 0, 3),
        "Options Flow": round(s.options_flow_score or 0, 3),
    } for s in signals]

    df = pd.DataFrame(rows)

    def color_confidence(val):
        if val == "high":
            return "background-color: #d4edda; color: #155724"
        if val == "medium":
            return "background-color: #fff3cd; color: #856404"
        return ""

    st.dataframe(
        df.style.applymap(color_confidence, subset=["Confidence"]),
        use_container_width=True,
    )
else:
    st.info("No signals yet. Run `python main.py` to start collecting data.")

# ── Score Distribution ─────────────────────────────────────────────────────────
if signals:
    st.subheader("Score Distribution")
    score_df = pd.DataFrame({"Final Score": [s.final_score for s in signals]})
    st.bar_chart(score_df["Final Score"].value_counts(bins=10).sort_index())

# ── Kalshi Z-Score History ─────────────────────────────────────────────────────
st.subheader("Kalshi Volume Z-Score History")
snaps = session.query(KalshiSnapshot).order_by(KalshiSnapshot.captured_at.desc()).limit(500).all()

if snaps:
    snap_df = pd.DataFrame([{
        "time": s.captured_at,
        "ticker": s.market_ticker,
        "z_score": s.volume_z_score or 0,
        "yes_price": s.yes_price or 0,
    } for s in snaps])

    for ticker in snap_df["ticker"].unique():
        st.markdown(f"**{ticker}**")
        t_df = snap_df[snap_df["ticker"] == ticker].sort_values("time")
        st.line_chart(t_df.set_index("time")[["z_score", "yes_price"]])
else:
    st.info("No Kalshi data yet.")

# ── Price History ──────────────────────────────────────────────────────────────
st.subheader("Asset Price History")
price_snaps = session.query(PriceSnapshot).order_by(PriceSnapshot.captured_at.desc()).limit(500).all()

if price_snaps:
    price_df = pd.DataFrame([{
        "time": p.captured_at,
        "ticker": p.ticker,
        "price": p.price,
        "change_1h_pct": p.change_1h_pct or 0,
    } for p in price_snaps])

    for ticker in price_df["ticker"].unique():
        st.markdown(f"**{ticker}**")
        t_df = price_df[price_df["ticker"] == ticker].sort_values("time")
        st.line_chart(t_df.set_index("time")[["price", "change_1h_pct"]])
else:
    st.info("No price data yet.")

session.close()
