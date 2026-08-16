import unittest

from services.fee_engine import get_months_from_amount


class FeeAmountTests(unittest.TestCase):
    def test_converts_every_two_thousand_won_to_one_month(self):
        self.assertEqual(get_months_from_amount(2000), 1)
        self.assertEqual(get_months_from_amount(4000), 2)
        self.assertEqual(get_months_from_amount(6000), 3)
        self.assertEqual(get_months_from_amount(12000), 6)

    def test_rejects_non_multiple_zero_and_negative_amounts(self):
        self.assertEqual(get_months_from_amount(3000), 0)
        self.assertEqual(get_months_from_amount(0), 0)
        self.assertEqual(get_months_from_amount(-2000), 0)
        self.assertEqual(get_months_from_amount("invalid"), 0)


if __name__ == "__main__":
    unittest.main()
