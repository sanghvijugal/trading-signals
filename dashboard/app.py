import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import streamlit as st
import pandas as pd
from storage.db import get_session, init_db
from storage.models import Signal, KalshiSnapshot, PolymarketSnapshot, MacroSnapshot

st.set_page_config(page_title="Signal Dashboard", layout="wide", page_icon="📡")
st.title("📡 Cross-Market Anomaly Signals")

init_db()
session = get_session()

# ── Macro Bar ──────────────────────────────────────────────────────────────────
macro = session.query(MacroSnapshot).order_by(MacroSnapshot.captured_at.desc()).first()
if macro:
    c1, c2, c3, c4, c5 = st.columns(5)
    c1.metric("VIX", f"{macro.vix:.1f}" if macro.vix else "—",
              f"{macro.vix_change_1d:+.1f}%" if macro.vix_change_1d else None)
    c2.metric("Put/Call Ratio", f"{macro.put_call_ratio:.2f}" if macro.put_call_ratio else "—")
    c3.metric("Yield Curve (10Y-2Y)", f"{macro.yield_curve:.2f}%" if macro.yield_curve else "—")
    c4.metric("Fed Funds Rate", f"{macro.fed_funds_rate:.2f}%" if macro.fed_funds_rate else "—")
    c5.metric("CPI YoY", f"{macro.cpi_yoy:.1f}%" if macro.cpi_yoy else "—")
    st.divider()

# ── Signals Table ──────────────────────────────────────────────────────────────
st.subheader("Recent Signals")
signals = session.query(Signal).order_by(Signal.generated_at.desc()).limit(50).all()

if signals:
    rows = [{
        "Time (UTC)": s.generated_at.strftime("%Y-%m-%d %H:%M"),
        "Kalshi Market": s.market_ticker,
        "Asset": s.asset_ticker,
        "Score": round(s.final_score, 3),
        "Dir": s.direction,
        "Confidence": s.confidence,
        "Kalshi Spike": round(s.kalshi_spike_score or 0, 2),
        "Poly Divergence": round(s.polymarket_divergence_score or 0, 2),
        "Price Div": round(s.price_divergence_score or 0, 2),
        "VIX": round(s.vix_score or 0, 2),
        "News": round(s.news_velocity_score or 0, 2),
        "1h Return": f"{s.outcome_1h:+.2f}%" if s.outcome_1h is not None else "—",
        "4h Return": f"{s.outcome_4h:+.2f}%" if s.outcome_4h is not None else "—",
        "24h Return": f"{s.outcome_24h:+.2f}%" if s.outcome_24h is not None else "—",
    } for s in signals]

    df = pd.DataFrame(rows)

    def color_confidence(val):
        if val == "high":
            return "background-color: #d4edda; color: #155724"
        if val == "medium":
            return "background-color: #fff3cd; color: #856404"
        return ""

    def color_return(val):
        if val == "—":
            return ""
        try:
            num = float(val.replace("%", "").replace("+", ""))
            if num > 0:
                return "color: #28a745"
            if num < 0:
                return "color: #dc3545"
        except Exception:
            pass
        return ""

    st.dataframe(
        df.style
          .applymap(color_confidence, subset=["Confidence"])
          .applymap(color_return, subset=["1h Return", "4h Return", "24h Return"]),
        use_container_width=True,
    )

    # Backtest summary
    completed = [s for s in signals if s.outcome_1h is not None]
    if completed:
        st.subheader("Backtest Summary")
        bc1, bc2, bc3 = st.columns(3)
        wins_1h = sum(1 for s in completed if (s.outcome_1h or 0) > 0)
        avg_1h = sum(s.outcome_1h or 0 for s in completed) / len(completed)
        bc1.metric("1h Win Rate", f"{wins_1h/len(completed):.0%}", f"avg {avg_1h:+.2f}%")

        completed_4h = [s for s in signals if s.outcome_4h is not None]
        if completed_4h:
            wins_4h = sum(1 for s in completed_4h if (s.outcome_4h or 0) > 0)
            avg_4h = sum(s.outcome_4h or 0 for s in completed_4h) / len(completed_4h)
            bc2.metric("4h Win Rate", f"{wins_4h/len(completed_4h):.0%}", f"avg {avg_4h:+.2f}%")

        completed_24h = [s for s in signals if s.outcome_24h is not None]
        if completed_24h:
            wins_24h = sum(1 for s in completed_24h if (s.outcome_24h or 0) > 0)
            avg_24h = sum(s.outcome_24h or 0 for s in completed_24h) / len(completed_24h)
            bc3.metric("24h Win Rate", f"{wins_24h/len(completed_24h):.0%}", f"avg {avg_24h:+.2f}%")
else:
    st.info("No signals yet. Anomalies trigger signals — check back after more data is collected.")

st.divider()

# ── Kalshi Z-Score History ─────────────────────────────────────────────────────
st.subheader("Kalshi Volume Z-Score History")
snaps = session.query(KalshiSnapshot).order_by(KalshiSnapshot.captured_at.desc()).limit(500).all()

if snaps:
    snap_df = pd.DataFrame([{
        "time": s.captured_at,
        "ticker": s.market_ticker,
        "z_score": s.volume_z_score or 0,
        "yes_price_pct": (s.yes_price or 0),
    } for s in snaps])

    for ticker in snap_df["ticker"].unique():
        t_df = snap_df[snap_df["ticker"] == ticker].sort_values("time")
        st.markdown(f"**{ticker}**")
        st.line_chart(t_df.set_index("time")[["z_score", "yes_price_pct"]])
else:
    st.info("No Kalshi data yet.")

st.divider()

# ── Polymarket Probabilities ───────────────────────────────────────────────────
st.subheader("Polymarket Probabilities")
poly_snaps = session.query(PolymarketSnapshot).order_by(PolymarketSnapshot.captured_at.desc()).limit(200).all()

if poly_snaps:
    poly_df = pd.DataFrame([{
        "time": p.captured_at,
        "question": p.question[:50] if p.question else "",
        "probability": round((p.probability or 0) * 100, 1),
        "volume_24h": p.volume_24h or 0,
    } for p in poly_snaps])

    latest = poly_df.drop_duplicates(subset="question", keep="first")
    st.dataframe(latest[["question", "probability", "volume_24h"]], use_container_width=True)
else:
    st.info("No Polymarket data yet.")

session.close()
