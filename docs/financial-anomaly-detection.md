# Financial anomaly detection

`app/accounting/anomaly_detection.py` -- transparent, rule-based, never
an opaque "fraud score". Every rule names its own evidence; nothing here
labels a transaction fraudulent, only flags a pattern worth a human
look (enforced by a test, `test_run_all_rules_never_marks_fraudulent`,
that greps every generated message for the word "fraud").

## Rules

| Rule code | What it catches | Severity |
|---|---|---|
| `DUPLICATE_PAYMENT` | Two non-voided payments, same amount + date, across different invoices | warning |
| `DUPLICATE_INVOICE` (Phase 13) | Same supplier + invoice number entered on more than one transaction -- a data-entry/double-upload mistake on the invoice side, distinct from `DUPLICATE_PAYMENT` which looks at the payment side | warning |
| `SUPPLIER_BANK_DETAILS_CHANGED` | A supplier's invoice uses an IBAN never seen from them before -- a common invoice-fraud indicator (payment redirection) | critical |
| `UNEXPECTED_EXPENSE_INCREASE` | An invoice from a known supplier is >50% above that supplier's historical average | info |
| `UNMATCHED_PAYMENT_AGING` | A bank transaction has been unmatched/suggested for over 14 days | warning |
| `UNUSUAL_CASH_WITHDRAWAL` (Phase 13) | A large (>EUR 500) outgoing bank transaction with no business counterparty name, or an ATM/cash keyword in its description | info |

Every `AnomalyFlag` carries: `rule_code`, `severity`, `message` (reason
+ a plain-language recommended action embedded in the sentence, e.g.
"verify directly with the supplier before paying"), `evidence` (JSON,
the exact data points the rule matched on), `related_entity_type`/
`related_entity_id` (the affected record), and `status`
(`OPEN`/`ACKNOWLEDGED`/`DISMISSED`, with `acknowledged_by_user_id`/
`acknowledged_at`) -- matching every field the Phase 13 brief asked an
alert to carry.

## Running the rules

`POST /companies/{id}/detect-anomalies` runs `run_all_rules`, which
clears each rule's previous `OPEN` flags for that company before
re-evaluating (idempotent re-runs, not an ever-growing duplicate list).
`GET /companies/{id}/anomalies` lists them (optionally filtered by
status); `POST /anomalies/{id}/acknowledge` / `/dismiss` are the human
review actions. Surfaced in the frontend at `/anomalies`, the
`/ai-intelligence` dashboard (open count + top flags), and the
`/review-centre` queue (inline acknowledge/dismiss).

## What this does NOT do

- Never auto-reverses, auto-blocks, or auto-flags a transaction as
  fraudulent -- every action remains a human decision.
- Does not use a trained ML model or an AI call -- every rule here is a
  plain, auditable Python function over the database, deliberately, so
  the evidence is always reproducible and explainable without needing to
  ask "why did the model think that."
- Does not attempt "possible personal expense" detection (see
  `docs/ai-document-processing.md` for why) or a generic "potential
  accounting error" catch-all -- validation errors from the document
  pipeline (`docs/ai-document-processing.md`) and the VAT reconciliation
  checks (`assistant_facts.vat_return_facts`) already cover the concrete,
  checkable error classes; a vaguer rule would risk false confidence.
