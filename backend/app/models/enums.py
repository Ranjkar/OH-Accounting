import enum


class UserRole(str, enum.Enum):
    admin = "admin"
    accountant = "accountant"
    viewer = "viewer"


class VatFrequency(str, enum.Enum):
    monthly = "monthly"
    quarterly = "quarterly"
    annual = "annual"


class VatPeriodStatus(str, enum.Enum):
    open = "open"
    filed = "filed"
    paid = "paid"
