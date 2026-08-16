from __future__ import annotations

import hashlib
import io
import os
import re
import shutil
from datetime import date, time
from pathlib import Path

import pandas as pd

from repositories.regular_run_repository import insert_regular_run, list_regular_runs


MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
KOREAN_WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")
ATTENDEE_IGNORE_WORDS = {
    "참석자",
    "참가자",
    "정모",
    "카카오톡으로 정모 공유하기",
    "화이팅",
    "파이팅",
    "참석",
    "불참",
    "미정",
}


class RegularRunImageError(ValueError):
    """업로드 이미지가 OCR 처리에 적합하지 않을 때 발생한다."""


class OCRUnavailableError(RuntimeError):
    """OCR 실행 환경이 준비되지 않았을 때 발생한다."""


def _clean_line(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip(" -|•·")


def _normalize_attendee_name(value: str) -> str:
    value = _clean_line(value)
    compact = value.replace(" ", "")
    if 2 <= len(compact) <= 8 and re.fullmatch(r"[가-힣]+", compact):
        return compact
    return value


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

    short_date = re.search(r"(?<!\d)(\d{1,2})[./](\d{1,2})일?(?!\d)", text)
    if short_date:
        try:
            return date(
                reference_date.year,
                int(short_date.group(1)),
                int(short_date.group(2)),
            )
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


def get_korean_weekday(value: date | str | None) -> str:
    if value in (None, ""):
        return ""
    try:
        parsed = pd.to_datetime(value).date()
    except (TypeError, ValueError):
        return ""
    return f"{KOREAN_WEEKDAYS[parsed.weekday()]}요일"


def _extract_participant_count(text: str) -> int:
    patterns = (
        r"(?:참석자|참가자)\s*\(\s*(\d+)\s*명\s*\)",
        r"(?:참여|참가|인원)?\s*(\d+)\s*명",
    )
    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            return int(match.group(1))
    return 0


def _is_attendee_name(value: str) -> bool:
    value = _normalize_attendee_name(value)
    if not value or value in ATTENDEE_IGNORE_WORDS:
        return False
    if any(word in value for word in ("공유하기", "오전", "오후", "참석자", "참가자")):
        return False
    if re.search(r"\d{1,2}[:/.]\d{1,2}|\d+명", value):
        return False
    return bool(re.fullmatch(r"[가-힣A-Za-z0-9_. ]{2,20}", value))


def _extract_attendees_from_text(lines: list[str], expected_count: int) -> list[str]:
    header_index = -1
    for index, line in enumerate(lines):
        if re.search(r"(?:정모\s*)?(?:참석자|참가자).*\d+\s*명", line):
            header_index = index

    candidates = []
    for line in lines[header_index + 1 :]:
        name = _normalize_attendee_name(line)
        if _is_attendee_name(name) and name not in candidates:
            candidates.append(name)
        if expected_count and len(candidates) >= expected_count:
            break
    return candidates


def _extract_attendees_from_layout(
    ocr_lines: list[dict],
    expected_count: int,
) -> list[str]:
    header_top = -1
    for line in ocr_lines:
        if re.search(r"(?:정모\s*)?(?:참석자|참가자).*\d+\s*명", line["text"]):
            header_top = max(header_top, int(line["top"]))

    content = [
        line
        for line in ocr_lines
        if int(line["top"]) > header_top and _is_attendee_name(line["text"])
    ]
    if not content:
        return []

    heights = sorted(max(1, int(line["height"])) for line in content)
    median_height = heights[len(heights) // 2]
    new_person_gap = max(24, median_height * 2.2)
    groups: list[list[dict]] = []

    for line in sorted(content, key=lambda item: (int(item["top"]), int(item["left"]))):
        if not groups:
            groups.append([line])
            continue
        previous_top = int(groups[-1][-1]["top"])
        if int(line["top"]) - previous_top > new_person_gap:
            groups.append([line])
        else:
            groups[-1].append(line)

    names = []
    for group in groups:
        name = _normalize_attendee_name(group[0]["text"])
        if name not in names:
            names.append(name)
        if expected_count and len(names) >= expected_count:
            break
    return names


def parse_regular_run_text(
    raw_text: str,
    filename: str = "",
    reference_date: date | None = None,
    ocr_lines: list[dict] | None = None,
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
    participant_count = _extract_participant_count(raw_text)
    pace_match = re.search(
        r"(?:페이스|pace)\s*[:：]?\s*([^\n]+)",
        raw_text,
        re.IGNORECASE,
    )

    run_date = _extract_date(raw_text, reference_date)
    attendee_names = (
        _extract_attendees_from_layout(ocr_lines, participant_count)
        if ocr_lines
        else []
    )
    if not attendee_names:
        attendee_names = _extract_attendees_from_text(lines, participant_count)

    return {
        "title": title[:100],
        "run_date": run_date,
        "weekday": get_korean_weekday(run_date),
        "start_time": _extract_time(raw_text),
        "location": _labeled_value(lines, ("장소", "집결지", "출발지"))[:150],
        "course_name": _labeled_value(lines, ("코스", "경로"))[:150],
        "distance_km": (
            float(distance_match.group(1).replace(",", "."))
            if distance_match
            else 0.0
        ),
        "target_pace": _clean_line(pace_match.group(1))[:50] if pace_match else "",
        "participant_count": participant_count,
        "attendee_names": attendee_names,
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
        if not shutil.which("tesseract"):
            for candidate in (
                Path(r"C:\Program Files\Tesseract-OCR\tesseract.exe"),
                Path(r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe"),
            ):
                if candidate.exists():
                    pytesseract.pytesseract.tesseract_cmd = str(candidate)
                    break

        tessdata_config = ""
        local_tessdata = Path(os.getenv("LOCALAPPDATA", "")) / "Tesseract-OCR" / "tessdata"
        if (local_tessdata / "kor.traineddata").exists():
            os.environ["TESSDATA_PREFIX"] = str(local_tessdata)

        languages = set(pytesseract.get_languages(config=tessdata_config))
        if "kor" not in languages:
            raise OCRUnavailableError(
                "Tesseract 한국어 언어 데이터(kor)가 없습니다. "
                "Windows 설치 프로그램에서 Korean 언어를 추가해주세요."
            )
        ocr_data = pytesseract.image_to_data(
            processed,
            lang="kor+eng" if "eng" in languages else "kor",
            config=f"{tessdata_config} --oem 3 --psm 11".strip(),
            output_type=pytesseract.Output.DICT,
            timeout=30,
        )
    except OCRUnavailableError:
        raise
    except (pytesseract.TesseractNotFoundError, RuntimeError) as exc:
        raise OCRUnavailableError(
            "Tesseract OCR 실행 파일을 찾지 못했습니다. Windows에서는 "
            "Tesseract-OCR과 Korean 언어 데이터를 설치한 뒤 앱을 다시 실행해주세요."
        ) from exc

    grouped_lines: dict[tuple[int, int, int], dict] = {}
    for index, text in enumerate(ocr_data["text"]):
        text = _clean_line(text)
        if not text:
            continue
        key = (
            int(ocr_data["block_num"][index]),
            int(ocr_data["par_num"][index]),
            int(ocr_data["line_num"][index]),
        )
        line = grouped_lines.setdefault(
            key,
            {
                "words": [],
                "left": int(ocr_data["left"][index]),
                "top": int(ocr_data["top"][index]),
                "height": int(ocr_data["height"][index]),
            },
        )
        line["words"].append(text)
        line["left"] = min(line["left"], int(ocr_data["left"][index]))
        line["top"] = min(line["top"], int(ocr_data["top"][index]))
        line["height"] = max(line["height"], int(ocr_data["height"][index]))

    ocr_lines = [
        {
            "text": _clean_line(" ".join(line["words"])),
            "left": line["left"],
            "top": line["top"],
            "height": line["height"],
        }
        for line in grouped_lines.values()
    ]
    ocr_lines.sort(key=lambda line: (line["top"], line["left"]))
    raw_text = "\n".join(line["text"] for line in ocr_lines)

    if not raw_text.strip():
        raise RegularRunImageError("이미지에서 글자를 찾지 못했습니다. 더 선명한 캡처를 사용해주세요.")
    return parse_regular_run_text(raw_text, filename=filename, ocr_lines=ocr_lines)


def get_regular_run_list() -> pd.DataFrame:
    rows = list_regular_runs()
    columns = [
        "날짜",
        "요일",
        "시간",
        "총 참석인원",
        "참석자 명단",
    ]
    if not rows:
        return pd.DataFrame(columns=columns)

    view = pd.DataFrame(rows)
    view["weekday"] = view["run_date"].apply(get_korean_weekday)
    view["attendee_names"] = view["attendee_names"].apply(
        lambda names: ", ".join(names) if isinstance(names, list) else str(names or "")
    )
    view = view.rename(
        columns={
            "run_date": "날짜",
            "weekday": "요일",
            "start_time": "시간",
            "participant_count": "총 참석인원",
            "attendee_names": "참석자 명단",
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
    attendee_names: list[str],
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
    attendee_names = [name.strip() for name in attendee_names if name.strip()]
    if participant_count != len(attendee_names):
        raise ValueError("총 참석인원과 참석자 명단의 인원수가 일치해야 합니다.")

    row = {
        "title": title[:100],
        "run_date": str(run_date),
        "start_time": start_time.strftime("%H:%M:%S") if start_time else None,
        "location": location.strip()[:150],
        "course_name": course_name.strip()[:150],
        "distance_km": round(float(distance_km), 2),
        "target_pace": target_pace.strip()[:50],
        "participant_count": int(participant_count),
        "attendee_names": attendee_names,
        "memo": memo.strip()[:500],
        "source_image_name": Path(source_image_name).name[:255],
        "raw_ocr_text": raw_ocr_text.strip()[:10_000],
        "source_hash": hashlib.sha256(source_image_data).hexdigest(),
        "created_by": created_by.strip()[:80] or "admin",
    }
    return insert_regular_run(row)
