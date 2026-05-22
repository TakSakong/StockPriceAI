# AWS 수동 설정 가이드

## EC2 초기 설정 (1회)

> **인스턴스 타입**: t3.medium 권장 (4GB RAM). ML 서비스 + Celery Worker를 함께 실행하므로 t3.micro는 OOM 위험이 있습니다.

```bash
# Ubuntu 22.04 LTS 인스턴스 접속 후

sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker ubuntu
newgrp docker

# 앱 디렉토리
git clone https://github.com/TakSakong/StockPriceAI.git /app
cd /app
cp .env.example .env
# .env에 RDS_URL, SECRET_KEY 등 실제 값 입력
# (docker compose는 기본으로 .env 파일을 읽음 — .env.prod 등 다른 이름 사용 시 deploy.sh에 --env-file 옵션 추가 필요)
```

## EC2 보안 그룹

| 규칙    | 포트      | 소스        |
| ------- | --------- | ----------- |
| SSH     | 22        | 내 IP만     |
| HTTP    | 80        | 0.0.0.0/0  |
| HTTPS   | 443       | 0.0.0.0/0  |

> RDS 5432 포트는 EC2 보안 그룹에서만 허용 (퍼블릭 액세스 비활성화).  
> Redis는 EC2 내부 Docker 컨테이너로 실행되므로 별도 보안 그룹 불필요.

## RDS PostgreSQL 설정

```
엔진: PostgreSQL 16
인스턴스: db.t3.micro
스토리지: 20GB gp3
Multi-AZ: 비활성화
퍼블릭 액세스: 비활성화 (EC2 보안 그룹에서만 5432 허용)
```

## 서비스 구성 (EC2에서 실행되는 컨테이너)

프로덕션 배포 시 아래 6개 서비스가 Docker Compose로 실행됩니다.

| 서비스          | 역할                              | 비고                        |
| --------------- | --------------------------------- | --------------------------- |
| `nginx`         | 리버스 프록시 (포트 80/443)       |                             |
| `frontend`      | Next.js 앱                        |                             |
| `backend`       | FastAPI 앱                        |                             |
| `ml`            | ML FastAPI 서비스 (포트 8001)     |                             |
| `celery_worker` | 비동기 ML 작업 처리 (Celery)      | ml 이미지 재사용            |
| `redis`         | 메시지 브로커 + 캐시 (포트 6379) | ElastiCache 미사용, 로컬 컨테이너 |

> `postgres`는 프로덕션에서 비활성화(`profiles: ["local"]`)되며 RDS를 사용합니다.

## SSL 인증서 (도메인 보유 시)

```bash
sudo apt install -y certbot

# nginx가 80 포트를 점유하므로 --standalone 대신 webroot 또는 nginx 플러그인 사용
sudo systemctl stop nginx 2>/dev/null || true   # 시스템 nginx가 없으면 무시
docker compose down                              # 컨테이너 nginx 중지
sudo certbot certonly --standalone -d yourdomain.com

# 자동 갱신
echo "0 0 1 * * certbot renew --quiet" | sudo crontab -
```

인증서 발급 후 `infra/nginx/nginx.conf`의 HTTPS 서버 블록(주석 처리된 `server { listen 443 ssl; ... }`)을 활성화하고 재배포하세요.

```bash
# nginx.conf 수정 후 nginx 컨테이너만 재시작
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --no-deps nginx
```

## 첫 배포

```bash
cd /app
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

## 이후 배포 (deploy.sh)

`infra/scripts/deploy.sh`는 EC2에서 직접 실행하거나 GitHub Actions CD에서 SSH로 호출하는 배포 스크립트입니다.

```bash
# EC2에서 수동 실행
bash /app/infra/scripts/deploy.sh
```

> **참고**: 현재 CD 워크플로우(`.github/workflows/cd.yml`)가 없어 배포는 수동으로 진행해야 합니다. CD 자동화 구현 절차는 [`docs/CICD_ROADMAP.md` Phase 1](../../docs/CICD_ROADMAP.md#-phase-1--cd-연결-및-aws-최초-배포-최우선)을 참조하세요.

## GitHub Secrets 등록

> CD 자동화(`cd.yml`) 구현 시 필요합니다. 현재 CI 워크플로우(`ci.yml`)는 이 시크릿을 사용하지 않습니다.  
> 등록 순서 및 브랜치 보호 규칙 설정은 [`docs/CICD_ROADMAP.md`](../../docs/CICD_ROADMAP.md)를 참조하세요.

| 이름          | 값                                      |
| ------------- | --------------------------------------- |
| `EC2_HOST`    | EC2 퍼블릭 IP 또는 도메인              |
| `EC2_USER`    | EC2 로그인 사용자 이름 (보통 `ubuntu`)  |
| `EC2_SSH_KEY` | EC2 접속용 PEM 키 내용 (전체 텍스트)   |
| `RDS_URL`     | `postgresql://user:password@rds-endpoint/stockai` |
| `SECRET_KEY`  | JWT 서명 키 (`openssl rand -hex 32`)    |
