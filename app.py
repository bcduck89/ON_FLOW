from pathlib import Path
import streamlit as st

from services.auth_service import init_auth_state
from ui.auth_widgets import render_top_auth

st.set_page_config(
    page_title="Home | ON_FLOW",
    page_icon="🏃",
    layout="wide",
    initial_sidebar_state="expanded",
)

init_auth_state()
render_top_auth(current_page="app.py")

logo_path = Path("assets/onflow_logo.png")

st.title("Home")

if logo_path.exists():
    st.image(str(logo_path), use_container_width=True)
else:
    st.warning("assets/onflow_logo.png 파일을 찾을 수 없습니다.")

st.markdown("---")

st.markdown(
    """
# ON:FLOW  
### Oncheoncheon Running Crew

온천천을 주 무대로 함께 달리고, 함께 성장합니다.  
각자의 페이스를 존중하며, 함께하는 즐거움을 만들어 갑니다.

📌 나이제한 : 없음  
📌 회비 : 월 2,000원  
📌 분기 납부 : 6,000원 가능  

🌊 Flow Spot  
- 메인코스 : 온천천  
- 서브코스 : 시민공원, 광안리, 해운대, 사직, 부산대 등  

⏰ Flow Time  
- 정규러닝 : 매주 일요일  
- 자유러닝 : 운영진, 회원 자유 개설  

🏃 Flow Activity  
- 마라톤  
- 트래킹  
- 수영  
- 계절별 모임 이벤트
"""
)

st.info("좌측 메뉴에서 원하는 기능을 선택하세요.")