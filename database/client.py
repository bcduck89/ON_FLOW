import streamlit as st
from supabase import create_client, Client


@st.cache_resource
def get_supabase_client() -> Client:
    return create_client(
        st.secrets["SUPABASE_URL"],
        st.secrets["SUPABASE_KEY"],
    )


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

