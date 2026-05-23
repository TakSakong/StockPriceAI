# CD 자동화 설정 가이드

> **선행 조건**: [P02_AWS_SETUP.md](./P02_AWS_SETUP.md) 완료 (EC2·RDS 구동 중, 첫 수동 배포 확인)

---

## 1. GitHub Secrets 등록

GitHub 저장소 → **Settings → Secrets and variables → Actions → New repository secret**

| 이름 | 값 |
|------|----|
| `EC2_HOST` | EC2 퍼블릭 IP 또는 도메인 |
| `EC2_USER` | `ubuntu` |
| `EC2_SSH_KEY` | `.pem` 파일 전체 내용 (`-----BEGIN RSA PRIVATE KEY-----` 포함) |
| `RDS_URL` | `postgresql://user:password@rds-endpoint:5432/stockai` |
| `SECRET_KEY` | `openssl rand -hex 32` 결과값 |

---

## 2. 브랜치 보호 규칙 설정

> **중요**: CD 워크플로우는 CI와 별도 파일이므로 `needs:`만으로 CI 통과를 강제할 수 없습니다.  
> 브랜치 보호 규칙으로 코드 레벨에서 막아야 "CI 통과한 코드만 main에 머지된다"는 보장이 생깁니다.

GitHub 저장소 → **Settings → Branches → Add branch protection rule**

**`main` 브랜치**

- [x] Require a pull request before merging
- [x] Require status checks to pass before merging
  - 필수 상태 체크: `backend`, `ml`, `frontend`, `docker`, `integration`
- [x] Do not allow bypassing the above settings

**`develop` 브랜치**

- [x] Require a pull request before merging
- [x] Require status checks to pass before merging
  - 필수 상태 체크: `backend`, `ml`, `frontend`, `docker`

---

## 3. GitHub Environment 생성

GitHub 저장소 → **Settings → Environments → New environment**

- 이름: `production`
- Required reviewers: 팀장 또는 2인 이상 지정 (선택)
- Deployment branches: `main` only

> `cd.yml`의 `environment: production`이 이 환경을 참조합니다.

---

## 4. `cd.yml` 작성

`.github/workflows/cd.yml` 파일을 새로 생성합니다. (현재 없음)

```yaml
name: CD

on:
  push:
    branches: [main]
    # main 머지 시 GitHub이 발생시키는 push 이벤트로 트리거됨.
    # 브랜치 보호 규칙(2번)으로 CI 미통과 시 main 머지 자체가 불가능.

concurrency:
  group: cd-production
  cancel-in-progress: false  # 배포 중 새 배포가 겹치지 않도록 큐잉

jobs:
  deploy:
    name: Deploy to EC2
    runs-on: ubuntu-latest
    environment: production

    steps:
      - name: SSH into EC2 and run deploy.sh
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.EC2_HOST }}
          username: ${{ secrets.EC2_USER }}
          key: ${{ secrets.EC2_SSH_KEY }}
          script: |
            bash /app/infra/scripts/deploy.sh
```

`deploy.sh`는 이미 작성되어 있습니다 ([`infra/scripts/deploy.sh`](../infra/scripts/deploy.sh)).

```bash
# deploy.sh 동작 요약
git pull origin main
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d --remove-orphans
sleep 10
curl -sf http://localhost/api/health && echo " backend OK"
curl -sf http://localhost/ml/health  && echo " ml OK"
```
