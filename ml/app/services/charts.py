"""
인터랙티브 차트 생성 모듈 (Plotly 기반)
- 캔들스틱 + 기술적 지표 오버레이
- RSI, MACD, 볼린저 밴드
- 포트폴리오 성과 차트
"""


import pandas as pd
import plotly.graph_objects as go
from plotly.subplots import make_subplots

DARK_THEME = dict(
    bg='#0d1117',
    paper_bg='#0d1117',
    plot_bg='#111827',
    grid='#1e2d40',
    text='#94a3b8',
    title='#e2e8f0',
    green='#10b981',
    red='#ef4444',
    blue='#3b82f6',
    orange='#f59e0b',
    purple='#a855f7',
    cyan='#06b6d4',
    candle_up='#10b981',
    candle_down='#ef4444',
)


def create_main_chart(
    df: pd.DataFrame,
    ticker: str,
    show_ma: bool = True,
    show_bb: bool = True,
    show_volume: bool = True,
    signal: str | None = None,
    display_days: int | None = None,
) -> go.Figure:
    """
    메인 캔들스틱 차트 + 기술적 지표 오버레이

    display_days: 표시할 거래일 수.
      None 또는 0 → 전체 데이터 표시
      252 → 최근 1년, 504 → 2년 ...
    """
    T = DARK_THEME

    # 표시 기간 슬라이싱 (None/0 = 전체)
    if display_days and display_days > 0:
        display_df = df.tail(display_days)
    else:
        display_df = df.copy()
    
    rows = 3 if show_volume else 2
    row_heights = [0.6, 0.25, 0.15] if show_volume else [0.65, 0.35]
    subplot_titles = (
        [f"{ticker} Price Chart", "RSI (14)", "Volume"]
        if show_volume
        else [f"{ticker} Price Chart", "RSI (14)"]
    )
    
    fig = make_subplots(
        rows=rows, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=row_heights,
        subplot_titles=subplot_titles
    )
    
    # ── 캔들스틱 ──────────────────────────────────────────
    fig.add_trace(
        go.Candlestick(
            x=display_df.index,
            open=display_df['Open'],
            high=display_df['High'],
            low=display_df['Low'],
            close=display_df['Close'],
            name='OHLC',
            increasing_line_color=T['candle_up'],
            decreasing_line_color=T['candle_down'],
            increasing_fillcolor=T['candle_up'],
            decreasing_fillcolor=T['candle_down'],
        ),
        row=1, col=1
    )
    
    # ── 이동평균선 ────────────────────────────────────────
    if show_ma:
        ma_config = [
            ('MA20', T['blue'], 1.5, 'MA 20'),
            ('MA50', T['orange'], 1.5, 'MA 50'),
            ('MA200', T['purple'], 1.5, 'MA 200'),
        ]
        for col, color, width, name in ma_config:
            if col in display_df.columns:
                fig.add_trace(
                    go.Scatter(
                        x=display_df.index, y=display_df[col],
                        name=name, line=dict(color=color, width=width),
                        opacity=0.8
                    ),
                    row=1, col=1
                )
    
    # ── 볼린저 밴드 ────────────────────────────────────────
    if show_bb and 'BB_Upper' in display_df.columns:
        fig.add_trace(
            go.Scatter(
                x=display_df.index, y=display_df['BB_Upper'],
                name='BB Upper', line=dict(color=T['cyan'], width=1, dash='dot'),
                opacity=0.5
            ),
            row=1, col=1
        )
        fig.add_trace(
            go.Scatter(
                x=display_df.index, y=display_df['BB_Lower'],
                name='BB Lower', line=dict(color=T['cyan'], width=1, dash='dot'),
                fill='tonexty', fillcolor='rgba(6, 182, 212, 0.05)',
                opacity=0.5
            ),
            row=1, col=1
        )
    
    # ── RSI ───────────────────────────────────────────────
    if 'RSI14' in display_df.columns:
        rsi = display_df['RSI14']
        
        # 색상 그라디언트 (과매수=빨강, 과매도=초록)
        fig.add_trace(
            go.Scatter(
                x=display_df.index, y=rsi,
                name='RSI 14',
                line=dict(color=T['blue'], width=1.5),
            ),
            row=2, col=1
        )
        
        # 과매수/과매도 기준선
        for level, color, label in [
            (70, T["red"], "Overbought"), (30, T["green"], "Oversold"), (50, T["grid"], "")
        ]:
            fig.add_hline(
                y=level, line_dash="dash", line_color=color,
                line_width=1, opacity=0.6, row=2, col=1
            )
        
        # 과매수 영역 강조
        fig.add_hrect(
            y0=70, y1=100, fillcolor=T['red'], opacity=0.05,
            line_width=0, row=2, col=1
        )
        fig.add_hrect(
            y0=0, y1=30, fillcolor=T['green'], opacity=0.05,
            line_width=0, row=2, col=1
        )
    
    # ── 거래량 ────────────────────────────────────────────
    if show_volume and rows == 3:
        colors = [T['candle_up'] if c >= o else T['candle_down']
                  for c, o in zip(display_df['Close'], display_df['Open'])]
        
        fig.add_trace(
            go.Bar(
                x=display_df.index,
                y=display_df['Volume'],
                name='Volume',
                marker_color=colors,
                opacity=0.7,
            ),
            row=3, col=1
        )
        
        if 'Volume_SMA20' in display_df.columns:
            fig.add_trace(
                go.Scatter(
                    x=display_df.index, y=display_df['Volume_SMA20'],
                    name='Vol MA20', line=dict(color=T['orange'], width=1.5),
                ),
                row=3, col=1
            )
    
    # ── 레이아웃 ──────────────────────────────────────────
    signal_colors = {'BUY': T['green'], 'SELL': T['red'], 'HOLD': T['orange']}
    title_color = signal_colors.get(signal, T['title']) if signal else T['title']
    signal_text = f" → <span style='color:{title_color}'>{signal}</span>" if signal else ""
    
    # 데이터 기간 표기
    date_range_str = ""
    if not display_df.empty:
        d_start = display_df.index[0]
        d_end   = display_df.index[-1]
        if hasattr(d_start, 'strftime'):
            s = d_start.strftime("%Y-%m-%d")
            e = d_end.strftime("%Y-%m-%d")
            date_range_str = (
                f" <span style='color:#475569;font-size:13px'>"
                f"({s} ~ {e}, {len(display_df):,}일)</span>"
            )

    fig.update_layout(
        title=dict(
            text=f"<b>{ticker}</b> Technical Analysis{signal_text}{date_range_str}",
            font=dict(size=18, color=T['title'])
        ),
        paper_bgcolor=T['paper_bg'],
        plot_bgcolor=T['plot_bg'],
        font=dict(color=T['text'], family='Space Grotesk, sans-serif'),
        height=700,
        showlegend=True,
        legend=dict(
            bgcolor='rgba(13,17,23,0.8)',
            bordercolor=T['grid'],
            borderwidth=1,
            font=dict(color=T['text'])
        ),
        xaxis_rangeslider_visible=False,
        margin=dict(t=60, b=20, l=10, r=10),
    )
    
    # 모든 서브플롯 배경 설정
    for i in range(1, rows + 1):
        fig.update_xaxes(
            gridcolor=T['grid'], gridwidth=0.5,
            zeroline=False, showspikes=True,
            spikecolor=T['text'], spikethickness=1,
            row=i, col=1
        )
        fig.update_yaxes(
            gridcolor=T['grid'], gridwidth=0.5,
            zeroline=False, showspikes=True,
            spikecolor=T['text'], spikethickness=1,
            row=i, col=1
        )
    
    # RSI 축 범위 고정
    fig.update_yaxes(range=[0, 100], row=2, col=1)
    
    return fig


def create_macd_chart(df: pd.DataFrame, display_days: int | None = None) -> go.Figure:
    """MACD 차트  display_days=None → 전체 표시"""
    T = DARK_THEME
    if display_days and display_days > 0:
        display_df = df.tail(display_days)
    else:
        display_df = df.copy()
    
    fig = make_subplots(
        rows=2, cols=1,
        shared_xaxes=True,
        vertical_spacing=0.05,
        row_heights=[0.5, 0.5],
        subplot_titles=['MACD Line & Signal', 'MACD Histogram']
    )
    
    if 'MACD' not in display_df.columns:
        return fig
    
    # MACD Lines
    fig.add_trace(
        go.Scatter(x=display_df.index, y=display_df['MACD'],
                   name='MACD', line=dict(color=T['blue'], width=1.5)),
        row=1, col=1
    )
    fig.add_trace(
        go.Scatter(x=display_df.index, y=display_df['MACD_Signal'],
                   name='Signal', line=dict(color=T['orange'], width=1.5)),
        row=1, col=1
    )
    
    # Histogram
    hist = display_df['MACD_Hist']
    colors = [T['green'] if v >= 0 else T['red'] for v in hist]
    fig.add_trace(
        go.Bar(x=display_df.index, y=hist, name='Histogram',
               marker_color=colors, opacity=0.7),
        row=2, col=1
    )
    fig.add_hline(y=0, line_color=T['grid'], line_width=1, row=2, col=1)
    
    fig.update_layout(
        paper_bgcolor=T['paper_bg'],
        plot_bgcolor=T['plot_bg'],
        font=dict(color=T['text']),
        height=400,
        showlegend=True,
        legend=dict(bgcolor='rgba(13,17,23,0.8)', bordercolor=T['grid'], borderwidth=1),
        margin=dict(t=40, b=20, l=10, r=10),
    )
    fig.update_xaxes(gridcolor=T['grid'], gridwidth=0.5)
    fig.update_yaxes(gridcolor=T['grid'], gridwidth=0.5)
    
    return fig


def create_feature_importance_chart(feature_importances: pd.Series, top_n: int = 15) -> go.Figure:
    """피처 중요도 차트"""
    T = DARK_THEME
    
    top = feature_importances.head(top_n).sort_values()
    
    # 색상: 중요도 높을수록 파란색
    max_val = top.max()
    colors = [f'rgba(59, 130, 246, {0.3 + 0.7 * v/max_val:.2f})' for v in top.values]
    
    fig = go.Figure(go.Bar(
        x=top.values,
        y=top.index,
        orientation='h',
        marker_color=colors,
        text=[f'{v:.3f}' for v in top.values],
        textposition='outside',
        textfont=dict(color=T['text'], size=11),
    ))
    
    fig.update_layout(
        title=dict(text='Feature Importance (Top 15)', font=dict(color=T['title'], size=14)),
        paper_bgcolor=T['paper_bg'],
        plot_bgcolor=T['plot_bg'],
        font=dict(color=T['text']),
        height=450,
        margin=dict(t=40, b=20, l=150, r=80),
        xaxis=dict(gridcolor=T['grid'], title='Importance Score'),
        yaxis=dict(gridcolor=T['grid']),
    )
    
    return fig


def create_sentiment_gauge(sentiment_score: float) -> go.Figure:
    """감성 점수 게이지 차트"""
    T = DARK_THEME
    
    # -1 ~ 1 → 0 ~ 100 변환
    gauge_val = (sentiment_score + 1) * 50
    
    if sentiment_score > 0.15:
        color = T['green']
        label = '긍정적 (Bullish)'
    elif sentiment_score < -0.15:
        color = T['red']
        label = '부정적 (Bearish)'
    else:
        color = T['orange']
        label = '중립 (Neutral)'
    
    gauge_title = f'뉴스 감성 지수<br><span style="font-size:14px;color:{T["text"]}">{label}</span>'
    fig = go.Figure(go.Indicator(
        mode="gauge+number+delta",
        value=gauge_val,
        delta={'reference': 50, 'suffix': '%'},
        number={'suffix': '%', 'font': {'size': 28, 'color': color}},
        title={'text': gauge_title, 'font': {'size': 14, 'color': T['title']}},
        gauge={
            'axis': {'range': [0, 100], 'tickwidth': 1, 'tickcolor': T['text']},
            'bar': {'color': color, 'thickness': 0.3},
            'bgcolor': T['plot_bg'],
            'borderwidth': 0,
            'steps': [
                {'range': [0, 35], 'color': 'rgba(239, 68, 68, 0.15)'},
                {'range': [35, 65], 'color': 'rgba(245, 158, 11, 0.1)'},
                {'range': [65, 100], 'color': 'rgba(16, 185, 129, 0.15)'},
            ],
            'threshold': {
                'line': {'color': color, 'width': 3},
                'thickness': 0.85,
                'value': gauge_val
            }
        }
    ))
    
    fig.update_layout(
        paper_bgcolor='rgba(0,0,0,0)',
        font=dict(color=T['text'], family='Space Grotesk'),
        height=250,
        margin=dict(t=50, b=10, l=20, r=20),
    )
    
    return fig


def create_portfolio_chart(portfolio_df: pd.DataFrame, initial_capital: float) -> go.Figure:
    """백테스트 포트폴리오 성과 차트"""
    T = DARK_THEME
    
    pct_returns = (portfolio_df['value'] / initial_capital - 1) * 100
    
    color = T['green'] if pct_returns.iloc[-1] >= 0 else T['red']
    
    fig = go.Figure()
    
    fig.add_trace(go.Scatter(
        x=portfolio_df.index,
        y=pct_returns,
        name='Strategy',
        line=dict(color=color, width=2),
        fill='tozeroy',
        fillcolor=f'rgba({int(color[1:3], 16)},{int(color[3:5], 16)},{int(color[5:7], 16)},0.1)',
    ))
    
    fig.add_hline(y=0, line_color=T['grid'], line_width=1)
    
    fig.update_layout(
        title=dict(text='백테스트 누적 수익률 (%)', font=dict(color=T['title'])),
        paper_bgcolor=T['paper_bg'],
        plot_bgcolor=T['plot_bg'],
        font=dict(color=T['text']),
        height=350,
        margin=dict(t=40, b=20, l=10, r=10),
        xaxis=dict(gridcolor=T['grid']),
        yaxis=dict(gridcolor=T['grid'], ticksuffix='%'),
    )
    
    return fig