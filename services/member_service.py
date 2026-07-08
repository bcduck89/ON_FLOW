import pandas as pd

from core.constants import MEMBER_STATUS, MEMBER_TYPES
from repositories.member_repository import (
    list_members,
    insert_member,
    update_member,
    delete_member,
)


def get_raw_member_list() -> pd.DataFrame:
    return list_members()


def get_member_list() -> pd.DataFrame:
    members = list_members()

    if members.empty:
        return members

    members = members.copy()

    members["상태"] = (
        members["status"]
        .map(MEMBER_STATUS)
        .fillna(members["status"])
    )

    members["회원구분"] = (
        members["member_type"]
        .map(MEMBER_TYPES)
        .fillna(members["member_type"])
    )

    view = members.rename(
        columns={
            "member_id": "회원ID",
            "member_code": "회원번호",
            "name": "이름",
            "nickname": "닉네임",
            "age": "나이",
            "gender": "성별",
            "city": "시도",
            "district": "시군구",
            "deposit_name": "입금자명",
            "joined_at": "가입일",
            "membership_start": "유효시작일",
            "membership_end": "유효종료일",
            "grace_until": "납부유예마감일",
            "memo": "비고",
        }
    )

    display_cols = [
        "회원번호",
        "회원ID",
        "회원구분",
        "이름",
        "닉네임",
        "나이",
        "성별",
        "시도",
        "시군구",
        "입금자명",
        "가입일",
        "유효시작일",
        "유효종료일",
        "납부유예마감일",
        "상태",
        "비고",
    ]

    return view[display_cols]


def add_member(
    name: str,
    nickname: str,
    age: int | None,
    gender: str,
    member_type: str,
    city: str,
    district: str,
    deposit_name: str,
    joined_at,
    memo: str,
) -> None:
    if not name.strip():
        raise ValueError("이름은 필수입니다.")

    if member_type not in MEMBER_TYPES:
        raise ValueError("회원구분 값이 올바르지 않습니다.")

    row = {
        "name": name.strip(),
        "nickname": nickname.strip(),
        "age": int(age) if age else None,
        "gender": gender,
        "member_type": member_type,
        "city": city.strip(),
        "district": district.strip(),
        "deposit_name": deposit_name.strip(),
        "joined_at": str(joined_at) if joined_at else None,
        "membership_start": None,
        "membership_end": None,
        "grace_until": None,
        "status": "active",
        "memo": memo.strip(),
    }

    insert_member(row)


def edit_member(
    member_id: int,
    name: str,
    nickname: str,
    age: int | None,
    gender: str,
    member_type: str,
    city: str,
    district: str,
    deposit_name: str,
    joined_at,
    status: str,
    memo: str,
) -> None:
    if not name.strip():
        raise ValueError("이름은 필수입니다.")

    if member_type not in MEMBER_TYPES:
        raise ValueError("회원구분 값이 올바르지 않습니다.")

    if status not in MEMBER_STATUS:
        raise ValueError("회원상태 값이 올바르지 않습니다.")

    values = {
        "name": name.strip(),
        "nickname": nickname.strip(),
        "age": int(age) if age else None,
        "gender": gender,
        "member_type": member_type,
        "city": city.strip(),
        "district": district.strip(),
        "deposit_name": deposit_name.strip(),
        "joined_at": str(joined_at) if joined_at else None,
        "status": status,
        "memo": memo.strip(),
    }

    update_member(int(member_id), values)


def remove_member(member_id: int) -> None:
    delete_member(int(member_id))