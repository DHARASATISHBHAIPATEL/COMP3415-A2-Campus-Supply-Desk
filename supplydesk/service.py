"""Operations used by the command-line order desk."""

from supplydesk.storage import JsonStore

# Business policy from FUNCTIONAL_SPEC.md. All money values are integer cents.
CUSTOMER_TYPES = ("regular", "student")
FULFILLMENT_OPTIONS = ("pickup", "delivery", "express")
MIN_QUANTITY = 1
MAX_QUANTITY = 99
STUDENT_DISCOUNT_THRESHOLD_CENTS = 5000  # spec: "at least"; code still uses ">" (known defect, kept by refactoring)
STUDENT_DISCOUNT_PERCENT = 10
FREE_DELIVERY_THRESHOLD_CENTS = 10000
DELIVERY_CHARGE_CENTS = 600
EXPRESS_DELIVERY_CHARGE_CENTS = 1200  # CR-01: flat fee, never waived


def percent_of_cents(amount_cents, percent):
    """Return percent of amount_cents, rounding half a cent upward (integer only)."""
    return (amount_cents * percent + 50) // 100


def calculate_charges(customer_type, fulfillment, subtotal_cents):
    """Return (discount_cents, delivery_cents) for an already validated request."""
    discount = 0
    if customer_type == "student" and subtotal_cents > STUDENT_DISCOUNT_THRESHOLD_CENTS:
        discount = percent_of_cents(subtotal_cents, STUDENT_DISCOUNT_PERCENT)
    delivery = 0
    if fulfillment == "express":
        delivery = EXPRESS_DELIVERY_CHARGE_CENTS
    elif fulfillment == "delivery" and subtotal_cents - discount < FREE_DELIVERY_THRESHOLD_CENTS:
        delivery = DELIVERY_CHARGE_CENTS
    return discount, delivery


class OrderService:
    def __init__(self, state_path=".supplydesk/state.json"):
        self.store = JsonStore(state_path)

    def catalog(self):
        return self.store.load()["catalog"]

    def quote(self, customer_type, items, fulfillment="pickup"):
        state = self.store.load()
        return self._price_request(state, customer_type, items, fulfillment)

    def place_order(self, customer_type, items, fulfillment="pickup"):
        state = self.store.load()
        priced = self._price_request(state, customer_type, items, fulfillment)
        order = {"order_id": self._format_order_id(state["next_order_number"]),
                 "status": "placed",
                 **priced}
        self._adjust_stock(state, order["items"], direction=-1)
        state["next_order_number"] += 1
        state["orders"].append(order)
        self.store.save(state)
        return order

    @staticmethod
    def _format_order_id(number):
        return "ORD-" + str(number).zfill(4)

    @staticmethod
    def _find_product(catalog, product_id):
        """Return the catalog entry with product_id, or None."""
        for product in catalog:
            if product["product_id"] == product_id:
                return product
        return None

    def _adjust_stock(self, state, lines, direction):
        """Add (direction=+1) or remove (direction=-1) each line's quantity from stock."""
        for line in lines:
            product = self._find_product(state["catalog"], line["product_id"])
            if product is not None:
                product["stock"] += direction * line["quantity"]

    def _price_request(self, state, customer_type, items, fulfillment):
        """Validate a request against state and price it. Shared by quote and place_order.

        Raises ValueError for an invalid request. Does not modify state.
        """
        if customer_type not in CUSTOMER_TYPES:
            raise ValueError("Customer type must be regular or student.")
        if fulfillment not in FULFILLMENT_OPTIONS:
            raise ValueError("Fulfillment must be pickup, delivery or express.")
        if not isinstance(items, list) or not items:
            raise ValueError("An order must contain at least one item.")
        lines = []
        subtotal = 0
        for item in items:
            if not isinstance(item, dict):
                raise ValueError("Each item must contain a product_id and quantity.")
            product = self._find_product(state["catalog"], item.get("product_id"))
            if product is None:
                raise ValueError("Unknown product.")
            quantity = item.get("quantity")
            if type(quantity) is not int or quantity < MIN_QUANTITY or quantity > MAX_QUANTITY:
                raise ValueError(f"Quantity must be an integer from {MIN_QUANTITY} to {MAX_QUANTITY}.")
            if quantity > product["stock"]:
                raise ValueError("Not enough stock for " + product["product_id"] + ".")
            line_total = product["unit_price_cents"] * quantity
            subtotal += line_total
            lines.append({
                "product_id": product["product_id"],
                "name": product["name"],
                "unit_price_cents": product["unit_price_cents"],
                "quantity": quantity,
                "line_total_cents": line_total,
            })
        discount, delivery = calculate_charges(customer_type, fulfillment, subtotal)
        return {
            "customer_type": customer_type,
            "fulfillment": fulfillment,
            "items": lines,
            "subtotal_cents": subtotal,
            "discount_cents": discount,
            "delivery_cents": delivery,
            "total_cents": subtotal - discount + delivery,
        }

    def list_orders(self):
        return self.store.load()["orders"]

    def get_order(self, order_id):
        state = self.store.load()
        for order in state["orders"]:
            if order["order_id"] == order_id:
                return order
        raise ValueError("Unknown order: " + order_id)

    def cancel_order(self, order_id):
        state = self.store.load()
        order = None
        for candidate in state["orders"]:
            if candidate["order_id"] == order_id:
                order = candidate
                break
        if order is None:
            raise ValueError("Unknown order: " + order_id)
        # Known defect (diagnosis 5): no check for an already-cancelled order,
        # so a second cancellation restores stock again. Kept by refactoring.
        self._adjust_stock(state, order["items"], direction=+1)
        order["status"] = "cancelled"
        self.store.save(state)
        return order
