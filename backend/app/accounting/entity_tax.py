"""Entity-specific Dutch tax estimation, built on top of
app.accounting.dutch_tax_rules. Never assumes every entity faces the same
taxes -- each function here corresponds to one LegalFormCode family and
only estimates the taxes that family is actually subject to. Every result
carries requires_accountant_confirmation=True; nothing here is a filing."""

from decimal import Decimal

from app.accounting import dutch_tax_rules as tax

ZERO = Decimal("0")


def estimate_sole_proprietor_income_tax(
    annual_profit: Decimal, hours_criterion_met: bool, is_starter: bool, rules: tax.DutchTaxRuleSet | None = None
) -> dict:
    """Eenmanszaak (and, per-partner, VOF/Maatschap/CV general partners)."""
    rules = rules or tax.get_rule_set()
    entrepreneur_deduction = tax.zelfstandigenaftrek_amount(rules, is_starter) if hours_criterion_met else ZERO
    profit_after_entrepreneur_deduction = max(annual_profit - entrepreneur_deduction, ZERO)
    mkb_exemption = tax.mkb_winstvrijstelling(profit_after_entrepreneur_deduction, rules)
    taxable_profit = max(profit_after_entrepreneur_deduction - mkb_exemption, ZERO)
    gross_income_tax = tax.calculate_box1_tax(taxable_profit, rules)
    general_tax_credit = tax.algemene_heffingskorting(taxable_profit, rules)
    net_income_tax = max(gross_income_tax - general_tax_credit, ZERO)

    return {
        "tax_year": rules.year,
        "annual_profit": annual_profit,
        "hours_criterion_met": hours_criterion_met,
        "entrepreneur_deduction_applied": entrepreneur_deduction,
        "mkb_winstvrijstelling_applied": mkb_exemption,
        "taxable_profit": taxable_profit,
        "gross_income_tax": gross_income_tax,
        "general_tax_credit": general_tax_credit,
        "net_income_tax": net_income_tax,
        "estimated_net_result": annual_profit - net_income_tax,
        "note": (
            "Entrepreneur deduction is only applied because hours_criterion_met=True was supplied -- this engine "
            "never assumes the urencriterium is met. Box-1 personal income tax only; does not include other "
            "personal income, mortgage interest, or other box 1/2/3 items."
            if hours_criterion_met
            else "No entrepreneur deduction applied -- the 1,225-hour urencriterium was not confirmed met."
        ),
        "requires_accountant_confirmation": True,
    }


def allocate_vof_profit(annual_profit: Decimal, partners: list[dict]) -> list[dict]:
    """partners: [{"name", "profit_share_percentage", "hours_criterion_met", "is_starter"}, ...].
    Never assumes equal shares or automatic entrepreneur-deduction eligibility -- both come from
    each partner's own record."""
    total_share = sum((Decimal(str(p["profit_share_percentage"])) for p in partners), ZERO)
    results = []
    for p in partners:
        share = Decimal(str(p["profit_share_percentage"]))
        partner_profit = (annual_profit * share / total_share).quantize(Decimal("0.01")) if total_share else ZERO
        estimate = estimate_sole_proprietor_income_tax(
            partner_profit, bool(p.get("hours_criterion_met")), bool(p.get("is_starter"))
        )
        results.append({"partner_name": p["name"], "profit_share_percentage": share, "allocated_profit": partner_profit, **estimate})
    return results


def estimate_bv_corporate_tax(annual_taxable_profit: Decimal, rules: tax.DutchTaxRuleSet | None = None) -> dict:
    rules = rules or tax.get_rule_set()
    corporate_tax = tax.calculate_corporate_tax(annual_taxable_profit, rules)
    return {
        "tax_year": rules.year,
        "annual_taxable_profit": annual_taxable_profit,
        "corporate_tax": corporate_tax,
        "retained_profit_after_tax": annual_taxable_profit - corporate_tax,
        "requires_accountant_confirmation": True,
    }


def estimate_dga_position(
    proposed_dga_salary: Decimal,
    comparable_role_salary: Decimal | None,
    highest_employee_salary: Decimal | None,
    dividend_declared: Decimal,
    rules: tax.DutchTaxRuleSet | None = None,
) -> dict:
    """DGA's personal position: box 1 on the gebruikelijk-loon salary, plus
    box 2 on any dividend. Never silently lowers the salary to minimize tax
    -- check_dga_customary_salary always reports the required minimum."""
    rules = rules or tax.get_rule_set()
    salary_check = tax.check_dga_customary_salary(proposed_dga_salary, comparable_role_salary, highest_employee_salary, rules)
    box1_tax = tax.calculate_box1_tax(proposed_dga_salary, rules)
    general_tax_credit = tax.algemene_heffingskorting(proposed_dga_salary, rules)
    net_box1_tax = max(box1_tax - general_tax_credit, ZERO)
    box2_tax = tax.calculate_box2_tax(dividend_declared, rules)

    return {
        "tax_year": rules.year,
        "salary_check": salary_check,
        "box1_gross_tax_on_salary": box1_tax,
        "general_tax_credit": general_tax_credit,
        "box1_net_tax_on_salary": net_box1_tax,
        "dividend_declared": dividend_declared,
        "box2_tax_on_dividend": box2_tax,
        "total_estimated_personal_tax": net_box1_tax + box2_tax,
        "requires_accountant_confirmation": True,
    }


def foundation_or_association_obligations_note(legal_form_name: str) -> dict:
    """Stichting/vereniging/VvE: never guesses whether an enterprise is
    being run -- always routes to an explicit accountant confirmation
    requirement instead of a number."""
    return {
        "legal_form": legal_form_name,
        "corporate_income_tax_applicable": None,
        "vat_applicable": None,
        "payroll_tax_applicable_if_employees": True,
        "note": (
            f"A {legal_form_name} is only subject to corporate income tax and/or VAT if and to the extent it runs "
            "an enterprise (onderneming) -- this depends on facts this system does not have (nature of activities, "
            "competition with commercial parties, surplus allocation). Never guessed; requires an accountant's "
            "assessment before any figure is estimated."
        ),
        "requires_accountant_confirmation": True,
    }
