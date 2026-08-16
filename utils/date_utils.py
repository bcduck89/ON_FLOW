import pandas as pd
from datetime import date


def date_input_bounds(reference_date: date | None = None) -> tuple[date, date]:
    reference_date = reference_date or date.today()
    return (
        date(reference_date.year - 70, 1, 1),
        date(reference_date.year + 10, 12, 31),
    )


def calculate_age(birth_date) -> int | None:
    if birth_date in ["", None]:
        return None

    try:
        birth = pd.to_datetime(birth_date).date()
    except Exception:
        return None

    today = date.today()

    age = today.year - birth.year

    if (today.month, today.day) < (birth.month, birth.day):
        age -= 1

    return age
