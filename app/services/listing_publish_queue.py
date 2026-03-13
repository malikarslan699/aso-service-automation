"""Compliance-safe listing bundle queue for paced Google Play publishing."""
from __future__ import annotations

import json
import logging
import random
import re
from datetime import datetime, timedelta
from typing import Iterable

from sqlalchemy import select

from app.models.app import App
from app.models.app_credential import AppCredential
from app.models.listing_publish_job import ListingPublishJob
from app.models.suggestion import Suggestion
from app.services import execution
from app.services.publish_guard import recent_live_publish_block_reason
from app.services.runtime_config import as_int, is_true, load_runtime_config
from app.services.safety_validator import BLOCKED_TERMS, FIELD_LIMITS
from app.services.suggestion_tracking import apply_status_log, parse_status_log, update_status_stage, utcnow_naive
from app.utils.encryption import decrypt_value

logger = logging.getLogger(__name__)

LISTING_FIELDS = {"title", "short_description", "long_description"}
OPEN_JOB_STATUSES = {"queued_bundle", "waiting_safe_window", "publishing"}
FINAL_JOB_STATUSES = {"published", "soft_published", "dry_run_only", "blocked", "failed", "superseded"}


def _serialize_ids(values: Iterable[int]) -> str:
    unique_values = []
    seen = set()
    for raw in values:
        try:
            item = int(raw)
        except Exception:
            continue
        if item in seen:
            continue
        seen.add(item)
        unique_values.append(item)
    return json.dumps(unique_values)


def _parse_ids(raw: str | None) -> list[int]:
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return []
    if not isinstance(data, list):
        return []

    out: list[int] = []
    for item in data:
        try:
            out.append(int(item))
        except Exception:
            continue
    return out


def _clamp(value: int, minimum: int, maximum: int) -> int:
    return max(minimum, min(value, maximum))


def _load_dispatch_policy(db) -> dict:
    config = load_runtime_config(db)

    window_start = _clamp(as_int(config.get("listing_publish_window_start_hour_utc"), 9), 0, 23)
    window_end = _clamp(as_int(config.get("listing_publish_window_end_hour_utc"), 22), 1, 24)
    jitter_min = max(0, as_int(config.get("listing_publish_jitter_min_seconds"), 90))
    jitter_max = max(jitter_min, as_int(config.get("listing_publish_jitter_max_seconds"), 480))

    return {
        "config": config,
        "window_start": window_start,
        "window_end": window_end,
        "jitter_min": jitter_min,
        "jitter_max": jitter_max,
        "min_gap_minutes": max(0, as_int(config.get("listing_publish_min_gap_minutes"), 60)),
        "recent_cooldown_hours": max(1, as_int(config.get("listing_recent_change_cooldown_hours"), 12)),
        "churn_max_per_24h": max(1, as_int(config.get("listing_churn_max_per_24h"), 2)),
    }


def _window_contains(moment: datetime, start_hour: int, end_hour: int) -> bool:
    hour = moment.hour
    if start_hour < end_hour:
        return start_hour <= hour < end_hour
    if start_hour > end_hour:
        return hour >= start_hour or hour < end_hour
    return True


def _align_to_window(moment: datetime, start_hour: int, end_hour: int) -> datetime:
    if _window_contains(moment, start_hour, end_hour):
        return moment

    aligned = moment.replace(minute=0, second=0, microsecond=0)
    if start_hour < end_hour:
        if moment.hour < start_hour:
            return aligned.replace(hour=start_hour)
        return (aligned + timedelta(days=1)).replace(hour=start_hour)

    # Overnight window (e.g. 22 -> 6)
    if moment.hour >= end_hour:
        return aligned.replace(hour=start_hour)
    return aligned


def _dispatch_window_label(policy: dict) -> str:
    return (
        f"{policy['window_start']:02d}:00-{policy['window_end']:02d}:00 UTC"
        f" | jitter {policy['jitter_min']}-{policy['jitter_max']}s"
        f" | gap {policy['min_gap_minutes']}m"
    )


def _latest_listing_job_execution(db, app_id: int) -> datetime | None:
    return db.execute(
        select(ListingPublishJob.executed_at)
        .where(ListingPublishJob.app_id == app_id)
        .where(ListingPublishJob.status.in_(("published", "dry_run_only")))
        .where(ListingPublishJob.executed_at.is_not(None))
        .order_by(ListingPublishJob.executed_at.desc())
        .limit(1)
    ).scalar_one_or_none()


def _count_recent_executions(db, app_id: int, since: datetime) -> int:
    rows = db.execute(
        select(ListingPublishJob.id)
        .where(ListingPublishJob.app_id == app_id)
        .where(ListingPublishJob.status.in_(("published", "dry_run_only")))
        .where(ListingPublishJob.executed_at >= since)
    ).scalars().all()
    return len(rows)


def _compute_next_eligible(db, app_id: int, policy: dict, now: datetime, keep_existing: datetime | None = None) -> tuple[datetime, int]:
    jitter_seconds = random.randint(policy["jitter_min"], policy["jitter_max"])
    next_eligible = now + timedelta(seconds=jitter_seconds)
    if keep_existing and keep_existing > next_eligible:
        next_eligible = keep_existing

    last_execution = _latest_listing_job_execution(db, app_id)
    if last_execution and policy["min_gap_minutes"] > 0:
        min_gap_target = last_execution + timedelta(minutes=policy["min_gap_minutes"])
        if min_gap_target > next_eligible:
            next_eligible = min_gap_target

    next_eligible = _align_to_window(next_eligible, policy["window_start"], policy["window_end"])
    return next_eligible, jitter_seconds


def _contains_repetitive_copy(text: str) -> bool:
    words = re.findall(r"[a-z0-9]+", (text or "").lower())
    freq: dict[str, int] = {}
    for word in words:
        if len(word) < 3:
            continue
        freq[word] = freq.get(word, 0) + 1
    return any(count > 4 for count in freq.values())


def _pre_dispatch_validation_reason(field_name: str, new_value: str) -> str | None:
    if not new_value.strip():
        return f"{field_name.replace('_', ' ')} is empty"

    limit = FIELD_LIMITS.get(field_name)
    if limit and len(new_value) > limit:
        return f"{field_name.replace('_', ' ')} exceeds limit {limit}"

    lowered = new_value.lower()
    for term in BLOCKED_TERMS:
        if term.lower() in lowered:
            return f"Blocked term detected: '{term}'"

    if _contains_repetitive_copy(new_value):
        return "Repetitive rewrite detected; looks too spammy for safe listing dispatch"

    return None


def _queue_guard_reason(suggestion: Suggestion, db, policy: dict, now: datetime) -> str | None:
    local_reason = _pre_dispatch_validation_reason(suggestion.field_name, suggestion.new_value)
    if local_reason:
        return local_reason

    duplicate_reason = recent_live_publish_block_reason(suggestion, db, now=now)
    if duplicate_reason:
        return duplicate_reason

    churn_count = _count_recent_executions(db, suggestion.app_id, now - timedelta(hours=24))
    if churn_count >= policy["churn_max_per_24h"]:
        return (
            f"Listing churn guard blocked this change ({churn_count} execution(s) in last 24h). "
            "Retry later to keep account behavior human-like."
        )

    return None


def _status_log_update(suggestion: Suggestion, *, key: str, status: str, message: str, actor: str, occurred_at: datetime) -> None:
    status_log = parse_status_log(suggestion.status_log, suggestion.created_at)
    status_log = update_status_stage(
        status_log,
        key,
        status=status,
        message=message,
        actor=actor,
        occurred_at=occurred_at,
    )
    apply_status_log(suggestion, status_log)


def _set_superseded(suggestion: Suggestion, *, now: datetime, message: str, job_id: int) -> None:
    suggestion.status = "superseded"
    suggestion.reviewed_by = "system"
    suggestion.publish_status = "superseded"
    suggestion.publish_message = message
    suggestion.publish_block_reason = message
    suggestion.last_transition_at = now
    suggestion.publish_completed_at = now
    suggestion.merged_into_job_id = job_id
    suggestion.google_play_edit_id = None

    _status_log_update(
        suggestion,
        key="publish_result",
        status="blocked",
        message=message,
        actor="system",
        occurred_at=now,
    )


def _set_waiting_state(
    suggestion: Suggestion,
    *,
    now: datetime,
    actor: str,
    status: str,
    message: str,
    job_id: int,
    next_eligible_at: datetime,
    dispatch_window: str,
) -> None:
    suggestion.status = "approved"
    suggestion.publish_status = status
    suggestion.publish_message = message
    suggestion.publish_block_reason = None
    suggestion.publish_started_at = None
    suggestion.publish_completed_at = None
    suggestion.last_transition_at = now
    suggestion.merged_into_job_id = job_id
    suggestion.next_eligible_at = next_eligible_at
    suggestion.dispatch_window = dispatch_window
    suggestion.published_live = False
    suggestion.is_dry_run_result = False
    suggestion.google_play_edit_id = None

    _status_log_update(
        suggestion,
        key="queued_for_publish",
        status="completed",
        message=message,
        actor=actor,
        occurred_at=now,
    )
    if status == "waiting_safe_window":
        _status_log_update(
            suggestion,
            key="waiting_safe_window",
            status="running",
            message=message,
            actor="system",
            occurred_at=now,
        )


def _set_blocked_state(
    suggestion: Suggestion,
    *,
    now: datetime,
    reason: str,
    job_id: int | None,
    actor: str = "system",
) -> None:
    suggestion.status = "approved"
    suggestion.publish_status = "blocked"
    suggestion.publish_message = reason
    suggestion.publish_block_reason = reason
    suggestion.publish_completed_at = now
    suggestion.last_transition_at = now
    suggestion.next_eligible_at = None
    suggestion.google_play_edit_id = None
    if job_id is not None:
        suggestion.merged_into_job_id = job_id

    _status_log_update(
        suggestion,
        key="publish_result",
        status="blocked",
        message=reason,
        actor=actor,
        occurred_at=now,
    )


def _set_publishing_state(suggestion: Suggestion, *, now: datetime, job_id: int) -> None:
    suggestion.publish_status = "publishing"
    suggestion.publish_message = f"Listing bundle #{job_id} is publishing to Google Play."
    suggestion.publish_block_reason = None
    suggestion.publish_started_at = now
    suggestion.publish_completed_at = None
    suggestion.last_transition_at = now
    suggestion.merged_into_job_id = job_id
    suggestion.google_play_edit_id = None

    _status_log_update(
        suggestion,
        key="publish_attempted",
        status="running",
        message=suggestion.publish_message,
        actor="system",
        occurred_at=now,
    )


def _set_result_state(
    suggestion: Suggestion,
    *,
    now: datetime,
    job_id: int,
    publish_status: str,
    message: str,
    edit_id: str | None = None,
) -> None:
    suggestion.publish_status = publish_status
    suggestion.publish_message = message
    suggestion.publish_block_reason = None
    suggestion.publish_completed_at = now
    suggestion.last_transition_at = now
    suggestion.merged_into_job_id = job_id
    suggestion.next_eligible_at = None
    suggestion.google_play_edit_id = edit_id if publish_status == "soft_published" else None
    suggestion.published_live = publish_status == "published"
    suggestion.is_dry_run_result = publish_status == "dry_run_only"
    if publish_status in {"dry_run_only", "soft_published"}:
        suggestion.status = "approved"
        suggestion.published_at = None
    else:
        suggestion.status = "published"
        suggestion.published_at = now

    _status_log_update(
        suggestion,
        key="publish_attempted",
        status="completed",
        message=message,
        actor="system",
        occurred_at=now,
    )
    _status_log_update(
        suggestion,
        key="publish_result",
        status="completed",
        message=message,
        actor="system",
        occurred_at=now,
    )


def _set_failed_state(suggestion: Suggestion, *, now: datetime, reason: str, job_id: int) -> None:
    suggestion.status = "approved"
    suggestion.publish_status = "failed"
    suggestion.publish_message = reason
    suggestion.publish_block_reason = reason
    suggestion.publish_completed_at = now
    suggestion.last_transition_at = now
    suggestion.merged_into_job_id = job_id
    suggestion.google_play_edit_id = None

    _status_log_update(
        suggestion,
        key="publish_attempted",
        status="failed",
        message=reason,
        actor="system",
        occurred_at=now,
    )
    _status_log_update(
        suggestion,
        key="publish_result",
        status="failed",
        message=reason,
        actor="system",
        occurred_at=now,
    )


def _collect_latest_approved_listing_suggestions(db, app_id: int, include_blocked_ids: set[int] | None = None) -> tuple[dict[str, Suggestion], list[Suggestion]]:
    include_blocked_ids = include_blocked_ids or set()
    allowed_publish_states = {None, "ready", "queued", "queued_bundle", "waiting_safe_window", "publishing"}

    rows = db.execute(
        select(Suggestion)
        .where(Suggestion.app_id == app_id)
        .where(Suggestion.suggestion_type == "listing")
        .where(Suggestion.field_name.in_(tuple(LISTING_FIELDS)))
        .where(Suggestion.status == "approved")
        .order_by(Suggestion.id.desc())
    ).scalars().all()

    latest: dict[str, Suggestion] = {}
    superseded: list[Suggestion] = []

    for suggestion in rows:
        state = suggestion.publish_status
        is_retry_item = suggestion.id in include_blocked_ids and state in {"blocked", "failed", "superseded"}
        if state not in allowed_publish_states and not is_retry_item:
            continue

        if suggestion.field_name not in latest:
            latest[suggestion.field_name] = suggestion
        else:
            superseded.append(suggestion)

    return latest, superseded


def _active_job_for_app(db, app_id: int) -> ListingPublishJob | None:
    return db.execute(
        select(ListingPublishJob)
        .where(ListingPublishJob.app_id == app_id)
        .where(ListingPublishJob.status.in_(tuple(OPEN_JOB_STATUSES)))
        .order_by(ListingPublishJob.id.desc())
        .limit(1)
    ).scalar_one_or_none()


def _queue_bundle(
    db,
    *,
    app_id: int,
    actor: str,
    include_blocked_ids: set[int] | None = None,
    force_job: ListingPublishJob | None = None,
    is_retry: bool = False,
) -> dict:
    now = utcnow_naive()
    policy = _load_dispatch_policy(db)
    dispatch_window = _dispatch_window_label(policy)

    selected_by_field, superseded = _collect_latest_approved_listing_suggestions(db, app_id, include_blocked_ids=include_blocked_ids)
    selected_items = list(selected_by_field.values())

    if not selected_items:
        if force_job:
            force_job.status = "blocked"
            force_job.blocked_reason = "No approved listing suggestions are available for bundling."
            force_job.last_error = force_job.blocked_reason
            force_job.next_eligible_at = None
            force_job.scheduled_at = None
            db.commit()
        return {
            "status": "blocked",
            "message": "No approved listing suggestions are available for bundling.",
            "job_id": force_job.id if force_job else None,
        }

    active_job = force_job or _active_job_for_app(db, app_id)
    if active_job is None:
        active_job = ListingPublishJob(
            app_id=app_id,
            job_type="listing_bundle",
            status="queued_bundle",
            created_by=actor,
        )
        db.add(active_job)
        db.flush()

    final_selected: list[Suggestion] = []
    for suggestion in selected_items:
        guard_reason = _queue_guard_reason(suggestion, db=db, policy=policy, now=now)
        if guard_reason:
            _set_blocked_state(suggestion, now=now, reason=guard_reason, job_id=active_job.id, actor="system")
            continue
        final_selected.append(suggestion)

    if not final_selected:
        active_job.status = "blocked"
        active_job.blocked_reason = "All listing suggestions were blocked by compliance guards before queueing."
        active_job.last_error = active_job.blocked_reason
        active_job.next_eligible_at = None
        active_job.scheduled_at = None
        db.commit()
        return {
            "status": "blocked",
            "message": active_job.blocked_reason,
            "job_id": active_job.id,
        }

    keep_existing = active_job.next_eligible_at if active_job.status in {"queued_bundle", "waiting_safe_window"} else None
    next_eligible_at, jitter_seconds = _compute_next_eligible(
        db,
        app_id=app_id,
        policy=policy,
        now=now,
        keep_existing=keep_existing,
    )

    active_job.title_value = next((s.new_value for s in final_selected if s.field_name == "title"), None)
    active_job.short_description_value = next((s.new_value for s in final_selected if s.field_name == "short_description"), None)
    active_job.long_description_value = next((s.new_value for s in final_selected if s.field_name == "long_description"), None)
    active_job.suggestion_ids = _serialize_ids([s.id for s in final_selected])
    active_job.dispatch_window = dispatch_window
    active_job.jitter_seconds = jitter_seconds
    active_job.min_gap_minutes = policy["min_gap_minutes"]
    active_job.next_eligible_at = next_eligible_at
    active_job.scheduled_at = next_eligible_at
    active_job.blocked_reason = None
    active_job.last_error = None
    active_job.dry_run = is_true(policy["config"].get("dry_run"), True)
    active_job.status = "waiting_safe_window" if next_eligible_at > now else "queued_bundle"

    queue_status = active_job.status
    queue_message = (
        f"Queued in Listing Bundle #{active_job.id}. Waiting safe window until {next_eligible_at.isoformat()} UTC."
        if queue_status == "waiting_safe_window"
        else f"Queued in Listing Bundle #{active_job.id}. Ready for paced dispatch."
    )

    for suggestion in final_selected:
        _set_waiting_state(
            suggestion,
            now=now,
            actor=actor,
            status=queue_status,
            message=queue_message,
            job_id=active_job.id,
            next_eligible_at=next_eligible_at,
            dispatch_window=dispatch_window,
        )

    supersede_message = f"Superseded by listing bundle #{active_job.id}; latest approved value for this field won."
    for suggestion in superseded:
        _set_superseded(suggestion, now=now, message=supersede_message, job_id=active_job.id)

    db.commit()

    from app.workers.celery_app import celery_app

    delay_seconds = max(0, int((next_eligible_at - now).total_seconds()))
    try:
        celery_app.send_task(
            "dispatch_listing_bundle_job",
            kwargs={"job_id": active_job.id},
            countdown=delay_seconds,
            ignore_result=True,
        )
    except Exception as exc:
        logger.warning("Could not queue listing bundle dispatch for job %s: %s", active_job.id, exc)

    return {
        "status": queue_status,
        "job_id": active_job.id,
        "message": queue_message,
        "next_eligible_at": next_eligible_at.isoformat() if next_eligible_at else None,
        "dispatch_window": dispatch_window,
        "is_retry": is_retry,
    }


def queue_listing_bundle_for_suggestion(db, app_id: int, suggestion_id: int, actor: str) -> dict:
    include_blocked = {suggestion_id}
    return _queue_bundle(
        db,
        app_id=app_id,
        actor=actor,
        include_blocked_ids=include_blocked,
        is_retry=False,
    )


def retry_listing_bundle_job(db, app_id: int, job_id: int, actor: str) -> dict:
    job = db.execute(
        select(ListingPublishJob)
        .where(ListingPublishJob.id == job_id)
        .where(ListingPublishJob.app_id == app_id)
    ).scalar_one_or_none()
    if job is None:
        return {"status": "not_found", "message": "Publish job not found"}
    if job.status not in {"blocked", "failed", "superseded"}:
        return {
            "status": "invalid_state",
            "message": f"Job retry allowed only for blocked/failed jobs (current={job.status})",
            "job_id": job.id,
        }

    include_blocked_ids = set(_parse_ids(job.suggestion_ids))
    for suggestion in db.execute(
        select(Suggestion)
        .where(Suggestion.app_id == app_id)
        .where(Suggestion.id.in_(tuple(include_blocked_ids or {0})))
    ).scalars().all():
        if suggestion.status == "superseded":
            continue
        if suggestion.status in {"approved", "published"}:
            suggestion.status = "approved"
        suggestion.publish_status = "ready"
        suggestion.publish_message = "Retry requested by admin. Re-entering paced listing queue."
        suggestion.publish_block_reason = None
        suggestion.publish_completed_at = None
        suggestion.last_transition_at = utcnow_naive()

    job.retry_count = int(job.retry_count or 0) + 1
    job.status = "queued_bundle"
    job.blocked_reason = None
    job.last_error = None
    job.executed_at = None

    return _queue_bundle(
        db,
        app_id=app_id,
        actor=actor,
        include_blocked_ids=include_blocked_ids,
        force_job=job,
        is_retry=True,
    )


def list_publish_jobs(db, app_id: int, limit: int = 25) -> list[dict]:
    rows = db.execute(
        select(ListingPublishJob)
        .where(ListingPublishJob.app_id == app_id)
        .order_by(ListingPublishJob.id.desc())
        .limit(limit)
    ).scalars().all()

    payload: list[dict] = []
    for job in rows:
        payload.append(
            {
                "id": job.id,
                "job_type": job.job_type,
                "status": job.status,
                "next_eligible_at": job.next_eligible_at.isoformat() if job.next_eligible_at else None,
                "scheduled_at": job.scheduled_at.isoformat() if job.scheduled_at else None,
                "executed_at": job.executed_at.isoformat() if job.executed_at else None,
                "blocked_reason": job.blocked_reason,
                "dispatch_window": job.dispatch_window,
                "jitter_seconds": job.jitter_seconds,
                "min_gap_minutes": job.min_gap_minutes,
                "suggestion_ids": _parse_ids(job.suggestion_ids),
                "retry_count": job.retry_count,
            }
        )
    return payload


def _limits_guard_reason(db, app_id: int, now: datetime) -> str | None:
    allowed, reason = execution.can_publish(app_id, db, publish_kind="listing", now=now)
    if not allowed:
        return reason
    return None


def _credentials_for_app(db, app_id: int) -> str | None:
    cred_row = db.execute(
        select(AppCredential)
        .where(AppCredential.app_id == app_id)
        .where(AppCredential.credential_type == "service_account_json")
    ).scalar_one_or_none()
    if cred_row is None:
        return None
    try:
        return decrypt_value(cred_row.value)
    except Exception:
        return None


def dispatch_listing_bundle_job(db, job_id: int) -> dict:
    job = db.execute(select(ListingPublishJob).where(ListingPublishJob.id == job_id)).scalar_one_or_none()
    if job is None:
        return {"status": "skipped", "reason": "job not found"}
    if job.status in FINAL_JOB_STATUSES:
        return {"status": "skipped", "reason": f"job already {job.status}"}

    now = utcnow_naive()
    policy = _load_dispatch_policy(db)
    dry_run = is_true(policy["config"].get("dry_run"), True)

    if not _window_contains(now, policy["window_start"], policy["window_end"]):
        next_eligible = _align_to_window(now, policy["window_start"], policy["window_end"])
        job.status = "waiting_safe_window"
        job.next_eligible_at = next_eligible
        job.scheduled_at = next_eligible
        job.dispatch_window = _dispatch_window_label(policy)
        db.commit()
        from app.workers.celery_app import celery_app

        celery_app.send_task(
            "dispatch_listing_bundle_job",
            kwargs={"job_id": job.id},
            countdown=max(1, int((next_eligible - now).total_seconds())),
            ignore_result=True,
        )
        return {"status": "waiting_safe_window", "next_eligible_at": next_eligible.isoformat()}

    if job.next_eligible_at and now < job.next_eligible_at:
        wait_seconds = max(1, int((job.next_eligible_at - now).total_seconds()))
        job.status = "waiting_safe_window"
        db.commit()

        from app.workers.celery_app import celery_app

        celery_app.send_task(
            "dispatch_listing_bundle_job",
            kwargs={"job_id": job.id},
            countdown=wait_seconds,
            ignore_result=True,
        )
        return {"status": "waiting_safe_window", "next_eligible_at": job.next_eligible_at.isoformat()}

    app = db.execute(select(App).where(App.id == job.app_id)).scalar_one_or_none()
    if app is None:
        job.status = "failed"
        job.last_error = "App not found"
        db.commit()
        return {"status": "failed", "reason": "app not found"}

    linked_ids = _parse_ids(job.suggestion_ids)
    if not linked_ids:
        job.status = "blocked"
        job.blocked_reason = "No suggestions linked to this listing bundle"
        job.last_error = job.blocked_reason
        db.commit()
        return {"status": "blocked", "reason": job.blocked_reason}

    linked_rows = db.execute(
        select(Suggestion)
        .where(Suggestion.app_id == job.app_id)
        .where(Suggestion.id.in_(tuple(linked_ids)))
        .where(Suggestion.suggestion_type == "listing")
        .order_by(Suggestion.id.desc())
    ).scalars().all()

    latest_by_field: dict[str, Suggestion] = {}
    stale: list[Suggestion] = []
    for item in linked_rows:
        if item.status != "approved":
            continue
        if item.field_name not in LISTING_FIELDS:
            continue
        if item.field_name not in latest_by_field:
            latest_by_field[item.field_name] = item
        else:
            stale.append(item)

    final_items = list(latest_by_field.values())
    if not final_items:
        reason = "No approved listing suggestions remain in this bundle."
        job.status = "blocked"
        job.blocked_reason = reason
        job.last_error = reason
        db.commit()
        return {"status": "blocked", "reason": reason}

    limits_reason = _limits_guard_reason(db, app.id, now)
    if limits_reason:
        job.status = "blocked"
        job.blocked_reason = limits_reason
        job.last_error = limits_reason
        job.next_eligible_at = None
        job.executed_at = now
        for suggestion in final_items:
            _set_blocked_state(suggestion, now=now, reason=limits_reason, job_id=job.id)
        db.commit()
        return {"status": "blocked", "reason": limits_reason}

    churn_count = _count_recent_executions(db, app.id, now - timedelta(hours=24))
    if churn_count >= policy["churn_max_per_24h"]:
        reason = (
            f"Blocked by churn guard: {churn_count} listing publish execution(s) in last 24h. "
            "Retry later to keep account behavior safe."
        )
        job.status = "blocked"
        job.blocked_reason = reason
        job.last_error = reason
        job.executed_at = now
        for suggestion in final_items:
            _set_blocked_state(suggestion, now=now, reason=reason, job_id=job.id)
        db.commit()
        return {"status": "blocked", "reason": reason}

    for suggestion in final_items:
        reason = _queue_guard_reason(suggestion, db=db, policy=policy, now=now)
        if reason:
            job.status = "blocked"
            job.blocked_reason = reason
            job.last_error = reason
            job.executed_at = now
            _set_blocked_state(suggestion, now=now, reason=reason, job_id=job.id)
            db.commit()
            return {"status": "blocked", "reason": reason}

    credential_json = _credentials_for_app(db, app.id)
    if not dry_run and not credential_json:
        reason = "Missing Google Play credential. Live listing publish cannot start."
        job.status = "blocked"
        job.blocked_reason = reason
        job.last_error = reason
        job.executed_at = now
        for suggestion in final_items:
            _set_blocked_state(suggestion, now=now, reason=reason, job_id=job.id)
        db.commit()
        return {"status": "blocked", "reason": reason}

    job.status = "publishing"
    job.dry_run = dry_run
    job.blocked_reason = None
    job.last_error = None
    job.title_value = next((s.new_value for s in final_items if s.field_name == "title"), None)
    job.short_description_value = next((s.new_value for s in final_items if s.field_name == "short_description"), None)
    job.long_description_value = next((s.new_value for s in final_items if s.field_name == "long_description"), None)
    job.suggestion_ids = _serialize_ids([s.id for s in final_items])

    for suggestion in final_items:
        _set_publishing_state(suggestion, now=now, job_id=job.id)
    for suggestion in stale:
        _set_superseded(
            suggestion,
            now=now,
            message=f"Superseded by latest value inside listing bundle #{job.id} before dispatch.",
            job_id=job.id,
        )

    db.commit()

    result = execution.publish_listing_bundle(
        app=app,
        credential_json=credential_json,
        dry_run=dry_run,
        db=db,
        title=job.title_value,
        short_description=job.short_description_value,
        long_description=job.long_description_value,
    )

    completed_at = utcnow_naive()
    if result.get("success"):
        if result.get("dry_run"):
            final_publish_status = "dry_run_only"
        elif result.get("status") == "soft_published":
            final_publish_status = "soft_published"
        else:
            final_publish_status = "published"

        job.status = final_publish_status
        job.executed_at = completed_at
        job.blocked_reason = None
        message = (
            f"Dry run listing bundle #{job.id} simulated successfully."
            if final_publish_status == "dry_run_only"
            else f"Listing bundle #{job.id} saved as draft edit."
            if final_publish_status == "soft_published"
            else f"Listing bundle #{job.id} published on Google Play."
        )
        for suggestion in final_items:
            _set_result_state(
                suggestion,
                now=completed_at,
                job_id=job.id,
                publish_status=final_publish_status,
                message=message,
                edit_id=result.get("edit_id"),
            )

        db.commit()
        return {
            "status": job.status,
            "job_id": job.id,
            "message": message,
            "dry_run": bool(result.get("dry_run")),
        }

    reason = result.get("message") or "Listing bundle publish failed"
    is_blocked = result.get("status") == "blocked"
    job.status = "blocked" if is_blocked else "failed"
    job.last_error = reason
    job.blocked_reason = reason
    job.executed_at = completed_at

    for suggestion in final_items:
        if is_blocked:
            _set_blocked_state(suggestion, now=completed_at, reason=reason, job_id=job.id)
        else:
            _set_failed_state(suggestion, now=completed_at, reason=reason, job_id=job.id)

    db.commit()
    return {"status": "blocked" if is_blocked else "failed", "job_id": job.id, "reason": reason}
