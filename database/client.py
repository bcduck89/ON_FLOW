import os

import streamlit as st
from supabase import create_client, Client


def _secret_value(*names: str) -> str | None:
    for name in names:
        value = st.secrets.get(name)
        if value:
            return str(value).strip()

    sections = [
        st.secrets.get("supabase"),
        st.secrets.get("SUPABASE"),
    ]
    connections = st.secrets.get("connections")
    if connections:
        sections.extend(
            [connections.get("supabase"), connections.get("SUPABASE")]
        )

    for section in sections:
        if not section:
            continue
        for name in names:
            nested_names = (
                name,
                name.lower(),
                name.removeprefix("SUPABASE_").lower(),
            )
            for nested_name in nested_names:
                value = section.get(nested_name)
                if value:
                    return str(value).strip()

    for name in names:
        value = os.getenv(name)
        if value:
            return value.strip()
    return None


def has_supabase_admin_credentials() -> bool:
    return bool(
        _secret_value("SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY")
    )


@st.cache_resource
def get_supabase_client() -> Client:
    supabase_url = _secret_value("SUPABASE_URL")
    supabase_key = _secret_value("SUPABASE_KEY", "SUPABASE_ANON_KEY")
    if not supabase_url or not supabase_key:
        raise RuntimeError("Supabase URL 또는 공개 키가 설정되지 않았습니다.")
    return create_client(
        supabase_url,
        supabase_key,
    )


@st.cache_resource
def get_supabase_admin_client() -> Client:
    supabase_url = _secret_value("SUPABASE_URL")
    service_role_key = _secret_value(
        "SUPABASE_SERVICE_ROLE_KEY", "SUPABASE_SERVICE_KEY"
    )
    if not service_role_key:
        raise RuntimeError(
            "Supabase Service Role 키가 설정되지 않았습니다. "
            "Streamlit secrets에 SUPABASE_SERVICE_ROLE_KEY를 추가해 주세요."
        )

    if not supabase_url:
        raise RuntimeError("Supabase URL이 설정되지 않았습니다.")

    return create_client(supabase_url, service_role_key)


def check_supabase_connection() -> tuple[bool, str]:
    """
    Supabase 연결 상태를 확인한다.
    members 테이블에 아주 가벼운 select 요청을 보낸다.
    """
    try:
        sb = get_supabase_client()
        sb.table("members").select("member_id").limit(1).execute()
        return True, "Supabase 연결 정상"
    except Exception as e:
        return False, str(e)

