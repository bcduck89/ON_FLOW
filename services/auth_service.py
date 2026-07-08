import streamlit as st


def init_auth_state() -> None:
    if "logged_in" not in st.session_state:
        st.session_state["logged_in"] = False

    if "user_role" not in st.session_state:
        st.session_state["user_role"] = "guest"

    if "user_id" not in st.session_state:
        st.session_state["user_id"] = ""

    if "user_name" not in st.session_state:
        st.session_state["user_name"] = "Guest"


def login(user_id: str, password: str) -> bool:
    init_auth_state()

    admin_id = st.secrets.get("ADMIN_ID", "admin")
    admin_password = st.secrets.get("ADMIN_PASSWORD", "")

    dev_id = st.secrets.get("DEV_ID", "developer")
    dev_password = st.secrets.get("DEV_PASSWORD", "")

    user_id = user_id.strip()

    if user_id == dev_id and password == dev_password:
        st.session_state["logged_in"] = True
        st.session_state["user_role"] = "developer"
        st.session_state["user_id"] = user_id
        st.session_state["user_name"] = "Developer"
        return True

    if user_id == admin_id and password == admin_password:
        st.session_state["logged_in"] = True
        st.session_state["user_role"] = "admin"
        st.session_state["user_id"] = user_id
        st.session_state["user_name"] = "Admin"
        return True

    return False


def logout() -> None:
    st.session_state["logged_in"] = False
    st.session_state["user_role"] = "guest"
    st.session_state["user_id"] = ""
    st.session_state["user_name"] = "Guest"


def is_logged_in() -> bool:
    init_auth_state()
    return st.session_state.get("logged_in", False)


def get_user_role() -> str:
    init_auth_state()
    return st.session_state.get("user_role", "guest")


def is_admin() -> bool:
    return get_user_role() in ["admin", "developer"]


def is_developer() -> bool:
    return get_user_role() == "developer"