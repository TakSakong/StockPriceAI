# AWS 인프라 구축 가이드

> **선행 조건**: [P00_BEFORE_START.md](./P00_BEFORE_START.md)에서 AWS 계정·IAM·비용 알림 설정을 완료한 상태  
> **이 단계가 끝나면**: 실제 서버(EC2)와 데이터베이스(RDS)가 생성되고, 앱이 처음으로 인터넷에서 접근 가능해집니다.  
> **다음 단계**: [P03_CD.md](./P03_CD.md)에서 GitHub 자동 배포를 연결합니다.

---

## 시작 전 — AWS 기본 개념

처음 접하시는 분들을 위해 핵심 용어만 정리합니다.

| AWS 서비스 | 쉬운 설명 |
|-----------|-----------|
| **EC2** (Elastic Compute Cloud) | AWS에서 빌리는 가상 서버. 우리 앱이 실제로 돌아가는 컴퓨터입니다. |
| **RDS** (Relational Database Service) | AWS가 대신 관리해주는 데이터베이스. 백업·패치 등을 AWS가 자동으로 처리합니다. |
| **보안 그룹** | EC2·RDS에 적용되는 방화벽. 어떤 포트로 누가 접근할 수 있는지 규칙을 설정합니다. |
| **키 페어 (.pem 파일)** | SSH로 EC2에 접속할 때 쓰는 비밀 열쇠 파일. 한 번 다운로드하면 다시 받을 수 없습니다. |
| **Elastic IP** | EC2에 연결하는 고정 IP 주소. 인스턴스를 재시작해도 IP가 바뀌지 않습니다. |
| **VPC** | AWS 안에서 EC2·RDS가 속하는 가상 네트워크. 기본값(Default VPC)을 그대로 써도 됩니다. |

---

## 1단계. EC2 인스턴스 생성 (우리 앱이 돌아갈 서버)

**AWS 콘솔** 접속 → 우측 상단 리전이 원하는 곳인지 확인 → 검색창에 **EC2** → **Launch Instance** 클릭

### 설정값

| 항목 | 값 | 이유 |
|------|----|------|
| **Name** | 원하는 이름 (예: `stockai-prod`) | 구분용 |
| **AMI** | `Ubuntu Server 22.04 LTS` | 안정적인 LTS 버전, Docker 지원 우수 |
| **인스턴스 타입** | **`t3.medium`** (2 vCPU, 4GB RAM) | ML 서비스 + Celery 동시 실행 시 4GB 이상 필요. t3.micro(1GB)는 메모리 부족 오류 발생 |
| **키 페어** | **새로 생성** → `.pem` 파일 다운로드 후 안전하게 보관 | SSH 접속에 필요한 비밀 열쇠 |
| **스토리지** | 20GB, gp3 | Docker 이미지가 꽤 크므로 20GB 이상 권장 |

> **키 페어 주의사항**: 다운로드한 `.pem` 파일을 잃어버리면 그 EC2에 SSH 접속이 영구적으로 불가능합니다. `~/.ssh/` 폴더 같은 안전한 곳에 보관하고, Git에는 절대 올리지 마세요.

### 보안 그룹 설정 (방화벽 규칙)

"Create security group"을 선택하고 아래 인바운드 규칙을 추가합니다.

| 유형 | 포트 | 소스 | 이유 |
|------|------|------|------|
| SSH | 22 | **내 IP** (드롭다운에서 `My IP` 선택) | 개발자만 접속 가능하도록 제한 |
| HTTP | 80 | `0.0.0.0/0` | 누구나 웹 접속 가능 |
| HTTPS | 443 | `0.0.0.0/0` | 누구나 안전한 웹 접속 가능 (나중에 HTTPS 설정 후 사용) |

> **SSH를 전체 허용하면 안 되는 이유**: `0.0.0.0/0`(전체 허용)으로 설정하면 전 세계 해커들이 로그인을 시도합니다. 반드시 내 IP만 허용하세요. 나중에 내 IP가 바뀌면 보안 그룹에서 SSH 소스를 `My IP`로 다시 설정하면 됩니다.

**Launch Instance** 클릭 → EC2 생성 완료!

> **⚠️ Stop과 Terminate 혼동 주의**: EC2 인스턴스를 우클릭하면 "Stop instance"(중지)와 "Terminate instance"(영구 삭제)가 나란히 나옵니다. **Terminate는 인스턴스와 내부 데이터를 영구 삭제**합니다. 절대로 실수로 클릭하지 않도록 주의하세요.

---

### Elastic IP 할당 (필수!)

EC2에 기본으로 할당되는 퍼블릭 IP는 인스턴스를 **stop 했다가 start 하면 바뀝니다.**  
나중에 GitHub Secrets에 `EC2_HOST`를 등록하는데, IP가 바뀌면 자동 배포가 전부 실패합니다.  
**Elastic IP**는 고정 IP 주소로, EC2에 연결되어 있는 동안 **무료**입니다.

1. EC2 콘솔 좌측 메뉴 **Network & Security** → **Elastic IPs** → **Allocate Elastic IP address** 클릭
2. **Allocate** 클릭 (기본값 그대로)
3. 새로 생성된 Elastic IP 체크 → **Actions** → **Associate Elastic IP address**
4. **Instance**: 방금 만든 EC2 인스턴스 선택 → **Associate** 클릭

이제 이 Elastic IP가 앞으로 계속 쓸 서버의 고정 주소입니다. **이 주소를 메모해 두세요.**  
이후 단계에서 "EC2 퍼블릭 IP"라고 하면 이 Elastic IP를 의미합니다.

> **주의**: Elastic IP를 할당만 해 두고 EC2에 연결하지 않으면 시간당 $0.005가 과금됩니다. 반드시 연결(Associate)까지 완료하세요.

---

## 2단계. RDS PostgreSQL 생성 (데이터베이스)

**AWS 콘솔** → 검색창에 **RDS** → **Create database** 클릭

### 설정값

| 항목 | 값 | 이유 |
|------|----|------|
| **Creation method** | Standard create | 세부 설정 가능 |
| **엔진** | `PostgreSQL`, 버전 `16` | 프로젝트에서 사용하는 DB |
| **템플릿** | `Free tier` 또는 `Dev/Test` | 비용 절감 |
| **인스턴스 클래스** | `db.t3.micro` | 개발 단계에선 충분 |
| **스토리지** | 20GB, gp3 | 기본값 |
| **Multi-AZ** | **비활성화** | 개발 단계에선 불필요. 활성화하면 비용 2배 |
| **퍼블릭 액세스** | **비활성화** | 외부에서 직접 DB 접근 차단. EC2만 접근 가능하도록 |
| **초기 DB 이름** | `stockai` | 앱에서 사용하는 DB 이름 |
| **마스터 사용자 이름** | 원하는 이름 (예: `stockai`) | 메모해 두세요 |
| **마스터 암호** | 강력한 비밀번호 설정 | 반드시 메모해 두세요. 나중에 환경변수에 씁니다 |

페이지 맨 아래 **Additional configuration** 섹션을 펼쳐서 **Enable deletion protection**을 체크하세요.  
실수로 DB를 영구 삭제하는 것을 막아주는 안전장치입니다.

### RDS 보안 그룹 설정 (중요!)

"Connectivity" 섹션의 "VPC security group" 항목에서 **새 보안 그룹을 생성**합니다.

- 이름: 예) `stockai-rds-sg`
- 인바운드 규칙: `PostgreSQL (포트 5432)`를 **EC2의 보안 그룹 ID**에서만 허용

> **EC2 보안 그룹 ID 확인 방법**: EC2 콘솔 → 인스턴스 선택 → "Security" 탭 → "Security groups" → `sg-xxxxxxxxxxxxxxxxx` 형태의 ID를 복사하세요.

**Create database** 클릭 → 생성에 약 5~10분 소요됩니다.

생성 완료 후 RDS 상세 페이지 "Connectivity & security" 탭에서 **엔드포인트** (`xxxx.rds.amazonaws.com` 형태)를 메모해 두세요.

---

## 3단계. EC2 초기 설정

이제 EC2에 SSH로 접속해서 Docker, Git 등을 설치합니다.

### SSH 접속

```bash
# .pem 파일 권한 설정 (처음 한 번만 실행)
chmod 400 /path/to/your-key.pem

# EC2에 SSH 접속 (EC2_퍼블릭_IP를 1단계에서 메모한 Elastic IP로 교체)
ssh -i /path/to/your-key.pem ubuntu@<EC2_퍼블릭_IP>
```

> **접속이 안 된다면?** 보안 그룹에서 SSH(22) 포트가 현재 내 IP로 허용되어 있는지 확인하세요. 공유기를 재시작하거나 장소가 바뀌면 IP가 변경될 수 있습니다. AWS 콘솔 → 보안 그룹 → 인바운드 규칙 수정 → SSH 소스를 `My IP`로 다시 설정하면 됩니다.

### 필요한 소프트웨어 설치

EC2 접속 후 아래 명령어를 순서대로 실행합니다.

```bash
# 패키지 목록 업데이트 및 Docker, Git 설치
sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
```

```bash
# ubuntu 계정에 Docker 권한 부여
# (이 설정이 없으면 docker 명령어마다 sudo를 앞에 붙여야 합니다)
sudo usermod -aG docker ubuntu
logout
```

> **logout 후 반드시 SSH를 다시 접속해야** Docker 권한이 적용됩니다.  
> 단순히 `newgrp docker`만 실행하면 현재 세션에만 임시 적용되고, 재접속 후에는 사라집니다.

### 타임존 및 스왑 메모리 설정

SSH 재접속 후 바로 실행합니다.

```bash
# 서버 시간을 한국 시간(KST)으로 설정
# 기본값 UTC를 그대로 쓰면 로그 시간이 9시간 차이 납니다
sudo timedatectl set-timezone Asia/Seoul

# 스왑 메모리 2GB 추가
sudo fallocate -l 2G /swapfile
sudo chmod 600 /swapfile
sudo mkswap /swapfile
sudo swapon /swapfile
echo '/swapfile none swap sw 0 0' | sudo tee -a /etc/fstab
```

> **스왑이 필요한 이유**: t3.medium의 RAM 4GB는 ML 서비스 Docker 이미지를 빌드할 때 일시적으로 부족할 수 있습니다. 스왑은 RAM이 꽉 찼을 때 디스크를 임시 메모리로 활용해 OOM(Out of Memory) 킬을 방지합니다.

### 코드 클론 및 환경변수 설정

```bash
# 앱 코드 받기
git clone https://github.com/OSP-team4-StockPriceAI/StockPriceAI.git /app
cd /app

# 환경변수 파일 생성 (예시 파일을 복사)
cp .env.example .env
```

> **저장소가 비공개(private)인 경우**: GitHub은 HTTPS 비밀번호 인증을 지원하지 않습니다. 아래와 같이 Deploy Key를 설정하고 SSH URL로 클론하세요.
>
> ```bash
> # EC2에서 Deploy Key 생성 (한 번만)
> ssh-keygen -t ed25519 -C "ec2-deploy-key" -f ~/.ssh/deploy_key -N ""
> cat ~/.ssh/deploy_key.pub   # 이 내용 전체를 복사
> ```
>
> GitHub 저장소 → **Settings** → **Deploy keys** → **Add deploy key** → 복사한 내용 붙여넣기 → **Allow write access 체크 안 함** → **Add key**
>
> 그다음 `~/.ssh/config` 파일에 아래를 추가합니다:
> ```
> Host github.com
>   IdentityFile ~/.ssh/deploy_key
> ```
>
> clone 명령어를 아래로 교체합니다:
> ```bash
> git clone git@github.com:OSP-team4-StockPriceAI/StockPriceAI.git /app
> ```

### 환경변수 파일 수정

`.env` 파일을 열어 실제 값으로 채워줍니다.

```bash
# nano 편집기로 열기 (저장: Ctrl+O → Enter, 종료: Ctrl+X)
nano .env
```

수정할 항목:

```bash
# Redis 주소 — Docker 내부 네트워크 이름이라 그대로 두세요
REDIS_URL=redis://redis:6379/0
CELERY_BROKER_URL=redis://redis:6379/2

# 앱 보안 키 — 아래 명령어로 생성한 값을 붙여넣으세요
# 생성: openssl rand -hex 32
SECRET_KEY=여기에_생성된_키를_붙여넣기

# ML 서비스 주소 — Docker 내부 이름이라 그대로 두세요
ML_SERVICE_URL=http://ml:8001

# EC2 Elastic IP로 교체 (나중에 도메인이 생기면 도메인으로 변경)
NEXT_PUBLIC_API_URL=http://<EC2_퍼블릭_IP>
NEXT_PUBLIC_ML_URL=http://<EC2_퍼블릭_IP>/ml
NEXT_PUBLIC_WS_URL=ws://<EC2_퍼블릭_IP>

# RDS 연결 주소 — 2단계에서 메모한 값으로 채우기
# 형식: postgresql://사용자명:비밀번호@RDS엔드포인트:5432/stockai
RDS_URL=postgresql://stockai:비밀번호@xxxx.rds.amazonaws.com:5432/stockai
```

> **SECRET_KEY 생성 방법**: EC2에서 아래 명령어를 실행하면 랜덤한 안전한 키가 생성됩니다.
> ```bash
> openssl rand -hex 32
> ```

---

## 4단계. 첫 배포 (수동)

```bash
cd /app

# 전체 서비스 시작 (처음엔 Docker 이미지 빌드로 5~15분 소요됩니다)
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

서비스 시작 후 정상 여부를 확인합니다.

```bash
# 15초 기다린 후 헬스체크
sleep 15
curl -sf http://localhost/api/health && echo "backend OK"
curl -sf http://localhost/ml/health  && echo "ml OK"
```

헬스체크가 OK로 나오면 **데이터베이스 마이그레이션을 반드시 실행**합니다.

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml \
  exec backend poetry run alembic upgrade head
```

> **이 단계를 빠뜨리면 앱이 동작하지 않습니다!**  
> 로컬 개발 시에는 `init.sql`로 테이블이 자동 생성되지만, RDS에는 적용되지 않습니다.  
> `alembic upgrade head`가 RDS에 필요한 테이블을 처음으로 만들어 줍니다.

### 배포 확인

브라우저에서 `http://<EC2_퍼블릭_IP>` 에 접속해 앱이 뜨는지 확인하세요.

앱이 잘 동작한다면 이 단계 완료입니다! 다음은 [P03_CD.md](./P03_CD.md)에서 자동 배포를 설정합니다.

### 문제가 생겼을 때

```bash
# 실행 중인 컨테이너 상태 확인
docker compose -f docker-compose.yml -f docker-compose.prod.yml ps

# 특정 서비스 로그 확인 (예: backend)
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs backend --tail=50

# 모든 서비스 로그 한번에 확인
docker compose -f docker-compose.yml -f docker-compose.prod.yml logs --tail=30
```
