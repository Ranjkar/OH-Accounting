"""Loonheffingen declaration workflow: Draft -> Validation -> Accountant
Review -> Approved -> Ready for Submission -> Submitted -> Accepted/Rejected.

There is no live SBR/Digipoort integration. "Submitted" only records that a
user has told this system a filing was made outside it (submission_reference
is a free-text field the user fills in, e.g. a Digipoort kenmerk) -- it is
never set automatically, and it is not the same as "Accepted". Moving to
Accepted/Rejected likewise requires an explicit government_response_reference
supplied by the caller. This system never marks a submission successful on
its own authority.

Totals are a pure aggregation of each payslip's own already-calculated
figures (reusing payroll_service/payroll_engine's output), never a second
tax calculation."""

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.models.enums import LoonheffingenDeclarationStatus, PayrollRunStatus
from app.models.loonheffingen import LoonheffingenDeclaration
from app.models.payroll import PayrollRun, Payslip


class LoonheffingenError(Exception):
    pass


def _non_voided_payslips(db: Session, run: PayrollRun) -> list[Payslip]:
    return db.query(Payslip).filter(Payslip.payroll_run_id == run.id, Payslip.voided.is_(False)).all()


def create_declaration(db: Session, run: PayrollRun) -> LoonheffingenDeclaration:
    existing = db.query(LoonheffingenDeclaration).filter(LoonheffingenDeclaration.payroll_run_id == run.id).first()
    if existing is not None:
        raise LoonheffingenError(f"A declaration already exists for payroll run {run.id}")

    payslips = _non_voided_payslips(db, run)
    gross = sum((p.gross_salary for p in payslips), Decimal("0.00"))
    wage_tax = sum((p.wage_tax_and_national_insurance for p in payslips), Decimal("0.00"))
    employer_premiums = sum((p.employer_costs_total - p.gross_salary for p in payslips), Decimal("0.00"))

    declaration = LoonheffingenDeclaration(
        tenant_id=run.tenant_id, company_id=run.company_id, payroll_run_id=run.id,
        total_gross_wages=gross, total_wage_tax_withheld=wage_tax, total_employer_premiums=employer_premiums,
        total_payable=wage_tax + employer_premiums,
    )
    db.add(declaration)
    db.flush()
    return declaration


def run_validation(db: Session, declaration: LoonheffingenDeclaration) -> list[str]:
    """Deterministic checks, not an LLM judgment call. Advances to
    ACCOUNTANT_REVIEW only when there are zero errors; otherwise stays at
    VALIDATION with the errors recorded, so a human must act on them."""
    if declaration.status not in (LoonheffingenDeclarationStatus.draft, LoonheffingenDeclarationStatus.validation):
        raise LoonheffingenError(f"Declaration is {declaration.status.value} -- validation only runs from DRAFT or VALIDATION")

    run = db.get(PayrollRun, declaration.payroll_run_id)
    payslips = _non_voided_payslips(db, run)

    errors: list[str] = []
    if run.status not in (PayrollRunStatus.approved, PayrollRunStatus.paid):
        errors.append(f"Payroll run is {run.status.value}, not APPROVED or PAID -- figures could still change.")
    if not payslips:
        errors.append("Payroll run has no non-voided payslips -- nothing to declare.")
    if declaration.total_gross_wages < 0 or declaration.total_wage_tax_withheld < 0:
        errors.append("Totals are negative -- this is not possible for a wage declaration, investigate the underlying payslips.")

    declaration.validation_errors = "; ".join(errors) if errors else None
    declaration.status = LoonheffingenDeclarationStatus.accountant_review if not errors else LoonheffingenDeclarationStatus.validation
    db.flush()
    return errors


def submit_for_review(db: Session, declaration: LoonheffingenDeclaration) -> None:
    """Explicit re-entry point if an accountant wants to re-trigger review
    after VALIDATION already passed and the declaration is sitting there."""
    if declaration.status != LoonheffingenDeclarationStatus.validation:
        raise LoonheffingenError(f"Declaration is {declaration.status.value}, not VALIDATION")
    if declaration.validation_errors:
        raise LoonheffingenError("Cannot move to accountant review while validation errors remain")
    declaration.status = LoonheffingenDeclarationStatus.accountant_review
    db.flush()


def approve(db: Session, declaration: LoonheffingenDeclaration, user_id: int) -> None:
    if declaration.status != LoonheffingenDeclarationStatus.accountant_review:
        raise LoonheffingenError(f"Declaration is {declaration.status.value}, not ACCOUNTANT_REVIEW")
    declaration.status = LoonheffingenDeclarationStatus.approved
    declaration.reviewed_by_user_id = user_id
    declaration.reviewed_at = datetime.now(timezone.utc)
    declaration.approved_by_user_id = user_id
    declaration.approved_at = datetime.now(timezone.utc)
    db.flush()


def mark_ready_for_submission(db: Session, declaration: LoonheffingenDeclaration) -> None:
    if declaration.status != LoonheffingenDeclarationStatus.approved:
        raise LoonheffingenError(f"Declaration is {declaration.status.value}, not APPROVED")
    declaration.status = LoonheffingenDeclarationStatus.ready_for_submission
    db.flush()


def record_submission(db: Session, declaration: LoonheffingenDeclaration, *, submission_reference: str, user_id: int) -> None:
    """Records that a user has filed this declaration OUTSIDE this system
    (e.g. via the accountant's own SBR/Digipoort software) and is telling us
    so. submission_reference must be a real, non-empty reference -- this is
    never set automatically."""
    if declaration.status != LoonheffingenDeclarationStatus.ready_for_submission:
        raise LoonheffingenError(f"Declaration is {declaration.status.value}, not READY_FOR_SUBMISSION")
    if not submission_reference or not submission_reference.strip():
        raise LoonheffingenError("submission_reference is required -- this system has no live submission integration")
    declaration.status = LoonheffingenDeclarationStatus.submitted
    declaration.submission_reference = submission_reference.strip()
    declaration.submitted_by_user_id = user_id
    declaration.submitted_at = datetime.now(timezone.utc)
    db.flush()


def record_government_response(
    db: Session, declaration: LoonheffingenDeclaration, *, accepted: bool,
    response_reference: str, rejection_reason: str | None = None,
) -> None:
    """Records the actual response received from the Belastingdienst -- this
    system cannot and does not fetch or guess that response itself."""
    if declaration.status != LoonheffingenDeclarationStatus.submitted:
        raise LoonheffingenError(f"Declaration is {declaration.status.value}, not SUBMITTED")
    if not response_reference or not response_reference.strip():
        raise LoonheffingenError("response_reference is required to record a government response")
    if not accepted and not rejection_reason:
        raise LoonheffingenError("rejection_reason is required when recording a rejection")
    declaration.status = LoonheffingenDeclarationStatus.accepted if accepted else LoonheffingenDeclarationStatus.rejected
    declaration.government_response_reference = response_reference.strip()
    declaration.government_response_at = datetime.now(timezone.utc)
    declaration.rejection_reason = rejection_reason if not accepted else None
    db.flush()
