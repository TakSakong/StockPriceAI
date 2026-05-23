# CI/CD 및 배포 로드맵

> **최근 업데이트**: 2026-05-23

---

## 이 문서를 먼저 읽으세요 — 전체 그림

**CI/CD**는 처음 들으면 어렵게 느껴지지만, 핵심은 이것 하나입니다.

> **"코드를 GitHub에 올리면 → 자동으로 테스트하고 → 테스트 통과 시 자동으로 서버에 배포"**

이것을 자동화하는 것이 이 로드맵의 목표입니다.

### 용어 정리

| 용어 | 의미 |
|------|------|
| **CI** (Continuous Integration, 지속적 통합) | 코드를 push할 때마다 자동으로 테스트를 돌려 코드 품질을 확인 |
| **CD** (Continuous Deployment, 지속적 배포) | CI 통과 후 자동으로 실제 서버에 코드를 반영 |
| **GitHub Actions** | CI/CD를 실행시켜 주는 GitHub 내장 자동화 도구 |
| **EC2** | AWS에서 빌리는 가상 서버 (우리 앱이 실제로 돌아가는 컴퓨터) |
| **RDS** | AWS에서 제공하는 관리형 데이터베이스 서비스 |

---

## 현재 상태

```
CI (지속적 통합)  ██████████  100%  — backend·ml·frontend·docker·integration 5개 잡 완비
CD (지속적 배포)  ░░░░░░░░░░    0%  — cd.yml 없음, 수동 배포만 가능
AWS 인프라        ░░░░░░░░░░    0%  — EC2·RDS 미생성, GitHub Secrets 미등록
HTTPS / 도메인    ░░░░░░░░░░    0%  — Let's Encrypt 미적용
```

### CI — 현재 자동으로 돌아가는 테스트 (`.github/workflows/ci.yml`)

코드를 push하거나 PR을 열 때마다 아래 5가지 테스트가 자동으로 실행됩니다.

| 잡 이름 | 하는 일 |
|---------|---------|
| `backend` | 코드 스타일 검사 → 타입 검사 → 단위 테스트 (커버리지 ≥70%) |
| `ml` | ML 서비스 코드 스타일 → 타입 검사 → 단위 테스트 (커버리지 ≥70%) |
| `frontend` | 타입 검사 → 린트 → 단위 테스트 → 빌드 검증 |
| `docker` | backend·ml·frontend Docker 이미지가 실제로 빌드되는지 확인 |
| `integration` | Docker로 전체 스택을 올린 뒤 실제 API가 응답하는지 E2E 테스트 |

### CD + 인프라 — 아직 없는 것

아래 항목들이 없어서 지금은 배포를 손으로 직접 해야 합니다.

- `.github/workflows/cd.yml` — **CD 자동화 워크플로우 파일 자체가 없음**
- EC2 인스턴스, RDS PostgreSQL — AWS에 아직 서버를 생성하지 않음
- GitHub Secrets 5개 — 서버 접속 정보를 GitHub에 아직 등록하지 않음
- GitHub 브랜치 보호 규칙 — 테스트 실패한 코드가 main에 들어오지 못하도록 막는 규칙
- HTTPS 인증서 — 안전한 `https://` 접속을 위한 인증서

---

## 목표 아키텍처

완성 후 코드가 배포되는 흐름입니다.

```
개발자가 PR 오픈 또는 develop에 push
  └─▶ CI 자동 실행 (병렬로 빠르게)
        ├─ backend / ml / frontend / docker: 코드 품질·타입·빌드 검사
        └─ integration: 실제 서비스처럼 Docker 올려서 API 응답 확인

CI 통과한 코드를 main에 머지 (브랜치 보호 규칙으로 CI 미통과 시 머지 불가)
  └─▶ CD 자동 실행
        ├─ GitHub "production" 환경 승인 (선택 사항)
        └─ EC2 서버에 SSH 접속 → deploy.sh 실행
             ├─ git pull origin main        ← 최신 코드 받기
             ├─ docker compose up --build  ← 새 이미지로 서비스 교체
             └─ curl 헬스체크              ← 서비스 정상 확인
```

### 프로덕션 서버 구성 (EC2 t3.medium 단일 인스턴스)

EC2 한 대 안에서 아래 6개 컨테이너가 Docker로 돌아갑니다.

| 컨테이너 | 역할 | 외부에서 접근 가능? |
|----------|------|---------------------|
| `nginx` | 외부 요청을 받아 내부 서비스로 분배, HTTPS 처리 | 포트 80, 443 |
| `frontend` | Next.js 웹 앱 | nginx 경유만 가능 |
| `backend` | FastAPI 백엔드 API | nginx 경유만 가능 |
| `ml` | ML 예측 FastAPI | nginx 경유만 가능 |
| `celery_worker` | 무거운 ML 작업을 백그라운드에서 비동기 처리 | 내부만 |
| `redis` | celery 작업 큐 + 캐시 저장소 | 내부만 |

> **postgres 컨테이너는 왜 없나요?** 로컬 개발용으로만 Docker postgres를 쓰고, 실제 서버에서는 AWS RDS(관리형 DB)를 사용합니다. `profiles: ["local"]` 설정으로 프로덕션에서 자동으로 비활성화됩니다.

---

## 실행 순서

이 순서대로 진행하세요. 각 단계를 완전히 완료한 후 다음 단계로 넘어가세요.

| 단계 | 문서 | 해야 할 일 |
|------|------|------------|
| **1단계** | [P02_AWS_SETUP.md](./P02_AWS_SETUP.md) | AWS에 서버(EC2)와 데이터베이스(RDS) 만들기 + 첫 수동 배포 확인 |
| **2단계** | [P03_CD_SETUP.md](./P03_CD_SETUP.md) | GitHub에 서버 접속 정보 등록 + 자동 배포 워크플로우 만들기 |
| **3단계 이후** | [P04_IMPROVEMENTS.md](./P04_IMPROVEMENTS.md) | HTTPS 적용, CI 강화, 무중단 배포, 모니터링 |

---

## 체크리스트

완료할 때마다 `- [ ]`를 `- [x]`로 바꾸며 진행하세요.

### 즉시 처리 (1~3단계)

- [ ] EC2 t3.medium 인스턴스 생성 및 보안 그룹 설정
- [ ] RDS PostgreSQL 16 생성 (db.t3.micro, 퍼블릭 액세스 비활성화)
- [ ] EC2 초기 환경 설정 (Docker 설치, 코드 클론, `.env` 작성)
- [ ] 첫 수동 배포 — 앱이 실제로 뜨는지 확인
- [ ] GitHub Secrets 5개 등록 (서버 접속 정보)
- [ ] GitHub `production` Environment 생성
- [ ] GitHub 브랜치 보호 규칙 적용 (`main`, `develop`)
- [ ] `.github/workflows/cd.yml` 작성 및 머지 → 자동 배포 동작 확인

### 단기 개선 (4~5단계)

- [ ] 도메인 구매 및 A 레코드 설정 (EC2 IP 연결)
- [ ] Let's Encrypt SSL 인증서 발급 → HTTPS 활성화
- [ ] CI backend 잡 PostgreSQL 전환 (현재 SQLite)
- [ ] Alembic 마이그레이션 Dry-Run CI 추가

### 중기 개선 (6~7단계)

- [ ] `deploy.sh`에 `alembic upgrade head` 추가 (자동 DB 마이그레이션)
- [ ] GHCR 이미지 레지스트리 도입 (배포 시간 단축)
- [ ] Rolling Restart + 자동 롤백 적용
- [ ] Prometheus + Grafana 모니터링 구축

---

## 관련 파일 안내

| 파일 | 역할 |
|------|------|
| [`.github/workflows/ci.yml`](../.github/workflows/ci.yml) | CI 워크플로우 (이미 완성됨) |
| `.github/workflows/cd.yml` | CD 워크플로우 (3단계에서 직접 만들 예정) |
| [`infra/scripts/deploy.sh`](../infra/scripts/deploy.sh) | EC2에서 실행되는 배포 스크립트 (이미 완성됨) |
| [`docker-compose.prod.yml`](../docker-compose.prod.yml) | 프로덕션용 Docker Compose 설정 (이미 완성됨) |
| [`infra/nginx/nginx.conf`](../infra/nginx/nginx.conf) | Nginx 설정 (HTTP 완성, HTTPS는 4단계에서 활성화) |
| [`docs/LOCAL_TESTING_GUIDE.md`](./LOCAL_TESTING_GUIDE.md) | 로컬에서 통합 테스트 하는 방법 |
| [`CONTRIBUTING.md`](../CONTRIBUTING.md) | 브랜치 이름 규칙, 커밋 컨벤션 |
