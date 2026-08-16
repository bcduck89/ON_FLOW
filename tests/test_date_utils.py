import unittest
from datetime import date

from utils.date_utils import date_input_bounds


class DateInputBoundsTests(unittest.TestCase):
    def test_uses_seventy_past_years_and_ten_future_years(self):
        minimum, maximum = date_input_bounds(date(2026, 8, 16))

        self.assertEqual(minimum, date(1956, 1, 1))
        self.assertEqual(maximum, date(2036, 12, 31))


if __name__ == "__main__":
    unittest.main()
