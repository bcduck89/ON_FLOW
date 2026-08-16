import hashlib
from datetime import date, time

import streamlit as st

from services.auth_service import init_auth_state, is_admin
from services.regular_run_service import (
    OCRUnavailableError,
    RegularRunImageError,
    create_regular_run,
    extract_regular_run_from_image,
    get_regular_run_list,
)
from ui.auth_widgets import render_top_auth


st.set_page_config(
    page_title="정기 러닝 | ON_FLOW",
    page_icon="🏃",
    layout="wide",
)

init_auth_state()
render_top_auth(current_page="app_pages/04_정기러닝.py")

st.title("정기 러닝")
st.caption("ON:FLOW 정기 러닝 일정을 한눈에 확인합니다.")

st.subheader("정기 러닝 목록")

try:
    regular_runs = get_regular_run_list()
    if regular_runs.empty:
        st.info("아직 등록된 정기 러닝이 없습니다.")
    else:
        st.dataframe(
            regular_runs,
            width="stretch",
            hide_index=True,
            column_config={
                "거리 (km)": st.column_config.NumberColumn(format="%.2f km"),
                "참여인원": st.column_config.NumberColumn(format="%d명"),
            },
        )
except Exception:
    st.warning(
        "정기 러닝 테이블을 불러오지 못했습니다. 관리자라면 Supabase에서 "
        "005_create_regular_runs.sql을 먼저 실행해주세요."
    )

if not is_admin():
    st.stop()

st.subheader("캡처 이미지로 등록")
st.caption(
    "캡처 이미지를 분석한 뒤 추출된 내용을 직접 확인·수정하고 등록할 수 있습니다."
)

uploader_version = st.session_state.setdefault("regular_run_uploader_version", 0)
uploaded_file = st.file_uploader(
    "정기 러닝 캡처 이미지",
    type=["png", "jpg", "jpeg", "webp"],
    key=f"regular_run_capture_{uploader_version}",
)

if uploaded_file is not None:
    image_data = uploaded_file.getvalue()
    image_hash = hashlib.sha256(image_data).hexdigest()

    if st.session_state.get("regular_run_source_hash") != image_hash:
        st.session_state["regular_run_source_hash"] = image_hash
        st.session_state.pop("regular_run_extracted", None)

    st.image(image_data, caption=uploaded_file.name, width=420)

    if st.button(
        "사진 정보 읽기",
        type="primary",
        icon=":material/document_scanner:",
    ):
        try:
            with st.spinner("캡처 이미지에서 정기 러닝 정보를 읽고 있습니다..."):
                st.session_state["regular_run_extracted"] = (
                    extract_regular_run_from_image(image_data, uploaded_file.name)
                )
            st.success("정보를 읽었습니다. 아래 내용을 확인한 뒤 등록해주세요.")
        except (RegularRunImageError, OCRUnavailableError) as exc:
            st.error(str(exc))
        except Exception:
            st.error("이미지 분석 중 오류가 발생했습니다. 다른 캡처로 다시 시도해주세요.")

    extracted = st.session_state.get("regular_run_extracted")
    if extracted:
        with st.expander("OCR로 읽은 원문 확인"):
            st.text(extracted["raw_ocr_text"])

        with st.form("regular_run_review_form"):
            st.markdown("#### 추출 정보 확인")
            first_row = st.container(horizontal=True)
            with first_row:
                title = st.text_input("정기러닝명", value=extracted["title"])
                run_date = st.date_input(
                    "날짜",
                    value=extracted["run_date"] or date.today(),
                    format="YYYY-MM-DD",
                )
                start_time = st.time_input(
                    "시간",
                    value=extracted["start_time"] or time(19, 30),
                )

            second_row = st.container(horizontal=True)
            with second_row:
                location = st.text_input("장소", value=extracted["location"])
                course_name = st.text_input("코스", value=extracted["course_name"])
                distance_km = st.number_input(
                    "거리 (km)",
                    min_value=0.0,
                    step=0.1,
                    value=float(extracted["distance_km"]),
                )

            third_row = st.container(horizontal=True)
            with third_row:
                target_pace = st.text_input(
                    "목표 페이스",
                    value=extracted["target_pace"],
                    placeholder="예: 6:00/km",
                )
                participant_count = st.number_input(
                    "참여인원",
                    min_value=0,
                    step=1,
                    value=int(extracted["participant_count"]),
                )

            memo = st.text_area("비고", value=extracted["memo"])
            submitted = st.form_submit_button(
                "정기 러닝 등록",
                type="primary",
                icon=":material/save:",
                width="stretch",
            )

            if submitted:
                try:
                    create_regular_run(
                        title=title,
                        run_date=run_date,
                        start_time=start_time,
                        location=location,
                        course_name=course_name,
                        distance_km=distance_km,
                        target_pace=target_pace,
                        participant_count=participant_count,
                        memo=memo,
                        source_image_name=uploaded_file.name,
                        source_image_data=image_data,
                        raw_ocr_text=extracted["raw_ocr_text"],
                        created_by=st.session_state.get("user_id", "admin"),
                    )
                    st.session_state.pop("regular_run_extracted", None)
                    st.session_state.pop("regular_run_source_hash", None)
                    st.session_state["regular_run_uploader_version"] += 1
                    st.success("정기 러닝이 등록되었습니다.")
                    st.rerun()
                except Exception as exc:
                    if "duplicate" in str(exc).lower() or "23505" in str(exc):
                        st.warning("이미 등록한 캡처 이미지입니다.")
                    else:
                        st.error("정기 러닝을 등록하지 못했습니다. 입력값과 DB 설정을 확인해주세요.")
