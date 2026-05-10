# Contributing Guide

## 브랜치 전략

```
main          ─── 프로덕션 배포 전용. 직접 push 금지.
  │
develop       ─── 통합 개발 브랜치. PR 필수.
  │
  ├── feature/FE-stock-chart
  ├── feature/BE-watchlist-api
  └── feature/ML-celery-scanner
```

### 브랜치 명명 규칙

```
{type}/{scope}-{short-description}

type : feature | fix | refactor | chore | docs
scope: FE | BE | ML | INFRA

예시:
  feature/FE-realtime-scan-progress
  feature/BE-jwt-auth
  fix/ML-predictor-null-check
  chore/INFRA-nginx-ssl-config
```

## 커밋 컨벤션 (Conventional Commits)

```
{type}({scope}): {subject}
```

| Type       | 사용 시점           |
| ---------- | ------------------- |
| `feat`     | 새로운 기능         |
| `fix`      | 버그 수정           |
| `refactor` | 기능 변경 없는 개선 |
| `test`     | 테스트              |
| `docs`     | 문서                |
| `chore`    | 빌드/패키지         |
| `ci`       | CI/CD 설정          |

Scope: `fe` | `be` | `ml` | `db` | `infra` | `ci`

예시:

```
feat(be): add JWT refresh token endpoint
fix(ml): handle null ticker in predictor
chore(infra): add healthcheck to postgres service
docs(ci): update GitHub Actions setup guide
```

## 개발 환경 세팅

```bash
# 1. 저장소 클론
git clone https://github.com/your-org/StockPriceAI.git
cd StockPriceAI

# 2. 환경 변수 설정 (SECRET_KEY만 임의 값으로 교체)
cp .env.example .env

# 3. 전체 서비스 실행
docker compose up --build

# 브라우저 확인
# Frontend : http://localhost:3000
# API Docs : http://localhost:8000/docs
# ML Docs  : http://localhost:8001/docs
```

### Python 가상환경 (IDE 자동완성 등 직접 편집 시)

```bash
# Poetry 설치 (1회)
curl -sSL https://install.python-poetry.org | python3 -

# backend
cd backend && poetry install && poetry shell

# ml
cd ../ml && poetry install && poetry shell
```

## PR 프로세스

1. `develop` 브랜치에서 작업 브랜치를 분기
2. 작업 완료 후 PR 생성 → `develop` 대상
3. CI(lint + test) 통과 필수
4. 팀원 1명 이상 리뷰 승인 후 Squash Merge
5. `develop` → `main` 병합은 팀 전체 합의 후 진행

## 팀 역할 분담

| 역할 | 담당 영역                                   |
| ---- | ------------------------------------------- |
| 지운 | Frontend (Next.js)                          |
| 공탁 | Backend API (FastAPI + JWT + RDS)           |
| 진우 | ML 서비스 (모델 이전 + Celery)              |
| 종윤 | 배포, CI/CD (EC2/RDS 설정 + GitHub Actions) |
