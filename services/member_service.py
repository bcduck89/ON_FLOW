from datetime import date

import pandas as pd

from core.constants import (
    DEFAULT_CITY,
    DEFAULT_DISTRICT,
    MEMBER_STATUS,
    MEMBER_TYPES,
)
from repositories.member_repository import (
    list_members,
    insert_member,
    insert_members,
    update_member,
    delete_member,
)
from services.transaction_engine import reprocess_transactions_for_member
from utils.date_utils import calculate_age


def get_raw_member_list() -> pd.DataFrame:
    return list_members()


def build_member_dashboard(
    members: pd.DataFrame,
    reference_date: date | None = None,
) -> dict:
    """회원 현황과 회비 미납 회원 목록을 계산한다."""
    reference_date = reference_date or date.today()
    members = members.copy()

    dashboard_columns = [
        "회원번호",
        "이름",
        "닉네임",
        "유효종료일",
        "납부유예마감일",
        "상태",
    ]

    if members.empty:
        return {
            "total": 0,
            "active": 0,
            "dormant": 0,
            "withdrawn": 0,
            "fee_exempt": 0,
            "unpaid": 0,
            "removal_due": 0,
            "unpaid_members": pd.DataFrame(columns=dashboard_columns),
            "removal_due_members": pd.DataFrame(columns=dashboard_columns),
        }

    statuses = members.get(
        "status",
        pd.Series("", index=members.index, dtype="object"),
    ).fillna("").astype(str).str.strip()
    membership_end_dates = pd.to_datetime(
        members.get(
            "membership_end",
            pd.Series("", index=members.index, dtype="object"),
        ),
        errors="coerce",
    ).dt.date
    grace_dates = pd.to_datetime(
        members.get(
            "grace_until",
            pd.Series("", index=members.index, dtype="object"),
        ),
        errors="coerce",
    ).dt.date

    payment_managed_mask = statuses.isin(["active", "grace"])
    unpaid_mask = (
        payment_managed_mask
        & membership_end_dates.notna()
        & grace_dates.notna()
        & membership_end_dates.lt(reference_date)
        & grace_dates.ge(reference_date)
    )
    removal_due_mask = (
        payment_managed_mask
        & grace_dates.notna()
        & grace_dates.lt(reference_date)
    )

    def build_status_view(mask: pd.Series) -> pd.DataFrame:
        view = members.loc[mask].copy()
        view["상태"] = statuses.loc[mask].map(MEMBER_STATUS).fillna(statuses.loc[mask])
        view = view.rename(
            columns={
                "member_code": "회원번호",
                "name": "이름",
                "nickname": "닉네임",
                "membership_end": "유효종료일",
                "grace_until": "납부유예마감일",
            }
        )

        for column in dashboard_columns:
            if column not in view.columns:
                view[column] = ""

        return view[dashboard_columns].reset_index(drop=True)

    return {
        "total": int(len(members)),
        "active": int(statuses.isin(["active", "grace", "fee_exempt"]).sum()),
        "dormant": int(statuses.eq("dormant").sum()),
        "withdrawn": int(statuses.eq("withdrawn").sum()),
        "fee_exempt": int(statuses.eq("fee_exempt").sum()),
        "unpaid": int(unpaid_mask.sum()),
        "removal_due": int(removal_due_mask.sum()),
        "unpaid_members": build_status_view(unpaid_mask),
        "removal_due_members": build_status_view(removal_due_mask),
    }


def get_member_dashboard(reference_date: date | None = None) -> dict:
    return build_member_dashboard(list_members(), reference_date=reference_date)


def build_unpaid_fee_message(unpaid_members: pd.DataFrame) -> str:
    if unpaid_members.empty:
        return "현재 회비 납부 확인이 필요한 회원이 없습니다. 감사합니다 😊"

    names = []
    for _, member in unpaid_members.iterrows():
        name = str(member.get("이름", "")).strip()
        nickname = str(member.get("닉네임", "")).strip()
        display_name = f"{name}({nickname})" if nickname and nickname != name else name
        if display_name:
            names.append(display_name)

    member_lines = "\n".join(f"- {name}" for name in names)
    return (
        "안녕하세요, ON:FLOW입니다 😊\n"
        "회비 납부 확인이 필요한 분을 안내드립니다.\n"
        f"{member_lines}\n"
        "이미 납부하셨다면 편하게 말씀해주세요. 감사합니다!"
    )


def get_member_list() -> pd.DataFrame:
    members = list_members()

    if members.empty:
        return members

    members = members.copy()

    members["나이 (만)"] = members["birth_date"].apply(calculate_age)

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
            "birth_date": "생년월일",
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
        "생년월일",
        "나이 (만)",
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
    birth_date,
    gender: str,
    member_type: str,
    city: str,
    district: str,
    deposit_name: str,
    joined_at,
    memo: str,
) -> pd.DataFrame:
    if not name.strip():
        raise ValueError("이름은 필수입니다.")

    if member_type not in MEMBER_TYPES:
        raise ValueError("회원구분 값이 올바르지 않습니다.")

    row = {
        "name": name.strip(),
        "nickname": nickname.strip(),
        "birth_date": str(birth_date) if birth_date else None,
        "age": None,
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

    inserted = insert_member(row)

    if inserted:
        return reprocess_transactions_for_member(inserted)

    return pd.DataFrame()


def edit_member(
    member_id: int,
    name: str,
    nickname: str,
    birth_date,
    gender: str,
    member_type: str,
    city: str,
    district: str,
    deposit_name: str,
    joined_at,
    status: str,
    memo: str,
) -> pd.DataFrame:
    if not name.strip():
        raise ValueError("이름은 필수입니다.")

    if member_type not in MEMBER_TYPES:
        raise ValueError("회원구분 값이 올바르지 않습니다.")

    if status not in MEMBER_STATUS:
        raise ValueError("회원상태 값이 올바르지 않습니다.")

    values = {
        "name": name.strip(),
        "nickname": nickname.strip(),
        "birth_date": str(birth_date) if birth_date else None,
        "age": None,
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

    member = values.copy()
    member["member_id"] = int(member_id)

    return reprocess_transactions_for_member(member)


def remove_member(member_id: int) -> None:
    delete_member(int(member_id))


def export_members_csv() -> bytes:
    df = get_member_list()
    return df.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig")


def normalize_member_type(value: str) -> str:
    value = str(value).strip()
    reverse_map = {v: k for k, v in MEMBER_TYPES.items()}

    if value in MEMBER_TYPES:
        return value

    if value in reverse_map:
        return reverse_map[value]

    return "member"


def import_members_from_csv(uploaded_file) -> pd.DataFrame:
    df = pd.read_csv(uploaded_file, encoding="utf-8-sig").fillna("")

    required_cols = ["이름"]

    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"필수 컬럼이 없습니다: {col}")

    rows = []
    result_rows = []

    for idx, row in df.iterrows():
        name = str(row.get("이름", "")).strip()

        if not name:
            result_rows.append(
                {
                    "행번호": idx + 2,
                    "이름": "",
                    "처리결과": "실패",
                    "사유": "이름이 비어 있음",
                }
            )
            continue

        member_type = normalize_member_type(row.get("회원구분", "일반"))

        birth_date = str(row.get("생년월일", "")).strip()
        if birth_date == "":
            birth_date = None

        joined_at = str(row.get("가입일", "")).strip()
        if joined_at == "":
            joined_at = None

        rows.append(
            {
                "name": name,
                "nickname": str(row.get("닉네임", "")).strip(),
                "birth_date": birth_date,
                "age": None,
                "gender": str(row.get("성별", "")).strip(),
                "member_type": member_type,
                "city": str(row.get("시도", DEFAULT_CITY)).strip() or DEFAULT_CITY,
                "district": str(row.get("시군구", DEFAULT_DISTRICT)).strip()
                or DEFAULT_DISTRICT,
                "deposit_name": str(row.get("입금자명", "")).strip(),
                "joined_at": joined_at,
                "membership_start": None,
                "membership_end": None,
                "grace_until": None,
                "status": "active",
                "memo": str(row.get("비고", "")).strip(),
            }
        )

        result_rows.append(
            {
                "행번호": idx + 2,
                "이름": name,
                "처리결과": "대기",
                "사유": "",
            }
        )

    inserted_members = insert_members(rows)

    for member in inserted_members:
        try:
            reprocess_result = reprocess_transactions_for_member(member)

            if not reprocess_result.empty:
                matched_name = member.get("name", "")

                for r in result_rows:
                    if r["이름"] == matched_name and r["처리결과"] == "대기":
                        r["처리결과"] = "반영완료"
                        r["사유"] = "회원등록 및 미매칭 거래 자동 재처리 완료"
                        break

        except Exception as e:
            matched_name = member.get("name", "")

            for r in result_rows:
                if r["이름"] == matched_name and r["처리결과"] == "대기":
                    r["처리결과"] = "반영완료"
                    r["사유"] = f"회원등록 완료, 자동 재처리 오류: {e}"
                    break

    for r in result_rows:
        if r["처리결과"] == "대기":
            r["처리결과"] = "반영완료"
            r["사유"] = "회원등록 완료"

    return pd.DataFrame(result_rows)
