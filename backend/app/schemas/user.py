from datetime import datetime

from pydantic import BaseModel, ConfigDict, EmailStr, Field

from app.models.enums import CompanyInvitationStatus, UserRole

# Roles assignable through the Phase 15 user-management endpoints. `customer`
# and `employee` are deliberately excluded -- they have their own dedicated
# flows (see app.api.v1.companies._require_company_owner and
# app.api.v1.employees.invite_employee_self_service) and are never created
# or re-assigned via this API.
ASSIGNABLE_ROLES = (UserRole.owner, UserRole.admin, UserRole.accountant, UserRole.viewer)


class CompanyAccessSummary(BaseModel):
    id: int
    name: str

    model_config = ConfigDict(from_attributes=True)


class TenantUserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    is_active: bool
    mfa_enabled: bool
    created_at: datetime
    companies: list[CompanyAccessSummary] = []

    model_config = ConfigDict(from_attributes=True)


class UserRoleUpdate(BaseModel):
    role: UserRole


class UserInvitationCreate(BaseModel):
    invited_email: EmailStr
    intended_role: UserRole
    initial_company_ids: list[int] | None = None


class UserInvitationOut(BaseModel):
    id: int
    invited_email: EmailStr
    intended_role: UserRole
    status: CompanyInvitationStatus
    invited_by_user_id: int
    created_at: datetime
    expires_at: datetime
    accepted_at: datetime | None

    model_config = ConfigDict(from_attributes=True)


class UserInvitationCreateResult(BaseModel):
    invitation: UserInvitationOut
    # Only populated when no email could be sent (no provider configured or
    # rate-limited) so the inviter can relay the link themselves; otherwise
    # None -- the token travels in the email and nowhere else.
    raw_token: str | None
    email_sent: bool = False


class UserCompanyAccessUpdate(BaseModel):
    company_ids: list[int]


class AcceptUserInvitationRequest(BaseModel):
    token: str
    full_name: str = Field(min_length=1, max_length=255)
    password: str = Field(min_length=8, max_length=255)
