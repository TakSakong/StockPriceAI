# 로컬 통합 테스트 가이드

> Phase 4까지 구현 완료된 상태에서 로컬 Docker Compose 환경으로 전체 서비스를 검증하는 절차입니다.

---

## 목차

1. [사전 준비](#1-사전-준비)
2. [환경 시작](#2-환경-시작)
3. [헬스체크](#3-헬스체크)
4. [백엔드 API 테스트](#4-백엔드-api-테스트-포트-8000)
5. [ML 서비스 테스트](#5-ml-서비스-테스트-포트-8001)
6. [WebSocket 테스트](#6-websocket-테스트)
7. [프론트엔드 테스트](#7-프론트엔드-테스트-포트-3000)
8. [서비스 간 연동 테스트](#8-서비스-간-연동-테스트)
9. [문제 해결](#9-문제-해결)

---

## 1. 사전 준비

### 필수 도구

```bash
docker --version          # 24.x 이상
docker compose version    # v2.x 이상 (docker-compose 아님)
```

### 환경 변수 설정

```bash
cd /path/to/StockPriceAI

cp .env.example .env

# SECRET_KEY를 임의의 문자열로 교체 (필수)
# macOS
sed -i '' 's/change-me-before-running/'"$(openssl rand -hex 32)"'/' .env

# 또는 직접 .env 열어서 SECRET_KEY= 값을 아무 문자열로 수정
```

`.env` 최종 확인 (로컬 기본값):

```
DATABASE_URL=postgresql://stockai:stockai@postgres:5432/stockai
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/2
SECRET_KEY=<임의의 문자열>
ML_SERVICE_URL=http://ml:8001
NEXT_PUBLIC_API_URL=http://localhost/api
NEXT_PUBLIC_ML_URL=http://localhost/ml
NEXT_PUBLIC_WS_URL=ws://localhost
```

---

## 2. 환경 시작

### 최초 빌드 및 실행

```bash
# 전체 서비스 빌드 + 실행 (처음에는 5~10분 소요)
docker compose up --build -d

# 로그 실시간 확인 (Ctrl+C로 종료, 컨테이너는 계속 실행)
docker compose logs -f
```

### 서비스별 로그 확인

```bash
docker compose logs -f backend
docker compose logs -f ml
docker compose logs -f celery_worker
docker compose logs -f frontend
docker compose logs -f postgres
```

### 재시작 (코드 변경 없이)

```bash
docker compose restart
```

### 코드 변경 후 재빌드

```bash
# 특정 서비스만
docker compose up --build -d backend
docker compose up --build -d ml frontend
```

### 종료

```bash
docker compose down              # 컨테이너만 제거 (DB 데이터 보존)
docker compose down -v           # 컨테이너 + 볼륨 전체 제거 (DB 초기화 포함)
```

---

## 3. 헬스체크

모든 서비스가 정상인지 먼저 확인합니다.

```bash
# 컨테이너 상태 확인 (State가 모두 running이어야 함)
docker compose ps

# 헬스 엔드포인트 일괄 확인
curl -s http://localhost:8000/health | python3 -m json.tool
curl -s http://localhost:8001/health | python3 -m json.tool

# 기대 응답
# {"status": "ok", "service": "backend"}
# {"status": "ok", "service": "ml"}
```

```bash
# Nginx 라우팅 확인 (포트 80 경유)
curl -s http://localhost/api/health | python3 -m json.tool   # → backend
curl -s http://localhost/ml/health  | python3 -m json.tool   # → ml
```

```bash
# PostgreSQL 접속 확인
docker compose exec postgres psql -U stockai -d stockai -c "\dt"

# 기대 출력: users, watchlist_items, predictions, scan_jobs, scan_results 테이블 목록
```

```bash
# Redis 확인
docker compose exec redis redis-cli ping
# 기대 출력: PONG
```

---

## 4. 백엔드 API 테스트 (포트 8000)

Swagger UI를 열거나 아래 curl 명령으로 직접 테스트합니다.

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc

### 4-1. 회원가입

```bash
curl -s -X POST http://localhost:8000/api/v1/auth/register \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "testpass123"}' \
  | python3 -m json.tool

# 기대 응답 (201)
# {
#   "id": "...",
#   "email": "test@example.com",
#   "created_at": "..."
# }
```

### 4-2. 로그인 (JWT 발급)

```bash
TOKEN=$(curl -s -X POST http://localhost:8000/api/v1/auth/login \
  -H "Content-Type: application/json" \
  -d '{"email": "test@example.com", "password": "testpass123"}' \
  | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['access_token'])")

echo "TOKEN: $TOKEN"
```

### 4-3. 내 정보 조회

```bash
curl -s http://localhost:8000/api/v1/auth/me \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -m json.tool
```

### 4-4. 관심종목 CRUD

```bash
# 추가
curl -s -X POST http://localhost:8000/api/v1/watchlist \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ticker": "AAPL", "memo": "애플 테스트"}' \
  | python3 -m json.tool

# 목록 조회
curl -s http://localhost:8000/api/v1/watchlist \
  -H "Authorization: Bearer $TOKEN" \
  | python3 -m json.tool

# 메모 수정
curl -s -X PATCH http://localhost:8000/api/v1/watchlist/AAPL \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"memo": "수정된 메모"}' \
  | python3 -m json.tool

# 삭제
curl -s -X DELETE http://localhost:8000/api/v1/watchlist/AAPL \
  -H "Authorization: Bearer $TOKEN" \
  -o /dev/null -w "HTTP %{http_code}\n"
# 기대: HTTP 204
```

### 4-5. 스캔 작업 시작 (백엔드 → ML 연동)

```bash
JOB=$(curl -s -X POST http://localhost:8000/api/v1/scanner/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sector": "Technology"}' \
  | python3 -m json.tool)

echo "$JOB"
JOB_ID=$(echo "$JOB" | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")
echo "Job ID: $JOB_ID"
```

---

## 5. ML 서비스 테스트 (포트 8001)

- **Swagger UI**: http://localhost:8001/docs

### 5-1. 단일 종목 예측

> ⚠️ 실제 yfinance 데이터를 받아와 ML 모델을 실행합니다. 인터넷 연결이 필요하며 **30초~2분** 소요될 수 있습니다.

```bash
curl -s -X POST http://localhost:8001/api/v1/predict \
  -H "Content-Type: application/json" \
  -d '{
    "ticker": "AAPL",
    "period_days": 400,
    "include_sentiment": false,
    "force_lstm": false
  }' \
  | python3 -m json.tool

# 기대 응답
# {
#   "ticker": "AAPL",
#   "signal": "BUY" | "HOLD" | "SELL",
#   "up_probability": 0.63,
#   "down_probability": 0.37,
#   "confidence": 0.63,
#   "model": "xgboost" | "ensemble",
#   "training_metrics": {...},
#   "technical_summary": {...}
# }
```

### 5-2. 기술적 지표

```bash
curl -s http://localhost:8001/api/v1/technical/AAPL \
  | python3 -m json.tool
```

### 5-3. 감성 분석

```bash
curl -s http://localhost:8001/api/v1/sentiment/AAPL \
  | python3 -m json.tool
```

### 5-4. S&P 500 배치 스캔 (Celery 비동기)

```bash
# 스캔 시작 (소규모 테스트: 5개 종목)
SCAN=$(curl -s -X POST http://localhost:8001/api/v1/scanner/start \
  -H "Content-Type: application/json" \
  -d '{
    "tickers": ["AAPL", "MSFT", "GOOGL", "AMZN", "NVDA"],
    "max_workers": 2,
    "force_refresh": false,
    "period_days": 400
  }' \
  | python3 -m json.tool)

echo "$SCAN"
SCAN_JOB_ID=$(echo "$SCAN" | python3 -c "import sys,json; print(json.load(sys.stdin)['job_id'])")

# 상태 폴링
curl -s http://localhost:8001/api/v1/scanner/status/$SCAN_JOB_ID | python3 -m json.tool

# S&P 500 종목 목록 확인
curl -s http://localhost:8001/api/v1/scanner/tickers | python3 -m json.tool | head -20

# 캐시 통계
curl -s http://localhost:8001/api/v1/scanner/cache/stats | python3 -m json.tool
```

---

## 6. WebSocket 테스트

### 6-1. wscat 설치 (없으면)

```bash
npm install -g wscat
# 또는
brew install node && npm install -g wscat
```

### 6-2. ML 스캔 진행률 WebSocket

```bash
# 먼저 스캔을 시작하고 job_id를 얻은 후 연결
wscat -c "ws://localhost/ws/scanner/$SCAN_JOB_ID"

# 1초마다 진행 상황이 JSON으로 수신됩니다:
# {"job_id": "...", "status": "running", "processed": 2, "total": 5, "result_count": 2, "top_results": [...]}
# 완료 시: {"status": "completed", ...}
```

### 6-3. Python으로 WebSocket 테스트

```python
# test_ws.py
import asyncio
import json
import websockets

JOB_ID = "여기에_job_id_입력"

async def watch():
    uri = f"ws://localhost/ws/scanner/{JOB_ID}"
    async with websockets.connect(uri) as ws:
        async for msg in ws:
            data = json.loads(msg)
            print(f"[{data['status']}] {data.get('processed', 0)}/{data.get('total', '?')}")
            if data["status"] in ("completed", "failed"):
                break

asyncio.run(watch())
```

```bash
pip install websockets
python3 test_ws.py
```

---

## 7. 프론트엔드 테스트 (포트 3000)

브라우저에서 직접 접속하여 UI를 검증합니다.

| URL                             | 설명                                 |
| ------------------------------- | ------------------------------------ |
| http://localhost:3000           | 메인 대시보드 (종목 검색 + 분석 7탭) |
| http://localhost:3000/scanner   | S&P 500 배치 스캔 + 실시간 진행률    |
| http://localhost:3000/watchlist | 관심종목 관리                        |

### 체크리스트

**메인 대시보드 (`/`)**

- [ ] 종목 코드 입력 후 검색 (예: `AAPL`)
- [ ] 캔들스틱 차트 렌더링 확인
- [ ] 기술적 지표 탭 전환 (MACD, 볼린저 밴드 등)
- [ ] 예측 결과 탭 — BUY/HOLD/SELL 시그널 표시
- [ ] 감성 분석 탭 표시
- [ ] 우측 상단 로그인 버튼 → 회원가입/로그인 모달

**스캐너 페이지 (`/scanner`)**

- [ ] 섹터 선택 후 스캔 시작
- [ ] 실시간 진행률 바 업데이트 (WebSocket)
- [ ] 완료 후 종목 랭킹 결과 테이블 표시

**관심종목 페이지 (`/watchlist`)**

- [ ] 로그인 상태에서 접근
- [ ] 종목 추가/삭제 동작
- [ ] 미니 차트 렌더링

---

## 8. 서비스 간 연동 테스트

백엔드 → ML 서비스 → 프론트엔드 전체 흐름을 검증합니다.

### 시나리오 1: 예측 조회 전체 흐름

```
프론트엔드(3000) → Nginx(80) → Backend(8000) → ML(8001)
```

```bash
# 1. 백엔드 통해 예측 요청 (백엔드가 ML에 프록시)
curl -s -X POST http://localhost:8000/api/v1/predictions \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"ticker": "MSFT"}' \
  | python3 -m json.tool
```

### 시나리오 2: 스캔 전체 흐름

```
Frontend → Backend(job 생성) → ML(Celery 작업) → Redis → WebSocket 진행률
```

```bash
# 1. 백엔드에서 job 생성
JOB_ID=$(curl -s -X POST http://localhost:8000/api/v1/scanner/jobs \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d '{"sector": "Technology"}' \
  | python3 -c "import sys,json; print(json.load(sys.stdin)['id'])")

# 2. ML 서비스에서 상태 확인
curl -s http://localhost:8001/api/v1/scanner/status/$JOB_ID | python3 -m json.tool

# 3. WebSocket으로 실시간 진행률 구독
wscat -c "ws://localhost:8001/ws/scanner/$JOB_ID"
```

### 시나리오 3: Celery 워커 동작 확인

```bash
# 워커가 작업을 받았는지 로그 확인
docker compose logs -f celery_worker

# Redis에서 직접 큐 상태 확인
docker compose exec redis redis-cli -n 2 LLEN celery
```

---

## 9. 문제 해결

### 컨테이너가 시작되지 않을 때

```bash
# 상세 오류 확인
docker compose logs backend --tail 50
docker compose logs ml --tail 50
```

### 포트 충돌

```bash
# 사용 중인 포트 확인
lsof -i :80 -i :3000 -i :8000 -i :8001 -i :5432 -i :6379

# 기존 프로세스 종료 후 재시작
docker compose down && docker compose up -d
```

### DB 스키마가 없거나 테이블 오류

```bash
# init.sql이 적용되지 않은 경우 (볼륨 초기화 필요)
docker compose down -v
docker compose up -d

# 직접 확인
docker compose exec postgres psql -U stockai -d stockai -c "\dt"
```

### ML 예측이 타임아웃

```bash
# ML 컨테이너 메모리/CPU 사용량 확인
docker stats ml celery_worker

# 로그 확인
docker compose logs ml --tail 100

# 인터넷 연결 확인 (yfinance 데이터 수신 필요)
docker compose exec ml curl -s https://finance.yahoo.com -o /dev/null -w "%{http_code}"
```

### Celery 워커가 작업을 처리하지 않을 때

```bash
# 워커 재시작
docker compose restart celery_worker

# Redis 브로커 상태
docker compose exec redis redis-cli -n 2 INFO keyspace
```

### 프론트엔드 빌드 오류

```bash
docker compose logs frontend --tail 50

# 컨테이너 내부에서 직접 확인
docker compose exec frontend sh
# 내부에서: npm run build
```

### 전체 초기화 (마지막 수단)

```bash
docker compose down -v --remove-orphans
docker system prune -f
docker compose up --build -d
```

---

## 빠른 참고

| 서비스       | URL                        | 용도                 |
| ------------ | -------------------------- | -------------------- |
| Frontend     | http://localhost:3000      | UI                   |
| Backend API  | http://localhost:8000/docs | Swagger              |
| ML API       | http://localhost:8001/docs | Swagger              |
| Nginx (통합) | http://localhost           | 프록시 진입점        |
| PostgreSQL   | localhost:5432             | DB (stockai/stockai) |
| Redis        | localhost:6379             | 캐시/브로커          |

| 자격증명    | 값                           |
| ----------- | ---------------------------- |
| DB 사용자   | `stockai`                    |
| DB 비밀번호 | `stockai`                    |
| DB 이름     | `stockai`                    |
| 테스트 계정 | 직접 `/auth/register`로 생성 |
