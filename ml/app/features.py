from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Tuple


def calculate_sma(series: pd.Series, window: int) -> pd.Series:
    return series.rolling(window=window, min_periods=1).mean()


def calculate_ema(series: pd.Series, span: int) -> pd.Series:
    return series.ewm(span=span, adjust=False).mean()


def calculate_rsi(series: pd.Series, window: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(com=window - 1, min_periods=window).mean()
    avg_loss = loss.ewm(com=window - 1, min_periods=window).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    rsi = 100 - 100 / (1 + rs)
    return rsi.fillna(50)


def calculate_macd(
    series: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    ema_fast = calculate_ema(series, fast)
    ema_slow = calculate_ema(series, slow)
    macd_line = ema_fast - ema_slow
    signal_line = calculate_ema(macd_line, signal)
    hist = macd_line - signal_line
    return macd_line, signal_line, hist


def calculate_bollinger_bands(
    series: pd.Series, window: int = 20, num_std: float = 2.0
) -> Tuple[pd.Series, pd.Series, pd.Series]:
    middle = calculate_sma(series, window)
    std = series.rolling(window=window, min_periods=1).std(ddof=0).fillna(0)
    upper = middle + std * num_std
    lower = middle - std * num_std
    return upper, middle, lower


def calculate_atr(df: pd.DataFrame, window: int = 14) -> pd.Series:
    high = df["High"]
    low = df["Low"]
    close = df["Close"]
    tr1 = high - low
    tr2 = (high - close.shift()).abs()
    tr3 = (low - close.shift()).abs()
    tr = pd.concat([tr1, tr2, tr3], axis=1).max(axis=1)
    return tr.ewm(com=window - 1, min_periods=window).mean()


def calculate_obv(df: pd.DataFrame) -> pd.Series:
    direction = df["Close"].diff().fillna(0).apply(lambda x: 1 if x > 0 else (-1 if x < 0 else 0))
    return (direction * df["Volume"]).cumsum()


def add_all_indicators(df: pd.DataFrame) -> pd.DataFrame:
    df = df.copy()
    close = df["Close"]

    df["MA5"] = calculate_sma(close, 5)
    df["MA20"] = calculate_sma(close, 20)
    df["MA50"] = calculate_sma(close, 50)

    df["RSI14"] = calculate_rsi(close, 14)
    df["RSI7"] = calculate_rsi(close, 7)

    macd, signal, hist = calculate_macd(close)
    df["MACD"] = macd
    df["MACD_Signal"] = signal
    df["MACD_Hist"] = hist

    bb_upper, bb_middle, bb_lower = calculate_bollinger_bands(close)
    df["BB_Upper"] = bb_upper
    df["BB_Middle"] = bb_middle
    df["BB_Lower"] = bb_lower
    width = (bb_upper - bb_lower) / bb_middle.replace(0, np.nan)
    df["BB_Width"] = width.fillna(0)
    position = (close - bb_lower) / (bb_upper - bb_lower).replace(0, np.nan)
    df["BB_Position"] = position.fillna(0.5).clip(0, 1)

    atr = calculate_atr(df, 14)
    df["ATR14"] = atr
    df["ATR_Pct"] = (atr / close * 100).replace([np.inf, -np.inf], np.nan).fillna(0)

    df["OBV"] = calculate_obv(df)
    df["OBV_Trend"] = (df["OBV"] - calculate_ema(df["OBV"], 10)) / calculate_ema(df["OBV"], 10).replace(0, np.nan)
    df["OBV_Trend"] = df["OBV_Trend"].fillna(0)

    df["Volume_SMA20"] = df["Volume"].rolling(window=20, min_periods=1).mean()
    df["Volume_Ratio"] = (df["Volume"] / df["Volume_SMA20"].replace(0, np.nan)).fillna(1)

    for n in [1, 3, 5, 10, 20]:
        df[f"Return_{n}d"] = close.pct_change(n)

    df["Price_vs_MA20"] = (close - df["MA20"]) / df["MA20"].replace(0, np.nan)
    df["Price_vs_MA50"] = (close - df["MA50"]) / df["MA50"].replace(0, np.nan)
    df["MA5_vs_MA20"] = (df["MA5"] - df["MA20"]) / df["MA20"].replace(0, np.nan)
    df["MA20_vs_MA50"] = (df["MA20"] - df["MA50"]) / df["MA50"].replace(0, np.nan)

    high20 = df["High"].rolling(window=20, min_periods=1).max()
    low20 = df["Low"].rolling(window=20, min_periods=1).min()
    df["Price_Position_20d"] = ((close - low20) / (high20 - low20).replace(0, np.nan)).fillna(0.5)

    body_top = pd.concat([df["Open"], close], axis=1).max(axis=1)
    body_bot = pd.concat([df["Open"], close], axis=1).min(axis=1)
    df["Body_Size"] = ((close - df["Open"]).abs() / df["Open"].replace(0, np.nan)).fillna(0)
    df["Upper_Shadow"] = ((df["High"] - body_top) / df["Open"].replace(0, np.nan)).fillna(0)
    df["Lower_Shadow"] = ((body_bot - df["Low"]) / df["Open"].replace(0, np.nan)).fillna(0)
    df["Is_Bullish"] = (close > df["Open"]).astype(int)
    df["Momentum_Normalized"] = ((close - close.shift(10)) / close.shift(10).replace(0, np.nan)).fillna(0)

    df["MACD_Cross"] = 0
    macd_above = df["MACD"] > df["MACD_Signal"]
    prev_macd_above = macd_above.shift(1).astype("boolean").fillna(False)
    df.loc[macd_above & ~prev_macd_above, "MACD_Cross"] = 1
    df.loc[~macd_above & prev_macd_above, "MACD_Cross"] = -1

    df["Target"] = (close.shift(-1) > close).astype(int)
    df["Target_Return"] = close.shift(-1) / close - 1

    return df
