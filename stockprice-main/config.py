"""
M4 Pro 하드웨어 최적화 설정
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
MacBook Pro M4 Pro (24GB Unified Memory) 전용 최적화:
  - CPU: P코어 12개 + E코어 4개 = 총 16코어
  - 메모리: 24GB Unified Memory (CPU/GPU 공유)
  - GPU: Metal (MPS) 지원 → PyTorch MPS 가속
  - XGBoost: tree_method='hist', nthread 자동 설정
  - Pandas: float32 기본, copy-on-write 활성화
"""

from __future__ import annotations

import os
import sys
import platform
import subprocess
import multiprocessing
from typing import Dict, Any

# ─────────────────────────────────────────────────────────────
# 하드웨어 감지
# ─────────────────────────────────────────────────────────────

def _is_apple_silicon() -> bool:
    return sys.platform == "darwin" and platform.machine() == "arm64"


def _get_cpu_count() -> Dict[str, int]:
    """M4 Pro 코어 수 감지 (p-core / e-core 분리)."""
    total = multiprocessing.cpu_count()
    if _is_apple_silicon():
        # sysctl로 P코어 / E코어 수 조회
        try:
            p = int(subprocess.check_output(
                ["sysctl", "-n", "hw.perflevel0.logicalcpu"], stderr=subprocess.DEVNULL
            ).decode().strip())
            e = int(subprocess.check_output(
                ["sysctl", "-n", "hw.perflevel1.logicalcpu"], stderr=subprocess.DEVNULL
            ).decode().strip())
            return {"total": total, "performance": p, "efficiency": e}
        except Exception:
            pass
    return {"total": total, "performance": total, "efficiency": 0}


def _get_memory_gb() -> float:
    """전체 메모리 용량 (GB)."""
    try:
        if sys.platform == "darwin":
            out = subprocess.check_output(["sysctl", "-n", "hw.memsize"],
                                          stderr=subprocess.DEVNULL).decode().strip()
            return int(out) / (1024 ** 3)
    except Exception:
        pass
    return 8.0   # 기본값


def _mps_available() -> bool:
    """Apple Metal (MPS) 사용 가능 여부."""
    try:
        import torch
        return torch.backends.mps.is_available()
    except Exception:
        return False


# ─────────────────────────────────────────────────────────────
# 하드웨어 프로필
# ─────────────────────────────────────────────────────────────

CPU      = _get_cpu_count()
MEM_GB   = _get_memory_gb()
IS_M_CHIP = _is_apple_silicon()
MPS_OK   = _mps_available()

# M4 Pro 기준 최적값 계산
# P코어만 연산에 사용 (E코어는 I/O 담당)
_P_CORES  = CPU["performance"]
_E_CORES  = CPU["efficiency"]
_ALL_CORES = CPU["total"]

# ─────────────────────────────────────────────────────────────
# 최적화 설정값
# ─────────────────────────────────────────────────────────────

# ── XGBoost (개별 분석용) ─────────────────────────────────────
XGBOOST = {
    "tree_method":    "hist",        # M4 CPU 최적
    "device":         "cpu",
    "nthread":        _P_CORES,      # P코어 전체 사용 (단일 분석)
    "max_bin":        256,
    "grow_policy":    "lossguide",
}

# ── XGBoost (스캐너용, 워커당 1스레드) ───────────────────────
# 전략 B: nthread=1 고정
# 3워커 × nthread=1 = OMP 3스레드 총합 → 경합/크래시 없음
XGBOOST_SCANNER = {
    "tree_method":    "hist",
    "device":         "cpu",
    "nthread":        1,             # ← 핵심: 워커당 1스레드 고정
    "max_bin":        128,           # 메모리/속도 균형
    "grow_policy":    "lossguide",
}

# ── PyTorch 스캐너 전용 (전략 C) ────────────────────────────
# LSTM device=cpu 강제: MPS 동시 접근 금지
# CPU에서 num_threads=1로 실행 → 3워커 동시에도 안전
PYTORCH_SCANNER = {
    "device":       "cpu",          # ← MPS 절대 사용 금지
    "dtype":        "float32",
    "num_threads":  1,              # 워커당 1스레드
    "batch_size":   32,
}

# ── PyTorch / LSTM ────────────────────────────────────────────
PYTORCH = {
    "device":          "mps" if MPS_OK else "cpu",
    "dtype":           "float32",    # MPS는 float32만 완전 지원
    "num_threads":     _P_CORES,     # CPU 폴백 시 P코어
    "pin_memory":      False,        # Unified Memory라 불필요
    "non_blocking":    True,         # 비동기 메모리 전송
    # 배치 크기: 메모리 GB에 비례
    "batch_size":      min(128, max(32, int(MEM_GB * 4))),
}

# ── Pandas ────────────────────────────────────────────────────
PANDAS = {
    "default_float":  "float32",     # float64 → float32 (메모리 50% 절감)
    "copy_on_write":  True,          # pandas 2.0+ CoW 활성화
}

# ── 병렬 처리 (스캐너) ────────────────────────────────────────
# ThreadPoolExecutor + LSTM CPU 앙상블:
#   - 워커 2개 × LSTM CPU (nthread=1) = OMP 2스레드 → 충돌 없음
#   - MPS 미사용 → GPU 크래시 구조적 불가능
#   - 처음 전체 스캔은 오래 걸리나 DP 캐시로 이후 대폭 단축
#   - M4 Pro 24GB 기준 500종목 약 2~4시간 (처음 1회)
PARALLEL = {
    "scanner_workers":  2,      # LSTM CPU 동시 2개 (안전 상한)
    "analysis_workers": _P_CORES,
    "scanner_sleep":    0.0,
}

# ── 메모리 한도 ───────────────────────────────────────────────
MEMORY = {
    "total_gb":          MEM_GB,
    # 전체 메모리의 60%만 사용 (OS + 브라우저 + Streamlit 여유)
    "usable_gb":         MEM_GB * 0.60,
    # 단일 분석 df 최대 행수 (row * ~50col * 4byte → ~1GB)
    "max_df_rows":       min(6000, int(MEM_GB * 250)),
    # 스캐너 캐시 최대 종목수
    "max_cache_tickers": min(600, int(MEM_GB * 25)),
    # Streamlit 세션 캐시 최대 항목
    "st_cache_items":    10,
}

# ── 데이터 기간 자동 조정 ─────────────────────────────────────
DATA = {
    # 메모리 24GB → 최대 6000일 (약 24년) 지원
    "max_period_days":   MEMORY["max_df_rows"],
    # ML 학습 최대 샘플 (메모리 기반)
    "max_train_samples": min(4000, int(MEM_GB * 167)),
    # LSTM 학습 최대 샘플 (GPU 메모리 고려)
    "max_lstm_samples":  3000,
}

# ─────────────────────────────────────────────────────────────
# 환경 변수 설정 (앱 시작 시 1회)
# ─────────────────────────────────────────────────────────────

def apply_system_settings() -> None:
    """OS 수준 최적화 환경변수 적용."""

    # NumPy / SciPy → Apple Accelerate 프레임워크 사용
    os.environ.setdefault("VECLIB_MAXIMUM_THREADS", str(_P_CORES))
    os.environ.setdefault("OPENBLAS_NUM_THREADS",   str(_P_CORES))
    os.environ.setdefault("MKL_NUM_THREADS",        str(_P_CORES))
    os.environ.setdefault("OMP_NUM_THREADS",        str(_P_CORES))
    os.environ.setdefault("NUMEXPR_NUM_THREADS",    str(_P_CORES))

    # PyTorch MPS 메모리 관리 (Unified Memory 최적화)
    if MPS_OK:
        os.environ.setdefault("PYTORCH_MPS_HIGH_WATERMARK_RATIO", "0.0")  # 동적 할당
        os.environ.setdefault("PYTORCH_ENABLE_MPS_FALLBACK", "1")          # 미지원 op CPU 폴백

    # Pandas Copy-on-Write (pandas 2.0+)
    try:
        import pandas as pd
        pd.options.mode.copy_on_write = True
    except Exception:
        pass

    # Streamlit watchdog 비활성화 (재시작 루프 방지)
    os.environ.setdefault("STREAMLIT_SERVER_FILE_WATCHER_TYPE", "none")

    # tokenizers 병렬화 경고 억제
    os.environ.setdefault("TOKENIZERS_PARALLELISM", "false")


def get_torch_device():
    """최적 PyTorch 디바이스 반환."""
    try:
        import torch
        if torch.backends.mps.is_available():
            return torch.device("mps")
        if torch.cuda.is_available():
            return torch.device("cuda")
    except Exception:
        pass
    return "cpu"  # string 반환 (torch 미설치 시)


def memory_status() -> Dict[str, Any]:
    """현재 메모리 사용 현황."""
    status: Dict[str, Any] = {
        "total_gb":  round(MEM_GB, 1),
        "cpu_cores": f"P{_P_CORES}+E{_E_CORES}",
        "mps":       MPS_OK,
        "chip":      "Apple Silicon" if IS_M_CHIP else platform.processor(),
    }
    try:
        import psutil
        vm = psutil.virtual_memory()
        status["used_gb"]      = round(vm.used / 1e9, 1)
        status["available_gb"] = round(vm.available / 1e9, 1)
        status["percent"]      = vm.percent
    except Exception:
        pass
    return status


def print_hw_info() -> None:
    """시작 시 하드웨어 정보 출력."""
    import logging
    log = logging.getLogger("stock_analyzer")
    status = memory_status()
    log.info("━" * 55)
    log.info(f"  🖥  칩:    {status['chip']}")
    log.info(f"  🧮  코어:  {status['cpu_cores']} ({_ALL_CORES}개 논리)")
    log.info(f"  💾  메모리: {status['total_gb']} GB")
    log.info(f"  🎮  MPS:  {'✅ 활성' if status['mps'] else '❌ 비활성'}")
    log.info(f"  ⚙️   XGB:  tree_method={XGBOOST['tree_method']}, nthread={XGBOOST['nthread']}")
    log.info(f"  🔀  스캐너 워커: {PARALLEL['scanner_workers']}개")
    log.info(f"  📊  최대 학습 샘플: {DATA['max_train_samples']:,}개")
    log.info("━" * 55)