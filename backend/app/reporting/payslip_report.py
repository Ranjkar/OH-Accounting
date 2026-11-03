"""Dutch payslip (loonstrook) PDF, reusing PdfReportBuilder -- no new PDF
library. Every required field from the engineering brief is included."""

from datetime import datetime, timezone

from app.models.company import Company
from app.models.employee import Employee
from app.models.payroll import PayrollRun, Payslip
from app.reporting.pdf_builder import PdfReportBuilder


def render_payslip_pdf(company: Company, employee: Employee, run: PayrollRun, payslip: Payslip) -> bytes:
    period_label = f"{run.period_type.value} period {run.period_number}/{run.period_year}"
    pdf = PdfReportBuilder(
        title="Loonstrook / Payslip", company_name=company.name, subtitle=period_label,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
    )

    pdf.heading("Employer")
    pdf.key_value_row("Company", company.name)
    pdf.key_value_row("VAT number", company.vat_number or "n/a")
    pdf.key_value_row("KVK number", company.kvk_number or "n/a")

    pdf.heading("Employee")
    pdf.key_value_row("Name", employee.full_name)
    pdf.key_value_row("Employee number", employee.employee_number)
    pdf.key_value_row("Job title", employee.job_title or "n/a")
    pdf.key_value_row("Contracted hours/week", str(employee.contracted_hours_per_week or "n/a"))

    pdf.heading("Period")
    pdf.key_value_row("Period", period_label)
    pdf.key_value_row("Tax year used", str(run.tax_year))
    if payslip.voided:
        pdf.text(f"VOIDED -- {payslip.void_reason}", color=(0.73, 0.11, 0.11))
    if payslip.corrects_payslip_id:
        pdf.text(f"Correction of payslip #{payslip.corrects_payslip_id}", size=8)

    pdf.heading("Earnings")
    pdf.key_value_row("Gross salary", str(payslip.gross_salary), highlight=True)
    pdf.key_value_row("Paid hours", str(payslip.paid_hours or "n/a"))
    pdf.key_value_row("Overtime hours", str(payslip.overtime_hours))
    pdf.key_value_row("Overtime amount", str(payslip.overtime_amount))
    pdf.key_value_row("Holiday allowance", str(payslip.holiday_allowance))
    pdf.key_value_row("Bonus", str(payslip.bonus_amount))
    pdf.key_value_row("Expense reimbursement (untaxed)", str(payslip.expense_reimbursement))

    pdf.heading("Deductions")
    pdf.key_value_row("Taxable wage", str(payslip.taxable_wage))
    pdf.key_value_row("Wage tax + national insurance", str(payslip.wage_tax_and_national_insurance))
    pdf.key_value_row("General tax credit applied", str(payslip.general_tax_credit_applied))
    pdf.key_value_row("Labor tax credit applied", str(payslip.labor_tax_credit_applied))
    pdf.key_value_row("Pension deduction", str(payslip.pension_deduction))
    pdf.key_value_row("Other deductions", str(payslip.other_deductions))

    pdf.heading("Net")
    pdf.key_value_row("Net salary", str(payslip.net_salary), highlight=True)

    pdf.heading("Employer cost (informational)")
    pdf.key_value_row("Employer Zvw levy (estimate)", str(payslip.employer_levy_zvw))
    pdf.key_value_row("Total employer cost (estimate)", str(payslip.employer_costs_total))

    if payslip.calculation_notes:
        pdf.heading("Calculation notes")
        pdf.text(payslip.calculation_notes, size=7, color=(0.35, 0.39, 0.46))

    return pdf.to_bytes()
