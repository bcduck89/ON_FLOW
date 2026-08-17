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
from repositories.regular_run_repository import list_regular_runs
from services.transaction_engine import reprocess_transactions_for_member
from utils.date_utils import calculate_age


def get_raw_member_list() -> pd.DataFrame:
    return add_member_attendance_counts(list_members())


def _get_payment_status_masks(
    members: pd.DataFrame,
    reference_date: date,
) -> tuple[pd.Series, pd.Series, pd.Series]:
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
    return statuses, unpaid_mask, removal_due_mask


def annotate_removal_due_memo(
    members: pd.DataFrame,
    reference_date: date | None = None,
) -> pd.DataFrame:
    if members.empty:
        return members.copy()

    annotated = members.copy()
    _, _, removal_due_mask = _get_payment_status_masks(
        annotated,
        reference_date or date.today(),
    )
    memo = annotated.get(
        "memo",
        pd.Series("", index=annotated.index, dtype="object"),
    ).fillna("").astype(str).str.strip()

    def add_removal_label(value: str) -> str:
        if "강퇴조치 대상" in value:
            return value
        return f"{value} · 강퇴조치 대상" if value else "강퇴조치 대상"

    annotated["memo"] = memo
    annotated.loc[removal_due_mask, "memo"] = memo.loc[removal_due_mask].apply(
        add_removal_label
    )
    return annotated


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
    management_columns = [
        "회원번호",
        "이름",
        "닉네임",
        "가입일",
        "가입 경과개월",
        "정기 참석",
        "자유 참석",
        "총 참석",
        "월 평균 참석",
    ]

    if members.empty:
        return {
            "total": 0,
            "active": 0,
            "withdrawn": 0,
            "total_gender": {"male": 0, "female": 0},
            "active_gender": {"male": 0, "female": 0},
            "withdrawn_gender": {"male": 0, "female": 0},
            "fee_exempt": 0,
            "unpaid": 0,
            "removal_due": 0,
            "management_target": 0,
            "unpaid_members": pd.DataFrame(columns=dashboard_columns),
            "removal_due_members": pd.DataFrame(columns=dashboard_columns),
            "management_target_members": pd.DataFrame(columns=management_columns),
        }

    statuses, unpaid_mask, removal_due_mask = _get_payment_status_masks(
        members,
        reference_date,
    )
    genders = members.get(
        "gender",
        pd.Series("", index=members.index, dtype="object"),
    ).fillna("").astype(str).str.strip()
    active_mask = statuses.isin(["active", "grace", "fee_exempt"])
    withdrawn_mask = statuses.eq("withdrawn")

    def gender_counts(mask: pd.Series) -> dict:
        return {
            "male": int((mask & genders.eq("남성")).sum()),
            "female": int((mask & genders.eq("여성")).sum()),
        }

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

    def build_management_target_view() -> pd.DataFrame:
        joined_dates = pd.to_datetime(
            members.get(
                "joined_at",
                pd.Series("", index=members.index, dtype="object"),
            ),
            errors="coerce",
        )
        regular_counts = pd.to_numeric(
            members.get(
                "정기 참석횟수",
                pd.Series(0, index=members.index, dtype="int64"),
            ),
            errors="coerce",
        ).fillna(0)
        free_counts = pd.to_numeric(
            members.get(
                "자유 참석횟수",
                pd.Series(0, index=members.index, dtype="int64"),
            ),
            errors="coerce",
        ).fillna(0)
        elapsed_months = (
            (reference_date.year - joined_dates.dt.year) * 12
            + reference_date.month
            - joined_dates.dt.month
            + 1
        ).clip(lower=1)
        total_counts = regular_counts + free_counts
        monthly_average = total_counts / elapsed_months
        management_mask = (
            active_mask
            & joined_dates.notna()
            & joined_dates.dt.date.le(reference_date)
            & monthly_average.lt(1)
        )

        view = members.loc[management_mask].copy()
        view["가입일"] = joined_dates.loc[management_mask].dt.date
        view["가입 경과개월"] = elapsed_months.loc[management_mask].astype(int)
        view["정기 참석"] = regular_counts.loc[management_mask].astype(int)
        view["자유 참석"] = free_counts.loc[management_mask].astype(int)
        view["총 참석"] = total_counts.loc[management_mask].astype(int)
        view["월 평균 참석"] = monthly_average.loc[management_mask].round(2)
        view = view.rename(
            columns={
                "member_code": "회원번호",
                "name": "이름",
                "nickname": "닉네임",
            }
        )

        for column in management_columns:
            if column not in view.columns:
                view[column] = ""

        return view[management_columns].sort_values(
            ["월 평균 참석", "가입일", "이름"],
            ascending=[True, True, True],
        ).reset_index(drop=True)

    management_target_members = build_management_target_view()

    return {
        "total": int(len(members)),
        "active": int(active_mask.sum()),
        "withdrawn": int(withdrawn_mask.sum()),
        "total_gender": gender_counts(pd.Series(True, index=members.index)),
        "active_gender": gender_counts(active_mask),
        "withdrawn_gender": gender_counts(withdrawn_mask),
        "fee_exempt": int(statuses.eq("fee_exempt").sum()),
        "unpaid": int(unpaid_mask.sum()),
        "removal_due": int(removal_due_mask.sum()),
        "management_target": int(len(management_target_members)),
        "unpaid_members": build_status_view(unpaid_mask),
        "removal_due_members": build_status_view(removal_due_mask),
        "management_target_members": management_target_members,
    }


def get_member_dashboard(reference_date: date | None = None) -> dict:
    return build_member_dashboard(get_raw_member_list(), reference_date=reference_date)


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


def add_member_attendance_counts(
    members: pd.DataFrame,
    regular_runs: list[dict] | None = None,
    include_history: bool = False,
) -> pd.DataFrame:
    counted = members.copy()
    counted["정기 참석횟수"] = 0
    counted["자유 참석횟수"] = 0
    if include_history:
        counted["참석 러닝 상세"] = pd.Series(
            [[] for _ in range(len(counted))],
            index=counted.index,
            dtype="object",
        )
    if counted.empty:
        return counted

    if regular_runs is None:
        try:
            regular_runs = list_regular_runs()
        except Exception:
            regular_runs = []

    for member_index, member in counted.iterrows():
        identities = {
            str(value or "").replace(" ", "").casefold()
            for value in (member.get("name", ""), member.get("nickname", ""))
            if str(value or "").strip()
        }
        for run_index, run in enumerate(regular_runs):
            attendee_keys = {
                str(name or "").replace(" ", "").casefold()
                for name in (run.get("attendee_names") or [])
            }
            if identities.isdisjoint(attendee_keys):
                continue
            if run.get("run_type") == "정기":
                counted.at[member_index, "정기 참석횟수"] += 1
            elif run.get("run_type") == "자유":
                counted.at[member_index, "자유 참석횟수"] += 1
            if include_history:
                counted.at[member_index, "참석 러닝 상세"].append(
                    {
                        "번호": len(regular_runs) - run_index,
                        "구분": str(run.get("run_type") or ""),
                        "날짜": str(run.get("run_date") or "")[:10],
                    }
                )
    return counted


def _format_member_list(
    members: pd.DataFrame,
    include_attendance_history: bool = False,
) -> pd.DataFrame:
    if include_attendance_history:
        members["참석 러닝"] = members["참석 러닝 상세"].apply(
            lambda runs: ":material/event_note: 보기"
            if runs
            else ":material/event_busy: 없음"
        )

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
        "정기 참석횟수",
        "자유 참석횟수",
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
    if include_attendance_history:
        display_cols.extend(["참석 러닝", "참석 러닝 상세"])

    if members.empty:
        return pd.DataFrame(columns=display_cols)

    return view[display_cols]


def get_member_list(include_attendance_history: bool = False) -> pd.DataFrame:
    members = annotate_removal_due_memo(list_members())
    members = add_member_attendance_counts(
        members,
        include_history=include_attendance_history,
    )
    return _format_member_list(members, include_attendance_history)


def get_member_management_data(reference_date: date | None = None) -> dict:
    """회원관리 화면에 필요한 데이터를 DB 조회 한 번씩으로 구성한다."""
    members = annotate_removal_due_memo(
        list_members(),
        reference_date=reference_date,
    )
    try:
        regular_runs = list_regular_runs()
    except Exception:
        regular_runs = []
    counted_members = add_member_attendance_counts(
        members,
        regular_runs=regular_runs,
        include_history=True,
    )
    member_list = _format_member_list(
        counted_members.copy(),
        include_attendance_history=True,
    )
    csv_frame = _format_member_list(
        counted_members.copy(),
        include_attendance_history=False,
    )
    return {
        "dashboard": build_member_dashboard(
            counted_members,
            reference_date=reference_date,
        ),
        "members": member_list,
        "raw_members": counted_members,
        "csv": csv_frame.to_csv(
            index=False,
            encoding="utf-8-sig",
        ).encode("utf-8-sig"),
    }


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
