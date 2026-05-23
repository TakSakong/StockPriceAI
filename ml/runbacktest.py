import os
# local docker-compose redis에 연결할 수 있도록 호스트를 localhost로 덮어씁니다.
os.environ["REDIS_URL"] = "redis://localhost:6379/1"

import pandas as pd
import numpy as np
from datetime import datetime

from ml.app.models.predictor import EnsemblePredictor
from ml.app.pipelines.fetcher import fetch_stock_data
from ml.app.pipelines.technical import add_all_indicators
from ml.app.pipelines.get_recent_SP500_tickers import get_sp500_tickers

# 외부 패키지 의존성을 없애기 위한 간이 표 출력 함수
def tabulate(data, headers=None, exclude=None):
    if exclude is None:
        exclude = []
        
    if isinstance(data, pd.DataFrame):
        cols = [c for c in data.columns if c not in exclude]
        rows = [[str(row[c]) for c in cols] for _, row in data.iterrows()]
        col_names = cols
    elif isinstance(data, list) and len(data) > 0 and isinstance(data[0], dict):
        cols = [k for k in data[0].keys() if k not in exclude]
        rows = [[str(row[c]) for c in cols] for row in data]
        col_names = cols
    else:
        return str(data)

    # 열 너비 계산
    widths = [len(name) for name in col_names]
    for row in rows:
        for i, val in enumerate(row):
            widths[i] = max(widths[i], len(val))

    # 표 그리기
    border = "+" + "+".join(["-" * (w + 2) for w in widths]) + "+"
    header_line = "|" + "|".join([f" {col_names[i].ljust(widths[i])} " for i in range(len(col_names))]) + "|"
    
    result_lines = [border, header_line, border]
    for row in rows:
        row_line = "|" + "|".join([f" {row[i].ljust(widths[i])} " for i in range(len(row))]) + "|"
        result_lines.append(row_line)
    result_lines.append(border)
    
    return "\n".join(result_lines)


def analyze_single_ticker_as_of(ticker: str, df_as_of: pd.DataFrame, info: dict) -> dict | None:
    """지정 시점까지의 데이터를 기준으로 composite_score와 예측 결과를 계산하는 함수."""
    try:
        if df_as_of is None or len(df_as_of) < 60:
            return None

        pred_m = EnsemblePredictor(scanner_mode=True)
        metrics = pred_m.train(df_as_of, include_sentiment=False, force_lstm=False)
        if "error" in metrics:
            return None

        pred = pred_m.predict(df_as_of)
        if "error" in pred:
            return None

        latest = df_as_of.iloc[-1]
        close = float(df_as_of["Close"].iloc[-1])
        high_52w = float(df_as_of["High"].tail(252).max())
        upside52 = (high_52w - close) / close * 100
        atr_pct = float(latest.get("ATR_Pct", 1.0))
        exp3m = atr_pct * np.sqrt(63)
        rsi = float(latest.get("RSI14", 50))
        up_prob = float(pred["up_probability"])

        est_up = (
            up_prob * exp3m * 0.4
            + max(0.0, (70 - rsi) / 70) * exp3m * 0.3
            + min(upside52, 30) * 0.3
        )

        momentum = float(latest.get("Momentum_Normalized", 0))
        mom_f = (
            0.7 if momentum > 0.15 else
            0.9 if momentum > 0.05 else
            1.1 if momentum < -0.10 else 1.0
        )
        composite = up_prob * est_up * mom_f

        per = info.get("trailingPE")
        beta = float(info.get("beta", 1.0) or 1.0)
        mktcap = float(info.get("marketCap", 0) or 0)
        qf = (
            (0.8 if mktcap < 1e9 else 1.0)
            * (0.7 if per and per < 0 else 1.0)
            * (0.8 if beta > 3 else 1.0)
        )
        composite *= qf

        return {
            "ticker": ticker,
            "name": info.get("shortName", ticker),
            "sector": info.get("sector", "N/A"),
            "price_at_scan": round(close, 2),
            "up_probability": round(up_prob * 100, 1),
            "composite_score": round(composite, 4),
            "rsi": round(rsi, 1),
            "ml_signal": pred["signal"],
        }
    except Exception as e:
        return None


# ═════════════════════════════════════════════════════════════
# ⚙️  백테스트 설정 — 이 블록의 값만 수정하면 됩니다
# ═════════════════════════════════════════════════════════════

# 1. 백테스트 시작 시점
#    - 특정 날짜 지정: "YYYY-MM-DD" 형태 문자열
#    - 자동 (오늘 기준 1년 전): None
BACKTEST_START_DATE = "2025-05-21"

# 2. 포트폴리오에 유지할 상위 종목 개수
TOP_N_STOCKS = 10

# 3. 매매 의사결정 주기 (거래일 기준)
#    예) 1: 매일 판단, 5: 일주일에 한 번, 20: 한 달에 한 번
DECISION_INTERVAL_DAYS = 1

# 4. 스캐너 갱신 주기 (거래일 기준)
#    예) 60: 3개월마다 상위 종목 교체, 0: 최초 1회만 스캔
SCAN_REFRESH_INTERVAL_DAYS = 60

# 5. 거래 수수료율 (편도)
#    예) 0.001 = 0.1%
COMMISSION_RATE = 0.001

# 6. 스캔 대상 종목 풀
#    기본값: 실제 스캐너(scanner.py)에서 사용하는 SP500_TICKERS 전체
#    일부만 사용하려면 리스트 형태로 직접 지정 가능
#    예) TICKERS = ["AAPL", "MSFT", "NVDA"]
TICKERS = get_sp500_tickers()

# ─────────────────────────────────────────────────────────────
# 메인 실행 흐름 (수정 불필요)
# ─────────────────────────────────────────────────────────────

commission_rate = COMMISSION_RATE

print(f"[설정] 백테스트 시작일: {BACKTEST_START_DATE if BACKTEST_START_DATE else '1년 전 자동계산'}")
print(f"[설정] 포트폴리오 유지 종목 수 (N): {TOP_N_STOCKS}개")
print(f"[설정] 매매 의사결정 주기: {DECISION_INTERVAL_DAYS}거래일")
print(f"[설정] 스캐너 갱신 주기: {SCAN_REFRESH_INTERVAL_DAYS}거래일\n")

print(f"1. {len(TICKERS)}개 실제 스캐너 후보 종목의 전체 역사적 데이터(550일)를 로드하는 중...")
stock_data_dict = {}
for idx, ticker in enumerate(TICKERS, 1):
    try:
        df, info = fetch_stock_data(ticker, period_days=550)
        if df is not None and len(df) >= 60:
            df = add_all_indicators(df)
            stock_data_dict[ticker] = (df, info)
    except Exception:
        pass

if not stock_data_dict:
    print("로드 성공한 데이터가 없습니다.")
    exit(1)

# 시작 날짜 및 인덱스 구하기
sample_df = list(stock_data_dict.values())[0][0]
if BACKTEST_START_DATE:
    start_dt = pd.to_datetime(BACKTEST_START_DATE)
    start_idx = int(np.searchsorted(sample_df.index, start_dt))
else:
    one_year_ago = sample_df.index[-1] - pd.Timedelta(days=365)
    start_idx = int(np.searchsorted(sample_df.index, one_year_ago))

start_idx = max(start_idx, 60)
total_days = len(sample_df)

# 포트폴리오 상태 변수 초기화
initial_capital = 10000 * TOP_N_STOCKS  # 종목당 1만달러 수준의 포트폴리오
cash = initial_capital
positions = {}  # {ticker: {"shares": int, "position": str, "predictor": predictor, "last_trained_idx": int}}
current_top_n = []
portfolio_history = []

print(f"\n2. 포트폴리오 시뮬레이션을 시작합니다. (초기 자산: ${initial_capital:,})")

for i in range(start_idx, total_days):
    current_date = sample_df.index[i].strftime('%Y-%m-%d')
    
    # ── [A] 스캐너 갱신 시점 확인 및 포트폴리오 재조정 ──
    is_scan_day = (i == start_idx) or (SCAN_REFRESH_INTERVAL_DAYS > 0 and (i - start_idx) % SCAN_REFRESH_INTERVAL_DAYS == 0)
    
    if is_scan_day:
        print(f"\n🔄 [스캐너 갱신일: {current_date}] 새로운 상위 {TOP_N_STOCKS}개 종목 스캔을 실행합니다...")
        scan_results = []
        for ticker, (df, info) in stock_data_dict.items():
            df_as_of = df.iloc[:i]
            res = analyze_single_ticker_as_of(ticker, df_as_of, info)
            if res:
                scan_results.append(res)
        
        # 새로운 상위 N개 선택
        df_scan = pd.DataFrame(scan_results)
        df_scan = df_scan.sort_values("composite_score", ascending=False).reset_index(drop=True)
        new_top_n = df_scan.head(TOP_N_STOCKS)["ticker"].tolist()
        
        # 포트폴리오 제외 종목 매도 처리 (기존 탑 N에 있었으나 새로운 탑 N에 없는 경우)
        for ticker in list(positions.keys()):
            if ticker not in new_top_n and positions[ticker]["position"] == "LONG":
                close_p = float(stock_data_dict[ticker][0]["Close"].iloc[i])
                shares = positions[ticker]["shares"]
                sell_val = shares * close_p * (1 - commission_rate)
                cash += sell_val
                print(f"   [포트폴리오 제외 매도] {ticker}: {shares}주 매도 (${close_p:,.2f}) -> 현금 ${sell_val:,.2f} 회수")
                positions[ticker] = {"shares": 0, "position": "NONE", "predictor": None, "last_trained_idx": 0}
                
        current_top_n = new_top_n
        print(f"   👉 새로운 추천 종목군: {', '.join(current_top_n)}")
    
    # ── [B] 현재 자산 가치 평가 ──
    current_val = cash
    for ticker in current_top_n:
        if ticker in positions and positions[ticker]["position"] == "LONG":
            close_p = float(stock_data_dict[ticker][0]["Close"].iloc[i])
            current_val += positions[ticker]["shares"] * close_p
            
    # ── [C] 매일 매수/매도/보유 신호 갱신 및 주문 체결 ──
    if (i - start_idx) % DECISION_INTERVAL_DAYS == 0:
        for ticker in current_top_n:
            df, info = stock_data_dict[ticker]
            close_p = float(df["Close"].iloc[i])
            
            # 예측기 가져오기 또는 새로 학습
            if ticker not in positions or positions[ticker]["predictor"] is None:
                predictor = EnsemblePredictor(scanner_mode=False)
                predictor.train(df.iloc[:i], include_sentiment=False)
                positions[ticker] = {
                    "shares": 0,
                    "position": "NONE",
                    "predictor": predictor,
                    "last_trained_idx": i
                }
            else:
                # 60일 경과 시 개별 예측 모델 주기적 업데이트
                pos_entry = positions[ticker]
                if i - pos_entry["last_trained_idx"] >= 60:
                    predictor = EnsemblePredictor(scanner_mode=False)
                    predictor.train(df.iloc[:i], include_sentiment=False)
                    pos_entry["predictor"] = predictor
                    pos_entry["last_trained_idx"] = i
            
            # 오늘자 예측 결과 생성
            predictor = positions[ticker]["predictor"]
            pred = predictor.predict(df.iloc[: i + 1])
            sig = pred.get("signal", "HOLD")
            
            # 신호 처리
            if sig == "BUY" and positions[ticker]["position"] == "NONE":
                target_alloc = current_val / TOP_N_STOCKS
                buy_cash = min(cash, target_alloc)
                shares = int(buy_cash * (1 - commission_rate) / close_p)
                if shares > 0:
                    cash -= shares * close_p * (1 + commission_rate)
                    positions[ticker]["shares"] = shares
                    positions[ticker]["position"] = "LONG"
                    print(f"   [매수 체결] {ticker}: {shares}주 매수 (${close_p:,.2f})")
                    
            elif sig == "SELL" and positions[ticker]["position"] == "LONG":
                shares = positions[ticker]["shares"]
                sell_val = shares * close_p * (1 - commission_rate)
                cash += sell_val
                positions[ticker]["shares"] = 0
                positions[ticker]["position"] = "NONE"
                print(f"   [매도 체결] {ticker}: {shares}주 전량 매도 (${close_p:,.2f}) -> 현금 ${sell_val:,.2f} 회수")

    # ── [D] 하루 자산 가치 기록 저장 ──
    # 하루 일과 후 최종 포트폴리오 가치 재평가
    end_day_val = cash
    for ticker in current_top_n:
        if ticker in positions and positions[ticker]["position"] == "LONG":
            close_p = float(stock_data_dict[ticker][0]["Close"].iloc[i])
            end_day_val += positions[ticker]["shares"] * close_p
            
    portfolio_history.append({
        "Date": current_date,
        "Total Portfolio Value": round(end_day_val, 2),
        "Cash": round(cash, 2),
    })

# 백테스트 종료 시 모든 보유 종목을 시장가 청산
print("\n🏁 백테스트가 종료되었습니다. 전체 자산을 현금으로 청산합니다...")
final_cash = cash
for ticker in current_top_n:
    if ticker in positions and positions[ticker]["position"] == "LONG":
        close_p = float(stock_data_dict[ticker][0]["Close"].iloc[-1])
        shares = positions[ticker]["shares"]
        sell_val = shares * close_p * (1 - commission_rate)
        final_cash += sell_val
        print(f"   [종료 청산] {ticker}: {shares}주 청산 (${close_p:,.2f}) -> ${sell_val:,.2f}")
        positions[ticker]["position"] = "NONE"
        positions[ticker]["shares"] = 0

# 최종 수익률 출력
total_return_pct = (final_cash / initial_capital - 1) * 100
print("\n" + "="*50)
print("             💰 포트폴리오 최종 성과 요약")
print("="*50)
print(f"시작 시점: {sample_df.index[start_idx].strftime('%Y-%m-%d')}")
print(f"종료 시점: {sample_df.index[-1].strftime('%Y-%m-%d')}")
print(f"초기 투자금: ${initial_capital:,.2f}")
print(f"최종 평가액: ${final_cash:,.2f}")
print(f"누적 수익률: {total_return_pct:.2f}%")
print("="*50)
