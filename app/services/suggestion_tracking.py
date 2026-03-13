"""Suggestion review and publish state tracking helpers."""
from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any


SUGGESTION_TIMELINE = [
    ("created", "Created by pipeline"),
    ("reviewed", "Reviewed manually"),
    ("queued_for_publish", "Queued for publish"),
    ("waiting_safe_window", "Waiting safe window"),
    ("publish_attempted", "Publish attempted"),
    ("publish_result", "Publish result"),
]


def utcnow_naive() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


def build_status_log(created_at: datetime | None = None, message: str = "Suggestion created by pipeline") -> list[dict[str, Any]]:
    created_iso = (created_at or utcnow_naive()).isoformat()
    stages: list[dict[str, Any]] = []
    for index, (key, label) in enumerate(SUGGESTION_TIMELINE):
        is_created = index == 0
        stages.append(
            {
                "key": key,
                "label": label,
                "status": "completed" if is_created else "pending",
                "started_at": created_iso if is_created else None,
                "completed_at": created_iso if is_created else None,
                "message": message if is_created else "",
                "actor": "system" if is_created else None,
            }
        )
    return stages


def parse_status_log(raw_value: str | None, created_at: datetime | None = None) -> list[dict[str, Any]]:
    if raw_value:
        try:
            data = json.loads(raw_value)
            if isinstance(data, list):
                return data
        except Exception:
            pass
    return build_status_log(created_at=created_at)


def serialize_status_log(stages: list[dict[str, Any]]) -> str:
    return json.dumps(stages)


def update_status_stage(
    stages: list[dict[str, Any]],
    key: str,
    *,
    status: str,
    message: str | None = None,
    actor: str | None = None,
    occurred_at: datetime | None = None,
) -> list[dict[str, Any]]:
    timestamp = (occurred_at or utcnow_naive()).isoformat()
    for stage in stages:
        if stage.get("key") != key:
            continue
        if status != "pending" and not stage.get("started_at"):
            stage["started_at"] = timestamp
        if status in {"completed", "failed", "blocked", "skipped"}:
            stage["completed_at"] = timestamp
        stage["status"] = status
        if message is not None:
            stage["message"] = message
        if actor is not None:
            stage["actor"] = actor
        break
    return stages


def resolve_publish_status(suggestion) -> str | None:
    status = getattr(suggestion, "publish_status", None)
    if status:
        return status
    if getattr(suggestion, "status", None) == "published":
        return "published"
    if getattr(suggestion, "status", None) == "approved":
        return "ready"
    return None


def resolve_review_status(suggestion) -> str:
    status = getattr(suggestion, "status", "pending")
    if status == "pending":
        return "pending"
    if status == "rejected":
        return "rejected"
    if status == "superseded":
        return "superseded"
    if status == "rolled_back":
        return "rolled_back"
    return "approved"


def hydrate_status_log(suggestion) -> list[dict[str, Any]]:
    stages = parse_status_log(getattr(suggestion, "status_log", None), getattr(suggestion, "created_at", None))
    review_status = resolve_review_status(suggestion)
    publish_status = resolve_publish_status(suggestion)

    if review_status == "pending":
        update_status_stage(stages, "reviewed", status="pending", message="", actor=None)
    elif review_status == "superseded":
        superseded_message = getattr(suggestion, "publish_message", None) or "Superseded by a newer pipeline run before manual review."
        update_status_stage(
            stages,
            "reviewed",
            status="skipped",
            message=superseded_message,
            actor="system",
            occurred_at=getattr(suggestion, "last_transition_at", None) or getattr(suggestion, "updated_at", None),
        )
        update_status_stage(
            stages,
            "publish_result",
            status="blocked",
            message=superseded_message,
            actor="system",
            occurred_at=getattr(suggestion, "last_transition_at", None) or getattr(suggestion, "updated_at", None),
        )
    elif review_status == "rejected":
        update_status_stage(
            stages,
            "reviewed",
            status="completed",
            message=(getattr(suggestion, "reasoning", "") or "Rejected during review")[:240],
            actor=getattr(suggestion, "reviewed_by", None) or "system",
            occurred_at=getattr(suggestion, "last_transition_at", None) or getattr(suggestion, "updated_at", None),
        )
        update_status_stage(
            stages,
            "publish_result",
            status="blocked",
            message="Rejected in review. Not sent to Google publish flow.",
            actor=getattr(suggestion, "reviewed_by", None) or "system",
            occurred_at=getattr(suggestion, "last_transition_at", None) or getattr(suggestion, "updated_at", None),
        )
    else:
        update_status_stage(
            stages,
            "reviewed",
            status="completed",
            message=f"Approved by {getattr(suggestion, 'reviewed_by', None) or 'system'}",
            actor=getattr(suggestion, "reviewed_by", None) or "system",
            occurred_at=getattr(suggestion, "last_transition_at", None) or getattr(suggestion, "updated_at", None),
        )

    if publish_status in {"ready", "queued", "queued_bundle", "publishing", "waiting_safe_window", "published", "dry_run_only", "blocked", "failed", "superseded"}:
        queue_status = "completed" if publish_status != "ready" else "pending"
        if publish_status == "superseded":
            queue_status = "blocked"
        queue_message = getattr(suggestion, "publish_message", None) or "Waiting for publish queue."
        update_status_stage(
            stages,
            "queued_for_publish",
            status=queue_status,
            message=queue_message,
            actor="system",
            occurred_at=getattr(suggestion, "last_transition_at", None) or getattr(suggestion, "updated_at", None),
        )

    if publish_status in {"waiting_safe_window", "queued_bundle"}:
        update_status_stage(
            stages,
            "waiting_safe_window",
            status="running",
            message=getattr(suggestion, "publish_message", None) or "Waiting for the next safe publish window.",
            actor="system",
            occurred_at=getattr(suggestion, "last_transition_at", None) or getattr(suggestion, "updated_at", None),
        )
    elif publish_status in {"blocked", "failed", "superseded"}:
        update_status_stage(
            stages,
            "waiting_safe_window",
            status="blocked" if publish_status in {"blocked", "superseded"} else "skipped",
            message=getattr(suggestion, "publish_message", None) or "Publish was stopped before completion.",
            actor="system",
            occurred_at=getattr(suggestion, "publish_completed_at", None) or getattr(suggestion, "last_transition_at", None),
        )
    elif publish_status in {"published", "dry_run_only"}:
        update_status_stage(
            stages,
            "waiting_safe_window",
            status="completed",
            message="Publish window available.",
            actor="system",
            occurred_at=getattr(suggestion, "publish_started_at", None) or getattr(suggestion, "last_transition_at", None),
        )

    if publish_status in {"publishing", "published", "dry_run_only", "failed"}:
        attempt_status = "running" if publish_status == "publishing" else ("failed" if publish_status == "failed" else "completed")
        update_status_stage(
            stages,
            "publish_attempted",
            status=attempt_status,
            message=getattr(suggestion, "publish_message", None) or "Publish attempt started.",
            actor="system",
            occurred_at=getattr(suggestion, "publish_started_at", None) or getattr(suggestion, "last_transition_at", None),
        )

    if publish_status in {"published", "dry_run_only", "blocked", "failed", "superseded"}:
        final_status = (
            "completed"
            if publish_status in {"published", "dry_run_only"}
            else ("blocked" if publish_status in {"blocked", "superseded"} else "failed")
        )
        update_status_stage(
            stages,
            "publish_result",
            status=final_status,
            message=getattr(suggestion, "publish_message", None) or "Publish flow finished.",
            actor="system",
            occurred_at=getattr(suggestion, "publish_completed_at", None) or getattr(suggestion, "last_transition_at", None),
        )

    return stages


def apply_status_log(suggestion, stages: list[dict[str, Any]]) -> None:
    suggestion.status_log = serialize_status_log(stages)


def build_publish_response_status(suggestion) -> dict[str, Any]:
    review_status = resolve_review_status(suggestion)
    publish_status = resolve_publish_status(suggestion)
    return {
        "review_status": review_status,
        "publish_status": publish_status,
        "published_live": bool(getattr(suggestion, "published_live", False)),
        "is_dry_run_result": bool(getattr(suggestion, "is_dry_run_result", False)),
    }
