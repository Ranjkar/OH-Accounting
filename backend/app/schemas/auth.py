from pydantic import BaseModel, ConfigDict, EmailStr

from app.models.enums import UserRole


class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    mfa_code: str | None = None


class TokenResponse(BaseModel):
    access_token: str | None = None
    token_type: str = "bearer"
    mfa_required: bool = False


class MfaSetupResponse(BaseModel):
    secret: str
    provisioning_uri: str


class MfaEnableRequest(BaseModel):
    secret: str
    code: str


class MfaDisableRequest(BaseModel):
    code: str


class UserOut(BaseModel):
    id: int
    email: EmailStr
    full_name: str
    role: UserRole
    mfa_enabled: bool
    is_platform_admin: bool
    # Phase 16: `locale` is the raw per-user override (null if the user
    # has never set one); `tenant_default_locale` is always set. The
    # frontend's *effective* locale is `locale ?? tenant_default_locale` --
    # kept as two fields rather than one pre-resolved value so the
    # language selector can show whether the current value is a personal
    # override or inherited from the organisation.
    locale: str | None
    tenant_default_locale: str

    model_config = ConfigDict(from_attributes=True)


class UpdateLocaleRequest(BaseModel):
    # None clears the personal override and reverts to the tenant default --
    # an explicit, intentional action, not the same as "field omitted."
    locale: str | None


class PasswordResetRequest(BaseModel):
    email: EmailStr


class PasswordResetConfirm(BaseModel):
    token: str
    new_password: str
