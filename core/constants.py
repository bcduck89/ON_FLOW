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
    "dormant": "휴면",
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