"""
AI-Powered Integrated Stock Analysis & Real-time Prediction System
Main Streamlit Application Entry Point
"""

import sys
import streamlit as st
import warnings
warnings.filterwarnings('ignore')

# ── Python 버전 체크 ──────────────────────────────────────────
def _check_env():
    ver = sys.version_info
    if ver < (3, 10):
        st.error(f"Python 3.10 이상이 필요합니다. 현재: {ver.major}.{ver.minor}")
        st.stop()

_check_env()

# ── M4 Pro 최적화 설정 1회 적용 ───────────────────────────────
from config import apply_system_settings, print_hw_info
apply_system_settings()
print_hw_info()

st.set_page_config(
    page_title="AI Stock Analyzer",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded"
)

st.markdown("""
<style>
    @import url('https://fonts.googleapis.com/css2?family=Space+Grotesk:wght@300;400;500;600;700&family=JetBrains+Mono:wght@400;500&display=swap');

    * { font-family: 'Space Grotesk', sans-serif; }
    code, .stCode { font-family: 'JetBrains Mono', monospace; }

    .main { background: #0a0e1a; }
    .stApp { background: linear-gradient(135deg, #0a0e1a 0%, #0d1421 50%, #0a0e1a 100%); }
    .css-1d391kg { background: #0d1421; border-right: 1px solid #1e2d40; }

    .signal-buy {
        background: linear-gradient(135deg, #065f46, #059669);
        color: #d1fae5; padding: 8px 20px; border-radius: 20px;
        font-weight: 700; font-size: 18px; display: inline-block;
    }
    .signal-sell {
        background: linear-gradient(135deg, #7f1d1d, #dc2626);
        color: #fee2e2; padding: 8px 20px; border-radius: 20px;
        font-weight: 700; font-size: 18px; display: inline-block;
    }
    .signal-hold {
        background: linear-gradient(135deg, #78350f, #d97706);
        color: #fef3c7; padding: 8px 20px; border-radius: 20px;
        font-weight: 700; font-size: 18px; display: inline-block;
    }

    .main-header {
        background: linear-gradient(90deg, #1e3a5f, #1a2332);
        border: 1px solid #1e3a5f; border-radius: 16px;
        padding: 24px 32px; margin-bottom: 24px;
    }

    .stButton > button {
        background: linear-gradient(135deg, #1d4ed8, #3b82f6);
        color: white; border: none; border-radius: 8px;
        font-weight: 600; padding: 12px 32px; font-size: 15px;
        transition: all 0.3s ease; width: 100%;
    }
    .stButton > button:hover {
        background: linear-gradient(135deg, #2563eb, #60a5fa);
        transform: translateY(-1px);
        box-shadow: 0 8px 25px rgba(59, 130, 246, 0.3);
    }

    h1, h2, h3 { color: #e2e8f0; }
    .stMarkdown p { color: #94a3b8; }

    .stTabs [data-baseweb="tab-list"] { background: #111827; border-radius: 10px; padding: 4px; }
    .stTabs [data-baseweb="tab"] { color: #64748b; font-weight: 500; }
    .stTabs [aria-selected="true"] { background: #1e3a5f; color: #93c5fd; border-radius: 8px; }

    .stProgress > div > div { background: linear-gradient(90deg, #1d4ed8, #06b6d4); border-radius: 4px; }
    .stSelectbox > div > div { background: #111827; border-color: #1e3a5f; color: #e2e8f0; }
    .stTextInput > div > div > input { background: #111827; border-color: #1e3a5f; color: #e2e8f0; }
    hr { border-color: #1e2d40; }
</style>
""", unsafe_allow_html=True)

from dashboard import render_dashboard

def main():
    render_dashboard()

if __name__ == "__main__":
    main()