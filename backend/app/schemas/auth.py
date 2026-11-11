from pydantic import BaseModel, ConfigDict, EmailStr, Field, field_validator

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
    # Phase 22: profile fields (all optional) + pending email change.
    first_name: str | None = None
    last_name: str | None = None
    display_name: str | None = None
    phone: str | None = None
    address_line: str | None = None
    postal_code: str | None = None
    city: str | None = None
    country: str | None = None
    pending_email: str | None = None
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


# ---- Phase 22: profile, password, email change, sessions ----

PASSWORD_MIN_LENGTH = 10


def validate_password_policy(password: str, email: str | None = None) -> str:
    """Minimum 10 characters, at least one letter and one digit, not equal
    to (or containing) the account's email local part. Deliberately no
    "special character" or forced-rotation rules (NIST 800-63B)."""
    if len(password) < PASSWORD_MIN_LENGTH:
        raise ValueError(f"Password must be at least {PASSWORD_MIN_LENGTH} characters")
    if len(password) > 255:
        raise ValueError("Password is too long")
    if not any(c.isalpha() for c in password) or not any(c.isdigit() for c in password):
        raise ValueError("Password must contain at least one letter and one digit")
    if email:
        local = email.split("@")[0].lower()
        if len(local) >= 4 and local in password.lower():
            raise ValueError("Password must not contain your email address")
    return password


class ProfileUpdate(BaseModel):
    first_name: str | None = Field(default=None, max_length=100)
    last_name: str | None = Field(default=None, max_length=100)
    display_name: str | None = Field(default=None, max_length=255)
    phone: str | None = Field(default=None, max_length=50)
    address_line: str | None = Field(default=None, max_length=255)
    postal_code: str | None = Field(default=None, max_length=20)
    city: str | None = Field(default=None, max_length=100)
    country: str | None = Field(default=None, min_length=2, max_length=2)

    @field_validator("country")
    @classmethod
    def _upper(cls, v: str | None) -> str | None:
        return v.upper() if v else v


class PasswordChangeRequest(BaseModel):
    current_password: str
    new_password: str
    confirm_password: str


class PasswordChangeResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class EmailChangeRequest(BaseModel):
    new_email: EmailStr
    current_password: str


class EmailChangeConfirm(BaseModel):
    token: str


class SessionsRevokeResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"
