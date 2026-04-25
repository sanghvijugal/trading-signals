"""
News Velocity Agent.

Uses NewsAPI free tier (100 req/day): https://newsapi.org/
Sign up for a free key and add NEWSAPI_KEY to your .env file.

Without a key, this agent returns 0 counts and logs a warning.
"""
import requests
from datetime import datetime
from config import NEWSAPI_KEY
from storage.db import get_session
from storage.models import NewsEvent


# Topics to track — map these to your Kalshi markets
TOPICS = [
    "federal reserve",
    "S&P 500",
    "interest rates",
]

# Typical baseline: how many articles per poll is "normal"
# Tune this after a few days of observation
BASELINE_ARTICLES = 5


def simple_sentiment(text: str) -> float:
    """
    Naive keyword sentiment. Returns -1.0 to +1.0.
    Replace with a proper model (e.g. finbert) once data is flowing.
    """
    positive = ["rise", "surge", "beat", "rally", "gain", "bullish", "strong", "growth"]
    negative = ["fall", "drop", "miss", "crash", "loss", "bearish", "weak", "recession"]

    text_lower = text.lower()
    pos = sum(1 for w in positive if w in text_lower)
    neg = sum(1 for w in negative if w in text_lower)

    total = pos + neg
    if total == 0:
        return 0.0
    return round((pos - neg) / total, 4)


def fetch_articles(topic: str, page_size: int = 10) -> list[dict]:
    if not NEWSAPI_KEY:
        return []

    url = (
        f"https://newsapi.org/v2/everything"
        f"?q={requests.utils.quote(topic)}"
        f"&sortBy=publishedAt"
        f"&pageSize={page_size}"
        f"&apiKey={NEWSAPI_KEY}"
    )
    resp = requests.get(url, timeout=10)
    if resp.status_code != 200:
        print(f"[News] Failed for topic '{topic}': {resp.status_code}")
        return []

    return resp.json().get("articles", [])


def run() -> dict[str, int]:
    """
    Fetch recent article counts per topic.
    Stores top-5 headlines per topic.
    Returns dict of topic -> article count.
    """
    if not NEWSAPI_KEY:
        print("[News] No NEWSAPI_KEY set — skipping news agent. Add it to .env to enable.")
        return {t: 0 for t in TOPICS}

    counts: dict[str, int] = {}
    session = get_session()

    for topic in TOPICS:
        articles = fetch_articles(topic)
        counts[topic] = len(articles)

        for article in articles[:5]:
            headline = article.get("title", "")
            event = NewsEvent(
                topic=topic,
                headline=headline,
                source=article.get("source", {}).get("name"),
                sentiment_score=simple_sentiment(headline),
            )
            session.add(event)

        print(f"[News] '{topic}': {len(articles)} articles")

    session.commit()
    session.close()
    return counts
