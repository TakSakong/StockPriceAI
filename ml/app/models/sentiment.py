"""
NLP 감성 분석 모듈
[뉴스 수집 - 3중 폴백]
  1) yfinance news
  2) Yahoo Finance RSS
  3) Google News RSS

[감성 분석]
  - VADER + 금융 특화 사전
  - FinBERT (선택)
  - Impact Score 가중 EWMA
"""

import re
import warnings
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Any
from urllib.parse import quote

import numpy as np
import pandas as pd
import requests

warnings.filterwarnings("ignore")


_SESSION = requests.Session()
_SESSION.headers.update(
    {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/120.0.0.0 Safari/537.36"
        )
    }
)


def _parse_rss_date(date_str: str) -> datetime:
    for fmt in (
        "%a, %d %b %Y %H:%M:%S %z",
        "%a, %d %b %Y %H:%M:%S GMT",
        "%Y-%m-%dT%H:%M:%SZ",
    ):
        try:
            dt = datetime.strptime(date_str.strip(), fmt)
            return dt.replace(tzinfo=None)
        except ValueError:
            continue
    return datetime.now()


def _parse_yf_news_item(item: dict[str, Any]) -> dict[str, Any] | None:
    try:
        title = publisher = link = ""
        pub_dt = datetime.now()

        content = item.get("content")
        if isinstance(content, dict):
            title = content.get("title", "")
            provider = content.get("provider") or {}
            publisher = provider.get("displayName", "") if isinstance(provider, dict) else ""
            pub_str = content.get("pubDate", "")
            if pub_str:
                try:
                    pub_dt = datetime.fromisoformat(pub_str.replace("Z", "+00:00")).replace(
                        tzinfo=None
                    )
                except Exception:
                    pass
            canonical = content.get("canonicalUrl") or {}
            link = canonical.get("url", "") if isinstance(canonical, dict) else ""

        if not title:
            title = item.get("title", "")
            publisher = item.get("publisher", "")
            pub_time = item.get("providerPublishTime", 0)
            if pub_time:
                try:
                    pub_dt = datetime.fromtimestamp(float(pub_time))
                except Exception:
                    pass
            link = item.get("link", "") or item.get("url", "")

        if not title:
            return None

        hours_ago = max(0.0, (datetime.now() - pub_dt).total_seconds() / 3600)
        return {
            "title": title.strip(),
            "publisher": (publisher or "Unknown").strip(),
            "published_at": pub_dt,
            "url": link,
            "hours_ago": hours_ago,
            "source": "yfinance",
        }
    except Exception:
        return None


def _fetch_yfinance_news(ticker: str, max_news: int = 30) -> list[dict[str, Any]]:
    news_list = []
    try:
        import yfinance as yf

        stock = yf.Ticker(ticker)
        raw = stock.news or []
        for item in raw[:max_news]:
            parsed = _parse_yf_news_item(item)
            if parsed:
                news_list.append(parsed)
    except Exception:
        pass
    return news_list


def _fetch_yahoo_rss(ticker: str, max_news: int = 20) -> list[dict[str, Any]]:
    url = f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={ticker}&region=US&lang=en-US"
    news_list = []
    try:
        resp = _SESSION.get(url, timeout=8)
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.content)
        for item in root.iter("item"):
            try:
                title = (item.findtext("title") or "").strip()
                pub_str = (item.findtext("pubDate") or "").strip()
                link = (item.findtext("link") or "").strip()
                publisher = (item.findtext("source") or "Yahoo Finance").strip()
                if not title:
                    continue
                pub_dt = _parse_rss_date(pub_str) if pub_str else datetime.now()
                hours_ago = max(0.0, (datetime.now() - pub_dt).total_seconds() / 3600)
                news_list.append(
                    {
                        "title": title,
                        "publisher": publisher,
                        "published_at": pub_dt,
                        "url": link,
                        "hours_ago": hours_ago,
                        "source": "yahoo_rss",
                    }
                )
                if len(news_list) >= max_news:
                    break
            except Exception:
                continue
    except Exception:
        pass
    return news_list


def _fetch_google_news_rss(
    ticker: str, company_name: str = "", max_news: int = 15
) -> list[dict[str, Any]]:
    query = company_name if company_name else ticker
    query_enc = quote(f"{query} stock")
    url = f"https://news.google.com/rss/search?q={query_enc}&hl=en-US&gl=US&ceid=US:en"
    news_list = []
    try:
        resp = _SESSION.get(url, timeout=8)
        if resp.status_code != 200:
            return []
        root = ET.fromstring(resp.content)
        for item in root.iter("item"):
            try:
                title = (item.findtext("title") or "").strip()
                pub_str = (item.findtext("pubDate") or "").strip()
                link = (item.findtext("link") or "").strip()
                source_el = item.find("source")
                publisher = (
                    (source_el.text or "").strip() if source_el is not None else "Google News"
                )
                if not title:
                    continue
                if " - " in title:
                    parts = title.rsplit(" - ", 1)
                    title = parts[0].strip()
                    publisher = parts[1].strip()
                pub_dt = _parse_rss_date(pub_str) if pub_str else datetime.now()
                hours_ago = max(0.0, (datetime.now() - pub_dt).total_seconds() / 3600)
                news_list.append(
                    {
                        "title": title,
                        "publisher": publisher,
                        "published_at": pub_dt,
                        "url": link,
                        "hours_ago": hours_ago,
                        "source": "google_rss",
                    }
                )
                if len(news_list) >= max_news:
                    break
            except Exception:
                continue
    except Exception:
        pass
    return news_list


def fetch_news(ticker: str, company_name: str = "", max_news: int = 30) -> list[dict[str, Any]]:
    """yfinance → Yahoo RSS → Google RSS 순서로 뉴스 수집."""
    all_news: list[dict[str, Any]] = []
    seen_titles: set[str] = set()

    for source_fn, args in [
        (_fetch_yfinance_news, (ticker, max_news)),
        (_fetch_yahoo_rss, (ticker, max_news)),
        (_fetch_google_news_rss, (ticker, company_name, max_news)),
    ]:
        if len(all_news) >= max_news:
            break
        try:
            batch = source_fn(*args)  # type: ignore[operator]
            for item in batch:
                norm = re.sub(r"\s+", " ", item["title"].lower().strip())
                key = norm[:60]
                if key not in seen_titles:
                    seen_titles.add(key)
                    all_news.append(item)
        except Exception:
            continue

    all_news.sort(key=lambda x: x.get("hours_ago", 9999))
    return all_news[:max_news]


# ─────────────────────────────────────────────────────────────
# VADER + 금융 특화 사전
# ─────────────────────────────────────────────────────────────

_vader_analyzer = None

_FINANCE_LEXICON = {
    "bullish": 2.5, "uptrend": 2.0, "breakout": 2.0, "rally": 2.0, "surge": 2.5,
    "soar": 2.5, "skyrocket": 3.0, "outperform": 2.0, "beat": 1.5, "exceed": 1.5,
    "record": 1.5, "strong": 1.5, "robust": 1.5, "growth": 1.5, "profit": 1.5,
    "upgrade": 2.0, "overweight": 1.5, "dividend": 1.0, "expansion": 1.5,
    "momentum": 1.2, "catalyst": 1.5, "recovery": 1.5, "rebound": 1.5,
    "acquisition": 0.8, "partnership": 1.0, "innovation": 1.2,
    "bearish": -2.5, "downtrend": -2.0, "breakdown": -2.0, "plunge": -2.5,
    "crash": -3.0, "collapse": -3.0, "underperform": -2.0, "miss": -1.5,
    "disappoint": -2.0, "loss": -1.5, "decline": -1.5, "weak": -1.5,
    "downgrade": -2.0, "underweight": -1.5, "recession": -2.5, "bankruptcy": -3.0,
    "lawsuit": -2.0, "investigation": -2.0, "fraud": -3.0, "scandal": -2.5,
    "layoff": -2.0, "cut": -1.5, "reduce": -1.0, "uncertainty": -1.5,
    "risk": -1.0, "concern": -1.5, "warning": -2.0, "caution": -1.5,
    "volatility": -0.8, "tariff": -1.2, "sanction": -1.5, "recall": -1.5,
}


class _KeywordFallback:
    _POS = {
        "beat", "exceed", "surge", "rise", "gain", "grow", "profit", "bullish", "upgrade",
        "outperform", "strong", "robust", "positive", "rally", "record", "high", "buy",
        "success", "boost", "expand", "increase", "rebound", "recovery", "momentum",
    }
    _NEG = {
        "miss", "fall", "drop", "decline", "loss", "bearish", "downgrade", "underperform",
        "weak", "negative", "crash", "plunge", "cut", "reduce", "risk", "concern",
        "warning", "fear", "sell", "low", "slump", "layoff", "fraud", "recall", "tariff",
    }

    def polarity_scores(self, text: str) -> dict[str, Any]:
        words = set(re.findall(r"\b\w+\b", text.lower()))
        pos = len(words & self._POS)
        neg = len(words & self._NEG)
        total = pos + neg or 1
        compound = (pos - neg) / total
        return {"compound": compound, "pos": pos / total, "neg": neg / total, "neu": 0.5}


def _get_vader() -> Any:
    global _vader_analyzer
    if _vader_analyzer is None:
        try:
            from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

            _vader_analyzer = SentimentIntensityAnalyzer()
            _vader_analyzer.lexicon.update(_FINANCE_LEXICON)
        except ImportError:
            _vader_analyzer = _KeywordFallback()
    return _vader_analyzer


def _scores_to_label(compound: float) -> tuple[str, str]:
    if compound >= 0.05:
        return "POSITIVE", "POSITIVE"
    if compound <= -0.05:
        return "NEGATIVE", "NEGATIVE"
    return "NEUTRAL", "NEUTRAL"


def analyze_sentiment_vader(text: str) -> dict[str, Any]:
    scores = _get_vader().polarity_scores(text)
    compound = scores["compound"]
    label, _ = _scores_to_label(compound)
    return {
        "compound": compound,
        "positive": scores.get("pos", 0),
        "negative": scores.get("neg", 0),
        "neutral": scores.get("neu", 0),
        "label": label,
    }


_finbert_pipeline = None
_finbert_ok: bool | None = None


def _finbert_available() -> bool:
    global _finbert_ok
    if _finbert_ok is None:
        try:
            import transformers  # noqa: F401

            _finbert_ok = True
        except ImportError:
            _finbert_ok = False
    return bool(_finbert_ok)


def _get_finbert() -> Any:
    global _finbert_pipeline
    if _finbert_pipeline is None and _finbert_available():
        try:
            from transformers import pipeline

            _finbert_pipeline = pipeline(
                "text-classification",
                model="ProsusAI/finbert",
                tokenizer="ProsusAI/finbert",
                return_all_scores=True,
                device=-1,
            )
        except Exception:
            _finbert_pipeline = None
    return _finbert_pipeline


def analyze_sentiment_finbert(text: str) -> dict[str, Any]:
    pipe = _get_finbert()
    if pipe is None:
        return analyze_sentiment_vader(text)
    try:
        res = pipe(text[:500])[0]
        scores = {r["label"].lower(): r["score"] for r in res}
        pos = scores.get("positive", 0)
        neg = scores.get("negative", 0)
        neu = scores.get("neutral", 0)
        compound = pos - neg
        label, _ = _scores_to_label(compound)
        return {
            "compound": compound,
            "positive": pos,
            "negative": neg,
            "neutral": neu,
            "label": label,
            "model": "FinBERT",
        }
    except Exception:
        return analyze_sentiment_vader(text)


# ─────────────────────────────────────────────────────────────
# 뉴스 분류 & Impact Score
# ─────────────────────────────────────────────────────────────

_SURPRISE_POSITIVE = [
    "beat", "beats", "exceeded", "surpassed", "topped", "above estimate",
    "above expectation", "better than expected", "record high", "record profit",
    "surprise profit", "earnings surprise", "eps beat", "guidance raised",
    "raised guidance", "upgraded", "upgrade", "outperform", "strong quarter",
]
_SURPRISE_NEGATIVE = [
    "missed", "miss", "below estimate", "below expectation", "worse than expected",
    "profit warning", "guidance cut", "lowered guidance", "downgrade", "downgraded",
    "weak quarter", "disappointing", "disappoints", "revenue shortfall",
    "earnings miss", "eps miss", "slashed forecast",
]
_STRUCTURAL_KEYWORDS = [
    "regulation", "ban", "antitrust", "monopoly", "law", "legislation",
    "patent", "supply chain", "restructure", "paradigm", "technology shift",
    "ai revolution", "trade war", "tariff", "sanction", "embargo",
    "merger", "acquisition", "spinoff", "ipo", "bankruptcy", "default",
    "interest rate", "fed rate", "rate hike", "rate cut", "quantitative",
    "recession", "deflation", "inflation", "pandemic", "war", "geopolitical",
]
_TRANSIENT_KEYWORDS = [
    "rumor", "speculation", "report says", "sources say", "unconfirmed",
    "temporary", "short-term", "one-time", "non-recurring", "exceptional item",
    "weather", "strike ends", "resolved", "settlement", "quarterly blip",
]
_CONTAGION_KEYWORDS = [
    "sector", "industry", "supply chain", "supplier", "customer",
    "contagion", "spillover", "ripple effect", "domino", "systemic",
    "broad market", "index", "etf", "all stocks", "market-wide",
    "peers", "competitor", "rival",
]

_PERSISTENCE_MAP = {
    "surprise_positive": 0.6,
    "surprise_negative": 0.6,
    "structural": 0.9,
    "transient": 0.15,
    "contagion": 0.55,
    "macro": 0.75,
    "general": 0.3,
}

_MACRO_KNOWLEDGE_GRAPH: dict[str, dict[str, float]] = {
    "rate_hike": {
        "Technology": -0.80, "Real Estate": -0.75, "Utilities": -0.60, "Financials": +0.60
    },
    "rate_cut": {
        "Technology": +0.80, "Real Estate": +0.75, "Utilities": +0.55, "Financials": -0.40
    },
    "geopolitical_crisis": {"Energy": +0.90, "Industrials": +0.70, "Technology": -0.60},
    "inflation_surge": {"Energy": +0.80, "Materials": +0.70, "Technology": -0.55},
    "recession": {"Consumer Discretionary": -0.80, "Consumer Staples": +0.50, "Healthcare": +0.45},
    "ai_boom": {"Technology": +0.95, "Utilities": +0.50, "Materials": +0.35},
    "trade_war": {"Technology": -0.70, "Consumer Discretionary": -0.55, "Industrials": -0.60},
}

_MACRO_THEME_TRIGGERS: dict[str, list[str]] = {
    "rate_hike": ["rate hike", "interest rate rise", "fed hike", "hawkish", "tightening"],
    "rate_cut": ["rate cut", "interest rate cut", "dovish", "easing", "lower rates"],
    "geopolitical_crisis": ["war", "conflict", "invasion", "military", "geopolitical", "sanctions"],
    "inflation_surge": ["inflation", "cpi", "pce", "price surge", "hyperinflation", "stagflation"],
    "recession": ["recession", "gdp contraction", "economic downturn", "hard landing"],
    "ai_boom": ["ai", "artificial intelligence", "nvidia", "semiconductor", "gpu", "llm"],
    "trade_war": ["trade war", "tariff", "trade barrier", "export ban", "import restriction"],
}


def classify_news_type(title: str) -> dict[str, Any]:
    t = title.lower()
    pos_hits = sum(1 for kw in _SURPRISE_POSITIVE if kw in t)
    neg_hits = sum(1 for kw in _SURPRISE_NEGATIVE if kw in t)
    if pos_hits > neg_hits and pos_hits > 0:
        news_type = "surprise_positive"
    elif neg_hits > pos_hits and neg_hits > 0:
        news_type = "surprise_negative"
    elif sum(1 for kw in _STRUCTURAL_KEYWORDS if kw in t) >= 1:
        news_type = "structural"
    elif sum(1 for kw in _TRANSIENT_KEYWORDS if kw in t) >= 1:
        news_type = "transient"
    elif sum(1 for kw in _CONTAGION_KEYWORDS if kw in t) >= 2:
        news_type = "contagion"
    else:
        news_type = "general"

    contagion_score = min(1.0, sum(1 for kw in _CONTAGION_KEYWORDS if kw in t) * 0.2)
    return {
        "news_type": news_type,
        "persistence": _PERSISTENCE_MAP[news_type],
        "contagion": round(contagion_score, 2),
    }


def detect_macro_theme(title: str) -> str | None:
    t = title.lower()
    best_theme = None
    best_score = 0
    for theme, keywords in _MACRO_THEME_TRIGGERS.items():
        score = sum(1 for kw in keywords if kw in t)
        if score > best_score:
            best_score, best_theme = score, theme
    return best_theme if best_score > 0 else None


def detect_market_regime(title: str) -> float:
    t = title.lower()
    RISK_OFF_SIGNALS = ["crash", "collapse", "crisis", "panic", "fear", "recession", "war"]
    RISK_ON_SIGNALS = ["bull market", "rally", "record high", "all-time high", "boom"]
    risk_off_hits = sum(1 for kw in RISK_OFF_SIGNALS if kw in t)
    risk_on_hits = sum(1 for kw in RISK_ON_SIGNALS if kw in t)
    if risk_off_hits >= 2:
        return 2.5
    elif risk_off_hits == 1:
        return 1.8
    elif risk_on_hits >= 1:
        return 0.8
    else:
        return 1.2


def compute_impact_score(
    compound: float,
    news_type: str,
    persistence: float,
    contagion: float,
    beta: float = 1.0,
    market_regime: float = 1.2,
    macro_exposure: float = 0.0,
) -> dict[str, Any]:
    surprise_bonus = {
        "surprise_positive": +0.25,
        "surprise_negative": -0.25,
        "structural": +0.10 if compound > 0 else -0.10,
        "transient": 0.0,
        "contagion": +0.05 if compound > 0 else -0.05,
        "macro": +0.08 if compound > 0 else -0.08,
        "general": 0.0,
    }.get(news_type, 0.0)

    S = float(np.clip(compound + surprise_bonus, -1.0, 1.0))
    M = market_regime
    if S < 0 and M > 1.5:
        S = S * (M / 1.2)

    V = max(0.1, float(beta))
    P = float(np.clip(persistence, 0.05, 1.0))
    C = float(np.clip(contagion, 0.0, 1.0))

    I_base = (S * M) * np.sqrt(V) * P
    I_contagion = I_base * (1 + C * 0.5)
    I_macro = macro_exposure * abs(compound) * persistence
    I_final = float(np.clip(I_contagion + I_macro, -3.0, 3.0))

    return {
        "impact_score": round(I_final, 4),
        "S_surprise": round(S, 3),
        "M_regime": round(M, 2),
        "P_persistence": round(P, 3),
    }


def impact_weighted_sentiment(news_df: pd.DataFrame, min_relevance: float = 0.08) -> float:
    if news_df.empty or "impact_score" not in news_df.columns:
        return 0.0
    df = news_df[news_df["relevance"] >= min_relevance].copy()
    if df.empty:
        return 0.0
    time_decay = np.exp(-df["hours_ago"].fillna(36) / 36)
    impact_w = df["impact_score"].abs().clip(0.01, 3.0)
    combined = time_decay * impact_w
    total_w = combined.sum()
    if total_w < 1e-9:
        return 0.0
    direction = np.sign(df["impact_score"])
    magnitude = (df["impact_score"].abs() * combined).sum() / total_w
    sign_avg = (direction * combined).sum() / total_w
    return float(np.clip(sign_avg * magnitude * 0.5, -1.0, 1.0))


_SECTOR_KEYWORDS: dict[str, list[str]] = {
    "Technology": ["tech", "software", "hardware", "chip", "semiconductor", "ai", "cloud", "gpu"],
    "Financials": ["bank", "finance", "interest rate", "fed", "credit", "loan", "insurance"],
    "Healthcare": ["drug", "fda", "clinical trial", "biotech", "pharma", "vaccine", "medical"],
    "Energy": ["oil", "gas", "crude", "opec", "energy", "refinery", "pipeline", "renewable"],
    "Consumer Discretionary": ["retail", "consumer", "spending", "e-commerce", "housing", "auto"],
    "Consumer Staples": ["grocery", "food", "beverage", "household", "staples"],
    "Industrials": ["manufacturing", "aerospace", "defense", "logistics", "infrastructure"],
    "Materials": ["mining", "commodity", "steel", "copper", "gold", "lithium", "chemical"],
    "Real Estate": ["reit", "property", "real estate", "rent", "mortgage"],
    "Utilities": ["power", "electric", "utility", "water", "grid", "nuclear"],
    "Communication Services": ["media", "streaming", "telecom", "5g", "content", "advertising"],
}

_MARKET_KEYWORDS = [
    "market", "stock", "wall street", "s&p", "nasdaq", "dow", "fed", "inflation",
    "interest rate", "economy", "gdp", "recession", "earnings season",
]


def compute_relevance(
    title: str,
    ticker: str,
    company_name: str = "",
    sector: str = "",
    beta: float = 1.0,
) -> dict[str, Any]:
    t = title.lower()

    ntype_info = classify_news_type(title)
    news_type = ntype_info["news_type"]
    persistence = ntype_info["persistence"]
    contagion_raw = ntype_info["contagion"]

    macro_theme = detect_macro_theme(title)
    macro_exposure = 0.0
    if macro_theme and sector and sector in _MACRO_KNOWLEDGE_GRAPH.get(macro_theme, {}):
        macro_exposure = _MACRO_KNOWLEDGE_GRAPH[macro_theme][sector]

    market_regime = detect_market_regime(title)

    aliases: set[str] = set()
    aliases.add(ticker.replace(".KS", "").replace(".KQ", "").upper())
    if company_name:
        aliases.add(company_name)
        short = re.sub(
            r"\b(Inc\.?|Corp\.?|Ltd\.?|LLC\.?|Co\.?|Group|Holdings?|Technologies|Technology)\b",
            "",
            company_name,
            flags=re.IGNORECASE,
        ).strip().rstrip(",.")
        if short and len(short) > 2:
            aliases.add(short)

    aliases.discard("")
    direct_hits = sum(
        1
        for alias in aliases
        if re.search(r"\b" + re.escape(alias.lower()) + r"\b", t)
    )

    if direct_hits > 0:
        base_score = min(0.70 + direct_hits * 0.12, 1.0)
        if news_type in ("surprise_positive", "surprise_negative"):
            base_score = min(base_score + 0.08, 1.0)
        return {
            "relevance": round(base_score, 3),
            "relevance_tier": "직접",
            "news_type": news_type,
            "persistence": persistence,
            "contagion": contagion_raw,
            "macro_theme": macro_theme,
            "macro_exposure": round(macro_exposure, 2),
            "market_regime": market_regime,
        }

    if macro_theme and abs(macro_exposure) > 0.3:
        macro_score = min(0.35 + abs(macro_exposure) * 0.55, 0.90)
        if news_type == "structural":
            macro_score = min(macro_score + 0.08, 0.90)
        return {
            "relevance": round(macro_score, 3),
            "relevance_tier": "매크로",
            "news_type": news_type,
            "persistence": persistence,
            "contagion": contagion_raw,
            "macro_theme": macro_theme,
            "macro_exposure": round(macro_exposure, 2),
            "market_regime": market_regime,
        }

    if sector and sector in _SECTOR_KEYWORDS:
        sector_hits = sum(1 for kw in _SECTOR_KEYWORDS[sector] if kw in t)
        if sector_hits > 0:
            sector_score = min(0.28 + sector_hits * 0.10, 0.65)
            return {
                "relevance": round(sector_score, 3),
                "relevance_tier": "섹터",
                "news_type": news_type,
                "persistence": persistence,
                "contagion": contagion_raw,
                "macro_theme": macro_theme,
                "macro_exposure": round(macro_exposure, 2),
                "market_regime": market_regime,
            }

    market_hits = sum(1 for kw in _MARKET_KEYWORDS if kw in t)
    if market_hits > 0:
        mkt_score = min(0.08 + market_hits * 0.05, 0.30)
        return {
            "relevance": round(mkt_score, 3),
            "relevance_tier": "시장",
            "news_type": news_type,
            "persistence": persistence,
            "contagion": contagion_raw,
            "macro_theme": macro_theme,
            "macro_exposure": round(macro_exposure, 2),
            "market_regime": market_regime,
        }

    return {
        "relevance": 0.03,
        "relevance_tier": "무관",
        "news_type": news_type,
        "persistence": persistence,
        "contagion": contagion_raw,
        "macro_theme": macro_theme,
        "macro_exposure": round(macro_exposure, 2),
        "market_regime": market_regime,
    }


def analyze_news_sentiment(
    ticker: str,
    company_name: str = "",
    sector: str = "",
    use_finbert: bool = False,
    max_news: int = 30,
    min_relevance: float = 0.08,
    beta: float = 1.0,
) -> tuple[pd.DataFrame, dict[str, Any]]:
    """뉴스 수집 → 분류 → Impact Score → 가중 감성 점수"""
    _empty = {
        "avg_sentiment": 0.0,
        "raw_avg": 0.0,
        "time_weighted_avg": 0.0,
        "impact_score_avg": 0.0,
        "positive_pct": 0.0,
        "negative_pct": 0.0,
        "neutral_pct": 0.0,
        "news_count": 0,
        "direct_news_count": 0,
        "sector_news_count": 0,
        "surprise_count": 0,
        "structural_count": 0,
        "transient_count": 0,
        "macro_themes": [],
        "model": "N/A",
        "signal": "NEUTRAL",
        "sources": [],
    }

    news_list = fetch_news(ticker, company_name=company_name, max_news=max_news)
    if not news_list:
        return pd.DataFrame(), _empty

    use_fb = use_finbert and _finbert_available()
    analyze_fn = analyze_sentiment_finbert if use_fb else analyze_sentiment_vader
    model_name = "FinBERT" if use_fb else "VADER + Impact Framework"

    rows = []
    for item in news_list:
        sent = analyze_fn(item["title"])
        rel = compute_relevance(
            title=item["title"],
            ticker=ticker,
            company_name=company_name,
            sector=sector,
            beta=beta,
        )
        imp = compute_impact_score(
            compound=sent["compound"],
            news_type=rel["news_type"],
            persistence=rel["persistence"],
            contagion=rel["contagion"],
            beta=beta,
            market_regime=rel["market_regime"],
            macro_exposure=rel["macro_exposure"],
        )
        rows.append(
            {
                "title": item["title"],
                "publisher": item["publisher"],
                "published_at": item["published_at"],
                "hours_ago": item["hours_ago"],
                "source": item.get("source", "unknown"),
                "compound": sent["compound"],
                "label": sent["label"],
                "positive": sent["positive"],
                "negative": sent["negative"],
                "neutral": sent["neutral"],
                "relevance": rel["relevance"],
                "relevance_tier": rel["relevance_tier"],
                "news_type": rel["news_type"],
                "persistence": rel["persistence"],
                "contagion": rel["contagion"],
                "macro_theme": rel["macro_theme"],
                "macro_exposure": rel["macro_exposure"],
                "market_regime": rel["market_regime"],
                "impact_score": imp["impact_score"],
                "S_surprise": imp["S_surprise"],
                "M_regime": imp["M_regime"],
                "P_persistence": imp["P_persistence"],
            }
        )

    news_df = pd.DataFrame(rows)

    time_w = np.exp(-news_df["hours_ago"].fillna(36) / 36)
    time_w_norm = time_w / time_w.sum()
    time_avg = float((news_df["compound"] * time_w_norm).sum())
    impact_avg = impact_weighted_sentiment(news_df, min_relevance)

    total = len(news_df)
    pos_c = int((news_df["label"] == "POSITIVE").sum())
    neg_c = int((news_df["label"] == "NEGATIVE").sum())
    neu_c = int((news_df["label"] == "NEUTRAL").sum())
    direct_c = int((news_df["relevance_tier"] == "직접").sum())
    sector_c = int((news_df["relevance_tier"] == "섹터").sum())
    surp_c = int(news_df["news_type"].isin(["surprise_positive", "surprise_negative"]).sum())
    struct_c = int((news_df["news_type"] == "structural").sum())
    trans_c = int((news_df["news_type"] == "transient").sum())
    sources = news_df["source"].unique().tolist()
    macro_themes = [t for t in news_df["macro_theme"].dropna().unique().tolist() if t]
    imp_score_avg = float(news_df["impact_score"].mean()) if not news_df.empty else 0.0

    score = impact_avg if abs(impact_avg) > 0.01 else time_avg
    if score > 0.10:
        signal = "BULLISH"
    elif score < -0.10:
        signal = "BEARISH"
    else:
        signal = "NEUTRAL"

    summary = {
        "avg_sentiment": round(impact_avg, 4),
        "time_weighted_avg": round(time_avg, 4),
        "raw_avg": round(float(news_df["compound"].mean()), 4),
        "impact_score_avg": round(imp_score_avg, 4),
        "positive_pct": round(pos_c / total * 100, 1),
        "negative_pct": round(neg_c / total * 100, 1),
        "neutral_pct": round(neu_c / total * 100, 1),
        "news_count": total,
        "direct_news_count": direct_c,
        "sector_news_count": sector_c,
        "surprise_count": surp_c,
        "structural_count": struct_c,
        "transient_count": trans_c,
        "macro_themes": macro_themes,
        "model": model_name,
        "signal": signal,
        "sources": sources,
    }

    return news_df, summary


def add_sentiment_to_features(df: pd.DataFrame, sentiment_score: float) -> pd.DataFrame:
    """Impact 감성 점수를 ML 피처로 추가."""
    df = df.copy()
    df["Sentiment_Score"] = sentiment_score
    df["Sentiment_Positive"] = max(0.0, sentiment_score)
    df["Sentiment_Negative"] = max(0.0, -sentiment_score)
    return df
