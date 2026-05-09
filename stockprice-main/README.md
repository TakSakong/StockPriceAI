# 📈 AI-Powered Stock Analyzer

기술적 분석 · 머신러닝 앙상블 · 뉴스 임팩트 정량화를 결합한  
**macOS Apple Silicon (M4 Pro) 최적화** 주가 예측 시스템

---

## 목차

1. [개요](#1-개요)
2. [주요 기능](#2-주요-기능)
3. [시스템 아키텍처](#3-시스템-아키텍처)
4. [설치 방법](#4-설치-방법)
5. [실행](#5-실행)
6. [모듈 상세](#6-모듈-상세)
7. [앙상블 예측 엔진](#7-앙상블-예측-엔진)
8. [뉴스 임팩트 프레임워크](#8-뉴스-임팩트-프레임워크)
9. [S&P 500 스캐너](#9-sp-500-스캐너)
10. [관심종목 관리](#10-관심종목-관리)
11. [M4 Pro 최적화 상세](#11-m4-pro-최적화-상세)
12. [터미널 로그 읽는 법](#12-터미널-로그-읽는-법)
13. [주의사항 및 면책](#13-주의사항-및-면책)

---

## 1. 개요

Bloomberg · Reuters 기사를 필터링하고, 기술적 지표 30개를 계산하고, XGBoost와 LSTM을 앙상블로 결합해 다음 거래일 주가 방향성(상승/하락)을 예측하는 Streamlit 대시보드입니다.

### 핵심 설계 원칙

- **노이즈 제거 우선** — 뉴스 95%는 노이즈. Surprise·Structural·Contagion 3단계 필터로 5%의 시그널만 추출
- **정량화** — 뉴스 임팩트를 `I = (S × M) × √V × P` 공식으로 수치화
- **앙상블** — XGBoost(베이스라인) + LSTM(복잡 국면) 동적 가중 결합
- **DP 캐싱** — 첫 스캔 후 EWMA 블렌딩으로 이후 스캔 시간 대폭 단축
- **Apple Silicon 최적화** — M4 Pro P코어·E코어·MPS 자동 감지 및 활용

---

## 2. 주요 기능

### 📊 개별 종목 분석
- yfinance로 주가 데이터 수집 (1년~전체 기간 선택)
- 기술적 지표 30개 자동 계산
- XGBoost + LSTM 앙상블 예측 (상승 확률, 신호)
- 뉴스 감성 분석 + Impact Score 계산
- 차트: 캔들스틱, MACD, 지지/저항선 (기간 선택 가능)
- 재무 정보: PER, 시가총액, 52주 고저가

### 🔭 S&P 500 배치 스캐너
- 최대 500개 종목 일괄 분석
- XGBoost + LSTM 전체 앙상블 적용
- DP(Dynamic Programming) EWMA 캐시로 재스캔 시간 단축
- 종합 스코어 = `상승확률 × 예상상승폭 × 모멘텀 × 품질지수`
- 섹터 필터, 실시간 진행 바, 상위 10개 카드 표시

### ⭐ 관심종목 관리
- 종목 추가/삭제, 메모 기능
- 90일 미니 차트 + 6개 지표 투표 기반 신호
- 상세 패널: 캔들+RSI 차트, Impact 뉴스 목록

### 📰 뉴스 임팩트 분석
- 3중 폴백 뉴스 수집 (yfinance → Yahoo RSS → Google RSS)
- 5가지 뉴스 유형 분류 (Surprise / Structural / Transient / Contagion / General)
- 매크로 Knowledge Graph: 10개 테마 × 11개 섹터 노출도 자동 계산
- Risk-On / Risk-Off 시장 국면 감지 (M = 0.8 ~ 2.5)

---

## 3. 시스템 아키텍처

```
┌─────────────────────────────────────────────────────────┐
│                    app.py  (진입점)                      │
│         config.py 하드웨어 감지 → 환경변수 설정          │
└──────────────────────┬──────────────────────────────────┘
                       │
              dashboard.py (Streamlit UI)
                       │
        ┌──────────────┼───────────────┐
        │              │               │
   fetcher.py    technical.py    sentiment.py
   (yfinance)   (지표 30개)    (뉴스 + Impact)
        │              │               │
        └──────────────┴───────────────┘
                       │
                 predictor.py
          ┌────────────┴────────────┐
          │                         │
   RegimeDetector            EnsemblePredictor
   (국면 감지)            ┌────────┴────────┐
                    XGBoostPredictor   LSTMPredictor
                    (베이스라인)       (복잡 국면)
                       │
                 scanner.py          watchlist.py
              (S&P500 배치)        (관심종목 관리)
                       │
                 charts.py
              (Plotly 시각화)
```

### 파일 구조

```
stock_analyzer/
├── app.py           # Streamlit 진입점, 다크 테마 CSS
├── config.py        # M4 Pro 하드웨어 감지 + 최적화 설정 허브
├── dashboard.py     # 메인 UI (7탭: 차트·기술·재무·뉴스·AI·스캐너·관심종목)
├── fetcher.py       # yfinance 데이터 수집 (tz-aware 정규화)
├── technical.py     # 기술적 지표 30개 (float32 최적화)
├── sentiment.py     # 뉴스 수집 + Impact Score 프레임워크
├── predictor.py     # 앙상블 예측 엔진 (XGBoost + LSTM)
├── scanner.py       # S&P 500 배치 스캐너 (DP 캐시)
├── watchlist.py     # 관심종목 관리
├── charts.py        # Plotly 다크 테마 차트
├── requirements.txt
├── scan_cache.json  # 스캐너 DP 캐시 (자동 생성)
└── watchlist.json   # 관심종목 저장 (자동 생성)
```

---

## 4. 설치 방법

### 요구사항

- macOS Apple Silicon (M1 / M2 / M3 / M4)
- Python 3.11+
- Homebrew

### 기본 설치

```bash
# 1. 저장소 클론
git clone <repo-url>
cd stock_analyzer

# 2. 가상환경 생성
python3.11 -m venv venv
source venv/bin/activate

# 3. 기본 패키지 설치
pip install -r requirements.txt

# 4. XGBoost OpenMP 의존성 (필수)
brew install libomp
```

### LSTM 모델 추가 설치 (선택, 권장)

```bash
# Apple Silicon 전용 TensorFlow (택 1)
pip install tensorflow-macos tensorflow-metal

# 또는 PyTorch (MPS GPU 가속)
pip install torch torchvision
```

### FinBERT 감성 분석 추가 설치 (선택)

```bash
# 모델 약 500MB 다운로드
pip install transformers torch tokenizers safetensors
```

---

## 5. 실행

```bash
source venv/bin/activate
streamlit run app.py
```

앱 시작 시 터미널에 하드웨어 정보가 출력됩니다:

```
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
  🖥  칩:    Apple M4 Pro
  🧮  코어:  P12+E4 (16개 논리)
  💾  메모리: 24.0 GB
  🎮  MPS:  ✅ 활성
  ⚙️   XGB:  tree_method=hist, nthread=12
  🔀  스캐너 워커: 2개
  📊  최대 학습 샘플: 4,000개
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
```

### 처음 스캔 전 초기화

```bash
# 이전 캐시 완전 삭제 (처음부터 전체 재분석)
rm -f scan_cache.json
```

---

## 6. 모듈 상세

### fetcher.py — 데이터 수집

| 함수 | 설명 |
|------|------|
| `fetch_stock_data(ticker, period_days)` | OHLCV + 재무정보 수집, tz-aware 인덱스 정규화 |
| `fetch_earnings_history(ticker)` | 분기별 실적 (quarterly_income_stmt) |
| `normalize_ticker(ticker)` | 한국/미국 종목코드 정규화 |

- yfinance 0.2.54+ 스키마 호환
- OHLCV 즉시 float32 변환 (메모리 50% 절감)
- tz-aware → UTC → tz-naive 정규화 (Plotly 호환)

### technical.py — 기술적 지표

```
이동평균:   MA5, MA10, MA20, MA50, MA200, EMA12, EMA26
모멘텀:     RSI14, RSI7, MACD, MACD_Signal, MACD_Hist, MACD_Cross
변동성:     볼린저밴드 (Upper/Middle/Lower/Width/Position), ATR14, ATR_Pct
가격포지션: Stochastic(K/D), Williams %R
거래량:     OBV, OBV_Trend, Volume_Ratio
피처:       Return_1d~20d, Price_vs_MA20/50, MA5_vs_MA20, MA20_vs_MA50
캔들:       Body_Size, Upper_Shadow, Lower_Shadow, Is_Bullish
ML타겟:     Target (내일 상승여부), Target_Return
```

**M4 최적화**: 모든 컬럼을 `dict`로 계산 후 `df.assign(**new_cols)` 1회 호출 → DataFrame 단편화(fragmentation) 방지

### sentiment.py — 뉴스 임팩트 프레임워크

뉴스 수집 3중 폴백:
1. yfinance news (v0/v1 스키마 자동 감지)
2. Yahoo Finance RSS
3. Google News RSS

감성 분석:
- **VADER** (기본): 금융 특화 사전 150개 단어 추가
- **FinBERT** (선택): `ProsusAI/finbert` 모델

---

## 7. 앙상블 예측 엔진

### 구조

```
EnsemblePredictor
├── RegimeDetector      → 시장 국면 복잡도 (0~1) 계산
├── XGBoostPredictor    → 항상 실행 (베이스라인)
└── LSTMPredictor       → 복잡 국면 조건부 실행
```

### 학습 흐름

```
[1/4] XGBoost 학습
      Walk-forward CV (n_splits = 3~5)
      tree_method='hist', nthread=P코어수

[2/4] RegimeDetector 국면 감지
      변동성 군집      (가중 30%)
      추세 방향 혼조   (가중 25%)
      RSI 극단 반복    (가중 15%)
      MACD 교차 빈도   (가중 15%)
      모멘텀 전환      (가중 10%)
      볼린저 이탈      (가중  5%)
      → complexity 0~1 / 국면: simple / moderate / complex

[3/4] LSTM 학습 (복잡도 ≥ 0.30 시)
      PyTorch MPS (단독 분석) 또는 CPU (스캐너)
      LayerNorm + AdamW + CosineAnnealingLR
      조기종료: patience=15

[4/4] 앙상블 가중치 결합
      w_lstm = interp(complexity, [0.30, 1.0], [0.20, 0.55])
      w_lstm × = (lstm_val_acc / xgb_cv_acc).clip(0.7, 1.3)
      p_final = w_xgb × p_xgb + w_lstm × p_lstm
      (두 모델 불일치 시 → p_final을 0.5 방향으로 40% 보정)
```

### 신호 기준

| 조건 | 신호 |
|------|------|
| 상승확률 > 58% | 📈 BUY |
| 하락확률 > 58% | 📉 SELL |
| 그 외 | ⏸ HOLD |

### 데이터 크기별 자동 파라미터 조정

| 샘플 수 | XGB n_estimators | CV splits | LSTM epochs |
|--------|-----------------|-----------|-------------|
| < 300  | 150 | 3 | 60 |
| < 800  | 200 | 4 | 80 |
| < 2000 | 300 | 5 | 100 |
| < 4000 | 300 | 5 | 120 |
| ≥ 4000 | 300 | 5 | 100 (최근 4000개만) |

### 피처 목록 (30개)

```python
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
```

---

## 8. 뉴스 임팩트 프레임워크

Wall Street 트레이딩 데스크 방법론을 코드로 구현한 뉴스 정량화 시스템입니다.

### Impact Score 공식

$$I = (S \times M) \times \sqrt{V} \times P$$

| 변수 | 의미 | 범위 |
|------|------|------|
| **S** (Surprise) | VADER/FinBERT 감성 + 서프라이즈 보정 | -1.0 ~ 1.0 |
| **M** (Market Regime) | 시장 국면 증폭 계수 | 0.8 ~ 2.5 |
| **V** (Volatility) | 종목 베타 (변동성 대리 지표) | 0.1 ~ ∞ |
| **P** (Persistence) | 정보 유효 기간 | 0.05 ~ 1.0 |

### 시장 국면 M 값

| 국면 | M | 적용 |
|------|---|------|
| 강세장 신호 | 0.8 | 호재 증폭 |
| 기본 | 1.2 | 중립 |
| 위기 신호 1개 | 1.8 | 악재 1.8배 |
| 극도 위기 2개+ | 2.5 | 악재 2.5배 |

> 하락장에서는 호재보다 악재에 3배 더 민감하게 반응한다는 실전 원칙 구현

### 3단계 필터링

| 필터 | 설명 | 지속성(P) |
|------|------|-----------|
| 🎯 Surprise | EPS 어닝 서프라이즈, 가이던스 상향/하향 | 0.60 |
| 🏗️ Structural | 규제·금리·공급망·M&A·파산 | 0.90 |
| 💨 Transient | 루머·일시적 사건·소문 | 0.15 |
| 🌊 Contagion | 섹터 전체 확산, 공급망 파급 | 0.55 |
| 📰 General | 일반 뉴스 | 0.30 |

### 매크로 Knowledge Graph (10 테마 × 11 섹터)

```
금리인상    → Technology(-0.80), Real Estate(-0.75), Financials(+0.60)
금리인하    → Technology(+0.80), Real Estate(+0.75), Financials(-0.40)
지정학위기  → Energy(+0.90), Industrials(+0.70), Technology(-0.60)
인플레이션  → Energy(+0.80), Materials(+0.70), Consumer Disc(-0.65)
경기침체    → Consumer Disc(-0.80), Industrials(-0.70), Staples(+0.50)
AI붐       → Technology(+0.95), Utilities(+0.50), Materials(+0.35)
무역전쟁    → Technology(-0.70), Industrials(-0.60), Staples(-0.30)
에너지전환  → Energy(-0.50), Utilities(+0.65), Materials(+0.60)
달러강세    → Technology(-0.45), Energy(-0.50), Financials(+0.30)
유동성긴축  → Technology(-0.75), Real Estate(-0.70), Financials(+0.20)
```

### 가중치 계산

```
weight_i = |impact_score_i| × exp(-hours_ago_i / 36)
avg_sentiment = Σ(direction_i × weight_i) / Σ(weight_i)
```

- 반감기 36시간 (기존 48h → 더 빠른 정보 소멸 반영)
- min_relevance=0.08 미만 기사는 노이즈로 제외

---

## 9. S&P 500 스캐너

### 동작 방식

```
ThreadPoolExecutor (워커 2개)
  ├─ Worker 1: 종목 A → XGBoost(nthread=1) + LSTM(CPU)
  └─ Worker 2: 종목 B → XGBoost(nthread=1) + LSTM(CPU)
      ↓
  OMP 스레드 총합: 2 × 1 = 2개 (경합 없음)
  MPS 접근: 없음 (GPU 충돌 구조적 불가능)
```

### DP 블렌딩 (EWMA)

```python
# 재스캔 시 이전 결과와 가중 평균
composite_new = 0.3 × new + 0.7 × old
```

새 정보(30%)와 누적 분석(70%)을 결합해 단기 노이즈를 줄입니다.

### 종합 스코어 공식

```
estimated_upside = up_prob × ATR√63 × 0.4
                 + RSI반등여력 × ATR√63 × 0.3
                 + min(52주여력, 30) × 0.3

composite = up_prob × estimated_upside × momentum_factor × quality_factor
```

### 소요 시간

| 상황 | 소요 시간 |
|------|----------|
| 첫 전체 스캔 500종목 (앙상블) | 약 2~4시간 |
| DP 캐시 재사용 시 | 수 분 |
| 가격 변동 종목만 재분석 | 변동 수 × ~60초 |

### 캐시 초기화

```bash
rm scan_cache.json  # 처음부터 재분석
```

---

## 10. 관심종목 관리

### 데이터 저장

`watchlist.json`에 영구 저장됩니다. 앱 재시작 후에도 유지됩니다.

```json
{
  "tickers": ["AAPL", "NVDA", "TSLA"],
  "memos": {"AAPL": "분할 매수 예정"},
  "added_at": {"AAPL": "2026-03-22T09:00:00"}
}
```

### 신호 계산 (6개 지표 투표)

개별 분석과 동일한 기준으로 일관성을 유지합니다:

| 지표 | 매수 조건 | 매도 조건 | 배점 |
|------|----------|----------|------|
| RSI | < 30 | > 70 | 2표 |
| RSI | < 40 | > 60 | 1표 |
| MA 정배열 | p>MA20>MA50 | p<MA20<MA50 | 2표 |
| MA | p>MA20 | p<MA20 | 1표 |
| 볼린저 | BB_pos < 5% | BB_pos > 95% | 1표 |
| MACD | EMA12>EMA26 | EMA12<EMA26 | 1표 |
| 스토캐스틱 | K < 20 | K > 80 | 1표 |

매수 2표 이상 → BUY, 매도 2표 이상 → SELL, 나머지 → HOLD

---

## 11. M4 Pro 최적화 상세

### 하드웨어 자동 감지 (config.py)

```python
# P코어 / E코어 분리 감지
sysctl hw.perflevel0.logicalcpu  # P코어
sysctl hw.perflevel1.logicalcpu  # E코어

# 메모리 용량
sysctl hw.memsize  # 24GB

# MPS 가용성
torch.backends.mps.is_available()
```

### 최적화 항목

| 항목 | 설정 | 이유 |
|------|------|------|
| XGBoost tree_method | `hist` | M4 CPU 히스토그램 최적화 |
| XGBoost nthread | P코어 수 (12) | E코어 제외 (연산 전용) |
| XGBoost nthread (스캐너) | 1 | OMP 멀티스레드 경합 방지 |
| LSTM device | MPS (단독 분석) | Metal GPU 가속 |
| LSTM device (스캐너) | CPU | MPS 동시 접근 크래시 방지 |
| DataFrame dtype | float32 | NEON SIMD 벡터화, 메모리 50% 절감 |
| Pandas CoW | True | 불필요한 복사 방지 |
| PYTORCH_MPS_HIGH_WATERMARK_RATIO | 0.0 | Unified Memory 동적 할당 |
| OMP_NUM_THREADS | P코어 수 | Apple Accelerate 프레임워크 활용 |

### 메모리 사용 계획 (24GB)

```
OS + 브라우저          ~4 GB (17%)
Streamlit 서버         ~1 GB ( 4%)
yfinance 캐시          ~1 GB ( 4%)
DataFrame (스캔 전체)  ~3 GB (13%)
XGBoost 모델          ~1 GB ( 4%)
PyTorch LSTM (MPS)    ~1 GB ( 4%)
여유 (GPU 공유)       ~13 GB (54%)
```

---

## 12. 터미널 로그 읽는 법

### 개별 종목 분석

```
[14:23:01] ▶▶▶  [AAPL] 분석 시작  |  기간=1825일  |  모델=XGBoost
[14:23:03]   [1/5] ✅ 데이터 수집 완료  1,825행 (1.8s)
[14:23:03]   [2/5] ✅ 지표 계산 완료  컬럼수=52개 (0.3s)
[14:23:05]   [3/5] ✅ 감성 분석 완료  뉴스 12건  점수=0.142 (2.1s)
[14:23:05]   =====================================================
[14:23:05]   앙상블 분석 시작  |  데이터: 1,825일
[14:23:05]   [1/4] XGBoost 베이스라인 학습...
[14:23:07]   │ Fold 1/5 [████░░░░░░░░░░░]  acc=0.534  (2.1s 경과)
[14:23:16]   └ XGBoost 완료  (10.8s)
[14:23:16]   [2/4] ✅ 국면: 🟡 moderate (복잡도=0.412)
[14:23:25]   [3/4] ✅ LSTM 완료  val_acc=0.561  (8.3s)
[14:23:25]   모델: Ensemble (XGB 65% + LSTM 35%)
[14:23:25]   [5/5] ✅ 예측 완료  신호=BUY  상승확률=63.2%
[14:23:25] ▶▶▶  [AAPL] 전체 분석 완료  총 소요=24.1s
```

### 스캐너

```
[14:30:00] 🔭  스캔 시작  |  종목=200개  |  워커=2개  |  기간=730일
[14:30:00]   ⚡ 캐시 재사용: 150개  |  🔄 신규 분석: 50개
[14:30:00]   ⏱  신규 분석 예상 시간: 약 25~50분
[14:31:33]   ✅ AAPL   Ensemble (XGB 65% + LSTM 35%)  47.3s
[14:31:44]   ✅ MSFT   XGBoost (단독)  38.1s
[14:32:01]   [████████░░░░░░░░░░░░░░░░░] 10/200  ⚡150 🔄9 ❌1  ETA 42분 30초
```

---

## 13. 주의사항 및 면책

> ⚠️ 본 시스템은 **투자 참고용**입니다. AI 예측 결과는 미래 수익을 보장하지 않으며, 모든 투자 결정과 그에 따른 책임은 투자자 본인에게 있습니다.

### 모델 한계

- 학습 데이터: 과거 가격 데이터 기반 → 블랙스완(예측 불가 사건) 대응 불가
- 예측 정확도: Walk-forward CV 기준 평균 53~58% (랜덤 50%보다 높으나 완벽하지 않음)
- 데이터 지연: yfinance는 실시간이 아닌 지연 데이터
- 뉴스 한계: RSS 기반으로 실시간 Bloomberg/Reuters 터미널 수준이 아님

### 알려진 제약

| 항목 | 제약 |
|------|------|
| yfinance API | Rate limit → 스캐너 워커 2개로 제한 |
| LSTM MPS | 단독 분석에서만 MPS 사용, 스캐너는 CPU |
| 한국 종목 | `.KS`, `.KQ` 코드 지원하나 뉴스는 영문 기사만 분석 |
| FinBERT | 별도 설치 필요, 500MB 모델 다운로드 |

---

## 라이선스

MIT License

---

*Built for macOS Apple Silicon with ❤️*