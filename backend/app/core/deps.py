from fastapi import Depends, HTTPException, status
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.orm import Session

from app.core.security import decode_access_token
from app.db.session import get_db
from app.models.enums import UserRole
from app.models.user import User

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/api/v1/auth/login")


def get_current_user(
    token: str = Depends(oauth2_scheme), db: Session = Depends(get_db)
) -> User:
    credentials_error = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED, detail="Could not validate credentials"
    )
    email = decode_access_token(token)
    if email is None:
        raise credentials_error
    user = db.query(User).filter(User.email == email).first()
    if user is None:
        raise credentials_error
    return user


def require_admin(user: User = Depends(get_current_user)) -> User:
    if user.role != UserRole.admin:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Admin only")
    return user


def require_editor(user: User = Depends(get_current_user)) -> User:
    if user.role not in (UserRole.admin, UserRole.accountant):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin or accountant role required"
        )
    return user


def require_uploader(user: User = Depends(get_current_user)) -> User:
    """Who may upload documents: accountants/admins for any company they can
    access, plus customers uploading their own company's invoices. Approval,
    rejection, locking, and every other mutating accounting action stay
    require_editor-only -- customers can upload, never approve."""
    if user.role not in (UserRole.admin, UserRole.accountant, UserRole.customer):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin, accountant, or customer role required"
        )
    return user


def require_editor_or_owner(user: User = Depends(get_current_user)) -> User:
    """Who may create/approve budgets and manual balance-sheet items:
    accountants/admins for any company they can access, plus a customer
    (the business-owner persona in this system) for their own company --
    checked separately via require_company_access. Viewers can still read
    every Phase 8 report through get_current_user + require_company_access,
    just never mutate one."""
    if user.role not in (UserRole.admin, UserRole.accountant, UserRole.customer):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="Admin, accountant, or business-owner role required"
        )
    return user


def require_company_access(company_id: int, user: User, db: Session) -> None:
    if user.role == UserRole.admin:
        return
    has_access = any(c.id == company_id for c in user.companies)
    if not has_access:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN, detail="No access to this company"
        )
