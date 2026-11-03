"""Jaaropgaaf (annual statement) PDF, reusing PdfReportBuilder like
payslip_report.py -- a sum of already-calculated payslip figures, not a
new calculation."""

from datetime import datetime, timezone

from app.models.company import Company
from app.models.employee import Employee
from app.reporting.pdf_builder import PdfReportBuilder


def render_annual_statement_pdf(company: Company, employee: Employee, statement: dict) -> bytes:
    pdf = PdfReportBuilder(
        title="Jaaropgaaf / Annual Statement", company_name=company.name,
        subtitle=f"Tax year {statement['tax_year']}",
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )

    pdf.heading("Employer")
    pdf.key_value_row("Company", company.name)
    pdf.key_value_row("VAT number", company.vat_number or "n/a")
    pdf.key_value_row("KVK number", company.kvk_number or "n/a")

    pdf.heading("Employee")
    pdf.key_value_row("Name", employee.full_name)
    pdf.key_value_row("Employee number", employee.employee_number)
    pdf.key_value_row("Tax year", str(statement["tax_year"]))
    pdf.key_value_row("Payslips included", str(statement["number_of_payslips"]))

    pdf.heading("Totals for the year")
    pdf.key_value_row("Gross salary", str(statement["gross_salary"]), highlight=True)
    pdf.key_value_row("Taxable wage", str(statement["taxable_wage"]))
    pdf.key_value_row("Wage tax + national insurance withheld", str(statement["wage_tax_and_national_insurance"]))
    pdf.key_value_row("General tax credit applied", str(statement["general_tax_credit_applied"]))
    pdf.key_value_row("Labor tax credit applied", str(statement["labor_tax_credit_applied"]))
    pdf.key_value_row("Pension deduction", str(statement["pension_deduction"]))
    pdf.key_value_row("Other deductions", str(statement["other_deductions"]))
    pdf.key_value_row("Net salary paid", str(statement["net_salary"]), highlight=True)

    pdf.heading("Employer cost (informational)")
    pdf.key_value_row("Employer Zvw levy", str(statement["employer_levy_zvw"]))
    pdf.key_value_row("Total employer cost", str(statement["employer_costs_total"]))

    pdf.heading("Note")
    pdf.text(statement["note"], size=8, color=(0.35, 0.39, 0.46))

    return pdf.to_bytes()
