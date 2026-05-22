## WebSocket 라우팅 불일치 — 원인 분석 및 해결 방안

> **발견 경위**: `docs/LOCAL_TESTING_GUIDE.md`와 `infra/nginx/nginx.conf`의 교차 검증 중 발견  
> **영향 범위**: 로컬 및 프로덕션 환경에서의 WebSocket 연결 방식

### 한 줄 요약

> `LOCAL_TESTING_GUIDE.md`는 WebSocket을 **ML 서비스에 직접** 연결하라고 안내하지만,  
> `nginx.conf`의 `/ws/` 경로는 **backend 서비스**로 연결되어 있어 Nginx를 통하면 연결이 실패합니다.

### 1. 현재 코드가 어떻게 생겼나요?

#### nginx.conf — `/ws/`는 backend로 라우팅

```nginx
# infra/nginx/nginx.conf

location /ws/ {
    proxy_pass http://backend/ws/;   # ← backend:8000 으로 보냄
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
}
```

#### ml/app/main.py — WebSocket 엔드포인트는 ML 서비스에 정의

```python
# ml/app/main.py

@app.websocket("/ws/scanner/{job_id}")   # ← ML 서비스(port 8001)가 제공
async def ws_scanner_progress(websocket: WebSocket, job_id: str):
    ...
```

#### LOCAL_TESTING_GUIDE.md — 테스트 URL이 ML 직접 접속

```bash
# docs/LOCAL_TESTING_GUIDE.md (현재 안내)

wscat -c "ws://localhost:8001/ws/scanner/$SCAN_JOB_ID"
#                 ^^^^
#                 ML 포트에 직접 연결 (Nginx 미경유)
```

### 2. 그래서 어떤 문제가 생기나요?

실제 트래픽이 흐르는 경로를 따라가 보면 문제가 명확하게 보입니다.

#### 🔴 경로 A — Nginx를 통한 WebSocket (현재 설정 기준, 실패)

```
클라이언트
    │
    │  ws://localhost/ws/scanner/{job_id}  ← Nginx 경유
    ▼
Nginx (port 80)
    │
    │  location /ws/ → proxy_pass http://backend/ws/
    ▼
backend:8000  ← ❌ /ws/scanner/{job_id} 라우트가 없음
                    → 연결 거부 또는 404
```

**backend 서비스에는 `/ws/scanner/` 라우트가 정의되어 있지 않습니다.**  
따라서 Nginx를 통해 `ws://localhost/ws/scanner/...`로 접속하면 연결이 실패합니다.

#### 🟡 경로 B — ML 서비스 직접 접속 (현재 문서 안내 방식, 로컬에서만 작동)

```
클라이언트
    │
    │  ws://localhost:8001/ws/scanner/{job_id}  ← ML 직접 접속
    ▼
ml:8001  ← ✅ main.py에 @app.websocket("/ws/scanner/{job_id}") 존재
    │
    │  Redis에서 진행률 읽기
    ▼
    진행률 JSON 실시간 전송
```

이 방식은 `docker-compose.yml`에서 `8001:8001` 포트가 외부에 노출되어 있기 때문에  
**로컬 개발 환경에서만** 작동합니다.

> [!WARNING]
> 프로덕션(AWS EC2)에서는 `docker-compose.prod.yml`에 `ports: []`가 설정되어  
> ML 포트(8001)가 외부에 노출되지 않습니다. 따라서 직접 접속 방식은 **프로덕션에서 작동하지 않습니다.**

### 3. 왜 이런 불일치가 발생했나요?

WebSocket 라우팅 설계가 두 단계에 걸쳐 이루어지면서 서로 다른 의도가 섞였습니다.

| 시점 | 의도 | 결과 |
|------|------|------|
| `nginx.conf` 작성 시 | `/ws/`를 backend에 연결 (backend가 WebSocket을 제공할 것이라 가정) | `backend:8000`으로 라우팅 |
| `ml/main.py` 작성 시 | WebSocket을 ML 서비스에 직접 구현 | `ml:8001/ws/scanner/{id}` |
| `LOCAL_TESTING_GUIDE.md` 작성 시 | ML 서비스 직접 접속으로 테스트 | `localhost:8001` 안내 |

**결과**: nginx.conf와 실제 구현 위치가 일치하지 않는 상태가 되었습니다.

### 4. 해결 방안 2가지

#### ✅ 방안 1 — nginx.conf에 ML WebSocket 경로 추가 (권장)

Nginx가 `/ws/scanner/` 요청을 ML 서비스로 보내도록 경로를 분리합니다.  
이렇게 하면 프론트엔드가 단일 진입점(`ws://localhost/...`)만 알면 되고,  
포트를 외부에 노출하지 않아도 됩니다.

```nginx
# infra/nginx/nginx.conf 수정안

location /ws/scanner/ {
    proxy_pass http://ml/ws/scanner/;    # ML WebSocket
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
}

location /ws/ {
    proxy_pass http://backend/ws/;       # Backend WebSocket (향후 사용)
    proxy_http_version 1.1;
    proxy_set_header Upgrade $http_upgrade;
    proxy_set_header Connection "upgrade";
    proxy_set_header Host $host;
}
```

> [!IMPORTANT]
> Nginx는 `location` 블록을 **더 긴 prefix 우선**으로 매칭합니다.  
> `/ws/scanner/`가 `/ws/`보다 먼저 매칭되므로 순서에 상관없이 동작하지만,  
> 명확성을 위해 구체적인 경로를 위에 작성하는 것이 관례입니다.

이 방안을 적용하면 `LOCAL_TESTING_GUIDE.md`의 테스트 URL도 수정합니다:

```bash
# 수정 후 — Nginx 경유 (로컬/프로덕션 모두 동일)
wscat -c "ws://localhost/ws/scanner/$SCAN_JOB_ID"
```

#### 🟡 방안 2 — 문서에 "직접 접속" 이유를 명시 (빠른 임시 해결)

nginx.conf를 수정하지 않고, 문서에 포트 직접 접속이 **로컬 전용**임을 명시합니다.

```markdown
<!-- LOCAL_TESTING_GUIDE.md 수정안 -->

#### 6-2. ML 스캔 진행률 WebSocket

> ⚠️ **로컬 전용**: ML 포트(8001)가 로컬에서만 외부에 노출됩니다.
> 프로덕션에서는 `ws://yourdomain.com/ws/scanner/$SCAN_JOB_ID`를 사용하세요.
> (단, 이를 위해서는 nginx.conf에 ML WebSocket 라우팅 추가가 필요합니다.)

```bash
wscat -c "ws://localhost:8001/ws/scanner/$SCAN_JOB_ID"
```

### 5. 방안 비교

| 항목 | 방안 1 (nginx.conf 수정) | 방안 2 (문서 명시) |
|------|--------------------------|-------------------|
| 로컬 작동 | ✅ | ✅ |
| 프로덕션 작동 | ✅ | ❌ (추가 작업 필요) |
| 프론트엔드 단일 진입점 | ✅ | ❌ |
| 변경 범위 | `nginx.conf` + `LOCAL_TESTING_GUIDE.md` | `LOCAL_TESTING_GUIDE.md` 만 |
| 권장 여부 | **권장** | 임시 방편 |

### 6. 방안 1 적용 체크리스트

- [x] `infra/nginx/nginx.conf` — `/ws/scanner/` 블록 추가
- [x] `docs/LOCAL_TESTING_GUIDE.md` L318, L336 — URL을 `ws://localhost/ws/scanner/...`로 수정
- [x] 로컬에서 `docker compose up --build -d` 후 WebSocket 연결 재테스트

### 관련 파일

- [`infra/nginx/nginx.conf`](../infra/nginx/nginx.conf) — Nginx 라우팅 설정
- [`ml/app/main.py`](../ml/app/main.py) — ML WebSocket 엔드포인트 정의
- [`docker-compose.yml`](../docker-compose.yml) — 로컬 포트 노출 설정
- [`docker-compose.prod.yml`](../docker-compose.prod.yml) — 프로덕션 포트 비노출 설정
- [`docs/LOCAL_TESTING_GUIDE.md`](./LOCAL_TESTING_GUIDE.md) — 테스트 가이드 (수정 대상)
