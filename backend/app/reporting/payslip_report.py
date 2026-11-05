"""Dutch payslip (loonstrook) PDF, reusing PdfReportBuilder -- no new PDF
library. Every required field from the engineering brief is included."""

from datetime import datetime, timezone

from app.models.company import Company
from app.models.employee import Employee
from app.models.payroll import PayrollRun, Payslip
from app.reporting.pdf_builder import PdfReportBuilder
from app.reporting.report_i18n import DEFAULT_LOCALE, t


def render_payslip_pdf(company: Company, employee: Employee, run: PayrollRun, payslip: Payslip, locale: str = DEFAULT_LOCALE) -> bytes:
    ns = "payrollDoc"
    na = t(locale, "common", "na")
    # period_type.value (e.g. "MONTHLY") is an enum identifier, kept
    # exactly as stored -- never translated, same rule as VAT box codes.
    period_label = f"{run.period_type.value} {t(locale, ns, 'period_label').lower()} {run.period_number}/{run.period_year}"
    pdf = PdfReportBuilder(
        title=t(locale, ns, "payslip_title"), company_name=company.name, subtitle=period_label,
        generated_at=datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        locale=locale,
    )

    pdf.heading(t(locale, ns, "employer_heading"))
    pdf.key_value_row(t(locale, ns, "company_label"), company.name)
    pdf.key_value_row(t(locale, ns, "vat_number_label"), company.vat_number or na)
    pdf.key_value_row(t(locale, ns, "kvk_number_label"), company.kvk_number or na)

    pdf.heading(t(locale, ns, "employee_heading"))
    pdf.key_value_row(t(locale, ns, "name_label"), employee.full_name)
    pdf.key_value_row(t(locale, ns, "employee_number_label"), employee.employee_number)
    pdf.key_value_row(t(locale, ns, "job_title_label"), employee.job_title or na)
    pdf.key_value_row(t(locale, ns, "contracted_hours_label"), str(employee.contracted_hours_per_week or na))

    pdf.heading(t(locale, ns, "period_heading"))
    pdf.key_value_row(t(locale, ns, "period_label"), period_label)
    pdf.key_value_row(t(locale, ns, "tax_year_used_label"), str(run.tax_year))
    if payslip.voided:
        pdf.text(t(locale, ns, "voided_prefix", reason=payslip.void_reason), color=(0.73, 0.11, 0.11))
    if payslip.corrects_payslip_id:
        pdf.text(t(locale, ns, "correction_of", id=payslip.corrects_payslip_id), size=8)

    pdf.heading(t(locale, ns, "earnings_heading"))
    pdf.key_value_row(t(locale, ns, "gross_salary_label"), str(payslip.gross_salary), highlight=True)
    pdf.key_value_row(t(locale, ns, "paid_hours_label"), str(payslip.paid_hours or na))
    pdf.key_value_row(t(locale, ns, "overtime_hours_label"), str(payslip.overtime_hours))
    pdf.key_value_row(t(locale, ns, "overtime_amount_label"), str(payslip.overtime_amount))
    pdf.key_value_row(t(locale, ns, "holiday_allowance_label"), str(payslip.holiday_allowance))
    pdf.key_value_row(t(locale, ns, "bonus_label"), str(payslip.bonus_amount))
    pdf.key_value_row(t(locale, ns, "expense_reimbursement_label"), str(payslip.expense_reimbursement))

    pdf.heading(t(locale, ns, "deductions_heading"))
    pdf.key_value_row(t(locale, ns, "taxable_wage_label"), str(payslip.taxable_wage))
    pdf.key_value_row(t(locale, ns, "wage_tax_label"), str(payslip.wage_tax_and_national_insurance))
    pdf.key_value_row(t(locale, ns, "general_tax_credit_label"), str(payslip.general_tax_credit_applied))
    pdf.key_value_row(t(locale, ns, "labor_tax_credit_label"), str(payslip.labor_tax_credit_applied))
    pdf.key_value_row(t(locale, ns, "pension_deduction_label"), str(payslip.pension_deduction))
    pdf.key_value_row(t(locale, ns, "other_deductions_label"), str(payslip.other_deductions))

    pdf.heading(t(locale, ns, "net_heading"))
    pdf.key_value_row(t(locale, ns, "net_salary_label"), str(payslip.net_salary), highlight=True)

    pdf.heading(t(locale, ns, "employer_cost_heading"))
    pdf.key_value_row(t(locale, ns, "employer_zvw_estimate_label"), str(payslip.employer_levy_zvw))
    pdf.key_value_row(t(locale, ns, "total_employer_cost_estimate_label"), str(payslip.employer_costs_total))

    if payslip.calculation_notes:
        pdf.heading(t(locale, ns, "calculation_notes_heading"))
        pdf.text(payslip.calculation_notes, size=7, color=(0.35, 0.39, 0.46))

    return pdf.to_bytes()
