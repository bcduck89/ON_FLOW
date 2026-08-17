from datetime import date
from pathlib import Path

import altair as alt
import pandas as pd
import streamlit as st

from services.home_dashboard_service import (
    build_monthly_distance_for_year,
    get_running_distance_dashboard,
)
from ui.auth_widgets import render_top_auth


st.set_page_config(
    page_title="Home | ON_FLOW",
    page_icon="🏃",
    layout="wide",
    initial_sidebar_state="expanded",
)

render_top_auth(current_page="app_pages/home.py")

logo_path = Path("assets/onflow_logo.png")
MONTH_COLORS = [
    "#2563EB",
    "#0891B2",
    "#0D9488",
    "#16A34A",
    "#65A30D",
    "#CA8A04",
    "#EA580C",
    "#DC2626",
    "#DB2777",
    "#9333EA",
    "#7C3AED",
    "#4F46E5",
]
MONTH_LABELS = [f"{month}월" for month in range(1, 13)]

st.title("Home")

logo_column, intro_column = st.columns(
    [1, 1],
    gap="large",
    vertical_alignment="center",
)
with logo_column:
    if logo_path.exists():
        st.image(str(logo_path), width="stretch")
    else:
        st.warning("assets/onflow_logo.png 파일을 찾을 수 없습니다.")
    st.caption(
        "온천천을 주 무대로 함께 달리고, 함께 성장하는 러닝 크루",
        text_alignment="center",
    )

with intro_column:
    st.subheader("ON:FLOW 소개")
    with st.container(border=True):
        st.markdown("#### :material/groups: 크루 안내")
        st.write("나이 제한 없이 각자의 페이스를 존중합니다.")

    with st.container(border=True):
        st.markdown("#### :material/directions_run: 러닝 안내")
        st.markdown(
            "- 정기 러닝: **매주 일요일**\n"
            "- 자유 러닝: **운영진·회원 자유 개설**\n"
            "- 메인 코스: **온천천**"
        )

    with st.container(border=True):
        st.markdown("#### :material/route: 함께하는 활동")
        st.markdown(
            "마라톤 · 트래킹 · 수영과 함께 시민공원, 광안리, "
            "해운대, 사직, 부산대 등 다양한 코스를 달립니다."
        )

    st.caption("좌측 메뉴에서 러닝 코스와 ON:FLOW의 다양한 기능을 확인해보세요.")

try:
    running_dashboard = get_running_distance_dashboard()
except Exception:
    st.warning("러닝 거리 현황을 불러오지 못했습니다. 잠시 후 다시 시도해주세요.")
else:
    dashboard_title, dashboard_filter = st.columns(
        [4, 1],
        vertical_alignment="bottom",
    )
    with dashboard_title:
        st.subheader("러닝 대시보드")
        st.caption("우리 크루가 함께 달린 거리를 한눈에 확인합니다.")
    with dashboard_filter:
        current_year = date.today().year
        available_years = sorted(
            set(running_dashboard.get("available_years") or []) | {current_year},
            reverse=True,
        )
        selected_year = st.selectbox(
            "연도",
            options=available_years,
            index=available_years.index(current_year),
            format_func=lambda year: f"{year}년",
            key="home_dashboard_year_v2",
        )

    yearly_months = build_monthly_distance_for_year(
        running_dashboard["monthly_distance"],
        selected_year,
    )
    selected_year_distance = sum(
        row["단체 거리 (km)"] for row in yearly_months
    )

    metric_column, chart_column = st.columns(
        [1, 3],
        gap="medium",
        vertical_alignment="top",
    )
    with metric_column:
        st.metric(
            "누적 단체 러닝 거리",
            f"{running_dashboard['total_distance_km']:,.1f} km",
            help="각 러닝의 거리 × 참석 인원을 모두 합산한 거리입니다.",
            border=True,
        )
        st.metric(
            f"{selected_year}년 단체 러닝 거리",
            f"{selected_year_distance:,.1f} km",
            help="선택한 연도의 거리 × 참석 인원을 합산한 거리입니다.",
            border=True,
        )

    with chart_column.container(border=True):
        st.markdown(f"#### {selected_year}년 월별 단체 러닝 거리")
        st.caption("거리 × 참석 인원을 합산했으며, 기록이 없는 월은 0km로 표시합니다.")
        monthly_distance = pd.DataFrame(yearly_months)
        chart = (
            alt.Chart(monthly_distance)
            .mark_bar(cornerRadiusTopLeft=7, cornerRadiusTopRight=7)
            .encode(
                x=alt.X(
                    "월:N",
                    sort=MONTH_LABELS,
                    title=None,
                    axis=alt.Axis(labelAngle=0),
                ),
                y=alt.Y(
                    "단체 거리 (km):Q",
                    title="단체 거리 (km)",
                    scale=alt.Scale(domainMin=0),
                ),
                color=alt.Color(
                    "월:N",
                    scale=alt.Scale(domain=MONTH_LABELS, range=MONTH_COLORS),
                    legend=None,
                ),
                tooltip=[
                    alt.Tooltip("월:N", title="월"),
                    alt.Tooltip(
                        "단체 거리 (km):Q",
                        title="단체 거리",
                        format=",.1f",
                    ),
                ],
            )
            .properties(height=340)
        )
        st.altair_chart(chart, width="stretch")
