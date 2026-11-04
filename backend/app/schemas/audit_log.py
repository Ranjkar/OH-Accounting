from datetime import datetime

from pydantic import BaseModel, ConfigDict


class AuditLogActorOut(BaseModel):
    id: int
    email: str
    full_name: str

    model_config = ConfigDict(from_attributes=True)


class AuditLogEntryOut(BaseModel):
    id: int
    user_id: int | None
    actor: AuditLogActorOut | None = None
    action: str
    entity_type: str
    entity_id: int
    before: dict | None
    after: dict | None
    request_id: str | None
    event_metadata: dict | None
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class AuditLogPage(BaseModel):
    items: list[AuditLogEntryOut]
    total: int
    skip: int
    limit: int
