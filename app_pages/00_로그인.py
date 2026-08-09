import streamlit as st

from core.constants import USER_ROLES
from services.auth_service import (
    init_auth_state,
    login,
    logout,
    is_logged_in,
    get_user_role,
)


st.set_page_config(
    page_title="로그인 | ON_FLOW",
    page_icon="🔐",
    layout="centered",
)

init_auth_state()

st.title("🔐 로그인")
st.caption("ON_FLOW Operator Login")

st.divider()

if is_logged_in():
    role = get_user_role()

    st.success(f"{st.session_state['user_name']} 계정으로 로그인되어 있습니다.")
    st.info(f"권한: {USER_ROLES.get(role, role)}")

    if st.button("홈으로 이동", width="stretch"):
        st.switch_page("app_pages/home.py")

    if st.button("로그아웃", width="stretch"):
        logout()
        st.rerun()

else:
    with st.form("login_form"):
        user_id = st.text_input("아이디")
        password = st.text_input("비밀번호", type="password")

        submitted = st.form_submit_button("로그인", width="stretch")

        if submitted:
            if login(user_id, password):
                return_to = st.session_state.get(
                    "return_to_page", "app_pages/home.py"
                )

                if return_to == "app_pages/00_로그인.py":
                    return_to = "app_pages/home.py"

                st.session_state["return_to_page"] = "app_pages/home.py"
                st.switch_page(return_to)

            else:
                st.error("아이디 또는 비밀번호가 올바르지 않습니다.")
