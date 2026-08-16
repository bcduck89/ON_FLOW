import unittest
from datetime import date

from utils.date_utils import calculate_age, date_input_bounds


class DateInputBoundsTests(unittest.TestCase):
    def test_uses_seventy_past_years_and_ten_future_years(self):
        minimum, maximum = date_input_bounds(date(2026, 8, 16))

        self.assertEqual(minimum, date(1956, 1, 1))
        self.assertEqual(maximum, date(2036, 12, 31))


class CalculateAgeTests(unittest.TestCase):
    def test_returns_full_age_before_birthday(self):
        age = calculate_age("2000-08-17", date(2026, 8, 16))

        self.assertEqual(age, 25)

    def test_increments_full_age_on_birthday(self):
        age = calculate_age("2000-08-16", date(2026, 8, 16))

        self.assertEqual(age, 26)


if __name__ == "__main__":
    unittest.main()
