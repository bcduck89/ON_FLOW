from __future__ import annotations

import hashlib
import importlib.util
import io
import mimetypes
import os
import re
import shutil
import uuid
from datetime import date, time
from pathlib import Path

import pandas as pd
import streamlit as st

from repositories.regular_run_repository import (
    REGULAR_RUN_IMAGE_BUCKET,
    find_regular_run_by_source_hash,
    insert_regular_run,
    list_regular_runs,
    remove_regular_run_image,
    update_regular_run as update_regular_run_row,
    upload_regular_run_image,
)
from repositories.member_repository import list_members
from utils.weekday_utils import get_korean_weekday


MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 25_000_000
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


class DuplicateRegularRunError(ValueError):
    """같은 캡처 이미지로 등록한 러닝 데이터가 이미 있을 때 발생한다."""


class RegularRunStorageError(RuntimeError):
    """러닝 데이터 또는 캡처 이미지 저장에 실패했을 때 발생한다."""


def has_paddle_ocr_runtime() -> bool:
    return bool(
        importlib.util.find_spec("paddleocr")
        and importlib.util.find_spec("paddle")
    )


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

    # 소모임 참석자 화면은 이름 아래에 상태 메시지나 이모지가 붙습니다.
    # 행 간격만으로 묶으면 다음 참석자의 이름이 앞사람 상태 메시지와 같은
    # 그룹으로 합쳐질 수 있으므로, 참석 인원 수를 아는 경우 큰 글자 행을
    # 이름으로 우선 선택합니다.
    if expected_count and len(content) >= expected_count:
        ranked = sorted(
            content,
            key=lambda item: (
                -int(item["height"]),
                int(item["top"]),
                int(item["left"]),
            ),
        )
        selected = sorted(
            ranked[:expected_count],
            key=lambda item: (int(item["top"]), int(item["left"])),
        )
        names = []
        for line in selected:
            name = _normalize_attendee_name(line["text"])
            if name not in names:
                names.append(name)
        if len(names) == expected_count:
            return names

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


def _paddle_result_to_lines(results) -> list[dict]:
    lines = []
    for result in results:
        texts = result["rec_texts"]
        scores = result["rec_scores"]
        boxes = result["rec_boxes"]
        for text, score, box in zip(texts, scores, boxes):
            text = _clean_line(str(text))
            if not text or float(score) < 0.35:
                continue
            left, top, right, bottom = (int(round(float(value))) for value in box)
            lines.append(
                {
                    "text": text,
                    "left": left,
                    "top": top,
                    "height": max(1, bottom - top),
                    "confidence": float(score),
                }
            )
    return sorted(lines, key=lambda line: (line["top"], line["left"]))


@st.cache_resource(show_spinner=False)
def _get_paddle_ocr():
    os.environ.setdefault("FLAGS_use_mkldnn", "0")
    os.environ.setdefault("PADDLE_PDX_MODEL_SOURCE", "BOS")
    os.environ.setdefault("PADDLE_PDX_DISABLE_MODEL_SOURCE_CHECK", "True")
    try:
        from paddleocr import PaddleOCR
    except ImportError as exc:
        raise OCRUnavailableError("PaddleOCR 한국어 모델이 설치되지 않았습니다.") from exc

    return PaddleOCR(
        text_detection_model_name="PP-OCRv5_mobile_det",
        text_recognition_model_name="korean_PP-OCRv5_mobile_rec",
        use_doc_orientation_classify=False,
        use_doc_unwarping=False,
        use_textline_orientation=False,
        enable_mkldnn=False,
        device="cpu",
    )


def _extract_regular_run_with_paddle(data: bytes, filename: str = "capture.png") -> dict:
    if not data:
        raise RegularRunImageError("이미지 파일이 비어 있습니다.")
    if len(data) > MAX_IMAGE_BYTES:
        raise RegularRunImageError("이미지는 최대 10MB까지 업로드할 수 있습니다.")

    try:
        import numpy as np
        from PIL import Image, UnidentifiedImageError

        image = Image.open(io.BytesIO(data))
        image.load()
        image = image.convert("RGB")
    except ImportError as exc:
        raise OCRUnavailableError("PaddleOCR 이미지 처리 패키지가 설치되지 않았습니다.") from exc
    except (UnidentifiedImageError, Image.DecompressionBombError, OSError) as exc:
        raise RegularRunImageError("PNG, JPG 또는 WEBP 이미지인지 확인해주세요.") from exc
    if image.width * image.height > MAX_IMAGE_PIXELS:
        raise RegularRunImageError("이미지 해상도가 너무 큽니다. 2,500만 픽셀 이하로 줄여주세요.")

    try:
        results = _get_paddle_ocr().predict(np.asarray(image))
        ocr_lines = _paddle_result_to_lines(results)
    except OCRUnavailableError:
        raise
    except Exception as exc:
        raise OCRUnavailableError("PaddleOCR 한국어 모델을 실행하지 못했습니다.") from exc

    raw_text = "\n".join(line["text"] for line in ocr_lines)
    if not raw_text.strip():
        raise RegularRunImageError("이미지에서 글자를 찾지 못했습니다. 더 선명한 캡처를 사용해주세요.")
    result = parse_regular_run_text(raw_text, filename=filename, ocr_lines=ocr_lines)
    result["recognition_method"] = "PaddleOCR PP-OCRv5 한국어 모델"
    return result


def _extract_regular_run_with_tesseract(data: bytes, filename: str = "capture.png") -> dict:
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
    result = parse_regular_run_text(raw_text, filename=filename, ocr_lines=ocr_lines)
    result["recognition_method"] = "Tesseract OCR"
    return result


def extract_regular_run_from_image(data: bytes, filename: str = "capture.png") -> dict:
    try:
        return _extract_regular_run_with_paddle(data, filename)
    except (OCRUnavailableError, RegularRunImageError) as paddle_error:
        try:
            result = _extract_regular_run_with_tesseract(data, filename)
        except (OCRUnavailableError, RegularRunImageError):
            raise paddle_error
        result["recognition_warning"] = (
            "PaddleOCR 한국어 모델을 사용할 수 없어 Tesseract OCR로 대신 읽었습니다."
        )
        return result


def default_run_type_for_date(run_date: date | None) -> str:
    return "정기" if run_date and run_date.weekday() == 6 else "자유"


def _member_identity_key(value: object) -> str:
    return re.sub(r"\s+", "", str(value or "")).casefold()


def match_attendee_names_to_members(
    attendee_names: list[str],
    members: pd.DataFrame | None = None,
) -> list[str]:
    """OCR 이름을 회원 이름·닉네임과 대조해 실제 이름으로 변환한다."""
    if not attendee_names:
        return []

    members = list_members() if members is None else members
    if members.empty:
        return attendee_names

    candidates: dict[str, set[str]] = {}
    for _, member in members.iterrows():
        actual_name = str(member.get("name", "")).strip()
        if not actual_name:
            continue
        for identity in (actual_name, member.get("nickname", "")):
            key = _member_identity_key(identity)
            if key:
                candidates.setdefault(key, set()).add(actual_name)

    unique_matches = {
        key: next(iter(names))
        for key, names in candidates.items()
        if len(names) == 1
    }
    return [
        unique_matches.get(_member_identity_key(name), name)
        for name in attendee_names
    ]


def get_regular_run_records() -> list[dict]:
    return list_regular_runs()


def get_regular_run_list() -> pd.DataFrame:
    rows = list_regular_runs()
    columns = [
        "구분",
        "날짜",
        "요일",
        "시간",
        "거리 (km)",
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
            "run_type": "구분",
            "run_date": "날짜",
            "weekday": "요일",
            "start_time": "시간",
            "distance_km": "거리 (km)",
            "participant_count": "총 참석인원",
            "attendee_names": "참석자 명단",
        }
    )
    for column in columns:
        if column not in view.columns:
            view[column] = ""
    return view[columns]


def update_regular_run(
    *,
    regular_run_id: int,
    run_type: str,
    run_date: date,
    start_time: time | None,
    distance_km: float,
    participant_count: int,
    attendee_names: list[str],
) -> dict:
    run_type = (run_type or "").strip()
    if run_type not in {"정기", "자유"}:
        raise ValueError("러닝 구분은 정기 또는 자유여야 합니다.")
    if not run_date:
        raise ValueError("러닝 날짜를 입력해주세요.")
    if distance_km < 0:
        raise ValueError("거리는 0km 이상이어야 합니다.")

    attendee_names = [name.strip() for name in attendee_names if name.strip()]
    if participant_count != len(attendee_names):
        raise ValueError("총 참석인원과 참석자 명단의 인원수가 일치해야 합니다.")

    values = {
        "run_type": run_type,
        "title": f"{run_date:%Y-%m-%d} {run_type} 러닝",
        "run_date": str(run_date),
        "start_time": start_time.strftime("%H:%M:%S") if start_time else None,
        "distance_km": round(float(distance_km), 2),
        "participant_count": int(participant_count),
        "attendee_names": attendee_names,
    }
    return update_regular_run_row(int(regular_run_id), values)


def create_regular_run(
    *,
    run_type: str,
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
    run_type = (run_type or "").strip()
    if run_type not in {"정기", "자유"}:
        raise ValueError("러닝 구분은 정기 또는 자유여야 합니다.")
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

    source_hash = hashlib.sha256(source_image_data).hexdigest()
    if find_regular_run_by_source_hash(source_hash):
        raise DuplicateRegularRunError("이미 등록한 캡처 이미지입니다.")

    safe_suffix = Path(source_image_name).suffix.lower()
    if safe_suffix not in {".png", ".jpg", ".jpeg", ".webp"}:
        safe_suffix = ".jpg"
    content_type = mimetypes.types_map.get(safe_suffix, "image/jpeg")
    image_path = (
        f"{run_date:%Y/%m}/{source_hash[:16]}-{uuid.uuid4().hex}{safe_suffix}"
    )

    row = {
        "run_type": run_type,
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
        "source_image_bucket": REGULAR_RUN_IMAGE_BUCKET,
        "source_image_path": image_path,
        "source_image_mime_type": content_type,
        "source_image_size": len(source_image_data),
        "raw_ocr_text": raw_ocr_text.strip()[:10_000],
        "source_hash": source_hash,
        "created_by": created_by.strip()[:80] or "admin",
    }
    try:
        upload_regular_run_image(
            path=image_path,
            data=source_image_data,
            content_type=content_type,
        )
    except Exception as exc:
        message = str(exc).lower()
        if "payload too large" in message or "maximum allowed size" in message:
            raise RegularRunStorageError(
                "캡처 이미지가 너무 큽니다. 10MB 이하 이미지로 다시 시도해주세요."
            ) from exc
        if "bucket not found" in message or "not found" in message:
            raise RegularRunStorageError(
                "캡처 이미지 저장소가 없습니다. Supabase에서 007 SQL을 실행해주세요."
            ) from exc
        if "unauthorized" in message or "forbidden" in message or "403" in message:
            raise RegularRunStorageError(
                "캡처 이미지 저장 권한이 없습니다. Streamlit의 Supabase 관리자 Secret을 확인해주세요."
            ) from exc
        raise RegularRunStorageError(
            "캡처 이미지를 Supabase Storage에 저장하지 못했습니다. 잠시 후 다시 시도해주세요."
        ) from exc
    try:
        return insert_regular_run(row)
    except Exception as exc:
        try:
            remove_regular_run_image(image_path)
        except Exception:
            pass
        message = str(exc).lower()
        if "23505" in message or "duplicate" in message:
            raise DuplicateRegularRunError("이미 등록한 캡처 이미지입니다.") from exc
        if "pgrst204" in message or "column" in message or "relation" in message:
            raise RegularRunStorageError(
                "러닝 데이터베이스 구조가 최신 버전이 아닙니다. Supabase에서 007 SQL을 실행해주세요."
            ) from exc
        raise RegularRunStorageError(
            "러닝 정보를 데이터베이스에 저장하지 못했습니다. 잠시 후 다시 시도해주세요."
        ) from exc
