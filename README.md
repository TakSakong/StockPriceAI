███████╗████████╗ ██████╗  ██████╗██╗  ██╗██████╗ ██████╗ ██╗ ██████╗███████╗ █████╗ ██╗
██╔════╝╚══██╔══╝██╔═══██╗██╔════╝██║ ██╔╝██╔══██╗██╔══██╗██║██╔════╝██╔════╝██╔══██╗██║
███████╗   ██║   ██║   ██║██║     █████╔╝ ██████╔╝██████╔╝██║██║     █████╗  ███████║██║
╚════██║   ██║   ██║   ██║██║     ██╔═██╗ ██╔═══╝ ██╔══██╗██║██║     ██╔══╝  ██╔══██║██║
███████║   ██║   ╚██████╔╝╚██████╗██║  ██╗██║     ██║  ██║██║╚██████╗███████╗██║  ██║██║
╚══════╝   ╚═╝    ╚═════╝  ╚═════╝╚═╝  ╚═╝╚═╝     ╚═╝  ╚═╝╚═╝ ╚═════╝╚══════╝╚═╝  ╚═╝╚═╝

# 🚀 StockPrice AI 🚀
**기존 Streamlit 기반 주식 분석 도구를 풀스택 프로덕션 웹 서비스로 확장한 AI 기반 주식 분석 서비스입니다.**

## Visual Demonstration
!(./demo.gif)

## Motivation & Problem
**Why this exists:** 기존의 단순한 평면 JSON 저장소(scan_cache.json, watchlist.json)를 관계형 데이터베이스로 마이그레이션하고, 기존 ML 모듈들을 REST API로 노출시켜야 할 필요성이 있었습니다. 
**The solution:** AWS RDS의 PostgreSQL을 기반으로 XGBoost와 LSTM 앙상블 기반의 주식 예측, S&P 500 스캐닝, 뉴스 감성 분석 및 관심 종목 기능을 제공하는 풀스택 웹 서비스를 구축하여 문제를 해결합니다. 
**Learning goals:** Docker를 이용한 컨테이너화, AWS(EC2 + RDS) 전체 스택 배포, EventBridge 및 Lambda를 활용한 자동화 작업, 그리고 GitHub Actions를 통한 CI/CD 파이프라인 구축을 경험하고 학습하는 것을 목표로 합니다. 

## Tech Stack & Rationale
* **Next.js (TypeScript):** 주식 분석 UI, 관심 종목 패널, 스캐너 결과를 표시하는 클라이언트 레이어를 구축하기 위해 선택했습니다. 
* **FastAPI:** 기존 파이썬 기반 ML 모듈을 손쉽게 REST API 서버로 구성하고 백그라운드 작업을 효율적으로 처리하기 위해 채택했습니다. 
* **PostgreSQL (AWS RDS):** 예측 결과, 관심 종목, 캐시 등의 데이터를 영구적이고 안정적으로 관리하는 관계형 데이터베이스 스토리지를 위해 선택했습니다. 
* **XGBoost & PyTorch (LSTM):** 주식 시장 데이터 분석 및 앙상블 예측 모델(predictor)을 구현하기 위한 핵심 머신러닝 기술로 활용했습니다. 
* **Docker & Docker Compose:** EC2 환경에서 모든 컴포넌트를 컨테이너화하여 다중 컨테이너 오케스트레이션을 쉽게 하기 위해 도입했습니다. 

## Key Features
* **AI 주식 예측 및 분석:** 티커를 입력받아 XGBoost+LSTM 앙상블 예측을 실행하고, 매수/매도/관망 신호, 상승 확률, 뉴스 감성 점수를 분석해 제공합니다. 
* **S&P 500 스캐너 자동화:** EventBridge와 Lambda를 이용해 매일 평일 17:00 KST에 S&P 500 배치 스캔을 자동으로 실행하고 종합 점수로 순위가 매겨진 결과를 제공합니다. 
* **관심 종목 (Watchlist) 관리:** 사용자가 관심 있는 주식 티커를 메모와 함께 저장, 수정, 삭제 및 조회할 수 있습니다. 
* **사용자 인증 및 보안:** JWT 및 OAuth2를 기반으로 사용자 가입, 로그인 처리, 보안 토큰 발급 및 검증을 수행하여 보호된 엔드포인트에 대한 접근을 관리합니다. 
* **실시간 모니터링 시스템:** Prometheus와 Grafana를 활용하여 EC2의 CPU/메모리 지표와 FastAPI API 응답 지연 시간을 수집하고 시각화합니다. 

## Getting Started
로컬 환경에서 프로젝트를 실행하기 위한 단계입니다.

### Prerequisites
* Node.js (v18 이상 권장)
* Python 3.10+
* Docker 및 Docker Compose
* PostgreSQL

### Installation

1. 저장소를 클론합니다.
   ```bash
   git clone [https://github.com/yourusername/stockprice-ai.git](https://github.com/yourusername/stockprice-ai.git)

2. 프로젝트 디렉토리로 이동합니다.
   '''cd stockprice-ai

3. 프론트엔드 패키지를 설치합니다.

   cd frontend
   npm install

4. 백엔드 패키지를 설치합니다.
   cd ../backend
   pip install -r requirements.txt

5. 환경 변수를 설정합니다.
   cp .env.example .env
# 데이터베이스 자격 증명 및 JWT 시크릿 키 등을 .env에 추가합니다.

6. Docker Compose를 이용해 서비스를 실행합니다.
   docker-compose up -d

## Lessons Learned & Challangers: A short section detailing the most difficult technical problem you solved. This is a powerful differentiator.