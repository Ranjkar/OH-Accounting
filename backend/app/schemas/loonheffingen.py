from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, ConfigDict

from app.models.enums import LoonheffingenDeclarationStatus


class LoonheffingenDeclarationOut(BaseModel):
    id: int
    company_id: int
    payroll_run_id: int
    status: LoonheffingenDeclarationStatus
    total_gross_wages: Decimal
    total_wage_tax_withheld: Decimal
    total_employer_premiums: Decimal
    total_payable: Decimal
    validation_errors: str | None
    reviewed_by_user_id: int | None
    reviewed_at: datetime | None
    approved_by_user_id: int | None
    approved_at: datetime | None
    submission_reference: str | None
    submitted_at: datetime | None
    government_response_reference: str | None
    government_response_at: datetime | None
    rejection_reason: str | None

    model_config = ConfigDict(from_attributes=True)


class RecordSubmissionRequest(BaseModel):
    submission_reference: str


class RecordGovernmentResponseRequest(BaseModel):
    accepted: bool
    response_reference: str
    rejection_reason: str | None = None
