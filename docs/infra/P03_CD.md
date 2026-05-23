# CD 자동화 설정 가이드

> **선행 조건**: [P02_AWS.md](./P02_AWS.md)를 완료해 EC2·RDS가 실행 중이고, 첫 수동 배포가 성공한 상태  
> **이 단계가 끝나면**: `main` 브랜치에 코드가 머지되면 자동으로 EC2에 배포됩니다.

---

## 큰 그림

지금까지는 EC2에 직접 SSH 접속해서 손으로 배포했습니다.  
이 단계에서는 **"main 브랜치에 코드가 올라오면 GitHub이 알아서 EC2에 배포"** 되도록 자동화합니다.

자동화를 위해 필요한 것:
1. **GitHub Secrets** — GitHub이 EC2에 접속하기 위한 비밀 정보 저장
2. **브랜치 보호 규칙** — 테스트 실패한 코드는 main에 못 들어오게 막기
3. **GitHub Environment** — 배포 환경(production) 정의
4. **`cd.yml` 파일** — 실제 자동 배포 워크플로우

---

## 1단계. GitHub Secrets 등록

**GitHub Secrets**는 비밀번호나 서버 접속 키처럼 코드에 직접 쓰면 안 되는 정보를 GitHub에 안전하게 저장하는 기능입니다.  
`cd.yml` 워크플로우에서 `${{ secrets.EC2_HOST }}` 형태로 꺼내 씁니다. 실제 값은 로그에 출력되지 않아 안전합니다.

**등록 경로**: 저장소 → **Settings** → **Secrets and variables** → **Actions** → **New repository secret**

| 이름 | 값 | 어디서 찾나요? |
|------|----|---------------|
| `EC2_HOST` | EC2 퍼블릭 IP 또는 도메인 | EC2 콘솔 → 인스턴스 선택 → "Public IPv4 address" |
| `EC2_USER` | `ubuntu` | Ubuntu AMI의 기본 사용자 이름 |
| `EC2_SSH_KEY` | `.pem` 파일의 **전체 내용** | 아래 설명 참고 |
| `RDS_URL` | `postgresql://user:password@rds-endpoint:5432/stockai` | P02에서 설정한 값 |
| `SECRET_KEY` | `openssl rand -hex 32` 결과값 | EC2에서 명령어 실행 후 복사 |

> **EC2_SSH_KEY 복사 방법**: `.pem` 파일을 텍스트 편집기(메모장, VSCode 등)로 열면 `-----BEGIN RSA PRIVATE KEY-----`로 시작하는 여러 줄의 텍스트가 보입니다. 이 전체를 그대로 복사해서 붙여넣으면 됩니다.

> **Secrets는 한 번 저장하면 다시 내용을 볼 수 없습니다.** 잘못 입력했다면 해당 Secret을 삭제하고 다시 등록하세요.

---

## 2단계. 브랜치 보호 규칙 설정

브랜치 보호 규칙은 **"CI 테스트를 통과하지 않은 코드는 main 브랜치에 머지할 수 없다"** 는 안전장치입니다.  
이 설정이 없으면 실수로 테스트 실패한 코드가 main에 들어와 서비스가 망가질 수 있습니다.

> **왜 중요한가요?** CD 워크플로우는 CI와 별도 파일이라 `needs:` 키워드만으로는 CI 통과를 강제할 수 없습니다. 브랜치 보호 규칙으로 코드 레벨에서 막아야 "CI 통과한 코드만 main에 들어온다"는 보장이 생깁니다.

**설정 경로**: 저장소 → **Settings** → **Branches** → **Add branch protection rule**

### `main` 브랜치 규칙

- [x] **Require a pull request before merging** — main에 직접 push 불가, 반드시 PR 경유
- [x] **Require status checks to pass before merging** — CI 통과 필수
  - "Status checks that are required" 검색창에 아래 5개를 입력해 추가:
    - `backend`
    - `ml`
    - `frontend`
    - `docker`
    - `integration`
- [x] **Do not allow bypassing the above settings** — 관리자도 예외 없음

### `develop` 브랜치 규칙

- [x] **Require a pull request before merging**
- [x] **Require status checks to pass before merging**
  - 필수 체크: `backend`, `ml`, `frontend`, `docker`

> **Status check 이름이 검색이 안 된다면?** CI가 최소 한 번 실행돼야 이름이 등록됩니다. 아직 한 번도 안 돌았다면 빈 커밋을 push해서 CI를 먼저 트리거하세요.
> ```bash
> git commit --allow-empty -m "ci: trigger CI for branch protection setup"
> git push origin develop
> ```

---

## 3단계. GitHub Environment 생성

**GitHub Environment**는 배포 대상 환경(여기선 production 서버)을 GitHub에 정의하는 것입니다.  
선택적으로 팀장 승인을 받아야만 배포가 진행되도록 설정할 수 있습니다.

**설정 경로**: 저장소 → **Settings** → **Environments** → **New environment**

| 항목 | 값 |
|------|----|
| **이름** | `production` (철자 정확하게 — cd.yml에서 이 이름을 참조합니다) |
| **Required reviewers** | 팀장 또는 2인 이상 지정 (선택 사항) |
| **Deployment branches** | `main` only (main 브랜치에서만 배포 허용) |

---

## 4단계. `cd.yml` 작성

이제 실제 자동 배포 워크플로우 파일을 만듭니다.

`.github/workflows/cd.yml` 파일을 **로컬에서** 아래 내용으로 새로 생성합니다. (현재 이 파일은 없습니다)

```yaml
name: CD

on:
  push:
    branches: [main]
    # main 브랜치에 push(= PR 머지)가 발생할 때 자동 실행됩니다.
    # 2단계에서 설정한 브랜치 보호 규칙 덕분에
    # CI를 통과하지 못한 코드는 main에 들어올 수 없습니다.

concurrency:
  group: cd-production
  cancel-in-progress: false
  # 배포 중에 새로운 배포 요청이 오면 큐에 쌓아 순서대로 처리합니다.
  # false = 진행 중인 배포를 취소하지 않음 (안전하게 배포 완료 후 다음 배포 시작)

jobs:
  deploy:
    name: Deploy to EC2
    runs-on: ubuntu-latest
    environment: production   # 3단계에서 만든 Environment 이름
    timeout-minutes: 10       # 배포가 10분을 넘으면 자동 취소 (무한 대기 방지)

    steps:
      - name: SSH into EC2 and run deploy.sh
        uses: appleboy/ssh-action@v1.0.3
        with:
          host: ${{ secrets.EC2_HOST }}       # 1단계에서 등록한 EC2 주소
          username: ${{ secrets.EC2_USER }}   # ubuntu
          key: ${{ secrets.EC2_SSH_KEY }}     # .pem 파일 내용
          script: |
            bash /app/infra/scripts/deploy.sh
            # EC2에 접속해서 deploy.sh를 실행합니다.
            # 이 스크립트가 git pull → docker compose up → 헬스체크를 수행합니다.
```

### `deploy.sh`가 하는 일

[`infra/scripts/deploy.sh`](../infra/scripts/deploy.sh)는 이미 작성되어 있습니다. 내용을 요약하면:

```bash
# 1. EC2에서 최신 코드를 받기
git pull origin main

# 2. 변경된 서비스를 새 이미지로 재시작
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d --remove-orphans

# 3. 서비스가 완전히 뜰 때까지 10초 대기
sleep 10

# 4. 정상 동작 확인 (실패하면 GitHub Actions에 오류 표시)
curl -sf http://localhost/api/health && echo "backend OK"
curl -sf http://localhost/ml/health  && echo "ml OK"
```

### `cd.yml` 적용하기

```bash
# 로컬에서 파일 생성 후 커밋
git add .github/workflows/cd.yml
git commit -m "ci: add CD workflow for automatic EC2 deployment"
git push origin develop

# develop → main PR 생성 → CI 통과 확인 → 머지
# 머지되는 순간 cd.yml이 자동으로 실행됩니다!
```

> **성공 확인 방법**: GitHub 저장소 → **Actions** 탭 → "CD" 워크플로우가 초록색 체크 표시로 완료되면 성공입니다. 브라우저에서 EC2 주소로 접속해 최신 코드가 반영되었는지 확인하세요.

> **배포가 실패했을 때**: Actions 탭에서 실패한 워크플로우를 클릭하면 어느 단계에서 오류가 났는지 로그를 볼 수 있습니다. EC2 접속 실패라면 Secrets 값을 다시 확인하고, 헬스체크 실패라면 EC2에서 직접 `docker compose logs` 로 컨테이너 로그를 확인하세요.
