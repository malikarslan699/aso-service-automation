"""Auto-approve engine: rule-based and learning-based suggestion auto-approval."""
import logging

logger = logging.getLogger(__name__)

# Only auto-approve these types initially (safest)
AUTO_APPROVE_TYPES = {"review_reply"}

# Minimum consecutive approvals before lowering risk threshold
LEARNING_THRESHOLD = 5


def should_auto_approve(
    suggestion: dict,
    rules: list,
    max_allowed_risk: int = 0,
) -> bool:
    """Determine if a suggestion should be auto-approved.

    Logic:
    - Only review_reply type is eligible initially
    - Risk score must be 0
    - Must have an active AutoApproveRule with matching type and max_risk_score >= suggestion risk

    Args:
        suggestion: dict with suggestion_type, risk_score
        rules: list of AutoApproveRule ORM instances or dicts

    Returns:
        bool — True if auto-approve
    """
    s_type = suggestion.get("suggestion_type", "")
    risk = int(suggestion.get("risk_score", 99))

    # Only safe types
    if s_type not in AUTO_APPROVE_TYPES:
        return False

    # Keep auto-approve constrained by global threshold.
    if risk > max_allowed_risk:
        return False

    # Check for active matching rule
    for rule in rules:
        rule_type = getattr(rule, "suggestion_type", rule.get("suggestion_type", "")) if not isinstance(rule, dict) else rule.get("suggestion_type", "")
        rule_active = getattr(rule, "is_active", rule.get("is_active", False)) if not isinstance(rule, dict) else rule.get("is_active", False)
        rule_max_risk = getattr(rule, "max_risk_score", rule.get("max_risk_score", 0)) if not isinstance(rule, dict) else rule.get("max_risk_score", 0)

        if rule_type == s_type and rule_active and rule_max_risk >= risk:
            logger.debug(f"Auto-approving {s_type} suggestion (risk={risk}, rule matched)")
            return True

    return False


def update_rules(
    suggestion_type: str,
    outcome: str,
    app_id: int,
    db,
) -> None:
    """Update auto-approve rules based on human approval/rejection.

    - On approval: increment approved_count
      → if approved_count >= LEARNING_THRESHOLD: activate rule
    - On rejection: increment rejected_count, deactivate rule (safety)

    Args:
        suggestion_type: e.g. "review_reply"
        outcome: "approved" or "rejected"
        app_id: DB app ID
        db: SQLAlchemy session
    """
    from sqlalchemy import select
    from app.models.auto_approve_rule import AutoApproveRule

    rule = db.execute(
        select(AutoApproveRule)
        .where(AutoApproveRule.app_id == app_id)
        .where(AutoApproveRule.suggestion_type == suggestion_type)
    ).scalar_one_or_none()

    if rule is None:
        # Create new rule
        rule = AutoApproveRule(
            app_id=app_id,
            suggestion_type=suggestion_type,
            max_risk_score=0,
            approved_count=0,
            rejected_count=0,
            is_active=False,
        )
        db.add(rule)

    if outcome == "approved":
        rule.approved_count += 1
        # Activate after enough consecutive approvals
        if rule.approved_count >= LEARNING_THRESHOLD and rule.rejected_count == 0:
            rule.is_active = True
            logger.info(
                f"Auto-approve rule activated for {suggestion_type} (app {app_id}) "
                f"after {rule.approved_count} approvals"
            )
    elif outcome == "rejected":
        rule.rejected_count += 1
        if rule.is_active:
            rule.is_active = False
            logger.info(
                f"Auto-approve rule deactivated for {suggestion_type} (app {app_id}) due to rejection"
            )

    db.commit()


def get_rules(app_id: int, db) -> list:
    """Get all auto-approve rules for an app."""
    from sqlalchemy import select
    from app.models.auto_approve_rule import AutoApproveRule

    return db.execute(
        select(AutoApproveRule).where(AutoApproveRule.app_id == app_id)
    ).scalars().all()
