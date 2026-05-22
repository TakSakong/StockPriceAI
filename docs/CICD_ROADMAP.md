# CI/CD 및 배포 구축 로드맵 (CI/CD & Deployment Roadmap)

> **최근 업데이트**: 2026-05-22 (실제 코드 반영 재점검)  
> **목적**: StockPriceAI 프로젝트의 CI(지속적 통합) 현황 및 CD(지속적 배포) 구축 방안을 일원화하여 관리하기 위한 문서입니다.

---

## 1. 전체 현황 및 목표 아키텍처

### 📊 현재 구축 수준
```
CI (지속적 통합)  █████████░  90%  (mypy·Docker smoke test 추가 완료, 프론트엔드 테스트·PG 연동 미비)
CD (지속적 배포)  ██░░░░░░░░  20%  (EC2 배포 스크립트 작성 완료, CD 워크플로우 없음)
인프라 설계       ████████░░  80%  (Nginx, Docker Compose prod 구성 완료, AWS 실제 구축 대기)
```

### 🏗️ 전체 목표 아키텍처 (완성 시)
```
PR 오픈 / 푸시 (develop, main)
  └─▶ CI (ci.yml) — 병렬 실행
        ├─ backend: ruff + mypy(strict) + pytest(SQLite -> Postgres) + pip-audit
        ├─ ml:      ruff + mypy + pytest + 커버리지
        └─ frontend: tsc + eslint + vitest + next build

main 브랜치 머지
  └─▶ CD (cd.yml)
        ├─ CI 완료 대기 (needs)
        ├─ ECR/GHCR 이미지 빌드 & 푸시 (도입 예정)
        ├─ Production EC2 SSH 접속 -> deploy.sh 실행
        │    ├─ Rolling Restart 무중단 배포 (docker compose up -d --no-deps 서비스별 순차 재시작)
        │    ├─ alembic upgrade head (DB 마이그레이션 자동화)
        │    └─ Nginx 경유 헬스체크 -> 실패 시 자동 롤백
        └─ Slack/이메일 알림
```

---

## 2. CI/CD 현재 상세 현황 및 Gap 분석

### 2-1. CI 현황 (`.github/workflows/ci.yml`)
`main`/`develop` 브랜치 PR 및 `develop` 푸시 시 3개 서비스(Backend, ML, Frontend)에 대한 테스트 및 검증이 병렬로 실행됩니다. 새 커밋이 오면 이전 실행을 자동 취소하도록 concurrency 제어가 적용되어 있습니다.

* **Backend (`backend/`)**: `ruff` Lint, `mypy` strict 모드 타입 체크, `pytest` 비동기 테스트(SQLite in-memory) 실행
* **ML Service (`ml/`)**: `ruff` Lint, `pytest` 기술적 지표 계산 로직 및 헬스체크 테스트 실행
* **Frontend (`frontend/`)**: `tsc` 타입 체크, `eslint` Lint, `next build` 번들 빌드 성공 확인

#### ✅ 해결 완료된 CI 항목
* ~~**[GAP-CI-1] ML Service mypy 미적용**~~ → **해결**: `ci.yml`의 ML 잡에 `poetry run mypy app` 단계가 추가되어 있습니다.
* ~~**[GAP-CI-3] Docker 이미지 빌드 검증 누락**~~ → **해결**: `ci.yml`에 `docker` job이 추가되어 backend/ml/frontend 모두 `--target production` 빌드를 검증합니다.

#### ⚠️ CI 개선이 필요한 부분 (CI Gaps)
* **[GAP-CI-1] 프론트엔드 테스트 부재**: `package.json`에 `test` 스크립트와 테스트 파일이 없어 단순 빌드 성공 여부만 검증합니다.
* **[GAP-CI-2] Backend 테스트가 SQLite를 사용**: psycopg2를 우회하여 SQLite in-memory DB로 테스트하므로 PostgreSQL 고유 쿼리 사용 시 프로덕션 버그를 예방하기 어렵습니다.

---

### 2-2. CD 및 배포 현황
로컬 Docker Compose(`docker-compose.yml`) 및 RDS 연동용 프로덕션 오버라이드([`docker-compose.prod.yml`](../docker-compose.prod.yml)), Nginx 라우팅([`infra/nginx/nginx.conf`](../infra/nginx/nginx.conf)), 배포 스크립트([`infra/scripts/deploy.sh`](../infra/scripts/deploy.sh))가 완성되어 있습니다.

#### ✅ 해결 완료된 CD 항목
* ~~**[GAP-CD-3] 배포 후 헬스체크 오류**~~ → **해결**: `deploy.sh`가 이미 Nginx 리버스 프록시 경유 방식(`curl http://localhost/api/health`, `curl http://localhost/ml/health`)으로 수정되어 있습니다.

#### ⚠️ CD 개선이 필요한 부분 (CD Gaps)
* **[GAP-CD-1] CD 워크플로우 파일 부재**: EC2 배포 스크립트는 존재하나 이를 트리거할 `.github/workflows/cd.yml` 파일이 없어 배포가 수동으로 진행되어야 합니다.
* **[GAP-CD-2] GitHub Secrets 미등록**: AWS 인프라(EC2, RDS)가 구동되지 않아 `EC2_HOST`, `EC2_USER`, `EC2_SSH_KEY`, `RDS_URL`, `SECRET_KEY`가 등록되어 있지 않습니다.
* **[GAP-CD-3] HTTPS 미적용**: 도메인 및 Let's Encrypt SSL 인증서 발급 프로세스 설정이 안 되어 있습니다.

---

## 3. 단계별 배포 로드맵

### 🚀 Phase 1 — CD 연결 및 AWS 최초 배포 (최우선)
> **목표**: AWS 기본 인프라를 구축하고 GitHub Actions를 통해 자동 배포를 수행합니다.

#### 1. AWS 인프라 생성 ([`AWS_SETUP.md`](../infra/docs/AWS_SETUP.md) 절차 실행)
* **EC2**: Ubuntu 22.04 LTS (**t3.medium 권장** — ML 서비스 + Celery OOM 방지에 4GB RAM 필요), 보안 그룹(SSH 22, HTTP 80, HTTPS 443) 설정
* **RDS**: PostgreSQL 16 (db.t3.micro 프리티어), 퍼블릭 액세스 차단 (EC2 보안 그룹에서만 5432 허용)

#### 2. ✅ `deploy.sh` 헬스체크 수정 ([`deploy.sh`](../infra/scripts/deploy.sh)) — **완료**
Nginx 리버스 프록시 주소로 헬스체크가 이미 수정되어 있습니다.
```bash
# 현재 deploy.sh (Nginx 경유 확인 — 적용 완료)
curl -sf http://localhost/api/health && echo " backend OK"
curl -sf http://localhost/ml/health  && echo " ml OK"
```

#### 3. GitHub 브랜치 보호 규칙 설정 (cd.yml 추가 전 필수)

> **주의**: CD 워크플로우는 별도 파일이므로 `needs:`로 CI 워크플로우 완료를 직접 연결할 수 없습니다.
> CI 통과 없이 `main`에 머지되는 것을 코드 레벨에서 막으려면 **GitHub 브랜치 보호 규칙**이 반드시 선행되어야 합니다.

GitHub 저장소 → **Settings → Branches → Add rule** 에서 아래 규칙을 적용합니다.

| 브랜치 | 설정 항목 | 값 |
|--------|-----------|-----|
| `main` | Require a pull request before merging | ✅ |
| `main` | Require status checks to pass: `backend`, `ml`, `frontend`, `docker` | ✅ |
| `main` | Do not allow bypassing the above settings | ✅ |
| `develop` | Require a pull request before merging | ✅ |
| `develop` | Require status checks to pass: `backend`, `ml`, `frontend`, `docker` | ✅ |

이 설정이 완료된 이후에야 CD 배포가 "CI 통과된 코드만 main에 올 수 있다"는 보장 위에서 동작합니다.

#### 4. `.github/workflows/cd.yml` 작성
`main` 브랜치에 머지(push) 시 작동하는 CD 워크플로우를 추가합니다.
```yaml
name: CD

on:
  push:
    branches: [main]
    # ↑ PR 머지 시 GitHub이 발생시키는 push 이벤트로 트리거됨.
    #   브랜치 보호 규칙(위 3번 항목)으로 CI 통과 없이는
    #   main에 머지 자체가 불가능하도록 강제해야 함.

concurrency:
  group: cd-production
  cancel-in-progress: false

jobs:
  deploy:
    name: Deploy to EC2
    runs-on: ubuntu-latest
    environment: production

    steps:
      - name: SSH into EC2 and deploy
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.EC2_HOST }}
          username: ${{ secrets.EC2_USER }}
          key: ${{ secrets.EC2_SSH_KEY }}
          script: |
            cd /app
            git pull origin main
            bash infra/scripts/deploy.sh
```

#### 4. GitHub Secrets 등록
* `EC2_HOST`: EC2 퍼블릭 IP/도메인
* `EC2_USER`: `ubuntu`
* `EC2_SSH_KEY`: SSH PEM 키 내용 전체
* `RDS_URL`: `postgresql://user:password@rds-endpoint/stockai`
* `SECRET_KEY`: JWT 서명 키 (`openssl rand -hex 32`)

---

### 🛡️ Phase 2 — CI 품질 강화
> **목표**: 빌드 전 자동화 검사를 꼼꼼하게 보완하여 잠재적인 배포 장애를 차단합니다.

* ~~**ML Service mypy 추가**~~ ✅ **완료**: `ci.yml` ML 잡에 `poetry run mypy app` 단계가 이미 추가되어 있습니다.
* **Frontend 테스트 도입**: Vitest + React Testing Library 설정 및 `package.json`에 `test` 스크립트 작성, `ci.yml`에 `npm test` 단계 추가
* ~~**Docker 빌드 사전 검증**~~ ✅ **완료**: `ci.yml`에 `docker` job이 추가되어 backend/ml/frontend 모두 production 타겟 빌드를 검증합니다.
* **Alembic 마이그레이션 Dry-Run**: 마이그레이션 스크립트 오류를 CI에서 잡기 위해 `--sql` dry-run 실행 검증 단계 추가

---

### 🔄 Phase 3 — 배포 전략 고도화 (무중단 & 안전성)
> **목표**: 배포 시 발생하는 서비스 다운타임을 없애고 예외 발생 시 자동으로 롤백합니다.

* **DB 마이그레이션 자동화**: `deploy.sh`에 `docker compose exec -T backend poetry run alembic upgrade head` 명령어를 포함하여 배포와 동시에 마이그레이션 실행
* **이미지 레지스트리 도입 (ECR/GHCR)**:
  - 현재: EC2 내에서 매번 `git pull` 후 소스 빌드 (3~10분 소요)
  - 개선: CI가 완료되면 이미지를 빌드해 레지스트리에 push하고, EC2는 이미지를 pull만 받아 재시작 (1분 미만 소요)
* **Rolling Restart 무중단 배포**: `docker compose up -d --no-deps <service>` 명령으로 서비스별 순차 재시작 (t3.medium 단일 인스턴스에서 Blue-Green은 컴테이너를 두 배로 돌려야 해 OOM 위험, Rolling Restart가 현실적인 대안)
* **자동 롤백 시스템**: 배포 직후 헬스체크 응답이 비정상이면 자동으로 `git reset` 및 이전 안정 버전 컨테이너로 원복 실행

---

### 📈 Phase 4 — 모니터링 연동
> **목표**: 배포 이후 실시간 서비스 성능 지표를 수집하고 알림을 설정합니다.

* **Prometheus 메트릭 노출**: `prometheus-fastapi-instrumentator`를 backend 패키지에 추가하여 `/metrics` 엔드포인트 활성화
* **Grafana 대시보드 구축**: API 에러율, P99 응답 속도, Celery 큐 적체 현황 시각화 및 임계치 초과 시 Slack 경보 송출
* **ML 예측 드리프트 감지**: 주기적인 성능 측정 스크립트 구동으로 예측 오차가 임계치를 넘어서면 모델 재학습 파이프라인 트리거

---

## 4. 관련 문서 및 리소스

* **로컬 통합 테스트**: [`LOCAL_TESTING_GUIDE.md`](./LOCAL_TESTING_GUIDE.md) — 로컬에서 전체 연동 확인 시 참조
* **AWS 설정 가이드**: [`AWS_SETUP.md`](../infra/docs/AWS_SETUP.md) — AWS 최초 인프라 설치 명령어 모음
* **기여 규칙**: [`CONTRIBUTING.md`](../CONTRIBUTING.md) — 브랜치 명명, 커밋 컨벤션 및 팀 업무 분담표
