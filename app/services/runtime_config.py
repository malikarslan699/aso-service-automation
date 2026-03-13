from sqlalchemy import select

from app.models.global_config import GlobalConfig
from app.utils.encryption import decrypt_value


DEFAULTS = {
    "dry_run": "true",
    "max_publish_per_day": "1",
    "max_publish_per_week": "5",
    "listing_publish_max_per_day": "1",
    "listing_publish_max_per_week": "5",
    "review_reply_max_per_day": "25",
    "review_reply_max_per_week": "120",
    "listing_publish_min_gap_minutes": "60",
    "listing_publish_jitter_min_seconds": "90",
    "listing_publish_jitter_max_seconds": "480",
    "listing_publish_window_start_hour_utc": "9",
    "listing_publish_window_end_hour_utc": "22",
    "listing_recent_change_cooldown_hours": "12",
    "listing_churn_max_per_24h": "2",
    "auto_approve_threshold": "0",
    "manual_approval_required": "true",
    "publish_after_approval": "true",
    "publish_mode": "live",
    "human_sim_enabled": "false",
    "pipeline_delay_min_minutes": "5",
    "pipeline_delay_max_minutes": "20",
    "publish_delay_min_minutes": "45",
    "publish_delay_max_minutes": "180",
    "manual_trigger_cooldown_minutes": "15",
    "openai_api_key": "",
}


def load_runtime_config(db) -> dict[str, str]:
    config = dict(DEFAULTS)
    rows = db.execute(select(GlobalConfig)).scalars().all()
    for row in rows:
        try:
            value = decrypt_value(row.value)
        except Exception:
            value = row.value
        config[row.key] = value
    return config


def is_true(value: str | None, default: bool = False) -> bool:
    if value is None:
        return default
    return str(value).strip().lower() == "true"


def as_int(value: str | None, default: int) -> int:
    try:
        return int(str(value))
    except Exception:
        return default
