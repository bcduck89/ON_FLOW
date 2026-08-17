from __future__ import annotations

import base64
import hashlib
import math
from datetime import date, datetime, timezone
from pathlib import Path
from xml.etree import ElementTree

from repositories.running_course_repository import (
    delete_course,
    insert_course,
    list_courses,
    update_course,
)
from services.auth_service import verify_admin_password


MAX_GPX_BYTES = 5 * 1024 * 1024
MAX_STORED_POINTS = 5_000


class GPXParseError(ValueError):
    """Raised when an uploaded GPX file is invalid or unsupported."""


def _local_name(tag: str) -> str:
    return tag.rsplit("}", 1)[-1]


def _direct_children(element, name: str):
    return [child for child in element if _local_name(child.tag) == name]


def _parse_point(
    element,
) -> tuple[float, float, float | None, datetime | None] | None:
    try:
        latitude = float(element.attrib["lat"])
        longitude = float(element.attrib["lon"])
    except (KeyError, TypeError, ValueError):
        return None

    if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
        return None

    elevation = None
    recorded_at = None
    for child in element:
        if _local_name(child.tag) == "ele" and child.text:
            try:
                elevation = float(child.text)
            except ValueError:
                pass
        elif _local_name(child.tag) == "time" and child.text:
            try:
                recorded_at = datetime.fromisoformat(
                    child.text.strip().replace("Z", "+00:00")
                )
                if recorded_at.tzinfo is None:
                    recorded_at = recorded_at.replace(tzinfo=timezone.utc)
            except ValueError:
                pass

    return longitude, latitude, elevation, recorded_at


def _haversine_meters(first, second) -> float:
    lon1, lat1 = first[:2]
    lon2, lat2 = second[:2]
    radius = 6_371_000

    lat1_rad = math.radians(lat1)
    lat2_rad = math.radians(lat2)
    delta_lat = math.radians(lat2 - lat1)
    delta_lon = math.radians(lon2 - lon1)

    value = (
        math.sin(delta_lat / 2) ** 2
        + math.cos(lat1_rad)
        * math.cos(lat2_rad)
        * math.sin(delta_lon / 2) ** 2
    )
    return 2 * radius * math.asin(min(1, math.sqrt(value)))


def _simplify_segments(segments, max_points: int = MAX_STORED_POINTS):
    point_count = sum(len(segment) for segment in segments)
    if point_count <= max_points:
        return segments

    step = math.ceil(point_count / max_points)
    simplified = []
    for segment in segments:
        sampled = segment[::step]
        if sampled[-1] != segment[-1]:
            sampled.append(segment[-1])
        if len(sampled) >= 2:
            simplified.append(sampled)
    return simplified


def _find_course_name(root, filename: str) -> str:
    for element_name in ("trk", "rte", "metadata"):
        for element in root.iter():
            if _local_name(element.tag) != element_name:
                continue
            for child in element:
                if _local_name(child.tag) == "name" and child.text:
                    return child.text.strip()[:80]
    return Path(filename).stem[:80] or "러닝 코스"


def parse_gpx(data: bytes, filename: str = "course.gpx") -> dict:
    if not data:
        raise GPXParseError("GPX 파일이 비어 있습니다.")
    if len(data) > MAX_GPX_BYTES:
        raise GPXParseError("GPX 파일은 최대 5MB까지 업로드할 수 있습니다.")

    header = data[:4096].upper()
    if b"<!DOCTYPE" in header or b"<!ENTITY" in header:
        raise GPXParseError("외부 엔티티가 포함된 GPX 파일은 지원하지 않습니다.")

    try:
        root = ElementTree.fromstring(data)
    except ElementTree.ParseError as exc:
        raise GPXParseError("올바른 GPX XML 파일이 아닙니다.") from exc

    if _local_name(root.tag).lower() != "gpx":
        raise GPXParseError("GPX 형식의 파일만 업로드할 수 있습니다.")

    segments = []
    for track in (item for item in root.iter() if _local_name(item.tag) == "trk"):
        for track_segment in _direct_children(track, "trkseg"):
            points = [
                point
                for element in _direct_children(track_segment, "trkpt")
                if (point := _parse_point(element)) is not None
            ]
            if len(points) >= 2:
                segments.append(points)

    for route in (item for item in root.iter() if _local_name(item.tag) == "rte"):
        points = [
            point
            for element in _direct_children(route, "rtept")
            if (point := _parse_point(element)) is not None
        ]
        if len(points) >= 2:
            segments.append(points)

    if not segments:
        raise GPXParseError("지도에 표시할 트랙 포인트가 2개 이상 필요합니다.")

    distance_meters = 0.0
    elevation_gain = 0.0
    timestamps = []
    for segment in segments:
        timestamps.extend(point[3] for point in segment if point[3] is not None)
        for previous, current in zip(segment, segment[1:]):
            distance_meters += _haversine_meters(previous, current)
            if previous[2] is not None and current[2] is not None:
                elevation_gain += max(0.0, current[2] - previous[2])

    started_at = min(timestamps) if timestamps else None
    ended_at = max(timestamps) if timestamps else None
    duration_seconds = (
        max(0, round((ended_at - started_at).total_seconds()))
        if started_at and ended_at
        else None
    )

    stored_segments = _simplify_segments(segments)
    paths = [
        [[round(point[0], 7), round(point[1], 7)] for point in segment]
        for segment in stored_segments
    ]
    flat_points = [point for segment in paths for point in segment]

    return {
        "name": _find_course_name(root, filename),
        "distance_km": round(distance_meters / 1000, 2),
        "elevation_gain_m": round(elevation_gain),
        "point_count": sum(len(segment) for segment in segments),
        "run_date": started_at.date().isoformat() if started_at else None,
        "started_at": started_at.isoformat() if started_at else None,
        "ended_at": ended_at.isoformat() if ended_at else None,
        "duration_seconds": duration_seconds,
        "paths": paths,
        "center_latitude": sum(point[1] for point in flat_points) / len(flat_points),
        "center_longitude": sum(point[0] for point in flat_points) / len(flat_points),
        "source_hash": hashlib.sha256(data).hexdigest(),
        "gpx_raw_base64": base64.b64encode(data).decode("ascii"),
        "gpx_filename": (Path(filename).name[:255] or "course.gpx"),
        "gpx_size_bytes": len(data),
    }


def get_running_courses() -> list[dict]:
    return list_courses()


def register_running_course(
    name: str,
    run_date: date,
    location_name: str,
    description: str,
    tags: list[str],
    uploaded_by: str,
    course: dict,
) -> dict:
    clean_name = name.strip()
    if not clean_name:
        raise ValueError("코스 이름을 입력해 주세요.")

    row = {
        "name": clean_name[:80],
        "run_date": run_date.isoformat(),
        "started_at": course.get("started_at"),
        "ended_at": course.get("ended_at"),
        "duration_seconds": course.get("duration_seconds"),
        "description": description.strip()[:500],
        "location_name": location_name.strip()[:100],
        "tags": [tag.strip()[:30] for tag in tags if tag.strip()][:10],
        "distance_km": course["distance_km"],
        "elevation_gain_m": course["elevation_gain_m"],
        "point_count": course["point_count"],
        "paths": course["paths"],
        "source_hash": course["source_hash"],
        "gpx_raw_base64": course["gpx_raw_base64"],
        "gpx_filename": course["gpx_filename"],
        "gpx_size_bytes": course["gpx_size_bytes"],
        "uploaded_by": uploaded_by.strip()[:80] or "admin",
    }
    return insert_course(row)


def update_running_course(
    activity_id: int,
    name: str,
    run_date: date,
    location_name: str,
    description: str,
    tags: list[str],
) -> dict:
    try:
        course_id = int(activity_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("수정할 코스 ID가 올바르지 않습니다.") from exc
    if course_id <= 0:
        raise ValueError("수정할 코스 ID가 올바르지 않습니다.")

    clean_name = name.strip()
    if not clean_name:
        raise ValueError("코스 이름을 입력해 주세요.")

    row = {
        "name": clean_name[:80],
        "run_date": run_date.isoformat(),
        "location_name": location_name.strip()[:100],
        "description": description.strip()[:500],
        "tags": [tag.strip()[:30] for tag in tags if tag.strip()][:10],
    }
    return update_course(course_id, row)


def delete_running_course(activity_id: int, admin_password: str) -> None:
    if not verify_admin_password(admin_password):
        raise PermissionError("관리자 비밀번호가 올바르지 않습니다.")

    try:
        course_id = int(activity_id)
    except (TypeError, ValueError) as exc:
        raise ValueError("삭제할 코스 ID가 올바르지 않습니다.") from exc
    if course_id <= 0:
        raise ValueError("삭제할 코스 ID가 올바르지 않습니다.")

    try:
        delete_course(course_id)
    except RuntimeError:
        raise
    except Exception as exc:
        raise RuntimeError(
            "Supabase가 코스 삭제 요청을 거부했습니다. "
            "등록된 관리자 Secret 키가 유효한지 확인해 주세요."
        ) from exc
