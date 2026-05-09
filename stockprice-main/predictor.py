"""
앙상블 예측 모듈 v3
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
구조:
  XGBoostPredictor   — 피처 기반 베이스라인 (항상 실행)
  LSTMPredictor      — 시계열 딥러닝 (복잡 국면에서 추가)
  RegimeDetector     — 시장 국면 감지 (단순 / 복잡 분류)
  EnsemblePredictor  — XGB + LSTM 가중 결합

앙상블 로직:
  1. XGBoost 항상 학습·예측
  2. RegimeDetector 로 현재 국면 판단
     - 변동성, 추세 일관성, 가격 구조 변화 분석
  3. 복잡 국면이거나 XGBoost 신뢰도 낮으면 LSTM 추가
  4. 각 모델 정확도 기반 동적 가중치로 최종 확률 결합
     p_final = w_xgb * p_xgb + w_lstm * p_lstm

macOS Apple Silicon (M4 Pro) 최적화:
  - XGBoost device='cpu'
  - PyTorch MPS(Metal) 자동 감지
  - TensorFlow-macos 지원
"""

from __future__ import annotations

import warnings
warnings.filterwarnings("ignore")

import sys
import time
import logging
import numpy as np
import pandas as pd
from datetime import datetime
from sklearn.model_selection import TimeSeriesSplit
from sklearn.preprocessing import StandardScaler
from sklearn.metrics import accuracy_score
from typing import Dict, List, Optional, Tuple
from config import (XGBOOST as XGB_CFG, PYTORCH as PT_CFG, DATA as DATA_CFG,
                    XGBOOST_SCANNER as XGB_SCAN, PYTORCH_SCANNER as PT_SCAN,
                    get_torch_device)

# ─────────────────────────────────────────────────────────────
# 터미널 로거
# ─────────────────────────────────────────────────────────────

def _setup_logger() -> logging.Logger:
    logger = logging.getLogger("stock_analyzer")
    if logger.handlers:
        return logger
    logger.setLevel(logging.DEBUG)

    # 터미널 핸들러 (색상 + 타임스탬프)
    handler = logging.StreamHandler(sys.stdout)
    handler.setLevel(logging.DEBUG)

    class _ColorFormatter(logging.Formatter):
        COLORS = {
            logging.DEBUG:    "[90m",   # 회색
            logging.INFO:     "[96m",   # 청록
            logging.WARNING:  "[93m",   # 노랑
            logging.ERROR:    "[91m",   # 빨강
            logging.CRITICAL: "[95m",   # 보라
        }
        RESET = "[0m"
        BOLD  = "[1m"

        def format(self, record):
            color  = self.COLORS.get(record.levelno, "")
            ts     = datetime.now().strftime("%H:%M:%S")
            prefix = f"{self.BOLD}[{ts}]{self.RESET} {color}"
            return f"{prefix}{record.getMessage()}{self.RESET}"

    handler.setFormatter(_ColorFormatter())
    logger.addHandler(handler)
    logger.propagate = False
    return logger


log = _setup_logger()


def _bar(current: int, total: int, width: int = 20) -> str:
    """간단한 ASCII 진행 막대."""
    if total <= 0:
        return "[" + "?" * width + "]"
    filled = int(width * current / total)
    return "[" + "█" * filled + "░" * (width - filled) + f"] {current}/{total}"

# ─────────────────────────────────────────────────────────────
# 피처 정의
# ─────────────────────────────────────────────────────────────

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
    cols = [f for f in BASE_FEATURES if f in df.columns]
    if include_sentiment:
        cols += [f for f in SENTIMENT_FEATURES if f in df.columns]
    return cols


# 데이터 크기별 자동 조정 파라미터 (config.py 기반)
def _auto_params(n_samples: int) -> Dict:
    """샘플 수에 따라 모델 파라미터 자동 조정 (M4 Pro 최적화)."""
    max_train = DATA_CFG["max_train_samples"]   # config에서 읽음 (24GB → 4000)
    max_lstm  = DATA_CFG["max_lstm_samples"]    # 3000

    if n_samples < 300:
        return {"n_estimators_xgb": 150, "n_splits": 3,
                "lstm_epochs": 60,  "fast": False,
                "max_lstm_samples": max_lstm}
    elif n_samples < 800:
        return {"n_estimators_xgb": 200, "n_splits": 4,
                "lstm_epochs": 80,  "fast": False,
                "max_lstm_samples": max_lstm}
    elif n_samples < 2000:
        return {"n_estimators_xgb": 300, "n_splits": 5,
                "lstm_epochs": 100, "fast": False,
                "max_lstm_samples": max_lstm}
    elif n_samples <= max_train:
        return {"n_estimators_xgb": 300, "n_splits": 5,
                "lstm_epochs": 120, "fast": False,
                "max_lstm_samples": max_lstm}
    else:
        # 대용량: max_train 개만 학습
        return {"n_estimators_xgb": 300, "n_splits": 5,
                "lstm_epochs": 100, "fast": True,
                "max_samples": max_train,
                "max_lstm_samples": max_lstm}


def prepare_training_data(
    df: pd.DataFrame,
    feature_cols: List[str],
    min_samples: int = 60,
    max_samples: Optional[int] = None,
) -> Tuple[Optional[np.ndarray], Optional[np.ndarray], Optional[pd.DatetimeIndex]]:
    """
    NaN/Inf 처리 후 (X, y, dates) 반환.
    max_samples 지정 시 최근 N개만 사용 (대용량 최적화).
    """
    work = df[feature_cols + ["Target"]].copy()
    work = work.dropna(subset=["Target"]).iloc[:-1]   # 마지막 날 제외

    if len(work) < min_samples:
        return None, None, None

    # 대용량 데이터: 최근 max_samples 개만 학습
    if max_samples and len(work) > max_samples:
        work = work.iloc[-max_samples:]

    X = work[feature_cols].ffill().bfill().fillna(0)
    X = X.replace([np.inf, -np.inf], 0).clip(-10, 10)
    return X.values, work["Target"].values.astype(int), work.index


# ─────────────────────────────────────────────────────────────
# RegimeDetector — 시장 국면 감지
# ─────────────────────────────────────────────────────────────

class RegimeDetector:
    """
    최근 데이터를 분석해 시장 국면을 판단합니다.

    complexity_score (0 ~ 1):
      0.0 ~ 0.3  단순 추세 → XGBoost 단독
      0.3 ~ 0.6  중간 복잡도 → 앙상블 권장
      0.6 ~ 1.0  복잡 국면 → LSTM 추가 필요

    복잡도를 높이는 요인:
      - 변동성 급증 (ATR 급증)
      - 추세 방향 비일관성 (MA 정배열/역배열 혼조)
      - RSI 과매수/과매도 반복
      - MACD 크로스 빈도 증가
      - 모멘텀 방향 전환
    """

    def __init__(self, lookback: int = 60):
        self.lookback = lookback

    def compute(self, df: pd.DataFrame) -> Dict:
        recent = df.tail(self.lookback).copy()
        scores: Dict[str, float] = {}

        # ── 1. 변동성 체계 ────────────────────────────────────
        if "ATR_Pct" in recent.columns:
            atr_series = recent["ATR_Pct"].dropna()
            if len(atr_series) > 10:
                atr_cv = atr_series.std() / (atr_series.mean() + 1e-9)
                # 변동성 자체의 변동성(변동성 군집)
                atr_recent_mean = atr_series.tail(10).mean()
                atr_full_mean   = atr_series.mean()
                atr_spike = atr_recent_mean / (atr_full_mean + 1e-9)
                scores["volatility"] = float(np.clip(atr_cv * 0.5 + (atr_spike - 1) * 0.3, 0, 1))
            else:
                scores["volatility"] = 0.3
        else:
            scores["volatility"] = 0.3

        # ── 2. 추세 일관성 ────────────────────────────────────
        if all(c in recent.columns for c in ["MA5_vs_MA20", "MA20_vs_MA50"]):
            ma_fast = recent["MA5_vs_MA20"].dropna()
            ma_slow = recent["MA20_vs_MA50"].dropna()
            if len(ma_fast) > 5:
                # 부호 전환 횟수 (많을수록 혼조)
                fast_flips = int((np.diff(np.sign(ma_fast.values)) != 0).sum())
                slow_flips = int((np.diff(np.sign(ma_slow.values)) != 0).sum())
                flip_rate  = (fast_flips + slow_flips) / (len(ma_fast) * 2 + 1e-9)
                scores["trend_inconsistency"] = float(np.clip(flip_rate * 3, 0, 1))
            else:
                scores["trend_inconsistency"] = 0.3
        else:
            scores["trend_inconsistency"] = 0.3

        # ── 3. RSI 극단값 반복 ────────────────────────────────
        if "RSI14" in recent.columns:
            rsi = recent["RSI14"].dropna()
            if len(rsi) > 5:
                extreme_ratio = ((rsi > 70) | (rsi < 30)).mean()
                scores["rsi_extremes"] = float(np.clip(extreme_ratio * 2.5, 0, 1))
            else:
                scores["rsi_extremes"] = 0.2
        else:
            scores["rsi_extremes"] = 0.2

        # ── 4. MACD 크로스 빈도 ───────────────────────────────
        if "MACD_Cross" in recent.columns:
            cross_count = recent["MACD_Cross"].abs().sum()
            cross_freq  = cross_count / (self.lookback + 1e-9)
            scores["macd_cross_freq"] = float(np.clip(cross_freq * 15, 0, 1))
        else:
            scores["macd_cross_freq"] = 0.2

        # ── 5. 모멘텀 방향 전환 ───────────────────────────────
        if "Momentum_Normalized" in recent.columns:
            mom = recent["Momentum_Normalized"].dropna()
            if len(mom) > 5:
                mom_flips = int((np.diff(np.sign(mom.values)) != 0).sum())
                scores["momentum_reversal"] = float(np.clip(mom_flips / len(mom) * 4, 0, 1))
            else:
                scores["momentum_reversal"] = 0.2
        else:
            scores["momentum_reversal"] = 0.2

        # ── 6. 볼린저 밴드 이탈 빈도 ─────────────────────────
        if "BB_Position" in recent.columns:
            bb = recent["BB_Position"].dropna()
            if len(bb) > 5:
                breakout_ratio = ((bb > 0.95) | (bb < 0.05)).mean()
                scores["bb_breakout"] = float(np.clip(breakout_ratio * 5, 0, 1))
            else:
                scores["bb_breakout"] = 0.2
        else:
            scores["bb_breakout"] = 0.2

        # ── 종합 복잡도 ───────────────────────────────────────
        weights = {
            "volatility":          0.30,
            "trend_inconsistency": 0.25,
            "rsi_extremes":        0.15,
            "macd_cross_freq":     0.15,
            "momentum_reversal":   0.10,
            "bb_breakout":         0.05,
        }
        complexity = sum(scores.get(k, 0) * w for k, w in weights.items())
        complexity = float(np.clip(complexity, 0, 1))

        # 국면 레이블
        if   complexity < 0.30: regime = "simple"
        elif complexity < 0.60: regime = "moderate"
        else:                    regime = "complex"

        return {
            "complexity":  round(complexity, 3),
            "regime":      regime,
            "scores":      {k: round(v, 3) for k, v in scores.items()},
            "use_lstm":    regime in ("moderate", "complex"),
        }


# ─────────────────────────────────────────────────────────────
# XGBoostPredictor
# ─────────────────────────────────────────────────────────────

class XGBoostPredictor:
    """XGBoost 기반 베이스라인 예측기."""

    def __init__(self, scanner_mode: bool = False):
        """
        scanner_mode=True: ThreadPoolExecutor 내부에서 호출 시 설정.
          - nthread=1 고정 (OMP 경합 방지)
          - MPS 비활성화
        """
        self.scanner_mode = scanner_mode
        self.model = None
        self.scaler = StandardScaler()
        self.feature_cols: Optional[List[str]] = None
        self.is_trained = False
        self.feature_importances_: Optional[pd.Series] = None
        self.training_metrics: Dict = {}
        self._cv_proba: Optional[np.ndarray] = None

    # ── 학습 ─────────────────────────────────────────────────
    def train(
        self,
        df: pd.DataFrame,
        include_sentiment: bool = True,
        n_splits: int = 5,
    ) -> Dict:
        try:
            import xgboost as xgb
            _ = xgb.XGBClassifier
        except Exception:
            return self._train_sklearn(df, include_sentiment)

        # 스캐너 모드: nthread=1 강제 (OMP 경합/크래시 방지)
        xgb_cfg = XGB_SCAN if self.scanner_mode else XGB_CFG

        self.feature_cols = get_feature_columns(df, include_sentiment)

        # 샘플 수에 따른 파라미터 자동 조정
        raw_len   = len(df)
        ap        = _auto_params(raw_len)
        max_samp  = ap.get("max_samples")
        # 스캐너 모드는 n_splits 줄여서 속도 확보
        n_est_cv  = max(80, ap["n_estimators_xgb"] - 100) if not self.scanner_mode else 100
        n_est_fin = ap["n_estimators_xgb"]             if not self.scanner_mode else 150
        n_splits_  = ap["n_splits"]                     if not self.scanner_mode else 3

        X, y, _ = prepare_training_data(df, self.feature_cols, max_samples=max_samp)
        if X is None:
            return {"error": "학습 데이터 부족 (최소 60일 필요)"}

        ds_note = f" → 최근 {len(y)}개로 다운샘플" if max_samp and raw_len > max_samp else ""
        log.info(f"  ┌ XGBoost 학습 시작")
        log.info(f"  │ 데이터: {raw_len:,}일{ds_note}  |  피처: {len(self.feature_cols)}개  |  트리: {n_est_fin}개")
        log.info(f"  │ Walk-forward CV: {n_splits_}-fold")

        t0    = time.time()
        tscv  = TimeSeriesSplit(n_splits=n_splits_)
        cv_scores = []
        oof_proba = np.full(len(y), 0.5)

        for fold_i, (tr_idx, val_idx) in enumerate(tscv.split(X), 1):
            sc = StandardScaler()
            Xtr = sc.fit_transform(X[tr_idx])
            Xvl = sc.transform(X[val_idx])

            m = xgb.XGBClassifier(
                n_estimators=n_est_cv, max_depth=4, learning_rate=0.05,
                subsample=0.8, colsample_bytree=0.8,
                min_child_weight=5, gamma=1,
                reg_alpha=0.1, reg_lambda=1.0,
                eval_metric="logloss", random_state=42,
                n_jobs=xgb_cfg["nthread"], verbosity=0,
                device=xgb_cfg["device"],
                tree_method=xgb_cfg["tree_method"],
                max_bin=xgb_cfg["max_bin"],
                grow_policy=xgb_cfg["grow_policy"],
            )
            m.fit(Xtr, y[tr_idx], eval_set=[(Xvl, y[val_idx])], verbose=False)
            oof_proba[val_idx] = m.predict_proba(Xvl)[:, 1]
            fold_acc = accuracy_score(y[val_idx], m.predict(Xvl))
            cv_scores.append(fold_acc)
            log.info(f"  │ Fold {fold_i}/{n_splits_} {_bar(fold_i, n_splits_, 15)}  acc={fold_acc:.3f}  ({time.time()-t0:.1f}s 경과)")

        self._cv_proba = oof_proba
        log.info(f"  │ CV 평균 정확도: {float(np.mean(cv_scores)):.3f} ± {float(np.std(cv_scores)):.3f}")
        log.info(f"  │ 최종 모델 학습 중 (n_estimators={n_est_fin})...")

        # 전체 데이터로 최종 모델
        X_sc = self.scaler.fit_transform(X)
        self.model = xgb.XGBClassifier(
            n_estimators=n_est_fin, max_depth=4, learning_rate=0.05,
            subsample=0.8, colsample_bytree=0.8,
            min_child_weight=5, gamma=1,
            reg_alpha=0.1, reg_lambda=1.0,
            eval_metric="logloss", random_state=42,
            n_jobs=xgb_cfg["nthread"], verbosity=0,
            device=xgb_cfg["device"],
            tree_method=xgb_cfg["tree_method"],
            max_bin=xgb_cfg["max_bin"],
            grow_policy=xgb_cfg["grow_policy"],
        )
        self.model.fit(X_sc, y, verbose=False)
        self.is_trained = True
        log.info(f"  └ XGBoost 완료  ({time.time()-t0:.1f}s)")

        self.feature_importances_ = pd.Series(
            self.model.feature_importances_, index=self.feature_cols
        ).sort_values(ascending=False)

        y_pred = self.model.predict(X_sc)
        self.training_metrics = {
            "cv_accuracy_mean": float(np.mean(cv_scores)),
            "cv_accuracy_std":  float(np.std(cv_scores)),
            "train_accuracy":   float(accuracy_score(y, y_pred)),
            "model_type":       "XGBoost",
            "n_features":       len(self.feature_cols),
            "n_samples":        len(y),
            "n_samples_total":  raw_len,
            "downsampled":      max_samp is not None and raw_len > max_samp,
        }
        return self.training_metrics

    def _train_sklearn(self, df: pd.DataFrame, include_sentiment: bool) -> Dict:
        """XGBoost 로드 실패 시 sklearn GradientBoosting 폴백."""
        from sklearn.ensemble import GradientBoostingClassifier

        log.warning("  ⚠  XGBoost 로드 실패 → sklearn GradientBoosting 폴백")
        self.feature_cols = get_feature_columns(df, include_sentiment)
        X, y, _ = prepare_training_data(df, self.feature_cols)
        if X is None:
            return {"error": "학습 데이터 부족"}

        log.info(f"  ┌ GradientBoosting 학습 시작  (샘플: {len(y):,}개)")
        t0 = time.time()
        X_sc = self.scaler.fit_transform(X)
        self.model = GradientBoostingClassifier(
            n_estimators=100, max_depth=3, learning_rate=0.1,
            subsample=0.8, random_state=42,
        )
        self.model.fit(X_sc, y)
        self.is_trained = True
        log.info(f"  └ GradientBoosting 완료  ({time.time()-t0:.1f}s)")

        self.feature_importances_ = pd.Series(
            self.model.feature_importances_, index=self.feature_cols
        ).sort_values(ascending=False)

        y_pred = self.model.predict(X_sc)
        self.training_metrics = {
            "train_accuracy": float(accuracy_score(y, y_pred)),
            "model_type":     "GradientBoosting (sklearn)",
            "n_features":     len(self.feature_cols),
            "n_samples":      len(y),
        }
        return self.training_metrics

    # ── 예측 ─────────────────────────────────────────────────
    def predict_proba(self, df: pd.DataFrame) -> Optional[float]:
        """상승 확률 (0~1) 반환. 실패 시 None."""
        if not self.is_trained or self.feature_cols is None:
            return None
        try:
            latest = df[self.feature_cols].iloc[-1:]
            latest = latest.ffill().bfill().fillna(0).replace([np.inf, -np.inf], 0)
            X_sc   = self.scaler.transform(latest.values)
            return float(self.model.predict_proba(X_sc)[0, 1])
        except Exception:
            return None

    def predict(self, df: pd.DataFrame) -> Dict:
        p = self.predict_proba(df)
        if p is None:
            return {"error": "예측 실패"}
        return _build_result(p, self.training_metrics.get("model_type", "XGBoost"))


# ─────────────────────────────────────────────────────────────
# LSTMPredictor  (PyTorch MPS / TensorFlow-macos)
# ─────────────────────────────────────────────────────────────

class LSTMPredictor:
    """LSTM 시계열 예측기. Apple Silicon MPS 자동 감지."""

    def __init__(self, sequence_length: int = 20, scanner_mode: bool = False):
        """
        scanner_mode=True: MPS 사용 금지 (Metal GPU 스트림 동시 접근 → 크래시)
        멀티스레드 환경에서는 반드시 scanner_mode=True 를 사용하세요.
        """
        self.sequence_length = sequence_length
        self.scanner_mode    = scanner_mode
        self.model = None
        self.scaler = StandardScaler()
        self.feature_cols: Optional[List[str]] = None
        self.is_trained = False
        self.framework: Optional[str] = None
        self.training_metrics: Dict = {}

    # ── 프레임워크 감지 ───────────────────────────────────────
    @staticmethod
    def available_framework() -> Optional[str]:
        try:
            import torch as _t; return "pytorch"  # noqa: E702
        except Exception:
            pass
        try:
            import tensorflow as _tf; return "tensorflow"  # noqa: E702
        except Exception:
            pass
        return None

    # ── 학습 ─────────────────────────────────────────────────
    def train(self, df: pd.DataFrame, include_sentiment: bool = True) -> Dict:
        fw = self.available_framework()
        if not fw:
            return {"error": "PyTorch / TensorFlow 미설치. pip install torch 또는 tensorflow-macos"}

        self.framework     = fw
        self.feature_cols  = get_feature_columns(df, include_sentiment)
        X, y, _            = prepare_training_data(df, self.feature_cols)

        if X is None or len(X) < self.sequence_length + 20:
            return {"error": f"LSTM 학습 데이터 부족 (최소 {self.sequence_length + 20}일 필요)"}

        X_sc = self.scaler.fit_transform(X)

        if fw == "pytorch":
            return self._train_pytorch(X_sc, y)
        return self._train_tensorflow(X_sc, y)

    # ── PyTorch ───────────────────────────────────────────────
    def _train_pytorch(self, X_sc: np.ndarray, y: np.ndarray) -> Dict:
        import torch
        import torch.nn as nn

        # 스캐너 모드: MPS 절대 금지 (Metal GPU 동시 접근 → 메모리 오염 크래시)
        if self.scanner_mode:
            device = torch.device("cpu")
            torch.set_num_threads(PT_SCAN["num_threads"])   # 1스레드
        else:
            device = get_torch_device()
            if not isinstance(device, torch.device):
                device = torch.device(device)
            if device.type == "cpu":
                torch.set_num_threads(PT_CFG["num_threads"])

        SEQ    = self.sequence_length
        X_seq  = np.array([X_sc[i - SEQ:i] for i in range(SEQ, len(X_sc))])
        y_seq  = y[SEQ:]
        split  = int(len(X_seq) * 0.8)

        to_t   = lambda a: torch.tensor(a.astype("float32")).to(device)  # noqa: E731
        Xtr, Xvl = to_t(X_seq[:split]), to_t(X_seq[split:])
        ytr, yvl = to_t(y_seq[:split].astype("float32")), to_t(y_seq[split:].astype("float32"))
        batch_sz = PT_CFG["batch_size"]

        n_feat = X_seq.shape[2]

        class _Net(nn.Module):
            def __init__(self):
                super().__init__()
                self.lstm1 = nn.LSTM(n_feat, 64, batch_first=True, dropout=0.2, num_layers=1)
                self.ln1   = nn.LayerNorm(64)
                self.lstm2 = nn.LSTM(64, 32, batch_first=True)
                self.drop  = nn.Dropout(0.2)
                self.fc    = nn.Sequential(
                    nn.Linear(32, 16), nn.ReLU(), nn.Linear(16, 1), nn.Sigmoid()
                )
            def forward(self, x):
                o, _ = self.lstm1(x)
                o    = self.ln1(o[:, -1, :]).unsqueeze(1)
                o, _ = self.lstm2(o)
                return self.fc(self.drop(o[:, -1, :])).squeeze(1)

        net  = _Net().to(device)
        opt  = torch.optim.AdamW(net.parameters(), lr=0.001, weight_decay=1e-4)
        crit = nn.BCELoss()
        sched = torch.optim.lr_scheduler.CosineAnnealingLR(opt, T_max=50)

        # 데이터 크기에 따른 에포크 자동 조정
        n_samples_lstm = len(X_seq)
        max_epochs = _auto_params(n_samples_lstm)["lstm_epochs"]
        patience   = max(10, max_epochs // 10)

        log.info(f"  ┌ LSTM (PyTorch/{device.type.upper()}) 학습 시작")
        log.info(f"  │ 시퀀스: {SEQ}일  |  피처: {n_feat}개  |  샘플: {len(X_seq):,}개  |  최대 에포크: {max_epochs}")

        t0 = time.time()
        best_val, best_state, wait = 0.0, None, 0
        log_interval = max(1, max_epochs // 10)   # 10% 단위 로그

        for epoch in range(max_epochs):
            net.train()
            # 미니배치 학습 (M4 Metal 파이프라인 효율화)
            perm     = torch.randperm(len(Xtr), device=device)
            for i in range(0, len(Xtr), batch_sz):
                idx      = perm[i:i + batch_sz]
                opt.zero_grad()
                loss_b   = crit(net(Xtr[idx]), ytr[idx])
                loss_b.backward()
                nn.utils.clip_grad_norm_(net.parameters(), 1.0)
                opt.step()
            sched.step()

            net.eval()
            with torch.no_grad():
                val_acc = ((net(Xvl) > 0.5).float() == yvl).float().mean().item()
            if val_acc > best_val:
                best_val  = val_acc
                best_state = {k: v.clone() for k, v in net.state_dict().items()}
                wait = 0
            else:
                wait += 1
                if wait >= patience:
                    log.info(f"  │ Epoch {epoch+1:3d}/{max_epochs}  {_bar(epoch+1, max_epochs, 15)}  best_acc={best_val:.3f}  조기종료")
                    break

            if (epoch + 1) % log_interval == 0 or epoch == 0:
                log.info(f"  │ Epoch {epoch+1:3d}/{max_epochs}  {_bar(epoch+1, max_epochs, 15)}  val_acc={val_acc:.3f}  best={best_val:.3f}  ({time.time()-t0:.1f}s)")

        if best_state:
            net.load_state_dict(best_state)
        self.model      = net
        self.is_trained = True
        log.info(f"  └ LSTM 완료  best_val_acc={best_val:.3f}  ({time.time()-t0:.1f}s)")
        self.training_metrics = {
            "val_accuracy":    round(best_val, 4),
            "model_type":      f"LSTM (PyTorch/{device.type.upper()})",
            "sequence_length": SEQ,
            "n_features":      n_feat,
            "n_samples":       len(y_seq),
        }
        return self.training_metrics

    # ── TensorFlow ────────────────────────────────────────────
    def _train_tensorflow(self, X_sc: np.ndarray, y: np.ndarray) -> Dict:
        import tensorflow as tf
        try:
            from tensorflow import keras
        except Exception:
            import tensorflow.keras as keras  # type: ignore

        SEQ   = self.sequence_length
        X_seq = np.array([X_sc[i - SEQ:i] for i in range(SEQ, len(X_sc))])
        y_seq = y[SEQ:]
        split = int(len(X_seq) * 0.8)

        inp   = keras.Input(shape=(SEQ, X_seq.shape[2]))
        x     = keras.layers.LSTM(64, return_sequences=True)(inp)
        x     = keras.layers.LayerNormalization()(x)
        x     = keras.layers.Dropout(0.2)(x)
        x     = keras.layers.LSTM(32)(x)
        x     = keras.layers.Dropout(0.2)(x)
        x     = keras.layers.Dense(16, activation="relu")(x)
        out   = keras.layers.Dense(1, activation="sigmoid")(x)
        model = keras.Model(inp, out)

        model.compile(
            optimizer=keras.optimizers.Adam(0.001),
            loss="binary_crossentropy", metrics=["accuracy"],
        )
        n_ep = _auto_params(len(X_seq))["lstm_epochs"]
        log.info(f"  ┌ LSTM (TensorFlow) 학습 시작")
        log.info(f"  │ 시퀀스: {self.sequence_length}일  |  피처: {X_seq.shape[2]}개  |  샘플: {len(X_seq):,}개  |  최대 에포크: {n_ep}")

        class _LogCallback(keras.callbacks.Callback):
            def __init__(self, total, interval):
                self.total = total
                self.interval = interval
                self.t0 = time.time()
            def on_epoch_end(self, epoch, logs=None):
                logs = logs or {}
                if (epoch + 1) % self.interval == 0 or epoch == 0:
                    va = logs.get("val_accuracy", 0)
                    log.info(
                        f"  │ Epoch {epoch+1:3d}/{self.total}  "
                        f"{_bar(epoch+1, self.total, 15)}  "
                        f"val_acc={va:.3f}  ({time.time()-self.t0:.1f}s)"
                    )

        t0_tf = time.time()
        cb_es  = keras.callbacks.EarlyStopping(
            monitor="val_loss", patience=max(10, n_ep // 10),
            restore_best_weights=True,
        )
        cb_log = _LogCallback(total=n_ep, interval=max(1, n_ep // 10))
        hist = model.fit(
            X_seq[:split], y_seq[:split],
            validation_data=(X_seq[split:], y_seq[split:]),
            epochs=n_ep, batch_size=32, callbacks=[cb_es, cb_log], verbose=0,
        )
        self.model      = model
        self.is_trained = True
        val_acc = max(hist.history.get("val_accuracy", [0.5]))
        log.info(f"  └ LSTM (TF) 완료  best_val_acc={val_acc:.3f}  ({time.time()-t0_tf:.1f}s)")
        self.training_metrics = {
            "val_accuracy":    float(val_acc),
            "model_type":      "LSTM (TensorFlow-macos)",
            "sequence_length": SEQ,
            "n_features":      X_seq.shape[2],
            "n_samples":       len(y_seq),
        }
        return self.training_metrics

    # ── 예측 ─────────────────────────────────────────────────
    def predict_proba(self, df: pd.DataFrame) -> Optional[float]:
        if not self.is_trained or self.feature_cols is None:
            return None
        try:
            SEQ    = self.sequence_length
            recent = df[self.feature_cols].tail(SEQ).copy()
            recent = recent.ffill().bfill().fillna(0).replace([np.inf, -np.inf], 0)
            if len(recent) < SEQ:
                return None

            X_sc  = self.scaler.transform(recent.values)
            X_seq = X_sc.reshape(1, SEQ, -1)

            if self.framework == "pytorch":
                import torch
                device = next(self.model.parameters()).device
                self.model.eval()
                with torch.no_grad():
                    t = torch.tensor(X_seq.astype("float32")).to(device)
                    return float(self.model(t)[0].cpu().item())
            else:
                return float(self.model.predict(X_seq, verbose=0)[0, 0])
        except Exception:
            return None

    def predict(self, df: pd.DataFrame) -> Dict:
        p = self.predict_proba(df)
        if p is None:
            return {"error": "LSTM 예측 실패"}
        return _build_result(p, self.training_metrics.get("model_type", "LSTM"))


# ─────────────────────────────────────────────────────────────
# EnsemblePredictor  ← 메인 인터페이스
# ─────────────────────────────────────────────────────────────

class EnsemblePredictor:
    """
    XGBoost + LSTM 동적 앙상블 예측기.

    사용법:
        ep = EnsemblePredictor()
        metrics = ep.train(df)
        pred = ep.predict(df)
        # pred['signal'], pred['up_probability'], pred['ensemble_detail']
    """

    def __init__(
        self,
        sequence_length: int = 20,
        complexity_threshold: float = 0.30,
        min_lstm_weight: float = 0.20,
        max_lstm_weight: float = 0.55,
        scanner_mode: bool = False,            # ← 스캐너 호출 시 True
    ):
        """
        scanner_mode=True 시:
          - XGBoost nthread=1 (OMP 경합 방지)
          - LSTM device=cpu (MPS 동시 접근 크래시 방지)
          - CV fold 3개로 축소 (속도)
        """
        self.sequence_length       = sequence_length
        self.complexity_threshold  = complexity_threshold
        self.min_lstm_weight       = min_lstm_weight
        self.max_lstm_weight       = max_lstm_weight
        self.scanner_mode          = scanner_mode

        self.xgb   = XGBoostPredictor(scanner_mode=scanner_mode)
        self.lstm  = LSTMPredictor(sequence_length=sequence_length,
                                   scanner_mode=scanner_mode)
        self.regime = RegimeDetector()

        self.is_trained      = False
        self.lstm_trained    = False
        self.training_metrics: Dict = {}
        self.feature_importances_: Optional[pd.Series] = None

    # ── 가중치 계산 ───────────────────────────────────────────
    def _compute_weights(self, complexity: float) -> Tuple[float, float]:
        """
        complexity 와 각 모델 CV 정확도를 기반으로 (w_xgb, w_lstm) 계산.
        LSTM 미학습 시 (1.0, 0.0) 반환.
        """
        if not self.lstm_trained:
            return 1.0, 0.0

        # 복잡도에 따른 LSTM 기본 가중치
        raw_lstm_w = np.interp(
            complexity,
            [self.complexity_threshold, 1.0],
            [self.min_lstm_weight, self.max_lstm_weight],
        )

        # 모델 정확도로 보정
        xgb_acc  = self.xgb.training_metrics.get("cv_accuracy_mean",
                   self.xgb.training_metrics.get("train_accuracy", 0.5))
        lstm_acc = self.lstm.training_metrics.get("val_accuracy", 0.5)

        # 정확도 차이가 클수록 더 정확한 모델에 가중치 부여
        acc_ratio = lstm_acc / (xgb_acc + 1e-9)
        # 0.9 ~ 1.1 범위로 클램핑 (과도한 쏠림 방지)
        acc_ratio = float(np.clip(acc_ratio, 0.7, 1.3))

        lstm_w = float(np.clip(raw_lstm_w * acc_ratio, self.min_lstm_weight, self.max_lstm_weight))
        xgb_w  = 1.0 - lstm_w

        return round(xgb_w, 3), round(lstm_w, 3)

    # ── 학습 ─────────────────────────────────────────────────
    def train(
        self,
        df: pd.DataFrame,
        include_sentiment: bool = True,
        force_lstm: bool = False,
    ) -> Dict:
        """
        1. XGBoost 항상 학습
        2. 국면 감지
        3. 복잡 국면이거나 force_lstm=True 면 LSTM 추가 학습
        """
        ap_ens  = _auto_params(len(df))
        t_total = time.time()
        log.info(f"")
        log.info(f"{'='*55}")
        log.info(f"  앙상블 분석 시작  |  데이터: {len(df):,}일  |  {'감성 포함' if include_sentiment else '감성 제외'}")
        log.info(f"{'='*55}")

        # ── Step 1: XGBoost ──────────────────────────────────
        log.info(f"  [1/4] XGBoost 베이스라인 학습...")
        xgb_metrics = self.xgb.train(df, include_sentiment=include_sentiment)
        if "error" in xgb_metrics:
            log.error(f"  XGBoost 실패: {xgb_metrics['error']}")
            return xgb_metrics
        self.is_trained         = True
        self.feature_importances_ = self.xgb.feature_importances_
        xgb_acc = xgb_metrics.get("cv_accuracy_mean", xgb_metrics.get("train_accuracy", 0))
        log.info(f"  [1/4] ✅ XGBoost 완료  CV acc={xgb_acc:.3f}")

        # ── Step 2: 국면 감지 ─────────────────────────────────
        log.info(f"  [2/4] 시장 국면 분석 중...")
        regime_info = self.regime.compute(df)
        complexity  = regime_info["complexity"]
        use_lstm    = force_lstm or regime_info["use_lstm"]
        regime_name = regime_info["regime"]
        regime_emoji = {"simple":"🟢","moderate":"🟡","complex":"🔴"}.get(regime_name,"⚪")
        log.info(f"  [2/4] ✅ 국면: {regime_emoji} {regime_name} (복잡도={complexity:.3f})  LSTM필요={use_lstm}")

        # ── Step 3: LSTM (조건부) ─────────────────────────────
        lstm_metrics: Dict = {}
        lstm_fw   = LSTMPredictor.available_framework()
        max_lstm  = ap_ens.get('max_lstm_samples', DATA_CFG['max_lstm_samples'])
        lstm_df   = df.iloc[-max_lstm:] if len(df) > max_lstm else df

        if self.scanner_mode and use_lstm and lstm_fw:
            # 전략 C: scanner_mode에서는 LSTM을 CPU로만 실행
            # - device='cpu' 강제 (MPS 동시 접근 금지)
            # - num_threads=1 (OMP 경합 방지)
            # - 워커 3개 × num_threads=1 = OMP 3개 → 안전
            log.info(f"  [3/4] LSTM (CPU 전용) 학습 중... (전략 C, 프레임워크: {lstm_fw})")
            lstm_metrics = self.lstm.train(lstm_df, include_sentiment=include_sentiment)
            if "error" not in lstm_metrics:
                self.lstm_trained = True
                lstm_acc = lstm_metrics.get("val_accuracy", 0)
                log.info(f"  [3/4] ✅ LSTM 완료  val_acc={lstm_acc:.3f}  device=CPU")
            else:
                self.lstm_trained = False
                log.warning(f"  [3/4] ⚠  LSTM 실패: {lstm_metrics.get('error')} → XGBoost 단독")
        elif self.scanner_mode and not use_lstm:
            self.lstm_trained = False
            log.info(f"  [3/4] ⏭  LSTM 스킵 (국면={regime_name}, 복잡도 낮음)")
        elif use_lstm and lstm_fw:
            log.info(f"  [3/4] LSTM 학습 중... (프레임워크: {lstm_fw}, 데이터: {len(lstm_df):,}일)")
            lstm_metrics = self.lstm.train(lstm_df, include_sentiment=include_sentiment)
            if "error" not in lstm_metrics:
                self.lstm_trained = True
                lstm_acc = lstm_metrics.get("val_accuracy", 0)
                log.info(f"  [3/4] ✅ LSTM 완료  val_acc={lstm_acc:.3f}")
            else:
                self.lstm_trained = False
                log.warning(f"  [3/4] ⚠  LSTM 실패: {lstm_metrics.get('error')} → XGBoost 단독")
        else:
            self.lstm_trained = False
            reason = "LSTM 강제 비활성화" if not use_lstm else f"{lstm_fw or '프레임워크 없음'}"
            log.info(f"  [3/4] ⏭  LSTM 스킵 ({reason})")

        # ── Step 4: 앙상블 메타 정보 ──────────────────────────
        log.info(f"  [4/4] 앙상블 가중치 계산 중...")
        w_xgb, w_lstm = self._compute_weights(complexity)

        self.training_metrics = {
            "model_type":       self._model_label(w_xgb, w_lstm),
            "xgb_metrics":      xgb_metrics,
            "lstm_metrics":     lstm_metrics,
            "regime":           regime_info,
            "w_xgb":            w_xgb,
            "w_lstm":           w_lstm,
            "lstm_active":      self.lstm_trained,
            "lstm_framework":   lstm_fw or "없음",
            "n_samples":        xgb_metrics.get("n_samples", 0),
            "n_features":       xgb_metrics.get("n_features", 0),
            "cv_accuracy_mean": xgb_metrics.get("cv_accuracy_mean",
                                xgb_metrics.get("train_accuracy", 0)),
        }
        if self.lstm_trained:
            self.training_metrics["lstm_val_accuracy"] = lstm_metrics.get("val_accuracy", 0)

        log.info(f"  모델: {self.training_metrics['model_type']}")
        log.info(f"  가중치: XGB={w_xgb:.0%}  LSTM={w_lstm:.0%}")
        log.info(f"{'='*55}")
        log.info(f"  ✅ 앙상블 학습 완료  총 소요: {time.time()-t_total:.1f}s")
        log.info(f"")
        return self.training_metrics

    def _model_label(self, w_xgb: float, w_lstm: float) -> str:
        if w_lstm == 0.0:
            return "XGBoost (단독)"
        pct_xgb  = int(round(w_xgb * 100))
        pct_lstm = int(round(w_lstm * 100))
        return f"Ensemble (XGB {pct_xgb}% + LSTM {pct_lstm}%)"

    # ── 예측 ─────────────────────────────────────────────────
    def predict(self, df: pd.DataFrame) -> Dict:
        if not self.is_trained:
            return {"error": "모델 미학습"}

        # ── XGBoost 확률 ──────────────────────────────────────
        p_xgb = self.xgb.predict_proba(df)
        if p_xgb is None:
            return {"error": "XGBoost 예측 실패"}

        # ── LSTM 확률 (학습된 경우만) ─────────────────────────
        p_lstm: Optional[float] = None
        if self.lstm_trained:
            p_lstm = self.lstm.predict_proba(df)

        # ── 현재 국면 재감지 (predict 시점 최신 데이터 기준) ──
        regime_now  = self.regime.compute(df)
        complexity  = regime_now["complexity"]
        w_xgb, w_lstm = self._compute_weights(complexity)

        # LSTM 확률이 없으면 XGBoost 단독
        if p_lstm is None:
            w_xgb, w_lstm = 1.0, 0.0
            p_final = p_xgb
        else:
            p_final = w_xgb * p_xgb + w_lstm * p_lstm

        # ── 신호 결정 ─────────────────────────────────────────
        # 앙상블 불일치 시 HOLD 방향으로 신뢰도 하락
        if p_lstm is not None:
            agree = (p_xgb > 0.5) == (p_lstm > 0.5)
            if not agree:
                # 두 모델이 반대 의견 → 확률을 0.5 방향으로 당김
                p_final = 0.5 + (p_final - 0.5) * 0.6

        result = _build_result(p_final, self.training_metrics.get("model_type", "Ensemble"))
        result["ensemble_detail"] = {
            "p_xgb":        round(p_xgb, 4),
            "p_lstm":       round(p_lstm, 4) if p_lstm is not None else None,
            "w_xgb":        w_xgb,
            "w_lstm":       w_lstm,
            "complexity":   complexity,
            "regime":       regime_now["regime"],
            "regime_scores": regime_now["scores"],
            "models_agree": bool((p_xgb > 0.5) == (p_final > 0.5))
                            if p_lstm is not None else True,
        }
        return result


# ─────────────────────────────────────────────────────────────
# 공통 유틸
# ─────────────────────────────────────────────────────────────

def _build_result(up_prob: float, model_name: str) -> Dict:
    """상승 확률 → 예측 딕셔너리 변환."""
    down_prob  = 1.0 - up_prob
    confidence = max(up_prob, down_prob)
    if   up_prob   > 0.58: signal = "BUY"
    elif down_prob > 0.58: signal = "SELL"
    else:                   signal = "HOLD"
    return {
        "direction":      1 if up_prob >= 0.5 else 0,
        "up_probability": round(up_prob, 4),
        "down_probability": round(down_prob, 4),
        "confidence":     round(confidence, 4),
        "signal":         signal,
        "model":          model_name,
    }


# ─────────────────────────────────────────────────────────────
# 백테스팅 (EnsemblePredictor 호환)
# ─────────────────────────────────────────────────────────────

def run_backtest(
    df: pd.DataFrame,
    predictor: EnsemblePredictor,
    initial_capital: float = 10_000_000,
    commission_rate: float = 0.001,
) -> Dict:
    """Walk-forward 백테스트. EnsemblePredictor / XGBoostPredictor 모두 호환."""
    if not predictor.is_trained:
        return {}

    close     = df["Close"]
    capital   = initial_capital
    shares    = 0
    position  = "NONE"
    trades    = []
    portfolio = []
    MIN_TRAIN = 80

    for i in range(MIN_TRAIN, len(df) - 1):
        if i == MIN_TRAIN or (i - MIN_TRAIN) % 20 == 0:
            # 백테스트 재학습: 속도 위해 XGBoost만 사용
            sub = df.iloc[:i]
            if isinstance(predictor, EnsemblePredictor):
                predictor.xgb.train(sub, include_sentiment=False)
            else:
                predictor.train(sub, include_sentiment=False)

        if isinstance(predictor, EnsemblePredictor):
            p_xgb = predictor.xgb.predict_proba(df.iloc[:i + 1])
            pred  = _build_result(p_xgb or 0.5, "XGBoost") if p_xgb else {"error": "x"}
        else:
            pred  = predictor.predict(df.iloc[:i + 1])

        if "error" in pred:
            portfolio.append({"date": df.index[i],
                              "value": capital + shares * float(close.iloc[i])})
            continue

        sig    = pred["signal"]
        price  = float(close.iloc[i])

        if sig == "BUY" and position == "NONE":
            shares = int(capital * (1 - commission_rate) / price)
            if shares > 0:
                capital  -= shares * price * (1 + commission_rate)
                position  = "LONG"
                trades.append({"date": df.index[i], "type": "BUY",
                               "price": price, "shares": shares})

        elif sig == "SELL" and position == "LONG":
            capital  += shares * price * (1 - commission_rate)
            position  = "NONE"
            trades.append({"date": df.index[i], "type": "SELL",
                           "price": price, "shares": shares})
            shares = 0

        portfolio.append({"date": df.index[i],
                          "value": capital + (shares * price if position == "LONG" else 0)})

    if position == "LONG" and shares > 0:
        capital += shares * float(close.iloc[-1]) * (1 - commission_rate)

    if not portfolio:
        return {}

    port_df = pd.DataFrame(portfolio).set_index("date")
    strat   = (capital / initial_capital - 1) * 100
    bench   = (float(close.iloc[-1]) / float(close.iloc[MIN_TRAIN]) - 1) * 100

    return {
        "initial_capital":      initial_capital,
        "final_capital":        round(capital, 2),
        "strategy_return_pct":  round(strat, 2),
        "benchmark_return_pct": round(bench, 2),
        "excess_return":        round(strat - bench, 2),
        "n_trades":             len(trades),
        "trades":               trades,
        "portfolio_values":     port_df,
    }