# 테스트 코드 완성도 감사 보고서 (Test Completeness Audit)

> **작성일**: 2026-05-22  
> **감사 범위**: CI 워크플로, Backend 단위 테스트, ML 단위 테스트, Frontend 테스트, 로컬 통합 스크립트  
> **목적**: 현재 테스트 커버리지의 공백을 식별하고, 우선순위에 따른 개선 작업 순서를 정의합니다.

---

## 1. 전체 요약

| 영역 | 테스트 파일 수 | 테스트 함수 수 | 상태 |
|------|:-----------:|:-----------:|:----:|
| Backend 단위 테스트 | 5 | 27 | 양호 (일부 공백) |
| ML 단위 테스트 | 6 | 223 | 매우 충실 |
| Frontend 단위 테스트 | 0 | 0 | **부재** |
| 로컬 통합 스크립트 | 1 (sh) + 1 (py) | — | 충실 (CI 미편입) |
| CI 워크플로 | 1 (4 jobs) | — | 양호 (coverage 미설정) |

---

## 2. CI 워크플로 분석 (`.github/workflows/ci.yml`)

### 2-1. 현황

4개 Job이 병렬 실행됩니다.

| Job | 실행 내용 | 트리거 |
|-----|-----------|--------|
| `backend` | ruff lint → mypy → pytest | PR to main/develop, push to develop |
| `ml` | ruff lint → mypy → pytest | 동일 |
| `frontend` | tsc type-check → eslint → next build | 동일 |
| `docker` | 3개 서비스 production image 빌드 | 동일 |

**잘 된 점**
- `concurrency.cancel-in-progress: true` 설정으로 동일 브랜치 중복 실행 자동 취소
- Poetry 캐시(`actions/cache@v4`)로 의존성 재설치 비용 절감
- Docker multi-stage `--target production` 빌드로 런타임 이미지 검증

### 2-2. 문제점

| 번호 | 문제 | 영향 |
|------|------|------|
| CI-1 | pytest에 `--cov` 플래그 없음 — coverage 수집 안 됨 | 신규 코드 추가 시 퇴행 감지 불가 |
| CI-2 | coverage 실패 임계값(fail-under) 미설정 | 테스트 없는 코드가 PR 통과 가능 |
| CI-3 | Frontend에 단위 테스트 job 없음 | UI 로직 버그를 CI에서 감지 불가 |
| CI-4 | 통합 테스트(`test_local.sh`) CI 미편입 | 서비스 간 연동 버그는 로컬에서만 발견 가능 |

---

## 3. Backend 단위 테스트 분석 (`backend/tests/`)

### 3-1. 현황

```
backend/tests/
├── conftest.py          # SQLite in-memory DB, client/auth_headers fixture
├── test_health.py       #  1개 — /health 엔드포인트
├── test_auth.py         #  7개 — register/login/refresh/me/에러 케이스
├── test_watchlist.py    #  8개 — CRUD + Redis 캐시 mock
├── test_prediction.py   #  4개 — DB 캐시 히트/미스, ML 다운 fallback
└── test_scanner.py      #  7개 — 작업 생성/ML오프라인/소유권 격리/목록
```

**잘 된 점**
- `conftest.py`가 SQLite in-memory를 사용해 psycopg2 없이 CI 실행 가능
- `pytest-asyncio` + `asyncio_mode = "auto"` 설정으로 async 테스트 boilerplate 없음
- `mypy strict = true` 적용 (backend만)
- 소유권 격리(Forbidden) 케이스를 명시적으로 테스트 — 보안 검증 포함
- ML 서비스 오프라인 시 graceful fallback 케이스 커버

### 3-2. 문제점

| 번호 | 누락 항목 | 파일 위치 | 영향 |
|------|----------|-----------|------|
| BE-1 | `GET /stocks/{ticker}` 엔드포인트 테스트 없음 | `app/api/v1/endpoints/stocks.py` | ML 프록시 라우팅 버그 미감지 |
| BE-2 | WebSocket 엔드포인트 테스트 없음 | `app/api/v1/endpoints/websocket.py` | WS 연결/메시지 직렬화 버그 미감지 |
| BE-3 | `app/services/stock.py` 서비스 단위 테스트 없음 | `app/services/stock.py` | fetch_stock_info 로직 미검증 |

### 3-3. 보완 방향

**BE-1 / BE-3**: httpx mock으로 ML 서비스 응답을 모킹하는 통합 테스트 추가

```python
# 예시: test_stocks.py
@patch("app.services.stock.get_http_client")
def test_get_stock_success(mock_client, client, auth_headers):
    mock_resp = AsyncMock()
    mock_resp.status_code = 200
    mock_resp.json = lambda: {"ticker": "AAPL", "current_price": 185.0, ...}
    mock_client.return_value.get.return_value = mock_resp

    resp = client.get("/api/v1/stocks/AAPL", headers=auth_headers)
    assert resp.status_code == 200
    assert resp.json()["ticker"] == "AAPL"
```

**BE-2**: `starlette.testclient.TestClient`의 WebSocket 지원 활용

```python
# 예시: test_websocket.py
def test_ws_scanner_streams_status(client):
    with client.websocket_connect("/ws/scanner/fake-job-id") as ws:
        # ML 서비스 mock 후 첫 메시지 검증
        data = ws.receive_json()
        assert "status" in data
```

---

## 4. ML 단위 테스트 분석 (`ml/tests/`)

### 4-1. 현황

```
ml/tests/
├── test_health.py       #  2개 — /health, /docs
├── test_technical.py    #  6개 — SMA/EMA/RSI/MACD/지표/시그널
├── test_predictor.py    #  7개 — 피처/학습데이터/레짐/빌드결과/백테스트
├── test_fetcher.py      # ~35개 — yfinance mock, Redis 캐시, 한국 종목 등
├── test_scanner.py      # ~60개 — 캐시/블렌딩/진행률/분석 전체 플로우
└── test_sentiment.py    # ~60개 — VADER/impact/relevance 전체 파이프라인
```

**잘 된 점**
- 외부 의존성(yfinance, Redis) 전부 mock — 네트워크 없이 실행 가능
- 경계값(boundary), 예외 케이스, 빈 데이터 케이스를 빠짐없이 커버
- `ScanProgress`, `dp_blend` 같은 내부 유틸리티 함수까지 테스트
- 클래스 기반 테스트 구조로 관련 케이스 그룹화

### 4-2. 문제점

| 번호 | 누락 항목 | 파일 위치 | 영향 |
|------|----------|-----------|------|
| ML-1 | API 엔드포인트 테스트 없음 | `ml/app/api/v1/endpoints/*.py` | 라우팅/스키마 직렬화 버그 미감지 |
| ML-2 | Celery 태스크 테스트 없음 | `ml/app/workers/scan_tasks.py` | 비동기 워커 로직 미검증 |
| ML-3 | `conftest.py` 없음 | `ml/tests/` | 공통 fixture 중복 (각 파일이 독립적으로 client 생성) |
| ML-4 | `mypy` strict 미적용 | `ml/pyproject.toml` | backend보다 타입 검사 수준이 낮음 |

### 4-3. 보완 방향

**ML-1**: FastAPI `TestClient`로 엔드포인트 레이어 테스트 추가

```python
# 예시: test_api_predict.py
from fastapi.testclient import TestClient
from unittest.mock import patch, AsyncMock
from app.main import app

client = TestClient(app)

@patch("app.api.v1.endpoints.predict.predict_ticker", new_callable=AsyncMock)
def test_predict_endpoint(mock_predict):
    mock_predict.return_value = {"ticker": "AAPL", "signal": "BUY", ...}
    resp = client.post("/api/v1/predict", json={"ticker": "AAPL"})
    assert resp.status_code == 200
    assert resp.json()["signal"] == "BUY"
```

**ML-2**: Celery `task.apply()` (동기 실행)로 태스크 로직 격리 테스트

```python
# 예시: test_scan_tasks.py
from unittest.mock import patch
from app.workers.scan_tasks import run_scan_task

@patch("app.workers.scan_tasks.run_sp500_scan")
def test_run_scan_task_success(mock_scan):
    mock_scan.return_value = (pd.DataFrame(), {})
    result = run_scan_task.apply(args=["job-123", ["AAPL", "MSFT"]]).get()
    assert result["status"] == "completed"
```

**ML-3**: 공통 `conftest.py` 생성으로 `TestClient` fixture 공유

---

## 5. Frontend 테스트 분석 (`frontend/`)

### 5-1. 현황

```
frontend/
├── src/
│   ├── app/         # Next.js 페이지 3개
│   ├── components/  # Plotly 차트, 공통 컴포넌트
│   └── lib/         # API 클라이언트, WS 훅 등
└── package.json     # scripts: dev / build / start / lint / type-check
                     # ← 'test' 스크립트 없음, Vitest/Jest 미설치
```

**CI에서 실행 중인 검사**

| 검사 | 도구 | 감지 가능 버그 |
|------|------|--------------|
| 타입 검사 | `tsc --noEmit` | 타입 불일치 |
| 린트 | eslint | 코드 스타일, 일부 로직 오류 |
| 빌드 | `next build` | 빌드 타임 에러 |
| 런타임 로직 버그 | 없음 | **감지 불가** |

### 5-2. 문제점

| 번호 | 문제 | 영향 |
|------|------|------|
| FE-1 | 테스트 파일 0개, 테스트 러너 미설치 | 컴포넌트/훅/유틸 로직 버그 감지 불가 |
| FE-2 | package.json에 `test` 스크립트 없음 | CI에 테스트 job 추가 불가 |
| FE-3 | API 클라이언트 / WS 훅 테스트 없음 | 서버 연동 로직 버그 미감지 |

### 5-3. 보완 방향

**최소 권장 설정 (Vitest + React Testing Library)**

```bash
npm install -D vitest @vitejs/plugin-react @testing-library/react @testing-library/user-event jsdom
```

`vitest.config.ts`:
```ts
import { defineConfig } from 'vitest/config'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  test: { environment: 'jsdom', globals: true },
})
```

`package.json` scripts 추가:
```json
"test": "vitest run",
"test:watch": "vitest"
```

**우선 커버할 테스트 대상**
1. API 클라이언트 함수 (fetch 래퍼, 에러 핸들링)
2. WS 훅 (연결/재연결/메시지 파싱 로직)
3. 핵심 컴포넌트 렌더링 스모크 테스트

---

## 6. 로컬 통합 스크립트 분석 (`scripts/`)

### 6-1. 현황

| 파일 | 역할 |
|------|------|
| `scripts/test_local.sh` | Docker Compose 환경에서 전체 서비스 E2E 검증 |
| `scripts/test_ws.py` | WebSocket 진행률 메시지 수신 검증 |

**test_local.sh 커버 범위**

| 섹션 | 내용 |
|------|------|
| 0 | 사전 확인 (docker, curl) |
| 3 | 헬스체크 (backend / ML / Nginx 라우팅 / PostgreSQL / Redis) |
| 4 | 백엔드 API (Auth + Watchlist CRUD + Scanner 작업 생성) |
| 5 | ML 서비스 (기술적지표 / 감성분석 / 배치스캔 / 단일예측) |
| 6 | WebSocket (진행률 스트리밍) |
| 8 | 서비스 간 연동 (예측 이력 조회 / Celery 큐 접근) |

### 6-2. 문제점

| 번호 | 문제 | 영향 |
|------|------|------|
| SH-1 | CI에 미편입 — 로컬에서만 실행 가능 | 서비스 간 연동 버그가 PR에서 감지 안 됨 |
| SH-2 | 섹션 번호 불연속 (0→3→4→5→6→8, 섹션 1·2·7 없음) | 문서와 스크립트 간 구조 불일치 |
| SH-3 | ML 예측(`--full`) 타임아웃이 130초로 고정 | 느린 환경에서 간헐적 실패 가능 |

### 6-3. 보완 방향

CI에 docker-compose 기반 통합 테스트 job 추가:

```yaml
# .github/workflows/ci.yml에 추가
integration:
  name: Integration tests (docker-compose)
  runs-on: ubuntu-latest
  needs: [backend, ml, frontend]   # 단위 테스트 통과 후 실행
  steps:
    - uses: actions/checkout@v4
    - name: Start services
      run: docker compose up -d --wait
    - name: Run integration tests
      run: bash scripts/test_local.sh --skip-ml   # ML 예측 제외 (CI 시간 절약)
    - name: Stop services
      if: always()
      run: docker compose down
```

---

## 7. 작업 순서 (우선순위)

개선 항목을 **즉각 효과**, **구현 난이도**, **리스크** 기준으로 정렬했습니다.

### Phase 1 — 빠른 승리 (1~2일)

> 코드 변경 없이 설정 파일만 수정하거나, 기존 패턴을 그대로 복사하면 되는 항목

| # | 작업 | 파일 | 예상 소요 |
|---|------|------|----------|
| 1-1 | CI에 coverage 수집 추가 (`--cov=app --cov-report=xml`) | `.github/workflows/ci.yml` | 30분 |
| 1-2 | CI backend/ml에 coverage 실패 임계값 설정 (`--cov-fail-under=70`) | `.github/workflows/ci.yml` | 10분 |
| 1-3 | `pyproject-dev` coverage 의존성 추가 (`pytest-cov`) | `backend/pyproject.toml`, `ml/pyproject.toml` | 15분 |
| 1-4 | ML `conftest.py` 생성 (공통 `TestClient` fixture) | `ml/tests/conftest.py` | 30분 |
| 1-5 | `test_local.sh` 섹션 번호 정리 (1·2·7 정비) | `scripts/test_local.sh` | 15분 |

### Phase 2 — 핵심 공백 보완 (2~4일)

> 현재 커버되지 않는 엔드포인트 테스트 추가

| # | 작업 | 파일 | 예상 소요 |
|---|------|------|----------|
| 2-1 | Backend `stocks` 엔드포인트 테스트 | `backend/tests/test_stocks.py` | 2시간 |
| 2-2 | Backend `websocket` 엔드포인트 테스트 | `backend/tests/test_websocket.py` | 3시간 |
| 2-3 | ML API 엔드포인트 테스트 (predict / technical / sentiment) | `ml/tests/test_api_*.py` | 반나절 |
| 2-4 | ML Celery `scan_tasks` 단위 테스트 | `ml/tests/test_scan_tasks.py` | 2시간 |

### Phase 3 — Frontend 테스트 기반 구축 (3~5일)

> 테스트 프레임워크 설치 + 핵심 모듈 우선 커버

| # | 작업 | 파일 | 예상 소요 |
|---|------|------|----------|
| 3-1 | Vitest + Testing Library 설치 및 설정 | `frontend/vitest.config.ts`, `package.json` | 1시간 |
| 3-2 | CI frontend job에 `npm run test` 추가 | `.github/workflows/ci.yml` | 15분 |
| 3-3 | API 클라이언트 함수 테스트 | `frontend/src/lib/__tests__/` | 반나절 |
| 3-4 | WS 훅 테스트 (연결/재연결/메시지 파싱) | `frontend/src/lib/__tests__/` | 반나절 |
| 3-5 | 핵심 컴포넌트 렌더링 스모크 테스트 3~5개 | `frontend/src/components/__tests__/` | 1일 |

### Phase 4 — CI 통합 테스트 편입 (1~2일)

> 로컬에서만 실행되던 E2E 스크립트를 CI로 올리는 작업

| # | 작업 | 파일 | 예상 소요 |
|---|------|------|----------|
| 4-1 | CI에 `integration` job 추가 (docker-compose up + test_local.sh) | `.github/workflows/ci.yml` | 2시간 |
| 4-2 | `--skip-ml` 플래그로 CI 실행 시간 제어 (ML 예측 제외) | 기존 스크립트 활용 | — |
| 4-3 | ML strict mypy 적용 (backend와 동일 수준 맞춤) | `ml/pyproject.toml` | 타입 에러 수정 포함 1일 |

---

## 8. 개선 후 예상 CI 구조

```
CI (pull_request to main/develop)
│
├── backend    — ruff + mypy(strict) + pytest --cov=app --cov-fail-under=70
├── ml         — ruff + mypy(strict) + pytest --cov=app --cov-fail-under=70
├── frontend   — tsc + eslint + vitest run + next build
├── docker     — production image 빌드 smoke test
│
└── integration (needs: backend + ml + frontend)
    └── docker compose up → test_local.sh --skip-ml → docker compose down
```

---

## 9. 참고 문서

- [로컬 통합 테스트 가이드](./LOCAL_TESTING_GUIDE.md)
- [CI/CD 로드맵](./CICD_ROADMAP.md)
- [pytest-cov 공식 문서](https://pytest-cov.readthedocs.io/)
- [Vitest 공식 문서](https://vitest.dev/)
- [React Testing Library](https://testing-library.com/docs/react-testing-library/intro/)
