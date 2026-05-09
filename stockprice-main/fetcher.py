"""
Multi-source Data Ingestion Module
- yfinance: 실시간 시세 + 재무지표
- 한국/미국 주식 모두 지원
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Optional, Tuple, Dict
import warnings
warnings.filterwarnings('ignore')


def is_korean_ticker(ticker: str) -> bool:
    """한국 종목 코드 판별 (숫자 6자리 또는 .KS/.KQ 접미사)"""
    ticker_clean = ticker.upper().strip()
    # 숫자만 있으면 한국 주식
    if ticker_clean.isdigit() and len(ticker_clean) == 6:
        return True
    # .KS (KOSPI) 또는 .KQ (KOSDAQ)
    if ticker_clean.endswith('.KS') or ticker_clean.endswith('.KQ'):
        return True
    return False


def normalize_ticker(ticker: str) -> str:
    """한국 종목 코드를 yfinance 형식으로 변환"""
    ticker = ticker.strip().upper()
    if ticker.isdigit() and len(ticker) == 6:
        return f"{ticker}.KS"  # 기본값: KOSPI
    return ticker


def fetch_stock_data(
    ticker: str,
    period_days: int = 365
) -> Tuple[Optional[pd.DataFrame], Optional[Dict]]:
    """
    주가 데이터 및 재무정보 수집

    period_days:
      ≤ 0   → 전체 기간 (max)
      1~365 → 해당 일수
      > 365 → 연단위 자동 변환 (yfinance는 일 단위 start 사용)
      최대 약 20년치 (yfinance 제공 범위 내)

    Returns:
        (price_df, financials_dict)
    """
    ticker = normalize_ticker(ticker)

    try:
        stock = yf.Ticker(ticker)

        # 1. 가격 데이터 (OHLCV)
        if period_days <= 0:
            # 전체 기간
            hist = stock.history(period="max", auto_adjust=True)
        else:
            end_date   = datetime.now()
            # 지표 계산용 여유분 200일 추가 (MA200 등)
            start_date = end_date - timedelta(days=period_days + 200)
            hist = stock.history(start=start_date, end=end_date, auto_adjust=True)

        if hist.empty or len(hist) < 30:
            return None, None

        hist.index = pd.to_datetime(hist.index)
        # yfinance 0.2.54+: tz-aware index → tz-naive (Plotly/matplotlib 호환)
        if hist.index.tz is not None:
            hist.index = hist.index.tz_convert("UTC").tz_localize(None)
        hist = hist[['Open', 'High', 'Low', 'Close', 'Volume']].copy()
        hist.dropna(inplace=True)
        # M4 최적화: float32 다운캐스팅 (메모리 50% 절감)
        for col in ['Open', 'High', 'Low', 'Close']:
            hist[col] = hist[col].astype('float32')
        hist['Volume'] = hist['Volume'].astype('float32')
        
        # 2. 재무정보
        info = {}
        try:
            raw_info = stock.info
            financial_keys = [
                'trailingPE', 'forwardPE', 'priceToBook', 'returnOnEquity',
                'returnOnAssets', 'debtToEquity', 'currentRatio', 'quickRatio',
                'revenueGrowth', 'earningsGrowth', 'grossMargins', 'operatingMargins',
                'profitMargins', 'marketCap', 'enterpriseValue', 'dividendYield',
                'beta', 'fiftyTwoWeekHigh', 'fiftyTwoWeekLow',
                'shortName', 'longName', 'sector', 'industry', 'currency',
                'regularMarketPrice', 'regularMarketChangePercent',
                'averageVolume', 'sharesOutstanding'
            ]
            for key in financial_keys:
                val = raw_info.get(key)
                if val is not None:
                    info[key] = val
        except Exception:
            pass  # 재무정보 없어도 기술적 분석은 가능
        
        return hist, info
    
    except Exception as e:
        raise ValueError(f"데이터 수집 실패 ({ticker}): {str(e)}")


def fetch_earnings_history(ticker: str) -> Optional[pd.DataFrame]:
    """분기별 실적 데이터 수집 (yfinance 0.2.54+ 호환)"""
    ticker = normalize_ticker(ticker)
    try:
        stock = yf.Ticker(ticker)

        # yfinance 0.2.54+: income_stmt (분기별)
        try:
            stmt = stock.quarterly_income_stmt
            if stmt is not None and not stmt.empty:
                # 전치해서 날짜를 인덱스로
                df = stmt.T.sort_index(ascending=False)
                # 주요 항목만 선택
                cols = [c for c in df.columns if any(
                    k in str(c).lower() for k in
                    ['revenue', 'net income', 'gross profit', 'ebit']
                )]
                if cols:
                    return df[cols].head(8)
                return df.head(8)
        except Exception:
            pass

        # 폴백: quarterly_financials (구버전)
        try:
            qf = stock.quarterly_financials
            if qf is not None and not qf.empty:
                return qf.T.sort_index(ascending=False).head(8)
        except Exception:
            pass

    except Exception:
        pass
    return None


def fetch_institutional_holders(ticker: str) -> Optional[pd.DataFrame]:
    """기관 투자자 보유 현황"""
    ticker = normalize_ticker(ticker)
    try:
        stock = yf.Ticker(ticker)
        holders = stock.institutional_holders
        if holders is not None and not holders.empty:
            return holders.head(10)
    except Exception:
        pass
    return None


def get_market_context(ticker: str) -> Dict:
    """시장 맥락 데이터 (벤치마크 대비 성과)"""
    context = {}
    
    # 해당 지수 결정
    norm_ticker = normalize_ticker(ticker)
    if '.KS' in norm_ticker or '.KQ' in norm_ticker:
        benchmark = '^KS11'  # KOSPI
        benchmark_name = 'KOSPI'
    else:
        benchmark = '^GSPC'  # S&P 500
        benchmark_name = 'S&P 500'
    
    try:
        bench_data = yf.Ticker(benchmark).history(period='3mo')
        if not bench_data.empty:
            bench_return = (bench_data['Close'].iloc[-1] / bench_data['Close'].iloc[0] - 1) * 100
            context['benchmark_name'] = benchmark_name
            context['benchmark_3mo_return'] = round(bench_return, 2)
    except Exception:
        pass
    
    return context


def get_available_tickers_examples() -> Dict[str, list]:
    """예시 종목 코드 반환"""
    return {
        "🇺🇸 미국 대형주": ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA", "NVDA", "META"],
        "🇺🇸 미국 ETF": ["SPY", "QQQ", "ARKK", "VTI"],
        "🇰🇷 한국 KOSPI": ["005930.KS", "000660.KS", "035420.KS", "051910.KS"],
        "🇰🇷 한국 입력 예시": ["005930 (삼성전자)", "000660 (SK하이닉스)"],
    }