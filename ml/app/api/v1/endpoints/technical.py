"""GET /api/v1/technical/{ticker} — 기술적 지표"""

import logging

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel

router = APIRouter()
log = logging.getLogger("stockai.api.technical")


class SignalItem(BaseModel):
    action: str
    description: str
    color: str


class TechnicalResponse(BaseModel):
    ticker: str
    period_days: int
    data_points: int
    signals: dict[str, SignalItem]
    support_resistance: dict[str, float]
    latest_indicators: dict[str, float | None]
    ma_trend: str
    overall_signal: str


@router.get("/{ticker}", response_model=TechnicalResponse, summary="기술적 지표 조회")
async def get_technical(
    ticker: str,
    period_days: int = Query(default=365, ge=60, le=3000, description="조회 기간(일)"),
):
    """
    주어진 종목의 기술적 지표와 매매 신호를 반환합니다.

    - RSI, MACD, 볼린저 밴드, 스토캐스틱, 이동평균 신호
    - 지지/저항 레벨
    """
    try:
        from ....services.fetcher import fetch_stock_data
        from ....services.technical import (
            add_all_indicators,
            get_current_signals,
            get_support_resistance,
        )

        ticker = ticker.strip().upper()
        df, _ = fetch_stock_data(ticker, period_days=period_days)
        if df is None:
            raise HTTPException(status_code=404, detail=f"데이터 없음: {ticker}")

        df = add_all_indicators(df)
        signals = get_current_signals(df)
        sr = get_support_resistance(df)

        signal_items = {
            k: SignalItem(action=v[0], description=v[1], color=v[2]) for k, v in signals.items()
        }

        latest = df.iloc[-1]

        def safe_float(col: str) -> float | None:
            try:
                return round(float(latest[col]), 4) if col in df.columns else None
            except Exception:
                return None

        # MA 추세 판단
        ma5 = safe_float("MA5")
        ma20 = safe_float("MA20")
        ma50 = safe_float("MA50")
        if ma5 and ma20 and ma50:
            if ma5 > ma20 > ma50:
                ma_trend = "bullish"
            elif ma5 < ma20 < ma50:
                ma_trend = "bearish"
            else:
                ma_trend = "mixed"
        else:
            ma_trend = "unknown"

        buy_count = sum(1 for s in signals.values() if s[0] == "BUY")
        sell_count = sum(1 for s in signals.values() if s[0] == "SELL")
        if buy_count > sell_count:
            overall = "BUY"
        elif sell_count > buy_count:
            overall = "SELL"
        else:
            overall = "HOLD"

        return TechnicalResponse(
            ticker=ticker,
            period_days=period_days,
            data_points=len(df),
            signals=signal_items,
            support_resistance=sr,
            latest_indicators={
                "close": safe_float("Close"),
                "rsi14": safe_float("RSI14"),
                "rsi7": safe_float("RSI7"),
                "macd": safe_float("MACD"),
                "macd_signal": safe_float("MACD_Signal"),
                "macd_hist": safe_float("MACD_Hist"),
                "bb_upper": safe_float("BB_Upper"),
                "bb_middle": safe_float("BB_Middle"),
                "bb_lower": safe_float("BB_Lower"),
                "bb_position": safe_float("BB_Position"),
                "stoch_k": safe_float("STOCH_K"),
                "stoch_d": safe_float("STOCH_D"),
                "williams_r": safe_float("WILLIAMS_R"),
                "atr14": safe_float("ATR14"),
                "atr_pct": safe_float("ATR_Pct"),
                "volume_ratio": safe_float("Volume_Ratio"),
                "obv_trend": safe_float("OBV_Trend"),
                "ma5": ma5,
                "ma20": ma20,
                "ma50": ma50,
                "ma200": safe_float("MA200"),
                "momentum_normalized": safe_float("Momentum_Normalized"),
            },
            ma_trend=ma_trend,
            overall_signal=overall,
        )

    except HTTPException:
        raise
    except Exception as e:
        log.exception(f"기술적 지표 조회 실패: {ticker}")
        raise HTTPException(status_code=500, detail=str(e))
