"""
Alert Agent — sends email when a high-confidence signal fires.

Uses Gmail SMTP with an app password (no third-party service needed).

Setup:
  1. Go to myaccount.google.com → Security → 2-Step Verification → App passwords
  2. Create an app password (name it "trading-signals")
  3. Add to GitHub Secrets:
       ALERT_EMAIL       — your Gmail address
       GMAIL_APP_PASSWORD — the 16-character app password
"""
import os
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from storage.models import Signal


ALERT_EMAIL = os.getenv("ALERT_EMAIL")
GMAIL_APP_PASSWORD = os.getenv("GMAIL_APP_PASSWORD")

SMTP_HOST = "smtp.gmail.com"
SMTP_PORT = 587

# Only alert on these confidence levels
ALERT_CONFIDENCE_LEVELS = {"high"}


def _build_subject(signal: Signal) -> str:
    direction = signal.direction.upper() if signal.direction else "?"
    return (
        f"[{signal.confidence.upper()}] {direction} signal: "
        f"{signal.market_ticker} → {signal.asset_ticker} "
        f"(score={signal.final_score:.2f})"
    )


def _build_body(signal: Signal) -> str:
    trigger = signal.trigger_source or "unknown"
    poly_score = signal.polymarket_divergence_score or 0
    kalshi_score = signal.kalshi_spike_score or 0
    price_score = signal.price_divergence_score or 0
    vix_score = signal.vix_score or 0
    news_score = signal.news_velocity_score or 0
    macro_score = signal.macro_context_score or 0

    trigger_labels = {
        "kalshi_spike": "Kalshi volume spike",
        "polymarket_spike": "Polymarket volume spike",
        "divergence": "Cross-market divergence (Kalshi vs Polymarket)",
    }
    trigger_desc = trigger_labels.get(trigger, trigger)

    return f"""
CROSS-MARKET ANOMALY SIGNAL
{'='*40}

Market:     {signal.market_ticker}
Asset:      {signal.asset_ticker}
Direction:  {(signal.direction or '?').upper()}
Confidence: {(signal.confidence or '?').upper()}
Score:      {signal.final_score:.3f}
Trigger:    {trigger_desc}
Time (UTC): {signal.generated_at.strftime('%Y-%m-%d %H:%M:%S')}

COMPONENT SCORES
{'='*40}
Kalshi spike:          {kalshi_score:.2f}
Polymarket divergence: {poly_score:.2f}
Price divergence:      {price_score:.2f}
VIX / fear:            {vix_score:.2f}
News velocity:         {news_score:.2f}
Macro context:         {macro_score:.2f}

Asset price at signal: ${signal.price_at_signal:.2f}

--
This is an automated alert from your trading-signals pipeline.
Signal validation only — not financial advice.
""".strip()


def send_alert(signal: Signal) -> bool:
    """
    Send email alert for a signal. Returns True if sent, False otherwise.
    Silently skips if credentials are not configured.
    """
    if not ALERT_EMAIL or not GMAIL_APP_PASSWORD:
        print("[Alert] No credentials configured — skipping email")
        return False

    if signal.confidence not in ALERT_CONFIDENCE_LEVELS:
        return False

    try:
        msg = MIMEMultipart()
        msg["From"] = ALERT_EMAIL
        msg["To"] = ALERT_EMAIL
        msg["Subject"] = _build_subject(signal)
        msg.attach(MIMEText(_build_body(signal), "plain"))

        with smtplib.SMTP(SMTP_HOST, SMTP_PORT) as server:
            server.starttls()
            server.login(ALERT_EMAIL, GMAIL_APP_PASSWORD)
            server.send_message(msg)

        print(f"[Alert] Email sent for {signal.market_ticker} (score={signal.final_score:.2f})")
        return True

    except Exception as e:
        print(f"[Alert] Failed to send email: {e}")
        return False
