# CR-01 Part C: review (after implementation)

Prediction commit: `00bd6a0`. Implementation commit: `640332c`.
Draft prepared with AI assistance; Dhara to review and reword in the report.

## 1. Files and methods that actually changed

| File | Change | Predicted? |
| --- | --- | --- |
| `supplydesk/service.py` | `FULFILLMENT_OPTIONS` gains `"express"`; new `EXPRESS_DELIVERY_CHARGE_CENTS = 1200`; a 2-line express branch in `calculate_charges()`; the error text now lists express (5 lines changed in total) | Yes |
| `supplydesk/cli.py` | `--fulfillment` choices reuse `FULFILLMENT_OPTIONS` instead of a duplicated literal; help text describes each option | Yes |
| `supplydesk/menu.py` | Fulfillment prompt text `[pickup/delivery/express]` | Yes |
| `FUNCTIONAL_SPEC.md`, `README.md` | Express rule (5a), the three CR-01 examples, CLI example, test file list | Yes |
| `storage.py`, `catalog.json`, `quote()`, `place_order()`, `_price_request()`, `cancel_order()` | **Unchanged** | Yes, predicted no change |

## 2. Was the prediction correct?

Yes. Every predicted file changed, and nothing outside the prediction changed.
The predicted risk, a second `== "delivery"` comparison elsewhere, did not occur.
Reopen and cancel needed no code because orders store `fulfillment` and `delivery_cents` as data.
`test_express_order_survives_reopen_and_cancel` confirms this.

One detail was learned during implementation.
`test_express_still_validates_stock` failed on the old code for a different reason than its name suggests.
`express` was rejected as a fulfillment value before stock was checked.
Validation order is therefore part of the observable behaviour.

## 3. Tests added or updated

- **Added:** `tests/test_cr01_express.py`, with 16 tests in three classes: `ExpressPricingTests`, `ExpressOrderLifecycleTests` and `ExpressInterfaceTests`.
- **Before implementation:** 12 of the 16 fail on the pre-CR-01 code (`evidence/03-cr01-tests-before-implementation.txt`). The 4 that already passed check behaviour that must not change: CLI and menu defaults, and rejection of unknown values.
- **After implementation:** all 16 pass.
- **Existing tests:** none were modified. The previous 42 tests give identical per-test results (`evidence/02-after-refactoring.txt` vs `evidence/04-after-cr01.txt`). This includes the same 3 known-defect failures, which CR-01 does not address.
- **CLI regression check:** the 17-command scenario gives byte-identical output before and after CR-01 (`evidence/04-cli-differential-after-cr01.txt`).

Final run: **58 tests, 55 pass, 3 known failures.**

## 4. Did the earlier refactoring help?

It made the change **easier**. The evidence is the size and location of the diff.

- **Without R2** (duplicated code): the fee rule would have had to be added in both `quote()` and `place_order()`. A missed copy would make quotes and orders disagree, which breaks CR-01 requirement 5.
- **With R2:** the rule changed in one place, `calculate_charges()`.
- **R1** (named constants): the new fee became a named constant beside the existing `DELIVERY_CHARGE_CENTS`, rather than a second magic number.
- **R3** (extracting `calculate_charges()`): the charge rules are isolated, so the express branch is two lines.

The CLI needed a change the refactoring had not covered: a duplicated `("pickup", "delivery")` literal.
That is a remaining instance of the duplication smell, outside the scope of R1–R3, and was fixed as part of CR-01.
