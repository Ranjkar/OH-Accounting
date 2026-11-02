from pydantic import BaseModel

from app.models.enums import NoteStatus, NoteType


class NoteCreate(BaseModel):
    note_type: NoteType
    body: str
    related_entity_type: str | None = None
    related_entity_id: int | None = None


class NoteStatusUpdate(BaseModel):
    status: NoteStatus
