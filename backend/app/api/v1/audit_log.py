from datetime import date, datetime, time, timezone

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.deps import require_admin
from app.db.session import get_db
from app.models.audit_log import AuditLog
from app.models.user import User
from app.schemas.audit_log import AuditLogActorOut, AuditLogEntryOut, AuditLogPage

router = APIRouter(prefix="/audit-log", tags=["audit-log"])

MAX_LIMIT = 200


@router.get("", response_model=AuditLogPage)
def list_audit_log(
    skip: int = Query(0, ge=0),
    limit: int = Query(50, ge=1, le=MAX_LIMIT),
    user_id: int | None = Query(None),
    action: str | None = Query(None),
    entity_type: str | None = Query(None),
    q: str | None = Query(None, description="Free-text search across action and entity_type"),
    date_from: date | None = Query(None),
    date_to: date | None = Query(None),
    db: Session = Depends(get_db),
    user: User = Depends(require_admin),
):
    """Owner/admin only, read-only (this module defines no POST/PATCH/
    DELETE -- see app.models.audit_log.AuditLog's docstring: nothing in
    this codebase ever mutates an audit row through the API).
    Tenant-scoped by construction -- every query below starts from
    AuditLog.tenant_id == user.tenant_id, so a cross-tenant row can never
    be returned regardless of the filters supplied."""
    query = db.query(AuditLog).filter(AuditLog.tenant_id == user.tenant_id)

    if user_id is not None:
        query = query.filter(AuditLog.user_id == user_id)
    if action:
        query = query.filter(AuditLog.action == action)
    if entity_type:
        query = query.filter(AuditLog.entity_type == entity_type)
    if q:
        like = f"%{q}%"
        query = query.filter((AuditLog.action.ilike(like)) | (AuditLog.entity_type.ilike(like)))
    if date_from is not None:
        query = query.filter(AuditLog.created_at >= datetime.combine(date_from, time.min, tzinfo=timezone.utc))
    if date_to is not None:
        query = query.filter(AuditLog.created_at <= datetime.combine(date_to, time.max, tzinfo=timezone.utc))

    total = query.count()
    rows = query.order_by(AuditLog.created_at.desc()).offset(skip).limit(limit).all()

    actor_ids = {r.user_id for r in rows if r.user_id is not None}
    actors = {u.id: u for u in db.query(User).filter(User.id.in_(actor_ids)).all()} if actor_ids else {}

    items = [
        AuditLogEntryOut(
            id=r.id, user_id=r.user_id,
            actor=AuditLogActorOut.model_validate(actors[r.user_id]) if r.user_id in actors else None,
            action=r.action, entity_type=r.entity_type, entity_id=r.entity_id,
            before=r.before, after=r.after, request_id=r.request_id, event_metadata=r.event_metadata,
            created_at=r.created_at,
        )
        for r in rows
    ]
    return AuditLogPage(items=items, total=total, skip=skip, limit=limit)


@router.get("/actions", response_model=list[str])
def list_audit_actions(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    """Distinct action values seen in this tenant's own log -- powers the
    Audit Log page's action filter dropdown with real values instead of a
    hardcoded, possibly-stale list."""
    rows = db.query(AuditLog.action).filter(AuditLog.tenant_id == user.tenant_id).distinct().order_by(AuditLog.action).all()
    return [r[0] for r in rows]


@router.get("/entity-types", response_model=list[str])
def list_audit_entity_types(db: Session = Depends(get_db), user: User = Depends(require_admin)):
    rows = db.query(AuditLog.entity_type).filter(AuditLog.tenant_id == user.tenant_id).distinct().order_by(AuditLog.entity_type).all()
    return [r[0] for r in rows]
