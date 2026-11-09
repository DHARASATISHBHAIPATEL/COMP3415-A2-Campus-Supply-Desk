"""Task 2 tests for the command-line and menu adapters (PRESERVE / INVALID).

These pin the user-visible behaviour of cli.main() and menu.run_menu() so that
refactoring OrderService cannot silently change what users see.
"""

import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest import mock

from supplydesk import cli
from supplydesk.menu import money, run_menu
from supplydesk.service import OrderService


class InterfaceTestCase(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.path = Path(self.directory.name) / "state.json"

    def run_cli(self, *args):
        out, err = io.StringIO(), io.StringIO()
        with contextlib.redirect_stdout(out), contextlib.redirect_stderr(err):
            status = cli.main(["--data", str(self.path), *args])
        return status, out.getvalue(), err.getvalue()

    def run_menu_with(self, *answers):
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=list(answers)), \
                contextlib.redirect_stdout(out):
            status = run_menu(OrderService(self.path))
        return status, out.getvalue()


class CliTests(InterfaceTestCase):
    def test_quote_defaults_to_regular_pickup_and_prints_json_cents(self):
        status, out, _ = self.run_cli("quote", "--item", "notebook:2")
        self.assertEqual(status, 0)
        result = json.loads(out)
        self.assertEqual(result["customer_type"], "regular")
        self.assertEqual(result["fulfillment"], "pickup")
        self.assertEqual(result["total_cents"], 1000)
        self.assertFalse(self.path.exists())

    def test_place_then_show_and_cancel(self):
        status, out, _ = self.run_cli("place", "--customer", "student",
                                      "--fulfillment", "delivery", "--item", "hoodie:2")
        self.assertEqual(status, 0)
        self.assertEqual(json.loads(out)["total_cents"], 7800)
        status, out, _ = self.run_cli("show", "ORD-0001")
        self.assertEqual((status, json.loads(out)["status"]), (0, "placed"))
        status, out, _ = self.run_cli("cancel", "ORD-0001")
        self.assertEqual((status, json.loads(out)["status"]), (0, "cancelled"))

    def test_rejected_request_exits_with_status_2(self):
        status, out, err = self.run_cli("place", "--item", "laptop:1")
        self.assertEqual(status, 2)
        self.assertEqual(out, "")
        self.assertIn("Error:", err)
        self.assertFalse(self.path.exists())

    def test_unknown_order_exits_with_status_2(self):
        status, _, err = self.run_cli("show", "ORD-0042")
        self.assertEqual(status, 2)
        self.assertIn("Unknown order", err)

    def test_badly_formed_item_rejected_by_parser(self):
        with self.assertRaises(SystemExit) as raised, \
                contextlib.redirect_stderr(io.StringIO()):
            cli.main(["--data", str(self.path), "quote", "--item", "notebook:two"])
        self.assertEqual(raised.exception.code, 2)


class MenuTests(InterfaceTestCase):
    def test_money_formats_cents_as_dollars(self):
        self.assertEqual(money(0), "$0.00")
        self.assertEqual(money(7805), "$78.05")

    def test_menu_quote_with_blank_defaults(self):
        # option 2, blank customer, notebook x2, finish items, blank fulfillment, exit
        status, out = self.run_menu_with("2", "", "notebook", "2", "", "", "0")
        self.assertEqual(status, 0)
        self.assertIn("Customer: regular | Fulfillment: pickup", out)
        self.assertIn("Total: $10.00", out)
        self.assertFalse(self.path.exists())

    def test_declining_placement_leaves_no_saved_data(self):
        status, out = self.run_menu_with("3", "", "mug", "1", "", "", "n", "0")
        self.assertEqual(status, 0)
        self.assertIn("Order not placed.", out)
        self.assertFalse(self.path.exists())

    def test_confirmed_placement_is_saved(self):
        self.run_menu_with("3", "", "mug", "1", "", "", "y", "0")
        self.assertEqual(OrderService(self.path).get_order("ORD-0001")["status"], "placed")

    def test_non_integer_quantity_asks_to_reenter_item(self):
        _, out = self.run_menu_with("2", "", "mug", "one", "mug", "1", "", "", "0")
        self.assertIn("Re-enter this item", out)
        self.assertIn("Total: $15.00", out)

    def test_invalid_request_reports_error_and_returns_to_menu(self):
        _, out = self.run_menu_with("2", "", "laptop", "1", "", "", "1", "0")
        self.assertIn("Error: Unknown product.", out)
        self.assertIn("Product ID", out)   # catalog shown again after option 1
        self.assertTrue(out.rstrip().endswith("Goodbye."))

    def test_end_of_input_exits_cleanly(self):
        out = io.StringIO()
        with mock.patch("builtins.input", side_effect=EOFError), \
                contextlib.redirect_stdout(out):
            status = run_menu(OrderService(self.path))
        self.assertEqual(status, 0)
        self.assertIn("Goodbye.", out.getvalue())


if __name__ == "__main__":
    unittest.main()
