# Intentionally untranslated backend-generated messages

Phase 16.3. Required inventory per the phase brief: "do not blindly
translate every backend string" — this documents exactly which
backend-generated, user-facing strings are localised, which are not,
and why, so the boundary is a documented decision rather than an
unexamined gap.

## Localised

- **Dashboard attention reasons** (`app/api/v1/dashboard.py`, via
  `app/core/messages_i18n.py`). Fixed in Phase 16.2.
- **All 5 PDF/XLSX report generators** (`app/reporting/*.py`, via
  `app/reporting/report_i18n.py`). Fixed in Phase 16.1–16.2.

## Not localised — stable by design, never should be

- Every `HTTPException(detail=...)` across the API. Error `detail`
  strings are a stable contract a client (or a human reading logs)
  parses; translating them would make error handling locale-dependent,
  which the brief explicitly asks to avoid ("keep machine-readable API
  error codes stable"). Verified with a dedicated test
  (`test_unsupported_document_language_error_detail_is_stable_english_regardless_of_accept_language`
  in `tests/test_report_i18n_full.py`).
- Enum values returned in API responses (`status.value`,
  `payment_status`, `upload_category`, etc.) — these are the actual
  stored/filed values, not display text; the frontend already
  translates them for display via its own dictionaries where a
  human-facing label exists.
- Internal logs (`logger.warning(...)`, `logger.info(...)`) — never
  user-facing, not in scope at all.

## Not localised — real user-facing text, deliberately deferred

This is the body of work this phase found but chose not to attempt,
and why.

### Validation findings (`app/services/validation_engine.py`)

13 rule codes (`AMOUNT_MISMATCH`, `DUPLICATE_DOCUMENT`,
`MISSING_VAT_BREAKDOWN`, `VAT_RATE_INCONSISTENT`, `UNUSUAL_VAT_RATE`,
`MISSING_INVOICE_NUMBER`, `MISSING_CREDIT_NOTE_REFERENCE`,
`DUE_DATE_BEFORE_INVOICE_DATE`, `INVALID_DATE`,
`UNRECOGNIZED_CURRENCY`, `SUPPLIER_CUSTOMER_IDENTICAL`,
`UPLOAD_CATEGORY_MISMATCH`, `POTENTIAL_BUSINESS_DUPLICATE`), each
paired with an English `message` built with an f-string that
interpolates runtime values (amounts, dates, filenames, other
document IDs). Shown directly to the user in `app/vat/[id]/page.tsx`
(`{v.rule_code}: {v.message}`) and surfaced via
`DocumentValidationResult` rows elsewhere.

### Anomaly findings (`app/accounting/anomaly_detection.py`)

6 similarly-interpolated English messages
(`DUPLICATE_PAYMENT`, `SUPPLIER_BANK_DETAILS_CHANGED`,
`UNEXPECTED_EXPENSE_INCREASE`, `UNMATCHED_PAYMENT_AGING`,
`DUPLICATE_INVOICE`, `UNUSUAL_CASH_WITHDRAWAL`), same shape and same
reason for being deferred.

**Why these are harder than the dashboard-reasons fix, and why that
matters:** the dashboard reasons are computed and formatted fresh on
every API request, so localising them was just "resolve locale, pick
the right template." These two are different: the formatted `message`
string is **persisted to the database** at document-processing time
(`DocumentValidationResult.message`, and the equivalent for anomalies)
and read back unchanged later, often much later, by a different user
session than the one that triggered the original processing run (and
document processing runs in a background pipeline with no
"requesting user" at all — only a company/tenant). Properly localising
this means:

1. Storing the rule code and its interpolation parameters (amounts,
   dates, other-document references) as structured data instead of a
   pre-rendered string.
2. Building a translation table for all 19 templates across 4 locales
   (non-trivial — several interpolate 2–4 values with locale-sensitive
   formatting of their own, e.g. amounts and dates within the
   message).
3. Rendering the message at **read time**, using the requesting user's
   current locale, not the locale in effect when the background job
   ran — otherwise switching UI language wouldn't retranslate
   already-stored findings, which would be a confusing, inconsistent
   half-fix.
4. A reversible Alembic migration adding the params column(s) to both
   `DocumentValidationResult` and whatever anomaly-finding table
   stores the equivalent, plus updating every call site that
   constructs a `ValidationFinding`/anomaly finding to stop
   pre-formatting text.

This is a genuine schema-and-pipeline change touching the
document-processing and anomaly-detection pipelines — both
correctness-sensitive, both already covered by their own test suites.
Attempting it as a rushed addition inside an already-large
internationalisation phase risked introducing a real bug in those
pipelines for a comparatively low-traffic set of strings (validation/
anomaly detail text, not a page's primary content). Deferred as a
separate, properly-scoped piece of future work rather than attempted
under time pressure.

### Other "note"/explanatory strings (investigated in Phase 16.3, deferred for a different reason than validation/anomaly)

Hardcoded English explanatory text exists in: `app/accounting/
financial_reports.py` (3, all in one function, `cash_flow_statement`),
`app/accounting/financial_forecast.py` (2, in `outstanding_invoice_
forecast` and `tax_liability_forecast`), `app/accounting/entity_tax.py`
(2, in `estimate_sole_proprietor_income_tax` and `foundation_or_
association_obligations_note`), `app/accounting/payroll_service.py` (1,
in `build_annual_statement` — also the untranslated note shown in the
annual-statement PDF), `app/accounting/scenario_engine.py` (1, in
`apply_scenario`), `app/accounting/dutch_tax_rules.py` (1, in
`calculate_wkr_free_space`), `app/api/v1/tax_centre.py` (6). No runtime
interpolation in any of them — unlike validation/anomaly findings,
these have no persisted-text problem, so the schema concern above does
not apply here.

Initially scoped (correctly) as the easiest item in this document, but
checking actual call sites in Phase 16.3 found a different complication:
several of these functions are called not just from an API endpoint
(where a `user` and therefore a resolvable locale is directly in scope)
but from OTHER accounting-layer functions one or two calls removed —
e.g. `estimate_sole_proprietor_income_tax` is called both directly from
`tax_centre.py` AND from `tax_optimization.py` (twice, comparing a
"with deduction" vs "without deduction" scenario) AND recursively from
within `entity_tax.py` itself; `apply_scenario` similarly calls itself
for scenario-comparison lists in `scenario_engine.py`. Threading a
`locale` parameter through correctly means touching every rung of each
call chain, not just the outermost API handler, and `foundation_or_
association_obligations_note`/`calculate_wkr_free_space` don't even
receive `db`/`company_id` today (pure calculation functions) so adding
locale resolution to them means deciding where in their caller chain it
should actually be resolved. None of this is as mechanical as the
dashboard-reasons fix looked at first — verified by reading the actual
call graph, not assumed. Deferred rather than threading a parameter
through partially-understood multi-level call chains under time
pressure; a good next task, but one that needs its own pass to map every
caller first, the same way this paragraph just did for future reference.

## What was checked and found to NOT be a gap

The phase brief named "banking import results" and "payroll status
messages" as categories to prioritise. Both were checked
(`app/accounting/bank_import.py`, `app/services/open_banking_
provider.py`, `app/accounting/payroll_service.py`) and neither
generates free-text user-facing messages beyond the one `note` field
already listed above — they return structured status/count data that
the frontend already renders and translates itself. No action needed.
