import os
# local docker-compose redis에 연결할 수 있도록 호스트를 localhost로 덮어씁니다.
os.environ["REDIS_URL"] = "redis://localhost:6379/1"

import pandas as pd
import numpy as np
from datetime import datetime

from ml.app.models.predictor import EnsemblePredictor
from ml.app.pipelines.fetcher import fetch_stock_data
from ml.app.pipelines.technical import add_all_indicators, get_current_signals
from ml.app.pipelines.scanner import SP500_TICKERS

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
    """지정 시점까지의 슬라이싱된 데이터를 기준으로 composite_score와 예측 결과를 계산하는 함수."""
    try:
        if df_as_of is None or len(df_as_of) < 60:
            return None

        # 1. 특정 시점까지의 데이터로 앙상블 모델 학습
        pred_m = EnsemblePredictor(scanner_mode=True)
        metrics = pred_m.train(df_as_of, include_sentiment=False, force_lstm=False)
        if "error" in metrics:
            return None

        # 2. 특정 시점에서의 예측 실행
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
        bb_pos = float(latest.get("BB_Position", 0.5))
        up_prob = float(pred["up_probability"])

        # composite_score 계산 공식
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


def run_backtest_last_year(
    df: pd.DataFrame,
    start_date_str: str,
    initial_capital: float = 10000,
    commission_rate: float = 0.001,
    retrain_interval: int = 60,
    decision_interval: int = 1,  # 매매 판단 주기 (거래일 기준, 예: 1은 매일, 5는 5일마다)
) -> dict:
    """설정된 시작 시점부터 매매 신호를 갱신하며 백테스트를 수행하는 함수."""
    close = df["Close"]
    capital = initial_capital
    shares = 0
    position = "NONE"
    trades = []
    portfolio_values = []

    # 백테스트 시작 인덱스 탐색
    start_dt = pd.to_datetime(start_date_str)
    start_idx = int(np.searchsorted(df.index, start_dt))
    start_idx = max(start_idx, 60)
    
    start_date = df.index[start_idx].strftime('%Y-%m-%d')
    end_date = df.index[-1].strftime('%Y-%m-%d')

    # 최초 학습 (시작일 이전 데이터로만 학습)
    predictor = EnsemblePredictor(scanner_mode=False)
    predictor.train(df.iloc[:start_idx], include_sentiment=False)

    days_since_retrain = 0

    for i in range(start_idx, len(df)):
        price = float(close.iloc[i])

        # 1. 의사결정 주기(decision_interval) 도달 여부 체크
        if (i - start_idx) % decision_interval != 0:
            portfolio_values.append(capital + (shares * price if position == "LONG" else 0))
            days_since_retrain += 1
            continue

        # 2. 주기적 모델 재학습 (갱신)
        if retrain_interval > 0 and days_since_retrain >= retrain_interval:
            predictor = EnsemblePredictor(scanner_mode=False)
            predictor.train(df.iloc[:i], include_sentiment=False)
            days_since_retrain = 0

        current_df = df.iloc[: i + 1]
        pred = predictor.predict(current_df)

        if "error" in pred:
            portfolio_values.append(
                capital + (shares * price if position == "LONG" else 0)
            )
            days_since_retrain += 1
            continue

        sig = pred["signal"]

        # BUY/SELL/HOLD 처리
        if sig == "BUY" and position == "NONE":
            shares = int(capital * (1 - commission_rate) / price)
            if shares > 0:
                capital -= shares * price * (1 + commission_rate)
                position = "LONG"
                trades.append({"type": "BUY", "price": price, "shares": shares})

        elif sig == "SELL" and position == "LONG":
            capital += shares * price * (1 - commission_rate)
            position = "NONE"
            trades.append({"type": "SELL", "price": price, "shares": shares})
            shares = 0

        portfolio_values.append(capital + (shares * price if position == "LONG" else 0))
        days_since_retrain += 1

    if position == "LONG" and shares > 0:
        capital += shares * float(close.iloc[-1]) * (1 - commission_rate)

    return {
        "start_date": start_date,
        "end_date": end_date,
        "initial_capital": initial_capital,
        "final_capital": round(capital, 2),
        "strategy_return_pct": round((capital / initial_capital - 1) * 100, 2),
        "n_trades": len(trades),
        "portfolio_values": portfolio_values,
    }


# ─────────────────────────────────────────────────────────────
# ⚙️ 백테스트 설정 변수 (사용자 정의 구역)
# ─────────────────────────────────────────────────────────────

# 1. 백테스트 및 스캔 시점 설정 (None으로 설정하면 오늘로부터 정확히 1년 전으로 자동 계산)
#    예: "2025-05-21" 형태로 특정 날짜 지정 가능
BACKTEST_START_DATE = "2025-05-21"

# 2. 스캐너 결과에서 상위 몇 개의 종목을 선택하여 백테스트할 것인가
TOP_N_STOCKS = 10

# 3. 몇 거래일을 주기로 사거나 팔거나 보유할지 의사결정 간격 설정
#    (1: 매일 판단 갱신, 5: 5거래일(일주일)마다 판단 갱신, 20: 20거래일(한달)마다 판단 갱신)
DECISION_INTERVAL_DAYS = 1

# ─────────────────────────────────────────────────────────────
# 메인 실행 흐름
# ─────────────────────────────────────────────────────────────

TICKERS = SP500_TICKERS

print(f"[설정] 스캔 시작일: {BACKTEST_START_DATE if BACKTEST_START_DATE else '1년 전 자동계산'}")
print(f"[설정] 투자 대상 종목 수: 상위 {TOP_N_STOCKS}개")
print(f"[설정] 매매 의사결정 주기: {DECISION_INTERVAL_DAYS}거래일 기준\n")

print(f"1. {len(TICKERS)}개 실제 스캐너 후보 종목의 전체 역사적 데이터(550일)를 로드하는 중...")
stock_data_dict = {}
for idx, ticker in enumerate(TICKERS, 1):
    if idx % 30 == 0 or idx == len(TICKERS):
        print(f" -> 데이터 로딩 중... ({idx}/{len(TICKERS)})")
    try:
        df, info = fetch_stock_data(ticker, period_days=550)
        if df is not None and len(df) >= 60:
            df = add_all_indicators(df)
            stock_data_dict[ticker] = (df, info)
    except Exception as e:
        pass

if not stock_data_dict:
    print("로드 성공한 데이터가 없습니다.")
    exit(1)

# 시작 날짜 계산 및 검증
sample_df = list(stock_data_dict.values())[0][0]
if BACKTEST_START_DATE:
    start_dt = pd.to_datetime(BACKTEST_START_DATE)
    start_idx = int(np.searchsorted(sample_df.index, start_dt))
else:
    one_year_ago = sample_df.index[-1] - pd.Timedelta(days=365)
    start_idx = int(np.searchsorted(sample_df.index, one_year_ago))

start_idx = max(start_idx, 60)
scan_date = sample_df.index[start_idx].strftime('%Y-%m-%d')

print(f"\n2. [스캔 시점: {scan_date}] 실제 스캐너 로직으로 후보군 {len(stock_data_dict)}개 종목을 분석합니다...")
scan_results = []

for idx, (ticker, (df, info)) in enumerate(stock_data_dict.items(), 1):
    if idx % 30 == 0 or idx == len(stock_data_dict):
        print(f" -> 분석 진행 중... ({idx}/{len(stock_data_dict)})")
    df_as_of = df.iloc[:start_idx]
    res = analyze_single_ticker_as_of(ticker, df_as_of, info)
    if res:
        scan_results.append(res)

if not scan_results:
    print("스캔 분석에 성공한 종목이 없습니다.")
    exit(1)

# composite_score가 높은 순으로 상위 TOP_N_STOCKS개 종목 선택
df_scan = pd.DataFrame(scan_results)
df_scan = df_scan.sort_values("composite_score", ascending=False).reset_index(drop=True)
top_selected = df_scan.head(TOP_N_STOCKS)

print(f"\n=== 스캔 기준일({scan_date}) 상위 {TOP_N_STOCKS}개 추천 종목 ===")
print(tabulate(top_selected))

# 3. 상위 선택 종목에 대해 백테스트 수행
print(f"\n3. 선정된 {TOP_N_STOCKS}개 종목에 대해 {scan_date}부터 백테스트를 진행합니다...")
results = []
initial_capital_per_stock = 10000

for idx, row in top_selected.iterrows():
    ticker = row["ticker"]
    df, info = stock_data_dict[ticker]
    try:
        res = run_backtest_last_year(
            df, 
            start_date_str=scan_date,
            initial_capital=initial_capital_per_stock, 
            commission_rate=0.001,
            retrain_interval=60,
            decision_interval=DECISION_INTERVAL_DAYS
        )
        if res:
            print(f" -> [{ticker}] 백테스트 완료 ({res['start_date']} ~ {res['end_date']}, 거래횟수: {res['n_trades']}회, 수익률: {res['strategy_return_pct']}%)")
            results.append({
                "Ticker": ticker,
                "Company": row["name"],
                "Period": f"{res['start_date']} ~ {res['end_date']}",
                "Initial Capital": f"${res['initial_capital']:,}",
                "Final Capital": f"${res['final_capital']:,}",
                "Return (%)": f"{res['strategy_return_pct']}%",
                "Trades": res["n_trades"],
                "raw_return": res['strategy_return_pct'],
                "raw_final": res['final_capital']
            })
    except Exception as e:
        print(f"    [{ticker}] 백테스트 중 오류 발생: {e}")

# 4. 개별 백테스트 결과 및 전체 요약 출력
if not results:
    print("성공한 백테스트 결과가 없습니다.")
    exit(1)

print(f"\n=== 스캔 기준일({scan_date}) 선택된 상위 {TOP_N_STOCKS}개 종목의 백테스트 결과 ===")
print(tabulate(results, exclude=["raw_return", "raw_final"]))

# 포트폴리오(동일 비중) 전체 수익률 요약
total_initial = initial_capital_per_stock * len(results)
total_final = sum(r["raw_final"] for r in results)
avg_return_pct = (total_final / total_initial - 1) * 100

print("\n=== 전체 동일 비중(Equal-Weight) 포트폴리오 요약 ===")
print(f"총 투자 종목 수: {len(results)}개")
print(f"총 초기 자금: ${total_initial:,}")
print(f"총 최종 자금: ${total_final:,.2f}")
print(f"포트폴리오 최종 수익률: {avg_return_pct:.2f}%")
print(f"평균 거래 횟수: {np.mean([r['Trades'] for r in results]):.1f}회")
