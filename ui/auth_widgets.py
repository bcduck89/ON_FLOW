import streamlit as st

from core.constants import USER_ROLES
from services.auth_service import (
    init_auth_state,
    logout,
    is_logged_in,
    get_user_role,
)


def render_top_auth(current_page: str = "app.py") -> None:
    init_auth_state()

    left, right = st.columns([5, 1.4])

    with right:
        role = get_user_role()
        role_label = USER_ROLES.get(role, role)

        if is_logged_in():
            st.markdown(
                f"""
                <div style='text-align:right; font-size:0.9rem;'>
                    <b>{st.session_state["user_name"]}</b><br>
                    <span style='color:#2563eb;'>권한: {role_label}</span>
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button("로그아웃", width="stretch"):
                logout()
                st.rerun()

        else:
            st.markdown(
                """
                <div style='text-align:right; font-size:0.9rem; color:#777;'>
                    로그아웃 상태
                </div>
                """,
                unsafe_allow_html=True,
            )

            if st.button("로그인", width="stretch"):
                st.session_state["return_to_page"] = current_page
                st.switch_page("pages/00_로그인.py")