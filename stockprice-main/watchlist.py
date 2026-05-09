"""
관심 종목 모듈
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
- watchlist.json 에 종목 저장 (영구)
- 종목별 빠른 시세 / 기술 지표 / 뉴스 요약
- 전체 관심종목 일괄 새로고침
"""

import json
import os
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

WATCHLIST_FILE = "watchlist.json"


# ─────────────────────────────────────────────────────────────
# 저장 / 불러오기
# ─────────────────────────────────────────────────────────────

def _load_raw() -> Dict:
    if not os.path.exists(WATCHLIST_FILE):
        return {"tickers": [], "memos": {}, "added_at": {}}
    try:
        with open(WATCHLIST_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        # 구버전 호환
        if isinstance(data, list):
            data = {"tickers": data, "memos": {}, "added_at": {}}
        data.setdefault("tickers",  [])
        data.setdefault("memos",    {})
        data.setdefault("added_at", {})
        return data
    except Exception:
        return {"tickers": [], "memos": {}, "added_at": {}}


def _save_raw(data: Dict) -> None:
    try:
        with open(WATCHLIST_FILE, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    except Exception:
        pass


# ─────────────────────────────────────────────────────────────
# CRUD
# ─────────────────────────────────────────────────────────────

def load_watchlist() -> List[str]:
    """관심 종목 리스트 반환 (순서 유지)."""
    return _load_raw()["tickers"]


def add_ticker(ticker: str, memo: str = "") -> bool:
    """
    관심 종목 추가.
    Returns True if 새로 추가됨, False if 이미 있음.
    """
    ticker = ticker.strip().upper()
    data   = _load_raw()
    if ticker in data["tickers"]:
        return False
    data["tickers"].append(ticker)
    data["memos"][ticker]    = memo
    data["added_at"][ticker] = datetime.now().isoformat()
    _save_raw(data)
    return True


def remove_ticker(ticker: str) -> bool:
    """관심 종목 삭제. Returns True if 삭제됨."""
    ticker = ticker.strip().upper()
    data   = _load_raw()
    if ticker not in data["tickers"]:
        return False
    data["tickers"].remove(ticker)
    data["memos"].pop(ticker, None)
    data["added_at"].pop(ticker, None)
    _save_raw(data)
    return True


def update_memo(ticker: str, memo: str) -> None:
    ticker = ticker.strip().upper()
    data   = _load_raw()
    data["memos"][ticker] = memo
    _save_raw(data)


def get_memo(ticker: str) -> str:
    data = _load_raw()
    return data["memos"].get(ticker.upper(), "")


def get_added_at(ticker: str) -> str:
    data = _load_raw()
    iso  = data["added_at"].get(ticker.upper(), "")
    if iso:
        try:
            return datetime.fromisoformat(iso).strftime("%Y-%m-%d")
        except Exception:
            pass
    return ""


def is_in_watchlist(ticker: str) -> bool:
    return ticker.strip().upper() in load_watchlist()


# ─────────────────────────────────────────────────────────────
# 종목 빠른 시세 스냅샷
# ─────────────────────────────────────────────────────────────

def _safe_float(v, default=None):
    try:
        f = float(v)
        return f if not (f != f) else default   # NaN 체크
    except Exception:
        return default


def fetch_quick_snapshot(ticker: str) -> Dict:
    """
    yfinance로 종목 핵심 정보 빠르게 수집.
    차트용 90일 가격 포함.
    """
    result = {
        "ticker":        ticker,
        "name":          ticker,
        "price":         None,
        "change_pct":    None,
        "prev_close":    None,
        "volume":        None,
        "market_cap":    None,
        "pe_ratio":      None,
        "week52_high":   None,
        "week52_low":    None,
        "sector":        "",
        "industry":      "",
        "currency":      "USD",
        "hist_90d":      None,   # pd.DataFrame or None
        "rsi14":         None,
        "ma20":          None,
        "ma50":          None,
        "signal":        "N/A",
        "error":         None,
        "fetched_at":    datetime.now().isoformat(),
    }

    try:
        stock = yf.Ticker(ticker)
        info  = stock.info or {}

        result["name"]       = info.get("longName") or info.get("shortName") or ticker
        result["price"]      = _safe_float(info.get("regularMarketPrice") or info.get("currentPrice"))
        result["change_pct"] = _safe_float(info.get("regularMarketChangePercent"))
        result["prev_close"] = _safe_float(info.get("regularMarketPreviousClose"))
        result["volume"]     = _safe_float(info.get("regularMarketVolume"))
        result["market_cap"] = _safe_float(info.get("marketCap"))
        result["pe_ratio"]   = _safe_float(info.get("trailingPE"))
        result["week52_high"]= _safe_float(info.get("fiftyTwoWeekHigh"))
        result["week52_low"] = _safe_float(info.get("fiftyTwoWeekLow"))
        result["sector"]     = info.get("sector", "")
        result["industry"]   = info.get("industry", "")
        result["currency"]   = info.get("currency", "USD")

        # 90일 가격 (미니 차트 + RSI 계산용)
        # yfinance 0.2.54+: tz-aware index → tz-naive로 정규화
        hist = stock.history(period="3mo", auto_adjust=True)
        if not hist.empty and len(hist) >= 14:
            hist.index = pd.to_datetime(hist.index)
            # tz-aware → tz-naive (Plotly 호환)
            if hist.index.tz is not None:
                hist.index = hist.index.tz_convert("UTC").tz_localize(None)
            result["hist_90d"] = hist[["Open","High","Low","Close","Volume"]].copy()

            close = hist["Close"]
            result["ma20"] = _safe_float(close.rolling(20).mean().iloc[-1])
            result["ma50"] = _safe_float(close.rolling(50).mean().iloc[-1])

            # RSI-14
            delta = close.diff()
            gain  = delta.clip(lower=0).ewm(com=13, min_periods=14).mean()
            loss  = (-delta.clip(upper=0)).ewm(com=13, min_periods=14).mean()
            rs    = gain / loss.replace(0, np.nan)
            rsi   = float((100 - 100 / (1 + rs)).iloc[-1])
            result["rsi14"] = round(rsi, 1)

            # ── 기술 지표 기반 종합 신호 (전체 분석과 동일 로직) ──────
            # get_current_signals()와 동일한 6개 지표 투표 방식
            p   = float(result["price"] or 0)
            m20 = float(result["ma20"] or 0)
            m50 = float(result["ma50"] or 0)

            buy_votes  = 0
            sell_votes = 0

            # 1. RSI
            if   rsi < 30: buy_votes  += 2   # 강한 과매도
            elif rsi < 40: buy_votes  += 1
            elif rsi > 70: sell_votes += 2   # 강한 과매수
            elif rsi > 60: sell_votes += 1

            # 2. MA 정배열/역배열
            if   p > m20 > m50: buy_votes  += 2
            elif p < m20 < m50: sell_votes += 2
            elif p > m20:       buy_votes  += 1
            elif p < m20:       sell_votes += 1

            # 3. 볼린저 밴드 위치 (있는 경우)
            if len(close) >= 20:
                bb_mid   = float(close.rolling(20).mean().iloc[-1])
                bb_std   = float(close.rolling(20).std().iloc[-1])
                bb_upper = bb_mid + 2 * bb_std
                bb_lower = bb_mid - 2 * bb_std
                bb_range = bb_upper - bb_lower
                if bb_range > 0:
                    bb_pos = (p - bb_lower) / bb_range
                    if   bb_pos < 0.05: buy_votes  += 1
                    elif bb_pos > 0.95: sell_votes += 1

            # 4. MACD (있는 경우)
            if len(close) >= 26:
                ema12 = float(close.ewm(span=12, adjust=False).mean().iloc[-1])
                ema26 = float(close.ewm(span=26, adjust=False).mean().iloc[-1])
                if   ema12 > ema26: buy_votes  += 1
                elif ema12 < ema26: sell_votes += 1

            # 5. 스토캐스틱 (있는 경우)
            if len(hist) >= 14:
                high14 = hist["High"].rolling(14).max().iloc[-1]
                low14  = hist["Low"].rolling(14).min().iloc[-1]
                if high14 != low14:
                    stoch_k = 100 * (p - low14) / (high14 - low14)
                    if   stoch_k < 20: buy_votes  += 1
                    elif stoch_k > 80: sell_votes += 1

            # 투표 결과로 신호 결정
            if   buy_votes > sell_votes and buy_votes >= 2:
                result["signal"] = "BUY"
            elif sell_votes > buy_votes and sell_votes >= 2:
                result["signal"] = "SELL"
            else:
                result["signal"] = "HOLD"

            result["signal_votes"] = {"buy": buy_votes, "sell": sell_votes}

    except Exception as e:
        result["error"] = str(e)

    return result


# ─────────────────────────────────────────────────────────────
# 뉴스 요약 (관심종목용)
# ─────────────────────────────────────────────────────────────

def fetch_news_summary(
    ticker: str,
    company_name: str = "",
    sector: str = "",
    max_news: int = 8,
) -> Tuple[List[Dict], Dict]:
    """
    관심종목 뉴스 빠른 수집 + VADER 감성 분석.
    Returns (news_list, summary_dict)
    """
    from sentiment import fetch_news, analyze_sentiment_vader, compute_relevance

    news_raw = fetch_news(ticker, company_name=company_name, max_news=max_news)

    if not news_raw:
        return [], {"signal": "NEUTRAL", "avg_score": 0.0, "count": 0}

    analyzed = []
    for item in news_raw:
        sent = analyze_sentiment_vader(item["title"])
        rel  = compute_relevance(
            title=item["title"], ticker=ticker,
            company_name=company_name, sector=sector,
        )
        analyzed.append({
            "title":          item["title"],
            "publisher":      item["publisher"],
            "hours_ago":      item.get("hours_ago", 0),
            "url":            item.get("url", ""),
            "compound":       sent["compound"],
            "label":          sent["label"],
            "emoji":          sent["emoji"],
            "relevance":      rel["relevance"],
            "relevance_tier": rel["relevance_tier"],
            "relevance_icon": rel["relevance_icon"],
        })

    # 연관도×시간 가중 평균
    if analyzed:
        arr     = pd.DataFrame(analyzed)
        time_w  = np.exp(-arr["hours_ago"].fillna(48) / 48)
        rel_w   = arr["relevance"].clip(0, 1)
        w       = time_w * rel_w
        total_w = w.sum()
        avg_score = float((arr["compound"] * w).sum() / total_w) if total_w > 0 else 0.0
    else:
        avg_score = 0.0

    if   avg_score >  0.12: signal = "BULLISH"
    elif avg_score < -0.12: signal = "BEARISH"
    else:                    signal = "NEUTRAL"

    summary = {
        "signal":    signal,
        "avg_score": round(avg_score, 3),
        "count":     len(analyzed),
        "direct":    sum(1 for a in analyzed if a["relevance_tier"] == "직접"),
    }
    return analyzed, summary


# ─────────────────────────────────────────────────────────────
# 전체 관심종목 일괄 새로고침
# ─────────────────────────────────────────────────────────────

def refresh_all_snapshots(
    tickers: List[str],
    progress_callback=None,
) -> Dict[str, Dict]:
    """
    관심종목 전체 스냅샷을 순차 수집.
    progress_callback(done, total, ticker) → None
    """
    from concurrent.futures import ThreadPoolExecutor, as_completed
    import time

    results = {}
    total   = len(tickers)
    done    = 0

    with ThreadPoolExecutor(max_workers=5) as ex:
        futures = {ex.submit(fetch_quick_snapshot, t): t for t in tickers}
        for future in as_completed(futures):
            ticker = futures[future]
            done  += 1
            try:
                results[ticker] = future.result(timeout=30)
            except Exception as e:
                results[ticker] = {"ticker": ticker, "error": str(e),
                                   "name": ticker, "price": None, "change_pct": None}
            if progress_callback:
                progress_callback(done, total, ticker)
            time.sleep(0.05)

    return results


# ─────────────────────────────────────────────────────────────
# 포맷 유틸
# ─────────────────────────────────────────────────────────────

def fmt_price(v, currency="USD") -> str:
    if v is None:
        return "—"
    sym = {"USD": "$", "KRW": "₩", "EUR": "€", "JPY": "¥"}.get(currency, "")
    if currency == "KRW":
        return f"{sym}{v:,.0f}"
    return f"{sym}{v:,.2f}"


def fmt_mktcap(v) -> str:
    if v is None:
        return "—"
    if v >= 1e12: return f"${v/1e12:.1f}T"
    if v >= 1e9:  return f"${v/1e9:.1f}B"
    return f"${v/1e6:.0f}M"


def fmt_change(v) -> str:
    if v is None:
        return "—"
    arrow = "▲" if v >= 0 else "▼"
    return f"{arrow} {abs(v):.2f}%"


def change_color(v) -> str:
    if v is None:
        return "#94a3b8"
    return "#10b981" if v >= 0 else "#ef4444"