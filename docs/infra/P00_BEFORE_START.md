# AWS 시작 전 준비

> **이 문서를 먼저 읽으세요**: EC2·RDS를 생성하기 전에 이 페이지의 모든 설정을 완료하세요.  
> **다음 단계**: [P02_AWS.md](./P02_AWS.md)에서 실제 서버를 생성합니다.

---

## 1. AWS 계정 확인

AWS 계정이 없다면 [aws.amazon.com](https://aws.amazon.com) → **"무료로 시작"** 에서 생성합니다.

- 신용카드 등록이 필요합니다. 즉시 과금되지 않고 실제 사용량에 따라 청구됩니다.
- 가입 후 이메일 인증 → 전화 인증까지 완료해야 AWS 콘솔을 쓸 수 있습니다.

---

## 2. IAM 사용자 생성 (root 계정 직접 사용 금지)

AWS에 가입하면 처음 만들어지는 계정을 **root 계정**이라고 합니다. root 계정은 결제 정보를 포함한 AWS의 모든 권한을 가진 슈퍼 계정입니다.

> **root 계정으로 일상 작업을 하면 안 되는 이유**: 해킹이나 키 유출 사고 시 계정 전체, 결제 수단, 모든 서버가 동시에 위험에 노출됩니다. AWS 공식 가이드에서도 root 계정은 초기 설정에만 사용하고 이후엔 IAM 사용자를 써야 한다고 강권합니다.

### IAM 사용자 생성 절차

**root 계정으로 로그인한 뒤** 아래 순서로 진행합니다.

1. AWS 콘솔 검색창에 **IAM** → **Users** → **Create user** 클릭
2. **User name**: 원하는 이름 (예: `admin-yourname`) → **Next**
3. **"Provide user access to the AWS Management Console"** 체크
4. **Console password**: 강력한 비밀번호 설정 → **Next**
5. **Permissions options**: "Attach policies directly" 선택
6. 정책 목록에서 **AdministratorAccess** 검색 → 체크 → **Next**
7. **Create user** 클릭

생성 후 표시되는 **콘솔 로그인 URL** (예: `https://123456789.signin.aws.amazon.com/console`)을 북마크합니다.  
**이후 모든 작업은 이 IAM 사용자로 로그인해서 진행합니다.**

---

## 3. 예상 월 비용

이 프로젝트를 AWS에서 운영할 때 드는 비용입니다. (서울 리전 기준, 2025년 기준)

| 서비스 | 사양 | 예상 비용 |
|--------|------|-----------|
| EC2 | t3.medium (2 vCPU, 4GB RAM) | ~$33/월 |
| RDS | db.t3.micro PostgreSQL 16 | ~$16/월 |
| EBS 스토리지 | EC2 20GB + RDS 20GB gp3 | ~$5/월 |
| 데이터 전송 | 아웃바운드 트래픽 | ~$1~5/월 |
| Elastic IP | EC2에 연결된 동안 | 무료 |
| **합계** | | **~$55~60/월** |

> **t3.medium은 AWS 프리 티어(무료) 대상이 아닙니다.** 프리 티어는 t2.micro · t3.micro에만 해당됩니다.  
> ML 서비스 + Celery를 함께 돌리면 RAM 4GB 이상이 필요하므로 t3.medium을 사용합니다.

---

## 4. Billing Alert 설정 (필수!)

잘못된 설정(인스턴스를 여러 개 켜두거나, 데이터 전송이 폭증하는 경우 등)이 있어도 이 설정이 있으면 이메일로 즉시 알 수 있습니다. **반드시 설정하세요.**

1. AWS 콘솔 → 우측 상단 **계정 이름** 클릭 → **Billing and Cost Management**
2. 좌측 메뉴 **Budgets** → **Create budget**
3. **Budget type**: "Use a template (simplified)" → **Monthly cost budget** → **Next**
4. 다음 값 입력:

   | 항목 | 값 |
   |------|----|
   | **Budget name** | `monthly-cost-alert` |
   | **Budgeted amount** | `$80` (예상 ~$60 + 여유분) |
   | **Email recipients** | 본인 이메일 주소 |

5. **Create budget** 클릭

이제 월 누적 비용이 $80을 초과하면 이메일로 알림이 옵니다.

> **추가 권장**: 예산 생성 후 **"Add alert threshold"** 로 70% 기준 알림($56)도 추가하면 초과 전에 미리 경고를 받을 수 있습니다.

---

## 5. 리전(Region) 선택

**리전**은 AWS 서버가 실제로 위치한 지역입니다. AWS 콘솔 우측 상단에 현재 리전이 표시됩니다.

한국 사용자라면 **아시아 태평양(서울) `ap-northeast-2`** 를 선택하세요.

> **주의**: 리전을 바꾸면 이전 리전에서 만든 EC2·RDS가 목록에서 사라집니다. 삭제된 것이 아니라 다른 리전에 있는 것입니다. 항상 같은 리전에서 작업하고, EC2와 RDS를 반드시 **같은 리전**에 생성하세요.

---

설정이 모두 완료됐으면 [P02_AWS.md](./P02_AWS.md)로 넘어갑니다.
