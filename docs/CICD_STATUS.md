# CI/CD 현황 및 로드맵

> **작성일**: 2026-05-15  
> **현재 브랜치**: `chore/INFRA-ci-strict-checks`  
> **요약**: CI(지속적 통합)는 3개 서비스 모두 동작 중이나 일부 보완이 필요하고, CD(지속적 배포)는 인프라 설계는 완료됐으나 워크플로우 파일이 없어 자동 배포가 아직 불가능한 상태입니다.

---

## 전체 현황 요약

```
CI (지속적 통합)  ████████░░  80%
CD (지속적 배포)  ██░░░░░░░░  20%
인프라 설계       ████████░░  80%
```

---

## 1. CI — 현재 구축된 것

### 워크플로우 파일 (`.github/workflows/ci.yml`)

`main`/`develop` 브랜치 PR과 `develop` 푸시 시 3개 잡이 병렬 실행됩니다.  
같은 브랜치에서 새 커밋이 오면 이전 실행을 자동 취소하는 concurrency 제어도 적용되어 있습니다.

#### Backend 잡 (`backend/`)

| 단계 | 도구 | 설정 |
|------|------|------|
| Lint | ruff | `select = ["E","F","I","UP"]`, `line-length = 100` |
| 타입 체크 | mypy | `strict = true` — 가장 엄격한 수준 |
| 테스트 | pytest | SQLite in-memory DB, `asyncio_mode = auto` |
| 캐시 | Poetry virtualenv | `poetry.lock` 해시 기준 |

현재 테스트 파일 목록:

```
backend/tests/
├── conftest.py       # SQLite override, auth_headers fixture
├── test_auth.py      # 회원가입/로그인/토큰 검증
├── test_health.py    # /api/health 엔드포인트
└── test_watchlist.py # 관심종목 CRUD
```

#### ML Service 잡 (`ml/`)

| 단계 | 도구 | 설정 |
|------|------|------|
| Lint | ruff | `select = ["E","F","I","UP"]`, `line-length = 100` |
| 테스트 | pytest | `asyncio_mode = auto` |
| 캐시 | Poetry virtualenv | `poetry.lock` 해시 기준 |

현재 테스트 파일 목록:

```
ml/tests/
├── test_health.py     # /health 엔드포인트
└── test_technical.py  # 기술 지표 계산 로직 (75줄)
```

#### Frontend 잡 (`frontend/`)

| 단계 | 도구 | 설명 |
|------|------|------|
| 타입 체크 | tsc --noEmit | tsconfig.json 기준 |
| Lint | eslint | next lint |
| 빌드 | next build | 번들 빌드 성공 여부 확인 |
| 캐시 | npm | `package-lock.json` 해시 기준 |

---

## 2. CD — 현재 구축된 것

### 인프라 설계 (완료)

| 파일 | 내용 | 상태 |
|------|------|------|
| `docker-compose.yml` | 개발 스택 전체 (6개 서비스) | ✅ |
| `docker-compose.prod.yml` | 프로덕션 오버라이드 (RDS 연결, 소스 마운트 제거, 포트 비노출) | ✅ |
| `infra/nginx/nginx.conf` | `/api/`, `/ml/`, `/ws/`, `/` 라우팅 (HTTPS 블록 주석 준비) | ✅ |
| `infra/scripts/deploy.sh` | EC2에서 git pull 후 docker compose up --build 실행 | ✅ |
| `infra/docs/AWS_SETUP.md` | EC2/RDS 수동 설정 절차, 필요한 GitHub Secrets 목록 | ✅ |

### Docker 이미지 구조 (완료)

모든 서비스(backend, ml, frontend, nginx)가 `development` / `production` 멀티스테이지 Dockerfile을 갖추고 있습니다.

```
프로덕션 실행 명령:
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

### 필요한 GitHub Secrets (목록 확인됨, 실제 등록은 미완)

| Secret 이름 | 값 |
|------------|-----|
| `EC2_HOST` | EC2 퍼블릭 IP 또는 도메인 |
| `EC2_SSH_KEY` | PEM 키 전체 텍스트 |
| `RDS_URL` | `postgresql://user:pass@rds-endpoint/stockai` |
| `SECRET_KEY` | JWT 서명 키 (`openssl rand -hex 32`) |

---

## 3. 현재 갭 (Gap) 분석

### CI 갭

#### [GAP-CI-1] ML Service mypy 미적용

`ci.yml`의 ml 잡에 mypy 단계가 없습니다. backend는 `strict = true`로 가장 엄격하게 검사하는데 ml은 타입 체크가 전혀 없습니다.

```yaml
# ci.yml ml 잡에 추가 필요
- name: Type check (mypy)
  run: poetry run mypy app
```

ml의 `pyproject.toml`에는 mypy 설정이 이미 있으나(`ignore_missing_imports = true`) strict 모드는 꺼져 있습니다. 먼저 non-strict로 추가하고 이후 strict로 올리는 것을 권장합니다.

#### [GAP-CI-2] 프론트엔드 테스트 없음

`frontend/package.json`에 `test` 스크립트가 없고 테스트 파일도 존재하지 않습니다. CI에서 `npm run build`가 성공하는 것은 확인하지만 컴포넌트/로직 단위 검증은 전혀 없습니다.

#### [GAP-CI-3] Docker 이미지 빌드 검증 없음

CI가 통과해도 실제 Docker 이미지 빌드가 깨질 수 있습니다. 특히 `production` 타겟에서 `--only main` 설치 후 누락 패키지가 생기는 경우를 잡지 못합니다.

#### [GAP-CI-4] Backend 테스트가 SQLite를 사용

`conftest.py`가 SQLite in-memory DB로 psycopg2를 우회합니다. PostgreSQL 고유 쿼리(JSON 컬럼, 특정 인덱스 타입 등)를 사용할 경우 CI는 통과하지만 프로덕션에서 실패할 수 있습니다.

### CD 갭

#### [GAP-CD-1] CD 워크플로우 파일 없음 ← 가장 큰 갭

`deploy.sh`의 주석에 "GitHub Actions CD에서 SSH로 호출됨"이라고 명시되어 있지만 `.github/workflows/cd.yml`이 존재하지 않습니다. 현재 배포는 100% 수동입니다.

만들어야 할 워크플로우 구조:

```yaml
on:
  push:
    branches: [main]

jobs:
  deploy:
    needs: [backend, ml, frontend]  # ci.yml 잡이 완료된 후 실행
    steps:
      - SSH into EC2 (appleboy/ssh-action)
      - run: bash /app/infra/scripts/deploy.sh
```

#### [GAP-CD-2] GitHub Secrets 미등록

AWS 인프라가 실제로 구성되어 있지 않으면 Secrets 등록도 불가능합니다. EC2와 RDS 생성이 선행되어야 합니다.

#### [GAP-CD-3] 배포 후 헬스체크 불완전

`deploy.sh`가 `curl localhost:8001/health`를 실행하는데, `docker-compose.prod.yml`에서 ml 서비스의 포트를 외부 노출하지 않으므로(`ports: []`) 이 curl은 항상 실패합니다.  
수정 방향: `curl localhost/ml/health` (Nginx 경유) 또는 `docker exec`로 컨테이너 내부에서 호출.

#### [GAP-CD-4] 스테이징 환경 없음

현재 플로우는 `main` 머지 → 즉시 프로덕션입니다. 배포 전 검증 단계가 없습니다.

#### [GAP-CD-5] HTTPS 미적용

`nginx.conf`에 HTTPS 블록이 주석으로 준비되어 있으나 활성화되지 않았습니다. Let's Encrypt 인증서 발급 및 도메인 연결이 필요합니다.

---

## 4. 향후 작업 목록 (우선순위 순)

### Phase A — CD 워크플로우 완성 (최우선)

- [ ] **A-1** `.github/workflows/cd.yml` 작성
  - `main` 푸시 시 트리거, CI 잡 완료를 `needs`로 대기
  - `appleboy/ssh-action`으로 EC2 SSH 접속 후 `deploy.sh` 실행
  - 완료 후 Slack/이메일 알림 (선택)
- [ ] **A-2** AWS 인프라 생성 (`infra/docs/AWS_SETUP.md` 절차 실행)
  - EC2 인스턴스 (ubuntu-22.04, t3.small 이상 권장)
  - RDS PostgreSQL 16 (db.t3.micro)
  - EC2에 Docker, git, `/app` 초기 설정
- [ ] **A-3** GitHub Secrets 4개 등록 (`EC2_HOST`, `EC2_SSH_KEY`, `RDS_URL`, `SECRET_KEY`)
- [ ] **A-4** `deploy.sh` 헬스체크 수정 (`curl localhost/ml/health`)

### Phase B — CI 품질 강화

- [ ] **B-1** `ci.yml` ml 잡에 mypy 단계 추가 (non-strict로 시작)
- [ ] **B-2** Frontend 테스트 도입
  - Vitest + React Testing Library 권장
  - `package.json`에 `"test": "vitest run"` 스크립트 추가
  - `ci.yml` frontend 잡에 `npm test` 단계 추가
- [ ] **B-3** CI에 Docker 빌드 검증 추가
  ```yaml
  - name: Build Docker images (smoke test)
    run: |
      docker build --target production -t backend-prod ./backend
      docker build --target production -t ml-prod ./ml
      docker build --target production -t frontend-prod ./frontend
  ```

### Phase C — 배포 안정성

- [ ] **C-1** HTTPS 활성화
  - 도메인 등록 또는 EC2 Elastic IP 확보
  - EC2에서 `certbot --standalone` 으로 Let's Encrypt 인증서 발급
  - `nginx.conf`의 HTTPS 블록 주석 해제 및 도메인 삽입
- [ ] **C-2** 스테이징 환경 추가 (선택)
  - `develop` → staging EC2 자동 배포
  - `main` → production EC2 수동 승인 후 배포 (`environment: production` + reviewers)
- [ ] **C-3** DB 마이그레이션 자동화
  - `deploy.sh`에 `docker exec backend poetry run alembic upgrade head` 추가
  - 현재는 마이그레이션이 배포 플로우에 포함되어 있지 않음
- [ ] **C-4** 롤백 절차 문서화
  - `git revert` + 재배포, 또는 이전 이미지 태그로 롤백하는 절차

### Phase D — 장기 개선

- [ ] **D-1** 이미지 레지스트리 도입 (ECR 또는 GHCR)
  - 현재는 EC2에서 `git pull` 후 매번 이미지를 새로 빌드 — 배포 시간 3~10분 소요
  - CI에서 이미지 빌드 & 푸시 → CD에서 pull만 하면 배포 시간 단축
- [ ] **D-2** ml mypy strict 모드 적용 (B-1 이후)
- [ ] **D-3** Backend 테스트 PostgreSQL 전환
  - GitHub Actions의 `services`로 postgres 컨테이너 올리기
  - SQLite 우회 제거로 프로덕션과 동일한 환경에서 테스트
- [ ] **D-4** Dependabot 또는 Renovate 설정 (의존성 자동 업데이트)

---

## 5. 전체 목표 아키텍처 (완성 시)

```
PR 오픈
  └─▶ CI (ci.yml)
        ├─ backend: ruff + mypy(strict) + pytest(postgres)
        ├─ ml:      ruff + mypy + pytest
        └─ frontend: tsc + eslint + vitest + next build

main 머지
  └─▶ CD (cd.yml)
        ├─ CI 완료 대기 (needs)
        ├─ ECR에 이미지 빌드 & 푸시
        ├─ EC2 SSH → deploy.sh (docker pull + compose up)
        ├─ alembic upgrade head
        ├─ 헬스체크 (Nginx 경유)
        └─ 슬랙 알림
```

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | CI 워크플로우 |
| [`docker-compose.yml`](../docker-compose.yml) | 개발 스택 |
| [`docker-compose.prod.yml`](../docker-compose.prod.yml) | 프로덕션 오버라이드 |
| [`infra/scripts/deploy.sh`](../infra/scripts/deploy.sh) | EC2 배포 스크립트 |
| [`infra/nginx/nginx.conf`](../infra/nginx/nginx.conf) | Nginx 라우팅 설정 |
| [`infra/docs/AWS_SETUP.md`](../infra/docs/AWS_SETUP.md) | AWS 수동 설정 가이드 |
