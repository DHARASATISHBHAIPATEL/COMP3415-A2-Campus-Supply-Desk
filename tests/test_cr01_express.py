"""CR-01 (Express Delivery) acceptance tests. See docs/CR-01.md."""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from supplydesk import cli
from supplydesk.menu import run_menu
from supplydesk.service import OrderService


def item(product_id, quantity):
    return {"product_id": product_id, "quantity": quantity}


class ExpressTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"
        self.service = OrderService(self.path)

    def charges(self, result):
        return (result["subtotal_cents"], result["discount_cents"],
                result["delivery_cents"], result["total_cents"])

    def stock(self, product_id):
        return next(p["stock"] for p in self.service.catalog()
                    if p["product_id"] == product_id)


class ExpressPricingTests(ExpressTestCase):
    """Acceptance requirements 2, 3 and 5 and the CR-01 examples."""

    def test_example_regular_two_notebooks_express(self):
        quote = self.service.quote("regular", [item("notebook", 2)], "express")
        self.assertEqual(self.charges(quote), (1000, 0, 1200, 2200))

    def test_example_student_two_hoodies_express(self):
        quote = self.service.quote("student", [item("hoodie", 2)], "express")
        self.assertEqual(self.charges(quote), (8000, 800, 1200, 8400))

    def test_example_regular_three_hoodies_standard_vs_express(self):
        standard = self.service.quote("regular", [item("hoodie", 3)], "delivery")
        express = self.service.quote("regular", [item("hoodie", 3)], "express")
        self.assertEqual(standard["total_cents"], 12000)
        self.assertEqual(express["total_cents"], 13200)

    def test_express_fee_not_waived_at_free_delivery_threshold(self):
        # 2 hoodies + 4 notebooks = exactly 10000: standard is free, express is not.
        items = [item("hoodie", 2), item("notebook", 4)]
        self.assertEqual(self.service.quote("regular", items, "delivery")["delivery_cents"], 0)
        self.assertEqual(self.charges(self.service.quote("regular", items, "express")),
                         (10000, 0, 1200, 11200))

    def test_discount_on_merchandise_only_and_unchanged_by_express(self):
        items = [item("hoodie", 1), item("mug", 2)]  # 7000
        for fulfillment in ("pickup", "delivery", "express"):
            with self.subTest(fulfillment=fulfillment):
                self.assertEqual(
                    self.service.quote("student", items, fulfillment)["discount_cents"], 700)
        self.assertEqual(self.service.quote("student", items, "express")["total_cents"],
                         7000 - 700 + 1200)

    def test_standard_delivery_and_pickup_unchanged(self):
        self.assertEqual(self.charges(self.service.quote("student", [item("hoodie", 2)], "delivery")),
                         (8000, 800, 600, 7800))
        self.assertEqual(self.charges(self.service.quote("regular", [item("notebook", 2)])),
                         (1000, 0, 0, 1000))

    def test_express_quote_and_placed_order_agree(self):
        items = [item("hoodie", 2), item("pen-pack", 1)]
        quote = self.service.quote("student", items, "express")
        order = self.service.place_order("student", items, "express")
        for key, value in quote.items():
            self.assertEqual(order[key], value, key)


class ExpressOrderLifecycleTests(ExpressTestCase):
    """Requirements 5 and 6: retrieval, reopen, cancellation, numbering."""

    def test_express_order_survives_reopen_and_cancel(self):
        order = self.service.place_order("student", [item("hoodie", 2)], "express")
        self.assertEqual(order["order_id"], "ORD-0001")
        self.assertEqual(self.stock("hoodie"), 3)

        reopened = OrderService(self.path)
        self.assertEqual(reopened.get_order("ORD-0001"), order)

        cancelled = reopened.cancel_order("ORD-0001")
        self.assertEqual(cancelled["status"], "cancelled")
        for key in ("fulfillment", "items", "delivery_cents", "discount_cents", "total_cents"):
            self.assertEqual(cancelled[key], order[key], key)
        self.assertEqual(self.stock("hoodie"), 5)
        self.assertEqual(self.service.place_order("regular", [item("mug", 1)], "express")
                         ["order_id"], "ORD-0002")

    def test_other_fulfillment_values_still_invalid(self):
        self.service.place_order("regular", [item("mug", 1)], "express")
        before = self.path.read_text(encoding="utf-8")
        for bad in ("Express", "express ", "overnight", "shipping", ""):
            with self.subTest(fulfillment=bad):
                with self.assertRaises(ValueError):
                    self.service.place_order("regular", [item("mug", 1)], bad)
        self.assertEqual(self.path.read_text(encoding="utf-8"), before)

    def test_express_still_validates_stock(self):
        with self.assertRaisesRegex(ValueError, "stock"):
            self.service.place_order("regular", [item("bag", 5)], "express")
        self.assertFalse(self.path.exists())


class ExpressInterfaceTests(ExpressTestCase):
    """Requirements 1 and 7: individual commands and the menu."""

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            try:
                status = cli.main(["--data", str(self.path), *args])
            except SystemExit as exit_:
                status = exit_.code
        return status, out.getvalue(), err.getvalue()

    def test_cli_example_from_cr01(self):
        status, out, _ = self.run_cli("quote", "--customer", "student",
                                      "--fulfillment", "express", "--item", "hoodie:2")
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out)["total_cents"], 8400)

    def test_cli_place_express_and_show(self):
        status, out, _ = self.run_cli("place", "--fulfillment", "express", "--item", "notebook:2")
        self.assertEqual((status, json.loads(out)["total_cents"]), (0, 2200))
        status, out, _ = self.run_cli("show", "ORD-0001")
        self.assertEqual(json.loads(out)["fulfillment"], "express")

    def test_cli_help_lists_express_and_unknown_value_rejected(self):
        status, out, _ = self.run_cli("quote", "--help")
        self.assertEqual(status, 0)
        self.assertIn("express", out)
        status, _, err = self.run_cli("quote", "--fulfillment", "overnight", "--item", "mug:1")
        self.assertEqual(status, 2)
        self.assertIn("invalid choice", err)

    def test_cli_default_still_pickup(self):
        _, out, _ = self.run_cli("quote", "--item", "mug:1")
        self.assertEqual(json.loads(out)["fulfillment"], "pickup")

    def run_menu_with(self, *answers):
        out = io.StringIO()
        prompts = []

        def fake_input(prompt=""):
            prompts.append(prompt)
            return answers[len(prompts) - 1]

        with mock.patch("builtins.input", side_effect=fake_input), \
                contextlib.redirect_stdout(out):
            run_menu(OrderService(self.path))
        return out.getvalue(), prompts

    def test_menu_express_quote_and_prompt_mentions_express(self):
        out, prompts = self.run_menu_with("2", "student", "hoodie", "2", "", "express", "0")
        self.assertIn("Fulfillment: express", out)
        self.assertIn("Delivery: $12.00", out)
        self.assertIn("Total: $84.00", out)
        self.assertTrue(any("express" in p for p in prompts if p.startswith("Fulfillment")))

    def test_menu_blank_fulfillment_still_pickup(self):
        out, _ = self.run_menu_with("2", "", "notebook", "2", "", "", "0")
        self.assertIn("Customer: regular | Fulfillment: pickup", out)


if __name__ == "__main__":
    unittest.main()
