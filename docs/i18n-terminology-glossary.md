# Accounting terminology glossary — nl / en / fa / ar

Phase 16.2. Central reference for the accounting/tax terminology used
across the frontend dictionaries (`frontend/messages/*.json`) and the
backend report generators (`backend/app/reporting/report_i18n.py`).
Dutch is the source of truth and the fallback locale everywhere in this
app; English, Persian, and Arabic are translations of it.

## Review status — read this first

**No native-speaker review has been performed on any Persian or Arabic
translation in this codebase, at any phase.** Every fa/ar string was
produced by an AI model using professional-register judgment and
general knowledge of Dutch/EU accounting and tax terminology, not by a
qualified human translator, a certified Persian/Arabic
accountant/bookkeeper, or any officially published Dutch-authority
glossary in these languages (the Belastingdienst does not publish one).
Treat every fa/ar string in this app as a *draft* suitable for a reader
to understand the general meaning, not as an authoritative translation
to rely on for a legal, tax, or financial decision. The Dutch version
remains what is actually filed with the Belastingdienst or paid out to
an employee; fa/ar/en are explanatory only (see each report generator's
docstring in `report_i18n.py` for the same point stated in code).

Before this app's fa/ar content is used in a context where translation
accuracy has real consequences (e.g. shown to a Persian/Arabic-speaking
business owner making a filing decision), get it reviewed by a
qualified native-speaking accountant or professional translator
familiar with Dutch tax law. This document exists to make that review
tractable (one place listing every term and what's already flagged as
uncertain), not to substitute for it.

## How to use this document

- Adding a new translated string anywhere in the app? Check here first
  for the term you need — reuse it for consistency rather than
  inventing a new phrasing.
- Introducing a new accounting/tax term not listed here? Add it to the
  relevant table below in the same commit.
- Never translate: account/box codes (`1a`, `5g`, ...), enum values,
  VAT percentages as raw numbers, IBAN/BIC/VAT/KVK numbers, EBITDA/EBIT
  (kept as the Latin acronym in every locale — no established
  translated abbreviation in fa/ar, and English finance usage already
  keeps it as-is in Dutch professional contexts too).

## Core terminology

| Dutch (canonical) | English | Persian | Arabic | Notes |
|---|---|---|---|---|
| Btw | VAT | مالیات بر ارزش افزوده | ضريبة القيمة المضافة | "VAT" used throughout rather than "sales tax" (US term) — EU VAT, not a US-style sales tax |
| Btw-aangifte | VAT return | اظهارنامه مالیات بر ارزش افزوده | الإقرار الضريبي | |
| Aangiftevak | Declaration box | کادر اظهارنامه | خانة الإقرار | Belastingdienst's own box numbering (1a, 5g, ...) stays untranslated |
| Verlegde btw | Reverse-charge VAT | مالیات معکوس | الآلية العكسية / ضريبة معكوسة | |
| Grootboek | (General) ledger | دفتر کل / دفتر‌الستاذ | دفتر الأستاذ العام | fa has two common renderings; "دفتر کل" used here as the shorter, more common one |
| Boeking / journaalpost | Journal entry | ثبت دفتری / سند حسابداری | قيد محاسبي | |
| Debet / Credit | Debit / Credit | بدهکار / بستانکار | مدين / دائن | **flagged for review** — confirm against whichever Gulf/Levant accounting glossary, if any, the business's target market already uses |
| Factuur | Invoice | فاکتور | فاتورة | |
| Creditfactuur / creditnota | Credit note | فاکتور اصلاحی / نُت اعتباری | إشعار دائن | No credit-note feature exists in the app yet (see Phase 16.1 report) — this entry is for when one is built |
| Tegenpartij | Counterparty | طرف حساب / طرف مقابل | الطرف المقابل | **flagged for review** — same term used for both invoicing and bank-reconciliation contexts; some Arabic accounting products use "الجهة المقابلة" in the reconciliation context specifically |
| Afstemming | Reconciliation | تطبیق / مغایرت‌گیری | التسوية / المطابقة | |
| Proefbalans | Trial balance | تراز آزمایشی | ميزان المراجعة | |
| Balans | Balance sheet | Balance Sheet | ترازنامه | |
| Winst- en verliesrekening | Profit & Loss Statement | صورت سود و زیان | قائمة الأرباح والخسائر | |
| Bruto / Netto | Gross / Net | ناخالص / خالص | إجمالي / صافي | |
| Loonstrook | Payslip | فیش حقوقی | قسيمة الراتب | |
| Jaaropgaaf | Annual Statement | اظهارنامه سالانه | البيان السنوي | Not a literal translation of "jaaropgaaf" (no fa/ar equivalent exists) — rendered by function/purpose instead |
| Loonheffing | Wage tax (+ national insurance) | مالیات حقوق + بیمه‌های اجتماعی | ضريبة الأجور + التأمينات الاجتماعية | Dutch term bundles wage tax and national-insurance contributions into one withholding; en/fa/ar spell both out since no single word covers it |
| Vakantiegeld | Holiday allowance | حق تعطیلات | بدل الإجازة | Dutch-specific statutory holiday pay (8% of gross), not generic "vacation pay" |
| Kamer van Koophandel (KvK) | Chamber of Commerce (KVK) | ثبت شرکت‌ها (KvK) | السجل التجاري الهولندي (KvK) | Kept as "KvK" acronym with a short explanatory gloss, since it's a specific Dutch institution with no foreign equivalent |
| Urencriterium | Hours criterion | معیار ساعات کار (زلفستندیگن‌آفترک) | معيار الساعات (لاستحقاق خصم الأعمال الحرة) | **flagged for review** — Dutch self-employment tax concept with no direct fa/ar equivalent; translation describes the mechanism rather than naming an established term |
| Boekjaar | Financial year | سال مالی | السنة المالية | |
| Begroting | Budget | بودجه | الموازنة | |

## Status/workflow labels (recurring across many pages)

| Dutch | English | Persian | Arabic | Notes |
|---|---|---|---|---|
| Geëxtraheerd | Extracted | استخراج‌شده | مستخرج | |
| Beoordeling nodig | Needs review | نیازمند بررسی | بحاجة إلى مراجعة | |
| Duplicaten | Duplicates | موارد تکراری | مكررات | **flagged for review** — one fork batch's draft used "التكرارات" (definite article); resolved to indefinite "مكررات" as more natural for a status label during merge, but not independently verified |
| Mislukt | Failed | ناموفق | فشل | |
| Goedgekeurd | Approved | تأییدشده | معتمد | |

## Known open items for a native-speaker reviewer

1. **Numeral system in Persian/Arabic UI text**: some strings use
   Eastern Arabic-Indic digits (۰–۹ / ٠–٩) in example/placeholder text
   (e.g. scenario-comparison examples), others use Western digits
   (0–9) for amounts and codes. This is inconsistent by region (Gulf
   vs. Levant/Egypt convention differs) and was a deliberate
   judgment call during translation, not a verified regional choice.
2. **Debit/credit, counterparty terminology** — see table above.
3. **Urencriterium (hours criterion)** — Dutch self-employment-specific
   concept with no established fa/ar term; current translations
   describe the mechanism, which a reviewer may want replaced with
   whatever term (if any) the target market's own tax software uses.
4. Every VAT-box description (`report_i18n.py`'s `box_descriptions`)
   is a reader-aid translation of a Belastingdienst box label, not an
   official rendering — there is no official Belastingdienst fa/ar
   terminology to match against.

## Where the actual strings live

- Frontend UI chrome: `frontend/messages/{nl,en,fa,ar}.json` (next-intl
  dictionaries, ~1,377 keys each as of Phase 16.2).
- PDF/XLSX report content: `backend/app/reporting/report_i18n.py`.
- Backend-generated dashboard messages: `backend/app/core/messages_i18n.py`.

Keep this document's tables in sync with those files' actual values —
if a term's translation changes in code, update the row here in the
same change.
