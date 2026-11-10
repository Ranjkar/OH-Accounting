from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.accounting import loonheffingen_service
from app.core.deps import get_current_user, require_company_access, require_editor
from app.db.session import get_db
from app.models.loonheffingen import LoonheffingenDeclaration
from app.models.payroll import PayrollRun
from app.models.user import User
from app.schemas.loonheffingen import LoonheffingenDeclarationOut, RecordGovernmentResponseRequest, RecordSubmissionRequest

router = APIRouter(tags=["loonheffingen"])


def _get_run_or_404(db: Session, user: User, run_id: int) -> PayrollRun:
    run = db.get(PayrollRun, run_id)
    if run is None or run.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Payroll run not found")
    require_company_access(run.company_id, user, db)
    return run


def _get_declaration_or_404(db: Session, user: User, declaration_id: int) -> LoonheffingenDeclaration:
    declaration = db.get(LoonheffingenDeclaration, declaration_id)
    if declaration is None or declaration.tenant_id != user.tenant_id:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Loonheffingen declaration not found")
    require_company_access(declaration.company_id, user, db)
    return declaration


@router.post("/payroll-runs/{run_id}/loonheffingen-declaration", response_model=LoonheffingenDeclarationOut, status_code=status.HTTP_201_CREATED)
def create_declaration(run_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    run = _get_run_or_404(db, user, run_id)
    try:
        declaration = loonheffingen_service.create_declaration(db, run)
    except loonheffingen_service.LoonheffingenError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(declaration)
    return declaration


@router.get("/loonheffingen-declarations/{declaration_id}", response_model=LoonheffingenDeclarationOut)
def get_declaration(declaration_id: int, db: Session = Depends(get_db), user: User = Depends(get_current_user)):
    return _get_declaration_or_404(db, user, declaration_id)


@router.post("/loonheffingen-declarations/{declaration_id}/validate", response_model=LoonheffingenDeclarationOut)
def validate_declaration(declaration_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    declaration = _get_declaration_or_404(db, user, declaration_id)
    try:
        loonheffingen_service.run_validation(db, declaration)
    except loonheffingen_service.LoonheffingenError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(declaration)
    return declaration


@router.post("/loonheffingen-declarations/{declaration_id}/approve", response_model=LoonheffingenDeclarationOut)
def approve_declaration(declaration_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    declaration = _get_declaration_or_404(db, user, declaration_id)
    try:
        loonheffingen_service.approve(db, declaration, user.id)
    except loonheffingen_service.LoonheffingenError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(declaration)
    return declaration


@router.post("/loonheffingen-declarations/{declaration_id}/mark-ready-for-submission", response_model=LoonheffingenDeclarationOut)
def mark_ready_for_submission(declaration_id: int, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    declaration = _get_declaration_or_404(db, user, declaration_id)
    try:
        loonheffingen_service.mark_ready_for_submission(db, declaration)
    except loonheffingen_service.LoonheffingenError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(declaration)
    return declaration


@router.post("/loonheffingen-declarations/{declaration_id}/record-submission", response_model=LoonheffingenDeclarationOut)
def record_submission(declaration_id: int, payload: RecordSubmissionRequest, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    declaration = _get_declaration_or_404(db, user, declaration_id)
    try:
        loonheffingen_service.record_submission(db, declaration, submission_reference=payload.submission_reference, user_id=user.id)
    except loonheffingen_service.LoonheffingenError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(declaration)
    return declaration


@router.post("/loonheffingen-declarations/{declaration_id}/record-government-response", response_model=LoonheffingenDeclarationOut)
def record_government_response(declaration_id: int, payload: RecordGovernmentResponseRequest, db: Session = Depends(get_db), user: User = Depends(require_editor)):
    declaration = _get_declaration_or_404(db, user, declaration_id)
    try:
        loonheffingen_service.record_government_response(
            db, declaration, accepted=payload.accepted, response_reference=payload.response_reference,
            rejection_reason=payload.rejection_reason,
        )
    except loonheffingen_service.LoonheffingenError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    db.commit()
    db.refresh(declaration)
    return declaration
