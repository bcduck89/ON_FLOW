from __future__ import annotations

from collections import defaultdict
from datetime import date, datetime

from repositories.regular_run_repository import list_regular_run_distance_rows


def _parse_run_date(value: object) -> date | None:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return date.fromisoformat(str(value)[:10])
    except (TypeError, ValueError):
        return None


def build_running_distance_dashboard(rows: list[dict]) -> dict:
    monthly_distance: dict[str, float] = defaultdict(float)
    total_distance_km = 0.0
    available_years: set[int] = set()

    for row in rows:
        run_date = _parse_run_date(row.get("run_date"))
        try:
            distance_km = max(float(row.get("distance_km") or 0), 0.0)
            participant_count = max(int(row.get("participant_count") or 0), 0)
        except (TypeError, ValueError):
            continue
        if run_date is None:
            continue

        group_distance_km = distance_km * participant_count
        total_distance_km += group_distance_km
        monthly_distance[run_date.strftime("%Y-%m")] += group_distance_km
        available_years.add(run_date.year)

    monthly_rows = [
        {
            "월": month,
            "단체 거리 (km)": round(distance, 2),
        }
        for month, distance in sorted(monthly_distance.items())
    ]
    return {
        "total_distance_km": round(total_distance_km, 2),
        "monthly_distance": monthly_rows,
        "available_years": sorted(available_years, reverse=True),
    }


def build_monthly_distance_for_year(
    monthly_distance: list[dict],
    selected_year: int,
) -> list[dict]:
    distance_by_month = {
        str(row.get("월")): float(row.get("단체 거리 (km)") or 0)
        for row in monthly_distance
        if str(row.get("월", "")).startswith(f"{selected_year:04d}-")
    }
    return [
        {
            "월": f"{month}월",
            "월 번호": month,
            "단체 거리 (km)": round(
                distance_by_month.get(f"{selected_year:04d}-{month:02d}", 0.0),
                2,
            ),
        }
        for month in range(1, 13)
    ]


def get_running_distance_dashboard() -> dict:
    return build_running_distance_dashboard(list_regular_run_distance_rows())
