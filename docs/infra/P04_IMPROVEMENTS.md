# 개선 계획

> Phase 1~3 (AWS 구축 + CD 자동화)이 안정화된 이후 적용하는 중기 과제들입니다.  
> 처음부터 한꺼번에 하려 하지 말고, 기본 배포가 잘 돌아가는 것을 확인한 뒤 순서대로 적용하세요.

---

## Phase 4 — HTTPS 적용 (보안 연결)

> **선행 조건**: 도메인을 구매하고, DNS A 레코드를 EC2 퍼블릭 IP로 연결 완료

### HTTPS가 왜 필요한가요?

현재는 `http://`로 접속하는데, 이 경우 데이터가 암호화되지 않아 중간에 누군가 내용을 엿볼 수 있습니다.  
`https://`는 SSL/TLS 인증서로 통신 내용을 암호화합니다.

**Let's Encrypt**는 이 SSL 인증서를 무료로 발급해주는 공인 기관입니다. 예전엔 인증서가 유료였지만, Let's Encrypt 덕분에 지금은 누구나 무료로 HTTPS를 적용할 수 있습니다.

### 4-1. 도메인 A 레코드 연결 확인

도메인 등록 대행사(가비아, 후이즈, Namecheap 등) 관리 페이지에서 DNS 설정 → A 레코드 추가:

```
yourdomain.com  →  EC2_퍼블릭_IP
```

DNS 변경이 전 세계에 전파되는 데 최대 24시간이 걸릴 수 있습니다. 아래 명령으로 확인합니다:

```bash
nslookup yourdomain.com
# EC2 IP가 출력되면 연결 완료
```

### 4-2. Let's Encrypt 인증서 발급

EC2에 SSH 접속 후 실행합니다.

```bash
# certbot 설치 (인증서 발급 및 갱신 도구)
sudo apt install -y certbot

# nginx 컨테이너가 80 포트를 점유하므로 먼저 내립니다
# (certbot이 80 포트를 열어 도메인 소유 여부를 검증합니다)
docker compose -f docker-compose.yml -f docker-compose.prod.yml down

# 인증서 발급 (yourdomain.com을 실제 도메인으로 교체)
sudo certbot certonly --standalone -d yourdomain.com
```

발급 성공 시 아래 경로에 인증서 파일이 생성됩니다:
- 인증서: `/etc/letsencrypt/live/yourdomain.com/fullchain.pem`
- 개인키: `/etc/letsencrypt/live/yourdomain.com/privkey.pem`

```bash
# Let's Encrypt 인증서는 90일마다 만료됩니다.
# 매월 1일 자정에 자동으로 갱신되도록 크론 작업을 등록합니다.
echo "0 0 1 * * certbot renew --quiet" | sudo crontab -
```

### 4-3. nginx.conf HTTPS 설정 활성화

[`infra/nginx/nginx.conf`](../infra/nginx/nginx.conf)를 편집해서 주석 처리된 HTTPS 블록을 활성화하고 `yourdomain.com`을 실제 도메인으로 교체합니다.

```nginx
# HTTP 접속 시 HTTPS로 자동 리다이렉트
server {
    listen 80;
    server_name yourdomain.com;
    return 301 https://$host$request_uri;
}

# HTTPS 설정
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

### 4-4. 전체 스택 재시작

4-2에서 `docker compose down`으로 모든 컨테이너를 내렸으므로 전체를 다시 올립니다.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d
```

> nginx 설정만 바꿨고 다른 서비스가 이미 실행 중인 경우에는, nginx만 재시작해도 됩니다:
> ```bash
> docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps nginx
> ```

### 4-5. 프론트엔드 환경변수 URL을 HTTPS로 업데이트

EC2의 `.env` 파일에서 HTTP → HTTPS, `ws://` → `wss://` 로 변경합니다.

```bash
# .env 수정
NEXT_PUBLIC_API_URL=https://yourdomain.com
NEXT_PUBLIC_ML_URL=https://yourdomain.com/ml
NEXT_PUBLIC_WS_URL=wss://yourdomain.com   # ws:// → wss:// 로 변경 필수!
```

변경 후 프론트엔드 컨테이너를 재시작해야 환경변수가 적용됩니다:

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  up -d --no-deps --build frontend
```

---

## Phase 5 — CI 품질 강화

### 5-1. Backend 테스트를 PostgreSQL로 전환

**현재 상황**: CI에서 백엔드 테스트가 PostgreSQL 대신 SQLite(파일 기반 경량 DB)를 사용합니다.  
**문제점**: PostgreSQL 고유 문법(JSON 연산자 `->`, `RETURNING` 절 등)을 쓰면 SQLite에서는 테스트가 통과해도 실제 서버(RDS)에서 오류가 날 수 있습니다.

`.github/workflows/ci.yml`의 `backend` 잡에 아래 내용을 추가합니다:

```yaml
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

**목적**: DB 스키마 변경(migration) 파일이 문법 오류 없이 실행되는지 CI에서 미리 확인합니다.

```yaml
# ci.yml → backend 잡, pytest 이후에 추가
- name: Alembic migration dry-run
  env:
    DATABASE_URL: postgresql://stockai:stockai@localhost:5432/stockai_test
  run: poetry run alembic upgrade head --sql | head -50
  # --sql 플래그: 실제 DB를 변경하지 않고 실행될 SQL만 출력합니다
```

### 5-3. pip-audit 보안 취약점 스캔

**목적**: 사용 중인 Python 패키지에 알려진 보안 취약점(CVE)이 있는지 자동으로 검사합니다.

```yaml
# ci.yml → backend·ml 잡에 추가
- name: Security audit (pip-audit)
  run: poetry run pip-audit
```

---

## Phase 6 — 배포 전략 고도화

> t3.medium 단일 인스턴스 기준입니다.

### 6-1. DB 마이그레이션 자동화

현재는 배포 후 수동으로 `alembic upgrade head`를 실행해야 합니다.  
`deploy.sh`에 아래를 추가해서 배포할 때마다 자동으로 실행되도록 합니다.

```bash
# deploy.sh 에서 docker compose up -d 이후에 추가
echo "[deploy] DB 마이그레이션 실행 중..."
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec -T backend poetry run alembic upgrade head
# -T 플래그: 비대화형 모드. SSH 자동화 환경에서 터미널이 없을 때 필요합니다.
```

### 6-2. GHCR 이미지 레지스트리 도입

**현재 방식의 문제**: EC2에서 git pull → 소스코드 빌드 → 이미지 생성까지 3~10분 소요됩니다.  
**개선 방법**: CI에서 미리 이미지를 빌드해 GitHub Container Registry(GHCR)에 올려두고, EC2는 이미지만 받아오면 됩니다. 빌드를 EC2가 아닌 GitHub 서버에서 하므로 EC2에 부하도 줄어듭니다.

| 방식 | 배포 시간 |
|------|-----------|
| 현재: EC2에서 소스 직접 빌드 | 3~10분 |
| 개선: GHCR에서 완성된 이미지 pull | 30초~1분 |

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
        password: ${{ secrets.GITHUB_TOKEN }}  # GitHub이 자동 제공하는 토큰
    - run: |
        docker build --target production \
          -t ghcr.io/${{ github.repository }}/backend:${{ github.sha }} ./backend
        docker push ghcr.io/${{ github.repository }}/backend:${{ github.sha }}
        # ml, frontend도 동일하게 반복
```

### 6-3. Rolling Restart (서비스 중단 없는 배포)

**현재 방식**: `docker compose up --build`로 모든 컨테이너를 동시에 재시작 → 배포 중 잠깐 서비스 중단 발생  
**개선 방법**: 서비스를 하나씩 순차적으로 재시작 → 전체 서비스가 동시에 중단되지 않음

```bash
# deploy.sh 개선 버전
for service in backend ml celery_worker frontend; do
  echo "[deploy] $service 재시작 중..."
  docker compose -f docker-compose.yml -f docker-compose.prod.yml \
    up -d --no-deps --build "$service"
  sleep 5   # 서비스가 안정화될 때까지 잠시 대기
done
```

> **Blue-Green 배포는 왜 안 쓰나요?** Blue-Green은 서비스를 2개 세트로 운영하다가 트래픽을 전환하는 방식인데, t3.medium(RAM 4GB)에서 컨테이너를 2배로 실행하면 메모리 부족(OOM) 오류가 발생할 수 있습니다.

### 6-4. 자동 롤백

배포 후 헬스체크 실패 시 이전 코드로 자동으로 되돌립니다.

```bash
# deploy.sh에 추가
PREV_COMMIT=$(git rev-parse HEAD~1)   # 배포 전 이전 커밋 해시 저장

if ! curl -sf http://localhost/api/health; then
  echo "[deploy] 헬스체크 실패! 이전 버전($PREV_COMMIT)으로 롤백합니다..."
  git checkout "$PREV_COMMIT"
  docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
  exit 1   # GitHub Actions에 실패로 표시 → 팀에 알림
fi
```

---

## Phase 7 — 모니터링

### 7-1. Prometheus 메트릭 수집

**Prometheus**는 앱의 요청 수, 응답 시간, 에러율 등을 주기적으로 수집하는 모니터링 도구입니다.  
`prometheus-fastapi-instrumentator` 라이브러리를 추가하면 FastAPI 앱에서 자동으로 메트릭을 노출합니다.

```toml
# backend/pyproject.toml 의존성에 추가
prometheus-fastapi-instrumentator = "^6.1"
```

```python
# backend/app/main.py에 추가
from prometheus_fastapi_instrumentator import Instrumentator
Instrumentator().instrument(app).expose(app, endpoint="/metrics")
# /metrics 엔드포인트로 Prometheus가 수집할 지표를 제공합니다
```

### 7-2. Grafana 대시보드

**Grafana**는 Prometheus가 수집한 데이터를 시각적으로 보여주는 대시보드 도구입니다.  
"API가 갑자기 느려졌다", "에러가 폭증하고 있다" 같은 상황을 차트로 한눈에 파악할 수 있습니다.

Docker Compose에 `prometheus` + `grafana` 서비스를 추가하고, 아래 지표를 대시보드로 구성합니다:

- **API 에러율**: 5xx 응답 비율 — 높아지면 버그 발생 신호
- **P99 응답 시간**: 느린 요청 상위 1% 기준 — 사용자 경험 지표
- **Celery 큐 적체 수**: 처리되지 않은 ML 작업 수 — 과부하 여부 확인
- **임계치 초과 시 Slack 알림**: 문제 발생 시 팀에 자동으로 알림 전송

### 7-3. ML 예측 드리프트 감지

ML 모델은 시간이 지나면 예측 정확도가 자연히 떨어질 수 있습니다. 이를 **드리프트(drift)** 라고 합니다.  
예를 들어 주가 패턴이 몇 달 사이에 달라지면 과거 데이터로 학습한 모델의 예측이 점점 빗나가게 됩니다.

- **감지 방법**: GitHub Actions 스케줄 잡(주기적 실행) 또는 Celery Beat로 예측 오차를 자동 측정
- **임계치 초과 시**: 모델 재학습 파이프라인을 자동으로 트리거
