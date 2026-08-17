import streamlit as st

from core.constants import USER_ROLES
from services.auth_service import (
    login,
    init_auth_state,
    logout,
    is_logged_in,
    get_user_role,
)


@st.dialog("ON:FLOW 로그인")
def render_login_dialog() -> None:
    st.caption("관리자 또는 개발자 계정으로 로그인해주세요.")
    with st.form("top_login_form"):
        user_id = st.text_input(
            "아이디",
            autocomplete="username",
        )
        password = st.text_input(
            "비밀번호",
            type="password",
            autocomplete="current-password",
        )
        submitted = st.form_submit_button(
            "로그인",
            type="primary",
            icon=":material/login:",
            width="stretch",
        )

    if submitted:
        if login(user_id, password):
            st.session_state["auth_success_message"] = "로그인되었습니다."
            st.rerun()
        else:
            st.error("아이디 또는 비밀번호가 올바르지 않습니다.")


def render_top_auth(current_page: str = "app_pages/home.py") -> None:
    init_auth_state()

    if message := st.session_state.pop("auth_success_message", None):
        st.toast(message, icon=":material/check_circle:")

    with st.container(
        horizontal=True,
        horizontal_alignment="right",
        vertical_alignment="center",
        gap="small",
    ):
        role = get_user_role()
        role_label = USER_ROLES.get(role, role)

        if is_logged_in():
            st.markdown(f"**{st.session_state['user_name']}**")
            st.badge(
                role_label,
                icon=":material/admin_panel_settings:",
                color="blue",
            )

            if st.button(
                "로그아웃",
                icon=":material/logout:",
                key=f"top_logout_{current_page}",
                width="content",
            ):
                logout()
                st.switch_page("app_pages/home.py")

        else:
            if st.button(
                "로그인",
                icon=":material/login:",
                key=f"top_login_{current_page}",
                width="content",
            ):
                render_login_dialog()
