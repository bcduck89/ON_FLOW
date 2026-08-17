import streamlit as st

from services.auth_service import init_auth_state, is_admin, is_logged_in


init_auth_state()

pages = [
    st.Page(
        "app_pages/home.py",
        title="홈",
        icon=":material/home:",
        default=True,
    ),
    st.Page(
        "app_pages/03_러닝코스.py",
        title="러닝 코스",
        icon=":material/route:",
    ),
]

if is_logged_in():
    pages.insert(
        2,
        st.Page(
            "app_pages/04_정기러닝.py",
            title="정기/자유러닝",
            icon=":material/calendar_month:",
        ),
    )

if is_admin():
    pages.extend(
        [
            st.Page(
                "app_pages/01_회원관리.py",
                title="회원관리",
                icon=":material/group:",
            ),
            st.Page(
                "app_pages/02_회비관리.py",
                title="회비관리",
                icon=":material/payments:",
            ),
        ]
    )

navigation = st.navigation(pages, position="sidebar")
navigation.run()
