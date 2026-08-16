from __future__ import annotations

from datetime import date

import pandas as pd


KOREAN_WEEKDAYS = ("월", "화", "수", "목", "금", "토", "일")


def get_korean_weekday(value: date | str | None) -> str:
    """Return the Korean weekday label for a date-like value."""
    if value in (None, ""):
        return ""
    try:
        parsed = pd.to_datetime(value).date()
    except (TypeError, ValueError):
        return ""
    return f"{KOREAN_WEEKDAYS[parsed.weekday()]}요일"
