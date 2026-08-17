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
    get_member_management_data,
    add_member,
    edit_member,
    remove_member,
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


@st.dialog("회원 참석 러닝")
def render_member_attendance_history(member: dict) -> None:
    name = str(member.get("이름") or "회원")
    nickname = str(member.get("닉네임") or "").strip()
    display_name = f"{name} ({nickname})" if nickname and nickname != name else name
    st.markdown(f"#### {display_name}")

    history = pd.DataFrame(
        member.get("참석 러닝 상세") or [],
        columns=["번호", "구분", "날짜"],
    )
    if history.empty:
        st.info("등록된 참석 러닝 기록이 없습니다.")
    else:
        st.dataframe(
            history,
            width="stretch",
            hide_index=True,
            column_config={
                "번호": st.column_config.NumberColumn(format="%d"),
                "날짜": st.column_config.DateColumn(format="YYYY-MM-DD"),
            },
        )

    with st.container(horizontal=True, horizontal_alignment="right"):
        if st.button("닫기", key="close_member_attendance_history"):
            st.session_state.pop("member_attendance_history", None)
            st.rerun()


def toggle_member_dashboard_panel(panel: str) -> None:
    current_panel = st.session_state.get("member_dashboard_panel")
    st.session_state["member_dashboard_panel"] = (
        None if current_panel == panel else panel
    )


def toggle_member_management_action(action: str) -> None:
    current_action = st.session_state.get("member_management_action")
    st.session_state["member_management_action"] = (
        None if current_action == action else action
    )


@st.cache_data(ttl="30s", max_entries=3, show_spinner=False)
def load_member_management_data(reference_date: date) -> dict:
    return get_member_management_data(reference_date=reference_date)


today = date.today()
earliest_date, latest_date = date_input_bounds(today)

try:
    member_management_data = load_member_management_data(today)
except Exception as error:
    st.error("회원관리 데이터를 불러오는 중 오류가 발생했습니다.")
    st.exception(error)
    st.stop()


# =========================================================
# 대시보드
# =========================================================
with st.container():
    st.subheader("회원 현황")

    try:
        dashboard = member_management_data["dashboard"]

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
            (
                "member_total_card",
                "총 등록 인원",
                dashboard["total"],
                dashboard["total_gender"],
            ),
            (
                "member_active_card",
                "현 활동인원",
                dashboard["active"],
                dashboard["active_gender"],
            ),
            (
                "member_withdrawn_card",
                "탈퇴인원",
                dashboard["withdrawn"],
                dashboard["withdrawn_gender"],
            ),
            ("member_unpaid_card", "회비미납인원", dashboard["unpaid"], None),
            ("member_exempt_card", "납부예외인원", dashboard["fee_exempt"], None),
            ("member_removal_card", "강퇴조치 대상", dashboard["removal_due"], None),
        ]

        with st.container(horizontal=True):
            for card_key, label, value, gender_breakdown in metric_cards:
                with st.container(border=True, key=card_key):
                    st.metric(label, f"{value}명")
                    if gender_breakdown is not None:
                        st.caption(
                            f"남성 {gender_breakdown['male']}명 · "
                            f"여성 {gender_breakdown['female']}명"
                        )

        st.caption(
            "회비 미납은 유효종료일 다음 날부터 납부유예마감일까지 집계합니다. "
            "납부예외·탈퇴 회원은 제외됩니다."
        )

        active_panel = st.session_state.get("member_dashboard_panel")
        panel_buttons = [
            ("unpaid", "회비 미납인원", ":material/groups:"),
            ("removal", "강퇴조치 대상", ":material/person_remove:"),
            ("management", "관리대상 인원", ":material/person_alert:"),
        ]

        with st.container(horizontal=True, gap="small"):
            for panel_key, panel_label, panel_icon in panel_buttons:
                is_active = active_panel == panel_key
                st.button(
                    f"{panel_label} {'접기' if is_active else '보기'}",
                    icon=":material/keyboard_arrow_up:" if is_active else panel_icon,
                    type="primary" if is_active else "secondary",
                    key=f"member_dashboard_{panel_key}",
                    on_click=toggle_member_dashboard_panel,
                    args=(panel_key,),
                )

        if active_panel == "unpaid":
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

        elif active_panel == "removal":
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

        elif active_panel == "management":
            st.markdown("#### 관리대상 인원")
            st.caption(
                "활동 회원 중 가입한 달부터 현재 달까지의 월 평균 참석이 "
                "1회 미만인 회원입니다."
            )
            management_target_members = dashboard["management_target_members"]

            if management_target_members.empty:
                st.success("현재 월 평균 참석이 1회 미만인 활동 회원이 없습니다.")
            else:
                st.dataframe(
                    management_target_members,
                    width="stretch",
                    hide_index=True,
                    column_config={
                        "가입 경과개월": st.column_config.NumberColumn(format="%d개월"),
                        "정기 참석": st.column_config.NumberColumn(format="%d회"),
                        "자유 참석": st.column_config.NumberColumn(format="%d회"),
                        "총 참석": st.column_config.NumberColumn(format="%d회"),
                        "월 평균 참석": st.column_config.NumberColumn(format="%.2f회"),
                    },
                )

    except Exception as e:
        st.error("회원 현황을 불러오는 중 오류가 발생했습니다.")
        st.exception(e)


st.divider()

csv_data = member_management_data["csv"]
member_action = st.session_state.get("member_management_action")
member_section_titles = {
    "add": "회원 추가",
    "import": "회원 일괄 업로드",
    "edit": "회원정보 수정 / 삭제",
}
member_title_col, member_actions_col = st.columns([1, 4], vertical_alignment="center")
with member_title_col:
    st.subheader(member_section_titles.get(member_action, "회원 목록"))
with member_actions_col:
    with st.container(
        horizontal=True,
        horizontal_alignment="right",
        gap="small",
    ):
        for action, label, icon in (
            ("add", "회원 추가", ":material/person_add:"),
            ("import", "일괄 업로드", ":material/upload_file:"),
            ("edit", "회원정보 관리", ":material/manage_accounts:"),
        ):
            is_open = member_action == action
            st.button(
                "닫기" if is_open else label,
                icon=":material/close:" if is_open else icon,
                type="secondary" if is_open else "primary",
                key=f"toggle_member_{action}",
                on_click=toggle_member_management_action,
                args=(action,),
                width="content",
            )
        st.download_button(
            label="CSV 다운로드",
            data=csv_data,
            file_name="onflow_members.csv",
            mime="text/csv",
            icon=":material/download:",
            type="primary",
            width="content",
        )


# =========================================================
# 회원 목록
# =========================================================
if member_action is None:
    try:
        members = member_management_data["members"]

        if members.empty:
            st.info("아직 등록된 회원이 없습니다.")
        else:
            def handle_member_attendance_click() -> None:
                click = st.session_state.get("member_attendance_click") or {}
                row_index = click.get("row")
                if row_index is None or not 0 <= int(row_index) < len(members):
                    return
                st.session_state["member_attendance_history"] = members.iloc[
                    int(row_index)
                ].to_dict()

            st.dataframe(
                members,
                width="stretch",
                hide_index=True,
                column_config={
                    "참석 러닝": st.column_config.ButtonColumn(
                        "참석 러닝",
                        width="small",
                        type="tertiary",
                        alignment="center",
                        on_click=handle_member_attendance_click,
                        key="member_attendance_click",
                    ),
                    "참석 러닝 상세": None,
                },
            )

            if selected_member := st.session_state.get("member_attendance_history"):
                render_member_attendance_history(selected_member)

    except Exception as e:
        st.error("회원 목록을 불러오는 중 오류가 발생했습니다.")
        st.exception(e)


# =========================================================
# 회원 추가
# =========================================================
elif member_action == "add":
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
                load_member_management_data.clear()

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
elif member_action == "import":

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
                load_member_management_data.clear()
                st.success("회원 일괄 업로드가 완료되었습니다.")
                st.dataframe(result, width="stretch", hide_index=True)

            except Exception as e:
                st.error("회원 일괄 업로드 중 오류가 발생했습니다.")
                st.exception(e)


# =========================================================
# 회원정보 수정 / 삭제
# =========================================================
elif member_action == "edit":
    raw_members = member_management_data["raw_members"]

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
                load_member_management_data.clear()

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
                load_member_management_data.clear()
                st.success("회원이 삭제되었습니다.")
                st.rerun()

            except Exception as e:
                st.error("회원 삭제 중 오류가 발생했습니다.")
                st.exception(e)
    else:
        st.info("회원 완전 삭제는 개발자 계정으로 로그인해야 가능합니다.")
