# StockPriceAI

[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

AI 기반 주식 분석 웹 서비스. XGBoost + LSTM 앙상블 예측, S&P 500 스캐너, 실시간 감성 분석을 제공합니다.

> **현재 상태**: Phase 5~6 진행 중 — 테스트·코드 품질 / EC2·RDS 배포 및 CI/CD 구축 단계  
> **목표**: Streamlit 단일 앱 → Next.js + FastAPI + Docker Compose 풀스택 웹 서비스

---

## 목차

1. [동기 및 문제 정의](#1-동기-및-문제-정의)
2. [주요 기능](#2-주요-기능)
3. [아키텍처](#3-아키텍처)
4. [기술 스택 및 선택 이유](#4-기술-스택-및-선택-이유)
5. [프로젝트 구조](#5-프로젝트-구조)
6. [빠른 시작 (로컬)](#6-빠른-시작-로컬)
7. [데이터베이스 설계](#7-데이터베이스-설계)
8. [API 설계](#8-api-설계)
9. [CI/CD 파이프라인](#9-cicd-파이프라인)
10. [리팩토링 진행 현황](#10-리팩토링-진행-현황)
11. [Lessons Learned & Challenges](#11-lessons-learned--challenges)
12. [팀](#12-팀)

---

## 1. 동기 및 문제 정의

### 왜 만들었는가

기존 Streamlit 앱([stockprice-main/](stockprice-main/))은 macOS Apple Silicon 전용 로컬 도구였습니다. 다음 문제들이 존재했습니다.

- **단일 사용자 구조**: 로컬에서만 실행되므로 팀원 간 결과 공유 불가
- **평면 파일 저장소**: `scan_cache.json`, `watchlist.json`으로 데이터를 관리해 동시성·영속성·쿼리 기능 없음
- **플랫폼 종속**: M4 Pro의 MPS, P코어 감지 등 Apple Silicon 특화 코드가 산재해 서버 배포 불가
- **ML 모듈 미노출**: XGBoost + LSTM 앙상블, 뉴스 임팩트 프레임워크 등 핵심 기능이 REST API로 제공되지 않음

### 해결 방법

AWS RDS(PostgreSQL)를 기반으로 세 서비스(Next.js 프론트엔드, FastAPI 백엔드, FastAPI ML 서비스)를 Docker Compose로 오케스트레이션하는 풀스택 웹 서비스를 구축합니다.

### 학습 목표

| 영역          | 목표 기술                            |
| ------------- | ------------------------------------ |
| 컨테이너화    | Docker, Docker Compose 멀티 컨테이너 |
| 클라우드 배포 | AWS EC2 + RDS 전체 스택              |
| 자동화        | GitHub Actions CI/CD, SSH 자동 배포  |
| 비동기 처리   | Celery + Redis 작업 큐               |
| 풀스택 개발   | Next.js ↔ FastAPI REST API 연동      |

---

## 2. 주요 기능

### 📊 AI 주식 예측 및 분석

티커를 입력하면 다음을 자동으로 수행합니다.

- yfinance로 OHLCV 및 재무 데이터 수집
- 기술적 지표 30개 계산 (RSI, MACD, 볼린저밴드, 스토캐스틱 등)
- **XGBoost + LSTM 앙상블 예측**: RegimeDetector가 시장 국면 복잡도(0~1)를 계산해 LSTM 가중치를 동적 결정
- 매수/매도/관망 신호 및 상승 확률 제공
- 차트: 캔들스틱, MACD, 지지/저항선 (Plotly)

#### 앙상블 예측 엔진

```
EnsemblePredictor
├── RegimeDetector      → 변동성·추세·RSI·MACD 등 6개 지표로 복잡도(0~1) 계산
├── XGBoostPredictor    → 항상 실행 (베이스라인, Walk-forward CV)
└── LSTMPredictor       → 복잡도 ≥ 0.30 시 조건부 실행 (LayerNorm + AdamW)

앙상블 가중치:
  w_lstm = interp(complexity, [0.30, 1.0], [0.20, 0.55])
  w_lstm ×= (lstm_val_acc / xgb_cv_acc).clip(0.7, 1.3)
  p_final = w_xgb × p_xgb + w_lstm × p_lstm
```

| 신호    | 조건           |
| ------- | -------------- |
| 📈 BUY  | 상승확률 > 58% |
| 📉 SELL | 하락확률 > 58% |
| ⏸ HOLD  | 그 외          |

### 🔭 S&P 500 배치 스캐너

- 최대 500개 종목 일괄 분석 (ThreadPoolExecutor 워커 2개)
- **DP 캐싱**: `composite_new = 0.3 × new + 0.7 × old` EWMA 블렌딩으로 재스캔 시간 대폭 단축
- 종합 스코어 = `up_prob × estimated_upside × momentum_factor × quality_factor`
- 섹터 필터, 실시간 진행률, 상위 종목 카드 표시
- EventBridge + Lambda를 이용한 **평일 17:00 KST 자동 실행** (프로덕션)

| 상황                 | 소요 시간  |
| -------------------- | ---------- |
| 첫 전체 스캔 500종목 | 약 2~4시간 |
| DP 캐시 재사용 시    | 수 분      |

### 📰 뉴스 임팩트 분석

Wall Street 트레이딩 데스크 방법론을 코드로 구현한 뉴스 정량화 시스템입니다.

**Impact Score 공식**: `I = (S × M) × √V × P`

| 변수              | 의미                                 | 범위       |
| ----------------- | ------------------------------------ | ---------- |
| S (Surprise)      | VADER/FinBERT 감성 + 서프라이즈 보정 | -1.0 ~ 1.0 |
| M (Market Regime) | 시장 국면 증폭 계수                  | 0.8 ~ 2.5  |
| V (Volatility)    | 종목 베타                            | 0.1 ~ ∞    |
| P (Persistence)   | 정보 유효 기간                       | 0.05 ~ 1.0 |

5가지 뉴스 유형 분류 (Surprise / Structural / Transient / Contagion / General)  
매크로 Knowledge Graph: 10개 테마 × 11개 섹터 자동 노출도 계산

### ⭐ 관심종목 (Watchlist) 관리

- 종목 추가/삭제, 메모 기능
- 90일 미니 차트 + 6개 기술 지표 투표 기반 신호 (RSI, MA정배열, 볼린저, MACD, 스토캐스틱)
- 데이터 저장: JSON 파일 → **PostgreSQL(RDS)** 마이그레이션 완료

### 🔐 사용자 인증 및 보안

- JWT + bcrypt 기반 회원가입/로그인
- 보호된 엔드포인트 접근 관리
- Swagger UI에서 Bearer Token 인증 테스트 지원

---

## 3. 아키텍처

### 목표 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                      클라이언트 (브라우저)                         │
│                    Next.js (TypeScript)                          │
│                    Vercel (무료 플랜)                             │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTPS
┌───────────────────────────▼─────────────────────────────────────┐
│                   EC2 t3.medium (단일 인스턴스)                   │
│                       Docker Compose                             │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────┐  ┌──────────┐  │
│  │    Nginx    │  │   Backend   │  │    ML    │  │  Redis   │  │
│  │ (80 / 443) │  │  FastAPI    │  │  FastAPI │  │ (Docker) │  │
│  │            ├─▶│  :8000     │  │  :8001   │  │  :6379   │  │
│  │ SSL 종료   ├─▶│            │  │          │  │          │  │
│  │ 라우팅     │  │ 인증/인가   │  │ 예측     │  │ 작업 큐  │  │
│  └─────────────┘  │ CRUD       │  │ 스캐너   │  │ 캐시     │  │
│                   │ Swagger    │  │ 기술지표  │  └──────────┘  │
│                   └──────┬──────┘  └────┬─────┘               │
└──────────────────────────┼──────────────┼─────────────────────┘
                           │              │
           ┌───────────────▼──────────────▼───────────────┐
           │        RDS PostgreSQL (db.t3.micro)           │
           │             단일 AZ, 20GB gp3                  │
           └───────────────────────────────────────────────┘
```

### 인프라 비용

| 항목       | 기존 계획 (오버스펙)      | 채택 계획                    | 절감         |
| ---------- | ------------------------- | ---------------------------- | ------------ |
| 컴퓨팅     | ECS Fargate ~$80-100/월   | EC2 t3.medium ~$30/월        | ~$70/월      |
| DB         | RDS Multi-AZ ~$100-150/월 | RDS t3.micro 단일AZ ~$15/월  | ~$120/월     |
| Redis      | ElastiCache ~$18/월       | EC2 내 Docker ~$0            | ~$18/월      |
| 로드밸런서 | ALB ~$22/월               | Nginx on EC2 ~$0             | ~$22/월      |
| **합계**   | **~$220-300/월**          | **~$45/월**                  | **~$230/월** |

> **t3.small (2GB) 대신 t3.medium (4GB)을 선택한 이유**: ML 서비스(PyTorch CPU)와 Celery Worker가 S&P 500 스캔 시 메모리를 3~4GB까지 소비합니다. t3.small로는 OOM(Out of Memory) 위험이 높아 안정적인 데모 운영을 위해 t3.medium을 채택했습니다.

> AWS 프리 티어(EC2 t2.micro + RDS t3.micro, 12개월) 활용 시 **사실상 $0**에 운영 가능하나, ML 기능 사용 시 OOM 위험이 있으므로 권장하지 않습니다.

---

## 4. 기술 스택 및 선택 이유

| 레이어    | 기술                         | 선택 이유                                                                                    |
| --------- | ---------------------------- | -------------------------------------------------------------------------------------------- |
| Frontend  | Next.js 16 (TypeScript)      | App Router + SSR, Vercel 무료 배포, 기존 Streamlit UI를 대시보드로 재구현하기 위한 최적 선택 |
| UI        | Tailwind CSS + shadcn/ui     | 유틸리티 기반 스타일링으로 빠른 컴포넌트 구성                                                |
| 상태 관리 | Zustand + TanStack Query     | 전역 상태(Zustand)와 서버 캐시 상태(TanStack Query) 분리                                     |
| Backend   | FastAPI                      | 기존 Python ML 모듈과 동일한 생태계, 자동 Swagger 문서, async 지원                           |
| ORM       | SQLAlchemy 2.0 + Alembic     | 선언적 ORM + 마이그레이션 관리                                                               |
| 인증      | python-jose (JWT) + bcrypt   | FastAPI 생태계 표준, OAuth2PasswordBearer 통합                                               |
| ML        | XGBoost + PyTorch (LSTM)     | 기존 앙상블 예측 엔진 그대로 이전, CPU 모드로 EC2 호환                                       |
| 비동기 큐 | Celery + Redis               | S&P 500 배치 스캔 같은 장시간 작업을 백그라운드로 처리                                       |
| DB        | PostgreSQL 16 (RDS)          | 기존 JSON 평면 파일 → 관계형 DB로 마이그레이션, 동시성·쿼리 확보                             |
| 인프라    | EC2 + Docker Compose + Nginx | ECS/K8s 대비 설정 단순, 4인 팀 트래픽에 오버스펙 없음                                        |
| CI/CD     | GitHub Actions               | PR 자동 검증 + main 푸시 시 EC2 SSH 배포 자동화                                              |
| 의존성    | Poetry                       | 가상환경과 의존성 관리를 한 도구로 통일, `poetry.lock`으로 팀 환경 재현                      |

---

## 5. 프로젝트 구조

```
StockPriceAI/
├── frontend/                          # Next.js + TypeScript (Vercel 배포)
│   └── src/
│       ├── app/                       # App Router (dashboard, scanner, watchlist)
│       ├── components/                # charts/, stock/, scanner/, ui/
│       ├── hooks/
│       ├── lib/                       # api.ts, websocket.ts
│       ├── store/                     # Zustand 전역 상태
│       ├── test/                      # Vitest 테스트
│       └── types/
│
├── backend/                           # FastAPI — 인증/CRUD/Swagger (EC2 :8000)
│   └── app/
│       ├── api/v1/endpoints/          # auth, stocks, watchlist, scanner, predictions, websocket
│       ├── core/                      # config, security, database
│       ├── models/                    # SQLAlchemy ORM 모델
│       ├── schemas/                   # Pydantic 스키마
│       └── services/
│
├── ml/                                # FastAPI — ML 예측/스캐너/Celery (EC2 :8001)
│   └── app/
│       ├── api/v1/endpoints/          # predict, technical, sentiment, scanner
│       ├── models/                    # predictor.py, sentiment.py
│       ├── pipelines/                 # fetcher.py, scanner.py, technical.py
│       └── workers/                   # Celery 태스크 (scan_tasks.py)
│
├── infra/
│   ├── nginx/                         # 리버스 프록시 + SSL 설정
│   ├── postgres/                      # 로컬 DB 초기화 SQL
│   ├── scripts/                       # EC2 배포 스크립트 (deploy.sh)
│   └── docs/                          # AWS_SETUP.md
│
├── .github/workflows/
│   └── ci.yml                         # PR 검증 (lint + mypy + vitest + pytest + Docker 빌드)
│                                      # ※ cd.yml 미구현 — 현재 배포는 수동 진행
│
├── docker-compose.yml                 # 로컬 개발용 (PostgreSQL 로컬 실행)
├── docker-compose.prod.yml            # 프로덕션 오버라이드 (RDS URL, 포트 비노출)
├── .env.example
└── stockprice-main/                   # 원본 Streamlit 소스 (참조용)
```

---

## 6. 빠른 시작 (로컬)

### Prerequisites

- Docker & Docker Compose
- (백엔드/ML 코드 직접 수정 시) Python 3.11+, Poetry
- (프론트엔드 코드 직접 수정 시) Node.js 20+

### 실행

```bash
# 1. 클론 및 환경 변수 설정
git clone https://github.com/TakSakong/StockPriceAI.git
cd StockPriceAI
cp .env.example .env          # SECRET_KEY만 임의 값으로 변경

# 2. 전체 서비스 실행
docker compose up --build

# 3. 브라우저 확인
# Frontend : http://localhost:3000
# API Docs : http://localhost:8000/docs
# ML Docs  : http://localhost:8001/docs
```

### Python 가상환경 (코드 직접 수정 시)

```bash
# Poetry 설치 (1회)
curl -sSL https://install.python-poetry.org | python3 -

# backend
cd backend && poetry install && poetry shell

# ml
cd ../ml && poetry install && poetry shell
```

### Frontend 테스트 (Vitest)

```bash
cd frontend
npm test          # 단발 실행
npm run test:watch  # watch 모드
```

### 환경 변수 (.env)

| 변수           | 설명                                |
| -------------- | ----------------------------------- |
| `SECRET_KEY`   | JWT 서명 키 (임의 문자열)           |
| `DATABASE_URL` | 로컬: 자동 설정 / 프로덕션: RDS URL |
| `REDIS_URL`    | 로컬: 자동 설정                     |

---

## 7. 데이터베이스 설계

기존 `scan_cache.json` / `watchlist.json` 평면 파일을 아래 스키마로 마이그레이션합니다.

```sql
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE watchlist_items (
    id       UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id  UUID REFERENCES users(id) ON DELETE CASCADE,
    ticker   VARCHAR(20) NOT NULL,
    memo     TEXT,
    added_at TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (user_id, ticker)
);

CREATE TABLE predictions (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    ticker      VARCHAR(20) NOT NULL,
    signal      VARCHAR(10) NOT NULL,   -- BUY / SELL / HOLD
    up_prob     FLOAT NOT NULL,
    model_type  VARCHAR(50),            -- XGBoost / Ensemble
    complexity  FLOAT,                  -- RegimeDetector 복잡도
    xgb_weight  FLOAT,
    lstm_weight FLOAT,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE scan_jobs (
    id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    user_id     UUID REFERENCES users(id),
    status      VARCHAR(20) DEFAULT 'pending',
    total       INT,
    processed   INT DEFAULT 0,
    sector      VARCHAR(100),
    started_at  TIMESTAMPTZ,
    finished_at TIMESTAMPTZ,
    created_at  TIMESTAMPTZ DEFAULT NOW()
);

CREATE TABLE scan_results (
    id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    job_id          UUID REFERENCES scan_jobs(id),
    ticker          VARCHAR(20) NOT NULL,
    composite_score FLOAT,
    up_prob         FLOAT,
    signal          VARCHAR(10),
    sector          VARCHAR(100),
    est_upside      FLOAT,
    cached_at       TIMESTAMPTZ DEFAULT NOW()
);
```

---

## 8. API 설계

### 엔드포인트 목록

```
# 인증
POST   /api/v1/auth/register
POST   /api/v1/auth/login
POST   /api/v1/auth/refresh

# 종목
GET    /api/v1/stocks/{ticker}

# 관심종목
GET    /api/v1/watchlist
POST   /api/v1/watchlist
DELETE /api/v1/watchlist/{ticker}

# 예측 (ML 서비스)
POST   /api/v1/predict
GET    /api/v1/predictions/{ticker}
GET    /api/v1/technical/{ticker}
GET    /api/v1/sentiment/{ticker}

# 스캐너 (비동기 Celery 작업)
POST   /api/v1/scanner/jobs
GET    /api/v1/scanner/jobs/{job_id}
GET    /api/v1/scanner/jobs/{job_id}/results

# WebSocket (실시간 스캔 진행률)
WS     /ws/scanner/{scan_id}
```

### 응답 형식

```json
{
  "data": { "ticker": "AAPL", "signal": "BUY", "up_prob": 0.632 },
  "meta": { "model_type": "Ensemble", "complexity": 0.41 },
  "error": null
}
```

---

## 9. CI/CD 파이프라인

### CI — PR 검증

```
트리거: PR → develop, main  /  develop 브랜치 push
        (동일 브랜치 신규 커밋 시 이전 실행 자동 취소)

Frontend    : npm ci → type-check → lint → vitest → next build
Backend     : poetry install → ruff → mypy → pytest (커버리지 70%↑)
ML          : poetry install → ruff → mypy → pytest (커버리지 70%↑)
Docker      : backend/ml/frontend --target production 빌드 스모크 테스트
Integration : docker compose up --wait → test_local.sh --skip-ml (e2e 연동 검증)
```

### CD — EC2 자동 배포

> ⚠️ **현재 미구현**: `.github/workflows/cd.yml` 파일이 없습니다.  
> 현재는 EC2에 직접 SSH 접속 후 `infra/scripts/deploy.sh`를 수동 실행하는 방식으로 배포합니다.  
> 자동화 계획은 [docs/CICD_ROADMAP.md](docs/CICD_ROADMAP.md)를 참고하세요.

**목표 CD 플로우 (구현 예정)**
```
트리거: main 브랜치 push (PR 머지)

1. CI 통과 확인 (브랜치 보호 규칙)
2. EC2에 SSH 접속 (GitHub Secrets의 키 사용)
3. git pull origin main
4. docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
5. 헬스체크 확인 (curl /health)
```

#### GitHub Secrets

| 키            | 설명                                              |
| ------------- | ------------------------------------------------- |
| `EC2_HOST`    | EC2 퍼블릭 IP 또는 도메인                         |
| `EC2_SSH_KEY` | EC2 접속용 PEM 키 내용                            |
| `RDS_URL`     | `postgresql://user:pass@rds-endpoint:5432/dbname` |
| `SECRET_KEY`  | JWT 서명 키                                       |

---

## 10. 리팩토링 진행 현황

| Phase | 내용                                                   | 기간       | 상태    |
| ----- | ------------------------------------------------------ | ---------- | ------- |
| 1     | 기반 환경 구성 (Docker Compose + Poetry + 브랜치 전략) | Week 1-2   | ✅ 완료 |
| 2     | Backend API + JWT + RDS 연동 + Swagger                 | Week 3-5   | ✅ 완료 |
| 3     | ML 서비스 이전 + Celery + Redis                        | Week 6-8   | ✅ 완료 |
| 4     | Frontend (Next.js)                                     | Week 9-12  | ✅ 완료 |
| 5     | 테스트 + 코드 품질                                     | Week 13-14 | ✅ 완료 |
| 6     | EC2/RDS 배포 + CI/CD + Vercel                          | Week 15-16 | 🔜 진행 중 |

CI/CD 및 배포 로드맵: [docs/CICD_ROADMAP.md](docs/CICD_ROADMAP.md)  
기여 가이드: [CONTRIBUTING.md](CONTRIBUTING.md)

---

## 11. Lessons Learned & Challenges

### 가장 어려웠던 기술적 문제: Apple Silicon → Linux 컨테이너 이식

기존 ML 코드는 M4 Pro에 최적화된 코드가 깊숙이 박혀 있었습니다.

- **MPS(Metal Performance Shaders)**: PyTorch LSTM을 `device="mps"`로 실행하던 코드를 EC2(CPU only)에서 돌리려면 조건부 디바이스 선택 로직이 필요했습니다. 단순히 `device="cpu"`로 바꾸는 것 외에도 스캐너의 ThreadPoolExecutor 환경에서는 MPS 자체가 크래시를 일으켜 스캐너는 항상 CPU로 강제해야 한다는 제약을 발견했습니다.
- **XGBoost OMP 설정**: `nthread=P코어수`로 최적화된 설정이 EC2의 vCPU 수와 다르고, 스캐너 워커 간 OMP 스레드 경합이 발생해 스캐너에서는 `nthread=1`로 강제해야 했습니다.
- **float32 최적화**: M4의 NEON SIMD를 노린 `float32` 변환은 EC2에서도 메모리 절감 효과가 유효해 그대로 유지했습니다.

### 인프라 설계 교훈

초기 설계에서 ECS Fargate + ALB + ElastiCache + RDS Multi-AZ 조합을 검토했으나, 4인 팀 프로젝트에 **월 ~$230 절감** 가능한 EC2 + Docker Compose 조합으로 축소했습니다. 학교 프로젝트 규모에서 오버스펙 아키텍처는 운영 복잡도만 높인다는 것을 확인했습니다.

ML 서비스(PyTorch + XGBoost + Celery)의 메모리 요구량을 고려해 EC2는 t3.small(2GB) 대신 t3.medium(4GB)을 채택했으며, 단일 인스턴스에서 현실적으로 구현 불가한 Blue-Green 배포 대신 Rolling Restart 방식을 적용합니다.

---

## 12. 팀

| 역할         | 이름 | 담당                                         |
| ------------ | ---- | -------------------------------------------- |
| Frontend     | 지운 | Next.js 대시보드, 스캐너 UI, 관심종목 패널   |
| Backend      | 공탁 | FastAPI 인증/CRUD, RDS 연동, Swagger         |
| ML           | 진우 | ML 서비스 이전, Celery 배치 작업, 예측 엔진  |
| Infra/DevOps | 종윤 | EC2/RDS 설정, Docker Compose, GitHub Actions |

---

---

## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.

---

> ⚠️ 본 시스템은 **투자 참고용**입니다. AI 예측 결과는 미래 수익을 보장하지 않으며, 모든 투자 결정과 그에 따른 책임은 투자자 본인에게 있습니다.
