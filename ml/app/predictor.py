from __future__ import annotations

import numpy as np
import pandas as pd
from typing import Dict, List, Optional, Tuple

BASE_FEATURES = [
    "RSI14", "RSI7",
    "MACD", "MACD_Signal", "MACD_Hist",
    "BB_Width", "BB_Position",
    "ATR_Pct",
    "STOCH_K", "STOCH_D",
    "WILLIAMS_R",
    "Volume_Ratio", "OBV_Trend",
    "Return_1d", "Return_3d", "Return_5d", "Return_10d", "Return_20d",
    "Price_vs_MA20", "Price_vs_MA50",
    "MA5_vs_MA20", "MA20_vs_MA50",
    "Price_Position_20d",
    "Body_Size", "Upper_Shadow", "Lower_Shadow", "Is_Bullish",
    "Momentum_Normalized", "MACD_Cross",
]
SENTIMENT_FEATURES = ["Sentiment_Score", "Sentiment_Positive", "Sentiment_Negative"]


def get_feature_columns(df: pd.DataFrame, include_sentiment: bool = True) -> List[str]:
    columns = [col for col in BASE_FEATURES if col in df.columns]
    if include_sentiment:
        columns += [col for col in SENTIMENT_FEATURES if col in df.columns]
    return columns


def _auto_params(n_samples: int) -> Dict[str, int]:
    if n_samples < 300:
        return {"n_estimators_xgb": 150, "n_splits": 3, "lstm_epochs": 60}
    if n_samples < 800:
        return {"n_estimators_xgb": 200, "n_splits": 4, "lstm_epochs": 80}
    if n_samples < 2000:
        return {"n_estimators_xgb": 300, "n_splits": 5, "lstm_epochs": 100}
    return {"n_estimators_xgb": 300, "n_splits": 5, "lstm_epochs": 100}


def prepare_training_data(
    df: pd.DataFrame,
    feature_cols: List[str],
    min_samples: int = 60,
    max_samples: Optional[int] = None,
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[pd.DatetimeIndex]]:
    work = df.loc[:, feature_cols + ["Target"]].copy()
    work = work.dropna(subset=["Target"]).iloc[:-1]
    if len(work) < min_samples:
        return None, None, None

    if max_samples is not None and len(work) > max_samples:
        work = work.iloc[-max_samples:]

    X = work[feature_cols].ffill().bfill().fillna(0)
    X = X.replace([np.inf, -np.inf], 0).clip(-10, 10)
    return X.to_numpy(dtype=np.float32), work["Target"].astype(int).to_numpy(), work.index


class RegimeDetector:
    def __init__(self, lookback: int = 60):
        self.lookback = lookback

    def compute(self, df: pd.DataFrame) -> Dict:
        recent = df.tail(self.lookback)
        scores: Dict[str, float] = {}

        if "ATR_Pct" in recent.columns:
            atr = recent["ATR_Pct"].dropna()
            if len(atr) >= 2 and atr.mean() != 0:
                cv = float(atr.std() / (atr.mean() + 1e-9))
                spike = float(atr.tail(10).mean() / (atr.mean() + 1e-9))
                scores["volatility"] = float(np.clip(cv * 0.5 + (spike - 1) * 0.3, 0, 1))
            else:
                scores["volatility"] = 0.3
        else:
            scores["volatility"] = 0.3

        if all(col in recent.columns for col in ["MA5_vs_MA20", "MA20_vs_MA50"]):
            fast = recent["MA5_vs_MA20"].dropna().to_numpy()
            slow = recent["MA20_vs_MA50"].dropna().to_numpy()
            if len(fast) > 1 and len(slow) > 1:
                fast_flips = int((np.diff(np.sign(fast)) != 0).sum())
                slow_flips = int((np.diff(np.sign(slow)) != 0).sum())
                flip_rate = float((fast_flips + slow_flips) / (len(fast) * 2 + 1e-9))
                scores["trend_inconsistency"] = float(np.clip(flip_rate * 3, 0, 1))
            else:
                scores["trend_inconsistency"] = 0.3
        else:
            scores["trend_inconsistency"] = 0.3

        if "RSI14" in recent.columns:
            rsi = recent["RSI14"].dropna()
            if len(rsi) > 0:
                scores["rsi_extremes"] = float(np.clip(((rsi > 70) | (rsi < 30)).mean() * 2.5, 0, 1))
            else:
                scores["rsi_extremes"] = 0.2
        else:
            scores["rsi_extremes"] = 0.2

        if "MACD_Cross" in recent.columns:
            cross_count = int(recent["MACD_Cross"].abs().sum())
            scores["macd_cross_freq"] = float(np.clip(cross_count / (len(recent) + 1e-9) * 15, 0, 1))
        else:
            scores["macd_cross_freq"] = 0.2

        if "Momentum_Normalized" in recent.columns:
            mom = recent["Momentum_Normalized"].dropna().to_numpy()
            if len(mom) > 1:
                flips = int((np.diff(np.sign(mom)) != 0).sum())
                scores["momentum_reversal"] = float(np.clip(flips / len(mom) * 4, 0, 1))
            else:
                scores["momentum_reversal"] = 0.2
        else:
            scores["momentum_reversal"] = 0.2

        if "BB_Position" in recent.columns:
            bb = recent["BB_Position"].dropna()
            if len(bb) > 5:
                breakout = float(np.clip(((bb > 0.95) | (bb < 0.05)).mean() * 5, 0, 1))
                scores["bb_breakout"] = breakout
            else:
                scores["bb_breakout"] = 0.2
        else:
            scores["bb_breakout"] = 0.2

        weights = {
            "volatility": 0.30,
            "trend_inconsistency": 0.25,
            "rsi_extremes": 0.15,
            "macd_cross_freq": 0.15,
            "momentum_reversal": 0.10,
            "bb_breakout": 0.05,
        }
        complexity = sum(scores.get(key, 0.0) * weight for key, weight in weights.items())
        complexity = float(np.clip(complexity, 0, 1))

        if complexity < 0.30:
            regime = "simple"
        elif complexity < 0.60:
            regime = "moderate"
        else:
            regime = "complex"

        return {
            "complexity": round(complexity, 3),
            "regime": regime,
            "scores": {k: round(v, 3) for k, v in scores.items()},
            "use_lstm": regime in {"moderate", "complex"},
        }


def _build_result(up_prob: float, model_name: str) -> Dict:
    down_prob = 1.0 - up_prob
    confidence = max(up_prob, down_prob)
    if up_prob > 0.58:
        signal = "BUY"
    elif down_prob > 0.58:
        signal = "SELL"
    else:
        signal = "HOLD"

    return {
        "direction": 1 if up_prob >= 0.5 else 0,
        "up_probability": round(up_prob, 4),
        "down_probability": round(down_prob, 4),
        "confidence": round(confidence, 4),
        "signal": signal,
        "model": model_name,
    }


def run_backtest(
    df: pd.DataFrame,
    predictor,
    initial_capital: float = 10_000_000,
    commission_rate: float = 0.001,
) -> Dict:
    if not getattr(predictor, "is_trained", False):
        return {}

    capital = initial_capital
    shares = 0
    position = "NONE"
    trades = []
    portfolio = []

    for i in range(80, len(df) - 1):
        sub_df = df.iloc[: i + 1]
        pred = predictor.predict(sub_df)
        if not isinstance(pred, dict) or "signal" not in pred:
            portfolio.append({"date": df.index[i], "value": capital + shares * float(df["Close"].iloc[i])})
            continue

        sig = pred["signal"]
        price = float(df["Close"].iloc[i])

        if sig == "BUY" and position == "NONE":
            shares = int(capital * (1 - commission_rate) / price)
            if shares > 0:
                capital -= shares * price * (1 + commission_rate)
                position = "LONG"
                trades.append({"date": df.index[i], "type": "BUY", "price": price, "shares": shares})

        elif sig == "SELL" and position == "LONG":
            capital += shares * price * (1 - commission_rate)
            position = "NONE"
            trades.append({"date": df.index[i], "type": "SELL", "price": price, "shares": shares})
            shares = 0

        portfolio.append({"date": df.index[i], "value": capital + shares * price})

    if shares > 0:
        capital += shares * float(df["Close"].iloc[-1]) * (1 - commission_rate)

    if not portfolio:
        return {}

    port_df = pd.DataFrame(portfolio).set_index("date")
    strat = (capital / initial_capital - 1) * 100
    bench = (float(df["Close"].iloc[-1]) / float(df["Close"].iloc[80]) - 1) * 100

    return {
        "initial_capital": initial_capital,
        "final_capital": round(capital, 2),
        "strategy_return_pct": round(strat, 2),
        "benchmark_return_pct": round(bench, 2),
        "excess_return": round(strat - bench, 2),
        "n_trades": len(trades),
        "trades": trades,
        "portfolio_values": port_df,
    }
