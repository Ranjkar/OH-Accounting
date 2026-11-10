"""Jaaropgaaf (annual statement) PDF, reusing PdfReportBuilder like
payslip_report.py -- a sum of already-calculated payslip figures, not a
new calculation."""

from datetime import datetime, timezone

from app.models.company import Company
from app.models.employee import Employee
from app.reporting.pdf_builder import PdfReportBuilder
from app.reporting.report_i18n import DEFAULT_LOCALE, t


def render_annual_statement_pdf(company: Company, employee: Employee, statement: dict, locale: str = DEFAULT_LOCALE) -> bytes:
    ns = "payrollDoc"
    pdf = PdfReportBuilder(
        title=t(locale, ns, "annual_statement_title"), company_name=company.name,
        subtitle=f"{t(locale, ns, 'tax_year_label')} {statement['tax_year']}",
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        locale=locale,
    )

    pdf.heading(t(locale, ns, "employer_heading"))
    pdf.key_value_row(t(locale, ns, "company_label"), company.name)
    pdf.key_value_row(t(locale, ns, "vat_number_label"), company.vat_number or t(locale, "common", "na"))
    pdf.key_value_row(t(locale, ns, "kvk_number_label"), company.kvk_number or t(locale, "common", "na"))

    pdf.heading(t(locale, ns, "employee_heading"))
    pdf.key_value_row(t(locale, ns, "name_label"), employee.full_name)
    pdf.key_value_row(t(locale, ns, "employee_number_label"), employee.employee_number)
    pdf.key_value_row(t(locale, ns, "tax_year_label"), str(statement["tax_year"]))
    pdf.key_value_row(t(locale, ns, "payslips_included_label"), str(statement["number_of_payslips"]))

    pdf.heading(t(locale, ns, "totals_heading"))
    pdf.key_value_row(t(locale, ns, "gross_salary_label"), str(statement["gross_salary"]), highlight=True)
    pdf.key_value_row(t(locale, ns, "taxable_wage_label"), str(statement["taxable_wage"]))
    pdf.key_value_row(t(locale, ns, "wage_tax_label"), str(statement["wage_tax_and_national_insurance"]))
    pdf.key_value_row(t(locale, ns, "general_tax_credit_label"), str(statement["general_tax_credit_applied"]))
    pdf.key_value_row(t(locale, ns, "labor_tax_credit_label"), str(statement["labor_tax_credit_applied"]))
    pdf.key_value_row(t(locale, ns, "pension_deduction_label"), str(statement["pension_deduction"]))
    pdf.key_value_row(t(locale, ns, "other_deductions_label"), str(statement["other_deductions"]))
    pdf.key_value_row(t(locale, ns, "net_salary_label"), str(statement["net_salary"]), highlight=True)

    pdf.heading(t(locale, ns, "employer_cost_heading"))
    pdf.key_value_row(t(locale, ns, "employer_zvw_label"), str(statement["employer_levy_zvw"]))
    pdf.key_value_row(t(locale, ns, "total_employer_cost_label"), str(statement["employer_costs_total"]))

    pdf.heading(t(locale, ns, "note_heading"))
    pdf.text(statement["note"], size=8, color=(0.35, 0.39, 0.46))

    return pdf.to_bytes()
