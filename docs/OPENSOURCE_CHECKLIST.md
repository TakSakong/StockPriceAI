# MIT 오픈소스 전환 체크리스트

> 이 문서는 StockPriceAI를 MIT 라이선스로 공개하기 위해 필요한 작업 목록입니다.  
> **라이선스 파일 추가만으로는 충분하지 않습니다.** 아래 항목을 순서대로 완료하세요.

---

## 우선순위 요약

| 순서 | 항목 | 이유 |
| ---- | ---- | ---- |
| 1 | **Git 히스토리 시크릿 스캔** | 공개 후 되돌릴 수 없음 |
| 2 | **팀원 실명 노출 동의 확인** | 개인정보 문제 |
| 3 | `LICENSE` 파일 추가 | 라이선스 효력의 핵심 |
| 4 | 패키지 메타데이터 업데이트 | 배포 시 필수 |
| 5 | README 업데이트 | 프로젝트 첫인상 |
| 6 | 의존성 라이선스 호환성 확인 | 법적 호환성 |
| 7 | `CODE_OF_CONDUCT.md` 추가 | 외부 기여자 관리 |
| 8 | GitHub 저장소 설정 | 검색 노출 및 관리 |

---

## 1. 보안 — Git 히스토리 시크릿 스캔

> **레포를 공개하면 과거 커밋 전체가 노출됩니다. 공개 전 반드시 완료하세요.**

### 1-1. 히스토리 전수 스캔

```bash
# trufflehog 설치 (1회)
brew install trufflehog

# 전체 히스토리 스캔
trufflehog git file://. --since-commit HEAD~100
```

### 1-2. 수동 확인 항목

```bash
# .env 파일이 실수로 커밋된 이력 확인
git log --all --oneline -- .env

# 하드코딩된 SECRET_KEY, API 키 검색
grep -r "SECRET_KEY\s*=" --include="*.py" .
grep -r "password" --include="*.py" . | grep -v "hash\|bcrypt\|test\|example"

# stockprice-main/ 내 개인 데이터 확인
cat stockprice-main/scan_cache.json | head -50
cat stockprice-main/watchlist.json
```

### 1-3. 민감 파일 히스토리 제거 (필요 시)

```bash
# git-filter-repo 설치
brew install git-filter-repo

# 특정 파일을 히스토리에서 완전 제거
git filter-repo --path .env --invert-paths
git filter-repo --path stockprice-main/scan_cache.json --invert-paths
```

> ⚠️ 히스토리 재작성 후에는 `git push --force`가 필요합니다.  
> 팀원 전원과 합의 후 진행하고, GitHub에서 캐시된 뷰도 갱신되는지 확인하세요.

### 체크리스트

- [ ] trufflehog 스캔 완료, 시크릿 없음 확인
- [ ] `.env`가 `.gitignore`에 등록되어 있음
- [ ] `stockprice-main/scan_cache.json`의 개인 데이터 검토 완료
- [ ] `stockprice-main/watchlist.json`의 개인 데이터 검토 완료

---

## 2. 팀원 실명 노출 동의 확인

> `README.md`와 `docs/REFACTORING_PLAN.md`의 팀 섹션에 팀원 실명이 명시되어 있습니다.

### 현재 노출 위치

| 파일 | 내용 |
| ---- | ---- |
| `README.md` §12 팀 | 지운, 공탁, 진우, 종윤 및 담당 역할 |
| `docs/REFACTORING_PLAN.md` §12 협업 가이드 | 동일 |

### 처리 방법 (팀 합의 필요)

**옵션 A — 실명 유지**: 팀원 전원 서면 동의 후 그대로 공개  
**옵션 B — GitHub ID로 대체**: `@jiun`, `@gongtack` 등 닉네임 사용  
**옵션 C — 역할만 표기**: 이름 제거, 역할(Frontend, Backend, ML, DevOps)만 남김

### 체크리스트

- [ ] 팀원 4명 전원 동의 확인 (실명 공개 또는 대체 방식 합의)
- [ ] `README.md` 팀 섹션 업데이트
- [ ] `docs/REFACTORING_PLAN.md` 팀 섹션 업데이트

---

## 3. LICENSE 파일 추가

루트 디렉토리에 `LICENSE` 파일을 생성합니다.

```
MIT License

Copyright (c) 2025 StockPriceAI Team

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

> **연도**와 **Copyright 저작권자 이름**을 실제 값으로 채우세요.  
> GitHub에서 저장소를 생성할 때 MIT 라이선스를 선택하면 자동 생성됩니다.

### 체크리스트

- [ ] 루트에 `LICENSE` 파일 생성 (연도·이름 기입 완료)

---

## 4. 패키지 메타데이터 업데이트

### 4-1. `backend/pyproject.toml`

```toml
[tool.poetry]
name = "stockai-backend"
version = "0.1.0"
license = "MIT"                          # 추가
authors = ["StockPriceAI Team <팀 이메일>"]  # 실제 이메일로 교체
```

### 4-2. `ml/pyproject.toml`

```toml
[tool.poetry]
name = "stockai-ml"
version = "0.1.0"
license = "MIT"                          # 추가
authors = ["StockPriceAI Team <팀 이메일>"]  # 실제 이메일로 교체
```

### 4-3. `frontend/package.json`

```json
{
  "name": "stockprice-frontend",
  "version": "0.1.0",
  "license": "MIT",
  "author": "StockPriceAI Team"
}
```

### 체크리스트

- [ ] `backend/pyproject.toml` — `license`, `authors` 필드 추가
- [ ] `ml/pyproject.toml` — `license`, `authors` 필드 추가
- [ ] `frontend/package.json` — `license`, `author` 필드 추가

---

## 5. README.md 업데이트

### 5-1. 라이선스 배지 및 섹션 추가

README 상단 배지 영역에 추가:

```markdown
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)
```

README 하단에 라이선스 섹션 추가:

```markdown
## License

This project is licensed under the MIT License — see the [LICENSE](LICENSE) file for details.
```

### 5-2. GitHub URL 플레이스홀더 교체

현재 README와 REFACTORING_PLAN.md에 `your-org/StockPriceAI` 플레이스홀더가 남아 있습니다.

```bash
# 플레이스홀더 위치 확인
grep -rn "your-org" .
```

실제 GitHub 저장소 URL로 일괄 교체하세요.

### 5-3. 리팩토링 진행 현황 표 업데이트

`README.md` §10의 Phase 상태가 실제와 다릅니다.

| Phase | 실제 상태 | README 표기 |
| ----- | --------- | ----------- |
| 3     | ✅ 완료   | 🔜 예정    |
| 4     | ✅ 완료   | 🔜 예정    |

실제 완료 상태로 업데이트 필요합니다.

### 체크리스트

- [ ] 라이선스 배지 추가 (상단)
- [ ] 라이선스 섹션 추가 (하단)
- [ ] `your-org/StockPriceAI` → 실제 GitHub URL 교체
- [ ] Phase 진행 현황 표 현행화

---

## 6. 의존성 라이선스 호환성 확인

MIT와 충돌하는 라이선스(GPL, AGPL 등)를 가진 패키지가 포함되면 법적 문제가 생깁니다.

### 6-1. Python 의존성 확인

```bash
# pip-licenses 설치
pip install pip-licenses

# backend
cd backend && poetry run pip install pip-licenses && poetry run pip-licenses --format=markdown

# ml
cd ../ml && poetry run pip install pip-licenses && poetry run pip-licenses --format=markdown
```

### 6-2. Node.js 의존성 확인

```bash
cd frontend
npx license-checker --summary
# GPL/AGPL 패키지가 있는지 확인
npx license-checker --failOn "GPL;AGPL"
```

### 6-3. 주요 의존성 라이선스 참고

| 패키지 | 라이선스 | MIT 호환 |
| ------ | -------- | -------- |
| FastAPI | MIT | ✅ |
| SQLAlchemy | MIT | ✅ |
| python-jose | MIT | ✅ |
| PyTorch | BSD-style | ✅ |
| XGBoost | Apache 2.0 | ✅ |
| Celery | BSD | ✅ |
| Next.js | MIT | ✅ |
| Plotly.js | MIT | ✅ |

### 6-4. LGPL/GPL 패키지 발견 시 처리

- **LGPL**: 동적 링크라면 MIT 프로젝트에 포함 가능. 해당 패키지를 `NOTICE` 파일에 명시
- **GPL**: MIT 프로젝트에 포함 불가. 동등 기능의 MIT/BSD 패키지로 교체 필요

```bash
# NOTICE 파일 예시 (LGPL 패키지가 있는 경우)
cat > NOTICE <<EOF
This project includes software with the following licenses:
- [패키지명] — LGPL v2.1 — [URL]
EOF
```

### 체크리스트

- [ ] Python 의존성 라이선스 전체 목록 생성 및 검토
- [ ] Node.js 의존성 라이선스 전체 목록 생성 및 검토
- [ ] GPL/AGPL 패키지 없음 확인 (또는 교체 완료)
- [ ] LGPL 패키지가 있다면 `NOTICE` 파일 작성

---

## 7. CODE_OF_CONDUCT.md 추가

외부 기여자가 생겼을 때 커뮤니티 기준을 명시합니다. GitHub에서 자동으로 인식하는 파일입니다.

루트에 `CODE_OF_CONDUCT.md` 생성:

```markdown
# Contributor Covenant Code of Conduct

## Our Pledge

We as members, contributors, and leaders pledge to make participation in our community
a harassment-free experience for everyone.

## Our Standards

Examples of behavior that contributes to a positive environment:
- Using welcoming and inclusive language
- Being respectful of differing viewpoints
- Gracefully accepting constructive criticism

Examples of unacceptable behavior:
- The use of sexualized language or imagery
- Personal or political attacks
- Public or private harassment

## Enforcement

Instances of abusive or unacceptable behavior may be reported by contacting the project team.
All complaints will be reviewed and investigated.

## Attribution

This Code of Conduct is adapted from the [Contributor Covenant](https://www.contributor-covenant.org), version 2.1.
```

### 체크리스트

- [ ] 루트에 `CODE_OF_CONDUCT.md` 생성
- [ ] `CONTRIBUTING.md`에 Code of Conduct 링크 추가

---

## 8. GitHub 저장소 설정

코드 외 GitHub UI에서 설정해야 하는 항목입니다.

### 8-1. 저장소 기본 설정

| 항목 | 설정값 |
| ---- | ------ |
| Repository visibility | Public |
| License | MIT License (자동 감지) |
| Description | AI 기반 주식 분석 웹 서비스 (XGBoost + LSTM, S&P 500 스캐너) |
| Website | Vercel 배포 URL |

### 8-2. Topics 추가

GitHub 검색 노출을 위해 Topics를 설정합니다 (Settings → General → Topics):

```
python fastapi nextjs typescript machine-learning
stock-analysis xgboost lstm celery redis docker
```

### 8-3. 브랜치 보호 규칙 강제 설정

`CONTRIBUTING.md`에 명시된 규칙을 GitHub Settings에서 실제로 강제합니다.

**Settings → Branches → Add rule:**

| 브랜치 | 규칙 |
| ------ | ---- |
| `main` | Require PR + 1 reviewer approval + CI passing |
| `develop` | Require PR + CI passing |

### 8-4. Discussions / Issues 활성화 여부 결정

| 기능 | 권장 |
| ---- | ---- |
| Issues | ✅ 활성화 (버그 리포트, 기능 제안) |
| Discussions | 선택 (Q&A, 커뮤니티 포럼) |
| Wiki | 비활성화 (문서는 `docs/` 폴더로 통합) |

### 체크리스트

- [ ] 저장소 Public으로 전환
- [ ] Description, Website 입력
- [ ] Topics 설정
- [ ] `main` 브랜치 보호 규칙 적용
- [ ] `develop` 브랜치 보호 규칙 적용
- [ ] Issues 활성화 확인

---

## 전체 진행 현황

> 아래 체크리스트를 완료 순서대로 체크하세요.

- [ ] **1. Git 히스토리 시크릿 스캔** — 공개 전 필수
- [ ] **2. 팀원 실명 노출 동의** — 공개 전 필수
- [ ] **3. LICENSE 파일 추가**
- [ ] **4. 패키지 메타데이터 업데이트** (pyproject.toml × 2, package.json)
- [ ] **5. README.md 업데이트** (배지, 라이선스 섹션, URL, Phase 현황)
- [ ] **6. 의존성 라이선스 호환성 확인**
- [ ] **7. CODE_OF_CONDUCT.md 추가**
- [ ] **8. GitHub 저장소 설정** (Topics, 브랜치 보호, Public 전환)
