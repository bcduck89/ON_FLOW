import pandas as pd
from datetime import date


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