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
)
from services.auth_service import get_user_role
from ui.auth_widgets import render_top_auth


DEFAULT_LATITUDE = 35.205937778825124
DEFAULT_LONGITUDE = 129.07877285285102
OPENFREEMAP_STYLE = "https://tiles.openfreemap.org/styles/liberty"
COURSE_COLORS = [
    [37, 99, 235, 210],
    [16, 185, 129, 210],
    [249, 115, 22, 210],
    [168, 85, 247, 210],
    [225, 29, 72, 210],
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
        legend_items.append(
            "<span style='display:inline-flex;align-items:center;gap:0.4rem;'>"
            f"<span style='width:1.5rem;height:0.3rem;border-radius:999px;"
            f"background:rgba({red},{green},{blue},{alpha:.2f});'></span>"
            f"<span>{course_name}</span></span>"
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
                        "name": f"{course.get('name', '러닝 코스')} · 출발",
                        "details": "출발 지점",
                        "position": path[0],
                        "color": color,
                    },
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
                get_width=5,
                width_min_pixels=3,
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
        width=height,
    )
    render_course_legend(courses)
    st.caption(
        "지도 © [OpenFreeMap](https://openfreemap.org/) · "
        "데이터 © [OpenStreetMap contributors](https://www.openstreetmap.org/copyright)"
    )


def render_course_table(courses: list[dict], can_delete: bool) -> None:
    columns = ["코스 이름", "거리 (km)", "지역"]
    if can_delete:
        columns.append("관리")

    course_rows = [
        {
            "코스 이름": course.get("name", ""),
            "거리 (km)": course.get("distance_km", 0),
            "지역": course.get("location_name", ""),
            **({"관리": ":material/delete:"} if can_delete else {}),
        }
        for course in courses
    ]
    course_frame = pd.DataFrame(course_rows, columns=columns)

    def handle_delete_click() -> None:
        click = st.session_state.get("course_delete_click")
        if not click:
            return
        row_index = int(click["row"])
        if 0 <= row_index < len(courses):
            st.session_state["course_pending_delete"] = courses[row_index]

    column_config = {
        "코스 이름": st.column_config.TextColumn(
            "코스 이름", width=260, pinned=True
        ),
        "거리 (km)": st.column_config.NumberColumn(
            "거리 (km)", width=110, format="%.2f"
        ),
        "지역": st.column_config.TextColumn("지역", width=160),
    }
    if can_delete:
        column_config["관리"] = st.column_config.ButtonColumn(
            "",
            width=52,
            type="tertiary",
            alignment="center",
            on_click=handle_delete_click,
            key="course_delete_click",
        )

    st.dataframe(
        course_frame,
        column_config=column_config,
        hide_index=True,
        width="content",
    )
    if course_frame.empty:
        st.caption("아직 등록된 러닝 코스가 없습니다.")


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

st.subheader("코스 지도")
map_slot = st.empty()

st.subheader("등록된 코스")
render_course_table(registered_courses, can_delete=is_admin_user)

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

preview_course = None
if is_admin_user:
    st.subheader("GPX 코스 등록")

    admin_storage_ready = has_supabase_admin_credentials()
    if not admin_storage_ready:
        st.warning(
            "관리자 등록을 활성화하려면 Streamlit secrets에 "
            "SUPABASE_SECRET_KEY를 추가해야 합니다."
        )

    uploaded_file = st.file_uploader(
        "GPX 파일",
        type=["gpx"],
        max_upload_size=5,
        help="GPS 앱이나 러닝 워치에서 내보낸 GPX 파일을 선택하세요. 최대 5MB입니다.",
        key="running_course_gpx",
    )

    if uploaded_file is not None:
        try:
            preview_course = parse_uploaded_gpx(
                uploaded_file.getvalue(), uploaded_file.name
            )
        except GPXParseError as error:
            st.error(str(error))

    if preview_course:
        with st.container(horizontal=True):
            st.metric("거리", f"{preview_course['distance_km']:.2f} km")
            st.metric("누적 상승", f"{preview_course['elevation_gain_m']:.0f} m")
            st.metric("소요 시간", format_duration(preview_course["duration_seconds"]))
            st.metric("GPS 포인트", f"{preview_course['point_count']:,}개")

        parsed_run_date = (
            date.fromisoformat(preview_course["run_date"])
            if preview_course.get("run_date")
            else date.today()
        )
        form_key = preview_course["source_hash"][:12]
        with st.form(f"course_registration_{form_key}"):
            course_name = st.text_input(
                "코스 이름",
                value=preview_course["name"],
                max_chars=80,
            )
            course_run_date = st.date_input(
                "뛴 날짜",
                value=parsed_run_date,
                max_value=date.today(),
            )
            course_location = st.text_input(
                "지역",
                max_chars=100,
                placeholder="예: 부산 온천천",
            )
            course_description = st.text_area(
                "코스 설명",
                max_chars=500,
                placeholder="출발 지점, 난이도, 추천 시간대 등을 기록해 주세요.",
            )
            course_tags = st.text_input(
                "태그",
                placeholder="예: 정규런, 야간런, 10K (쉼표로 구분)",
            )
            submitted = st.form_submit_button(
                "코스 등록",
                type="primary",
                icon=":material/add_location_alt:",
                disabled=not (storage_ready and admin_storage_ready),
                width="stretch",
            )

        if submitted:
            try:
                saved_course = register_running_course(
                    course_name,
                    course_run_date,
                    course_location,
                    course_description,
                    course_tags.split(","),
                    st.session_state.get("user_id", "admin"),
                    preview_course,
                )
            except ValueError as error:
                st.error(str(error))
            except Exception as error:
                if "23505" in str(error):
                    st.warning("이미 등록된 GPX 코스입니다.")
                else:
                    st.error("코스 등록에 실패했습니다. 잠시 후 다시 시도해 주세요.")
            else:
                load_courses.clear()
                st.session_state["recently_registered_course"] = saved_course
                st.session_state["course_success_message"] = (
                    f"'{course_name}' 코스를 등록했습니다."
                )
                st.rerun()

display_courses = list(registered_courses)

with map_slot.container():
    render_course_map(display_courses)
