# AWS 인프라 구축 가이드

> **선행 조건**: AWS 콘솔 접근 권한 보유  
> **완료 후**: [P03_CD_SETUP.md](./P03_CD_SETUP.md)로 이어서 진행

---

## 1. EC2 인스턴스 생성

AWS 콘솔 → EC2 → Launch Instance

| 항목 | 값 |
|------|----|
| AMI | Ubuntu 22.04 LTS |
| 인스턴스 타입 | **t3.medium** (4GB RAM 필수 — ML + Celery 동시 실행 시 t3.micro OOM 위험) |
| 키 페어 | 새로 생성 후 `.pem` 파일 안전하게 보관 |
| 스토리지 | 20GB gp3 이상 |

**보안 그룹 인바운드 규칙**

| 유형 | 포트 | 소스 |
|------|------|------|
| SSH | 22 | **내 IP만** (0.0.0.0/0 절대 금지) |
| HTTP | 80 | 0.0.0.0/0 |
| HTTPS | 443 | 0.0.0.0/0 |

> RDS 5432 포트는 아래 2번에서 EC2 보안 그룹 ID를 소스로 지정해 허용합니다.

---

## 2. RDS PostgreSQL 생성

AWS 콘솔 → RDS → Create database

| 항목 | 값 |
|------|----|
| 엔진 | PostgreSQL 16 |
| 인스턴스 클래스 | db.t3.micro |
| 스토리지 | 20GB gp3 |
| Multi-AZ | 비활성화 (개발 단계) |
| 퍼블릭 액세스 | **비활성화** |
| VPC 보안 그룹 | 새 보안 그룹 생성: EC2 보안 그룹 ID에서 5432 인바운드 허용 |
| 초기 DB 이름 | `stockai` |

> 생성 완료 후 엔드포인트(`xxxx.rds.amazonaws.com`)를 메모해 둡니다.

---

## 3. EC2 초기 설정

EC2에 SSH 접속 후 순서대로 실행합니다.

```bash
# 패키지 설치
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git

# ubuntu 계정에 docker 권한 부여 (logout 후 재접속해야 적용됨)
sudo usermod -aG docker ubuntu
logout
# ↑ 이후 SSH 재접속 필요 — newgrp docker는 현재 세션에만 유효

# 앱 클론
git clone https://github.com/OSP-team4-StockPriceAI/StockPriceAI.git /app
cd /app

# 환경변수 파일 생성
cp .env.example .env
```

`.env`에서 아래 항목을 실제 값으로 수정합니다.

```bash
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/2
SECRET_KEY=           # openssl rand -hex 32
ML_SERVICE_URL=http://ml:8001
NEXT_PUBLIC_API_URL=http://<EC2_PUBLIC_IP>
NEXT_PUBLIC_ML_URL=http://<EC2_PUBLIC_IP>/ml
NEXT_PUBLIC_WS_URL=ws://<EC2_PUBLIC_IP>
RDS_URL=postgresql://<user>:<password>@<rds-endpoint>:5432/stockai
```

> `docker-compose.prod.yml`이 `RDS_URL`과 `SECRET_KEY`를 `.env`에서 읽어 backend/ml 컨테이너에 주입합니다.

---

## 4. 첫 배포 (수동)

```bash
cd /app
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d

# 헬스체크 확인
sleep 15
curl -sf http://localhost/api/health && echo "backend OK"
curl -sf http://localhost/ml/health  && echo "ml OK"
```

서비스가 뜬 것을 확인한 후 **DB 마이그레이션을 반드시 실행합니다.**  
로컬 개발 환경과 달리 RDS에는 `init.sql`이 적용되지 않으므로 이 단계를 건너뛰면 테이블이 없어 앱이 동작하지 않습니다.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec backend poetry run alembic upgrade head
```

정상 확인 후 → [P03_CD_SETUP.md](./P03_CD_SETUP.md)로 이동해 GitHub 설정 및 CD 자동화를 진행합니다.
