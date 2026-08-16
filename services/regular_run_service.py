from __future__ import annotations

import hashlib
import io
import re
from datetime import date, time
from pathlib import Path

import pandas as pd

from repositories.regular_run_repository import insert_regular_run, list_regular_runs


MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000


class RegularRunImageError(ValueError):
    """업로드 이미지가 OCR 처리에 적합하지 않을 때 발생한다."""


class OCRUnavailableError(RuntimeError):
    """OCR 실행 환경이 준비되지 않았을 때 발생한다."""


def _clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" -|•·")


def _labeled_value(lines: list[str], labels: tuple[str, ...]) -> str:
    label_pattern = "|".join(re.escape(label) for label in labels)
    pattern = re.compile(rf"^(?:{label_pattern})\s*[:：]?\s*(.+)$", re.IGNORECASE)
    for line in lines:
        match = pattern.match(line)
        if match:
            return _clean_line(match.group(1))
    return ""


def _extract_date(text: str, reference_date: date) -> date | None:
    numeric = re.search(r"\b(20\d{2})[.\-/년]\s*(\d{1,2})[.\-/월]\s*(\d{1,2})일?\b", text)
    if numeric:
        try:
            return date(*(int(value) for value in numeric.groups()))
        except ValueError:
            pass

    korean = re.search(r"(?:(20\d{2})년\s*)?(\d{1,2})월\s*(\d{1,2})일", text)
    if korean:
        year = int(korean.group(1) or reference_date.year)
        try:
            return date(year, int(korean.group(2)), int(korean.group(3)))
        except ValueError:
            pass
    return None


def _extract_time(text: str) -> time | None:
    meridiem_match = re.search(
        r"(오전|오후)\s*(\d{1,2})(?::|시)\s*(\d{1,2})?분?",
        text,
    )
    if meridiem_match:
        hour = int(meridiem_match.group(2)) % 12
        if meridiem_match.group(1) == "오후":
            hour += 12
        minute = int(meridiem_match.group(3) or 0)
        if minute < 60:
            return time(hour, minute)

    clock_match = re.search(r"(?<!\d)([01]?\d|2[0-3]):([0-5]\d)(?!\d)", text)
    if clock_match:
        return time(int(clock_match.group(1)), int(clock_match.group(2)))
    return None


def parse_regular_run_text(
    raw_text: str,
    filename: str = "",
    reference_date: date | None = None,
) -> dict:
    reference_date = reference_date or date.today()
    lines = [_clean_line(line) for line in raw_text.splitlines() if _clean_line(line)]

    title = _labeled_value(lines, ("제목", "일정", "러닝명", "정기 러닝"))
    if not title:
        ignored = re.compile(r"^(날짜|일시|시간|장소|집결지|코스|거리|페이스|인원)\b")
        title = next((line for line in lines if not ignored.match(line)), "")
    if not title:
        title = Path(filename).stem or "정기 러닝"

    distance_match = re.search(r"(\d+(?:[.,]\d+)?)\s*(?:km|킬로미터)", raw_text, re.IGNORECASE)
    participant_match = re.search(r"(?:참여|참가|인원)?\s*(\d+)\s*명", raw_text)
    pace_match = re.search(
        r"(?:페이스|pace)\s*[:：]?\s*([^\n]+)",
        raw_text,
        re.IGNORECASE,
    )

    return {
        "title": title[:100],
        "run_date": _extract_date(raw_text, reference_date),
        "start_time": _extract_time(raw_text),
        "location": _labeled_value(lines, ("장소", "집결지", "출발지"))[:150],
        "course_name": _labeled_value(lines, ("코스", "경로"))[:150],
        "distance_km": (
            float(distance_match.group(1).replace(",", "."))
            if distance_match
            else 0.0
        ),
        "target_pace": _clean_line(pace_match.group(1))[:50] if pace_match else "",
        "participant_count": int(participant_match.group(1)) if participant_match else 0,
        "memo": "",
        "raw_ocr_text": raw_text.strip(),
    }


def extract_regular_run_from_image(data: bytes, filename: str = "capture.png") -> dict:
    if not data:
        raise RegularRunImageError("이미지 파일이 비어 있습니다.")
    if len(data) > MAX_IMAGE_BYTES:
        raise RegularRunImageError("이미지는 최대 10MB까지 업로드할 수 있습니다.")

    try:
        from PIL import Image, ImageEnhance, ImageFilter, ImageOps, UnidentifiedImageError
        import pytesseract
    except ImportError as exc:
        raise OCRUnavailableError("OCR Python 패키지가 설치되지 않았습니다.") from exc

    try:
        image = Image.open(io.BytesIO(data))
        image.load()
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise RegularRunImageError("PNG, JPG 또는 WEBP 이미지인지 확인해주세요.") from exc

    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise RegularRunImageError("이미지 해상도가 너무 큽니다. 2,500만 픽셀 이하로 줄여주세요.")

    processed = ImageOps.grayscale(image)
    if processed.width < 1800:
        scale = min(3, max(2, round(1800 / max(processed.width, 1))))
        processed = processed.resize(
            (processed.width * scale, processed.height * scale),
            Image.Resampling.LANCZOS,
        )
    processed = ImageOps.autocontrast(processed)
    processed = ImageEnhance.Contrast(processed).enhance(1.4)
    processed = processed.filter(ImageFilter.SHARPEN)

    try:
        languages = set(pytesseract.get_languages(config=""))
        if "kor" not in languages:
            raise OCRUnavailableError("Tesseract 한국어 언어 데이터가 설치되지 않았습니다.")
        raw_text = pytesseract.image_to_string(
            processed,
            lang="kor+eng" if "eng" in languages else "kor",
            config="--oem 3 --psm 6",
            timeout=30,
        )
    except OCRUnavailableError:
        raise
    except (pytesseract.TesseractNotFoundError, RuntimeError) as exc:
        raise OCRUnavailableError(
            "Tesseract OCR을 실행할 수 없습니다. 서버 설치 상태를 확인해주세요."
        ) from exc

    if not raw_text.strip():
        raise RegularRunImageError("이미지에서 글자를 찾지 못했습니다. 더 선명한 캡처를 사용해주세요.")
    return parse_regular_run_text(raw_text, filename=filename)


def get_regular_run_list() -> pd.DataFrame:
    rows = list_regular_runs()
    columns = [
        "날짜",
        "시간",
        "정기러닝명",
        "장소",
        "코스",
        "거리 (km)",
        "목표 페이스",
        "참여인원",
        "비고",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)

    view = pd.DataFrame(rows).rename(
        columns={
            "run_date": "날짜",
            "start_time": "시간",
            "title": "정기러닝명",
            "location": "장소",
            "course_name": "코스",
            "distance_km": "거리 (km)",
            "target_pace": "목표 페이스",
            "participant_count": "참여인원",
            "memo": "비고",
        }
    )
    for column in columns:
        if column not in view.columns:
            view[column] = ""
    return view[columns]


def create_regular_run(
    *,
    title: str,
    run_date: date,
    start_time: time | None,
    location: str,
    course_name: str,
    distance_km: float,
    target_pace: str,
    participant_count: int,
    memo: str,
    source_image_name: str,
    source_image_data: bytes,
    raw_ocr_text: str,
    created_by: str,
) -> dict:
    title = title.strip()
    if not title:
        raise ValueError("정기러닝명을 입력해주세요.")
    if not run_date:
        raise ValueError("러닝 날짜를 입력해주세요.")
    if distance_km < 0:
        raise ValueError("거리는 0 이상이어야 합니다.")
    if participant_count < 0:
        raise ValueError("참여인원은 0명 이상이어야 합니다.")

    row = {
        "title": title[:100],
        "run_date": str(run_date),
        "start_time": start_time.strftime("%H:%M:%S") if start_time else None,
        "location": location.strip()[:150],
        "course_name": course_name.strip()[:150],
        "distance_km": round(float(distance_km), 2),
        "target_pace": target_pace.strip()[:50],
        "participant_count": int(participant_count),
        "memo": memo.strip()[:500],
        "source_image_name": Path(source_image_name).name[:255],
        "raw_ocr_text": raw_ocr_text.strip()[:10_000],
        "source_hash": hashlib.sha256(source_image_data).hexdigest(),
        "created_by": created_by.strip()[:80] or "admin",
    }
    return insert_regular_run(row)
