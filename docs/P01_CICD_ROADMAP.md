# CI/CD 및 배포 로드맵

> **최근 업데이트**: 2026-05-23

---

## 현재 상태

```
CI (지속적 통합)  ██████████  100%  — backend·ml·frontend·docker·integration 5개 잡 완비
CD (지속적 배포)  ░░░░░░░░░░    0%  — cd.yml 없음, 수동 배포만 가능
AWS 인프라        ░░░░░░░░░░    0%  — EC2·RDS 미생성, GitHub Secrets 미등록
HTTPS / 도메인    ░░░░░░░░░░    0%  — Let's Encrypt 미적용
```

### CI — 현재 동작하는 잡 (`.github/workflows/ci.yml`)

| 잡 | 실행 내용 |
|----|-----------|
| `backend` | ruff → mypy strict → pytest (SQLite in-memory, 커버리지 ≥70%) |
| `ml` | ruff → mypy → pytest (커버리지 ≥70%) |
| `frontend` | tsc → eslint → vitest → next build |
| `docker` | backend·ml·frontend `--target production` 빌드 검증 |
| `integration` | docker compose up --wait → `test_local.sh --skip-ml` e2e |

### CD + 인프라 — 아직 없는 것

- `.github/workflows/cd.yml` — **파일 자체가 없음**
- EC2 인스턴스, RDS PostgreSQL — 미생성
- GitHub Secrets 5개 — 미등록
- GitHub 브랜치 보호 규칙 — 미설정
- HTTPS 인증서 — 미발급

---

## 목표 아키텍처

```
PR 오픈 / develop 푸시
  └─▶ CI (ci.yml) — 병렬 실행
        ├─ backend·ml·frontend·docker: 정적 검증
        └─ integration: docker compose --wait → e2e

main 브랜치 머지 (브랜치 보호로 CI 통과 필수)
  └─▶ CD (cd.yml)
        ├─ GitHub Environment: production 승인
        ├─ EC2 SSH → deploy.sh
        │    ├─ git pull origin main
        │    ├─ docker compose -f ... -f docker-compose.prod.yml up --build -d
        │    └─ curl 헬스체크 → 실패 시 알림
        └─ (추후) Slack 알림
```

### 프로덕션 컨테이너 구성 (EC2 t3.medium 단일 인스턴스)

| 컨테이너 | 역할 | 외부 포트 |
|----------|------|-----------|
| `nginx` | 리버스 프록시, SSL 종료 | 80, 443 |
| `frontend` | Next.js 앱 | — (nginx 경유) |
| `backend` | FastAPI | — |
| `ml` | ML FastAPI | — |
| `celery_worker` | 비동기 ML 작업 처리 | — |
| `redis` | 메시지 브로커 + 캐시 | — (내부) |

> `postgres` 컨테이너는 `profiles: ["local"]`이므로 프로덕션에서 자동 비활성화, RDS 사용.

---

## 실행 순서

| 단계 | 문서 | 내용 |
|------|------|------|
| **1** | [P02_AWS_SETUP.md](./P02_AWS_SETUP.md) | EC2·RDS 생성, EC2 초기 설정, 첫 수동 배포 |
| **2** | [P03_CD_SETUP.md](./P03_CD_SETUP.md) | GitHub Secrets, 브랜치 보호, cd.yml 작성 |
| **3+** | [P04_IMPROVEMENTS.md](./P04_IMPROVEMENTS.md) | HTTPS, CI 강화, 무중단 배포, 모니터링 |

---

## 체크리스트

### 즉시 (Phase 1~3)

- [ ] EC2 t3.medium 생성 및 보안 그룹 설정
- [ ] RDS PostgreSQL 16 생성 (db.t3.micro, 퍼블릭 액세스 비활성화)
- [ ] EC2 초기 설정 (Docker, git clone, `.env` 작성)
- [ ] 수동 첫 배포 확인
- [ ] GitHub Secrets 5개 등록
- [ ] GitHub `production` Environment 생성
- [ ] GitHub 브랜치 보호 규칙 적용 (`main`, `develop`)
- [ ] `.github/workflows/cd.yml` 작성 및 머지

### 단기 (Phase 4~5)

- [ ] 도메인 구매 및 A 레코드 설정
- [ ] Let's Encrypt 인증서 발급 및 nginx.conf HTTPS 활성화
- [ ] CI backend 잡 PostgreSQL 전환
- [ ] Alembic migration dry-run CI 추가

### 중기 (Phase 6~7)

- [ ] deploy.sh에 alembic upgrade head 추가
- [ ] GHCR 이미지 레지스트리 도입
- [ ] Rolling Restart + 자동 롤백 적용
- [ ] Prometheus + Grafana 모니터링 구축

---

## 관련 파일

| 파일 | 역할 |
|------|------|
| [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | CI 워크플로우 (완성) |
| `.github/workflows/cd.yml` | CD 워크플로우 (미생성) |
| [`infra/scripts/deploy.sh`](../infra/scripts/deploy.sh) | EC2 배포 스크립트 (완성) |
| [`docker-compose.prod.yml`](../docker-compose.prod.yml) | 프로덕션 오버라이드 (완성) |
| [`infra/nginx/nginx.conf`](../infra/nginx/nginx.conf) | Nginx 설정 (HTTP 완성, HTTPS 주석 처리) |
| [`docs/LOCAL_TESTING_GUIDE.md`](./LOCAL_TESTING_GUIDE.md) | 로컬 통합 테스트 가이드 |
| [`CONTRIBUTING.md`](../CONTRIBUTING.md) | 브랜치 명명, 커밋 컨벤션 |
