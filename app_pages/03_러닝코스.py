from __future__ import annotations

import html
import math
from datetime import date

import pandas as pd
import pydeck as pdk
import streamlit as st

from database.client import has_supabase_admin_credentials
from services.running_course_service import (
    GPXParseError,
    delete_running_course,
    get_running_courses,
    parse_gpx,
    register_running_course,
    update_running_course,
)
from services.auth_service import get_user_role
from ui.auth_widgets import render_top_auth


DEFAULT_LATITUDE = 35.205937778825124
DEFAULT_LONGITUDE = 129.07877285285102
OPENFREEMAP_STYLE = "https://tiles.openfreemap.org/styles/liberty"
START_FLAG_BACKGROUND = {
    "url": (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAAAXNSR0IArs4c6QAAAARnQU1BAACx"
        "jwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAAFjSURBVHhe7ZuxbQJREEQ3dAkugdAhoUNCSnAJ"
        "LsEZIaUQktIBZVCCQ1ubjlbm//0XeEbzpMlug3kHp38riDDmL94j4utJ8hpZsuDPk+Q1slhAURhz"
        "K74W/zF7LDdCDmJhxnxHxCuWG0FFwAmLjaIg4BERL1hsFAUBn1hqBnYBdyw0C7uAIxaahVnAFct0"
        "YBbwhmU6sArY5O4nrALaBx+EVUDmjGU6MAvILD8H2AVcsNAs7AIyByw1g4KApdOggoDMBxYbRUVA"
        "+41QRUCm9SlQEdA+GKkI8EYIi42iIMAboRXYBXgjtAqzgOU3wYRVwCZ3P2EV0D74IKwCMt4IbfEc"
        "YBfgjZA3QounQQUBmdYuIFER0H4jHBHA8huhHZYbIQexMCavkcUCisIYC8AhJSygKIyxABxSwgKK"
        "whgLwCElLKAojLEAHFLCAorCGAvAISUsoCiMsQAcUsICisIYaQHyf57+BXuUrhIj5hiWAAAAAElF"
        "TkSuQmCC"
    ),
    "width": 64,
    "height": 64,
    "anchorX": 13,
    "anchorY": 61,
    "mask": True,
}
START_FLAG_CHECKERS = {
    "url": (
        "data:image/png;base64,"
        "iVBORw0KGgoAAAANSUhEUgAAAEAAAABACAYAAACqaXHeAAAAAXNSR0IArs4c6QAAAARnQU1BAACx"
        "jwv8YQUAAAAJcEhZcwAADsMAAA7DAcdvqGQAAAGBSURBVHhe7ZvBaQNREEN/aS4pJaQUl5LOEuYq"
        "JBhnNMHZ1QNdPmtJX8awF58TQgg9HuecT6I6vwV12W+iOr8FGYBcvvQkPwum7k9F/dRQXT8bFYqX"
        "L32RM6b6fAeVg+r62VDFMgA5Y+oWVjmorp8NVSwDkDOmbmGVg+r62VDFMgA5Y+oWVjmorp8NVaz7"
        "HvBBzph++9w6FYKXf+WbUJ9HTfxWYYHTwkxTvzVU4LQwauq3hgqcFkY5/FZQgY7CG352VKCrsNv"
        "Pjgp0Fd7ws6IC3+U9gMlKGeLlS7d/E8wA5IypW1jloLp+NlSxDEDOmLqFVQ6q62dDFcsA5IypW1"
        "jloLp+NlSxd3kPWKdC8PKvfBPq86iJ3yoscFqYaeq3hgqcFkZN/dZQgdPCKIffCirQUXjDz44KdB"
        "V2+9lRga7CG35WVGC38L8nA5DLZ4AMkAEyQAbAB69KBiCXzwAZIANkgAyAD16VDEAunwEyQAbIAB"
        "kAH7wqtx9A/Z3tz/++Foz8ABtyknP5GpB3AAAAAElFTkSuQmCC"
    ),
    "width": 64,
    "height": 64,
    "anchorX": 13,
    "anchorY": 60,
    "mask": True,
}
COURSE_COLORS = [
    [37, 99, 235, 210],
    [234, 88, 12, 210],
    [22, 163, 74, 210],
    [219, 39, 119, 210],
    [8, 145, 178, 210],
    [220, 38, 38, 210],
    [124, 58, 237, 210],
    [202, 138, 4, 210],
    [13, 148, 136, 210],
    [79, 70, 229, 210],
    [77, 124, 15, 210],
    [190, 24, 93, 210],
    [3, 105, 161, 210],
    [126, 34, 206, 210],
    [194, 65, 12, 210],
    [4, 120, 87, 210],
    [190, 18, 60, 210],
    [29, 78, 216, 210],
    [146, 64, 14, 210],
    [71, 85, 105, 210],
]
@st.cache_data(ttl="2m", max_entries=5, show_spinner=False)
def load_courses() -> list[dict]:
    return get_running_courses()


@st.cache_data(max_entries=20, show_spinner=False)
def parse_uploaded_gpx(data: bytes, filename: str) -> dict:
    return parse_gpx(data, filename)


def is_missing_courses_table(error: Exception) -> bool:
    message = str(error)
    return "PGRST205" in message or (
        "running_activities" in message and "schema cache" in message
    )


def format_duration(duration_seconds) -> str:
    if not duration_seconds:
        return "-"
    hours, remainder = divmod(int(duration_seconds), 3600)
    minutes, seconds = divmod(remainder, 60)
    return f"{hours}:{minutes:02d}:{seconds:02d}"


def format_distance_km(distance_km) -> str:
    try:
        value = float(distance_km or 0)
    except (TypeError, ValueError):
        value = 0.0
    return f"{value:.2f}".rstrip("0").rstrip(".") + "km"


def map_view(courses: list[dict]) -> pdk.ViewState:
    points = [
        point
        for course in courses
        for path in course.get("paths", [])
        for point in path
        if isinstance(point, list) and len(point) >= 2
    ]
    if not points:
        return pdk.ViewState(
            latitude=DEFAULT_LATITUDE,
            longitude=DEFAULT_LONGITUDE,
            zoom=15,
        )

    longitudes = [float(point[0]) for point in points]
    latitudes = [float(point[1]) for point in points]
    span = max(max(longitudes) - min(longitudes), max(latitudes) - min(latitudes))
    zoom = 15 if span == 0 else max(7, min(16, math.log2(360 / span) - 1.5))

    return pdk.ViewState(
        latitude=(min(latitudes) + max(latitudes)) / 2,
        longitude=(min(longitudes) + max(longitudes)) / 2,
        zoom=zoom,
    )


def course_color(course: dict, course_index: int) -> list[int]:
    return course.get("color", COURSE_COLORS[course_index % len(COURSE_COLORS)])


def render_course_legend(courses: list[dict]) -> None:
    legend_items = []
    for course_index, course in enumerate(courses):
        if not any(len(path) >= 2 for path in course.get("paths", [])):
            continue
        color = course_color(course, course_index)
        red, green, blue = color[:3]
        alpha = (color[3] / 255) if len(color) > 3 else 1
        course_name = html.escape(str(course.get("name") or "러닝 코스"))
        distance = html.escape(format_distance_km(course.get("distance_km")))
        legend_items.append(
            "<span style='display:inline-flex;align-items:center;gap:0.4rem;'>"
            f"<span style='width:1.5rem;height:0.3rem;border-radius:999px;"
            f"background:rgba({red},{green},{blue},{alpha:.2f});'></span>"
            f"<span>{course_name}({distance})</span></span>"
        )

    if not legend_items:
        return

    st.html(
        "<div aria-label='코스 범례' style='display:flex;flex-wrap:wrap;"
        "align-items:center;gap:0.6rem 1rem;margin:0.35rem 0 0.2rem;'>"
        "<strong style='font-size:0.9rem;'>코스 범례</strong>"
        + "".join(legend_items)
        + "</div>"
    )


def render_course_map(courses: list[dict], height: int = 680) -> None:
    path_rows = []
    endpoints = []
    start_flags = []
    course_labels = []

    for course_index, course in enumerate(courses):
        color = course_color(course, course_index)
        valid_paths = [path for path in course.get("paths", []) if len(path) >= 2]
        if valid_paths:
            label_path = max(valid_paths, key=len)
            course_labels.append(
                {
                    "name": course.get("name", "러닝 코스"),
                    "position": label_path[len(label_path) // 2],
                }
            )
            start_flags.append(
                {
                    "name": f"{course.get('name', '러닝 코스')} · 출발",
                    "details": "코스 시작점",
                    "position": valid_paths[0][0],
                    "color": color,
                    "background_icon": START_FLAG_BACKGROUND,
                    "checker_icon": START_FLAG_CHECKERS,
                }
            )

        for path in valid_paths:
            path_rows.append(
                {
                    "name": course.get("name", "러닝 코스"),
                    "details": (
                        f"{course.get('run_date') or '날짜 미등록'} · "
                        f"{float(course.get('distance_km') or 0):.2f} km"
                    ),
                    "path": path,
                    "color": color,
                }
            )
            endpoints.extend(
                [
                    {
                        "name": f"{course.get('name', '러닝 코스')} · 도착",
                        "details": "도착 지점",
                        "position": path[-1],
                        "color": color,
                    },
                ]
            )

    layers = []
    if not courses:
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=[{"position": [DEFAULT_LONGITUDE, DEFAULT_LATITUDE]}],
                get_position="position",
                get_fill_color=[0, 0, 0, 0],
                get_radius=1,
                pickable=False,
            )
        )
    if path_rows:
        layers.append(
            pdk.Layer(
                "PathLayer",
                data=path_rows,
                get_path="path",
                get_color="color",
                get_width=8,
                width_min_pixels=5,
                width_max_pixels=12,
                pickable=True,
            )
        )
        layers.append(
            pdk.Layer(
                "IconLayer",
                data=start_flags,
                get_position="position",
                get_icon="background_icon",
                get_color=[255, 255, 255, 245],
                get_size=56,
                size_units=pdk.types.String("pixels"),
                get_pixel_offset=[8, 0],
                billboard=True,
                pickable=False,
            )
        )
        layers.append(
            pdk.Layer(
                "IconLayer",
                data=start_flags,
                get_position="position",
                get_icon="checker_icon",
                get_color="color",
                get_size=54,
                size_units=pdk.types.String("pixels"),
                get_pixel_offset=[8, 0],
                billboard=True,
                pickable=True,
            )
        )
        layers.append(
            pdk.Layer(
                "ScatterplotLayer",
                data=endpoints,
                get_position="position",
                get_fill_color="color",
                get_radius=18,
                radius_min_pixels=5,
                pickable=True,
            )
        )
        layers.append(
            pdk.Layer(
                "TextLayer",
                data=course_labels,
                get_position="position",
                get_text="name",
                get_color=[15, 23, 42, 255],
                get_size=70,
                size_units=pdk.types.String("meters"),
                size_min_pixels=11,
                size_max_pixels=28,
                get_pixel_offset=[0, -16],
                get_text_anchor=pdk.types.String("middle"),
                get_alignment_baseline=pdk.types.String("bottom"),
                billboard=True,
                pickable=False,
            )
        )

    st.pydeck_chart(
        pdk.Deck(
            map_style=OPENFREEMAP_STYLE,
            map_provider="maplibre",
            initial_view_state=map_view(courses),
            layers=layers,
            tooltip={"text": "{name}\n{details}"},
        ),
        height=height,
        width="stretch",
    )
    render_course_legend(courses)
    st.caption(
        "지도 © [OpenFreeMap](https://openfreemap.org/) · "
        "데이터 © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright)"
    )


def render_course_table(courses: list[dict], can_manage: bool) -> None:
    columns = ["코스 이름", "거리 (km)", "지역"]
    if can_manage:
        columns.append("관리")

    course_rows = [
        {
            "코스 이름": course.get("name", ""),
            "거리 (km)": course.get("distance_km", 0),
            "지역": course.get("location_name", ""),
            **(
                {
                    "관리": [
                        ":material/edit: 수정",
                        ":material/delete: 삭제",
                    ]
                }
                if can_manage
                else {}
            ),
        }
        for course in courses
    ]
    course_frame = pd.DataFrame(course_rows, columns=columns)

    def handle_management_click() -> None:
        click = st.session_state.get("course_management_click")
        if not click:
            return
        row_index = int(click["row"])
        if 0 <= row_index < len(courses):
            selected_course = courses[row_index]
            if "수정" in str(click.get("label", "")):
                st.session_state["course_pending_edit"] = selected_course
                st.session_state.pop("course_pending_delete", None)
            elif "삭제" in str(click.get("label", "")):
                st.session_state["course_pending_delete"] = selected_course
                st.session_state.pop("course_pending_edit", None)

    column_config = {
        "코스 이름": st.column_config.TextColumn(
            "코스 이름", width=260, pinned=True
        ),
        "거리 (km)": st.column_config.NumberColumn(
            "거리 (km)", width=110, format="%.2f"
        ),
        "지역": st.column_config.TextColumn("지역", width=160),
    }
    if can_manage:
        column_config["관리"] = st.column_config.ButtonColumn(
            "관리",
            width=90,
            type="tertiary",
            alignment="center",
            on_click=handle_management_click,
            key="course_management_click",
        )

    st.dataframe(
        course_frame,
        column_config=column_config,
        hide_index=True,
        width="stretch",
    )
    if course_frame.empty:
        st.caption("아직 등록된 러닝 코스가 없습니다.")


@st.dialog("코스 수정")
def edit_running_course(course: dict) -> None:
    course_name = str(course.get("name") or "러닝 코스")
    try:
        selected_date = date.fromisoformat(str(course.get("run_date"))[:10])
    except (TypeError, ValueError):
        selected_date = date.today()

    tags = course.get("tags") or []
    tag_text = tags if isinstance(tags, str) else ", ".join(str(tag) for tag in tags)

    st.caption("GPX 경로·거리 원본은 유지하고 코스 정보를 수정합니다.")
    with st.form(f"edit_course_{course.get('activity_id')}"):
        name = st.text_input(
            "코스 이름",
            value=course_name,
            max_chars=80,
        )
        run_date = st.date_input(
            "뛴 날짜",
            value=selected_date,
            max_value=date.today(),
            format="YYYY-MM-DD",
        )
        location_name = st.text_input(
            "지역",
            value=str(course.get("location_name") or ""),
            max_chars=100,
        )
        description = st.text_area(
            "코스 설명",
            value=str(course.get("description") or ""),
            max_chars=500,
        )
        tag_input = st.text_input(
            "태그",
            value=tag_text,
            placeholder="예: 정규런, 야간런, 10K (쉼표로 구분)",
        )
        with st.container(horizontal=True, horizontal_alignment="right"):
            cancelled = st.form_submit_button("취소")
            submitted = st.form_submit_button(
                "수정 저장",
                type="primary",
                icon=":material/save:",
            )

    if cancelled:
        st.session_state.pop("course_pending_edit", None)
        st.rerun()

    if submitted:
        try:
            update_running_course(
                activity_id=course.get("activity_id"),
                name=name,
                run_date=run_date,
                location_name=location_name,
                description=description,
                tags=tag_input.split(","),
            )
        except ValueError as error:
            st.error(str(error))
        except Exception:
            st.error("코스를 수정하지 못했습니다. 잠시 후 다시 시도해 주세요.")
        else:
            st.session_state.pop("course_pending_edit", None)
            load_courses.clear()
            st.session_state["course_success_message"] = (
                f"'{name.strip()}' 코스를 수정했습니다."
            )
            st.rerun()


@st.dialog("코스 삭제")
def confirm_course_deletion(course: dict) -> None:
    course_name = str(course.get("name") or "러닝 코스")
    st.warning(f"'{course_name}' 코스를 삭제하면 복구할 수 없습니다.")

    with st.form(f"delete_course_{course.get('activity_id')}"):
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
        st.session_state.pop("course_pending_delete", None)
        st.rerun()

    if confirmed:
        try:
            delete_running_course(course.get("activity_id"), admin_password)
        except PermissionError as error:
            st.error(str(error))
        except RuntimeError as error:
            st.error(str(error))
        except Exception:
            st.error("코스를 삭제하지 못했습니다. 잠시 후 다시 시도해 주세요.")
        else:
            recent_course = st.session_state.get("recently_registered_course")
            if recent_course and recent_course.get("source_hash") == course.get(
                "source_hash"
            ):
                st.session_state.pop("recently_registered_course", None)
            st.session_state.pop("course_pending_delete", None)
            load_courses.clear()
            st.session_state["course_success_message"] = (
                f"'{course_name}' 코스를 삭제했습니다."
            )
            st.rerun()


st.set_page_config(
    page_title="러닝 코스 | ON_FLOW",
    page_icon="🗺️",
    layout="wide",
)

render_top_auth(current_page="app_pages/03_러닝코스.py")
is_admin_user = get_user_role() == "admin"

st.title("러닝 코스")
st.caption("GPX 파일로 ON:FLOW가 달린 코스를 지도에 기록하고 공유합니다.")

storage_ready = True
storage_notice = None
try:
    registered_courses = load_courses()
except Exception as error:
    registered_courses = []
    storage_ready = False
    if is_missing_courses_table(error):
        storage_notice = (
            "코스 저장소 설정 전입니다. GPX 파일 분석은 바로 사용할 수 있으며, "
            "영구 등록은 database/migrations/001_create_running_activities.sql 적용 후 활성화됩니다."
        )
    else:
        storage_notice = "등록된 코스를 불러오지 못했습니다. 잠시 후 다시 시도해 주세요."

recent_course = st.session_state.get("recently_registered_course")
if recent_course:
    recent_hash = recent_course.get("source_hash")
    course_is_loaded = any(
        course.get("source_hash") == recent_hash for course in registered_courses
    )
    if course_is_loaded:
        st.session_state.pop("recently_registered_course", None)
    else:
        registered_courses.insert(0, recent_course)

recent_courses = st.session_state.get("recently_registered_courses", [])
pending_recent_courses = []
registered_hashes = {course.get("source_hash") for course in registered_courses}
for course in reversed(recent_courses):
    if course.get("source_hash") not in registered_hashes:
        registered_courses.insert(0, course)
        pending_recent_courses.append(course)
if pending_recent_courses:
    st.session_state["recently_registered_courses"] = pending_recent_courses
else:
    st.session_state.pop("recently_registered_courses", None)

map_column, table_column = st.columns(
    [3, 2],
    gap="medium",
    vertical_alignment="top",
)
with map_column:
    st.subheader("코스 지도")
    map_slot = st.empty()

with table_column:
    with st.container(
        horizontal=True,
        horizontal_alignment="distribute",
        vertical_alignment="center",
    ):
        st.subheader("등록된 코스")
        if is_admin_user:
            uploader_is_open = st.session_state.get("show_course_uploader", False)
            if st.button(
                "닫기" if uploader_is_open else "GPX 등록",
                icon=":material/close:" if uploader_is_open else ":material/upload_file:",
                type="secondary" if uploader_is_open else "primary",
                key="toggle_course_uploader",
                width="content",
            ):
                st.session_state["show_course_uploader"] = not uploader_is_open
                st.rerun()
    render_course_table(registered_courses, can_manage=is_admin_user)

pending_edit = st.session_state.get("course_pending_edit")
if pending_edit:
    if is_admin_user:
        edit_running_course(pending_edit)
    else:
        st.session_state.pop("course_pending_edit", None)

pending_delete = st.session_state.get("course_pending_delete")
if pending_delete:
    if is_admin_user:
        confirm_course_deletion(pending_delete)
    else:
        st.session_state.pop("course_pending_delete", None)

if storage_notice:
    st.info(storage_notice)

if message := st.session_state.pop("course_success_message", None):
    st.success(message)

for message_type, message in st.session_state.pop("course_batch_messages", []):
    getattr(st, message_type)(message)

preview_courses = []
if is_admin_user and st.session_state.get("show_course_uploader", False):
    st.subheader("GPX 코스 등록")

    admin_storage_ready = has_supabase_admin_credentials()
    if not admin_storage_ready:
        st.warning(
            "관리자 등록을 활성화하려면 Streamlit secrets에 "
            "SUPABASE_SECRET_KEY를 추가해야 합니다."
        )

    uploader_version = st.session_state.setdefault("course_uploader_version", 0)
    uploaded_files = st.file_uploader(
        "GPX 파일",
        type=["gpx"],
        accept_multiple_files=True,
        max_upload_size=5,
        help="GPX 파일을 여러 개 선택할 수 있습니다. 파일당 최대 5MB입니다.",
        key=f"running_course_gpx_{uploader_version}",
    )

    seen_hashes = set()
    for uploaded_file in uploaded_files or []:
        try:
            preview_course = parse_uploaded_gpx(
                uploaded_file.getvalue(), uploaded_file.name
            )
        except GPXParseError as error:
            st.error(f"{uploaded_file.name}: {error}")
            continue
        if preview_course["source_hash"] in seen_hashes:
            st.warning(f"{uploaded_file.name}: 같은 내용의 GPX 파일이 중복 선택되었습니다.")
            continue
        seen_hashes.add(preview_course["source_hash"])
        preview_courses.append(preview_course)

    if preview_courses:
        st.caption(f"선택한 GPX {len(preview_courses)}개를 확인한 뒤 한 번에 등록할 수 있습니다.")
        course_inputs = []
        with st.form("course_batch_registration"):
            for index, preview_course in enumerate(preview_courses, start=1):
                form_key = preview_course["source_hash"][:12]
                parsed_run_date = (
                    date.fromisoformat(preview_course["run_date"])
                    if preview_course.get("run_date")
                    else date.today()
                )
                with st.container(border=True):
                    st.markdown(f"#### {index}. {preview_course['name']}")
                    with st.container(horizontal=True):
                        st.metric("거리", f"{preview_course['distance_km']:.2f} km")
                        st.metric("누적 상승", f"{preview_course['elevation_gain_m']:.0f} m")
                        st.metric("소요 시간", format_duration(preview_course["duration_seconds"]))
                        st.metric("GPS 포인트", f"{preview_course['point_count']:,}개")

                    course_inputs.append(
                        {
                            "preview": preview_course,
                            "name": st.text_input(
                                "코스 이름",
                                value=preview_course["name"],
                                max_chars=80,
                                key=f"course_name_{form_key}",
                            ),
                            "run_date": st.date_input(
                                "뛴 날짜",
                                value=parsed_run_date,
                                max_value=date.today(),
                                key=f"course_date_{form_key}",
                            ),
                            "location": st.text_input(
                                "지역",
                                max_chars=100,
                                placeholder="예: 부산 온천천",
                                key=f"course_location_{form_key}",
                            ),
                            "description": st.text_area(
                                "코스 설명",
                                max_chars=500,
                                placeholder="출발 지점, 난이도, 추천 시간대 등을 기록해 주세요.",
                                key=f"course_description_{form_key}",
                            ),
                            "tags": st.text_input(
                                "태그",
                                placeholder="예: 정규런, 야간런, 10K (쉼표로 구분)",
                                key=f"course_tags_{form_key}",
                            ),
                        }
                    )

            submitted = st.form_submit_button(
                f"코스 {len(preview_courses)}개 등록",
                type="primary",
                icon=":material/add_location_alt:",
                disabled=not (storage_ready and admin_storage_ready),
                width="stretch",
            )

        if submitted:
            saved_courses = []
            batch_messages = []
            for course_input in course_inputs:
                try:
                    saved_course = register_running_course(
                        course_input["name"],
                        course_input["run_date"],
                        course_input["location"],
                        course_input["description"],
                        course_input["tags"].split(","),
                        st.session_state.get("user_id", "admin"),
                        course_input["preview"],
                    )
                except ValueError as error:
                    batch_messages.append(("error", f"{course_input['name']}: {error}"))
                except Exception as error:
                    if "23505" in str(error):
                        batch_messages.append(
                            ("warning", f"{course_input['name']}: 이미 등록된 GPX 코스입니다.")
                        )
                    elif "gpx_raw_base64" in str(error) or "gpx_filename" in str(error):
                        batch_messages.append(
                            (
                                "error",
                                f"{course_input['name']}: Supabase에서 "
                                "008_add_running_course_gpx_raw.sql을 먼저 실행해 주세요.",
                            )
                        )
                    else:
                        batch_messages.append(
                            ("error", f"{course_input['name']}: 등록에 실패했습니다.")
                        )
                else:
                    saved_courses.append(saved_course)
                    batch_messages.append(
                        ("success", f"{course_input['name']}: 등록했습니다.")
                    )

            if saved_courses:
                load_courses.clear()
                st.session_state["recently_registered_courses"] = saved_courses
            if len(saved_courses) == len(course_inputs):
                st.session_state["course_uploader_version"] = uploader_version + 1
                st.session_state["show_course_uploader"] = False
            st.session_state["course_batch_messages"] = batch_messages
            st.rerun()

display_courses = list(registered_courses)

with map_slot.container():
    render_course_map(display_courses)
