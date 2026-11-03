# Financial forecasting & cash-flow intelligence

`app/accounting/financial_forecast.py` (Phase 8, re-verified this
phase) + `app/accounting/cash_flow.py` (Phase 6, reused unchanged, never
reimplemented). Every function returns both a number and the
information needed to judge how much to trust it -- an `is_estimate`
flag, an explicit assumptions list, or a disclaimer string -- rather
than presenting a projection as a certainty.

## What's confirmed vs. estimated

| Function | Returns | `is_estimate` |
|---|---|---|
| `outstanding_invoice_forecast` | Receivables/payables already on the books, with aging | `False` -- these are recorded amounts owed, not a projection |
| `revenue_expense_profit_forecast` | Trailing-average revenue/expense/profit carried forward, with a +/-15% uncertainty band | `True` -- explicitly "a trend projection, not a guaranteed outcome" |
| `vat_payment_forecast` | Next 4 VAT periods' estimated net payable | `True` for periods not yet filed; figures change as more invoices are recorded |
| `tax_liability_forecast` | Corporate income tax | Always `None` -- **this system tracks Dutch VAT only and never fabricates a corporate-tax estimate** |
| `cash_flow.build_cash_flow_forecast` | Expected incoming/outgoing from invoices + recurring patterns, forecast VAT | Carries its own per-field disclaimer strings (`net_bank_transaction_movement_disclaimer`, `forecast_vat_disclaimer`) |

`full_forecast` assembles all of the above into one response
(`GET /forecasts/full`) -- the single call behind the `/ai-intelligence`
dashboard's cash-flow and outstanding-invoice sections and the
assistant's `financial-question` facts.

## Scenario comparison

`app/accounting/scenario_engine.py` (Phase 8) -- stored `Scenario`
records with named assumptions (e.g. "revenue -15%"), applied on top of
the same deterministic forecast functions above, never a separate
projection path. `GET /scenarios/compare` and the assistant's
`scenario_assumptions` payload (on `/assistant/financial-question`) both
go through this one engine.

## Budget vs. actual

`app/accounting/budget_service.py` + `ai_budget_provider.py` --
AI may *suggest* a budget allocation (`POST /budgets/suggest`), but the
budget itself is a stored, editable record compared against actuals
deterministically; the AI suggestion is never saved without a human
accepting it via the normal create/update endpoints.

## Frontend

`/forecasts` (full forecast + scenario builder/comparison),
`/cash-flow` (cash-flow forecast detail), `/budgets` (budget vs. actual),
`/working-capital` (outstanding invoices/aging), and the `/ai-intelligence`
dashboard's cash-flow/outstanding-invoice/tax-preparation panels --
all calling the endpoints above, no duplicate forecast logic in the
frontend.

## Known limitations (stated, not hidden)

- The revenue/expense/profit forecast is a flat trailing average, not a
  seasonal or ML model -- stated directly in its own `assumptions` list.
- Corporate income tax is never estimated (VAT-only system) --
  `tax_liability_forecast` always returns `None` rather than guessing.
- No customer-specific payment-behavior scoring beyond the existing
  debtors-aging buckets (`financial_reports.debtors`) -- a per-customer
  "likely to pay late" model was judged too speculative to build as a
  deterministic rule and was not added this phase.
