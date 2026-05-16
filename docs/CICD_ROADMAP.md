# CI/CD 구축 로드맵

> **작성일**: 2026-05-16
> **현재 상태 상세**: [CICD_STATUS.md](./CICD_STATUS.md) 참고
> **목적**: CI/CD를 단계별로 어떻게 발전시킬지 방향과 구체적인 구현 방법을 정리한 문서

---

## 한눈에 보는 로드맵

```
현재
 │
 ├─ [Phase 1] CD 연결            ← 지금 바로 착수 가능 (1~2일)
 │    deploy.sh + cd.yml 작성
 │
 ├─ [Phase 2] CI 품질 강화        ← 1~2주
 │    커버리지 / 보안 스캔 / DB 마이그레이션 검증
 │
 ├─ [Phase 3] 배포 전략 고도화    ← 2~4주
 │    무중단 배포 / 자동 롤백 / 이미지 레지스트리
 │
 └─ [Phase 4] 모니터링 연동       ← 1~2달
      Prometheus + Grafana / Celery 큐 / ML 드리프트
```

---

## Phase 1 — CD 연결 (최우선)

> `infra/scripts/deploy.sh`와 `docker-compose.prod.yml`이 이미 갖춰져 있어
> **워크플로우 파일 하나 + GitHub Secrets 등록**만 하면 자동 배포가 됩니다.

### 1-1. `.github/workflows/cd.yml` 작성

```yaml
name: CD

on:
  push:
    branches: [main]

# main에 동시에 두 개의 배포가 실행되지 않도록 직렬화
concurrency:
  group: cd-production
  cancel-in-progress: false # 배포는 취소하지 않고 대기

jobs:
  deploy:
    name: Deploy to EC2
    runs-on: ubuntu-latest
    environment: production # GitHub 환경 보호 규칙 적용 가능

    steps:
      - name: SSH into EC2 and deploy
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.EC2_HOST }}
          username: ${{ secrets.EC2_USER }}
          key: ${{ secrets.EC2_SSH_KEY }}
          script: |
            cd /app
            bash infra/scripts/deploy.sh

      - name: Notify on failure
        if: failure()
        run: |
          echo "배포 실패 — Slack 알림 또는 이메일 발송 로직 추가"
```

**흐름 설명:**

```
main 브랜치에 머지
  → cd.yml 트리거
  → EC2에 SSH 접속
  → deploy.sh 실행
      ├── git pull origin main
      ├── docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
      └── curl localhost/api/health  (Nginx 경유 헬스체크)
  → 성공 / 실패 알림
```

### 1-2. GitHub Secrets 등록

GitHub 저장소 → **Settings → Secrets and variables → Actions** 에서 등록:

| Secret 이름   | 값                                        | 비고                                   |
| ------------- | ----------------------------------------- | -------------------------------------- |
| `EC2_HOST`    | EC2 퍼블릭 IP 또는 도메인                 |                                        |
| `EC2_USER`    | `ubuntu`                                  | AMI에 따라 다름                        |
| `EC2_SSH_KEY` | PEM 키 전체 텍스트                        | `-----BEGIN RSA PRIVATE KEY-----` 포함 |
| `RDS_URL`     | `postgresql://user:pass@endpoint/stockai` |                                        |
| `SECRET_KEY`  | JWT 서명 키                               | `openssl rand -hex 32` 로 생성         |

### 1-3. `deploy.sh` 헬스체크 수정

현재 `deploy.sh`의 `curl localhost:8001/health`는 `docker-compose.prod.yml`에서
ML 서비스 포트를 외부 노출하지 않기 때문에 항상 실패합니다.

```bash
# 수정 전
curl -sf http://localhost:8001/health && echo " ml OK"

# 수정 후 (Nginx 경유)
curl -sf http://localhost/api/health && echo " backend OK"
curl -sf http://localhost/ml/health  && echo " ml OK"
```

### 1-4. main 브랜치에 CI 적용

현재 `ci.yml`은 `pull_request: branches: [main, develop]` 으로 설정되어 있어
PR에서는 CI가 돌지만, **main에 직접 push할 경우 CI가 실행되지 않습니다**.

```yaml
# ci.yml on: 블록 수정
on:
  pull_request:
    branches: [main, develop]
  push:
    branches: [main, develop] # develop → main 추가
```

---

## Phase 2 — CI 품질 강화

> 코드가 합쳐지기 전에 더 많은 문제를 자동으로 잡습니다.

### 2-1. 테스트 커버리지 측정

커버리지를 측정하면 "테스트가 얼마나 코드를 검증하는가"를 수치로 확인할 수 있습니다.

```yaml
# ci.yml backend/ml 잡의 pytest 단계 교체
- name: Test (pytest + coverage)
  run: |
    poetry run pytest tests/ -v --tb=short \
      --cov=app \
      --cov-report=xml \
      --cov-report=term-missing \
      --cov-fail-under=70    # 커버리지 70% 미만이면 CI 실패
```

PR마다 커버리지 변화량을 코멘트로 남기려면:

```yaml
- name: Upload coverage
  uses: codecov/codecov-action@v4
  with:
    files: ./coverage.xml
    token: ${{ secrets.CODECOV_TOKEN }}
```

**권장 커버리지 목표:**

| 서비스  | 현재   | 단기 목표 | 장기 목표 |
| ------- | ------ | --------- | --------- |
| backend | 미측정 | 70%       | 85%       |
| ml      | 미측정 | 60%       | 80%       |

### 2-2. 보안 취약점 스캔

#### Python 의존성 취약점 (pip-audit)

```yaml
- name: Security scan (pip-audit)
  run: |
    pip install pip-audit
    poetry export -f requirements.txt | pip-audit -r /dev/stdin
```

#### Docker 이미지 취약점 (Trivy)

```yaml
- name: Docker image vulnerability scan (Trivy)
  uses: aquasecurity/trivy-action@master
  with:
    image-ref: backend-prod
    format: table
    exit-code: 1 # CRITICAL 취약점 발견 시 CI 실패
    severity: CRITICAL,HIGH
```

#### 코드 내 비밀 키 노출 탐지 (Gitleaks)

```yaml
- name: Secret scan (Gitleaks)
  uses: gitleaks/gitleaks-action@v2
  env:
    GITHUB_TOKEN: ${{ secrets.GITHUB_TOKEN }}
```

### 2-3. DB 마이그레이션 검증

Alembic 마이그레이션 파일이 깨진 상태로 main에 병합되는 것을 방지합니다.

```yaml
- name: Validate Alembic migrations
  run: |
    # 마이그레이션 SQL을 dry-run으로 생성 (실제 DB 없이)
    poetry run alembic upgrade head --sql > /dev/null
    echo "Migration SQL generation OK"
```

### 2-4. ML Service mypy 추가

현재 CI의 ml 잡에는 mypy가 빠져 있습니다. non-strict로 먼저 추가합니다.

```yaml
# ci.yml ml 잡에 추가
- name: Type check (mypy)
  run: poetry run mypy app --ignore-missing-imports
```

이후 `ml/pyproject.toml`의 mypy 설정을 점진적으로 강화합니다:

```toml
# ml/pyproject.toml — 단계별 강화
[tool.mypy]
# 1단계 (현재): ignore_missing_imports = true
# 2단계: disallow_untyped_defs = true
# 3단계: strict = true
```

### 2-5. 프론트엔드 단위 테스트

현재 프론트엔드는 타입 체크 + lint + 빌드만 확인합니다.
컴포넌트 단위 테스트를 추가하면 UI 버그를 PR 단계에서 잡을 수 있습니다.

```bash
# 설치
npm install -D vitest @vitejs/plugin-react @testing-library/react @testing-library/user-event jsdom
```

```json
// package.json에 추가
{
  "scripts": {
    "test": "vitest run",
    "test:watch": "vitest"
  }
}
```

```yaml
# ci.yml frontend 잡에 추가
- name: Test (vitest)
  run: npm test
```

---

## Phase 3 — 배포 전략 고도화

> 배포 중 다운타임을 없애고, 실패 시 빠르게 복구합니다.

### 3-1. 이미지 레지스트리 도입 (ECR 또는 GHCR)

**현재 문제:** EC2에서 매번 `git pull` 후 이미지를 새로 빌드 → **배포에 3~10분 소요**

**개선:** CI에서 이미지를 빌드해 레지스트리에 push → EC2는 pull만 하면 됨 → **배포 1분 이내**

```
CI (GitHub Actions)               CD (GitHub Actions)
  빌드 + 테스트 통과                  EC2 SSH 접속
    → 이미지 빌드                       → docker pull 최신 이미지
    → ECR/GHCR에 push                   → docker compose up (재시작만)
    → 태그: main-{commit_sha}
```

```yaml
# cd.yml에 추가 (GHCR 예시)
- name: Build and push images
  run: |
    echo ${{ secrets.GITHUB_TOKEN }} | docker login ghcr.io -u ${{ github.actor }} --password-stdin
    docker build --target production -t ghcr.io/${{ github.repository }}/backend:${{ github.sha }} ./backend
    docker push ghcr.io/${{ github.repository }}/backend:${{ github.sha }}
```

### 3-2. DB 마이그레이션 자동화

배포 스크립트에 마이그레이션을 포함시켜 누락을 방지합니다.

```bash
# infra/scripts/deploy.sh에 추가
echo "[deploy] Running DB migrations..."
docker compose exec -T backend poetry run alembic upgrade head
echo "[deploy] Migrations done."
```

주의: 마이그레이션은 **새 컨테이너가 뜬 직후, 트래픽을 받기 전**에 실행해야 합니다.

### 3-3. 스테이징 환경 추가

```
develop 브랜치 머지 → 스테이징 EC2 자동 배포 (자동)
main 브랜치 머지    → 프로덕션 EC2 배포 (수동 승인 후)
```

```yaml
# cd.yml에 환경 보호 규칙 추가
jobs:
  deploy-staging:
    environment: staging
    if: github.ref == 'refs/heads/develop'
    # ...

  deploy-production:
    environment: production # GitHub에서 Reviewer 지정 가능
    if: github.ref == 'refs/heads/main'
    needs: deploy-staging
    # ...
```

### 3-4. 무중단 배포 (Blue-Green)

**현재 문제:** `docker compose up --build` 실행 중 약 10~30초 다운타임 발생

**Blue-Green 개념:**

```
현재 운영 중 (Blue)
  └── 새 버전 컨테이너 시작 (Green)
        └── 헬스체크 통과 확인
              └── Nginx upstream을 Green으로 전환
                    └── Blue 컨테이너 종료
```

Nginx가 이미 있으니 upstream 전환 방식으로 구현 가능합니다:

```nginx
# nginx.conf — upstream 전환용 구조
upstream backend {
    server backend_green:8000;  # 배포 시 blue ↔ green 교체
}
```

```bash
# deploy.sh 확장 — Blue-Green 전환
CURRENT=$(docker ps --filter "name=backend_blue" -q)
if [ -n "$CURRENT" ]; then
    TARGET="green"
else
    TARGET="blue"
fi

docker compose up -d --no-deps backend_${TARGET}
sleep 5
curl -sf http://localhost/api/health || (docker stop backend_${TARGET} && exit 1)

# Nginx upstream 전환
sed -i "s/backend_[a-z]*/backend_${TARGET}/" /etc/nginx/conf.d/upstream.conf
nginx -s reload

# 이전 버전 종료
docker stop backend_$([ "$TARGET" = "blue" ] && echo "green" || echo "blue") 2>/dev/null || true
```

### 3-5. 자동 롤백

배포 후 헬스체크 실패 시 자동으로 이전 버전으로 되돌립니다.

```bash
# deploy.sh에 rollback 로직 추가
deploy() {
    docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
}

rollback() {
    echo "[deploy] Health check failed. Rolling back..."
    git reset --hard HEAD~1
    docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
    echo "[deploy] Rollback complete."
    exit 1
}

deploy || rollback

sleep 10
curl -sf http://localhost/api/health || rollback
curl -sf http://localhost/ml/health  || rollback

echo "[deploy] All health checks passed."
```

---

## Phase 4 — 모니터링 연동

> "배포가 잘 됐나?" 를 사람이 확인하지 않아도 자동으로 알 수 있어야 합니다.

### 4-1. FastAPI 메트릭 수집 (Prometheus)

```bash
# backend/pyproject.toml에 추가
poetry add prometheus-fastapi-instrumentator
```

```python
# backend/app/main.py에 추가
from prometheus_fastapi_instrumentator import Instrumentator

Instrumentator().instrument(app).expose(app)
# → GET /metrics 엔드포인트가 생성됨
```

수집 가능한 메트릭:

- 요청 수 / 응답 시간 / 에러율
- 엔드포인트별 상세 분류

### 4-2. Celery 큐 모니터링

```yaml
# docker-compose.yml에 추가
flower:
  image: mher/flower
  command: celery flower --broker=redis://redis:6379/2
  ports:
    - "5555:5555"
```

또는 `celery-exporter`로 Prometheus 메트릭으로 추출:

- 큐 대기 중인 태스크 수
- 태스크 성공/실패율
- 평균 처리 시간

### 4-3. Grafana 대시보드

```yaml
# docker-compose.yml에 추가
prometheus:
  image: prom/prometheus
  volumes:
    - ./infra/prometheus/prometheus.yml:/etc/prometheus/prometheus.yml

grafana:
  image: grafana/grafana
  ports:
    - "3001:3000"
  volumes:
    - grafana_data:/var/lib/grafana
```

**주요 대시보드 패널:**

| 패널              | 메트릭                               | 알림 조건     |
| ----------------- | ------------------------------------ | ------------- |
| API 에러율        | `http_requests_total{status=~"5.."}` | 1분간 5% 초과 |
| 응답 시간 P99     | `http_request_duration_seconds`      | 1초 초과      |
| Celery 큐 대기    | `celery_queue_length`                | 100개 초과    |
| ML 예측 소요 시간 | 커스텀 메트릭                        | 5초 초과      |

### 4-4. ML 예측 드리프트 감지

ML 모델이 시간이 지남에 따라 성능이 떨어지는 것을 자동으로 탐지합니다.

```python
# ml/app/services/monitoring.py 신규 작성
import statistics

class PredictionMonitor:
    def __init__(self):
        self.recent_errors: list[float] = []

    def record(self, predicted: float, actual: float):
        error = abs(predicted - actual) / actual
        self.recent_errors.append(error)
        if len(self.recent_errors) > 100:
            self.recent_errors.pop(0)

    def check_drift(self, threshold: float = 0.1) -> bool:
        """최근 100건의 평균 오차가 threshold를 넘으면 드리프트로 판단"""
        if len(self.recent_errors) < 10:
            return False
        return statistics.mean(self.recent_errors) > threshold
```

드리프트 감지 시 → Slack 알림 → 모델 재학습 트리거

### 4-5. 배포 알림

```yaml
# cd.yml에 Slack 알림 추가
- name: Notify Slack
  if: always()
  uses: slackapi/slack-github-action@v1.26.0
  with:
    payload: |
      {
        "text": "${{ job.status == 'success' && '✅ 배포 성공' || '❌ 배포 실패' }}",
        "blocks": [{
          "type": "section",
          "text": {
            "type": "mrkdwn",
            "text": "*${{ job.status == 'success' && '✅ 배포 성공' || '❌ 배포 실패' }}*\n브랜치: `${{ github.ref_name }}`\n커밋: `${{ github.sha }}`\n작성자: ${{ github.actor }}"
          }
        }]
      }
  env:
    SLACK_WEBHOOK_URL: ${{ secrets.SLACK_WEBHOOK_URL }}
```

---

## 전체 목표 아키텍처 (완성 시)

```
PR 오픈
  └─▶ CI (ci.yml) — 병렬 실행
        ├─ backend: ruff + mypy(strict) + pytest(PostgreSQL) + pip-audit
        ├─ ml:      ruff + mypy + pytest + 커버리지
        ├─ frontend: tsc + eslint + vitest + next build
        └─ docker:  이미지 빌드 + Trivy 보안 스캔

develop 머지
  └─▶ CD (cd.yml)
        └─ Staging EC2 자동 배포

main 머지
  └─▶ CD (cd.yml)
        ├─ Reviewer 수동 승인
        ├─ ECR에 이미지 빌드 & 푸시
        ├─ Production EC2 SSH → deploy.sh
        │    ├─ Blue-Green 무중단 배포
        │    ├─ alembic upgrade head
        │    └─ 헬스체크 → 실패 시 자동 롤백
        └─ Slack 알림

운영 중
  └─▶ Prometheus + Grafana 메트릭 수집
        ├─ API 에러율 / 응답 시간 알림
        ├─ Celery 큐 적체 알림
        └─ ML 예측 드리프트 감지 → 모델 재학습 트리거
```

---

## 단계별 체크리스트

### Phase 1 — CD 연결

- [ ] `deploy.sh` 헬스체크 URL 수정 (`localhost/ml/health`)
- [ ] `.github/workflows/cd.yml` 작성
- [ ] GitHub Secrets 5개 등록
- [ ] `ci.yml`에 `push: branches: [main]` 추가
- [ ] 테스트 배포 실행 및 확인

### Phase 2 — CI 품질 강화

- [ ] `pytest --cov` 커버리지 측정 추가
- [ ] `pip-audit` 보안 스캔 추가
- [ ] Trivy Docker 이미지 스캔 추가
- [ ] Gitleaks 시크릿 탐지 추가
- [ ] ml 잡에 mypy 추가 (non-strict)
- [ ] Alembic 마이그레이션 dry-run 검증 추가
- [ ] Frontend Vitest 단위 테스트 추가

### Phase 3 — 배포 전략 고도화

- [ ] ECR 또는 GHCR 레지스트리 연동
- [ ] `deploy.sh`에 alembic 마이그레이션 추가
- [ ] 스테이징 환경 추가 (별도 EC2)
- [ ] Nginx Blue-Green 전환 구조 설계
- [ ] 자동 롤백 로직 추가

### Phase 4 — 모니터링

- [ ] `prometheus-fastapi-instrumentator` 설치 및 `/metrics` 노출
- [ ] Flower 또는 celery-exporter 설정
- [ ] Prometheus + Grafana docker-compose 추가
- [ ] Grafana 대시보드 구성 (에러율, 응답시간, 큐 대기)
- [ ] ML 드리프트 모니터링 서비스 작성
- [ ] Slack 배포 알림 연동

---

## 관련 파일

| 파일                                                      | 역할                             |
| --------------------------------------------------------- | -------------------------------- |
| [`CICD_STATUS.md`](./CICD_STATUS.md)                      | 현재 CI/CD 상세 현황 및 Gap 분석 |
| [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | CI 워크플로우                    |
| [`docker-compose.prod.yml`](../docker-compose.prod.yml)   | 프로덕션 Docker 설정             |
| [`infra/scripts/deploy.sh`](../infra/scripts/deploy.sh)   | EC2 배포 스크립트                |
| [`infra/nginx/nginx.conf`](../infra/nginx/nginx.conf)     | Nginx 라우팅 설정                |
| [`infra/docs/AWS_SETUP.md`](../infra/docs/AWS_SETUP.md)   | AWS 인프라 설정 가이드           |
