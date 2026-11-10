"""phase_10_index_tenant_and_company_filter_columns

A performance review (requested by Phase 10) found that essentially every
company_id/tenant_id column in this schema -- the columns EVERY query in a
multi-tenant app filters on -- had no index at all, meaning full table
scans on every list/filter request as data grows. This migration adds
one b-tree index per such column (54 total), plus payslips.employee_id
and payslips.payroll_run_id specifically (hot paths added this phase:
the cumulative-wage-this-year lookup in payroll_service.add_payslip,
the annual-statement aggregation, and the employee self-service
payslip list all filter on these).

Deliberately NOT mirrored as index=True on the ~30 affected SQLAlchemy
model columns (that would be a much larger, purely mechanical diff for
no behavioral difference) -- a future `alembic revision --autogenerate`
run will therefore propose DROPPING these indexes, since the model
metadata doesn't declare them. A reviewer running autogenerate should
discard any auto-generated drop_index calls for the indexes created
here rather than applying them.

On a large existing production table, consider running the equivalent
CREATE INDEX CONCURRENTLY statements outside of Alembic's transaction
instead, to avoid holding a lock during creation -- not done here since
plain CREATE INDEX is simpler and this is not yet a large-data
production deployment.

Revision ID: 3853605281ec
Revises: 5e014e66b859
Create Date: 2026-11-03 11:55:17.213633

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '3853605281ec'
down_revision: Union[str, None] = '5e014e66b859'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

_INDEXES = [
    ("ix_accountant_notes_company_id", "accountant_notes", ["company_id"]),
    ("ix_accountant_notes_tenant_id", "accountant_notes", ["tenant_id"]),
    ("ix_accounting_transactions_company_id", "accounting_transactions", ["company_id"]),
    ("ix_accounting_transactions_tenant_id", "accounting_transactions", ["tenant_id"]),
    ("ix_anomaly_flags_company_id", "anomaly_flags", ["company_id"]),
    ("ix_anomaly_flags_tenant_id", "anomaly_flags", ["tenant_id"]),
    ("ix_audit_logs_tenant_id", "audit_logs", ["tenant_id"]),
    ("ix_bank_accounts_tenant_id", "bank_accounts", ["tenant_id"]),
    ("ix_bank_import_batches_company_id", "bank_import_batches", ["company_id"]),
    ("ix_bank_import_batches_tenant_id", "bank_import_batches", ["tenant_id"]),
    ("ix_bank_transactions_company_id", "bank_transactions", ["company_id"]),
    ("ix_bank_transactions_tenant_id", "bank_transactions", ["tenant_id"]),
    ("ix_budgets_company_id", "budgets", ["company_id"]),
    ("ix_budgets_tenant_id", "budgets", ["tenant_id"]),
    ("ix_categorization_rules_company_id", "categorization_rules", ["company_id"]),
    ("ix_categorization_rules_tenant_id", "categorization_rules", ["tenant_id"]),
    ("ix_companies_tenant_id", "companies", ["tenant_id"]),
    ("ix_company_legal_forms_company_id", "company_legal_forms", ["company_id"]),
    ("ix_customers_company_id", "customers", ["company_id"]),
    ("ix_documents_company_id", "documents", ["company_id"]),
    ("ix_documents_tenant_id", "documents", ["tenant_id"]),
    ("ix_employee_timesheet_entries_company_id", "employee_timesheet_entries", ["company_id"]),
    ("ix_employee_timesheet_entries_employee_id", "employee_timesheet_entries", ["employee_id"]),
    ("ix_employee_timesheet_entries_tenant_id", "employee_timesheet_entries", ["tenant_id"]),
    ("ix_employees_company_id", "employees", ["company_id"]),
    ("ix_employees_tenant_id", "employees", ["tenant_id"]),
    ("ix_entrepreneur_hours_entries_company_id", "entrepreneur_hours_entries", ["company_id"]),
    ("ix_entrepreneur_hours_entries_tenant_id", "entrepreneur_hours_entries", ["tenant_id"]),
    ("ix_financial_years_company_id", "financial_years", ["company_id"]),
    ("ix_loonheffingen_declarations_company_id", "loonheffingen_declarations", ["company_id"]),
    ("ix_loonheffingen_declarations_tenant_id", "loonheffingen_declarations", ["tenant_id"]),
    ("ix_manual_balance_sheet_items_company_id", "manual_balance_sheet_items", ["company_id"]),
    ("ix_manual_balance_sheet_items_tenant_id", "manual_balance_sheet_items", ["tenant_id"]),
    ("ix_partners_company_id", "partners", ["company_id"]),
    ("ix_payment_matches_company_id", "payment_matches", ["company_id"]),
    ("ix_payment_matches_tenant_id", "payment_matches", ["tenant_id"]),
    ("ix_payments_company_id", "payments", ["company_id"]),
    ("ix_payments_tenant_id", "payments", ["tenant_id"]),
    ("ix_payroll_runs_company_id", "payroll_runs", ["company_id"]),
    ("ix_payroll_runs_tenant_id", "payroll_runs", ["tenant_id"]),
    ("ix_payslips_company_id", "payslips", ["company_id"]),
    ("ix_payslips_employee_id", "payslips", ["employee_id"]),
    ("ix_payslips_payroll_run_id", "payslips", ["payroll_run_id"]),
    ("ix_payslips_tenant_id", "payslips", ["tenant_id"]),
    ("ix_recurring_patterns_company_id", "recurring_patterns", ["company_id"]),
    ("ix_recurring_patterns_tenant_id", "recurring_patterns", ["tenant_id"]),
    ("ix_scenarios_company_id", "scenarios", ["company_id"]),
    ("ix_scenarios_tenant_id", "scenarios", ["tenant_id"]),
    ("ix_shareholders_company_id", "shareholders", ["company_id"]),
    ("ix_upload_batches_company_id", "upload_batches", ["company_id"]),
    ("ix_upload_batches_tenant_id", "upload_batches", ["tenant_id"]),
    ("ix_users_tenant_id", "users", ["tenant_id"]),
    ("ix_vat_returns_company_id", "vat_returns", ["company_id"]),
    ("ix_vat_returns_tenant_id", "vat_returns", ["tenant_id"]),
]


def upgrade() -> None:
    for index_name, table_name, columns in _INDEXES:
        op.create_index(index_name, table_name, columns)


def downgrade() -> None:
    for index_name, table_name, columns in _INDEXES:
        op.drop_index(index_name, table_name=table_name)
