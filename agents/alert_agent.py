"""
Alert Agent — sends email via Resend when a high-confidence signal fires.

Setup:
  Add to GitHub Secrets:
    RESEND_API_KEY — from resend.com dashboard
"""
import os
import resend
from storage.models import Signal


resend.api_key = os.getenv("RESEND_API_KEY")

FROM_ADDRESS = "alerts@splitbank.app"
TO_ADDRESS = "jugaltsanghvi@gmail.com"

ALERT_CONFIDENCE_LEVELS = {"high"}


def _build_subject(signal: Signal) -> str:
    direction = (signal.direction or "?").upper()
    return (
        f"[{signal.confidence.upper()}] {direction} signal: "
        f"{signal.market_ticker} → {signal.asset_ticker} "
        f"(score={signal.final_score:.2f})"
    )


def _build_body(signal: Signal) -> str:
    trigger_labels = {
        "kalshi_spike":     "Kalshi volume spike",
        "polymarket_spike": "Polymarket volume spike",
        "divergence":       "Cross-market divergence (Kalshi vs Polymarket)",
    }
    trigger_desc = trigger_labels.get(signal.trigger_source or "", signal.trigger_source or "unknown")

    rows = [
        ("Market",               signal.market_ticker),
        ("Asset",                signal.asset_ticker),
        ("Direction",            (signal.direction or "?").upper()),
        ("Confidence",           (signal.confidence or "?").upper()),
        ("Score",                f"{signal.final_score:.3f}"),
        ("Trigger",              trigger_desc),
        ("Time (UTC)",           signal.generated_at.strftime("%Y-%m-%d %H:%M:%S")),
        ("",                     ""),
        ("Kalshi spike",         f"{signal.kalshi_spike_score or 0:.2f}"),
        ("Polymarket divergence",f"{signal.polymarket_divergence_score or 0:.2f}"),
        ("Price divergence",     f"{signal.price_divergence_score or 0:.2f}"),
        ("VIX / fear",           f"{signal.vix_score or 0:.2f}"),
        ("News velocity",        f"{signal.news_velocity_score or 0:.2f}"),
        ("Macro context",        f"{signal.macro_context_score or 0:.2f}"),
        ("",                     ""),
        ("Asset price",          f"${signal.price_at_signal:.2f}" if signal.price_at_signal else "—"),
    ]

    lines = ["CROSS-MARKET ANOMALY SIGNAL", "=" * 44, ""]
    for label, value in rows:
        if label == "":
            lines.append("")
        elif label in ("Market", "Kalshi spike"):
            lines.append("COMPONENT SCORES" if label == "Kalshi spike" else "")
            if label == "Kalshi spike":
                lines.append("=" * 44)
            lines.append(f"{label:<24} {value}")
        else:
            lines.append(f"{label:<24} {value}")

    lines += [
        "",
        "--",
        "Signal validation only — not financial advice.",
    ]
    return "\n".join(lines)


def send_alert(signal: Signal) -> bool:
    """Send email for high-confidence signals. Returns True if sent."""
    if not resend.api_key:
        print("[Alert] No RESEND_API_KEY configured — skipping")
        return False

    if signal.confidence not in ALERT_CONFIDENCE_LEVELS:
        return False

    try:
        resend.Emails.send({
            "from": FROM_ADDRESS,
            "to": TO_ADDRESS,
            "subject": _build_subject(signal),
            "text": _build_body(signal),
        })
        print(f"[Alert] Email sent for {signal.market_ticker} (score={signal.final_score:.2f})")
        return True
    except Exception as e:
        print(f"[Alert] Failed to send email: {e}")
        return False
