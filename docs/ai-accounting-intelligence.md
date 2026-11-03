# AI Accounting Intelligence

What "AI" means in this codebase, consistently, everywhere: the AI
narrates, explains, and suggests over numbers a deterministic Python
service already computed with `Decimal` arithmetic. It never computes a
financial figure itself, never silently posts a transaction, and never
replaces the ledger/VAT/payroll engines. This is enforced by construction
(the AI provider functions take already-computed facts/evidence as input
and return text/labels, not amounts) rather than by a prompt instruction
alone.

## AI Accounting Assistant

`app/api/v1/assistant.py` + `app/accounting/assistant_facts.py` (mostly
Phase 8, re-verified this phase, not rebuilt). Every endpoint builds a
deterministic FACTS dict from the real services below, then hands it to
`app/services/ai_assistant_provider.py` to narrate -- the assistant
cannot see anything not already in that dict, and the dict is returned
alongside the answer (`AssistantResponse.facts`) so the frontend can show
exactly what it was given.

| Question type | Endpoint | Facts source |
|---|---|---|
| "Summarize this company's position" | `GET /assistant/company-summary` | `assistant_facts.company_facts` |
| "Explain this VAT return" | `GET /assistant/vat-return-explanation/{id}` | `assistant_facts.vat_return_facts` + `reconciliation.build_reconciliation` |
| "What documents are missing?" | `GET /assistant/missing-documents` | `assistant_facts.missing_documents_facts` |
| Free-form financial question (profit, overdue customers, expense changes, cash balance, biggest costs, what-if scenarios) | `POST /assistant/financial-question` | `assistant_facts.financial_intelligence_facts` -- assembles `financial_reports.profit_and_loss`/`expense_breakdown`/`balance_sheet`/`debtors`/`creditors`, `kpi_engine.all_kpis`, `working_capital.payment_delay_alerts`, `financial_forecast.full_forecast` |
| Arbitrary question with a VAT period attached | `POST /assistant/ask` | `assistant_facts.company_facts` (+ VAT return facts if a period is given) |

Tenant/company isolation: every endpoint calls `require_company_access`
before building facts -- an account cannot ask about a company it isn't
linked to, by the same mechanism every other company-scoped endpoint
uses (no separate, forgettable check).

Actual vs. estimate: `financial_intelligence_facts` tags every forecast
figure under a key ending `_forecast` or carrying `is_estimate`, and the
assistant's system prompt (see `ai_assistant_provider.py`) is instructed
to preserve that distinction in its answer rather than blur it.

**Frontend** (`/assistant`): company picker, two one-click presets
("Summarize financial position", "Identify missing documents"), a
free-text question box wired to `/assistant/ask`, and the raw facts
shown in a collapsible `<details>` so a user can verify the answer
against what it was actually given -- not just trust it.

**New this phase** (`/ai-intelligence`, Workstream G): a dashboard that
reuses `assistant_facts`/`company-summary` for narration alongside
anomalies, automation-centre counts, cash-flow/outstanding-invoice
forecasts, and upcoming VAT deadlines -- see `docs/financial-forecasting.md`
and `docs/financial-anomaly-detection.md` for those pieces individually.

## Intelligent transaction classification

`app/services/ai_categorization_provider.py` + `GET
/transactions/{id}/category-suggestion` (Phase 6/8, re-verified this
phase). Returns `suggested_category`, `confidence`, `reasoning`,
`evidence`, and `requires_accountant_review` -- never applies itself.
Applying a category is a separate, explicit `POST
/transactions/{id}/categorize` call that always records
`category_source=manual` when a human makes the call (even when they
accepted the AI's suggestion verbatim) and can optionally save the
correction as a reusable rule (`categorization.create_rule_from_correction`)
for next time -- rule-matched categorization (no AI call) is tried first
on import, per `categorization.apply_rules`.

## Intelligent invoice/document processing

See `docs/ai-document-processing.md` for the extraction pipeline itself.
In summary, already in place pre-Phase-13 and re-verified now: supplier
name/VAT/IBAN extraction, document-type classification with a confidence
score, duplicate-document detection (content hash), missing-field
validation, and a human review/approval gate before anything reaches the
ledger (`app/services/document_approval.py`) -- an extraction is never
auto-posted.

## What this is not

- Not a chatbot with its own memory of your business -- every answer is
  stateless, rebuilt from the database on each call.
- Not a replacement for the accountant's judgment -- every assistant
  response and every category suggestion carries a disclaimer and a
  `requires_accountant_review`/confidence signal rather than presenting
  itself as a verdict.
- Not connected to anything outside this database -- it cannot see market
  data, other tenants' data, or anything not already computed by
  `app/accounting/*`.
