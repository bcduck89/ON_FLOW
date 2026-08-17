from datetime import date, time

import streamlit as st

from database.client import check_supabase_connection
from repositories.fee_repository import FeePaymentSchemaError
from services.auth_service import init_auth_state, is_admin
from services.transaction_engine import create_manual_transaction, import_kakaobank_excel
from services.transaction_service import get_fee_transaction_lists
from ui.auth_widgets import render_top_auth


st.set_page_config(
    page_title="회비관리 | ON_FLOW",
    page_icon="💳",
    layout="wide",
)

init_auth_state()
render_top_auth(current_page="app_pages/02_회비관리.py")

st.title("💳 회비관리")
st.caption("ON_FLOW Membership Fee Management")

if not is_admin():
    st.warning("회비관리는 관리자 권한으로 로그인해야 사용할 수 있습니다.")
    st.stop()

ok, msg = check_supabase_connection()

if not ok:
    st.error("Supabase 연결 실패")
    st.caption(msg)
    st.stop()

st.divider()

manual_form_is_open = st.session_state.get("show_manual_transaction_form", False)
uploader_is_open = st.session_state.get("show_transaction_uploader", False)

transaction_title_col, transaction_actions_col = st.columns(
    [3, 2],
    vertical_alignment="center",
)
with transaction_title_col:
    st.subheader("거래내역 조회")
with transaction_actions_col:
    with st.container(
        horizontal=True,
        horizontal_alignment="right",
        gap="small",
    ):
        if st.button(
            "닫기" if manual_form_is_open else "수동 입력",
            icon=":material/close:" if manual_form_is_open else ":material/edit_note:",
            type="secondary" if manual_form_is_open else "primary",
            key="toggle_manual_transaction_form",
            width="content",
        ):
            st.session_state["show_manual_transaction_form"] = not manual_form_is_open
            st.session_state["show_transaction_uploader"] = False
            st.rerun()
        if st.button(
            "닫기" if uploader_is_open else "거래내역 업로드",
            icon=":material/close:" if uploader_is_open else ":material/upload_file:",
            type="secondary" if uploader_is_open else "primary",
            key="toggle_transaction_uploader",
            width="content",
        ):
            st.session_state["show_transaction_uploader"] = not uploader_is_open
            st.session_state["show_manual_transaction_form"] = False
            st.rerun()

if manual_form_is_open:
    st.markdown("#### 거래내역 수동 입력")
    st.caption("입금은 기존 회비 자동 반영 절차로 처리되고, 출금은 회비 사용 내역으로 저장됩니다.")
    with st.form("manual_transaction_form", clear_on_submit=True):
        direction = st.segmented_control(
            "입출금 구분",
            ["입금", "출금"],
            default="입금",
            selection_mode="single",
        )
        with st.container(horizontal=True):
            transaction_date = st.date_input(
                "거래일",
                value=date.today(),
                max_value=date.today(),
                format="YYYY-MM-DD",
            )
            transaction_time = st.time_input("거래시간", value=time(12, 0))
            amount = st.number_input(
                "금액",
                min_value=1,
                step=1000,
                value=2000,
            )
            balance = st.number_input(
                "거래 후 잔액",
                min_value=0,
                step=1000,
                value=0,
                help="알 수 없다면 0원으로 두어도 됩니다.",
            )
        description = st.text_input(
            "입금자명 또는 사용 내용",
            placeholder="예: 김주희 / 8월 소모임 구독료",
        )
        memo = st.text_input("메모", placeholder="선택 입력")
        bank_name = st.text_input("은행", value="카카오뱅크")
        with st.container(horizontal=True, horizontal_alignment="right"):
            cancelled = st.form_submit_button("취소")
            submitted = st.form_submit_button(
                "거래 저장",
                type="primary",
                icon=":material/save:",
            )

    if cancelled:
        st.session_state["show_manual_transaction_form"] = False
        st.rerun()

    if submitted:
        try:
            result = create_manual_transaction(
                transaction_date=transaction_date,
                transaction_time=transaction_time,
                direction=direction,
                amount=amount,
                balance=balance,
                description=description,
                memo=memo,
                bank_name=bank_name,
            )
        except FeePaymentSchemaError as error:
            st.error("수동 거래 처리 중 오류가 발생했습니다.")
            st.warning(str(error))
        except (ValueError, RuntimeError) as error:
            st.error(str(error))
        except Exception:
            st.error("수동 거래를 처리하지 못했습니다. 잠시 후 다시 시도해 주세요.")
        else:
            st.session_state["show_manual_transaction_form"] = False
            st.session_state["transaction_process_result"] = result
            st.rerun()

elif uploader_is_open:
    st.markdown("#### 카카오뱅크 거래내역 업로드")
    st.caption(
        "카카오뱅크에서 다운로드한 Excel(.xlsx)을 업로드하면 중복 거래를 제외하고 "
        "회비를 자동 반영합니다."
    )
    uploader_version = st.session_state.setdefault("transaction_uploader_version", 0)
    uploaded_file = st.file_uploader(
        "카카오뱅크 Excel 파일",
        type=["xlsx"],
        key=f"kakaobank_transactions_{uploader_version}",
    )
    if uploaded_file is not None and st.button(
        "거래내역 업로드 및 회비 자동 반영",
        type="primary",
        icon=":material/upload:",
        width="stretch",
    ):
        try:
            result = import_kakaobank_excel(uploaded_file)
        except FeePaymentSchemaError as error:
            st.error("거래내역 처리 중 오류가 발생했습니다.")
            st.warning(str(error))
        except Exception:
            st.error("거래내역 처리 중 오류가 발생했습니다. 잠시 후 다시 시도해 주세요.")
        else:
            st.session_state["show_transaction_uploader"] = False
            st.session_state["transaction_uploader_version"] += 1
            st.session_state["transaction_process_result"] = result
            st.rerun()

process_result = st.session_state.pop("transaction_process_result", None)
if process_result is not None:
    st.success("거래내역 처리가 완료되었습니다.")
    st.dataframe(process_result, width="stretch", hide_index=True)

deposits, expenses = get_fee_transaction_lists()

if deposits.empty and expenses.empty:
    st.info("등록된 거래내역이 없습니다.")
else:
    deposit_tab, expense_tab = st.tabs(
        [
            f"회비 입금 내역 · {len(deposits)}건",
            f"회비 사용 내역 · {len(expenses)}건",
        ]
    )

    with deposit_tab:
        st.caption("회원의 회비 입금과 자동 반영 상태를 확인합니다.")
        if deposits.empty:
            st.info("등록된 회비 입금 내역이 없습니다.")
        else:
            st.dataframe(
                deposits,
                width="stretch",
                hide_index=True,
                column_config={
                    "금액": st.column_config.NumberColumn(format="%,d원"),
                },
            )

    with expense_tab:
        st.caption("회비가 사용된 출금 거래만 모아 보여줍니다.")
        if expenses.empty:
            st.info("등록된 회비 사용 내역이 없습니다.")
        else:
            st.dataframe(
                expenses,
                width="stretch",
                hide_index=True,
                column_config={
                    "사용금액": st.column_config.NumberColumn(format="%,d원"),
                    "잔액": st.column_config.NumberColumn(format="%,d원"),
                },
            )
