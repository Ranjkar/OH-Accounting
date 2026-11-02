"""Company-specific expense categorization. Rules never cross company
boundaries -- a rule created for one company is never consulted for another,
even within the same tenant."""

import re

from sqlalchemy.orm import Session

from app.models.accounting import AccountingTransaction
from app.models.categorization import CategorizationRule
from app.models.enums import CategorizationRuleType, CategorySource

EXPENSE_CATEGORIES = [
    "Office expenses", "Travel", "Fuel", "Software subscriptions", "Telecommunications",
    "Rent", "Insurance", "Professional services", "Equipment", "Marketing", "Other",
]


def apply_rules(db: Session, transaction: AccountingTransaction) -> bool:
    """Returns True if a rule matched and set the category."""
    rules = db.query(CategorizationRule).filter(CategorizationRule.company_id == transaction.company_id).all()
    for rule in rules:
        if _rule_matches(rule, transaction):
            transaction.expense_category = rule.category
            transaction.category_confidence = None  # a rule match is a company decision, not a confidence score
            transaction.category_source = CategorySource.rule
            return True
    return False


def _rule_matches(rule: CategorizationRule, transaction: AccountingTransaction) -> bool:
    if rule.rule_type == CategorizationRuleType.supplier_name:
        return bool(transaction.counterparty_name) and rule.match_value.lower() in transaction.counterparty_name.lower()
    if rule.rule_type == CategorizationRuleType.iban:
        return bool(transaction.counterparty_iban) and rule.match_value.upper().replace(" ", "") == transaction.counterparty_iban.upper().replace(" ", "")
    if rule.rule_type == CategorizationRuleType.description_pattern:
        description = transaction.accounting_classification or ""
        return bool(re.search(rule.match_value, description, re.IGNORECASE))
    return False


def create_rule_from_correction(
    db: Session, transaction: AccountingTransaction, category: str, created_by_user_id: int
) -> CategorizationRule | None:
    """When an accountant manually corrects a category, offer to remember it
    as a supplier-based rule for next time -- only when there's a supplier
    name to key off of."""
    if not transaction.counterparty_name:
        return None
    rule = CategorizationRule(
        tenant_id=transaction.tenant_id, company_id=transaction.company_id,
        rule_type=CategorizationRuleType.supplier_name, match_value=transaction.counterparty_name,
        category=category, created_by_user_id=created_by_user_id,
    )
    db.add(rule)
    db.flush()
    return rule
