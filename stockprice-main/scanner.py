"""
S&P 500 배치 스캐너 v5  — ThreadPoolExecutor + 전체 앙상블
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

[설계 원칙]
  ProcessPoolExecutor는 Streamlit 안에서 spawn pickling 오류로 silent fail
  → ThreadPoolExecutor 복귀, 대신 MPS 충돌 완전 방지

[앙상블 전략]
  scanner_mode=True + LSTM CPU 강제:
    - XGBoost: nthread=1 (OMP 경합 없음)
    - LSTM:    device='cpu', num_threads=1 (MPS 동시 접근 없음)
    - 워커 2개 × (XGB 1스레드 + LSTM CPU 1스레드) = 완전 안전
    - 종목당 30~90초, 500종목 약 2~4시간 (처음 1회)
    - 이후 DP 캐시로 수 분으로 단축

[캐시 시스템]
  - scan_cache.json, TTL 24h
  - 가격 2% 변동 시 재분석
  - DP EWMA 블렌딩 (alpha=0.3)
"""

import json
import os
import sys
import time
import logging
import warnings
import traceback
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timedelta
from typing import Dict, List, Optional, Tuple

import numpy as np
import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

# 전역 OMP 스레드 수 제한 (nthread=1이므로 1로 고정)
os.environ.setdefault("OMP_NUM_THREADS",      "1")
os.environ.setdefault("OPENBLAS_NUM_THREADS", "1")
os.environ.setdefault("MKL_NUM_THREADS",      "1")
os.environ.setdefault("VECLIB_MAXIMUM_THREADS","1")

# ─────────────────────────────────────────────────────────────
# 터미널 로거
# ─────────────────────────────────────────────────────────────
log = logging.getLogger("stock_analyzer")
if not log.handlers:
    _h = logging.StreamHandler(sys.stdout)
    class _CF(logging.Formatter):
        def format(self, r):
            ts    = datetime.now().strftime("%H:%M:%S")
            color = "\033[93m" if r.levelno >= logging.WARNING else "\033[96m"
            return f"\033[1m[{ts}]\033[0m {color}{r.getMessage()}\033[0m"
    _h.setFormatter(_CF())
    log.addHandler(_h)
    log.setLevel(logging.DEBUG)
    log.propagate = False


# ─────────────────────────────────────────────────────────────
# 상수
# ─────────────────────────────────────────────────────────────
CACHE_FILE   = "scan_cache.json"
CACHE_TTL_H  = 24
EWMA_ALPHA   = 0.3

# 타임아웃: LSTM 포함 시 종목당 최대 600초
WORKER_TIMEOUT_SEC = 600


# ─────────────────────────────────────────────────────────────
# S&P 500 종목 리스트
# ─────────────────────────────────────────────────────────────
SP500_TICKERS = [
    "AAPL","MSFT","NVDA","AVGO","META","GOOGL","GOOG","TSLA","ORCL","CRM",
    "AMD","QCOM","TXN","INTC","ADI","MU","AMAT","LRCX","KLAC","MRVL",
    "CDNS","SNPS","FTNT","PANW","CRWD","NOW","ADSK","ANSS","GDDY","PAYC",
    "TTWO","EA","AKAM","CTSH","EPAM","FFIV","JNPR","NTAP","STX","WDC",
    "HPE","HPQ","DELL","CSCO","IBM","ACN","INTU","FSLR","GLW","KEYS",
    "BRK-B","JPM","V","MA","BAC","WFC","GS","MS","AXP","BLK",
    "SCHW","USB","PNC","TFC","COF","SPGI","MCO","ICE","CME","CBOE",
    "AON","MMC","AJG","BRO","WTW","AFL","MET","PRU","ALL","CB",
    "TRV","PGR","HIG","LNC","UNM","GL","FAF","RLI","ESGR","ARGO",
    "LLY","UNH","JNJ","MRK","ABBV","TMO","ABT","DHR","BMY","AMGN",
    "GILD","CVS","CI","HUM","ELV","CNC","MOH","MDT","SYK","BSX",
    "EW","ISRG","RMD","DXCM","IDXX","IQV","BDX","ZBH","HOLX","ALGN",
    "VTRS","CTLT","WBA","CAH","MCK","ABC","HSIC","PDCO","AMED","ACAD",
    "AMZN","HD","MCD","NKE","SBUX","TJX","LOW","BKNG","CMG","MAR",
    "HLT","CCL","RCL","NCLH","MGM","CZR","WYNN","LVS","F","GM",
    "TSCO","ROST","DLTR","DG","BBY","KMX","AN","PAG","AZO","ORLY",
    "ULTA","LEN","PHM","DHI","NVR","TOL","GRBK","SKY","LGIH","MDC",
    "PG","KO","PEP","COST","WMT","PM","MO","CL","MDLZ","KHC",
    "GIS","K","CPB","SJM","CAG","HRL","MKC","CHD","CLX","EL",
    "BMS","PKG","IP","WRK","SLVM","SON","SEE","REYN","PTVE","RANPAK",
    "XOM","CVX","COP","EOG","SLB","MPC","PSX","VLO","PXD","DVN",
    "HES","HAL","BKR","FANG","OXY","APA","MRO","NFG","SWN","RRC",
    "CNX","AR","EQT","CHK","CTRA","SM","MGY","MTDR","VTLE","ESTE",
    "CAT","HON","UPS","BA","RTX","LMT","NOC","GD","DE","EMR",
    "ETN","ROK","AME","FTV","CARR","OTIS","TDG","HWM","GE","GEV",
    "WM","RSG","WCN","CTAS","PAYX","ADP","VRSK","LDOS","SAIC","BAH",
    "CACI","FLR","J","PWR","MTZ","PRIM","STRL","ROAD","DY","MYR",
    "LIN","APD","SHW","FCX","NEM","NUE","STLD","RS","CMC","ATI",
    "AA","ALB","CC","OLN","ECL","PPG","RPM","IFF","EMN","CE",
    "HUN","DOW","LYB","WLK","TROX","MEOH","HWKN","ASIX","SLCA","IOSP",
    "AMT","PLD","EQIX","CCI","SPG","PSA","EXR","WELL","VTR","ARE",
    "BXP","SLG","KIM","REG","FRT","MAC","SKT","RPT","SITC","CBL",
    "NEE","DUK","SO","D","EXC","AEP","SRE","PCG","XEL","WEC",
    "ES","ETR","PPL","EIX","AEE","CMS","NI","LNT","EVRG","PNW",
    "NFLX","DIS","CMCSA","T","VZ","TMUS","CHTR","PARA","WBD","FOX",
    "FOXA","NWSA","NWS","IPG","OMC","TTWO","MTCH","IAC","ANGI","YELP",
]
SP500_TICKERS = list(dict.fromkeys(SP500_TICKERS))[:500]


# ─────────────────────────────────────────────────────────────
# 캐시
# ─────────────────────────────────────────────────────────────

def load_cache() -> Dict:
    if not os.path.exists(CACHE_FILE):
        return {}
    try:
        with open(CACHE_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except Exception:
        return {}


def save_cache(cache: Dict) -> None:
    try:
        with open(CACHE_FILE, "w", encoding="utf-8") as f:
            json.dump(cache, f, ensure_ascii=False, indent=2, default=str)
    except Exception:
        pass


def is_cache_valid(entry: Dict, ttl_hours: float = CACHE_TTL_H) -> bool:
    try:
        t = datetime.fromisoformat(entry["cached_at"])
        return datetime.now() - t < timedelta(hours=ttl_hours)
    except Exception:
        return False


def get_latest_close(ticker: str) -> Optional[float]:
    try:
        hist = yf.Ticker(ticker).history(period="2d")
        if not hist.empty:
            return float(hist["Close"].iloc[-1])
    except Exception:
        pass
    return None


def price_changed(entry: Dict, threshold_pct: float = 2.0) -> bool:
    cached_price = entry.get("current_price")
    if cached_price is None:
        return True
    latest = get_latest_close(entry["ticker"])
    if latest is None:
        return False
    return abs(latest - cached_price) / cached_price * 100 >= threshold_pct


# ─────────────────────────────────────────────────────────────
# DP 블렌딩
# ─────────────────────────────────────────────────────────────

BLENDABLE = [
    "up_probability", "estimated_upside", "composite_score",
    "rsi", "bb_position", "momentum_pct", "atr_pct",
    "buy_signals", "sell_signals",
]


def dp_blend(old: Dict, new: Dict, alpha: float = EWMA_ALPHA) -> Dict:
    out = new.copy()
    for field in BLENDABLE:
        if field in old and field in new:
            try:
                out[field] = round(
                    alpha * float(new[field]) + (1 - alpha) * float(old[field]), 4
                )
            except (TypeError, ValueError):
                pass
    out["dp_blend_count"]       = old.get("dp_blend_count", 1) + 1
    out["prev_composite_score"] = old.get("composite_score")
    return out


# ─────────────────────────────────────────────────────────────
# 단일 종목 앙상블 분석 (스캐너용)
# ─────────────────────────────────────────────────────────────

def analyze_single_ticker(ticker: str, period_days: int = 400) -> Optional[Dict]:
    """
    XGBoost + LSTM 전체 앙상블 분석.

    scanner_mode=True 사용:
      - XGBoost: nthread=1 (OMP 경합 방지)
      - LSTM: device='cpu', num_threads=1 (MPS 동시 접근 방지)
      - 워커 2개가 동시에 실행해도 충돌 없음
      - 종목당 30~90초 예상
    """
    t0 = time.time()
    try:
        from fetcher   import fetch_stock_data
        from technical import add_all_indicators, get_current_signals
        from predictor import EnsemblePredictor

        df, info = fetch_stock_data(ticker, period_days=period_days)
        if df is None or len(df) < 60:
            log.debug(f"  {ticker}: 데이터 부족 ({len(df) if df is not None else 0}행)")
            return None

        df = add_all_indicators(df)

        # scanner_mode=True:
        #   - XGBoost nthread=1 (XGBOOST_SCANNER 설정)
        #   - LSTM device='cpu' (PYTORCH_SCANNER 설정)
        #   - 멀티스레드 환경에서도 안전
        pred_m  = EnsemblePredictor(scanner_mode=True)
        metrics = pred_m.train(df, include_sentiment=False, force_lstm=False)
        if "error" in metrics:
            log.debug(f"  {ticker}: 모델 학습 실패 — {metrics['error']}")
            return None

        pred = pred_m.predict(df)
        if "error" in pred:
            log.debug(f"  {ticker}: 예측 실패 — {pred['error']}")
            return None

        latest   = df.iloc[-1]
        close    = float(df["Close"].iloc[-1])
        high_52w = float(df["High"].tail(252).max())
        upside52 = (high_52w - close) / close * 100
        atr_pct  = float(latest.get("ATR_Pct", 1.0))
        exp3m    = atr_pct * np.sqrt(63)
        rsi      = float(latest.get("RSI14", 50))
        bb_pos   = float(latest.get("BB_Position", 0.5))
        up_prob  = float(pred["up_probability"])

        est_up = (
            up_prob * exp3m * 0.4
            + max(0.0, (70 - rsi) / 70) * exp3m * 0.3
            + min(upside52, 30) * 0.3
        )

        momentum  = float(latest.get("Momentum_Normalized", 0))
        mom_f     = (0.7 if momentum >  0.15 else
                     0.9 if momentum >  0.05 else
                     1.1 if momentum < -0.10 else 1.0)
        composite = up_prob * est_up * mom_f

        per    = info.get("trailingPE")
        beta   = float(info.get("beta", 1.0) or 1.0)
        mktcap = float(info.get("marketCap", 0) or 0)
        qf = ((0.8 if mktcap < 1e9 else 1.0)
              * (0.7 if per and per < 0 else 1.0)
              * (0.8 if beta > 3 else 1.0))
        composite *= qf

        signals      = get_current_signals(df)
        buy_signals  = sum(1 for s, _, _ in signals.values() if s == "BUY")
        sell_signals = sum(1 for s, _, _ in signals.values() if s == "SELL")
        now_iso      = datetime.now().isoformat()

        elapsed = time.time() - t0
        model_label = metrics.get("model_type", "N/A")
        log.debug(f"  ✅ {ticker:<6} {model_label}  {elapsed:.1f}s")

        return {
            "ticker":               ticker,
            "period_days":          period_days,
            "name":                 info.get("shortName", ticker),
            "sector":               info.get("sector", "N/A"),
            "current_price":        round(close, 2),
            "up_probability":       round(up_prob * 100, 1),
            "estimated_upside":     round(est_up, 1),
            "composite_score":      round(composite, 4),
            "rsi":                  round(rsi, 1),
            "bb_position":          round(bb_pos, 2),
            "momentum_pct":         round(momentum * 100, 1),
            "atr_pct":              round(atr_pct, 2),
            "beta":                 round(beta, 2),
            "market_cap":           mktcap,
            "per":                  round(per, 1) if per else None,
            "buy_signals":          buy_signals,
            "sell_signals":         sell_signals,
            "ml_signal":            pred["signal"],
            "model_type":           model_label,
            "upside_to_52w":        round(upside52, 1),
            "analyzed_at":          now_iso,
            "cached_at":            now_iso,
            "dp_blend_count":       1,
            "prev_composite_score": None,
        }

    except Exception:
        elapsed = time.time() - t0
        log.warning(f"  ❌ {ticker} 오류 ({elapsed:.1f}s):\n{traceback.format_exc()}")
        return None


# ─────────────────────────────────────────────────────────────
# 캐시 처리 래퍼
# ─────────────────────────────────────────────────────────────

def _process_one(
    ticker:              str,
    cache:               Dict,
    force_refresh:       bool,
    price_threshold_pct: float,
    period_days:         int = 400,
) -> Tuple[str, Optional[Dict], str]:
    """캐시 확인 후 필요 시 분석 실행."""
    old = cache.get(ticker)

    if old and old.get("period_days", 400) != period_days:
        force_refresh = True

    if old and not force_refresh and is_cache_valid(old, CACHE_TTL_H):
        if price_changed(old, price_threshold_pct):
            status = "price_changed"
        else:
            return ticker, old, "cached"
    else:
        status = "refreshed"

    new = analyze_single_ticker(ticker, period_days=period_days)
    if new is None:
        return ticker, old, "failed"

    blended = dp_blend(old, new) if old else new
    return ticker, blended, status


# ─────────────────────────────────────────────────────────────
# 진행 상태 객체
# ─────────────────────────────────────────────────────────────

class ScanProgress:
    def __init__(self, total: int):
        self.total         = total
        self.done          = 0
        self.cached        = 0
        self.refreshed     = 0
        self.price_changed = 0
        self.failed        = 0
        self.current_ticker = ""
        self.live_results: List[Dict] = []
        self.started_at    = datetime.now()

    @property
    def pct(self) -> float:
        return self.done / self.total if self.total else 0.0

    @property
    def elapsed_sec(self) -> float:
        return (datetime.now() - self.started_at).total_seconds()

    @property
    def eta_sec(self) -> Optional[float]:
        if self.done == 0:
            return None
        rate = self.done / max(self.elapsed_sec, 0.001)
        return (self.total - self.done) / rate if rate > 0 else None

    def fmt_eta(self) -> str:
        eta = self.eta_sec
        if eta is None:
            return "계산 중..."
        h, rem = divmod(int(eta), 3600)
        m, s   = divmod(rem, 60)
        return f"{h}시간 {m}분" if h > 0 else f"{m}분 {s}초"

    def fmt_elapsed(self) -> str:
        h, rem = divmod(int(self.elapsed_sec), 3600)
        m, s   = divmod(rem, 60)
        return f"{h}시간 {m}분" if h > 0 else f"{m}분 {s}초"

    def log_progress(self, ticker: str, status: str) -> None:
        icons  = {"cached":"⚡","refreshed":"🔄","price_changed":"📈","failed":"❌"}
        icon   = icons.get(status, "?")
        bar_w  = 25
        filled = int(bar_w * self.pct)
        bar    = "█" * filled + "░" * (bar_w - filled)
        log.info(
            f"  [{bar}] {self.done:>3}/{self.total}  {icon}{ticker:<8}  "
            f"✅{self.cached} 🔄{self.refreshed+self.price_changed} ❌{self.failed}  "
            f"ETA {self.fmt_eta()}"
        )

    def sorted_df(self) -> pd.DataFrame:
        if not self.live_results:
            return pd.DataFrame()
        df = pd.DataFrame(self.live_results)
        return df.sort_values("composite_score", ascending=False).reset_index(drop=True)


# ─────────────────────────────────────────────────────────────
# 메인 배치 스캐너
# ─────────────────────────────────────────────────────────────

def run_sp500_scan(
    tickers:             List[str],
    max_workers:         int   = 0,
    force_refresh:       bool  = False,
    price_threshold_pct: float = 2.0,
    stop_flag:           Optional[Dict] = None,
    progress:            Optional[ScanProgress] = None,
    period_days:         int   = 400,
) -> Tuple[pd.DataFrame, Dict]:
    """
    ThreadPoolExecutor 기반 전체 앙상블 스캔.

    워커 수 기본값 = config.PARALLEL["scanner_workers"] = 2
    (2 워커 × LSTM CPU = OMP 2스레드, MPS 접근 없음 → 안전)

    처음 실행 시 오래 걸리지만 DP 캐시로 이후 대폭 단축됩니다.
    """
    from config import PARALLEL as PAR_CFG

    if max_workers <= 0:
        max_workers = PAR_CFG["scanner_workers"]

    cache  = load_cache()
    t_scan = time.time()

    # 캐시 없는 종목(신규 분석 필요) 수 계산
    need_analysis = sum(
        1 for t in tickers
        if force_refresh
        or t not in cache
        or not is_cache_valid(cache.get(t, {}), CACHE_TTL_H)
    )
    cached_count = len(tickers) - need_analysis

    log.info("")
    log.info(f"🔭  스캔 시작  |  종목={len(tickers)}개  |  워커={max_workers}개  |  기간={period_days}일")
    log.info(f"  ⚡ 캐시 재사용: {cached_count}개  |  🔄 신규 분석: {need_analysis}개")
    log.info(f"  모델: XGBoost+LSTM 앙상블 (CPU, nthread=1)")
    if need_analysis > 0:
        est_min = need_analysis * 60 / max_workers / 60
        log.info(f"  ⏱  신규 분석 예상 시간: 약 {est_min:.0f}~{est_min*2:.0f}분")
    log.info(f"  ⚡=캐시  🔄=신규  📈=가격변동  ❌=실패")

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        futures = {
            executor.submit(
                _process_one, t, cache, force_refresh,
                price_threshold_pct, period_days
            ): t
            for t in tickers
        }

        for future in as_completed(futures):
            if stop_flag and stop_flag.get("stop"):
                log.warning("  ⏹  스캔 중단 요청")
                executor.shutdown(wait=False, cancel_futures=True)
                break

            ticker = futures[future]
            if progress:
                progress.current_ticker = ticker

            try:
                _, result, status = future.result(timeout=WORKER_TIMEOUT_SEC)
            except TimeoutError:
                result, status = None, "failed"
                log.warning(f"  ⏱  {ticker} 타임아웃 ({WORKER_TIMEOUT_SEC}s 초과)")
            except Exception as e:
                result, status = None, "failed"
                log.warning(f"  ❌  {ticker} 미래 오류: {e}")

            if progress:
                progress.done += 1
                if   status == "cached":        progress.cached        += 1
                elif status == "refreshed":     progress.refreshed     += 1
                elif status == "price_changed": progress.price_changed += 1
                else:                           progress.failed        += 1
                if progress.done % 5 == 0 or progress.done == progress.total:
                    progress.log_progress(ticker, status)

            if result is not None:
                cache[ticker] = result
                if progress:
                    progress.live_results.append(result)

            if progress and progress.done % 10 == 0:
                save_cache(cache)

    save_cache(cache)
    elapsed = time.time() - t_scan
    n_ok    = sum(1 for t in tickers if t in cache)
    log.info(f"🏁  스캔 완료  |  {elapsed/60:.1f}분  |  성공={n_ok}종목")
    log.info("")

    all_res = [cache[t] for t in tickers if t in cache]
    if not all_res:
        return pd.DataFrame(), cache

    df = pd.DataFrame(all_res)
    df = df.sort_values("composite_score", ascending=False).reset_index(drop=True)
    df.index += 1
    return df, cache


# ─────────────────────────────────────────────────────────────
# 결과 포맷 유틸
# ─────────────────────────────────────────────────────────────

def fmt_mktcap(v) -> str:
    try:
        v = float(v)
        if v >= 1e12: return f"${v/1e12:.1f}T"
        if v >= 1e9:  return f"${v/1e9:.1f}B"
        return f"${v/1e6:.0f}M"
    except Exception:
        return "N/A"


def get_top10(scan_df: pd.DataFrame) -> pd.DataFrame:
    if scan_df.empty:
        return scan_df
    top10 = scan_df.head(10).copy()
    top10["시가총액"]   = top10["market_cap"].apply(fmt_mktcap)
    top10["상승확률"]   = top10["up_probability"].apply(lambda x: f"{x:.1f}%")
    top10["예상상승폭"] = top10["estimated_upside"].apply(lambda x: f"+{x:.1f}%")
    top10["종합스코어"] = top10["composite_score"].apply(lambda x: f"{x:.3f}")
    top10["RSI"]        = top10["rsi"].apply(lambda x: f"{x:.1f}")
    top10["52주여력"]   = top10["upside_to_52w"].apply(lambda x: f"+{x:.1f}%")
    top10["매수신호"]   = top10["buy_signals"].apply(lambda x: "🟢" * int(x))
    top10["ML신호"]     = top10["ml_signal"].apply(
        lambda x: {"BUY":"📈 BUY","SELL":"📉 SELL","HOLD":"⏸ HOLD"}.get(x, x)
    )
    return top10


def format_market_cap(v) -> str:
    return fmt_mktcap(v)


def get_cache_stats(tickers: List[str]) -> Dict:
    cache = load_cache()
    valid = stale = 0
    for t in tickers:
        e = cache.get(t)
        if e:
            if is_cache_valid(e):
                valid += 1
            else:
                stale += 1
    return {
        "total_cached": len([t for t in tickers if t in cache]),
        "valid":         valid,
        "stale":         stale,
        "uncached":      len([t for t in tickers if t not in cache]),
        "ttl_hours":     CACHE_TTL_H,
    }