import hashlib
from datetime import date, time

import streamlit as st

from services.auth_service import init_auth_state, is_admin
from services.regular_run_service import (
    OCRUnavailableError,
    RegularRunImageError,
    create_regular_run,
    default_run_type_for_date,
    extract_regular_run_from_image,
    get_regular_run_list,
    get_regular_run_records,
    has_paddle_ocr_runtime,
    match_attendee_names_to_members,
    update_regular_run,
)
from ui.auth_widgets import render_top_auth
from utils.weekday_utils import get_korean_weekday


st.set_page_config(
    page_title="정기/자유러닝 | ON_FLOW",
    page_icon="🏃",
    layout="wide",
)

init_auth_state()
render_top_auth(current_page="app_pages/04_정기러닝.py")

OCR_PARSER_VERSION = 4

st.title("정기/자유러닝")
st.caption("ON:FLOW의 정기 러닝과 자유 러닝 참석 현황을 한눈에 확인합니다.")

st.subheader("정기/자유러닝 목록")

try:
    regular_runs = get_regular_run_list()
    if regular_runs.empty:
        st.info("아직 등록된 러닝이 없습니다.")
    else:
        st.dataframe(
            regular_runs,
            width="stretch",
            hide_index=True,
            column_config={
                "거리 (km)": st.column_config.NumberColumn(format="%.1f km"),
                "총 참석인원": st.column_config.NumberColumn(format="%d명"),
                "참석자 명단": st.column_config.TextColumn(width="large"),
            },
        )
except Exception:
    st.warning(
        "정기/자유러닝 테이블을 불러오지 못했습니다. 관리자라면 Supabase SQL Editor에서 "
        "007_create_or_upgrade_regular_runs.sql을 먼저 실행해주세요."
    )

if not is_admin():
    st.stop()

if edit_success_message := st.session_state.pop("regular_run_edit_success", None):
    st.success(edit_success_message)

if "show_regular_run_editor" not in st.session_state:
    st.session_state["show_regular_run_editor"] = False

if not st.session_state["show_regular_run_editor"]:
    if st.button("러닝 기록 수정", icon=":material/edit:"):
        st.session_state["show_regular_run_editor"] = True
        st.rerun()

if st.session_state["show_regular_run_editor"]:
    st.markdown("#### 러닝 기록 수정")
    try:
        run_records = get_regular_run_records()
        if not run_records:
            st.info("수정할 러닝 기록이 없습니다.")
        else:
            record_by_label = {
                (
                    f"{record.get('run_date', '')} | {record.get('run_type', '')} | "
                    f"{record.get('participant_count', 0)}명 | "
                    f"{record.get('distance_km', 0)}km | #{record.get('regular_run_id')}"
                ): record
                for record in run_records
            }
            selected_label = st.selectbox(
                "수정할 러닝 선택",
                options=list(record_by_label),
                key="regular_run_edit_selection",
            )
            selected_record = record_by_label[selected_label]
            selected_id = int(selected_record["regular_run_id"])
            selected_date = date.fromisoformat(str(selected_record["run_date"])[:10])
            selected_time_value = selected_record.get("start_time")
            selected_time = (
                time.fromisoformat(str(selected_time_value))
                if selected_time_value
                else time(20, 0)
            )
            selected_attendees = selected_record.get("attendee_names") or []

            with st.form(f"edit_regular_run_{selected_id}"):
                edit_run_type = st.segmented_control(
                    "러닝 구분",
                    options=["정기", "자유"],
                    default=str(selected_record.get("run_type") or "자유"),
                    selection_mode="single",
                )
                with st.container(horizontal=True):
                    edit_run_date = st.date_input(
                        "날짜",
                        value=selected_date,
                        format="YYYY-MM-DD",
                    )
                    edit_start_time = st.time_input("시간", value=selected_time)
                    edit_distance_km = st.number_input(
                        "거리 (km)",
                        min_value=0.0,
                        step=0.5,
                        value=float(selected_record.get("distance_km") or 5.0),
                    )
                    edit_participant_count = st.number_input(
                        "총 참석인원",
                        min_value=0,
                        step=1,
                        value=int(selected_record.get("participant_count") or 0),
                    )
                edit_attendee_text = st.text_area(
                    "참석자 명단",
                    value="\n".join(str(name) for name in selected_attendees),
                    height=180,
                )
                submitted_edit = st.form_submit_button(
                    "수정 내용 저장",
                    type="primary",
                    icon=":material/save:",
                    width="stretch",
                )

            if submitted_edit:
                edit_attendee_names = [
                    name.strip()
                    for name in edit_attendee_text.splitlines()
                    if name.strip()
                ]
                update_regular_run(
                    regular_run_id=selected_id,
                    run_type=edit_run_type,
                    run_date=edit_run_date,
                    start_time=edit_start_time,
                    distance_km=edit_distance_km,
                    participant_count=edit_participant_count,
                    attendee_names=edit_attendee_names,
                )
                st.session_state["show_regular_run_editor"] = False
                st.session_state["regular_run_edit_success"] = "러닝 기록을 수정했습니다."
                st.rerun()
    except (ValueError, RuntimeError) as exc:
        st.error(str(exc))
    except Exception:
        st.error("러닝 기록을 수정하지 못했습니다. 잠시 후 다시 시도해주세요.")

st.subheader("캡처 이미지로 등록")
st.caption(
    "소모임 참석자 화면을 업로드하면 날짜·시간·요일·참석인원·참석자 명단을 읽습니다. "
    "OCR 결과는 반드시 확인한 뒤 등록해주세요."
)
if has_paddle_ocr_runtime():
    st.info(
        "PaddleOCR 한국어 모델을 서버에서 직접 실행합니다. 업로드한 사진은 외부 AI API로 "
        "전송되지 않으며 별도 API 사용료가 없습니다. 첫 실행은 모델 준비로 시간이 걸릴 수 있습니다."
    )
else:
    st.warning(
        "현재 실행 환경에서는 PaddleOCR을 사용할 수 없어 Tesseract OCR로 동작합니다. "
        "Streamlit Cloud 배포 Python을 3.13으로 선택한 뒤 다시 배포해주세요."
    )

uploader_version = st.session_state.setdefault("regular_run_uploader_version", 0)
uploaded_file = st.file_uploader(
    "러닝 참석자 캡처 이미지",
    type=["png", "jpg", "jpeg", "webp"],
    key=f"regular_run_capture_{uploader_version}",
)

if uploaded_file is not None:
    image_data = uploaded_file.getvalue()
    image_hash = hashlib.sha256(image_data).hexdigest()
    extraction_key = f"{OCR_PARSER_VERSION}:{image_hash}"

    if st.session_state.get("regular_run_source_hash") != extraction_key:
        st.session_state["regular_run_source_hash"] = extraction_key
        st.session_state.pop("regular_run_extracted", None)

    st.image(image_data, caption=uploaded_file.name, width=420)

    if st.button(
        "사진 정보 읽기",
        type="primary",
        icon=":material/document_scanner:",
    ):
        try:
            with st.spinner("캡처 이미지에서 러닝 정보를 읽고 있습니다..."):
                extracted_result = extract_regular_run_from_image(
                    image_data,
                    uploaded_file.name,
                )
                original_names = extracted_result["attendee_names"]
                matched_names = match_attendee_names_to_members(original_names)
                extracted_result["attendee_names"] = matched_names
                extracted_result["matched_member_count"] = sum(
                    original != matched
                    for original, matched in zip(original_names, matched_names)
                )
                st.session_state["regular_run_extracted"] = extracted_result
            st.success("정보를 읽었습니다. 아래 내용을 확인한 뒤 등록해주세요.")
        except (RegularRunImageError, OCRUnavailableError) as exc:
            st.error(str(exc))
        except Exception:
            st.error("이미지 분석 중 오류가 발생했습니다. 다른 캡처로 다시 시도해주세요.")

    extracted = st.session_state.get("regular_run_extracted")
    if extracted:
        if warning := extracted.get("recognition_warning"):
            st.warning(warning)
        st.caption(f"인식 방식: {extracted.get('recognition_method', 'OCR')}")
        if matched_count := extracted.get("matched_member_count", 0):
            st.success(f"닉네임 {matched_count}명을 회원목록의 실제 이름으로 변환했습니다.")
        with st.expander("OCR로 읽은 원문 확인"):
            st.text(extracted["raw_ocr_text"])

        st.markdown("#### 추출 정보 확인")
        first_row = st.container(horizontal=True)
        with first_row:
            run_date = st.date_input(
                "날짜",
                value=extracted["run_date"] or date.today(),
                format="YYYY-MM-DD",
                key=f"regular_run_date_{image_hash}",
            )
            start_time = st.time_input(
                "시간",
                value=extracted["start_time"] or time(20, 0),
                key=f"regular_run_time_{image_hash}",
            )
            st.text_input(
                "요일",
                value=get_korean_weekday(run_date),
                disabled=True,
            )

        run_type = st.segmented_control(
            "러닝 구분",
            options=["정기", "자유"],
            default=default_run_type_for_date(run_date),
            selection_mode="single",
            key=f"regular_run_type_{image_hash}_{run_date.isoformat()}",
        )
        st.caption("일요일은 정기, 그 외 요일은 자유로 자동 설정됩니다. 필요하면 변경할 수 있습니다.")

        distance_km = st.number_input(
            "거리 (km)",
            min_value=0.0,
            step=0.5,
            value=float(extracted.get("distance_km") or 5.0),
            key=f"regular_run_distance_{image_hash}",
        )

        participant_count = st.number_input(
            "총 참석인원",
            min_value=0,
            step=1,
            value=int(extracted["participant_count"]),
            key=f"regular_run_count_{image_hash}",
        )
        attendee_text = st.text_area(
            "참석자 명단",
            value="\n".join(extracted["attendee_names"]),
            placeholder="참석자 이름을 한 줄에 한 명씩 입력해주세요.",
            height=180,
            key=f"regular_run_attendees_{image_hash}",
        )
        attendee_names = [name.strip() for name in attendee_text.splitlines() if name.strip()]

        if participant_count != len(attendee_names):
            st.warning(
                f"총 참석인원은 {participant_count}명이지만 명단에는 "
                f"{len(attendee_names)}명이 있습니다. 등록 전에 맞춰주세요."
            )
        else:
            st.caption(f"참석자 {len(attendee_names)}명의 명단이 확인되었습니다.")

        if st.button(
            "러닝 데이터 등록",
            type="primary",
            icon=":material/save:",
            width="stretch",
            disabled=participant_count != len(attendee_names) or participant_count == 0,
        ):
            try:
                create_regular_run(
                    run_type=run_type,
                    title=f"{run_date:%Y-%m-%d} {run_type} 러닝",
                    run_date=run_date,
                    start_time=start_time,
                    location="",
                    course_name="",
                    distance_km=distance_km,
                    target_pace="",
                    participant_count=participant_count,
                    attendee_names=attendee_names,
                    memo="",
                    source_image_name=uploaded_file.name,
                    source_image_data=image_data,
                    raw_ocr_text=extracted["raw_ocr_text"],
                    created_by=st.session_state.get("user_id", "admin"),
                )
                st.session_state.pop("regular_run_extracted", None)
                st.session_state.pop("regular_run_source_hash", None)
                st.session_state["regular_run_uploader_version"] += 1
                st.success(f"{run_type} 러닝이 등록되었습니다.")
                st.rerun()
            except ValueError as exc:
                if "이미 등록한" in str(exc):
                    st.warning(str(exc))
                else:
                    st.error(str(exc))
            except RuntimeError as exc:
                st.error(str(exc))
            except Exception:
                st.error("러닝 데이터를 등록하지 못했습니다. 잠시 후 다시 시도해주세요.")
