"""
ON_FLOW common constants.
"""
USER_ROLES = {
    "guest": "비로그인",
    "admin": "관리자",
    "developer": "개발자",
}

MEMBER_TYPES = {
    "member": "일반",
    "staff": "운영진",
}

MEMBER_STATUS = {
    "active": "활동",
    "grace": "납부유예",
    "fee_exempt": "납부예외",
    "withdrawn": "탈퇴",
}

GENDERS = [
    "",
    "남성",
    "여성",
    "기타",
    "응답안함",
]

DEFAULT_CITY = "부산광역시"
DEFAULT_DISTRICT = "동래구"

MONTHLY_FEE = 2000
QUARTERLY_FEE = 6000
GRACE_DAYS = 7

TRANSACTION_STATUS = {
    "uploaded": "신규저장",
    "duplicated": "중복거래",
    "matched": "회원매칭",
    "fee_applied": "회비반영완료",
    "unmatched": "미매칭",
    "need_review": "확인필요",
    "skipped": "건너뜀",
}
