import hashlib
from datetime import date, time

import streamlit as st

from services.auth_service import init_auth_state, is_admin, is_logged_in
from services.regular_run_service import (
    OCRUnavailableError,
    RegularRunImageError,
    create_manual_regular_run,
    create_regular_run,
    delete_regular_run,
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
if not is_logged_in():
    st.switch_page("app_pages/00_로그인.py")
render_top_auth(current_page="app_pages/04_정기러닝.py")
admin_user = is_admin()

OCR_PARSER_VERSION = 5
RUN_TYPE_LABELS = {"정기": "🔵 정기", "자유": "🟠 자유"}
RUN_TYPE_VALUES = {label: value for value, label in RUN_TYPE_LABELS.items()}
AFTER_PARTY_LABELS = {
    "카페": "☕️ 카페",
    "식사": "🍽️ 식사",
    "없음": "➖ 없음",
}
AFTER_PARTY_VALUES = {
    label: value for value, label in AFTER_PARTY_LABELS.items()
}

st.title("정기/자유러닝")
st.caption("ON:FLOW의 정기 러닝과 자유 러닝 참석 현황을 한눈에 확인합니다.")

def render_regular_run_editor(record: dict) -> None:
    selected_id = int(record["regular_run_id"])
    selected_run_type = str(record.get("run_type") or "자유")
    if selected_run_type not in {"정기", "자유"}:
        selected_run_type = "자유"
    selected_date = date.fromisoformat(str(record["run_date"])[:10])
    selected_time_value = record.get("start_time")
    selected_time = (
        time.fromisoformat(str(selected_time_value)[:8])
        if selected_time_value
        else time(20, 0)
    )
    selected_attendees = record.get("attendee_names") or []

    with st.container(border=True):
        st.markdown("#### 러닝 기록 수정")
        st.caption("날짜 입력창을 누르면 달력에서 날짜를 선택할 수 있습니다.")
        with st.form(f"edit_regular_run_{selected_id}"):
            edit_run_type_label = st.segmented_control(
                "러닝 구분",
                options=list(RUN_TYPE_VALUES),
                default=RUN_TYPE_LABELS[selected_run_type],
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
                    value=float(record.get("distance_km") or 5.0),
                )
                edit_participant_count = st.number_input(
                    "총 참석인원",
                    min_value=0,
                    step=1,
                    value=int(record.get("participant_count") or 0),
                )
            edit_course_name = st.text_input(
                "코스 이름",
                value=str(record.get("course_name") or ""),
                placeholder="예: 온천천 왕복 코스",
            )
            selected_after_party = str(record.get("after_party") or "없음")
            if selected_after_party not in AFTER_PARTY_LABELS:
                selected_after_party = "없음"
            edit_after_party_label = st.segmented_control(
                "뒷풀이",
                options=list(AFTER_PARTY_VALUES),
                default=AFTER_PARTY_LABELS[selected_after_party],
                selection_mode="single",
            )
            edit_attendee_text = st.text_area(
                "참석자 명단",
                value="\n".join(str(name) for name in selected_attendees),
                height=180,
                help="한 줄에 한 명씩 입력해주세요.",
            )
            with st.container(horizontal=True, horizontal_alignment="right"):
                cancel_edit = st.form_submit_button("취소")
                submitted_edit = st.form_submit_button(
                    "수정 내용 저장",
                    type="primary",
                    icon=":material/save:",
                )

    if cancel_edit:
        st.session_state.pop("regular_run_pending_edit", None)
        st.rerun()

    if submitted_edit:
        edit_attendee_names = [
            name.strip()
            for name in edit_attendee_text.splitlines()
            if name.strip()
        ]
        try:
            update_regular_run(
                regular_run_id=selected_id,
                run_type=RUN_TYPE_VALUES.get(edit_run_type_label, "자유"),
                run_date=edit_run_date,
                start_time=edit_start_time,
                course_name=edit_course_name,
                distance_km=edit_distance_km,
                after_party=AFTER_PARTY_VALUES.get(
                    edit_after_party_label,
                    "없음",
                ),
                participant_count=edit_participant_count,
                attendee_names=edit_attendee_names,
            )
        except (ValueError, RuntimeError) as exc:
            st.error(str(exc))
        except Exception:
            st.error("러닝 기록을 수정하지 못했습니다. 잠시 후 다시 시도해주세요.")
        else:
            st.session_state.pop("regular_run_pending_edit", None)
            st.session_state["regular_run_edit_success"] = "러닝 기록을 수정했습니다."
            st.rerun()


def render_manual_regular_run_form() -> None:
    st.subheader("러닝 기록 수동 등록")
    st.caption("캡처 이미지 없이 러닝 정보와 참석자 명단을 직접 등록합니다.")

    with st.form("manual_regular_run_form", clear_on_submit=True):
        run_type_label = st.segmented_control(
            "러닝 구분",
            options=list(RUN_TYPE_VALUES),
            default=RUN_TYPE_LABELS[default_run_type_for_date(date.today())],
            selection_mode="single",
        )
        with st.container(horizontal=True):
            run_date = st.date_input(
                "날짜",
                value=date.today(),
                format="YYYY-MM-DD",
            )
            start_time = st.time_input("시간", value=time(20, 0))
            distance_km = st.number_input(
                "거리 (km)",
                min_value=0.0,
                step=0.5,
                value=5.0,
            )
        course_name = st.text_input(
            "코스 이름",
            placeholder="예: 온천천 왕복 코스",
        )
        after_party_label = st.segmented_control(
            "뒷풀이",
            options=list(AFTER_PARTY_VALUES),
            default=AFTER_PARTY_LABELS["없음"],
            selection_mode="single",
        )
        attendee_text = st.text_area(
            "참석자 명단",
            placeholder="한 줄에 한 명씩 입력해주세요.",
            height=180,
        )
        st.caption("총 참석인원은 입력한 참석자 명단을 기준으로 자동 계산됩니다.")
        with st.container(horizontal=True, horizontal_alignment="right"):
            cancelled = st.form_submit_button("취소")
            submitted = st.form_submit_button(
                "수동 등록",
                type="primary",
                icon=":material/save:",
            )

    if cancelled:
        st.session_state["show_manual_run_form"] = False
        st.rerun()

    if submitted:
        attendee_names = [
            name.strip() for name in attendee_text.splitlines() if name.strip()
        ]
        attendee_names = match_attendee_names_to_members(attendee_names)
        try:
            create_manual_regular_run(
                run_type=RUN_TYPE_VALUES.get(run_type_label, "자유"),
                run_date=run_date,
                start_time=start_time,
                course_name=course_name,
                distance_km=distance_km,
                after_party=AFTER_PARTY_VALUES.get(after_party_label, "없음"),
                attendee_names=attendee_names,
                created_by=st.session_state.get("user_id", "admin"),
            )
        except (ValueError, RuntimeError) as exc:
            st.error(str(exc))
        except Exception:
            st.error("러닝 기록을 등록하지 못했습니다. 잠시 후 다시 시도해주세요.")
        else:
            st.session_state["show_manual_run_form"] = False
            st.session_state["regular_run_edit_success"] = "러닝 기록을 수동 등록했습니다."
            st.rerun()


@st.dialog("러닝 기록 삭제")
def confirm_regular_run_deletion(record: dict) -> None:
    run_id = int(record["regular_run_id"])
    run_date = str(record.get("run_date") or "")[:10]
    run_type = str(record.get("run_type") or "러닝")
    st.warning(
        f"'{run_date} {run_type} 러닝' 기록을 삭제하면 복구할 수 없습니다."
    )
    st.caption("연결된 원본 캡처 이미지도 함께 정리됩니다.")

    with st.form(f"delete_regular_run_{run_id}"):
        admin_password = st.text_input(
            "관리자 비밀번호",
            type="password",
            autocomplete="current-password",
        )
        with st.container(horizontal=True, horizontal_alignment="right"):
            cancelled = st.form_submit_button("취소")
            confirmed = st.form_submit_button(
                "삭제",
                type="primary",
                icon=":material/delete:",
            )

    if cancelled:
        st.session_state.pop("regular_run_pending_delete", None)
        st.rerun()

    if confirmed:
        try:
            delete_regular_run(
                run_id,
                admin_password,
                record.get("source_image_path"),
            )
        except (PermissionError, ValueError, RuntimeError) as exc:
            st.error(str(exc))
        except Exception:
            st.error("러닝 기록을 삭제하지 못했습니다. 잠시 후 다시 시도해주세요.")
        else:
            st.session_state.pop("regular_run_pending_delete", None)
            st.session_state["regular_run_edit_success"] = (
                f"'{run_date} {run_type} 러닝' 기록을 삭제했습니다."
            )
            st.rerun()


run_title_col, run_actions_col = st.columns([3, 2], vertical_alignment="center")
with run_title_col:
    st.subheader("정기/자유러닝 목록")
with run_actions_col:
    if admin_user:
        manual_form_is_open = st.session_state.get("show_manual_run_form", False)
        uploader_is_open = st.session_state.get(
            "show_regular_run_uploader",
            False,
        )
        with st.container(
            horizontal=True,
            horizontal_alignment="right",
            gap="small",
        ):
            if st.button(
                "닫기" if manual_form_is_open else "수동 등록",
                icon=":material/close:" if manual_form_is_open else ":material/edit_calendar:",
                type="secondary" if manual_form_is_open else "primary",
                key="toggle_manual_run_form",
                width="content",
            ):
                st.session_state["show_manual_run_form"] = not manual_form_is_open
                st.session_state["show_regular_run_uploader"] = False
                st.rerun()
            if st.button(
                "닫기" if uploader_is_open else "캡처 이미지 등록",
                icon=":material/close:" if uploader_is_open else ":material/add_photo_alternate:",
                type="secondary" if uploader_is_open else "primary",
                key="toggle_regular_run_uploader",
                width="content",
            ):
                st.session_state["show_regular_run_uploader"] = not uploader_is_open
                st.session_state["show_manual_run_form"] = False
                st.rerun()

if edit_success_message := st.session_state.pop("regular_run_edit_success", None):
    st.success(edit_success_message)

run_records = []
try:
    run_records = get_regular_run_records() if admin_user else []
    regular_runs = get_regular_run_list(run_records if admin_user else None)
except Exception as exc:
    st.warning(
        "정기/자유러닝 데이터를 불러오지 못했습니다. Supabase 연결과 "
        "regular_runs 테이블을 확인해주세요. 뒷풀이 기능을 처음 적용한다면 "
        "009_add_regular_run_after_party.sql을 실행해주세요."
    )
    if admin_user:
        st.caption(f"상세 오류: {type(exc).__name__}: {exc}")
else:
    if regular_runs.empty:
        st.info("아직 등록된 러닝이 없습니다.")
    else:
        regular_runs["구분"] = regular_runs["구분"].replace(RUN_TYPE_LABELS)
        regular_runs["뒷풀이"] = regular_runs["뒷풀이"].replace(
            AFTER_PARTY_LABELS
        )
        column_config = {
            "번호": st.column_config.NumberColumn(
                "번호",
                width="small",
                format="%d",
                pinned=True,
            ),
            "코스 이름": st.column_config.TextColumn(
                "코스 이름",
                width="medium",
            ),
            "거리 (km)": st.column_config.NumberColumn(format="%.1f km"),
            "뒷풀이": st.column_config.TextColumn(
                "뒷풀이",
                width="small",
            ),
            "총 참석인원": st.column_config.NumberColumn(format="%d명"),
            "참석자 명단": st.column_config.TextColumn(width="large"),
        }
        if admin_user:
            regular_runs["관리"] = [
                [":material/edit: 수정", ":material/delete: 삭제"]
            ] * len(regular_runs)

            def handle_regular_run_management() -> None:
                click = st.session_state.get("regular_run_management_click") or {}
                row_index = click.get("row")
                if row_index is None or not 0 <= int(row_index) < len(run_records):
                    return
                selected_record = dict(run_records[int(row_index)])
                if "삭제" in str(click.get("label", "")):
                    st.session_state["regular_run_pending_delete"] = selected_record
                    st.session_state.pop("regular_run_pending_edit", None)
                elif "수정" in str(click.get("label", "")):
                    st.session_state["regular_run_pending_edit"] = selected_record
                    st.session_state.pop("regular_run_pending_delete", None)

            column_config["관리"] = st.column_config.ButtonColumn(
                "관리",
                width="small",
                type="tertiary",
                alignment="center",
                on_click=handle_regular_run_management,
                key="regular_run_management_click",
            )

        st.dataframe(
            regular_runs,
            width="stretch",
            hide_index=True,
            column_config=column_config,
        )

if admin_user and (pending_edit := st.session_state.get("regular_run_pending_edit")):
    render_regular_run_editor(pending_edit)
elif admin_user and (
    pending_delete := st.session_state.get("regular_run_pending_delete")
):
    confirm_regular_run_deletion(pending_delete)

if not admin_user:
    st.stop()

if st.session_state.get("show_manual_run_form", False):
    render_manual_regular_run_form()
    st.stop()

if not st.session_state.get("show_regular_run_uploader", False):
    st.stop()

st.subheader("캡처 이미지로 등록")
st.caption(
    "소모임 참석자 화면을 업로드하면 날짜·시간·요일·참석인원·참석자 명단을 읽습니다. "
    "OCR 결과는 반드시 확인한 뒤 등록해주세요."
)
if not has_paddle_ocr_runtime():
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
        if extracted.get("run_date") is None:
            st.warning(
                "캡처에서 러닝 날짜를 확실하게 인식하지 못했습니다. "
                "아래 날짜는 오늘로 임시 설정되므로 등록 전 확인해주세요."
            )
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

        default_run_type = default_run_type_for_date(run_date)
        run_type_label = st.segmented_control(
            "러닝 구분",
            options=list(RUN_TYPE_VALUES),
            default=RUN_TYPE_LABELS[default_run_type],
            selection_mode="single",
            key=f"regular_run_type_colored_{image_hash}_{run_date.isoformat()}",
        )
        run_type = RUN_TYPE_VALUES.get(run_type_label, default_run_type)
        st.caption("일요일은 정기, 그 외 요일은 자유로 자동 설정됩니다. 필요하면 변경할 수 있습니다.")

        distance_km = st.number_input(
            "거리 (km)",
            min_value=0.0,
            step=0.5,
            value=float(extracted.get("distance_km") or 5.0),
            key=f"regular_run_distance_{image_hash}",
        )

        course_name = st.text_input(
            "코스 이름",
            value=str(extracted.get("course_name") or ""),
            placeholder="예: 온천천 왕복 코스",
            key=f"regular_run_course_{image_hash}",
        )

        after_party_label = st.segmented_control(
            "뒷풀이",
            options=list(AFTER_PARTY_VALUES),
            default=AFTER_PARTY_LABELS["없음"],
            selection_mode="single",
            key=f"regular_run_after_party_{image_hash}",
        )
        after_party = AFTER_PARTY_VALUES.get(after_party_label, "없음")

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
                    course_name=course_name,
                    distance_km=distance_km,
                    target_pace="",
                    after_party=after_party,
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
                st.session_state["show_regular_run_uploader"] = False
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
