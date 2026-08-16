from datetime import date

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
from services.auth_service import init_auth_state, is_admin, is_developer
from services.member_service import (
    build_unpaid_fee_message,
    get_member_dashboard,
    get_member_list,
    get_raw_member_list,
    add_member,
    edit_member,
    remove_member,
    export_members_csv,
    import_members_from_csv,
)
from ui.auth_widgets import render_top_auth
from utils.date_utils import date_input_bounds


st.set_page_config(
    page_title="회원관리 | ON_FLOW",
    page_icon="👥",
    layout="wide",
)

init_auth_state()
render_top_auth(current_page="app_pages/01_회원관리.py")

st.title("👥 회원관리")
st.caption("ON_FLOW Member Management")

if not is_admin():
    st.warning("회원관리는 관리자 권한으로 로그인해야 사용할 수 있습니다.")
    st.stop()

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


def optional_date(value):
    if value in ["", None]:
        return None

    try:
        return pd.to_datetime(value).date()
    except Exception:
        return None


today = date.today()
earliest_date, latest_date = date_input_bounds(today)


# =========================================================
# 대시보드
# =========================================================
with st.container():
    st.subheader("회원 현황")

    try:
        dashboard = get_member_dashboard(reference_date=today)

        st.html(
            """
            <style>
            .st-key-member_total_card {background:#eff6ff;border-color:#93c5fd;border-left:5px solid #2563eb;}
            .st-key-member_active_card {background:#ecfdf5;border-color:#86efac;border-left:5px solid #16a34a;}
            .st-key-member_withdrawn_card {background:#f8fafc;border-color:#cbd5e1;border-left:5px solid #64748b;}
            .st-key-member_unpaid_card {background:#fff7ed;border-color:#fdba74;border-left:5px solid #f97316;}
            .st-key-member_exempt_card {background:#faf5ff;border-color:#d8b4fe;border-left:5px solid #9333ea;}
            .st-key-member_removal_card {background:#fef2f2;border-color:#fca5a5;border-left:5px solid #dc2626;}
            </style>
            """
        )

        metric_cards = [
            ("member_total_card", "총 등록 인원", dashboard["total"]),
            ("member_active_card", "현 활동인원", dashboard["active"]),
            ("member_withdrawn_card", "탈퇴인원", dashboard["withdrawn"]),
            ("member_unpaid_card", "회비미납인원", dashboard["unpaid"]),
            ("member_exempt_card", "납부예외인원", dashboard["fee_exempt"]),
            ("member_removal_card", "강퇴조치 대상", dashboard["removal_due"]),
        ]

        with st.container(horizontal=True):
            for card_key, label, value in metric_cards:
                with st.container(border=True, key=card_key):
                    st.metric(label, f"{value}명")

        st.caption(
            "회비 미납은 유효종료일 다음 날부터 납부유예마감일까지 집계합니다. "
            "납부예외·탈퇴 회원은 제외됩니다."
        )

        show_unpaid = st.session_state.get("show_unpaid_members", False)
        button_label = "회비 미납인원 접기" if show_unpaid else "회비 미납인원 보기"
        show_removal_due = st.session_state.get("show_removal_due_members", False)
        removal_button_label = (
            "강퇴조치 대상 접기" if show_removal_due else "강퇴조치 대상 보기"
        )

        with st.container(gap="small", width="content"):
            if st.button(button_label, icon=":material/groups:"):
                st.session_state["show_unpaid_members"] = not show_unpaid
                show_unpaid = not show_unpaid

            if st.button(removal_button_label, icon=":material/person_remove:"):
                st.session_state["show_removal_due_members"] = not show_removal_due
                show_removal_due = not show_removal_due

        if show_unpaid:
            st.markdown("#### 회비 미납인원")
            unpaid_members = dashboard["unpaid_members"]

            if unpaid_members.empty:
                st.success("현재 회비 납부 확인이 필요한 회원이 없습니다.")
            else:
                st.dataframe(
                    unpaid_members,
                    width="stretch",
                    hide_index=True,
                )

                st.markdown("#### 카카오톡 안내문")
                st.caption("아래 문구 오른쪽 위의 복사 버튼을 눌러 바로 붙여넣을 수 있습니다.")
                st.code(
                    build_unpaid_fee_message(unpaid_members),
                    language=None,
                    wrap_lines=True,
                )

        if show_removal_due:
            st.markdown("#### 강퇴조치 대상")
            removal_due_members = dashboard["removal_due_members"]

            if removal_due_members.empty:
                st.success("현재 강퇴조치 대상 회원이 없습니다.")
            else:
                st.warning(
                    "납부유예마감일이 지난 회원입니다. 조치 전 납부 여부와 "
                    "납부예외 사유를 확인해주세요."
                )
                st.dataframe(
                    removal_due_members,
                    width="stretch",
                    hide_index=True,
                )

    except Exception as e:
        st.error("회원 현황을 불러오는 중 오류가 발생했습니다.")
        st.exception(e)


st.divider()

menu = st.segmented_control(
    "회원관리 메뉴",
    ["회원 목록", "회원 추가", "회원 일괄 업로드", "회원정보 수정 / 삭제"],
    default="회원 목록",
    required=True,
    key="member_management_menu",
    label_visibility="collapsed",
    width="stretch",
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

            csv_data = export_members_csv()

            st.download_button(
                label="회원목록 CSV 다운로드",
                data=csv_data,
                file_name="onflow_members.csv",
                mime="text/csv",
                width="stretch",
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

            birth_date = st.date_input(
                "생년월일",
                value=None,
                min_value=earliest_date,
                max_value=today,
                format="YYYY-MM-DD",
            )

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

            joined_at = st.date_input(
                "가입일",
                min_value=earliest_date,
                max_value=latest_date,
                format="YYYY-MM-DD",
            )

        memo = st.text_area("비고")

        submitted = st.form_submit_button("회원 추가", width="stretch")

        if submitted:
            try:
                reprocess_result = add_member(
                    name=name,
                    nickname=nickname,
                    birth_date=birth_date,
                    gender=gender,
                    member_type=member_type,
                    city=city,
                    district=district,
                    deposit_name=deposit_name,
                    joined_at=joined_at,
                    memo=memo,
                )

                st.success(f"{name} 회원이 추가되었습니다.")

                if not reprocess_result.empty:
                    st.info("회원 추가 후 미매칭 거래가 자동으로 재처리되었습니다.")
                    st.dataframe(
                        reprocess_result,
                        width="stretch",
                        hide_index=True,
                    )

            except Exception as e:
                st.error("회원 추가 중 오류가 발생했습니다.")
                st.exception(e)


# =========================================================
# 회원 일괄 업로드
# =========================================================
elif menu == "회원 일괄 업로드":
    st.subheader("회원 CSV 일괄 업로드")

    st.info(
        "CSV 컬럼 형식: 이름, 닉네임, 생년월일, 성별, 회원구분, 시도, 시군구, 입금자명, 가입일, 비고"
    )

    template = pd.DataFrame(
        [
            {
                "이름": "홍길동",
                "닉네임": "길동",
                "생년월일": "1996-01-01",
                "성별": "남성",
                "회원구분": "일반",
                "시도": "부산광역시",
                "시군구": "동래구",
                "입금자명": "홍길동",
                "가입일": "2026-07-01",
                "비고": "",
            }
        ]
    )

    st.download_button(
        label="업로드 양식 다운로드",
        data=template.to_csv(index=False, encoding="utf-8-sig").encode("utf-8-sig"),
        file_name="onflow_member_upload_template.csv",
        mime="text/csv",
        width="stretch",
    )

    uploaded_file = st.file_uploader(
        "회원 CSV 파일 업로드",
        type=["csv"],
    )

    if uploaded_file is not None:
        if st.button("회원 일괄 업로드 실행", type="primary", width="stretch"):
            try:
                result = import_members_from_csv(uploaded_file)
                st.success("회원 일괄 업로드가 완료되었습니다.")
                st.dataframe(result, width="stretch", hide_index=True)

            except Exception as e:
                st.error("회원 일괄 업로드 중 오류가 발생했습니다.")
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

    with st.container(horizontal=True):
        st.metric("정기 러닝 참석", f"{int(selected_row.get('정기 참석횟수', 0))}회")
        st.metric("자유 러닝 참석", f"{int(selected_row.get('자유 참석횟수', 0))}회")

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

            edit_birth_date = st.date_input(
                "생년월일",
                value=optional_date(selected_row.get("birth_date", "")),
                min_value=earliest_date,
                max_value=today,
                format="YYYY-MM-DD",
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
                min_value=earliest_date,
                max_value=latest_date,
                format="YYYY-MM-DD",
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
            st.caption("납부예외로 변경하는 경우 사유를 비고에 기록해주세요.")

        edit_memo = st.text_area(
            "비고",
            value=str(selected_row.get("memo", "")),
        )

        submitted_edit = st.form_submit_button("회원정보 수정", width="stretch")

        if submitted_edit:
            try:
                reprocess_result = edit_member(
                    member_id=member_id,
                    name=edit_name,
                    nickname=edit_nickname,
                    birth_date=edit_birth_date,
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

                if not reprocess_result.empty:
                    st.info("회원정보 수정 후 미매칭 거래가 자동으로 재처리되었습니다.")
                    st.dataframe(
                        reprocess_result,
                        width="stretch",
                        hide_index=True,
                    )

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
