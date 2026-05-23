# 개선 계획

> Phase 1~3(AWS 구축 + CD 연결)이 안정화된 이후 적용하는 중기 과제 모음입니다.

---

## Phase 4 — HTTPS 적용

> **선행 조건**: 도메인 구매 및 EC2 IP로 A 레코드 연결 완료

### 4-1. Let's Encrypt 인증서 발급

```bash
# EC2에서 실행
sudo apt install -y certbot

# 컨테이너 nginx가 80 포트를 점유하므로 먼저 내림
docker compose -f docker-compose.yml -f docker-compose.prod.yml down

# 인증서 발급
sudo certbot certonly --standalone -d yourdomain.com

# 자동 갱신 크론 등록
echo "0 0 1 * * certbot renew --quiet" | sudo crontab -
```

### 4-2. nginx.conf HTTPS 블록 활성화

[`infra/nginx/nginx.conf`](../infra/nginx/nginx.conf)에서 주석 처리된 HTTPS 서버 블록을 활성화하고 도메인명을 교체합니다.

```nginx
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

    location /api/        { proxy_pass http://backend; ... }
    location /ml/         { proxy_pass http://ml/;     ... }
    location /ws/scanner/ { ... websocket upgrade ...       }
    location /ws/         { ... websocket upgrade ...       }
    location /            { proxy_pass http://frontend/;    }
}
```

### 4-3. 전체 스택 재시작

4-1에서 `docker compose down`으로 모든 컨테이너를 내렸으므로, nginx만 재시작하는 게 아니라 전체 스택을 올려야 합니다.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

> nginx 설정만 바꾼 경우(이미 다른 서비스가 실행 중일 때)에는 `up -d --no-deps nginx`로 nginx만 재시작해도 됩니다.

### 4-4. 프론트엔드 환경변수 URL 변경

`.env`의 `NEXT_PUBLIC_*` 값을 HTTP → HTTPS로 갱신합니다.

```bash
NEXT_PUBLIC_API_URL=https://yourdomain.com
NEXT_PUBLIC_ML_URL=https://yourdomain.com/ml
NEXT_PUBLIC_WS_URL=wss://yourdomain.com
```

---

## Phase 5 — CI 품질 강화

### 5-1. Backend 테스트 PostgreSQL 전환 (현재 SQLite)

현재 CI는 SQLite in-memory로 psycopg2를 우회합니다. PostgreSQL 고유 구문(JSON 연산자, `RETURNING` 등) 버그를 CI에서 잡으려면 서비스 컨테이너 추가가 필요합니다.

```yaml
# ci.yml → backend 잡에 추가
services:
  postgres:
    image: postgres:16
    env:
      POSTGRES_USER: stockai
      POSTGRES_PASSWORD: stockai
      POSTGRES_DB: stockai_test
    ports: ["5432:5432"]
    options: >-
      --health-cmd pg_isready
      --health-interval 5s
      --health-timeout 5s
      --health-retries 5

steps:
  - name: Test (pytest)
    env:
      DATABASE_URL: postgresql://stockai:stockai@localhost:5432/stockai_test
    run: poetry run pytest tests/ -v --tb=short --cov=app --cov-report=xml --cov-fail-under=70
```

### 5-2. Alembic 마이그레이션 Dry-Run

```yaml
# ci.yml → backend 잡, pytest 이후에 추가
- name: Alembic migration dry-run
  env:
    DATABASE_URL: postgresql://stockai:stockai@localhost:5432/stockai_test
  run: poetry run alembic upgrade head --sql | head -50
```

### 5-3. pip-audit 보안 취약점 스캔

```yaml
# ci.yml → backend·ml 잡에 추가
- name: Security audit (pip-audit)
  run: poetry run pip-audit
```

---

## Phase 6 — 배포 전략 고도화

> t3.medium 단일 인스턴스 기준입니다.

### 6-1. DB 마이그레이션 자동화

`deploy.sh`에 추가합니다 (docker compose up -d 이후).

```bash
echo "[deploy] Running DB migrations..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec -T backend poetry run alembic upgrade head
```

### 6-2. 이미지 레지스트리 도입 (GHCR)

| 방식 | 배포 시간 |
|------|-----------|
| 현재: EC2에서 git pull 후 소스 빌드 | 3~10분 |
| 개선: CI에서 이미지 빌드 → GHCR push → EC2에서 pull만 | 30초~1분 |

```yaml
# cd.yml에 deploy 잡 이전으로 추가
build-and-push:
  runs-on: ubuntu-latest
  steps:
    - uses: actions/checkout@v4
    - uses: docker/login-action@v3
      with:
        registry: ghcr.io
        username: ${{ github.actor }}
        password: ${{ secrets.GITHUB_TOKEN }}
    - run: |
        docker build --target production \
          -t ghcr.io/${{ github.repository }}/backend:${{ github.sha }} ./backend
        docker push ghcr.io/${{ github.repository }}/backend:${{ github.sha }}
        # ml, frontend도 동일하게
```

### 6-3. Rolling Restart 무중단 배포

> Blue-Green은 컨테이너를 2배로 실행해야 해 t3.medium에서 OOM 위험이 있습니다.

```bash
# deploy.sh 개선 버전
for service in backend ml celery_worker frontend; do
  echo "[deploy] Restarting $service..."
  docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    up -d --no-deps --build "$service"
  sleep 5
done
```

### 6-4. 자동 롤백

```bash
# deploy.sh에 추가
PREV_COMMIT=$(git rev-parse HEAD~1)

if ! curl -sf http://localhost/api/health; then
  echo "[deploy] Health check failed. Rolling back to $PREV_COMMIT..."
  git checkout "$PREV_COMMIT"
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
  exit 1
fi
```

---

## Phase 7 — 모니터링

### 7-1. Prometheus 메트릭 노출

```toml
# backend/pyproject.toml
prometheus-fastapi-instrumentator = "^6.1"
```

```python
# backend/app/main.py
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
```

### 7-2. Grafana 대시보드

Docker Compose에 prometheus + grafana 서비스 추가 후 시각화 항목:

- API 에러율 (5xx 비율)
- P99 응답 지연
- Celery 큐 적체 수
- 임계치 초과 시 Slack Webhook 알림

### 7-3. ML 예측 드리프트 감지

GitHub Actions 스케줄 잡 또는 Celery Beat로 예측 오차를 주기적으로 측정합니다. 임계치 초과 시 모델 재학습 파이프라인을 트리거합니다.
