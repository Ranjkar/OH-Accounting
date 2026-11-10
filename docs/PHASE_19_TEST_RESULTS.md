# Phase 19 — Test Results

Commands actually executed, with actual output.

---

## 1. New regression suite

```
$ cd backend && ANTHROPIC_API_KEY="" .venv/bin/python -m pytest tests/test_phase19_accounting_fixes.py \
      -p no:randomly -q --no-header

29 passed, 12 warnings in 4.04s
```

`ANTHROPIC_API_KEY=""` is set for every pytest invocation in Phases 17–20. Audit finding 7.13 identified two tests — `test_automation_api.py:131` and `test_financial_reports_api.py:278`, both named `..._uses_stub_provider_without_api_key` — that do not null the key and therefore make real, billable calls to `api.anthropic.com` when `backend/.env` supplies one, which it does. Nulling it forces the stub path those tests claim to exercise. Recorded as a deviation from a bare `pytest` invocation; fixing the leak itself is roadmap Tier 2.4.

### Breakdown of the 29

| Fix | Tests | Assertions of note |
|---|---|---|
| 7.3 `previous_period` | 12 | All four quarters step back exactly; four month cases including February in leap and non-leap years; annual across a leap year; twelve monthly previous periods tile Dec 2025 – Nov 2026 with no gap, no overlap and a reconciling day count; non-calendar range falls back to day arithmetic; agreement with the independent `resolve_period` implementation |
| 8.8 payment validation | 4 | Schema rejects `0`, `-0.01`, `-1210.00`; accepts `1210.00`; API returns `422`, creates no `Payment` row, leaves `payment_status == UNPAID`, then a legitimate payment returns `201` |
| 6.2 cash-based VAT | 8 | Unpaid → `None`; payment assigns the period containing the **payment** date (Feb invoice paid in Oct → Q4; May payment → Q2); invoice-based period never moved; already-assigned never reassigned; return is `0` before payment and `1000.00 / 210.00 / 210.00` after; API path; bank-match path (August booking → Q3) |
| 6.6 double-posting | 3 | Two transactions cannot share a `source_document_id` (`IntegrityError`); many may have `NULL`; the constraint is declared on the **model** so `create_all`-built test schemas enforce it |

---

## 2. Mutation testing — proof the tests detect the bugs

### 2.1 `previous_period`

Reverted to the original day arithmetic by string replacement, with the file copied to `/tmp/p19_fr.py` and checksummed first:

```
reverted previous_period to day arithmetic

--- tests against the BUGGY version ---
FAILED test_previous_period_of_q1_is_exactly_q4_of_the_prior_year
FAILED test_every_quarter_steps_back_to_the_exact_previous_quarter[current0-expected0]
FAILED test_every_quarter_steps_back_to_the_exact_previous_quarter[current1-expected1]
FAILED test_every_quarter_steps_back_to_the_exact_previous_quarter[current2-expected2]
FAILED test_every_month_steps_back_to_the_exact_previous_month[current0-expected0]
FAILED test_every_month_steps_back_to_the_exact_previous_month[current1-expected1]
FAILED test_every_month_steps_back_to_the_exact_previous_month[current2-expected2]
FAILED test_annual_period_spanning_a_leap_year_steps_back_to_the_exact_prior_year
FAILED test_twelve_monthly_previous_periods_tile_the_prior_twelve_months_with_no_gaps_or_overlaps
FAILED test_previous_period_agrees_with_resolve_period_for_every_quarter

10 failed, 3 passed, 16 deselected, 9 warnings in 0.10s

--- restore ---
/tmp/p19_fr.py: OK
29 passed, 12 warnings in 3.92s
```

**10 failures against the buggy version; restore verified by SHA-256; 29 passing again.** The three that passed against the buggy version are the non-calendar fallback case and two that do not exercise the changed path — correct in both versions.

### 2.2 Cash-based VAT and the unique constraint

Not mutation-tested by reverting source, for stated reasons:

- **6.2** — the pre-fix state is a *missing call*, not wrong code. There is nothing to revert to; removing the two new call sites would simply restore the absence. The tests assert the observable consequence directly (`vat_period_id is None` → `== q2.id`, and a return going from `0.00` to `210.00`), and the dead `determine_vat_period` import at `transactions.py:8` is the documented evidence that the call was always intended.
- **6.6** — reverting would mean removing a `UniqueConstraint` from model metadata, which changes the schema the whole suite runs against. The constraint's effect is asserted directly: `pytest.raises(IntegrityError)` on a second posting of the same document, and `test_the_unique_constraint_is_declared_on_the_model` pins that it lives in model metadata and not only in the migration — because tests build the schema with `create_all`, a migration-only constraint would never be exercised (audit 7.14).

---

## 3. One pre-existing test was modified

`tests/test_financial_reports.py::test_previous_period_same_length` asserted:

```python
assert (prev.end - prev.start).days == (period.end - period.start).days
```

For February 2027 that demands a 28-day predecessor ending 31 January — i.e. **4–31 January**, silently dropping 1–3 January. It is only satisfiable by the buggy implementation. **This is the only pre-existing test changed in Phases 17–20.**

It was renamed to `test_previous_period_is_the_whole_preceding_calendar_period`, its first assertion (`prev.end == date(2027, 1, 31)`) kept unchanged because it was always correct, and a docstring added recording precisely what the second assertion got wrong. Two sibling tests were added for the quarter and leap-year cases.

The failure that surfaced it, verbatim:

```
>       assert (prev.end - prev.start).days == (period.end - period.start).days
E       assert 30 == 27
E        +  where 30 = (datetime.date(2027, 1, 31) - datetime.date(2027, 1, 1)).days
E        +  and   27 = (datetime.date(2027, 2, 28) - datetime.date(2027, 2, 1)).days
```

---

## 4. Full backend regression

Run after all Phase 19 changes:

```
$ cd backend && ANTHROPIC_API_KEY="" .venv/bin/python -m pytest tests/ -p no:randomly -q --no-header -rf

662 passed, 986 warnings in 286.56s (0:04:46)
failures: 0
```

**Count reconciliation:**

| | Tests |
|---|---|
| Baseline before Phase 17 (540 functions + 2 parametrisation expansions) | 542 |
| Phase 17.2 cross-tenant isolation | +22 |
| Phase 17.3 logout revocation | +1 |
| Phase 17.4 security configuration | +59 |
| Phase 19 accounting fixes | +29 |
| Phase 19 `previous_period` test replaced by three | +2 |
| Phase 20.3 end-to-end scenarios | +7 |
| **Total** | **662** ✓ |

An intermediate run partway through Phase 19 returned `1 failed, 652 passed` — the single failure being `test_previous_period_same_length`, resolved in §3. No other test failed at any point, so **the new unique constraint and the payment validation broke nothing** in the existing 624-test suite.

**No test was skipped, xfailed or deselected.** The five KVK network tests ran and passed, meaning `api.kvk.nl` was reachable at execution time.

---

## 5. Static verification of the changed modules

```
$ .venv/bin/alembic heads
e4f7a9c2b1d8 (head)                     # exactly one head

$ .venv/bin/python -c "
    import app.main
    from app.accounting import period_assignment, financial_reports, reconciliation_service, ledger_service
    from app.models.accounting import AccountingTransaction
    from app.schemas.accounting import PaymentCreate
    print('imports OK'); print('table_args:', AccountingTransaction.__table_args__)"
imports OK
table_args: (UniqueConstraint(Column('source_document_id', Integer(), ForeignKey('documents.id'),
             table=<accounting_transactions>)),)
```

No circular import was introduced by `period_assignment` gaining an `AccountingTransaction` import or by `reconciliation_service` importing `period_assignment`.

Schema-level validation, executed directly:

```
rejected amount 0     OK
rejected amount -5    OK
accepted 1210.00      OK
```

---

## 6. Migration verification

Full transcript in `PHASE_18_TEST_RESULTS.md` §1. Summary:

| Step | Result |
|---|---|
| `createdb` scratch → `alembic upgrade head` | 23 migrations, 48 tables, version `e4f7a9c2b1d8` |
| Constraint present in `pg_constraint` | `uq_accounting_transaction_source_document` |
| `alembic downgrade -1` | constraint dropped, version back to `d90e97d4bc35` |
| `alembic upgrade head` again | constraint re-created |
| `dropdb` scratch | clean |

The migration's duplicate-refusal path was **not exercised** — it requires a database that already contains duplicate postings, and manufacturing one would mean writing bad financial data. It is covered by code review only. Recorded as a gap.

---

## 7. Not executed

1. **No concurrency test.** The double-posting race is verified at the database level (`IntegrityError` on a second insert), not by firing simultaneous HTTP requests. A true race test needs two sessions and is roadmap work.
2. **The migration's duplicate-refusal branch** (§6).
3. **No FX or manual-balance-sheet-item tests**, because neither was fixed (§5.3, §5.4 of the accounting review).
4. **No 2026 tax-rule tests**, because no 2026 rule set was written (§5.5).
5. **No coverage measurement** — `pytest-cov`/`coverage` are in neither `requirements.txt` nor the venv, so no coverage figure can be given for the new tests or the codebase.
6. **No backend linter or type checker** — `ruff`, `mypy`, `flake8`, `black` and `pylint` are all absent and there is no config file anywhere. Static checking was limited to `py_compile` and import verification.
