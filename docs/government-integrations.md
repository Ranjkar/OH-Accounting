# Dutch government integrations

## Architecture

**SBR → Digipoort → Belastingdienst.** Digipoort (operated by Logius) is the central message-handling facility that receives, validates, and confirms receipt of government-bound messages. SBR (Standard Business Reporting) is the submission channel using Digipoort as transport; XBRL is the report file format for BTW/ICP filings specifically — **loonheffingen historically used XML, not XBRL**, via Digipoort since 2017 (full SBR/XBRL migration for loonheffingen was "planned for later" per sbr-nl.nl as of this research; current status unverified this session). **Message formats are not uniform across declaration types** — never assume otherwise.

A **technical receipt from Digipoort ("ontvangstbevestiging") confirms only that a message arrived, not that the Belastingdienst accepted the filing.** This system reflects that distinction: `LoonheffingenDeclaration.status` has a `SUBMITTED` state distinct from `ACCEPTED`/`REJECTED`, and moving to either of the latter requires an explicit `government_response_reference` supplied by a human — never inferred from the act of sending.

## Certificate requirements

Production SBR/Digipoort access requires a **PKIoverheid "services server certificate"** from a Logius-listed CA (confirmed on belastingdienst.nl's own "Aansluiten op SBR" page). For the **preproduction/test** environment, a free Logius test certificate (or PKIoverheid/PKItrial cert) is available by request — no paid production certificate needed to test. **Logius is migrating to a new Digipoort; the old one retires April 1, 2026, with full G4-certificate support from ~Q1 2027** — relevant to any real onboarding timeline.

## Status: loonheffingen (payroll tax)

**IMPLEMENTED** (declaration lifecycle, locally): `app/accounting/loonheffingen_service.py` implements the full Draft → Validation → Accountant Review → Approved → Ready for Submission → Submitted → Accepted/Rejected state machine against real payroll data.

**BLOCKED BY EXTERNAL REQUIREMENT** (actual Digipoort transmission): no PKIoverheid/Logius test certificate was requested or obtained this session (requires an external email-based registration process, not something obtainable via automated tooling). `record_submission()` and `record_government_response()` require the caller to supply real references **because this system has no way to obtain them itself** — it never fabricates a successful submission.

## Status: BTW/VAT, ICP, income tax, corporate tax

**NOT IMPLEMENTED** (declaration lifecycle matching loonheffingen's) this phase — VAT already has its own real, working `VatReturn` draft→locked workflow from earlier phases (reused, not duplicated), but it does not yet transmit to Digipoort either. ICP is **NOT_TRACKED** (surfaced honestly in `/tax-centre/overview`, not fabricated). Income/corporate tax have estimate-only endpoints, no filing workflow.

## KVK (Chamber of Commerce)

**SANDBOX VERIFIED.** `app/services/kvk_provider.py` calls the real, officially published KVK API test sandbox (`api.kvk.nl/test`) using KVK's own publicly documented test API key — fetched directly from `developers.kvk.nl/documentation/testing` and exercised over the network this session (`tests/test_kvk_integration.py`, not mocked). Production requires a signed KVK agreement and a paid key (**€6.40/month + €0.02/query**, per KVK's own published pricing at `developers.kvk.nl/nl/pricing`). Scraping is explicitly prohibited by KVK's own terms (Databankenwet) and was never considered.

## Status summary

| Integration | Status |
|---|---|
| Loonheffingen declaration lifecycle (local) | IMPLEMENTED |
| Loonheffingen → Digipoort transmission | BLOCKED BY EXTERNAL REQUIREMENT (no test certificate) |
| BTW/VAT → Digipoort transmission | NOT IMPLEMENTED |
| ICP, income tax, corporate tax filing | NOT IMPLEMENTED |
| KVK company lookup | SANDBOX VERIFIED |
