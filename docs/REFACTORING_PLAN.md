# StockPriceAI 웹 서비스 전환 리팩토링 계획

> **현재 상태**: Streamlit 단일 애플리케이션 (macOS Apple Silicon 전용)  
> **목표 상태**: 웹 서비스 (Docker Compose on EC2 + RDS + Vercel)

---

## 목차

1. [목표 아키텍처](#1-목표-아키텍처)
2. [디렉토리 구조](#2-디렉토리-구조)
3. [단계별 리팩토링 계획](#3-단계별-리팩토링-계획)
4. [서비스별 기술 스펙](#4-서비스별-기술-스펙)
5. [데이터베이스 설계](#5-데이터베이스-설계)
6. [API 설계 원칙](#6-api-설계-원칙)
7. [Docker Compose 구성](#7-docker-compose-구성)
8. [브랜치 전략](#8-브랜치-전략)
9. [커밋 컨벤션](#9-커밋-컨벤션)
10. [CI/CD 파이프라인](#10-cicd-파이프라인)
11. [AWS 배포 계획](#11-aws-배포-계획)
12. [협업 가이드](#12-협업-가이드)

---

## 1. 목표 아키텍처

```
┌─────────────────────────────────────────────────────────────────┐
│                          클라이언트                               │
│                    Next.js (TypeScript)                          │
│                   Vercel (무료 플랜)                              │
└───────────────────────────┬─────────────────────────────────────┘
                            │ HTTPS
┌───────────────────────────▼─────────────────────────────────────┐
│                   EC2 t3.small (단일 인스턴스)                    │
│                     Docker Compose                               │
│                                                                  │
│  ┌─────────────┐  ┌─────────────┐  ┌──────────┐  ┌──────────┐  │
│  │    Nginx    │  │   Backend   │  │    ML    │  │  Redis   │  │
│  │  (80/443)  │  │  FastAPI    │  │  FastAPI │  │ (Docker) │  │
│  │            ├─▶│  (8000)    │  │  (8001)  │  │  (6379)  │  │
│  │ SSL 종료   ├─▶│            │  │          │  │          │  │
│  │ 라우팅     │  │ - 인증/인가  │  │ - 예측   │  │ - 작업 큐 │  │
│  └─────────────┘  │ - CRUD     │  │ - 스캐너  │  │ - 캐시   │  │
│                   │ - Swagger  │  │ - 지표   │  └──────────┘  │
│                   └──────┬──────┘  └────┬─────┘               │
└──────────────────────────┼──────────────┼─────────────────────┘
                           │              │
           ┌───────────────▼──────────────▼───────────────┐
           │        RDS PostgreSQL (db.t3.micro)           │
           │           단일 AZ, 20GB gp3                   │
           └───────────────────────────────────────────────┘
```

### 비용 비교

| 항목       | 기존 계획 (오버스펙)      | 수정 계획                   | 절감         |
| ---------- | ------------------------- | --------------------------- | ------------ |
| 컴퓨팅     | ECS Fargate ~$80-100/월   | EC2 t3.small ~$15/월        | ~$80/월      |
| DB         | RDS Multi-AZ ~$100-150/월 | RDS t3.micro 단일AZ ~$15/월 | ~$120/월     |
| Redis      | ElastiCache ~$18/월       | EC2 내 Docker ~$0           | ~$18/월      |
| 로드밸런서 | ALB ~$22/월               | Nginx on EC2 ~$0            | ~$22/월      |
| IaC        | Terraform (학습비용)      | 불필요                      | -            |
| 프론트     | Vercel 무료               | Vercel 무료                 | -            |
| **합계**   | **~$220-300/월**          | **~$30/월**                 | **~$250/월** |

> **AWS 프리 티어 활용 시**: EC2 t2.micro(750h/월) + RDS t3.micro(750h/월)가 12개월간 무료  
> → 첫 1년은 **사실상 $0**에 운영 가능 (학기 프로젝트 기간에 충분)

### 핵심 단순화 원칙

| 제거 항목    | 이유                                                  |
| ------------ | ----------------------------------------------------- |
| ECS Fargate  | Docker Compose on EC2로 대체, 관리가 훨씬 단순        |
| ALB          | Nginx on EC2로 대체, 4인 트래픽에 ALB 불필요          |
| ElastiCache  | Redis를 EC2 Docker 컨테이너로 실행, 비용 Zero         |
| RDS Multi-AZ | 학교 프로젝트에 이중화 불필요, 단일 AZ로 충분         |
| Terraform    | 수동 EC2 설정으로 충분, IaC 학습비용 대비 효과 낮음   |
| Kubernetes   | Docker Compose로 충분, 4인 팀에 K8s는 극단적 오버스펙 |
| Staging 환경 | local ↔ production 2단계로 충분                       |

---

## 2. 디렉토리 구조

```
StockPriceAI/
├── frontend/                          # Next.js + TypeScript
│   ├── src/
│   │   ├── app/
│   │   │   ├── (dashboard)/
│   │   │   │   ├── page.tsx
│   │   │   │   ├── scanner/page.tsx
│   │   │   │   └── watchlist/page.tsx
│   │   │   ├── layout.tsx
│   │   │   └── globals.css
│   │   ├── components/
│   │   │   ├── charts/
│   │   │   ├── stock/
│   │   │   ├── scanner/
│   │   │   └── ui/
│   │   ├── hooks/
│   │   ├── lib/
│   │   │   ├── api.ts
│   │   │   └── websocket.ts
│   │   ├── store/
│   │   └── types/
│   ├── public/
│   ├── package.json
│   ├── tsconfig.json
│   └── Dockerfile
│
├── backend/                           # FastAPI (비즈니스 로직)
│   ├── app/
│   │   ├── api/v1/
│   │   │   ├── endpoints/
│   │   │   │   ├── auth.py
│   │   │   │   ├── stocks.py
│   │   │   │   ├── watchlist.py
│   │   │   │   ├── scanner.py
│   │   │   │   └── predictions.py
│   │   │   └── router.py
│   │   ├── core/
│   │   │   ├── config.py
│   │   │   ├── security.py
│   │   │   └── database.py
│   │   ├── models/
│   │   ├── schemas/
│   │   ├── services/
│   │   └── main.py
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
│
├── ml/                                # FastAPI (ML 서비스)
│   ├── app/
│   │   ├── api/v1/
│   │   │   ├── endpoints/
│   │   │   │   ├── predict.py
│   │   │   │   ├── technical.py
│   │   │   │   ├── sentiment.py
│   │   │   │   └── scanner.py
│   │   │   └── router.py
│   │   ├── core/config.py
│   │   ├── models/
│   │   │   ├── predictor.py
│   │   │   ├── xgboost_model.py
│   │   │   └── lstm_model.py
│   │   ├── services/
│   │   │   ├── fetcher.py
│   │   │   ├── technical.py
│   │   │   ├── sentiment.py
│   │   │   ├── scanner.py
│   │   │   └── charts.py
│   │   ├── workers/
│   │   │   └── scan_tasks.py
│   │   └── main.py
│   ├── tests/
│   ├── Dockerfile
│   └── pyproject.toml
│
├── infra/                             # 배포 및 CI/CD (인프라 전반)
│   ├── nginx/
│   │   ├── nginx.conf                 # 리버스 프록시 + SSL 설정
│   │   └── Dockerfile
│   ├── postgres/
│   │   └── init.sql                   # 로컬 DB 초기화
│   ├── scripts/
│   │   └── deploy.sh                  # EC2 배포 스크립트 (git pull + docker compose up)
│   └── docs/
│       └── AWS_SETUP.md               # EC2/RDS 수동 설정 가이드
│
├── .github/
│   └── workflows/
│       ├── ci.yml                     # PR 검증
│       └── cd.yml                     # main 병합 시 EC2 자동 배포 (SSH)
│
├── docker-compose.yml                 # 로컬 개발용
├── docker-compose.prod.yml            # 프로덕션 오버라이드 (RDS URL, 볼륨 등)
├── .env.example
└── README.md
```

---

## 3. 단계별 리팩토링 계획

### Phase 1 — 기반 환경 구성 (1~2주)

**목표**: 팀 전체가 동일한 환경에서 개발할 수 있는 기반 마련

#### 1-1. 모노레포 구조 초기화

- [ ] 루트 디렉토리 재구성
- [ ] `.env.example` 작성
- [ ] 루트 `README.md` 업데이트

#### 1-2. Python 의존성 관리 (Poetry + 가상환경)

Poetry는 의존성 관리와 가상환경(virtualenv)을 함께 처리합니다.  
`poetry install` 시 자동으로 프로젝트 전용 가상환경을 생성하며, 팀원 전원이 동일한 환경을 재현할 수 있습니다.

```bash
# Poetry 설치 (팀원 1회)
curl -sSL https://install.python-poetry.org | python3 -

# backend 가상환경 생성 및 의존성 설치
cd backend
poetry init
poetry add fastapi uvicorn sqlalchemy psycopg2-binary alembic \
           pydantic-settings python-jose bcrypt
poetry shell          # 가상환경 활성화
poetry env info       # 가상환경 경로 확인

# ml 가상환경 생성 및 의존성 설치
cd ../ml
poetry init
poetry add fastapi uvicorn pandas numpy scikit-learn xgboost \
           yfinance vaderSentiment plotly celery redis
poetry shell
```

> **가상환경 위치**: 기본적으로 `~/.cache/pypoetry/virtualenvs/`에 생성됩니다.  
> 프로젝트 내부에 두려면 `poetry config virtualenvs.in-project true` 설정 후 `.venv/` 경로에 생성됩니다.

- [ ] `backend/pyproject.toml` 작성
- [ ] `ml/pyproject.toml` 작성
- [ ] 기존 `requirements.txt` → Poetry 마이그레이션
- [ ] `poetry.lock` 커밋
- [ ] `.venv/` `.gitignore`에 추가

#### 1-3. Docker Compose 로컬 환경

- [ ] `docker-compose.yml` 작성 (backend, ml, postgres, redis, nginx)
- [ ] 각 서비스 `Dockerfile` 작성 (개발용 hot-reload)
- [ ] `infra/postgres/init.sql` 작성
- [ ] `docker compose up` 원커맨드 실행 확인

#### 1-4. 브랜치 전략 및 컨벤션

- [ ] `CONTRIBUTING.md` 작성
- [ ] GitHub 브랜치 보호 규칙 (main, develop)
- [ ] PR 템플릿

---

### Phase 2 — 백엔드 API 개발 (2~3주)

**목표**: FastAPI 기반 REST API + RDS PostgreSQL 연동

#### 2-1. 데이터베이스 마이그레이션

- [ ] SQLAlchemy ORM 모델 정의 (`User`, `Watchlist`, `Prediction`, `ScanResult`)
- [ ] Alembic 마이그레이션 설정
- [ ] 초기 마이그레이션 생성 및 적용

#### 2-2. 인증 시스템 (JWT)

- [ ] 회원가입/로그인 (`/api/v1/auth/register`, `/login`, `/refresh`)
- [ ] bcrypt 비밀번호 해싱
- [ ] JWT 발급/검증 미들웨어

#### 2-3. 핵심 API 엔드포인트

- [ ] 관심종목 CRUD (`/api/v1/watchlist`)
- [ ] 종목 검색/조회 (`/api/v1/stocks/{ticker}`)
- [ ] 예측 결과 조회 (`/api/v1/predictions/{ticker}`)
- [ ] 스캔 작업 요청/상태 조회 (`/api/v1/scanner`)

#### 2-4. Swagger UI

- [ ] FastAPI 자동 문서 활성화 (`/docs`, `/redoc`)
- [ ] 모든 엔드포인트에 `summary`, `response_model` 명시
- [ ] Bearer Token 인증 스키마 연동

#### 2-5. WebSocket (실시간 스캔 진행률)

- [ ] `/ws/scanner/{scan_id}` 엔드포인트
- [ ] 연결 관리 매니저 구현

---

### Phase 3 — ML 서비스 이전 (2~3주)

**목표**: 기존 Python 모듈을 독립적인 FastAPI 서비스로 분리

#### 3-1. 기존 코드 이전

- [ ] `fetcher.py` → `ml/app/services/fetcher.py` (macOS 의존성 제거)
- [ ] `technical.py` → `ml/app/services/technical.py`
- [ ] `sentiment.py` → `ml/app/services/sentiment.py`
- [ ] `predictor.py` → `ml/app/models/predictor.py`
- [ ] `scanner.py` → `ml/app/services/scanner.py`
- [ ] `charts.py` → `ml/app/services/charts.py`

#### 3-2. ML API 엔드포인트

- [ ] `POST /api/v1/predict` — 단일 종목 예측
- [ ] `POST /api/v1/scanner/start` — 배치 스캔 시작 (비동기)
- [ ] `GET /api/v1/scanner/status/{job_id}` — 작업 상태
- [ ] `GET /api/v1/technical/{ticker}` — 기술적 지표
- [ ] `GET /api/v1/sentiment/{ticker}` — 감성 분석

#### 3-3. Celery + Redis 비동기 작업 큐

- [ ] S&P 500 배치 스캔 Celery 태스크 구현
- [ ] Redis (Docker 컨테이너)를 브로커/결과 백엔드로 설정
- [ ] 기존 `scan_cache.json` → Redis 캐시 대체
- [ ] WebSocket 진행률 콜백

#### 3-4. 플랫폼 의존성 제거

- [ ] Apple Silicon 특화 설정 → 환경 변수 기반 범용 설정
- [ ] MPS → CPU 모드 (EC2는 GPU 없음)
- [ ] 컨테이너 환경 동작 검증

---

### Phase 4 — 프론트엔드 개발 (3~4주)

**목표**: Next.js + TypeScript로 Streamlit UI 기능 재구현

#### 4-1. 프로젝트 초기화

- [ ] `create-next-app` (TypeScript + Tailwind + App Router)
- [ ] shadcn/ui 설정
- [ ] Zustand + TanStack Query 설정
- [ ] 다크 테마 설정

#### 4-2. 핵심 페이지 구현

- [ ] **메인 대시보드** (`/`) — 종목 검색 + 분석 뷰 (7탭)
- [ ] **스캐너 페이지** (`/scanner`) — S&P 500 배치 스캔 + 실시간 진행률
- [ ] **관심종목 페이지** (`/watchlist`) — 종목 관리 + 미니 차트

#### 4-3. 차트 + WebSocket

- [ ] Plotly.js 연동 (캔들스틱, MACD, 볼린저 밴드)
- [ ] WebSocket 스캔 진행률 연동

#### 4-4. 타입 안전성

- [ ] openapi-typescript로 백엔드 타입 자동 생성
- [ ] strict TypeScript 설정

---

### Phase 5 — 테스트 및 품질 관리 (1~2주)

**목표**: 서비스 간 연동 검증 + 최소한의 테스트 커버리지

#### 5-1. 백엔드/ML 테스트

- [ ] pytest + httpx 통합 테스트
- [ ] 핵심 ML 로직 단위 테스트
- [ ] 커버리지 목표: 60% 이상

#### 5-2. 코드 품질 도구

- [ ] **Python**: ruff (lint + formatter) + mypy
- [ ] **TypeScript**: ESLint + Prettier
- [ ] pre-commit 훅

---

### Phase 6 — CI/CD 및 AWS 배포 (1주)

**목표**: GitHub Actions 자동화 + EC2/RDS 배포

#### 6-1. EC2 초기 설정 (수동, 1회)

```bash
# EC2 접속 후 초기 설정
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker ubuntu

# 앱 디렉토리 준비
git clone https://github.com/TakSakong/StockPriceAI.git /app
cd /app && cp .env.example .env.prod
# .env.prod에 RDS 주소, SECRET_KEY 등 입력
```

#### 6-2. GitHub Actions (SSH 자동 배포)

```yaml
# .github/workflows/cd.yml
# 트리거: main 브랜치 push
#
# 1. CI 통과 확인
# 2. EC2에 SSH 접속
# 3. git pull + docker compose up --build -d
```

- [ ] GitHub Secrets에 `EC2_HOST`, `EC2_SSH_KEY` 등록
- [ ] `infra/scripts/deploy.sh` 작성

#### 6-3. Nginx SSL 설정 (Let's Encrypt)

```bash
# EC2에서 Certbot으로 무료 SSL 발급
sudo apt install -y certbot
sudo certbot certonly --standalone -d yourdomain.com
```

- [ ] `infra/nginx/nginx.conf` 작성 (HTTP → HTTPS 리다이렉트 + 라우팅)
- [ ] SSL 인증서 자동 갱신 설정 (cron)

#### 6-4. Vercel 배포 (Frontend)

- [ ] Vercel GitHub 연동 (main 브랜치 자동 배포)
- [ ] 환경변수 설정 (`NEXT_PUBLIC_API_URL` = EC2 도메인)

---

## 4. 서비스별 기술 스펙

### Frontend

| 항목       | 선택                     |
| ---------- | ------------------------ |
| 프레임워크 | Next.js 14+ (App Router) |
| 언어       | TypeScript               |
| 스타일     | Tailwind CSS + shadcn/ui |
| 상태 관리  | Zustand                  |
| 서버 상태  | TanStack Query           |
| 차트       | Plotly.js                |
| 배포       | Vercel 무료 플랜         |

### Backend

| 항목         | 선택                       |
| ------------ | -------------------------- |
| 프레임워크   | FastAPI                    |
| ORM          | SQLAlchemy 2.0             |
| 마이그레이션 | Alembic                    |
| 인증         | python-jose (JWT) + bcrypt |
| 의존성 관리  | Poetry                     |

### ML 서비스

| 항목        | 선택                                 |
| ----------- | ------------------------------------ |
| 프레임워크  | FastAPI                              |
| ML          | scikit-learn, XGBoost, PyTorch (CPU) |
| 비동기 큐   | Celery + Redis (Docker)              |
| 의존성 관리 | Poetry                               |

### 인프라

| 항목          | 선택                              | 비용                        |
| ------------- | --------------------------------- | --------------------------- |
| 컴퓨팅        | EC2 t3.small (Docker Compose)     | ~$15/월 (프리티어: $0)      |
| DB            | RDS PostgreSQL db.t3.micro 단일AZ | ~$15/월 (프리티어: $0)      |
| Redis         | Docker 컨테이너 (EC2 내부)        | $0                          |
| 리버스 프록시 | Nginx (Docker 컨테이너)           | $0                          |
| SSL           | Let's Encrypt (Certbot)           | $0                          |
| 프론트 배포   | Vercel 무료 플랜                  | $0                          |
| CI/CD         | GitHub Actions                    | $0                          |
| **합계**      |                                   | **~$30/월 (프리티어: ~$0)** |

---

## 5. 데이터베이스 설계

```sql
CREATE TABLE users (
    id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
    email         VARCHAR(255) UNIQUE NOT NULL,
    password_hash VARCHAR(255) NOT NULL,
    created_at    TIMESTAMPTZ DEFAULT NOW(),
    updated_at    TIMESTAMPTZ DEFAULT NOW()
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
    signal      VARCHAR(10) NOT NULL,
    up_prob     FLOAT NOT NULL,
    model_type  VARCHAR(50),
    complexity  FLOAT,
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

## 6. API 설계 원칙

### RESTful 규칙

```
GET    /api/v1/stocks/{ticker}
POST   /api/v1/predictions
GET    /api/v1/predictions/{ticker}
GET    /api/v1/watchlist
POST   /api/v1/watchlist
DELETE /api/v1/watchlist/{ticker}
POST   /api/v1/scanner/jobs
GET    /api/v1/scanner/jobs/{job_id}
GET    /api/v1/scanner/jobs/{job_id}/results
```

### 응답 형식

```json
{
  "data": { ... },
  "meta": { "page": 1, "total": 100 },
  "error": null
}
```

---

## 7. Docker Compose 구성

```yaml
# docker-compose.yml (로컬 개발용 — PostgreSQL 로컬 실행)
version: "3.9"

services:
  nginx:
    build: ./infra/nginx
    ports:
      - "80:80"
    depends_on: [frontend, backend, ml]

  frontend:
    build:
      context: ./frontend
      target: development
    ports:
      - "3000:3000"
    volumes:
      - ./frontend/src:/app/src
    environment:
      - NEXT_PUBLIC_API_URL=http://localhost/api

  backend:
    build:
      context: ./backend
      target: development
    ports:
      - "8000:8000"
    volumes:
      - ./backend/app:/app/app
    environment:
      - DATABASE_URL=postgresql://stockai:stockai@postgres:5432/stockai
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY}
      - ML_SERVICE_URL=http://ml:8001
    depends_on: [postgres, redis]

  ml:
    build:
      context: ./ml
      target: development
    ports:
      - "8001:8001"
    volumes:
      - ./ml/app:/app/app
    environment:
      - REDIS_URL=redis://redis:6379/1
      - CELERY_BROKER_URL=redis://redis:6379/2
    depends_on: [redis]

  celery_worker:
    build:
      context: ./ml
      target: development
    command: celery -A app.workers.celery_app worker --loglevel=info
    environment:
      - CELERY_BROKER_URL=redis://redis:6379/2
      - REDIS_URL=redis://redis:6379/1
    depends_on: [redis]

  postgres:
    image: postgres:16-alpine
    ports:
      - "5432:5432"
    environment:
      - POSTGRES_USER=stockai
      - POSTGRES_PASSWORD=stockai
      - POSTGRES_DB=stockai
    volumes:
      - postgres_data:/var/lib/postgresql/data
      - ./infra/postgres/init.sql:/docker-entrypoint-initdb.d/init.sql

  redis:
    image: redis:7-alpine
    ports:
      - "6379:6379"
    volumes:
      - redis_data:/data

volumes:
  postgres_data:
  redis_data:
```

```yaml
# docker-compose.prod.yml (프로덕션 오버라이드 — RDS 사용, 포트 노출 제거)
version: "3.9"

services:
  frontend:
    build:
      context: ./frontend
      target: production # 빌드 최적화 스테이지

  backend:
    environment:
      - DATABASE_URL=${RDS_URL} # RDS 연결 문자열
      - REDIS_URL=redis://redis:6379/0
      - SECRET_KEY=${SECRET_KEY}
      - ML_SERVICE_URL=http://ml:8001
    ports: [] # 외부 포트 비노출 (Nginx 경유)

  ml:
    environment:
      - REDIS_URL=redis://redis:6379/1
      - CELERY_BROKER_URL=redis://redis:6379/2
    ports: []

  postgres: # 프로덕션에서는 제외 (RDS 사용)
    profiles: ["local"] # docker compose --profile local up 으로만 실행


# 실행 명령:
# docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

---

## 8. 브랜치 전략

```
main          ─── 프로덕션 배포 전용. 직접 push 금지.
  │
develop       ─── 통합 개발 브랜치.
  │
  ├── feature/FE-stock-chart
  ├── feature/BE-watchlist-api
  └── feature/ML-celery-scanner
```

### 브랜치 명명 규칙

```
{type}/{scope}-{short-description}

type: feature / fix / refactor / chore / docs
scope: FE / BE / ML / INFRA

예시:
  feature/FE-realtime-scan-progress
  feature/BE-jwt-auth
  fix/ML-predictor-null-check
  chore/INFRA-nginx-ssl-config
```

### 브랜치 보호 규칙

| 브랜치    | 규칙                                |
| --------- | ----------------------------------- |
| `main`    | PR 필수 + 리뷰어 1명 승인 + CI 통과 |
| `develop` | PR 필수 + CI 통과                   |

---

## 9. 커밋 컨벤션

**Conventional Commits** 사양을 따릅니다.

```
{type}({scope}): {subject}
```

| Type       | 사용 시점           |
| ---------- | ------------------- |
| `feat`     | 새로운 기능         |
| `fix`      | 버그 수정           |
| `refactor` | 기능 변경 없는 개선 |
| `test`     | 테스트              |
| `docs`     | 문서                |
| `chore`    | 빌드/패키지         |
| `ci`       | CI/CD 설정          |

Scope: `fe` | `be` | `ml` | `db` | `infra` | `ci`

---

## 10. CI/CD 파이프라인

### CI — Pull Request 검증

```
트리거: PR → develop, main

Frontend: npm ci → type-check → lint → build
Backend:  poetry install → ruff → pytest
ML:       poetry install → ruff → pytest
```

### CD — EC2 자동 배포

```
트리거: main 브랜치 push

1. CI 통과 확인
2. EC2에 SSH 접속 (GitHub Secrets의 키 사용)
3. git pull origin main
4. docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
5. 헬스체크 확인 (curl /health)
```

```yaml
# .github/workflows/cd.yml 핵심 부분
- name: Deploy to EC2
  uses: appleboy/ssh-action@v1
  with:
    host: ${{ secrets.EC2_HOST }}
    username: ubuntu
    key: ${{ secrets.EC2_SSH_KEY }}
    script: |
      cd /app
      git pull origin main
      docker compose -f docker-compose.yml -f docker-compose.prod.yml \
        up --build -d --remove-orphans
```

### 시크릿 관리

```
GitHub Secrets:
  EC2_HOST          # EC2 퍼블릭 IP 또는 도메인
  EC2_SSH_KEY       # EC2 접속용 PEM 키 내용
  RDS_URL           # postgresql://user:pass@rds-endpoint:5432/dbname
  SECRET_KEY        # JWT 서명 키
```

---

## 11. AWS 배포 계획

### 인프라 구성 (콘솔에서 수동 설정, 1회)

```
AWS 계정
  │
  ├── EC2 t3.small (또는 t2.micro 프리티어)
  │   ├── Ubuntu 22.04 LTS
  │   ├── Docker + Docker Compose
  │   ├── Elastic IP (고정 IP, 무료)
  │   └── 보안 그룹: 22(SSH), 80(HTTP), 443(HTTPS) 허용
  │
  └── RDS PostgreSQL db.t3.micro
      ├── 단일 AZ (Multi-AZ 불필요)
      ├── 20GB gp3 스토리지
      ├── 퍼블릭 액세스: 비활성화
      └── 보안 그룹: EC2에서만 5432 허용
```

### EC2 인스턴스 선택

| 상황                        | 인스턴스            | 비용    |
| --------------------------- | ------------------- | ------- |
| 첫 12개월 (프리티어)        | t2.micro (1GB RAM)  | $0/월   |
| 이후 또는 ML 메모리 부족 시 | t3.small (2GB RAM)  | ~$15/월 |
| ML 모델이 너무 무거울 경우  | t3.medium (4GB RAM) | ~$30/월 |

> **RAM 주의**: XGBoost + LSTM 모델을 함께 올리면 1GB는 부족할 수 있습니다.  
> 프리티어 기간에는 t2.micro로 시작하고, 메모리 부족 시 t3.small로 업그레이드하세요.

### RDS 설정

```
엔진: PostgreSQL 16
인스턴스: db.t3.micro (프리티어)
스토리지: 20GB gp3
백업: 자동 백업 7일 (무료)
Multi-AZ: 비활성화
퍼블릭 액세스: 비활성화 (EC2에서만 접속)
```

### Nginx 설정 (EC2 내 컨테이너)

```nginx
# infra/nginx/nginx.conf
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name yourdomain.com;

    ssl_certificate     /etc/letsencrypt/live/yourdomain.com/fullchain.pem;
    ssl_certificate_key /etc/letsencrypt/live/yourdomain.com/privkey.pem;

    location /api/ {
        proxy_pass http://backend:8000;
    }

    location /ml/ {
        proxy_pass http://ml:8001;
    }

    location /ws/ {
        proxy_pass http://backend:8000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
    }
}
```

### 도메인 (선택)

- **무료**: EC2 Elastic IP를 `NEXT_PUBLIC_API_URL`에 직접 사용 (IP 변경 걱정 없음)
- **유료**: 도메인 구매 후 Route 53 또는 외부 DNS에 A 레코드 등록 (~$12/년)
- SSL은 도메인이 있어야 Let's Encrypt 발급 가능. IP만 쓸 경우 자체 서명 인증서 사용

### 환경 구성

| 환경           | 인프라                               | 배포 트리거                     |
| -------------- | ------------------------------------ | ------------------------------- |
| **local**      | Docker Compose (로컬 Postgres/Redis) | 수동                            |
| **production** | EC2 + RDS + Vercel                   | main push 자동 (GitHub Actions) |

---

## 12. 협업 가이드

### 팀 역할 분담

| 역할 | 담당 영역                                   |
| ---- | ------------------------------------------- |
| 지운 | Frontend (Next.js)                          |
| 공탁 | Backend API (FastAPI + JWT + RDS)           |
| 진우 | ML 서비스 (모델 이전 + Celery)              |
| 종윤 | 배포, CI/CD (EC2/RDS 설정 + GitHub Actions) |

### 개발 환경 세팅 (신규 팀원)

```bash
# 1. 저장소 클론
git clone https://github.com/TakSakong/StockPriceAI.git
cd StockPriceAI

# 2. 환경 변수 설정
cp .env.example .env
# SECRET_KEY만 임의의 문자열로 채우면 로컬 실행 가능

# 3. Python 가상환경 세팅 (백엔드 코드 직접 수정할 팀원만)
cd backend && poetry install && poetry shell   # backend 가상환경 활성화
cd ../ml    && poetry install && poetry shell   # ml 가상환경 활성화
cd ..

# 4. 전체 서비스 실행 (Docker 사용 시 가상환경 불필요)
docker compose up --build

# 브라우저에서 확인
# Frontend:  http://localhost:3000
# API Docs:  http://localhost:8000/docs
# ML Docs:   http://localhost:8001/docs
```

### Swagger UI 활용

- 로컬: `http://localhost:8000/docs`
- 프로덕션: `https://yourdomain.com/api/docs`
- **Authorize** 버튼 → `/login` 응답의 JWT 토큰 입력 후 인증 테스트

---

## 우선순위 요약

```
Week 1-2   Phase 1  기반 환경 (Docker Compose + Poetry + 브랜치 전략)
Week 3-5   Phase 2  Backend API + RDS 연동 + JWT 인증 + Swagger
Week 6-8   Phase 3  ML 서비스 이전 + Celery + Redis
Week 9-12  Phase 4  Frontend (Next.js)
Week 13-14 Phase 5  테스트 + 코드 품질
Week 15-16 Phase 6  EC2/RDS 설정 + CI/CD + Vercel 배포
```

> **권장 시작점**: Phase 1의 Docker Compose 환경을 팀 전체가 함께 실행해보는 것부터 시작하세요.  
> EC2/RDS는 Phase 6까지 건드릴 필요 없습니다. 로컬 Docker로 충분합니다.
