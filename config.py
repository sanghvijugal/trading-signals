import os
from dotenv import load_dotenv

load_dotenv()

# Kalshi API (free tier available at kalshi.com)
KALSHI_API_KEY = os.getenv("KALSHI_API_KEY")
KALSHI_BASE_URL = "https://api.elections.kalshi.com/trade-api/v2"

# Optional paid: Unusual Whales (options flow)
UNUSUAL_WHALES_KEY = os.getenv("UNUSUAL_WHALES_KEY")

# Optional free: NewsAPI
NEWSAPI_KEY = os.getenv("NEWSAPI_KEY")

# Database path
DB_PATH = "sqlite:///data/signals.db"

# Signal weights (tune these later based on backtests)
WEIGHTS = {
    "kalshi_spike": 0.30,
    "options_flow": 0.25,
    "divergence": 0.30,
    "news_velocity": 0.15,
}

# Z-score threshold to trigger a Kalshi or Polymarket anomaly
ANOMALY_THRESHOLD = 2.0

# Cross-market divergence threshold — fires even without a volume spike
# 0.20 = Kalshi and Polymarket disagree by 20%+ on same topic
DIVERGENCE_THRESHOLD = 0.20

# Lookback window for z-score baseline (in minutes)
ZSCORE_WINDOW = 60
