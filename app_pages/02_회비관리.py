import streamlit as st

from database.client import check_supabase_connection
from services.auth_service import init_auth_state, is_admin
from services.transaction_engine import import_kakaobank_excel
from services.transaction_service import get_transaction_list
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

menu = st.radio(
    "회비관리 메뉴",
    ["거래내역 업로드", "거래내역 조회"],
    horizontal=True,
)

if menu == "거래내역 업로드":
    st.subheader("카카오뱅크 거래내역 업로드")

    st.info(
        "카카오뱅크에서 다운로드한 Excel(.xlsx) 거래내역을 업로드하세요. "
        "이미 등록된 거래는 transaction_hash 기준으로 자동 제외됩니다."
    )

    uploaded_file = st.file_uploader(
        "카카오뱅크 Excel 파일 업로드",
        type=["xlsx"],
    )

    if uploaded_file is not None:
        if st.button("거래내역 업로드 및 회비 자동 반영", type="primary", width="stretch"):
            try:
                result = import_kakaobank_excel(uploaded_file)

                st.success("거래내역 처리가 완료되었습니다.")
                st.dataframe(result, width="stretch", hide_index=True)

            except Exception as e:
                st.error("거래내역 처리 중 오류가 발생했습니다.")
                st.exception(e)

elif menu == "거래내역 조회":
    st.subheader("거래내역 조회")

    transactions = get_transaction_list()

    if transactions.empty:
        st.info("등록된 거래내역이 없습니다.")
    else:
        st.dataframe(
            transactions,
            width="stretch",
            hide_index=True,
        )
