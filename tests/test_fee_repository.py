import unittest
from unittest.mock import MagicMock, patch

from repositories.fee_repository import (
    FeePaymentSchemaError,
    insert_fee_payment,
)


class FeeRepositoryTests(unittest.TestCase):
    def test_reports_outdated_amount_constraint_safely(self):
        client = MagicMock()
        client.table.return_value.insert.return_value.execute.side_effect = Exception(
            "23514 fee_payments_amount_check failing row contains private data"
        )

        with patch(
            "repositories.fee_repository.get_supabase_client",
            return_value=client,
        ):
            with self.assertRaises(FeePaymentSchemaError) as context:
                insert_fee_payment({"amount": 4000, "months": 2})

        message = str(context.exception)
        self.assertIn("002_update_fee_payment_constraints.sql", message)
        self.assertNotIn("private data", message)


if __name__ == "__main__":
    unittest.main()
