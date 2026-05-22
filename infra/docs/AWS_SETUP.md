# AWS 수동 설정 가이드

## EC2 초기 설정 (1회)

```bash
# Ubuntu 22.04 LTS 인스턴스 접속 후

sudo apt update && sudo apt install -y docker.io docker-compose-plugin git
sudo usermod -aG docker ubuntu
newgrp docker

# 앱 디렉토리
git clone https://github.com/TakSakong/StockPriceAI.git /app
cd /app
cp .env.example .env.prod
# .env.prod에 RDS_URL, SECRET_KEY 등 실제 값 입력
```

## EC2 보안 그룹

| 규칙    | 포트      | 소스        |
| ------- | --------- | ----------- |
| SSH     | 22        | 내 IP만     |
| HTTP    | 80        | 0.0.0.0/0  |
| HTTPS   | 443       | 0.0.0.0/0  |

## RDS PostgreSQL 설정

```
엔진: PostgreSQL 16
인스턴스: db.t3.micro (프리티어)
스토리지: 20GB gp3
Multi-AZ: 비활성화
퍼블릭 액세스: 비활성화 (EC2 보안 그룹에서만 5432 허용)
```

## SSL 인증서 (도메인 보유 시)

```bash
sudo apt install -y certbot
sudo certbot certonly --standalone -d yourdomain.com
# 자동 갱신
echo "0 0 1 * * certbot renew --quiet" | sudo crontab -
```

## 첫 배포

```bash
cd /app
docker compose -f docker-compose.yml -f docker-compose.prod.yml up --build -d
```

## GitHub Secrets 등록

| 이름         | 값                                     |
| ------------ | -------------------------------------- |
| `EC2_HOST`   | EC2 퍼블릭 IP 또는 도메인             |
| `EC2_USER`   | EC2 로그인 사용자 이름 (보통 `ubuntu`) |
| `EC2_SSH_KEY`| EC2 접속용 PEM 키 내용 (전체 텍스트)  |
| `RDS_URL`    | `postgresql://user:pass@endpoint/db`   |
| `SECRET_KEY` | JWT 서명 키 (openssl rand -hex 32)     |
