# ON_FLOW Development Log

## Project Direction

ON_FLOW는 부산광역시 동래구, 특히 온천천을 중심으로 활동하는 러닝 크루 운영 플랫폼이다.

초기에는 회비와 회원 관리를 위한 Streamlit 앱으로 시작했지만, 장기적으로는 지역 기반 사교, 운동, 생활 플랫폼으로 확장하는 방향으로 정리했다.

핵심 원칙은 다음과 같다.

- 회원이 ON_FLOW의 핵심 데이터다.
- 과도한 개인정보 수집은 지양한다.
- 운영자가 반복적으로 하는 일을 자동화한다.
- 항상 실행 가능한 상태를 유지하면서 Sprint 단위로 개발한다.
- Page는 DB를 직접 호출하지 않고, Service → Repository → Database 구조를 따른다.
- CSV는 운영 저장소가 아니라 Import, Export, Backup 용도로만 사용한다.

---

## Legacy에서 새 ON_FLOW로 전환한 이유

기존 ON_FLOW는 기능이 빠르게 늘어나면서 CSV 기반 manager 구조가 복잡해졌다.

기존 구조:

```text
Page
→ manager
→ CSV
```

새 구조:

```text
Page
→ Service
→ Repository
→ Supabase
```

이 구조로 바꾸는 이유는 다음과 같다.

- GitHub에 운영 데이터를 올리지 않기 위해
- 배포 환경에서도 데이터가 유지되도록 하기 위해
- 여러 운영자가 동시에 접속해도 안정적으로 관리하기 위해
- 향후 공지, 사진, QR 출석, 행사관리, 러닝지도 등을 확장하기 위해

---

## Project Naming

이제 새 프로젝트를 정식 ON_FLOW로 사용한다.

- 기존 프로젝트: `ON_FLOW_LEGACY`
- 새 프로젝트: `ON_FLOW`
- 이전에 부르던 V2는 내부적으로만 리팩터링 개념이고, 실제 이름은 ON_FLOW로 정리한다.

---

## Sprint 1

### 목표

실행 가능한 최소 Streamlit 프로젝트를 만든다.

### 완료

- `uv` 기반 Python 프로젝트 생성
- Streamlit 설치
- `app.py` 실행 성공
- 실행 명령 확정

```powershell
python -m streamlit run app.py
```

### 중요 결정

Windows 환경에서는 `uv run streamlit run app.py`보다 `python -m streamlit run app.py`를 기본 실행 명령으로 사용한다.

---

## Sprint 2 방향 수정

초기에는 프로젝트 골격 전체를 먼저 만들려 했으나, 실제 운영 관점에서 회원 데이터가 핵심이라고 판단했다.

Sprint 2 목표를 다음으로 수정했다.

```text
Sprint 2: 회원관리 목록 MVP
```

1차 목표:

```text
ON_FLOW 실행
→ 회원관리 페이지 진입
→ Supabase members 테이블 연결
→ 회원 목록 조회
```

그 이후 목표:

```text
회원 추가
회원 수정
회원 상태 변경
회원 삭제
```

---

## Member Schema Discussion

ON_FLOW는 동래구 중심의 지역 러닝 크루이며, 장기적으로 지역 생활 플랫폼으로 확장할 수 있다.

하지만 모임이 과도하게 무거워지지 않도록 개인정보 수집은 최소화한다.

### 결정된 회원 정보

| 필드 | 설명 |
|---|---|
| member_id | DB 자동 증가 회원 ID |
| name | 이름 |
| nickname | 닉네임 |
| age | 정확한 나이 |
| gender | 성별 |
| city | 시도, 기본값 부산광역시 |
| district | 시군구, 기본값 동래구 |
| deposit_name | 회비 입금자명 |
| joined_at | 가입일 |
| membership_start | 회비 유효 시작일 |
| membership_end | 회비 유효 종료일 |
| grace_until | 회비 납부 유예 마감일 |
| status | active, grace, fee_exempt, withdrawn |
| memo | 비고 |

### 받지 않기로 한 정보

초기 버전에서는 아래 정보는 받지 않는다.

- 전화번호
- 상세주소
- 생년월일
- 직업
- 학교/회사
- SNS 계정
- 건강정보
- 응급연락처

필요성이 명확해질 때까지 보류한다.

---

## Fee Policy

회비 체계는 다음과 같이 결정했다.

```text
1개월 회비: 2,000원
3개월 회비: 6,000원
```

납부 유효기간:

```text
1개월 납부:
입금한 달의 1일 ~ 해당 달 말일

3개월 납부:
입금한 달의 1일 ~ 3개월 후 말일
```

예시:

```text
2026-07-15에 2,000원 납부
→ 2026-07-01 ~ 2026-07-31 유효

2026-07-15에 6,000원 납부
→ 2026-07-01 ~ 2026-09-30 유효
```

유예기간:

```text
유효종료일 다음날부터 7일간
```

예시:

```text
유효종료일: 2026-07-31
유예기간: 2026-08-01 ~ 2026-08-07
2026-08-08부터 강퇴조치 대상
```

회원 상태:

| 상태 | 의미 |
|---|---|
| active | 회비 유효기간 안 |
| grace | 유효기간 종료 후 7일 이내 |
| fee_exempt | 납부예외 사유가 있어 미납 및 강퇴조치 대상에서 제외 |
| withdrawn | 탈퇴 |

---

## Supabase Migration

기존 CSV 저장 방식에서 Supabase PostgreSQL로 전환한다.

Supabase 테이블:

```text
members
transactions
fee_payments
officers
running_spots
audit_logs
```

추후 확장 예정:

```text
events
attendance
notices
photos
running_courses
```

---

## Supabase Network Issue

개발 중 Supabase 접속이 실패했다.

증상:

```text
WinError 10060
curl https://xxxx.supabase.co 실패
nslookup 결과가 honeypot-malware.anl.gov로 잘못 해석됨
Supabase Dashboard에서 Unhealthy로 보임
```

원인:

```text
eduroam 또는 해당 네트워크 DNS가 Supabase 도메인을 정상적으로 해석하지 못함
```

확인:

```text
스마트폰 핫스팟으로 변경하자 Supabase 프로젝트가 Healthy 상태로 변경됨
```

해결책:

```text
개발 중 Supabase 연결이 필요할 경우:
- 스마트폰 핫스팟 사용
- 집 인터넷 사용
- DNS를 1.1.1.1 또는 8.8.8.8로 변경
```

이 내용은 이후 `docs/TROUBLESHOOTING.md`로 분리할 예정이다.

---

## Current Execution Command

```powershell
python -m streamlit run app.py
```

---

## Immediate Next Steps

1. 새 Supabase 프로젝트에 전체 SQL 스키마 실행
2. `.streamlit/secrets.toml`에 새 Supabase URL과 Publishable Key 입력
3. `members` 테이블 연결 테스트
4. 회원 목록 조회 기능 확인
5. 회원 추가 기능 구현
6. 회원 CRUD 완성 후 Sprint 2 종료
7. Git commit 및 tag

권장 커밋:

```powershell
git add .
git commit -m "Sprint 2 - Member schema and Supabase setup"
git tag v0.2.0
```
