"""Task 2 safety-net tests for OrderService.

Expected values come from FUNCTIONAL_SPEC.md, not from what the starter code
happens to do. Tests that fail on the starter code expose suspected defects and
are documented in evidence/ and the report; their expected values have NOT been
changed to make them pass.

Categories (see README "Running the tests"):
  NORMAL    - expected operation with valid inputs
  BOUNDARY  - limits and edge cases
  INVALID   - invalid input / unsupported operation
  PRESERVE  - behaviour the planned refactoring must not change
"""

import json
from pathlib import Path
import tempfile
import unittest

from supplydesk.service import OrderService


def item(product_id, quantity):
    return {"product_id": product_id, "quantity": quantity}


class ServiceTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.service = OrderService(self.path)

    def stock(self, product_id):
        for product in self.service.catalog():
            if product["product_id"] == product_id:
                return product["stock"]
        raise AssertionError("product not in catalog: " + product_id)

    def snapshot(self):
        """Raw save-file contents (None when no save file exists)."""
        if not self.path.exists():
            return None
        return self.path.read_text(encoding="utf-8")


class NormalBehaviourTests(ServiceTestCase):
    """NORMAL: valid requests produce the prices and records in the spec."""

    def test_quote_lists_line_details_and_does_not_create_save_file(self):
        quote = self.service.quote("regular", [item("notebook", 2)])
        self.assertEqual(quote["items"], [{
            "product_id": "notebook", "name": "Notebook",
            "unit_price_cents": 500, "quantity": 2, "line_total_cents": 1000,
        }])
        self.assertEqual(quote["total_cents"], 1000)
        self.assertNotIn("order_id", quote)
        self.assertFalse(self.path.exists(), "a quote must not create a save file")

    def test_regular_delivery_three_hoodies_free_delivery(self):
        quote = self.service.quote("regular", [item("hoodie", 3)], "delivery")
        self.assertEqual(
            (quote["subtotal_cents"], quote["discount_cents"],
             quote["delivery_cents"], quote["total_cents"]),
            (12000, 0, 0, 12000))

    def test_place_order_deducts_stock_and_saves(self):
        order = self.service.place_order(
            "student", [item("hoodie", 1), item("mug", 2)], "delivery")
        # subtotal 4000 + 3000 = 7000; discount 700; 6300 < 10000 so delivery 600
        self.assertEqual(order["order_id"], "ORD-0001")
        self.assertEqual(order["status"], "placed")
        self.assertEqual(order["subtotal_cents"], 7000)
        self.assertEqual(order["discount_cents"], 700)
        self.assertEqual(order["delivery_cents"], 600)
        self.assertEqual(order["total_cents"], 6900)
        self.assertEqual(self.stock("hoodie"), 4)
        self.assertEqual(self.stock("mug"), 6)
        self.assertEqual(self.service.list_orders(), [order])

    def test_order_ids_increase_and_history_keeps_placement_order(self):
        first = self.service.place_order("regular", [item("pen-pack", 1)])
        second = self.service.place_order("regular", [item("notebook", 1)])
        self.assertEqual([first["order_id"], second["order_id"]], ["ORD-0001", "ORD-0002"])
        self.assertEqual([o["order_id"] for o in self.service.list_orders()],
                         ["ORD-0001", "ORD-0002"])


class BoundaryBehaviourTests(ServiceTestCase):
    """BOUNDARY: exact limits named in the spec."""

    def test_student_discount_applies_at_exactly_5000(self):
        # Spec: 10% discount when subtotal is AT LEAST 5000 cents.
        # Predicted failure (Checkpoint A): code uses `subtotal > 5000`.
        quote = self.service.quote("student", [item("bag", 2)])
        self.assertEqual(quote["subtotal_cents"], 5000)
        self.assertEqual(quote["discount_cents"], 500)
        self.assertEqual(quote["total_cents"], 4500)

    def test_student_discount_not_applied_below_5000(self):
        # 9 notebooks = 4500, the closest reachable subtotal under the threshold.
        quote = self.service.quote("student", [item("notebook", 9)])
        self.assertEqual(quote["subtotal_cents"], 4500)
        self.assertEqual(quote["discount_cents"], 0)

    def test_student_discount_just_above_5000_is_integer_ten_percent(self):
        # 7 pen packs (5250) + 1 notebook (500) = 5750 -> discount 575.
        # Note: every catalog price is a multiple of 250 cents, so 10% of any
        # reachable subtotal is already whole; the half-cent rounding rule
        # cannot be exercised through the service with the shipped catalog.
        quote = self.service.quote("student", [item("pen-pack", 7), item("notebook", 1)])
        self.assertEqual(quote["subtotal_cents"], 5750)
        self.assertEqual(quote["discount_cents"], 575)
        self.assertIsInstance(quote["discount_cents"], int)

    def test_delivery_free_at_exactly_10000_after_discount(self):
        # regular: 2 hoodies (8000) + 4 notebooks (2000) = 10000 -> free delivery
        quote = self.service.quote(
            "regular", [item("hoodie", 2), item("notebook", 4)], "delivery")
        self.assertEqual(quote["subtotal_cents"], 10000)
        self.assertEqual(quote["delivery_cents"], 0)
        self.assertEqual(quote["total_cents"], 10000)

    def test_delivery_charged_when_discount_drops_below_10000(self):
        # student: 10500 subtotal, discount 1050 -> 9450 < 10000 -> 600 delivery
        quote = self.service.quote(
            "student", [item("hoodie", 2), item("notebook", 5)], "delivery")
        self.assertEqual(quote["subtotal_cents"], 10500)
        self.assertEqual(quote["discount_cents"], 1050)
        self.assertEqual(quote["delivery_cents"], 600)
        self.assertEqual(quote["total_cents"], 10050)

    def test_quantity_limits_1_and_99_accepted_by_validation(self):
        self.assertEqual(self.service.quote("regular", [item("mug", 1)])["total_cents"], 1500)
        # 99 is a valid quantity; it fails only on stock, not on the range check.
        with self.assertRaisesRegex(ValueError, "stock"):
            self.service.quote("regular", [item("notebook", 99)])

    def test_order_can_take_all_remaining_stock(self):
        self.service.place_order("regular", [item("bag", 4)])
        self.assertEqual(self.stock("bag"), 0)
        with self.assertRaisesRegex(ValueError, "stock"):
            self.service.quote("regular", [item("bag", 1)])

    def test_combined_duplicate_lines_cannot_exceed_stock(self):
        # Spec: combined quantity of a product across lines must not exceed stock.
        # Predicted failure (Checkpoint A): stock is checked per line.
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.service.place_order("regular", [item("bag", 3), item("bag", 2)])
        self.assertEqual(self.snapshot(), before, "rejected request must not save")

    def test_duplicate_lines_within_stock_stay_separate(self):
        order = self.service.place_order("regular", [item("mug", 1), item("mug", 2)])
        self.assertEqual([line["quantity"] for line in order["items"]], [1, 2])
        self.assertEqual(self.stock("mug"), 5)


class InvalidInputTests(ServiceTestCase):
    """INVALID: bad requests raise ValueError and change nothing."""

    def assert_rejected_without_change(self, call):
        self.service.place_order("regular", [item("notebook", 1)])  # earlier success
        before = self.snapshot()
        with self.assertRaises(ValueError):
            call()
        self.assertEqual(self.snapshot(), before)

    def test_invalid_quantities_rejected(self):
        for bad in (0, 100, -1, True, 2.0, "2", None):
            with self.subTest(quantity=bad):
                self.assert_rejected_without_change(
                    lambda: self.service.place_order("regular", [item("mug", bad)]))

    def test_unknown_or_missing_product_rejected(self):
        for bad_item in (item("laptop", 1), {"quantity": 1}, "mug:1"):
            with self.subTest(item=bad_item):
                self.assert_rejected_without_change(
                    lambda: self.service.place_order("regular", [bad_item]))

    def test_unsupported_customer_or_fulfillment_rejected(self):
        for customer, fulfillment in (("staff", "pickup"), ("Student", "pickup"),
                                      ("regular", "shipping"), ("regular", None)):
            with self.subTest(customer=customer, fulfillment=fulfillment):
                self.assert_rejected_without_change(
                    lambda: self.service.place_order(customer, [item("mug", 1)], fulfillment))

    def test_empty_or_non_list_items_rejected(self):
        for items in ([], None, item("mug", 1)):
            with self.subTest(items=items):
                self.assert_rejected_without_change(
                    lambda: self.service.place_order("regular", items))

    def test_rejected_order_does_not_consume_order_id(self):
        with self.assertRaises(ValueError):
            self.service.place_order("regular", [item("hoodie", 6)])
        self.assertEqual(self.service.place_order("regular", [item("mug", 1)])["order_id"],
                         "ORD-0001")

    def test_unknown_order_id_rejected(self):
        self.service.place_order("regular", [item("mug", 1)])
        before = self.snapshot()
        with self.assertRaises(ValueError):
            self.service.get_order("ORD-9999")
        with self.assertRaises(ValueError):
            self.service.cancel_order("ORD-9999")
        self.assertEqual(self.snapshot(), before)

    def test_malformed_save_file_raises_instead_of_resetting(self):
        self.path.write_text("{not json", encoding="utf-8")
        with self.assertRaises(ValueError):
            self.service.catalog()
        self.assertEqual(self.path.read_text(encoding="utf-8"), "{not json")


class PreserveBehaviourTests(ServiceTestCase):
    """PRESERVE: behaviour the refactoring of quote()/place_order() must keep."""

    def test_quote_and_placement_agree_on_pricing(self):
        cases = [
            ("regular", [item("notebook", 2)], "pickup"),
            ("student", [item("hoodie", 2)], "delivery"),
            ("student", [item("hoodie", 1), item("mug", 1), item("pen-pack", 3)], "delivery"),
            ("regular", [item("hoodie", 3)], "delivery"),
        ]
        for customer, items, fulfillment in cases:
            with self.subTest(customer=customer, items=items, fulfillment=fulfillment):
                quote = self.service.quote(customer, items, fulfillment)
                order = self.service.place_order(customer, items, fulfillment)
                for key in quote:
                    self.assertEqual(order[key], quote[key], key)
                self.service.cancel_order(order["order_id"])

    def test_quote_does_not_change_existing_save_file(self):
        self.service.place_order("regular", [item("mug", 1)])
        before = self.snapshot()
        self.service.quote("student", [item("hoodie", 2)], "delivery")
        self.assertEqual(self.snapshot(), before)

    def test_reopen_preserves_history_stock_and_numbering(self):
        order = self.service.place_order("regular", [item("mug", 1)])
        reopened = OrderService(self.path)
        self.assertEqual(reopened.list_orders(), [order])
        self.assertEqual(self.stock("mug"), 7)
        self.assertEqual(reopened.place_order("regular", [item("mug", 1)])["order_id"],
                         "ORD-0002")

    def test_historical_prices_not_recalculated(self):
        order = self.service.place_order("regular", [item("mug", 1)])
        state = json.loads(self.path.read_text(encoding="utf-8"))
        state["catalog"][3]["unit_price_cents"] = 9999  # mug price change
        self.path.write_text(json.dumps(state), encoding="utf-8")
        self.assertEqual(self.service.get_order(order["order_id"])["total_cents"], 1500)

    def test_cancel_keeps_order_in_history_and_id_not_reused(self):
        order = self.service.place_order("regular", [item("mug", 1)])
        cancelled = self.service.cancel_order(order["order_id"])
        self.assertEqual(cancelled["status"], "cancelled")
        self.assertEqual(cancelled["total_cents"], order["total_cents"])
        self.assertEqual(cancelled["items"], order["items"])
        self.assertEqual(self.stock("mug"), 8)
        self.assertEqual(self.service.place_order("regular", [item("mug", 1)])["order_id"],
                         "ORD-0002")

    def test_cancelling_twice_restores_stock_only_once(self):
        # Spec: cancelling an already cancelled order returns it without
        # changing stock again. Predicted failure (Checkpoint A diagnosis 5).
        order = self.service.place_order("regular", [item("mug", 1)])
        OrderService(self.path).cancel_order(order["order_id"])
        again = OrderService(self.path).cancel_order(order["order_id"])
        self.assertEqual(again["status"], "cancelled")
        self.assertEqual(self.stock("mug"), 8)


if __name__ == "__main__":
    unittest.main()
