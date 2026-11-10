"""Working-hours services: employee timesheets (with approval) and
entrepreneur hours (for the 1,225-hour urencriterium). Entering a total
here never automatically grants a deduction -- app.accounting.tax_optimization
only treats the criterion as met when the caller explicitly confirms it,
same as every other eligibility check in this codebase."""

from datetime import date, datetime, timezone
from decimal import Decimal

from sqlalchemy.orm import Session

from app.accounting import dutch_tax_rules as tax
from app.models.enums import TimesheetStatus
from app.models.timesheet import EmployeeTimesheetEntry, EntrepreneurHoursEntry

ZERO = Decimal("0")


class HoursError(Exception):
    pass


def submit_timesheet_entry(db: Session, entry: EmployeeTimesheetEntry) -> None:
    if entry.status != TimesheetStatus.draft:
        raise HoursError(f"Timesheet entry is {entry.status.value}, not DRAFT")
    entry.status = TimesheetStatus.submitted
    db.flush()


def approve_timesheet_entry(db: Session, entry: EmployeeTimesheetEntry, user_id: int) -> None:
    if entry.status != TimesheetStatus.submitted:
        raise HoursError(f"Timesheet entry is {entry.status.value}, not SUBMITTED")
    entry.status = TimesheetStatus.approved
    entry.approved_by_user_id = user_id
    entry.approved_at = datetime.now(timezone.utc)
    db.flush()


def reject_timesheet_entry(db: Session, entry: EmployeeTimesheetEntry, user_id: int) -> None:
    if entry.status != TimesheetStatus.submitted:
        raise HoursError(f"Timesheet entry is {entry.status.value}, not SUBMITTED")
    entry.status = TimesheetStatus.rejected
    entry.approved_by_user_id = user_id
    entry.approved_at = datetime.now(timezone.utc)
    db.flush()


def employee_hours_summary(db: Session, employee_id: int, year: int) -> dict:
    entries = (
        db.query(EmployeeTimesheetEntry)
        .filter(EmployeeTimesheetEntry.employee_id == employee_id, EmployeeTimesheetEntry.entry_date.between(date(year, 1, 1), date(year, 12, 31)))
        .all()
    )
    by_type: dict[str, Decimal] = {}
    for e in entries:
        by_type[e.entry_type.value] = by_type.get(e.entry_type.value, ZERO) + e.hours
    return {"year": year, "hours_by_type": by_type, "total_entries": len(entries)}


def urencriterium_dashboard(db: Session, company_id: int, year: int, partner_id: int | None = None, rules: tax.DutchTaxRuleSet | None = None) -> dict:
    """1,225-hour dashboard. Distinguishes actually-recorded hours from the
    threshold -- never implies the deduction is granted just because a
    total was entered."""
    rules = rules or tax.get_rule_set()
    query = db.query(EntrepreneurHoursEntry).filter(
        EntrepreneurHoursEntry.company_id == company_id,
        EntrepreneurHoursEntry.entry_date.between(date(year, 1, 1), date(year, 12, 31)),
    )
    if partner_id is not None:
        query = query.filter(EntrepreneurHoursEntry.partner_id == partner_id)
    else:
        query = query.filter(EntrepreneurHoursEntry.partner_id.is_(None))
    entries = query.all()

    by_category: dict[str, Decimal] = {}
    for e in entries:
        by_category[e.activity_category] = by_category.get(e.activity_category, ZERO) + e.duration_hours
    total_hours = sum(by_category.values(), ZERO)

    return {
        "year": year,
        "total_recorded_hours": total_hours,
        "hours_by_category": by_category,
        "threshold_hours": rules.urencriterium_hours,
        "threshold_met_by_recorded_hours_alone": total_hours >= rules.urencriterium_hours,
        "entry_count": len(entries),
        "disclaimer": (
            "This reflects only hours explicitly logged in this system. Meeting the recorded-hours threshold here "
            "is necessary but not sufficient to claim the urencriterium is met -- the Belastingdienst's actual test "
            "also requires the business to be the entrepreneur's main time commitment and considers which hours "
            "legally count. An accountant must confirm eligibility before any deduction is claimed."
        ),
    }
