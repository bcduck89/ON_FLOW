import pandas as pd
import streamlit as st

from core.constants import (
    DEFAULT_CITY,
    DEFAULT_DISTRICT,
    GENDERS,
    MEMBER_STATUS,
    MEMBER_TYPES,
)
from database.client import check_supabase_connection
from services.auth_service import init_auth_state, is_developer
from services.member_service import (
    get_member_list,
    get_raw_member_list,
    add_member,
    edit_member,
    remove_member,
)
from ui.auth_widgets import render_top_auth


st.set_page_config(
    page_title="회원관리 | ON_FLOW",
    page_icon="👥",
    layout="wide",
)

init_auth_state()
render_top_auth(current_page="pages/01_회원관리.py")

st.title("👥 회원관리")
st.caption("ON_FLOW Member Management")

ok, msg = check_supabase_connection()
if not ok:
    st.error("Supabase 연결 실패")
    st.caption(msg)
    st.stop()

st.divider()


def safe_date(value):
    if value in ["", None]:
        return pd.Timestamp.today().date()
    try:
        return pd.to_datetime(value).date()
    except Exception:
        return pd.Timestamp.today().date()


menu = st.radio(
    "회원관리 메뉴",
    ["회원 목록", "회원 추가", "회원정보 수정 / 삭제"],
    horizontal=True,
)


# =========================================================
# 회원 목록
# =========================================================
if menu == "회원 목록":
    st.subheader("회원 목록")

    try:
        members = get_member_list()

        if members.empty:
            st.info("아직 등록된 회원이 없습니다.")
        else:
            st.dataframe(
                members,
                width="stretch",
                hide_index=True,
            )

    except Exception as e:
        st.error("회원 목록을 불러오는 중 오류가 발생했습니다.")
        st.exception(e)


# =========================================================
# 회원 추가
# =========================================================
elif menu == "회원 추가":
    st.subheader("회원 추가")

    with st.form("add_member_form", clear_on_submit=True):
        col1, col2 = st.columns(2)

        with col1:
            name = st.text_input("이름 *")
            nickname = st.text_input("닉네임")
            age = st.number_input("나이", min_value=0, max_value=120, value=0)

            gender = st.selectbox(
                "성별",
                GENDERS,
            )

            member_type = st.selectbox(
                "회원구분",
                options=list(MEMBER_TYPES.keys()),
                format_func=lambda x: MEMBER_TYPES[x],
            )

        with col2:
            city = st.text_input("시도", value=DEFAULT_CITY)
            district = st.text_input("시군구", value=DEFAULT_DISTRICT)
            deposit_name = st.text_input("입금자명")
            joined_at = st.date_input("가입일")

        memo = st.text_area("비고")

        submitted = st.form_submit_button("회원 추가", width="stretch")

        if submitted:
            try:
                add_member(
                    name=name,
                    nickname=nickname,
                    age=age if age > 0 else None,
                    gender=gender,
                    member_type=member_type,
                    city=city,
                    district=district,
                    deposit_name=deposit_name,
                    joined_at=joined_at,
                    memo=memo,
                )

                st.success(f"{name} 회원이 추가되었습니다.")

            except Exception as e:
                st.error("회원 추가 중 오류가 발생했습니다.")
                st.exception(e)


# =========================================================
# 회원정보 수정 / 삭제
# =========================================================
elif menu == "회원정보 수정 / 삭제":
    st.subheader("회원정보 수정 / 삭제")

    raw_members = get_raw_member_list()

    if raw_members.empty:
        st.info("수정할 회원이 없습니다.")
        st.stop()

    raw_members = raw_members.copy()

    raw_members["label"] = raw_members.apply(
        lambda row: f'{row.get("member_code", "")} | {row.get("name", "")} | {row.get("nickname", "")}',
        axis=1,
    )

    selected_label = st.selectbox(
        "수정할 회원 선택",
        raw_members["label"].tolist(),
    )

    selected_row = raw_members[raw_members["label"] == selected_label].iloc[0]
    member_id = int(selected_row["member_id"])

    st.divider()

    with st.form("edit_member_form"):
        col1, col2 = st.columns(2)

        with col1:
            edit_name = st.text_input(
                "이름 *",
                value=str(selected_row.get("name", "")),
            )

            edit_nickname = st.text_input(
                "닉네임",
                value=str(selected_row.get("nickname", "")),
            )

            current_age = selected_row.get("age", 0)
            try:
                current_age = int(current_age)
            except Exception:
                current_age = 0

            edit_age = st.number_input(
                "나이",
                min_value=0,
                max_value=120,
                value=current_age,
            )

            current_gender = str(selected_row.get("gender", ""))
            gender_index = GENDERS.index(current_gender) if current_gender in GENDERS else 0

            edit_gender = st.selectbox(
                "성별",
                GENDERS,
                index=gender_index,
            )

            current_member_type = str(selected_row.get("member_type", "member"))
            member_type_keys = list(MEMBER_TYPES.keys())
            member_type_index = (
                member_type_keys.index(current_member_type)
                if current_member_type in member_type_keys
                else 0
            )

            edit_member_type = st.selectbox(
                "회원구분",
                options=member_type_keys,
                index=member_type_index,
                format_func=lambda x: MEMBER_TYPES[x],
            )

        with col2:
            edit_city = st.text_input(
                "시도",
                value=str(selected_row.get("city", DEFAULT_CITY)),
            )

            edit_district = st.text_input(
                "시군구",
                value=str(selected_row.get("district", DEFAULT_DISTRICT)),
            )

            edit_deposit_name = st.text_input(
                "입금자명",
                value=str(selected_row.get("deposit_name", "")),
            )

            edit_joined_at = st.date_input(
                "가입일",
                value=safe_date(selected_row.get("joined_at", "")),
            )

            current_status = str(selected_row.get("status", "active"))
            status_keys = list(MEMBER_STATUS.keys())
            status_index = (
                status_keys.index(current_status)
                if current_status in status_keys
                else 0
            )

            edit_status = st.selectbox(
                "회원상태",
                options=status_keys,
                index=status_index,
                format_func=lambda x: MEMBER_STATUS[x],
            )

        edit_memo = st.text_area(
            "비고",
            value=str(selected_row.get("memo", "")),
        )

        submitted_edit = st.form_submit_button("회원정보 수정", width="stretch")

        if submitted_edit:
            try:
                edit_member(
                    member_id=member_id,
                    name=edit_name,
                    nickname=edit_nickname,
                    age=edit_age if edit_age > 0 else None,
                    gender=edit_gender,
                    member_type=edit_member_type,
                    city=edit_city,
                    district=edit_district,
                    deposit_name=edit_deposit_name,
                    joined_at=edit_joined_at,
                    status=edit_status,
                    memo=edit_memo,
                )

                st.success("회원정보가 수정되었습니다.")

            except Exception as e:
                st.error("회원정보 수정 중 오류가 발생했습니다.")
                st.exception(e)

    st.divider()
    st.subheader("회원 삭제")

    st.warning(
        "회원 삭제는 데이터베이스에서 회원 정보를 완전히 삭제합니다. "
        "운영 중에는 삭제보다 '탈퇴' 상태 변경을 권장합니다."
    )

    if is_developer():
        delete_confirm = st.checkbox(
            f"{selected_row.get('name', '')} 회원을 완전히 삭제하는 것에 동의합니다."
        )

        if st.button("회원 완전 삭제", type="primary", disabled=not delete_confirm):
            try:
                remove_member(member_id)
                st.success("회원이 삭제되었습니다.")
                st.rerun()

            except Exception as e:
                st.error("회원 삭제 중 오류가 발생했습니다.")
                st.exception(e)
    else:
        st.info("회원 완전 삭제는 개발자 계정으로 로그인해야 가능합니다.")