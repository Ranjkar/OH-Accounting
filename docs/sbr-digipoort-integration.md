# SBR / Digipoort Integration — Research & Architecture

**Status: not implemented.** This is an investigation and a proposed architecture
only. Nothing in OnHolland submits a VAT return to the Belastingdienst, and
nothing simulates a successful submission. The VAT return workflow ends at
`locked` (Phase 3/4) — a locked return is the accountant's internally finalized
figure, ready to be filed through whatever channel the firm currently uses
outside this application.

## What SBR and Digipoort actually are

- **SBR (Standard Business Reporting)** is the Dutch government's standard for
  exchanging structured business reports — financial statements, VAT returns,
  statistics — with government bodies (Belastingdienst, KvK, CBS), expressed as
  XBRL instance documents against a published **Nederlandse Taxonomie (NT)**.
  The VAT return lives in the Belastingdienst ("BD") domain of that taxonomy.
- **Digipoort** is the government's secure message gateway. SBR messages to the
  Belastingdienst are transported through Digipoort using either the
  ebMS2-based "Digipoort Koppelvlak" (for software that submits in volume) or a
  simpler web portal flow for one-off submissions. Authentication uses a
  **PKIoverheid-certified SBR server certificate** issued to the submitting
  party by an accredited Certificate Authority — not a username/password.

## What would actually be required before any code could submit a return

1. **A PKIoverheid SBR certificate** issued to OnHolland (or to each accounting
   firm/tenant using the platform, depending on who is the legal submitter of
   record) — a real, audited, paid process through an accredited CA, not
   something this session can provision or simulate.
2. **Registration with Logius** (who operate Digipoort) as a software party,
   including passing their **SBR conformance/chain test suite** against their
   test (acceptance) environment before any production access is granted.
3. **A correct, current-year XBRL instance** built against the exact NT
   taxonomy version the Belastingdienst is accepting for that filing period —
   taxonomy versions change periodically and must be verified against current
   Logius/Belastingdienst documentation at implementation time, not assumed
   from training data.
4. **A legal/liability decision** by OnHolland about who is authorized to
   submit on a client's behalf, and under what explicit client authorization —
   this is a business and compliance decision, not an engineering one.
5. **Handling asynchronous acknowledgements**: Digipoort submission is not a
   simple request/response. A submission gets an immediate transport receipt
   (a "kwitantie" with a Digipoort reference), and the actual
   accepted/rejected processing status from the Belastingdienst arrives later,
   via polling or a callback, often with structured error codes requiring
   human handling.

None of this is available in this environment, and manufacturing a fake
version of any of it (a mock certificate, a simulated acknowledgement) would
violate the explicit instruction not to claim or simulate a working filing
integration.

## Proposed architecture, for when that groundwork exists

Keep the same separation the rest of the app already uses — AI/extraction,
deterministic calculation, and now *submission* as three distinct concerns
that never collapse into each other:

```
VatReturn (locked)  -->  FilingBuilder  -->  FilingSubmission  -->  Digipoort adapter
                         (XBRL instance)     (status tracking)      (real, certified,
                                                                      out of scope today)
```

- **`FilingBuilder`** (pure, deterministic, like `vat_engine.py`): takes a
  locked `VatReturn` and renders the XBRL instance against the current NT
  taxonomy. Testable entirely offline against known-good fixture XBRL — no
  network, no certificate needed to build and validate the document shape.
- **`FilingSubmission`** (a new table, analogous to `DocumentProcessingAttempt`):
  one row per submission attempt, with `status` (`not_submitted`, `submitted`,
  `acknowledged`, `accepted`, `rejected`, `error`), the Digipoort reference
  number once issued, and the raw acknowledgement/response payload for audit.
  This is the only part that would ever need to exist before a real adapter
  does — it lets the UI show "not yet filed" / "filed, awaiting confirmation"
  honestly without the adapter existing yet.
- **Digipoort adapter**: the actual ebMS2/certificate-authenticated transport.
  Built last, only once a real certificate and Logius registration exist, and
  only after passing their conformance test suite. Everything upstream of it
  is swappable/testable without it, same pattern as the AI and OCR provider
  abstractions elsewhere in this codebase.

**Hard rule carried through from Phase 3 onward, restated here explicitly:**
even once a real adapter exists, submission is never automatic. It requires
an explicit accountant action on an already-`locked` return, with its own
audit log entry, the same way `approve`/`lock` work today.
