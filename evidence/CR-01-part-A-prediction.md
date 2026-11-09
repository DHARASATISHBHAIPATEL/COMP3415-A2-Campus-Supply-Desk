# CR-01 Part A: prediction (recorded before implementation)

Recorded 2026-11-09, at commit `a0aaaa0`, before any CR-01 code was written.
Draft prepared with AI assistance; Dhara to review and reword in the report.
The CR-01 text is in `docs/CR-01.md`.

## 1. Behaviour and requirements that will change

- **Fulfillment values:** `express` becomes a third valid value next to `pickup` and `delivery`.
  Other values (for example `shipping` and `overnight`) stay invalid.
- **Delivery charge:** express is a flat 1200 cents. Unlike standard delivery, it is never waived,
  even when subtotal minus discount is at least 10000.
- **Unchanged:**
  - student discount threshold and rounding;
  - the discount is still computed on merchandise only;
  - pickup is free;
  - standard delivery is 600, free from 10000;
  - validation, stock, numbering, history and cancellation.
  - The known defects (`> 5000` threshold, per-line stock check, repeated cancellation) are outside
    CR-01 and should stay as they are, so that the CR-01 diff contains only CR-01.
- **Discoverability:** the menu prompt, `--fulfillment` help and choices, FUNCTIONAL_SPEC.md and the
  README must mention express. The `regular` and `pickup` defaults stay.

## 2. Files and methods expected to change

| File | Expected change | Why |
| --- | --- | --- |
| `supplydesk/service.py` | Add `"express"` to `FULFILLMENT_OPTIONS`; add `EXPRESS_DELIVERY_CHARGE_CENTS = 1200`; add an express branch in `calculate_charges()`; update the "Fulfillment must be…" error text | After refactoring R1–R3, the pricing rule lives in one function (`calculate_charges`) and the valid set in one constant, so `quote()`, `place_order()` and `_price_request()` should **not** need editing |
| `supplydesk/cli.py` | `--fulfillment` choices are a hard-coded `("pickup", "delivery")` tuple → reuse `FULFILLMENT_OPTIONS` and add help text | Otherwise argparse rejects `express` before the service sees it |
| `supplydesk/menu.py` | `read_request()` prompt text `[pickup/delivery]` → `[pickup/delivery/express]` | Discoverability; menu passes the typed value straight to the service |
| `FUNCTIONAL_SPEC.md`, `README.md` | Document express, its fee and an example | Requirement 7 |
| `supplydesk/storage.py`, `catalog.json` | **No change expected** | Orders already store `fulfillment` and `delivery_cents` as data, so reopening and cancelling should keep express orders unchanged |

Risk to check: if any code compares `fulfillment == "delivery"` elsewhere (menu display, cancellation), express could be mistreated.
A static search before implementing found only `calculate_charges()`.

## 3. Tests needed

New tests, in a new `tests/test_cr01_express.py`:

- the three CR-01 examples, as quote **and** placement: regular 2 notebooks → 2200; student 2 hoodies → discount 800, total 8400; regular 3 hoodies → standard 12000 vs express 13200;
- express fee not waived at or above the free-delivery threshold, after discount;
- student discount unchanged by express: the discount is computed on merchandise only;
- an express order keeps fulfillment, items, fee, discount and total when retrieved, reopened and cancelled, and cancellation restores stock;
- invalid fulfillment values still raise `ValueError` with no state change, for example `Express` (case) and `overnight`;
- CLI: `quote --customer student --fulfillment express --item hoodie:2` gives `total_cents` 8400 and exit 0; `--help` lists express; an unsupported value still exits with status 2;
- menu: typing `express` at the fulfillment prompt works; the prompt lists express; a blank answer still gives pickup.

Existing tests expected to keep passing unchanged: all 39 that pass now, including the standard delivery boundaries and the CLI and menu defaults.
The 3 known-defect failures are expected to stay failing, because CR-01 does not touch them.
