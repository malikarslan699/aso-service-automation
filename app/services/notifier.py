"""Telegram notification service."""
import logging
from typing import Optional

logger = logging.getLogger(__name__)


def _get_bot_config(db) -> tuple[str, str]:
    """Get Telegram bot token and chat_id from global_config."""
    from sqlalchemy import select
    from app.models.global_config import GlobalConfig
    from app.utils.encryption import decrypt_value

    bot_token = ""
    chat_id = ""

    rows = db.execute(select(GlobalConfig)).scalars().all()
    for row in rows:
        try:
            val = decrypt_value(row.value)
            if row.key == "telegram_bot_token":
                bot_token = val
            elif row.key == "telegram_chat_id":
                chat_id = val
        except Exception:
            pass

    return bot_token, chat_id


def _send_message(bot_token: str, chat_id: str, text: str) -> bool:
    """Send a Telegram message synchronously.

    Returns True on success, False on failure (never raises).
    """
    if not bot_token or not chat_id:
        logger.debug("Telegram not configured — skipping notification")
        return False

    try:
        import httpx

        url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
        response = httpx.post(
            url,
            json={"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            timeout=10.0,
        )
        response.raise_for_status()
        return True
    except Exception as exc:
        logger.warning(f"Telegram notification failed: {exc}")
        return False


def send_suggestion_alert(suggestions: list, app_name: str, db) -> bool:
    """Alert about new high-risk suggestions requiring human review.

    Args:
        suggestions: list of Suggestion ORM instances or dicts with risk_score >= 2
        app_name: display name of the app
        db: SQLAlchemy session for config lookup
    """
    if not suggestions:
        return False

    bot_token, chat_id = _get_bot_config(db)

    lines = [f"<b>🔔 ASO Suggestions Ready — {app_name}</b>"]
    lines.append(f"{len(suggestions)} suggestion(s) need your review:\n")

    for s in suggestions[:5]:
        if isinstance(s, dict):
            field = s.get("field_name", "unknown")
            risk = s.get("risk_score", 0)
        else:
            field = getattr(s, "field_name", "unknown")
            risk = getattr(s, "risk_score", 0)
        risk_emoji = "🔴" if risk >= 3 else "🟡" if risk >= 2 else "🟢"
        lines.append(f"{risk_emoji} {field} (risk: {risk})")

    return _send_message(bot_token, chat_id, "\n".join(lines))


def send_publish_confirmation(suggestion, app_name: str, dry_run: bool, db) -> bool:
    """Confirm a successful publish (or dry run)."""
    bot_token, chat_id = _get_bot_config(db)

    field = getattr(suggestion, "field_name", "unknown")
    dry_tag = " [DRY RUN]" if dry_run else ""
    text = (
        f"<b>✅ Published{dry_tag} — {app_name}</b>\n"
        f"Field: {field}\n"
        f"New value: {getattr(suggestion, 'new_value', '')[:100]}"
    )
    return _send_message(bot_token, chat_id, text)


def send_error_alert(error: str, app_name: str, db) -> bool:
    """Alert on pipeline or publish error."""
    bot_token, chat_id = _get_bot_config(db)
    text = f"<b>❌ ASO Error — {app_name}</b>\n{error[:300]}"
    return _send_message(bot_token, chat_id, text)


def send_keyword_opportunity(rising_trends: list, app_name: str, db) -> bool:
    """Alert about rising keyword opportunities."""
    if not rising_trends:
        return False

    bot_token, chat_id = _get_bot_config(db)

    lines = [f"<b>📈 Keyword Opportunity — {app_name}</b>"]
    lines.append(f"{len(rising_trends)} keyword(s) trending up:\n")

    for t in rising_trends[:5]:
        kw = t.get("keyword", "")
        change = t.get("change_pct", 0)
        trend = t.get("trend", "rising")
        lines.append(f"⬆️ {kw} (+{change:.0f}%)" if trend == "rising" else f"🆕 {kw}")

    return _send_message(bot_token, chat_id, "\n".join(lines))


def send_rollback_alert(suggestion, app_name: str, reason: str, db) -> bool:
    """Alert when a published suggestion is rolled back."""
    bot_token, chat_id = _get_bot_config(db)

    field = getattr(suggestion, "field_name", "unknown")
    text = (
        f"<b>⚠️ Rollback — {app_name}</b>\n"
        f"Field: {field}\n"
        f"Reason: {reason}"
    )
    return _send_message(bot_token, chat_id, text)
