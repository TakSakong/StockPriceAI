"""
Streamlit 메인 대시보드 UI
모든 모듈을 로컬(같은 폴더)에서 직접 import
"""

import sys
import time
import logging
import streamlit as st
import pandas as pd
import numpy as np
import warnings
from datetime import datetime
from typing import Dict, List, Optional, Tuple
warnings.filterwarnings('ignore')

# dashboard용 터미널 로거 (predictor의 logger와 공유)
def _get_logger():
    logger = logging.getLogger("stock_analyzer")
    if not logger.handlers:
        handler = logging.StreamHandler(sys.stdout)
        class _CF(logging.Formatter):
            COLORS = {logging.DEBUG:"[90m", logging.INFO:"[96m",
                      logging.WARNING:"[93m", logging.ERROR:"[91m"}
            R = "[0m"; B = "[1m"
            def format(self, r):
                c = self.COLORS.get(r.levelno, "")
                ts = datetime.now().strftime("%H:%M:%S")
                return f"{self.B}[{ts}]{self.R} {c}{r.getMessage()}{self.R}"
        handler.setFormatter(_CF())
        logger.addHandler(handler)
        logger.setLevel(logging.DEBUG)
        logger.propagate = False
    return logger

log = _get_logger()

# ── 로컬 모듈 직접 import ─────────────────────────────────
from fetcher import (
    fetch_stock_data, fetch_earnings_history,
    normalize_ticker
)
from technical import (
    add_all_indicators, get_current_signals, get_support_resistance
)
from sentiment import analyze_news_sentiment, add_sentiment_to_features
from predictor import XGBoostPredictor, LSTMPredictor, EnsemblePredictor
from charts import (
    create_main_chart, create_macd_chart,
    create_feature_importance_chart, create_sentiment_gauge
)
from scanner import (
    SP500_TICKERS, run_sp500_scan, get_top10, format_market_cap
)
from config import MEMORY as MEM_CFG, DATA as DATA_CFG, memory_status
from watchlist import (
    load_watchlist, add_ticker, remove_ticker, update_memo,
    get_memo, get_added_at, is_in_watchlist,
    fetch_quick_snapshot, fetch_news_summary, refresh_all_snapshots,
    fmt_price, fmt_mktcap, fmt_change, change_color,
)


# ─────────────────────────────────────────────────────────────
# 세션 상태 초기화
# ─────────────────────────────────────────────────────────────

def init_session():
    defaults = {
        'analysis_done': False,
        'df': None,
        'info': None,
        'news_df': None,
        'sentiment': None,
        'predictor': None,
        'prediction': None,
        'ticker': '',
        'model_metrics': {},
        'signals': {},
        # 관심종목
        'wl_snapshots': {},        # {ticker: snapshot_dict}
        'wl_selected':  None,      # 상세 보기 중인 ticker
        'wl_detail_data': {},      # {ticker: {news, news_summary, df, info}}
        'wl_refreshing': False,
        # 스캐너
        'scan_running': False,
        'scan_results': None,
        'scan_top10': None,
        'scan_progress': 0,
        'scan_total': 0,
        'scan_current_ticker': '',
        'scan_done': False,
        'scan_stop': {},
    }
    for k, v in defaults.items():
        if k not in st.session_state:
            st.session_state[k] = v


# ─────────────────────────────────────────────────────────────
# 헬퍼 함수
# ─────────────────────────────────────────────────────────────

def format_number(val, prefix='', suffix='', decimals=2):
    if val is None or (isinstance(val, float) and np.isnan(val)):
        return 'N/A'
    if abs(val) >= 1_000_000_000_000:
        return f"{prefix}{val/1_000_000_000_000:.1f}T{suffix}"
    if abs(val) >= 1_000_000_000:
        return f"{prefix}{val/1_000_000_000:.1f}B{suffix}"
    if abs(val) >= 1_000_000:
        return f"{prefix}{val/1_000_000:.1f}M{suffix}"
    return f"{prefix}{val:,.{decimals}f}{suffix}"


def get_signal_html(signal: str) -> str:
    classes = {'BUY': 'signal-buy', 'SELL': 'signal-sell', 'HOLD': 'signal-hold'}
    emojis  = {'BUY': '📈 매수',    'SELL': '📉 매도',    'HOLD': '⏸️ 보유'}
    cls   = classes.get(signal, 'signal-hold')
    label = emojis.get(signal, signal)
    return f'<span class="{cls}">{label}</span>'


# ─────────────────────────────────────────────────────────────
# 캐시된 데이터 수집
# ─────────────────────────────────────────────────────────────

@st.cache_data(ttl=900)   # 15분
def cached_fetch_data(ticker: str, period_days: int = 500):
    return fetch_stock_data(ticker, period_days=period_days)


@st.cache_data(ttl=1800)  # 30분
def cached_fetch_news(ticker: str, use_finbert: bool, company_name: str = '', sector: str = ''):
    return analyze_news_sentiment(ticker, company_name=company_name, sector=sector, use_finbert=use_finbert)


# ─────────────────────────────────────────────────────────────
# 분석 파이프라인
# ─────────────────────────────────────────────────────────────

def run_analysis(ticker: str, model_type: str, use_finbert: bool, period: int):
    t_start = time.time()
    log.info(f"")
    log.info(f"▶▶▶  [{ticker}] 분석 시작  |  기간={period}일  |  모델={model_type}")

    with st.status("🔄 분석 파이프라인 실행 중...", expanded=True) as status:

        # Step 1 · 주가 데이터 수집
        log.info(f"  [1/5] 주가 데이터 수집 중... ({ticker}, {period}일)")
        st.write("📡 주가 데이터 수집 중...")
        t1 = time.time()
        try:
            df, info = cached_fetch_data(ticker, period_days=period)
        except ValueError as e:
            log.error(f"  [1/5] ❌ 데이터 수집 실패: {e}")
            st.error(f"❌ {str(e)}")
            return False

        if df is None:
            log.error(f"  [1/5] ❌ {ticker} 데이터 없음")
            st.error(f"❌ {ticker} 데이터를 찾을 수 없습니다. 종목 코드를 확인해주세요.")
            return False
        log.info(f"  [1/5] ✅ 데이터 수집 완료  {len(df):,}행 ({time.time()-t1:.1f}s)")

        # Step 2 · 기술적 지표 계산
        log.info(f"  [2/5] 기술적 지표 계산 중...")
        st.write("📊 기술적 지표 계산 중...")
        t2 = time.time()
        df = add_all_indicators(df)
        log.info(f"  [2/5] ✅ 지표 계산 완료  컬럼수={len(df.columns)}개 ({time.time()-t2:.1f}s)")

        # Step 3 · 뉴스 감성 분석
        log.info(f"  [3/5] 뉴스 감성 분석 중...")
        st.write("📰 뉴스 감성 분석 중...")
        t3 = time.time()
        company_name = info.get('longName') or info.get('shortName') or '' if info else ''
        sector_name  = info.get('sector', '') if info else ''
        news_df, sentiment = cached_fetch_news(ticker, use_finbert, company_name, sector_name)
        df = add_sentiment_to_features(df, sentiment.get('avg_sentiment', 0.0))
        n_news = sentiment.get('news_count', 0)
        log.info(f"  [3/5] ✅ 감성 분석 완료  뉴스 {n_news}건  점수={sentiment.get('avg_sentiment',0):.3f} ({time.time()-t3:.1f}s)")

        # Step 4 · ML 앙상블 모델 학습
        force_lstm = (model_type == 'LSTM')
        n_rows = len(df)
        if n_rows > 3000:
            est_sec = n_rows // 100
            log.info(f"  [4/5] 앙상블 학습 시작  데이터={n_rows:,}일  예상 {est_sec}~{est_sec*2}초...")
            st.write(f"🤖 앙상블 모델 학습 중 — 데이터 {n_rows:,}일 (예상 {est_sec}~{est_sec*2}초)...")
        else:
            log.info(f"  [4/5] 앙상블 학습 시작  데이터={n_rows:,}일  {'LSTM강제' if force_lstm else '국면자동감지'}")
            st.write(f"🤖 앙상블 모델 학습 중 {'(LSTM 강제 활성화)' if force_lstm else '(국면 자동 감지)'}...")
        t4 = time.time()
        predictor = EnsemblePredictor()
        metrics   = predictor.train(df, include_sentiment=True, force_lstm=force_lstm)

        if 'error' in metrics:
            log.warning(f"  [4/5] ⚠  앙상블 실패 → XGBoost 단독 재시도")
            st.warning(f"⚠️ {metrics['error']} → XGBoost 단독으로 전환합니다.")
            predictor = EnsemblePredictor()
            metrics   = predictor.train(df, include_sentiment=False, force_lstm=False)
        log.info(f"  [4/5] ✅ 앙상블 완료  모델={metrics.get('model_type','?')} ({time.time()-t4:.1f}s)")

        # Step 5 · 예측
        log.info(f"  [5/5] 방향성 예측 중...")
        st.write("🔮 내일 방향성 예측 중...")
        t5 = time.time()
        prediction = predictor.predict(df)
        signals    = get_current_signals(df)
        sig = prediction.get('signal','?')
        up  = prediction.get('up_probability', 0)
        log.info(f"  [5/5] ✅ 예측 완료  신호={sig}  상승확률={up:.1%} ({time.time()-t5:.1f}s)")
        log.info(f"▶▶▶  [{ticker}] 전체 분석 완료  총 소요={time.time()-t_start:.1f}s")
        log.info(f"")

        st.session_state.update({
            'analysis_done': True,
            'df': df,
            'info': info or {},
            'news_df': news_df,
            'sentiment': sentiment,
            'predictor': predictor,
            'prediction': prediction,
            'ticker': ticker,
            'model_metrics': metrics,
            'signals': signals,
        })

        status.update(label="✅ 분석 완료!", state="complete", expanded=False)

    return True


# ─────────────────────────────────────────────────────────────
# UI 컴포넌트
# ─────────────────────────────────────────────────────────────

def render_sidebar():
    with st.sidebar:
        st.markdown("## 📈 AI Stock Analyzer")
        st.markdown("---")

        st.markdown("### 🔍 종목 검색")
        # 스캐너 "검색창에 입력" 버튼으로 채워진 값 처리
        _prefill = st.session_state.pop('_prefill_ticker', '')
        ticker_input = st.text_input(
            "종목 코드 (Ticker)",
            value=_prefill,
            placeholder="AAPL, TSLA, 005930...",
            help="미국: AAPL, TSLA  |  한국: 005930 (삼성전자)"
        ).strip().upper()

        st.markdown("**빠른 선택:**")
        examples = {
            '🍎 Apple': 'AAPL', '⚡ Tesla': 'TSLA', '🎮 NVIDIA': 'NVDA',
            '📱 Microsoft': 'MSFT', '🇰🇷 삼성': '005930', '🇰🇷 SK하이닉스': '000660'
        }
        cols = st.columns(2)
        selected = None
        for i, (label, t) in enumerate(examples.items()):
            if cols[i % 2].button(label, key=f"ex_{t}", use_container_width=True):
                selected = t

        final_ticker = selected or ticker_input

        st.markdown("---")
        st.markdown("### ⚙️ 분석 설정")

        model_type  = st.selectbox("ML 모델", ["XGBoost", "LSTM"],
                                   help="XGBoost: 빠름 | LSTM: TensorFlow 필요")
        use_finbert = st.toggle("FinBERT 사용 (금융 특화 NLP)", value=False,
                                help="미설치 시 VADER로 자동 전환")
        period_unit = st.selectbox("분석 기간", [
            "1년 (252 거래일)", "2년", "3년", "5년", "10년", "전체 (max)"
        ], index=0, help="길수록 ML 학습 샘플이 늘어나 예측 안정성이 높아집니다")
        _unit_map = {
            "1년 (252 거래일)": 365,
            "2년": 730, "3년": 1095, "5년": 1825,
            "10년": 3650, "전체 (max)": 0
        }
        period = _unit_map[period_unit]

        st.markdown("---")

        # ── 관심종목 빠른 추가 ──────────────────────────────
        wl_col1, wl_col2 = st.columns([3, 1])
        wl_ticker_input = wl_col1.text_input(
            "관심종목 추가", placeholder="AAPL...",
            key="wl_add_input", label_visibility="collapsed"
        ).strip().upper()
        if wl_col2.button("★ 추가", key="wl_add_btn", use_container_width=True):
            if wl_ticker_input:
                t_norm = normalize_ticker(wl_ticker_input)
                if add_ticker(t_norm):
                    st.toast(f"⭐ {t_norm} 관심종목에 추가됐습니다!", icon="⭐")
                    st.session_state['wl_snapshots'].pop(t_norm, None)
                else:
                    st.toast(f"{t_norm}은 이미 관심종목입니다", icon="ℹ️")

        # 현재 분석 중인 종목 관심종목 추가/제거
        cur_ticker = st.session_state.get('ticker', '')
        if cur_ticker:
            if is_in_watchlist(cur_ticker):
                if st.button(f"★ {cur_ticker} 관심종목 해제", key="wl_remove_cur",
                             use_container_width=True):
                    remove_ticker(cur_ticker)
                    st.toast(f"{cur_ticker} 관심종목에서 제거됐습니다")
                    st.rerun()
            else:
                if st.button(f"☆ {cur_ticker} 관심종목 추가", key="wl_add_cur",
                             use_container_width=True, type="primary"):
                    add_ticker(cur_ticker)
                    st.toast(f"⭐ {cur_ticker} 관심종목에 추가됐습니다!", icon="⭐")
                    st.rerun()

        st.markdown("---")

        analyze_btn = st.button(
            "🚀 AI 분석 시작",
            use_container_width=True,
            type="primary",
            disabled=not bool(final_ticker)
        )

        # 스캐너에서 클릭해서 온 경우 자동 분석
        goto = st.session_state.pop('goto_ticker', None)
        if goto and not st.session_state.get('analysis_done'):
            st.session_state['_auto_analyze'] = goto

        if analyze_btn and final_ticker:
            norm = normalize_ticker(final_ticker)
            st.session_state['_pending_ticker']     = norm
            st.session_state['_pending_model']      = model_type
            st.session_state['_pending_finbert']    = use_finbert
            st.session_state['_pending_period']     = period
            run_analysis(norm, model_type, use_finbert, period)

        if st.session_state.analysis_done:
            st.markdown("---")
            st.markdown("### 📊 모델 정보")
            m = st.session_state.model_metrics
            if m and 'error' not in m:
                st.metric("모델", m.get('model_type', 'N/A'))
                if 'cv_accuracy_mean' in m:
                    st.metric("CV 정확도",
                              f"{m['cv_accuracy_mean']:.1%}",
                              f"±{m.get('cv_accuracy_std', 0):.1%}")
                elif 'train_accuracy' in m:
                    st.metric("학습 정확도", f"{m['train_accuracy']:.1%}")
                st.metric("학습 샘플", f"{m.get('n_samples', 0):,}일")
                st.metric("피처 수",   f"{m.get('n_features', 0)}개")

        st.markdown("---")
        # 메모리 상태 표시
        try:
            ms = memory_status()
            used_pct = ms.get("percent", 0)
            color = "#10b981" if used_pct < 60 else "#f59e0b" if used_pct < 80 else "#ef4444"
            st.markdown(
                f"<div style='text-align:center;color:#475569;font-size:11px;margin-bottom:4px'>"
                f"💾 메모리: <span style='color:{color}'>{ms.get('used_gb','?')}GB "
                f"/ {ms.get('total_gb','?')}GB ({used_pct:.0f}%)</span></div>",
                unsafe_allow_html=True
            )
        except Exception:
            pass
        st.markdown(
            "<div style='text-align:center;color:#475569;font-size:12px'>"
            "⚠️ 본 서비스는 투자 참고용이며<br>투자 결정의 책임은 투자자 본인에게 있습니다."
            "</div>",
            unsafe_allow_html=True
        )


def render_header():
    info   = st.session_state.info
    ticker = st.session_state.ticker

    name        = info.get('longName') or info.get('shortName') or ticker
    sector      = info.get('sector', '')
    industry    = info.get('industry', '')
    currency    = info.get('currency', 'USD')
    cur_price   = info.get('regularMarketPrice', 0) or 0
    chg_pct     = info.get('regularMarketChangePercent', 0) or 0

    st.markdown(f"""
    <div class="main-header">
        <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:16px">
            <div>
                <div style="color:#94a3b8;font-size:13px;margin-bottom:4px">
                    {sector}{'> ' + industry if industry else ''}
                </div>
                <h1 style="margin:0;color:#e2e8f0;font-size:28px;font-weight:700">{name}</h1>
                <div style="color:#64748b;font-size:14px;margin-top:4px">{ticker}</div>
            </div>
            <div style="text-align:right">
                <div style="color:#e2e8f0;font-size:32px;font-weight:700;font-family:'JetBrains Mono',monospace">
                    {currency} {cur_price:,.2f}
                </div>
                <div style="color:{'#10b981' if chg_pct >= 0 else '#ef4444'};font-size:16px;font-weight:600">
                    {'▲' if chg_pct >= 0 else '▼'} {abs(chg_pct):.2f}%
                </div>
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)


def render_prediction_card():
    pred = st.session_state.prediction
    if not pred or 'error' in pred:
        return

    signal   = pred.get('signal', 'HOLD')
    up_prob  = pred.get('up_probability', 0.5)
    down_prob= pred.get('down_probability', 0.5)
    model    = pred.get('model', 'AI')

    c1, c2, c3 = st.columns(3)
    with c1:
        st.markdown("#### 🔮 AI 예측 신호")
        st.markdown(get_signal_html(signal), unsafe_allow_html=True)
        st.caption(f"모델: {model}")
    with c2:
        st.markdown("#### 📈 상승 확률")
        st.progress(up_prob)
        st.markdown(f"<h3 style='color:#10b981;margin:0'>{up_prob:.1%}</h3>", unsafe_allow_html=True)
    with c3:
        st.markdown("#### 📉 하락 확률")
        st.progress(down_prob)
        st.markdown(f"<h3 style='color:#ef4444;margin:0'>{down_prob:.1%}</h3>", unsafe_allow_html=True)


def render_financial_metrics():
    info = st.session_state.info
    if not info:
        return

    st.markdown("### 📋 주요 재무 지표")

    def pct(key):
        v = info.get(key)
        return v * 100 if v is not None else None

    metrics = [
        ("PER (TTM)",  info.get('trailingPE'),   "x",  "주가수익비율"),
        ("PBR",        info.get('priceToBook'),   "x",  "주가순자산비율"),
        ("ROE",        pct('returnOnEquity'),      "%",  "자기자본이익률"),
        ("영업이익률", pct('operatingMargins'),    "%",  "Operating Margin"),
        ("부채비율",   info.get('debtToEquity'),  "x",  "D/E Ratio"),
        ("배당수익률", pct('dividendYield'),       "%",  "Dividend Yield"),
        ("베타",       info.get('beta'),           "",   "시장 변동성 대비"),
        ("시가총액",   info.get('marketCap'),      "",   "Market Cap"),
    ]

    cols = st.columns(4)
    for i, (label, val, suffix, help_text) in enumerate(metrics):
        with cols[i % 4]:
            if val is not None and not (isinstance(val, float) and np.isnan(val)):
                if label == "시가총액":
                    display = format_number(val, prefix='$')
                elif suffix == "%":
                    display = f"{val:.2f}%"
                else:
                    display = f"{val:.2f}{suffix}"
                st.metric(label, display, help=help_text)
            else:
                st.metric(label, "N/A", help=help_text)


def render_technical_signals():
    signals = st.session_state.signals
    if not signals:
        return

    st.markdown("### 🎯 기술적 신호 요약")

    rows = []
    buy_c = sell_c = hold_c = 0
    for indicator, (sig, desc, _) in signals.items():
        emoji = {'BUY': '🟢', 'SELL': '🔴', 'HOLD': '⚪', 'WATCH': '🟡'}.get(sig, '⚪')
        rows.append({'지표': indicator, '신호': f"{emoji} {sig}", '설명': desc})
        if sig == 'BUY':   buy_c  += 1
        elif sig == 'SELL': sell_c += 1
        else:               hold_c += 1

    c1, c2, c3, c4 = st.columns(4)
    c1.metric("🟢 매수", f"{buy_c}개")
    c2.metric("🔴 매도", f"{sell_c}개")
    c3.metric("⚪ 중립", f"{hold_c}개")

    if   buy_c > sell_c + hold_c: overall = "🟢 종합 매수"
    elif sell_c > buy_c + hold_c: overall = "🔴 종합 매도"
    elif buy_c > sell_c:          overall = "🟡 약한 매수"
    elif sell_c > buy_c:          overall = "🟠 약한 매도"
    else:                          overall = "⚪ 중립"
    c4.metric("종합", overall)

    st.dataframe(
        pd.DataFrame(rows),
        hide_index=True,
        column_config={
            '지표': st.column_config.TextColumn('지표', width='small'),
            '신호': st.column_config.TextColumn('신호', width='small'),
            '설명': st.column_config.TextColumn('설명'),
        }
    )


def render_news_section():
    news_df   = st.session_state.news_df
    sentiment = st.session_state.sentiment

    st.markdown("### 📰 뉴스 감성 분석")

    if not sentiment or sentiment.get("news_count", 0) == 0:
        st.warning(
            "⚠️ 뉴스를 수집하지 못했습니다.  \n"
            "- **yfinance**, **Yahoo RSS**, **Google RSS** 세 가지 소스를 모두 시도했지만 결과가 없습니다.  \n"
            "- 네트워크 연결 상태를 확인하거나 잠시 후 다시 분석해보세요.  \n"
            "- 뉴스 없이도 기술적 분석과 ML 예측은 정상 작동합니다."
        )
        return

    # 수집 소스 배지
    sources = sentiment.get("sources", [])
    src_labels = {"yfinance": "📊 yfinance", "yahoo_rss": "📡 Yahoo RSS", "google_rss": "🔍 Google RSS"}
    src_str = "  ·  ".join(src_labels.get(s, s) for s in sources)
    st.markdown(
        f"<div style=\"background:#111827;border:1px solid #1e3a5f;border-radius:8px;"
        f"padding:8px 16px;margin-bottom:12px;font-size:12px;color:#64748b\">"
        f"수집 소스: {src_str} &nbsp;|&nbsp; "
        f"총 {sentiment.get('news_count',0)}건 &nbsp;|&nbsp; "
        f"모델: {sentiment.get('model','VADER')}</div>",
        unsafe_allow_html=True
    )

    c1, c2 = st.columns([1, 2])

    with c1:
        st.plotly_chart(
            create_sentiment_gauge(sentiment.get("avg_sentiment", 0)),
            width='stretch'
        )
        # 신호 텍스트
        signal     = sentiment.get("signal", "NEUTRAL")
        sig_colors = {"BULLISH": "#10b981", "BEARISH": "#ef4444", "NEUTRAL": "#f59e0b"}
        sig_label  = {"BULLISH": "📈 강세 (Bullish)", "BEARISH": "📉 약세 (Bearish)", "NEUTRAL": "➡️ 중립 (Neutral)"}
        st.markdown(
            f"<div style=\"text-align:center;padding:6px;color:{sig_colors.get(signal,'#f59e0b')};"
            f"font-weight:700;font-size:15px\">{sig_label.get(signal,signal)}</div>",
            unsafe_allow_html=True
        )
        s1, s2, s3 = st.columns(3)
        s1.metric("🟢 긍정", f"{sentiment.get('positive_pct', 0):.0f}%")
        s2.metric("🔴 부정", f"{sentiment.get('negative_pct', 0):.0f}%")
        s3.metric("⚪ 중립", f"{sentiment.get('neutral_pct', 0):.0f}%")

        # 가중 평균 vs 단순 평균
        st.markdown("---")
        wa1, wa2, wa3 = st.columns(3)
        wa1.metric("⚡ Impact 가중 점수",
                   f"{sentiment.get('avg_sentiment', 0):.3f}",
                   help="Impact Score(서프라이즈×국면×베타×지속성)×시간 감쇠 가중")
        wa2.metric("시간 가중 점수",
                   f"{sentiment.get('time_weighted_avg', 0):.3f}")
        wa3.metric("평균 임팩트",
                   f"{sentiment.get('impact_score_avg', 0):.3f}",
                   help="I = (S×M)×√V×P 평균값")
        st.markdown("---")
        d1, d2, d3, d4 = st.columns(4)
        d1.metric("🎯 서프라이즈",
                  f"{sentiment.get('surprise_count',0)}건",
                  help="기대치 괴리 기사 (필터 1)")
        d2.metric("🏗️ 구조적",
                  f"{sentiment.get('structural_count',0)}건",
                  help="구조적 변화 기사 (필터 2, 높은 P값)")
        d3.metric("💨 일시적",
                  f"{sentiment.get('transient_count',0)}건",
                  help="일시적 이벤트 (낮은 P값, 노이즈)")
        d4.metric("🏭 섹터 관련",
                  f"{sentiment.get('sector_news_count',0)}건")
        # 매크로 테마 표시
        macro_themes = sentiment.get("macro_themes", [])
        if macro_themes:
            theme_labels = {
                "rate_hike":"금리인상","rate_cut":"금리인하",
                "geopolitical_crisis":"지정학 위기","inflation_surge":"인플레이션",
                "recession":"경기침체","ai_boom":"AI붐","trade_war":"무역전쟁",
                "energy_transition":"에너지전환","dollar_strength":"달러강세",
                "quantitative_tightening":"유동성긴축",
            }
            theme_str = " · ".join(f"🌐 {theme_labels.get(t, t)}" for t in macro_themes[:4])
            st.markdown(
                f"<div style='background:#0d2137;border:1px solid #1e3a5f;"
                f"border-radius:6px;padding:6px 12px;font-size:12px;color:#93c5fd'>"
                f"감지된 매크로 테마: {theme_str}</div>",
                unsafe_allow_html=True
            )

    with c2:
        if news_df is not None and not news_df.empty:
            # 소스별 필터
            source_options = ["전체"] + [
                {"yfinance":"yfinance","yahoo_rss":"Yahoo RSS","google_rss":"Google RSS"}.get(s,s)
                for s in news_df["source"].unique()
            ] if "source" in news_df.columns else ["전체"]
            src_filter = st.selectbox("소스 필터", source_options, key="news_src_filter")

            display_df = news_df.copy()
            if src_filter != "전체" and "source" in display_df.columns:
                src_map_rev = {"yfinance":"yfinance","Yahoo RSS":"yahoo_rss","Google RSS":"google_rss"}
                display_df  = display_df[display_df["source"] == src_map_rev.get(src_filter, src_filter)]

            # 연관도 필터
            rel_filter = st.select_slider(
                "최소 연관도 필터",
                options=[0.0, 0.1, 0.3, 0.5, 0.7],
                value=0.0,
                format_func=lambda v: {0.0:"전체",0.1:"시장↑",0.3:"섹터↑",0.5:"직접↑",0.7:"직접(강)"}[v],
                key="rel_filter_slider"
            )
            if "relevance" in display_df.columns and rel_filter > 0:
                display_df = display_df[display_df["relevance"] >= rel_filter]

            st.markdown(f"**뉴스 헤드라인 ({len(display_df)}건):**")
            for _, row in display_df.head(12).iterrows():
                hours     = row.get("hours_ago", 0)
                time_str  = f"{hours:.0f}시간 전" if hours < 24 else f"{hours/24:.1f}일 전"
                title     = row.get("title", "")
                emoji     = row.get("emoji", "⚪")
                publisher = row.get("publisher", "")
                compound  = row.get("compound", 0)
                relevance = row.get("relevance", 0)
                rel_icon  = row.get("relevance_icon", "⬜")
                rel_tier  = row.get("relevance_tier", "")
                src_icon  = {"yfinance":"📊","yahoo_rss":"📡","google_rss":"🔍"}.get(
                    row.get("source",""), "📰")
                sent_color = "#10b981" if compound > 0.05 else "#ef4444" if compound < -0.05 else "#64748b"
                rel_color  = ("#10b981" if relevance >= 0.7 else
                              "#3b82f6" if relevance >= 0.35 else
                              "#f59e0b" if relevance >= 0.1 else "#475569")

                # 추가 필드 안전하게 추출
                impact    = row.get("impact_score", 0)
                ntype     = row.get("news_type", "general")
                type_icon = row.get("type_icon", "📰")
                persist   = row.get("persistence", 0.3)
                macro_t   = row.get("macro_theme") or ""
                imp_color = "#10b981" if impact > 0.05 else "#ef4444" if impact < -0.05 else "#64748b"
                ntype_labels = {
                    "surprise_positive":"🎯 서프라이즈↑","surprise_negative":"⚠️ 서프라이즈↓",
                    "structural":"🏗️ 구조적","transient":"💨 일시적",
                    "contagion":"🌊 전염성","macro":"🌐 매크로","general":"📰 일반",
                }
                ntype_label = ntype_labels.get(ntype, ntype)
                macro_str   = f" | 📡 {macro_t}" if macro_t else ""

                item_html = (
                    f"<div style='border-left:3px solid {imp_color};"
                    f"padding:6px 10px;margin-bottom:6px;background:#0d1421;border-radius:0 6px 6px 0'>"
                    f"<div style='color:#e2e8f0;font-size:13px;margin-bottom:3px'>"
                    f"{emoji} {title[:90]}{'...' if len(title)>90 else ''}</div>"
                    f"<div style='display:flex;gap:10px;flex-wrap:wrap;align-items:center'>"
                    f"<span style='color:#64748b;font-size:11px'>{src_icon} {publisher} · {time_str}</span>"
                    f"<span style='color:{sent_color};font-size:11px'>"
                    f"{'▲' if compound>0.05 else '▼' if compound<-0.05 else '●'} 감성 {compound:+.2f}</span>"
                    f"<span style='color:{rel_color};font-size:11px'>{rel_icon} 연관 {relevance:.2f} ({rel_tier})</span>"
                    f"<span style='color:{imp_color};font-size:11px;font-weight:600'>⚡ 임팩트 {impact:+.3f}</span>"
                    f"<span style='color:#64748b;font-size:11px'>{ntype_label}</span>"
                    f"<span style='color:#475569;font-size:10px'>P={persist:.2f}{macro_str}</span>"
                    f"</div></div>"
                )
                st.markdown(item_html, unsafe_allow_html=True)
        else:
            st.info("수집된 뉴스가 없습니다.")


def render_support_resistance():
    df = st.session_state.df
    if df is None:
        return
    sr      = get_support_resistance(df)
    current = sr['current']
    st.markdown("### 🎯 지지/저항 레벨")
    cols = st.columns(4)
    for i, (label, price) in enumerate([
        ("52주 저항선", sr['resistance_52w']),
        ("20일 저항선", sr['resistance_20d']),
        ("20일 지지선", sr['support_20d']),
        ("52주 지지선", sr['support_52w']),
    ]):
        diff_pct = (price - current) / current * 100
        cols[i].metric(label, f"{price:,.2f}", f"{diff_pct:+.2f}%",
                       delta_color="normal" if diff_pct >= 0 else "inverse")


# ─────────────────────────────────────────────────────────────
# 메인 대시보드
# ─────────────────────────────────────────────────────────────

def render_dashboard():
    init_session()
    render_sidebar()

    # 스캐너 → 분석 페이지 자동 이동 처리
    auto_ticker = st.session_state.pop('_auto_analyze', None)
    if auto_ticker:
        model_t = st.session_state.get('_pending_model', 'XGBoost')
        finbert = st.session_state.get('_pending_finbert', False)
        per_d   = st.session_state.get('_pending_period', 365)
        run_analysis(auto_ticker, model_t, finbert, per_d)
        st.rerun()

    # 스캐너는 항상 표시; 개별 분석은 종목 선택 후
    if not st.session_state.analysis_done:
        # 홈 화면 + 스캐너 탭만 표시
        st.markdown("""
        <div style='text-align:center;padding:40px 20px 20px'>
            <div style='font-size:60px;margin-bottom:16px'>📈</div>
            <h1 style='color:#e2e8f0;font-size:32px;margin-bottom:8px'>AI-Powered Stock Analyzer</h1>
            <p style='color:#94a3b8;font-size:15px;max-width:500px;margin:0 auto'>
                기술적 분석 · 기본적 분석 · 뉴스 감성 분석을 결합한 머신러닝 주가 예측 시스템
            </p>
        </div>
        """, unsafe_allow_html=True)

        # 미분석 상태에서도 관심종목·스캐너 탭 사용 가능
        wl_count = len(load_watchlist())
        wl_label = f"⭐ 관심종목{f' ({wl_count})' if wl_count else ''}"
        home_tabs = st.tabs([wl_label, "🔭 S&P 500 스캐너"])
        with home_tabs[0]:
            render_watchlist_tab()
        with home_tabs[1]:
            render_scanner_tab()
        return

    df         = st.session_state.df
    info       = st.session_state.info
    prediction = st.session_state.prediction

    render_header()

    st.markdown("### 🔮 AI 예측 결과")
    render_prediction_card()
    st.markdown("---")

    wl_count = len(load_watchlist())
    wl_label = f"⭐ 관심종목{f' ({wl_count})' if wl_count else ''}"
    tab1, tab2, tab3, tab4, tab5, tab6, tab7 = st.tabs([
        "📈 차트 분석", "🎯 기술적 신호", "💰 재무 분석",
        "📰 감성 분석", "🤖 AI 모델", "🔭 S&P 500 스캐너", wl_label
    ])

    with tab1:
        # ── 차트 표시 기간 선택 ────────────────────────────
        period_options = {
            "1개월": 21, "3개월": 63, "6개월": 126,
            "1년": 252, "2년": 504, "3년": 756,
            "5년": 1260, "전체": 0,
        }
        _total_days = len(df)

        ctrl1, ctrl2, ctrl3, ctrl4 = st.columns([2, 1, 1, 1])
        with ctrl1:
            chart_period = st.select_slider(
                "📅 차트 표시 기간",
                options=list(period_options.keys()),
                value="1년",
                key="chart_period_slider",
            )
        show_ma     = ctrl2.checkbox("이동평균선", value=True)
        show_bb     = ctrl3.checkbox("볼린저 밴드", value=True)
        show_volume = ctrl4.checkbox("거래량", value=True)

        display_days = period_options[chart_period]  # 0 = 전체

        # 데이터 범위 정보 표시
        actual_days = min(display_days, _total_days) if display_days > 0 else _total_days
        if not df.empty:
            _d_start = df.index[-actual_days] if actual_days < _total_days else df.index[0]
            _d_end   = df.index[-1]
            st.caption(
                f"📊 전체 보유 데이터: **{_total_days:,}일** "
                f"({df.index[0].strftime('%Y-%m-%d')} ~ {df.index[-1].strftime('%Y-%m-%d')})  "
                f"| 현재 표시: **{actual_days:,}일** "
                f"({_d_start.strftime('%Y-%m-%d')} ~ {_d_end.strftime('%Y-%m-%d')})"
            )

        signal = prediction.get('signal') if prediction else None
        st.plotly_chart(
            create_main_chart(
                df, st.session_state.ticker,
                show_ma, show_bb, show_volume, signal,
                display_days=display_days
            ),
            width='stretch'
        )
        st.markdown("#### MACD 분석")
        st.plotly_chart(create_macd_chart(df, display_days=display_days), width='stretch')
        render_support_resistance()

    with tab2:
        render_technical_signals()
        st.markdown("### 📊 현재 지표값")
        latest = df.iloc[-1]
        indicator_rows = {
            '지표': ['RSI (14)', 'MACD', 'MACD Signal', 'Stochastic %K', 'Williams %R',
                     'BB Position', 'BB Width', 'ATR%', 'Volume Ratio', 'MA5 vs MA20'],
            '값':   [
                f"{latest.get('RSI14',      0):.2f}",
                f"{latest.get('MACD',        0):.4f}",
                f"{latest.get('MACD_Signal', 0):.4f}",
                f"{latest.get('STOCH_K',     0):.2f}",
                f"{latest.get('WILLIAMS_R',  0):.2f}",
                f"{latest.get('BB_Position', 0):.2%}",
                f"{latest.get('BB_Width',    0):.4f}",
                f"{latest.get('ATR_Pct',     0):.2f}%",
                f"{latest.get('Volume_Ratio',1):.2f}x",
                f"{latest.get('MA5_vs_MA20', 0):.2%}",
            ]
        }
        st.dataframe(pd.DataFrame(indicator_rows), hide_index=True)

    with tab3:
        render_financial_metrics()
        st.markdown("---")
        st.markdown("### 📏 52주 가격 범위")
        high_52 = info.get('fiftyTwoWeekHigh', df['High'].tail(252).max())
        low_52  = info.get('fiftyTwoWeekLow',  df['Low'].tail(252).min())
        current = df['Close'].iloc[-1]
        if high_52 and low_52:
            pos = (current - low_52) / (high_52 - low_52) * 100
            cc1, cc2, cc3 = st.columns(3)
            cc1.metric("52주 최저", f"{low_52:,.2f}")
            cc2.metric("현재가",    f"{current:,.2f}", f"범위 내 {pos:.0f}%")
            cc3.metric("52주 최고", f"{high_52:,.2f}")
            st.progress(pos / 100)

        earnings = fetch_earnings_history(st.session_state.ticker)
        if earnings is not None and not earnings.empty:
            st.markdown("---")
            st.markdown("### 💼 분기별 실적 (최근 8분기)")
            st.dataframe(earnings)

    with tab4:
        render_news_section()

    with tab5:
        st.markdown("### 🤖 앙상블 모델 분석")
        metrics   = st.session_state.model_metrics
        predictor = st.session_state.predictor
        pred      = st.session_state.prediction or {}

        # ── 앙상블 구성 배지 ────────────────────────────────
        model_label = metrics.get('model_type', 'N/A')
        lstm_active = metrics.get('lstm_active', False)
        regime_info = metrics.get('regime', {})
        regime_name = regime_info.get('regime', '—')
        complexity  = regime_info.get('complexity', 0)
        regime_colors = {"simple":"#10b981","moderate":"#f59e0b","complex":"#ef4444"}
        regime_labels = {"simple":"🟢 단순 추세","moderate":"🟡 중간 복잡도","complex":"🔴 복잡 국면"}
        r_color = regime_colors.get(regime_name, "#64748b")
        r_label = regime_labels.get(regime_name, regime_name)

        st.markdown(
            f"""<div style="background:linear-gradient(135deg,#111827,#1a2332);
                border:1px solid #1e3a5f;border-radius:12px;padding:16px 20px;margin-bottom:16px">
                <div style="display:flex;gap:24px;flex-wrap:wrap;align-items:center">
                    <div>
                        <div style="color:#64748b;font-size:11px">활성 모델</div>
                        <div style="color:#e2e8f0;font-size:16px;font-weight:700">{model_label}</div>
                    </div>
                    <div>
                        <div style="color:#64748b;font-size:11px">시장 국면</div>
                        <div style="color:{r_color};font-size:16px;font-weight:700">{r_label}</div>
                    </div>
                    <div>
                        <div style="color:#64748b;font-size:11px">복잡도 점수</div>
                        <div style="color:#e2e8f0;font-size:16px;font-weight:700">{complexity:.3f}</div>
                    </div>
                    <div>
                        <div style="color:#64748b;font-size:11px">LSTM 상태</div>
                        <div style="color:{'#10b981' if lstm_active else '#475569'};font-size:16px;font-weight:700">
                            {'✅ 활성' if lstm_active else '⏸ 비활성'}
                        </div>
                    </div>
                    {"<div><div style='color:#64748b;font-size:11px'>LSTM 프레임워크</div><div style='color:#93c5fd;font-size:14px'>" + metrics.get('lstm_framework','') + "</div></div>" if lstm_active else ""}
                </div>
            </div>""",
            unsafe_allow_html=True
        )

        # ── 국면 복잡도 요인 레이더 ──────────────────────────
        regime_scores = regime_info.get('scores', {})
        if regime_scores:
            st.markdown("#### 📊 국면 복잡도 구성 요인")
            score_cols = st.columns(len(regime_scores))
            factor_labels = {
                "volatility":"변동성","trend_inconsistency":"추세 혼조",
                "rsi_extremes":"RSI 극단","macd_cross_freq":"MACD 교차",
                "momentum_reversal":"모멘텀 전환","bb_breakout":"BB 이탈",
            }
            for i, (k, v) in enumerate(regime_scores.items()):
                bar = "█" * int(v * 10) + "░" * (10 - int(v * 10))
                score_cols[i].metric(factor_labels.get(k, k), f"{v:.2f}", help=bar)

        st.markdown("---")

        # ── 개별 모델 성능 ───────────────────────────────────
        xgb_m  = metrics.get('xgb_metrics', metrics)
        lstm_m = metrics.get('lstm_metrics', {})

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("모델", metrics.get('model_type', 'N/A'))
        if 'cv_accuracy_mean' in xgb_m:
            m2.metric("XGB CV 정확도",  f"{xgb_m['cv_accuracy_mean']:.2%}")
            m3.metric("XGB CV 표준편차", f"±{xgb_m.get('cv_accuracy_std', 0):.2%}")
        elif 'train_accuracy' in xgb_m:
            m2.metric("XGB 학습 정확도", f"{xgb_m['train_accuracy']:.2%}")
        m4.metric("학습 데이터", f"{metrics.get('n_samples', 0):,}일")

        if lstm_active and lstm_m and 'val_accuracy' in lstm_m:
            lm1, lm2, lm3, lm4 = st.columns(4)
            lm1.metric("LSTM 검증 정확도", f"{lstm_m['val_accuracy']:.2%}")
            lm2.metric("XGB 가중치", f"{metrics.get('w_xgb', 1.0):.0%}")
            lm3.metric("LSTM 가중치", f"{metrics.get('w_lstm', 0.0):.0%}")
            lm4.metric("LSTM 시퀀스", f"{lstm_m.get('sequence_length', 20)}일")

        # ── 앙상블 예측 상세 ─────────────────────────────────
        ens_detail = pred.get('ensemble_detail', {})
        if ens_detail:
            st.markdown("---")
            st.markdown("#### 🔮 앙상블 예측 분해")
            ed1, ed2, ed3, ed4, ed5 = st.columns(5)
            ed1.metric("XGBoost 확률",  f"{ens_detail.get('p_xgb', 0):.1%}")
            if ens_detail.get('p_lstm') is not None:
                ed2.metric("LSTM 확률",     f"{ens_detail.get('p_lstm', 0):.1%}")
                agree = ens_detail.get('models_agree', True)
                ed3.metric("모델 합의",
                           "✅ 일치" if agree else "⚠️ 불일치",
                           help="불일치 시 확률이 0.5 방향으로 보정됩니다")
            ed4.metric("최종 확률",     f"{pred.get('up_probability', 0):.1%}")
            ed5.metric("신뢰도",        f"{pred.get('confidence', 0):.1%}")

        if hasattr(predictor, 'feature_importances_') and predictor.feature_importances_ is not None:
            st.markdown("---")
            st.markdown("### 📊 특성 중요도")
            st.plotly_chart(
                create_feature_importance_chart(predictor.feature_importances_),
                width='stretch'
            )

        if prediction and 'error' not in prediction:
            st.markdown("---")
            st.markdown("### 🔮 예측 상세")
            st.dataframe(pd.DataFrame([{
                '방향':    '📈 상승' if prediction['direction'] == 1 else '📉 하락',
                '상승 확률': f"{prediction['up_probability']:.2%}",
                '하락 확률': f"{prediction['down_probability']:.2%}",
                '신뢰도':  f"{prediction['confidence']:.2%}",
                '신호':    prediction['signal'],
            }]), hide_index=True)

        st.markdown("---")
        st.warning(
            "⚠️ **투자 주의사항**: 본 AI 예측은 과거 데이터 기반의 통계적 추정이며, "
            "미래 수익을 보장하지 않습니다. 투자 결정 시 다양한 정보를 종합적으로 검토하고 "
            "전문가의 조언을 구하시기 바랍니다."
        )

    with tab6:
        render_scanner_tab()

    with tab7:
        render_watchlist_tab()


# ─────────────────────────────────────────────────────────────
# S&P 500 스캐너 UI  (v2: 실시간 진행 + 캐시 + DP 블렌딩)
# ─────────────────────────────────────────────────────────────

def render_scanner_tab():
    import plotly.graph_objects as go
    from scanner import (
        SP500_TICKERS, ScanProgress, run_sp500_scan,
        get_top10, fmt_mktcap, get_cache_stats,
    )

    st.markdown("## 🔭 S&P 500 종목 스캐너")
    st.markdown(
        "500개 종목을 AI로 일괄 분석하여 **3개월 내 상승 가능성이 가장 높은 TOP 10**을 선별합니다.  \n"
        "분석 결과는 자동으로 캐시되며, 재스캔 시 변동 없는 종목은 스킵합니다."
    )

    # ── 캐시 현황 배지 ────────────────────────────────────────
    tickers_all = SP500_TICKERS
    stats = get_cache_stats(tickers_all)
    bc1, bc2, bc3, bc4 = st.columns(4)
    bc1.metric("💾 캐시된 종목",  f"{stats['total_cached']}개")
    bc2.metric("✅ 유효 캐시",    f"{stats['valid']}개",
               help=f"최근 {stats['ttl_hours']}시간 이내 분석")
    bc3.metric("⏳ 만료 캐시",    f"{stats['stale']}개")
    bc4.metric("🆕 미분석 종목",  f"{stats['uncached']}개")

    st.markdown("---")

    # ── 설정 패널 ─────────────────────────────────────────────
    with st.expander("⚙️ 스캔 설정", expanded=not st.session_state.get('scan_done')):
        col1, col2, col3 = st.columns(3)
        scan_count = col1.slider("분석 종목 수", 50, 500, 200, step=50)
        workers    = col2.slider("병렬 스레드", 2, 16, 8, step=2)
        price_thr  = col3.slider("가격 변동 임계값(%)", 0.5, 10.0, 2.0, step=0.5,
                                  help="이 % 이상 가격 변동 시 캐시 무시하고 재분석")

        # ── 분석 기간 선택 ──────────────────────────────────
        _max_d = DATA_CFG["max_period_days"]
        _period_map = {
            "1년 (252일)":    365,
            "2년 (504일)":    730,
            "3년 (756일)":   1095,
            "5년 (1,260일)": 1825,
            "10년":          3650,
            f"전체 (max, ~{_max_d:,}일)": 0,
        }
        per1, per2 = st.columns(2)
        scan_period_label = per1.selectbox(
            "📅 ML 학습 기간",
            list(_period_map.keys()),
            index=1,   # 기본값: 2년
            help="길수록 ML 학습 샘플이 늘어납니다. 단, 스캔 속도가 느려집니다."
        )
        scan_period_days = _period_map[scan_period_label]
        per2.markdown(
            f"<div style='padding-top:28px;color:#64748b;font-size:13px'>"
            f"예상 샘플 수: <b style='color:#93c5fd'>~{max(scan_period_days, 365)//4 * 3:,}개</b> "
            f"(지표 계산 여유분 포함)</div>",
            unsafe_allow_html=True
        )

        adv1, adv2 = st.columns(2)
        force_refresh = adv1.toggle("🔄 전체 강제 재분석", value=False,
                                     help="캐시를 무시하고 모든 종목을 새로 분석합니다")

        # 전략 A+B+C 안내 배지
        adv2.markdown(
            "<div style='background:#0d2137;border:1px solid #1e3a5f;"
            "border-radius:8px;padding:10px 12px;font-size:12px;margin-top:4px'>"
            "<b style='color:#93c5fd'>🧠 전체 앙상블 모드</b><br>"
            "<span style='color:#64748b'>"
            "A) 워커 3개 &nbsp;B) XGB nthread=1 &nbsp;C) LSTM CPU 전용<br>"
            "→ 모든 종목에 XGBoost+LSTM 앙상블 적용, 크래시 없음</span>"
            "</div>",
            unsafe_allow_html=True
        )

        sector_filter = st.multiselect(
            "섹터 필터",
            ["Technology","Financials","Healthcare","Consumer Discretionary",
             "Consumer Staples","Energy","Industrials","Materials",
             "Real Estate","Utilities","Communication Services"],
            default=[]
        )

    btn1, btn2 = st.columns([3, 1])
    start_btn = btn1.button("🚀 스캔 시작", use_container_width=True, type="primary",
                             disabled=st.session_state.get('scan_running', False))
    stop_btn  = btn2.button("⏹ 중단",      use_container_width=True,
                             disabled=not st.session_state.get('scan_running', False))

    if stop_btn:
        st.session_state['scan_stop'] = {'stop': True}
        st.session_state['scan_running'] = False

    # ── 스캔 실행 ─────────────────────────────────────────────
    if start_btn and not st.session_state.get('scan_running'):
        tickers = SP500_TICKERS[:scan_count]
        st.session_state.update({
            'scan_running': True,
            'scan_done':    False,
            'scan_results': None,
            'scan_top10':   None,
            'scan_stop':    {},
        })

        progress = ScanProgress(total=len(tickers))

        # ── 실시간 진행 UI 컨테이너 ───────────────────────────
        st.markdown("### ⏳ 실시간 스캔 진행")

        # 상태 바 행
        prog_bar   = st.progress(0.0, text="스캔 준비 중...")

        # 카운터 행
        cnt_cols   = st.columns(6)
        cnt_done   = cnt_cols[0].empty()
        cnt_cached = cnt_cols[1].empty()
        cnt_new    = cnt_cols[2].empty()
        cnt_price  = cnt_cols[3].empty()
        cnt_fail   = cnt_cols[4].empty()
        cnt_eta    = cnt_cols[5].empty()

        # 현재 종목 표시
        cur_ticker_box = st.empty()

        # 라이브 TOP-10 테이블
        st.markdown("#### 📊 실시간 중간 결과 (스코어 상위)")
        live_table = st.empty()

        # ── ThreadPoolExecutor 실행 (XGBoost+LSTM 전체 앙상블) ──────
        from concurrent.futures import ThreadPoolExecutor, as_completed
        from scanner import _process_one, save_cache, load_cache
        import time as _time

        cache = load_cache()

        # 예상 시간 안내
        need_new = sum(
            1 for t in tickers
            if force_refresh or t not in cache
        )
        if need_new > 0:
            est_min = need_new * 60 / max(workers, 1) / 60
            cur_ticker_box.markdown(
                f"""<div style="background:#0d2137;border:1px solid #1e3a5f;
                    border-radius:8px;padding:10px 16px">
                    🧠 XGBoost+LSTM 앙상블 스캔 시작<br>
                    <span style="color:#64748b;font-size:12px">
                    신규 분석 {need_new}개 | 워커 {workers}개 | 예상 {est_min:.0f}~{est_min*2:.0f}분
                    </span></div>""",
                unsafe_allow_html=True
            )

        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _process_one, t, cache, force_refresh, price_thr, scan_period_days
                ): t
                for t in tickers
            }

            for future in as_completed(futures):
                if st.session_state.get('scan_stop', {}).get('stop'):
                    executor.shutdown(wait=False, cancel_futures=True)
                    break

                ticker = futures[future]
                progress.current_ticker = ticker

                try:
                    _, result, status = future.result(timeout=600)
                except TimeoutError:
                    result, status = None, "failed"
                except Exception:
                    result, status = None, "failed"

                progress.done += 1
                if   status == "cached":        progress.cached        += 1
                elif status == "refreshed":     progress.refreshed     += 1
                elif status == "price_changed": progress.price_changed += 1
                else:                           progress.failed        += 1

                if result is not None:
                    cache[ticker] = result
                    progress.live_results.append(result)

                # ── UI 업데이트 ────────────────────────────────
                pct  = progress.pct
                done = progress.done
                tot  = progress.total

                prog_bar.progress(
                    pct,
                    text=f"분석 중... {done}/{tot} ({pct*100:.1f}%)"
                )

                cnt_done.metric(  "완료",      f"{done}/{tot}")
                cnt_cached.metric("⚡ 캐시",   f"{progress.cached}개",
                                  help="캐시 재사용 (빠름)")
                cnt_new.metric(   "🔄 신규",   f"{progress.refreshed + progress.price_changed}개",
                                  help="새로 분석한 종목")
                cnt_price.metric( "📈 가격변동", f"{progress.price_changed}개",
                                  help="가격 변동으로 재분석")
                cnt_fail.metric(  "❌ 실패",   f"{progress.failed}개")
                cnt_eta.metric(   "⏱ 남은시간", progress.fmt_eta())

                icon = {"cached":"⚡","refreshed":"🔄",
                        "price_changed":"📈","failed":"❌"}.get(status, "🔄")
                cur_ticker_box.markdown(
                    f"""<div style="background:#111827;border:1px solid #1e3a5f;
                        border-radius:8px;padding:10px 16px;font-family:'JetBrains Mono',monospace">
                        {icon} 현재 분석 중: <span style="color:#60a5fa;font-weight:700;
                        font-size:16px">{ticker}</span>
                        &nbsp;&nbsp;<span style="color:#64748b;font-size:13px">
                        경과: {progress.fmt_elapsed()}</span>
                    </div>""",
                    unsafe_allow_html=True
                )

                if progress.done % 5 == 0 and progress.live_results:
                    live_df = progress.sorted_df().head(10)
                    cols_needed = ["ticker","name","sector","current_price",
                                   "up_probability","estimated_upside","composite_score",
                                   "rsi","ml_signal","buy_signals"]
                    display_live = (
                        live_df[cols_needed].copy()
                        if all(col in live_df.columns for col in cols_needed)
                        else live_df.head(10)
                    )
                    if len(display_live.columns) == 10:
                        display_live.columns = [
                            "종목","회사명","섹터","현재가",
                            "상승확률(%)","예상상승폭(%)","종합스코어",
                            "RSI","ML신호","매수신호"
                        ]
                    live_table.dataframe(display_live, hide_index=True)

                if progress.done % 10 == 0:
                    save_cache(cache)

        save_cache(cache)

        # 최종 정리
        prog_bar.progress(1.0, text="✅ 스캔 완료!")
        cur_ticker_box.markdown(
            f"""<div style="background:#064e3b;border:1px solid #10b981;
                border-radius:8px;padding:10px 16px">
                ✅ 스캔 완료! &nbsp;
                총 {progress.done}개 분석 | ⚡ 캐시 {progress.cached}개 |
                🔄 신규 {progress.refreshed + progress.price_changed}개 |
                ❌ 실패 {progress.failed}개 | 소요: {progress.fmt_elapsed()}
            </div>""",
            unsafe_allow_html=True
        )

        # 결과 저장
        all_res = [cache[t] for t in tickers if t in cache]
        if all_res:
            result_df = pd.DataFrame(all_res)
            result_df = result_df.sort_values("composite_score", ascending=False).reset_index(drop=True)
            result_df.index += 1

            if sector_filter:
                result_df = result_df[result_df["sector"].isin(sector_filter)]

            st.session_state['scan_results'] = result_df
            st.session_state['scan_top10']   = get_top10(result_df)

        st.session_state['scan_running'] = False
        st.session_state['scan_done']    = True
        st.rerun()

    # ── 결과 표시 ─────────────────────────────────────────────
    if st.session_state.get('scan_done') and st.session_state.get('scan_top10') is not None:
        top10    = st.session_state['scan_top10']
        scan_all = st.session_state['scan_results']

        if top10.empty:
            st.warning("분석 결과가 없습니다. 다시 시도해주세요.")
            return

        st.markdown("---")
        st.markdown("## 🏆 TOP 10 추천 종목")

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("분석 종목",       f"{len(scan_all):,}개")
        m2.metric("평균 상승확률",    f"{scan_all['up_probability'].mean():.1f}%")
        m3.metric("TOP10 상승확률",   f"{top10['up_probability'].mean():.1f}%")
        m4.metric("TOP10 예상상승폭", f"+{top10['estimated_upside'].mean():.1f}%")

        st.markdown("---")

        # TOP 10 카드
        for rank, (_, row) in enumerate(top10.iterrows(), 1):
            medal      = {1:"🥇",2:"🥈",3:"🥉"}.get(rank, f"**#{rank}**")
            rsi_color  = ("ef4444" if float(row["RSI"])>70
                          else "10b981" if float(row["RSI"])<40 else "e2e8f0")
            score_chg  = ""
            prev_score = row.get("prev_composite_score")
            if prev_score:
                delta = float(row["종합스코어"]) - float(prev_score)
                score_chg = (f"<span style='color:#10b981;font-size:11px'>▲{delta:.3f}</span>"
                             if delta > 0 else
                             f"<span style='color:#ef4444;font-size:11px'>▼{abs(delta):.3f}</span>")
            blend_cnt  = row.get("dp_blend_count", 1)

            st.markdown(f"""
            <div style="background:linear-gradient(135deg,#111827,#1a2332);
                        border:1px solid #1e3a5f;border-radius:12px;
                        padding:20px 24px;margin-bottom:12px">
                <div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:12px">
                    <div>
                        <span style="font-size:22px">{medal}</span>
                        <span style="color:#e2e8f0;font-size:20px;font-weight:700;margin-left:8px">{row['ticker']}</span>
                        <span style="color:#94a3b8;font-size:14px;margin-left:8px">{row.get('name','')}</span>
                        <br>
                        <span style="color:#475569;font-size:12px">{row.get('sector','')}
                        &nbsp;·&nbsp; 누적 분석 {int(blend_cnt)}회</span>
                    </div>
                    <div style="display:flex;gap:20px;flex-wrap:wrap;text-align:center">
                        <div>
                            <div style="color:#10b981;font-size:22px;font-weight:700">{row['상승확률']}</div>
                            <div style="color:#64748b;font-size:11px">상승확률</div>
                        </div>
                        <div>
                            <div style="color:#3b82f6;font-size:22px;font-weight:700">{row['예상상승폭']}</div>
                            <div style="color:#64748b;font-size:11px">예상상승폭(3M)</div>
                        </div>
                        <div>
                            <div style="color:#f59e0b;font-size:22px;font-weight:700">${row['current_price']:,.2f}</div>
                            <div style="color:#64748b;font-size:11px">현재가</div>
                        </div>
                        <div>
                            <div style="color:#a855f7;font-size:22px;font-weight:700">{row['종합스코어']} {score_chg}</div>
                            <div style="color:#64748b;font-size:11px">종합스코어</div>
                        </div>
                        <div>
                            <div style="color:#{rsi_color};font-size:22px;font-weight:700">{row['RSI']}</div>
                            <div style="color:#64748b;font-size:11px">RSI</div>
                        </div>
                        <div style="text-align:center">
                            <div style="font-size:18px">{row['ML신호']}</div>
                            <div style="color:#64748b;font-size:11px">ML신호</div>
                        </div>
                        <div style="text-align:center">
                            <div style="font-size:16px">{row['매수신호']}</div>
                            <div style="color:#64748b;font-size:11px">기술신호</div>
                        </div>
                    </div>
                </div>
                <div style="margin-top:12px;display:flex;gap:16px;flex-wrap:wrap">
                    <span style="color:#64748b;font-size:12px">시가총액: {row['시가총액']}</span>
                    <span style="color:#64748b;font-size:12px">Beta: {row['beta']}</span>
                    <span style="color:#64748b;font-size:12px">PER: {row['per'] if row['per'] else 'N/A'}</span>
                    <span style="color:#64748b;font-size:12px">52주 여력: {row['52주여력']}</span>
                    <span style="color:#64748b;font-size:12px">모멘텀: {row['momentum_pct']:+.1f}%</span>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # ── 상세 분석 이동 버튼 ──────────────────────────
            b1, b2, b3 = st.columns([2, 2, 1])
            ticker_val = row['ticker']
            if b1.button(
                f"📈 {ticker_val} 상세 분석 →",
                key=f"goto_{ticker_val}_{rank}",
                use_container_width=True,
                type="primary",
            ):
                st.session_state['goto_ticker']       = ticker_val
                st.session_state['_auto_analyze']     = ticker_val
                st.session_state['_pending_model']    = 'XGBoost'
                st.session_state['_pending_finbert']  = False
                st.session_state['_pending_period']   = 1825  # 5년
                st.session_state['analysis_done']     = False
                st.rerun()

            if b2.button(
                f"🔍 {ticker_val} 검색창에 입력",
                key=f"search_{ticker_val}_{rank}",
                use_container_width=True,
            ):
                st.session_state['_prefill_ticker'] = ticker_val
                st.toast(f"← 사이드바 검색창에 {ticker_val}이 입력됩니다", icon="✅")
                st.rerun()

        # 전체 결과 테이블
        st.markdown("---")
        st.markdown("### 📋 전체 스캔 결과 (상위 50개)")
        disp_cols = ["ticker","name","sector","current_price",
                     "up_probability","estimated_upside","composite_score",
                     "rsi","buy_signals","ml_signal","beta","dp_blend_count"]
        disp_cols = [c for c in disp_cols if c in scan_all.columns]
        col_names = {
            "ticker":"종목","name":"회사명","sector":"섹터",
            "current_price":"현재가","up_probability":"상승확률(%)",
            "estimated_upside":"예상상승폭(%)","composite_score":"종합스코어",
            "rsi":"RSI","buy_signals":"매수신호수","ml_signal":"ML신호",
            "beta":"Beta","dp_blend_count":"누적분석"
        }
        disp_df = scan_all[disp_cols].head(50).rename(columns=col_names)
        st.dataframe(
            disp_df,
            column_config={
                "상승확률(%)":   st.column_config.ProgressColumn("상승확률(%)", min_value=0, max_value=100),
                "예상상승폭(%)": st.column_config.NumberColumn("예상상승폭(%)", format="%.1f%%"),
                "종합스코어":    st.column_config.NumberColumn("종합스코어",    format="%.4f"),
                "누적분석":      st.column_config.NumberColumn("누적분석",      format="%d회"),
            }
        )

        # 섹터 분포 차트
        if "sector" in scan_all.columns:
            st.markdown("---")
            st.markdown("### 📊 TOP 20 섹터 분포")
            sector_cnt = scan_all.head(20)["sector"].value_counts()
            fig = go.Figure(go.Bar(
                x=sector_cnt.index, y=sector_cnt.values,
                marker_color="#3b82f6", opacity=0.8,
            ))
            fig.update_layout(
                paper_bgcolor="#0d1117", plot_bgcolor="#111827",
                font=dict(color="#94a3b8"), height=300,
                margin=dict(t=20,b=20,l=10,r=10),
                xaxis=dict(gridcolor="#1e2d40"),
                yaxis=dict(gridcolor="#1e2d40", title="종목 수"),
            )
            st.plotly_chart(fig, width='stretch')

        st.markdown("---")
        st.warning(
            "⚠️ **투자 주의사항**: 본 스캐너는 과거 데이터 기반의 통계적 추정이며 "
            "미래 수익을 보장하지 않습니다. 반드시 추가적인 기본적 분석을 병행하시기 바랍니다."
        )


# ─────────────────────────────────────────────────────────────
# ⭐ 관심종목 탭
# ─────────────────────────────────────────────────────────────

def _wl_mini_chart(hist: pd.DataFrame, positive: bool) -> "go.Figure":
    """90일 종가 미니 라인 차트."""
    import plotly.graph_objects as go
    color = "#10b981" if positive else "#ef4444"
    fig = go.Figure(go.Scatter(
        x=hist.index, y=hist["Close"],
        mode="lines", line=dict(color=color, width=1.5),
        fill="tozeroy",
        fillcolor=f"rgba({','.join(str(int(color.lstrip('#')[i:i+2],16)) for i in (0,2,4))},0.08)",
    ))
    fig.update_layout(
        margin=dict(t=0, b=0, l=0, r=0), height=60,
        paper_bgcolor="rgba(0,0,0,0)", plot_bgcolor="rgba(0,0,0,0)",
        showlegend=False,
        xaxis=dict(visible=False), yaxis=dict(visible=False),
    )
    return fig


def _render_snapshot_card(ticker: str, snap: Dict, col) -> None:
    """관심종목 카드 한 장 렌더링."""
    with col:
        price     = snap.get("price")
        chg       = snap.get("change_pct")
        name      = snap.get("name", ticker)
        signal    = snap.get("signal", "N/A")
        rsi       = snap.get("rsi14")
        mktcap    = snap.get("market_cap")
        currency  = snap.get("currency", "USD")
        hist_90d  = snap.get("hist_90d")
        error     = snap.get("error")
        memo      = get_memo(ticker)
        added_at  = get_added_at(ticker)

        sig_cfg = {
            "BUY":  ("#10b981", "📈 매수"),
            "SELL": ("#ef4444", "📉 매도"),
            "HOLD": ("#f59e0b", "⏸ 보유"),
            "N/A":  ("#475569", "— N/A"),
        }
        sig_color, sig_label = sig_cfg.get(signal, ("#475569", signal))
        chg_color = change_color(chg)
        border_color = sig_color if signal in ("BUY","SELL") else "#1e3a5f"

        # 조건부 HTML 조각 미리 계산 (f-string 중첩 방지)
        price_str  = fmt_price(price, currency) if not error else "오류"
        rsi_str    = f"{rsi:.0f}" if rsi else "—"
        mktcap_str = fmt_mktcap(mktcap)
        memo_html  = f'<span style="color:#475569;font-size:11px">📝 {memo[:20]}</span>' if memo else ""
        error_html = f'<div style="color:#ef4444;font-size:11px;margin-top:6px">⚠️ {str(error)[:60]}</div>' if error else ""

        card_html = (
            f'<div style="background:linear-gradient(135deg,#111827,#1a2332);'
            f'border:1px solid {border_color};border-radius:12px;'
            f'padding:16px 18px;margin-bottom:4px">'
            f'<div style="display:flex;justify-content:space-between;align-items:flex-start">'
            f'<div>'
            f'<span style="color:#e2e8f0;font-size:17px;font-weight:700">{ticker}</span>'
            f'<span style="color:#64748b;font-size:12px;margin-left:6px">{name[:22]}</span>'
            f'</div>'
            f'<span style="color:{sig_color};font-size:12px;font-weight:600;'
            f'background:rgba(0,0,0,0.3);padding:2px 8px;border-radius:10px">'
            f'{sig_label}</span>'
            f'</div>'
            f'<div style="margin-top:10px;display:flex;justify-content:space-between;align-items:baseline">'
            f'<span style="color:#e2e8f0;font-size:22px;font-weight:700;font-family:JetBrains Mono,monospace">'
            f'{price_str}</span>'
            f'<span style="color:{chg_color};font-size:14px;font-weight:600">{fmt_change(chg)}</span>'
            f'</div>'
            f'<div style="margin-top:6px;display:flex;gap:12px;flex-wrap:wrap">'
            f'<span style="color:#475569;font-size:11px">RSI: <b style="color:#94a3b8">{rsi_str}</b></span>'
            f'<span style="color:#475569;font-size:11px">시총: <b style="color:#94a3b8">{mktcap_str}</b></span>'
            f'{memo_html}'
            f'</div>'
            f'{error_html}'
            f'</div>'
        )
        st.markdown(card_html, unsafe_allow_html=True)

        # 미니 차트
        if hist_90d is not None and not hist_90d.empty:
            st.plotly_chart(
                _wl_mini_chart(hist_90d, (chg or 0) >= 0),
                width='stretch', key=f"minichart_{ticker}"
            )

        # 버튼 행
        b1, b2, b3 = st.columns(3)
        if b1.button("📊 상세분석", key=f"wl_detail_{ticker}", use_container_width=True):
            st.session_state["wl_selected"] = ticker
            st.rerun()
        if b2.button("🚀 AI분석", key=f"wl_full_{ticker}", use_container_width=True):
            st.session_state["_auto_analyze"]    = ticker
            st.session_state["_pending_model"]   = "XGBoost"
            st.session_state["_pending_finbert"] = False
            st.session_state["_pending_period"]  = 1825
            st.session_state["analysis_done"]    = False
            st.rerun()
        if b3.button("🗑 삭제", key=f"wl_del_{ticker}", use_container_width=True):
            remove_ticker(ticker)
            st.session_state["wl_snapshots"].pop(ticker, None)
            if st.session_state.get("wl_selected") == ticker:
                st.session_state["wl_selected"] = None
            st.rerun()


def _render_detail_panel(ticker: str) -> None:
    """관심종목 상세 패널 (뉴스 요약 + 차트 + 지표)."""
    import plotly.graph_objects as go
    from plotly.subplots import make_subplots

    st.markdown(f"## 📋 {ticker} 상세 정보")

    # 닫기 버튼
    if st.button("✕ 닫기", key="wl_close_detail"):
        st.session_state["wl_selected"] = None
        st.rerun()

    st.markdown("---")

    # 캐시 확인
    cache_key = f"wl_detail_{ticker}"
    cached    = st.session_state.get("wl_detail_data", {}).get(ticker)

    if not cached:
        with st.spinner(f"{ticker} 데이터 로딩 중..."):
            snap    = fetch_quick_snapshot(ticker)
            news, news_sum = fetch_news_summary(
                ticker,
                company_name = snap.get("name", ""),
                sector       = snap.get("sector", ""),
                max_news     = 12,
            )
            st.session_state.setdefault("wl_detail_data", {})[ticker] = {
                "snap": snap, "news": news, "news_summary": news_sum
            }
            cached = st.session_state["wl_detail_data"][ticker]

    snap      = cached["snap"]
    news      = cached["news"]
    news_sum  = cached["news_summary"]

    # ── 상단 지표 행 ──────────────────────────────────────────
    price    = snap.get("price")
    chg      = snap.get("change_pct")
    currency = snap.get("currency", "USD")
    m1,m2,m3,m4,m5,m6 = st.columns(6)
    m1.metric("현재가",   fmt_price(price, currency))
    m2.metric("등락률",   fmt_change(chg),
              delta=f"{chg:.2f}%" if chg else None,
              delta_color="normal" if (chg or 0) >= 0 else "inverse")
    m3.metric("RSI(14)",  f"{snap.get('rsi14','—')}")
    m4.metric("MA20",     f"{snap.get('ma20',0):,.2f}" if snap.get("ma20") else "—")
    m5.metric("시가총액",  fmt_mktcap(snap.get("market_cap")))
    m6.metric("PER",      f"{snap.get('pe_ratio',0):.1f}x" if snap.get("pe_ratio") else "—")

    st.markdown("---")

    # ── 탭: 차트 / 뉴스 ──────────────────────────────────────
    dtab1, dtab2 = st.tabs(["📈 90일 차트 + 지표", "📰 관련 뉴스 요약"])

    with dtab1:
        hist = snap.get("hist_90d")
        if hist is not None and not hist.empty:
            T = {
                "paper_bg": "#0d1117", "plot_bg": "#111827", "grid": "#1e2d40",
                "text": "#94a3b8", "title": "#e2e8f0",
                "green": "#10b981", "red": "#ef4444",
                "blue": "#3b82f6", "orange": "#f59e0b",
            }

            fig = make_subplots(
                rows=2, cols=1, shared_xaxes=True,
                row_heights=[0.65, 0.35], vertical_spacing=0.04,
                subplot_titles=[f"{ticker} 90일 캔들차트", "RSI (14)"]
            )

            # 캔들스틱
            fig.add_trace(go.Candlestick(
                x=hist.index,
                open=hist["Open"], high=hist["High"],
                low=hist["Low"], close=hist["Close"],
                name="OHLC",
                increasing_line_color=T["green"],
                decreasing_line_color=T["red"],
                increasing_fillcolor=T["green"],
                decreasing_fillcolor=T["red"],
            ), row=1, col=1)

            # MA20 / MA50
            close = hist["Close"]
            ma20  = close.rolling(20).mean()
            ma50  = close.rolling(50).mean()
            for ma, color, name in [(ma20, T["blue"], "MA20"), (ma50, T["orange"], "MA50")]:
                fig.add_trace(go.Scatter(
                    x=hist.index, y=ma, name=name,
                    line=dict(color=color, width=1.5), opacity=0.8
                ), row=1, col=1)

            # RSI
            delta = close.diff()
            gain  = delta.clip(lower=0).ewm(com=13).mean()
            loss  = (-delta.clip(upper=0)).ewm(com=13).mean()
            rsi   = 100 - 100 / (1 + gain / loss.replace(0, np.nan))
            fig.add_trace(go.Scatter(
                x=hist.index, y=rsi, name="RSI",
                line=dict(color=T["blue"], width=1.5)
            ), row=2, col=1)
            for level, color in [(70, T["red"]), (30, T["green"])]:
                fig.add_hline(y=level, line_dash="dash", line_color=color,
                              line_width=1, opacity=0.5, row=2, col=1)
            fig.add_hrect(y0=70, y1=100, fillcolor=T["red"], opacity=0.05, line_width=0, row=2, col=1)
            fig.add_hrect(y0=0, y1=30, fillcolor=T["green"], opacity=0.05, line_width=0, row=2, col=1)

            fig.update_layout(
                paper_bgcolor=T["paper_bg"], plot_bgcolor=T["plot_bg"],
                font=dict(color=T["text"]), height=480,
                showlegend=True,
                legend=dict(bgcolor="rgba(13,17,23,0.8)", bordercolor=T["grid"], borderwidth=1),
                xaxis_rangeslider_visible=False,
                margin=dict(t=40, b=10, l=10, r=10),
            )
            for i in [1, 2]:
                fig.update_xaxes(gridcolor=T["grid"], zeroline=False, row=i, col=1)
                fig.update_yaxes(gridcolor=T["grid"], zeroline=False, row=i, col=1)
            fig.update_yaxes(range=[0, 100], row=2, col=1)
            st.plotly_chart(fig, width='stretch')
        else:
            st.info("차트 데이터를 불러올 수 없습니다.")

        # 메모 입력
        st.markdown("---")
        st.markdown("**📝 메모**")
        current_memo = get_memo(ticker)
        new_memo = st.text_area("메모 입력", value=current_memo, height=80,
                                key=f"memo_{ticker}", label_visibility="collapsed")
        if st.button("메모 저장", key=f"memo_save_{ticker}"):
            update_memo(ticker, new_memo)
            st.toast("메모가 저장됐습니다 ✅")

    with dtab2:
        # 감성 요약 배지
        sig        = news_sum.get("signal", "NEUTRAL")
        avg_score  = news_sum.get("avg_score", 0.0)
        sig_colors = {"BULLISH": "#10b981", "BEARISH": "#ef4444", "NEUTRAL": "#f59e0b"}
        sig_labels = {"BULLISH": "📈 강세 (Bullish)", "BEARISH": "📉 약세 (Bearish)", "NEUTRAL": "➡️ 중립 (Neutral)"}
        sig_color  = sig_colors.get(sig, "#f59e0b")

        ns1, ns2, ns3, ns4 = st.columns(4)
        ns1.markdown(
            f"<div style='background:rgba(0,0,0,0.3);border:1px solid {sig_color};"
            f"border-radius:8px;padding:10px;text-align:center'>"
            f"<div style='color:{sig_color};font-size:16px;font-weight:700'>"
            f"{sig_labels.get(sig,sig)}</div>"
            f"<div style='color:#64748b;font-size:11px'>뉴스 감성 신호</div></div>",
            unsafe_allow_html=True
        )
        ns2.metric("가중 감성점수", f"{avg_score:+.3f}", help="연관도×시간 가중 평균")
        ns3.metric("수집 기사 수", f"{news_sum.get('count', 0)}건")
        ns4.metric("직접 언급", f"{news_sum.get('direct', 0)}건", help="ticker/회사명 직접 포함")

        st.markdown("---")

        if not news:
            st.info("관련 뉴스를 찾을 수 없습니다.")
        else:
            for item in news:
                compound  = item.get("compound", 0)
                relevance = item.get("relevance", 0)
                rel_icon  = item.get("relevance_icon", "⬜")
                rel_tier  = item.get("relevance_tier", "")
                hours     = item.get("hours_ago", 0)
                time_str  = f"{hours:.0f}시간 전" if hours < 24 else f"{hours/24:.1f}일 전"
                title     = item.get("title", "")
                publisher = item.get("publisher", "")
                emoji     = item.get("emoji", "⚪")

                sent_color = "#10b981" if compound > 0.05 else "#ef4444" if compound < -0.05 else "#64748b"
                rel_color  = ("#10b981" if relevance >= 0.7 else
                              "#3b82f6" if relevance >= 0.35 else
                              "#f59e0b" if relevance >= 0.1 else "#475569")

                url = item.get("url", "")
                title_html = (f"<a href='{url}' target='_blank' style='color:#e2e8f0;"
                              f"text-decoration:none'>{title}</a>") if url else title

                st.markdown(
                    f"<div style='background:#111827;border:1px solid #1e2d40;"
                    f"border-radius:8px;padding:12px 14px;margin-bottom:8px'>"
                    f"<div style='margin-bottom:4px'>{emoji} {title_html}</div>"
                    f"<div style='display:flex;gap:12px;flex-wrap:wrap'>"
                    f"<span style='color:#64748b;font-size:11px'>{publisher} · {time_str}</span>"
                    f"<span style='color:{sent_color};font-size:11px'>"
                    f"{'▲' if compound>0.05 else '▼' if compound<-0.05 else '●'} "
                    f"감성 {compound:+.2f}</span>"
                    f"<span style='color:{rel_color};font-size:11px'>"
                    f"{rel_icon} 연관도 {relevance:.2f} ({rel_tier})</span>"
                    f"</div></div>",
                    unsafe_allow_html=True,
                )

        if st.button("🔄 뉴스 새로고침", key=f"news_refresh_{ticker}"):
            st.session_state.get("wl_detail_data", {}).pop(ticker, None)
            st.rerun()


def render_watchlist_tab() -> None:
    """관심종목 탭 전체 렌더링."""

    st.markdown("## ⭐ 관심 종목")

    tickers = load_watchlist()

    # ── 빈 상태 ────────────────────────────────────────────────
    if not tickers:
        st.markdown("""
        <div style='text-align:center;padding:60px 20px;color:#64748b'>
            <div style='font-size:48px;margin-bottom:16px'>⭐</div>
            <div style='font-size:18px;font-weight:600;margin-bottom:8px'>관심종목이 없습니다</div>
            <div style='font-size:14px'>
                사이드바의 <b>★ 추가</b> 버튼이나<br>
                분석 중인 종목의 <b>☆ 관심종목 추가</b> 버튼을 눌러주세요
            </div>
        </div>
        """, unsafe_allow_html=True)
        return

    # ── 상세 패널 모드 ─────────────────────────────────────────
    selected = st.session_state.get("wl_selected")
    if selected and selected in tickers:
        _render_detail_panel(selected)
        return

    # ── 관심종목 목록 상단 컨트롤 ─────────────────────────────
    top1, top2, top3 = st.columns([1, 1, 2])
    refresh_btn = top1.button(
        "🔄 전체 새로고침", use_container_width=True,
        help="모든 관심종목 시세를 다시 가져옵니다"
    )
    sort_by = top2.selectbox(
        "정렬 기준", ["추가 순", "등락률↓", "등락률↑", "시총↓", "RSI↓", "RSI↑"],
        label_visibility="collapsed", key="wl_sort"
    )
    top3.caption(f"총 {len(tickers)}개 종목 등록됨")

    # ── 스냅샷 로드 ────────────────────────────────────────────
    snapshots: Dict = st.session_state.get("wl_snapshots", {})

    # 새로 추가된 종목 또는 강제 새로고침
    missing = [t for t in tickers if t not in snapshots]
    if missing or refresh_btn:
        target = tickers if refresh_btn else missing
        prog   = st.progress(0.0, text="시세 로딩 중...")
        status = st.empty()

        def _cb(done, total, ticker):
            prog.progress(done / total, text=f"로딩 중... {done}/{total}  {ticker}")
            status.markdown(f"<span style='color:#64748b;font-size:12px'>현재: {ticker}</span>",
                            unsafe_allow_html=True)

        new_snaps = refresh_all_snapshots(target, progress_callback=_cb)
        snapshots.update(new_snaps)
        st.session_state["wl_snapshots"] = snapshots
        prog.empty()
        status.empty()

    # ── 정렬 ──────────────────────────────────────────────────
    def _sort_key(t):
        s = snapshots.get(t, {})
        if sort_by == "등락률↓": return -(s.get("change_pct") or -999)
        if sort_by == "등락률↑": return   s.get("change_pct") or 999
        if sort_by == "시총↓":   return -(s.get("market_cap") or 0)
        if sort_by == "RSI↓":    return -(s.get("rsi14") or 0)
        if sort_by == "RSI↑":    return   s.get("rsi14") or 999
        return tickers.index(t)   # 추가 순

    sorted_tickers = sorted(tickers, key=_sort_key)

    # ── 카드 그리드 (3열) ─────────────────────────────────────
    COLS = 3
    for row_start in range(0, len(sorted_tickers), COLS):
        row_tickers = sorted_tickers[row_start: row_start + COLS]
        cols = st.columns(COLS)
        for col_idx, ticker in enumerate(row_tickers):
            snap = snapshots.get(ticker, {"ticker": ticker, "name": ticker,
                                          "price": None, "change_pct": None})
            _render_snapshot_card(ticker, snap, cols[col_idx])

    # ── 전체 비교 테이블 ───────────────────────────────────────
    if len(tickers) >= 3:
        st.markdown("---")
        st.markdown("### 📊 전체 비교 테이블")
        rows = []
        for t in sorted_tickers:
            s = snapshots.get(t, {})
            rows.append({
                "종목":     t,
                "회사명":   (s.get("name") or t)[:20],
                "현재가":   fmt_price(s.get("price"), s.get("currency","USD")),
                "등락률":   fmt_change(s.get("change_pct")),
                "RSI":      f"{s.get('rsi14',0):.0f}" if s.get("rsi14") else "—",
                "신호":     s.get("signal","—"),
                "시가총액": fmt_mktcap(s.get("market_cap")),
                "PER":      f"{s.get('pe_ratio',0):.1f}" if s.get("pe_ratio") else "—",
                "섹터":     (s.get("sector") or "—")[:18],
                "추가일":   get_added_at(t),
            })
        tbl_df = pd.DataFrame(rows)

        def _color_signal(val):
            colors = {"BUY":"color:#10b981;font-weight:600",
                      "SELL":"color:#ef4444;font-weight:600",
                      "HOLD":"color:#f59e0b"}
            return colors.get(val, "")

        st.dataframe(tbl_df, hide_index=True,
                     column_config={
                         "종목":   st.column_config.TextColumn("종목",   width="small"),
                         "등락률": st.column_config.TextColumn("등락률", width="small"),
                         "신호":   st.column_config.TextColumn("신호",   width="small"),
                     })