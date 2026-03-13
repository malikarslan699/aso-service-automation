"""Daily ASO pipeline task with step tracking, provider analytics, and fallback-aware status."""
from __future__ import annotations

import json
import logging
from datetime import datetime, timezone

from redis import Redis

from app.workers.celery_app import celery_app
from app.services.publish_guard import should_skip_candidate

logger = logging.getLogger(__name__)


def _acquire_pipeline_lock(redis_url: str, app_id: int, token: str, ttl_seconds: int = 3600) -> tuple[Redis | None, str, bool]:
    lock_key = f"pipeline_lock:app_{app_id}"
    try:
        redis_client = Redis.from_url(redis_url, decode_responses=True)
        acquired = bool(redis_client.set(lock_key, token, ex=ttl_seconds, nx=True))
        return redis_client, lock_key, acquired
    except Exception as exc:
        logger.warning("Pipeline lock unavailable for app %s; continuing without lock: %s", app_id, exc)
        return None, lock_key, True


def _release_pipeline_lock(redis_client: Redis | None, lock_key: str, token: str) -> None:
    if redis_client is None:
        return
    try:
        current_token = redis_client.get(lock_key)
        if current_token == token:
            redis_client.delete(lock_key)
    except Exception as exc:
        logger.warning("Failed to release pipeline lock %s: %s", lock_key, exc)

def _dedupe_suggestions(
    validated: list[dict],
    existing_suggestions: list[dict],
    current_pipeline_run_id: int | None = None,
) -> tuple[list[dict], int, dict[str, int]]:
    # Pending suggestions from older runs should not block fresh suggestions.
    # They are superseded later once this run creates new items.
    dedupe_context = [
        item
        for item in list(existing_suggestions)
        if not (
            item.get("status") == "pending"
            and current_pipeline_run_id is not None
            and item.get("pipeline_run_id") not in {None, current_pipeline_run_id}
        )
    ]
    deduped: list[dict] = []
    duplicates_skipped = 0
    skip_reasons: dict[str, int] = {}

    for suggestion in validated:
        should_skip, reason = should_skip_candidate(suggestion, dedupe_context)
        if should_skip:
            duplicates_skipped += 1
            reason_key = (reason or "duplicate").strip().lower()
            skip_reasons[reason_key] = skip_reasons.get(reason_key, 0) + 1
            continue

        deduped.append(suggestion)
        dedupe_context.append(
            {
                "field_name": suggestion.get("field_name", ""),
                "new_value": suggestion.get("new_value", ""),
                "status": suggestion.get("status", "pending"),
                "created_at": datetime.now(timezone.utc).replace(tzinfo=None).isoformat(),
                "published_at": None,
            }
        )

    return deduped, duplicates_skipped, skip_reasons


def _supersede_old_pending_suggestions(app_id: int, current_pipeline_run_id: int, db) -> int:
    from sqlalchemy import select, or_
    from app.models.suggestion import Suggestion
    from app.services.suggestion_tracking import apply_status_log, parse_status_log, update_status_stage, utcnow_naive

    stale_pending = db.execute(
        select(Suggestion)
        .where(Suggestion.app_id == app_id)
        .where(Suggestion.status == "pending")
        .where(or_(Suggestion.pipeline_run_id.is_(None), Suggestion.pipeline_run_id != current_pipeline_run_id))
    ).scalars().all()

    if not stale_pending:
        return 0

    now = utcnow_naive()
    for suggestion in stale_pending:
        suggestion.status = "superseded"
        suggestion.reviewed_by = "system"
        suggestion.publish_status = "superseded"
        suggestion.publish_message = f"Superseded by newer pipeline run #{current_pipeline_run_id} before manual review."
        suggestion.publish_block_reason = suggestion.publish_message
        suggestion.last_transition_at = now

        suggestion_log = parse_status_log(suggestion.status_log, suggestion.created_at)
        suggestion_log = update_status_stage(
            suggestion_log,
            "reviewed",
            status="skipped",
            message=suggestion.publish_message,
            actor="system",
            occurred_at=now,
        )
        suggestion_log = update_status_stage(
            suggestion_log,
            "publish_result",
            status="blocked",
            message=suggestion.publish_message,
            actor="system",
            occurred_at=now,
        )
        apply_status_log(suggestion, suggestion_log)

    db.commit()
    return len(stale_pending)


@celery_app.task(name="daily_pipeline", bind=True, max_retries=2)
def run_daily_pipeline(
    self,
    app_id: int,
    trigger: str = "scheduled",
    pipeline_run_id: int | None = None,
    dry_run_override: bool | None = None,
):
    from sqlalchemy import create_engine, select
    from sqlalchemy.orm import Session

    from app.config import get_settings
    from app.models.app import App
    from app.models.app_credential import AppCredential
    from app.models.app_fact import AppFact
    from app.models.pipeline_run import PipelineRun
    from app.models.suggestion import Suggestion
    from app.services import ai_engine, auto_approve_engine, data_fetcher, human_simulator, notifier, safety_validator
    from app.services.keywords import run_discovery
    from app.services.pipeline_tracking import build_step_log, compute_overall_status, serialize_step_log, update_step
    from app.services.runtime_config import as_int, is_true, load_runtime_config
    from app.services.suggestion_tracking import apply_status_log, build_status_log, parse_status_log, update_status_stage, utcnow_naive
    from app.utils.encryption import decrypt_value

    settings = get_settings()
    engine = create_engine(settings.database_url_sync)
    request_id = getattr(getattr(self, "request", None), "id", "unknown")
    lock_token = f"{request_id}:{pipeline_run_id or 'new'}"
    redis_client, lock_key, lock_acquired = _acquire_pipeline_lock(settings.redis_url, app_id, lock_token)

    if not lock_acquired:
        logger.info("Pipeline already running for app %s, skipping duplicate dispatch.", app_id)
        with Session(engine) as db:
            if pipeline_run_id is not None:
                duplicate_run = db.execute(select(PipelineRun).where(PipelineRun.id == pipeline_run_id)).scalar_one_or_none()
                if duplicate_run and duplicate_run.status in {"queued", "running"}:
                    duplicate_run.status = "skipped"
                    duplicate_run.error_message = "Skipped duplicate dispatch: another pipeline is already running for this app."
                    duplicate_run.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                    duplicate_run.step_log = serialize_step_log(
                        update_step(
                            build_step_log(),
                            "finalization",
                            status="skipped",
                            message=duplicate_run.error_message,
                        )
                    )
                    db.commit()
        return {
            "status": "skipped",
            "app_id": app_id,
            "reason": "duplicate_pipeline_lock",
        }

    def persist_run(db: Session, run: PipelineRun, step_log: list[dict]) -> None:
        run.step_log = serialize_step_log(step_log)
        run.steps_completed = sum(1 for step in step_log if step.get("status") == "completed")
        run.total_steps = len(step_log)
        db.commit()

    with Session(engine) as db:
        pipeline_run = None
        step_log = build_step_log()
        suggestions_generated = 0
        duplicates_skipped = 0
        duplicate_reason_counts: dict[str, int] = {}
        auto_approved = 0
        high_risk = []

        try:
            if pipeline_run_id is not None:
                pipeline_run = db.execute(select(PipelineRun).where(PipelineRun.id == pipeline_run_id)).scalar_one_or_none()
                if pipeline_run is None:
                    raise ValueError(f"PipelineRun {pipeline_run_id} not found")
                # Respect cancel requests made before the worker picked up the task
                if pipeline_run.status == "cancelled":
                    logger.info("Pipeline run %s was cancelled before worker started — exiting early", pipeline_run_id)
                    return
                pipeline_run.status = "running"
                pipeline_run.trigger = trigger
                pipeline_run.total_steps = len(step_log)
                pipeline_run.error_message = None
                step_log = build_step_log()
                if pipeline_run.started_at is None:
                    pipeline_run.started_at = datetime.now(timezone.utc).replace(tzinfo=None)
            else:
                pipeline_run = PipelineRun(
                    app_id=app_id,
                    status="running",
                    trigger=trigger,
                    steps_completed=0,
                    total_steps=len(step_log),
                    started_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
                db.add(pipeline_run)
                db.commit()
                db.refresh(pipeline_run)

            step_log = update_step(step_log, "queue_accepted", status="completed", message="Pipeline accepted by the worker queue")
            step_log = update_step(step_log, "run_started", status="completed", message="Worker picked up the pipeline run")
            persist_run(db, pipeline_run, step_log)

            app = db.execute(select(App).where(App.id == app_id)).scalar_one_or_none()
            if app is None:
                raise ValueError(f"App {app_id} not found")

            if app.status != "active":
                step_log = update_step(step_log, "finalization", status="skipped", message=f"App status is {app.status}")
                pipeline_run.status = "skipped"
                pipeline_run.error_message = f"App status={app.status}"
                pipeline_run.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                persist_run(db, pipeline_run, step_log)
                return {"status": "skipped", "reason": f"App status={app.status}"}

            config_values = load_runtime_config(db)
            dry_run = True if dry_run_override is True else is_true(config_values.get("dry_run"), settings.dry_run)
            human_sim_enabled = is_true(config_values.get("human_sim_enabled"), False)
            manual_approval_required = is_true(config_values.get("manual_approval_required"), True)
            auto_approve_threshold = as_int(config_values.get("auto_approve_threshold"), 0)
            credential_rows = db.execute(
                select(AppCredential)
                .where(AppCredential.app_id == app_id)
                .where(
                    AppCredential.credential_type.in_(
                        ("service_account_json", "anthropic_api_key", "openai_api_key")
                    )
                )
            ).scalars().all()

            credential_map: dict[str, str] = {}
            for row in credential_rows:
                try:
                    credential_map[row.credential_type] = decrypt_value(row.value)
                except Exception:
                    continue

            credential_json = credential_map.get("service_account_json")
            anthropic_api_key = credential_map.get("anthropic_api_key") or config_values.get("anthropic_api_key") or settings.anthropic_api_key
            openai_api_key = credential_map.get("openai_api_key") or config_values.get("openai_api_key") or settings.openai_api_key

            facts = db.execute(select(AppFact).where(AppFact.app_id == app_id)).scalars().all()
            app_facts = [{"fact_key": fact.fact_key, "fact_value": fact.fact_value, "verified": fact.verified} for fact in facts]

            step_log = update_step(step_log, "app_data_fetch", status="running", message="Fetching listing and reviews")
            persist_run(db, pipeline_run, step_log)
            current_listing = data_fetcher.fetch_listing(app.package_name)
            reviews = data_fetcher.fetch_reviews(app.package_name, count=20)
            step_log = update_step(
                step_log,
                "app_data_fetch",
                status="completed",
                message=f"Fetched listing, reviews, and {'credential' if credential_json else 'no credential'} context",
            )
            persist_run(db, pipeline_run, step_log)

            pip_min = as_int(config_values.get("pipeline_delay_min_minutes"), 5)
            pip_max = as_int(config_values.get("pipeline_delay_max_minutes"), 20)
            delay_seconds = human_simulator.compute_pipeline_delay_seconds(
                dry_run=dry_run,
                enabled=human_sim_enabled,
                min_minutes=pip_min,
                max_minutes=pip_max,
            )
            if delay_seconds > 0:
                delay_minutes = max(1, (delay_seconds + 59) // 60)
                step_log = update_step(
                    step_log,
                    "keyword_discovery",
                    status="running",
                    message=f"Waiting {delay_minutes} min (human sim delay)",
                )
                persist_run(db, pipeline_run, step_log)
                human_simulator.pipeline_delay_sync(
                    dry_run=dry_run,
                    enabled=human_sim_enabled,
                    delay_seconds=delay_seconds,
                )

            step_log = update_step(step_log, "keyword_discovery", status="running", message="Running keyword discovery")
            persist_run(db, pipeline_run, step_log)
            keyword_result = run_discovery(
                app_id=app_id,
                package_name=app.package_name,
                app_facts=app_facts,
                db=db,
                anthropic_api_key=anthropic_api_key,
                openai_api_key=openai_api_key,
            )
            top_keywords = keyword_result.get("keywords", [])
            rising_trends = keyword_result.get("rising_trends", [])
            pipeline_run.keywords_discovered = len(top_keywords)
            pipeline_run.estimated_cost = round(float(pipeline_run.estimated_cost or 0.0) + float(keyword_result.get("cluster_estimated_cost", 0.0)), 6)
            pipeline_run.input_tokens = int(pipeline_run.input_tokens or 0) + int(keyword_result.get("cluster_input_tokens", 0) or 0)
            pipeline_run.output_tokens = int(pipeline_run.output_tokens or 0) + int(keyword_result.get("cluster_output_tokens", 0) or 0)
            step_log = update_step(
                step_log,
                "keyword_discovery",
                status="completed",
                message=f"Discovered {len(top_keywords)} active keywords",
                provider=keyword_result.get("cluster_provider"),
                estimated_cost=keyword_result.get("cluster_estimated_cost", 0.0),
                input_tokens=keyword_result.get("cluster_input_tokens", 0),
                output_tokens=keyword_result.get("cluster_output_tokens", 0),
            )
            persist_run(db, pipeline_run, step_log)

            if rising_trends:
                notifier.send_keyword_opportunity(rising_trends, app.name, db)

            recent_suggestions = [
                {
                    "field_name": suggestion.field_name,
                    "new_value": suggestion.new_value,
                    "status": suggestion.status,
                    "pipeline_run_id": suggestion.pipeline_run_id,
                    "created_at": suggestion.created_at.isoformat() if suggestion.created_at else "",
                    "published_at": suggestion.published_at.isoformat() if suggestion.published_at else "",
                }
                for suggestion in db.execute(
                    select(Suggestion).where(Suggestion.app_id == app_id).order_by(Suggestion.id.desc()).limit(250)
                ).scalars().all()
            ]

            step_log = update_step(step_log, "duplicate_filtering", status="running", message="Preparing AI-safe dedupe context")
            persist_run(db, pipeline_run, step_log)
            ai_result = ai_engine.generate_suggestions(
                app_facts=app_facts,
                current_listing=current_listing,
                top_keywords=top_keywords,
                anthropic_api_key=anthropic_api_key,
                openai_api_key=openai_api_key,
                reviews=reviews,
            )
            pipeline_run.provider_name = ai_result.get("provider_name")
            pipeline_run.fallback_provider_name = ai_result.get("fallback_provider_name")
            pipeline_run.provider_status = ai_result.get("provider_status")
            pipeline_run.provider_error_class = ai_result.get("provider_error_class")
            pipeline_run.estimated_cost = round(float(pipeline_run.estimated_cost or 0.0) + float(ai_result.get("estimated_cost", 0.0)), 6)
            pipeline_run.input_tokens = int(pipeline_run.input_tokens or 0) + int(ai_result.get("input_tokens", 0) or 0)
            pipeline_run.output_tokens = int(pipeline_run.output_tokens or 0) + int(ai_result.get("output_tokens", 0) or 0)

            raw_suggestions = ai_result.get("suggestions", [])
            if raw_suggestions:
                step_log = update_step(
                    step_log,
                    "ai_generation",
                    status="completed",
                    message=ai_result.get("message", f"Generated {len(raw_suggestions)} AI suggestion(s)"),
                    provider=ai_result.get("provider_name"),
                    estimated_cost=ai_result.get("estimated_cost", 0.0),
                    input_tokens=ai_result.get("input_tokens", 0),
                    output_tokens=ai_result.get("output_tokens", 0),
                )
            else:
                pipeline_run.error_message = ai_result.get("message") or "AI generation returned 0 suggestions."
                step_log = update_step(
                    step_log,
                    "ai_generation",
                    status="failed",
                    message=pipeline_run.error_message,
                    provider=ai_result.get("provider_name"),
                    estimated_cost=ai_result.get("estimated_cost", 0.0),
                    input_tokens=ai_result.get("input_tokens", 0),
                    output_tokens=ai_result.get("output_tokens", 0),
                )

            validated = []
            for raw in raw_suggestions:
                result = safety_validator.validate(
                    suggestion=raw,
                    app_facts=app_facts,
                    recent_suggestions=recent_suggestions,
                )
                raw["risk_score"] = result["risk_score"]
                raw["safety_result"] = json.dumps(result)
                raw["status"] = "pending"
                validated.append(raw)

            validated, duplicates_skipped, duplicate_reason_counts = _dedupe_suggestions(validated, recent_suggestions, pipeline_run.id)
            pipeline_run.duplicates_skipped = duplicates_skipped
            reason_summary = ", ".join(f"{key}: {count}" for key, count in sorted(duplicate_reason_counts.items()))
            step_log = update_step(
                step_log,
                "duplicate_filtering",
                status="completed",
                message=(
                    f"Skipped {duplicates_skipped} duplicate or no-op suggestion(s)"
                    + (f" ({reason_summary})" if reason_summary else "")
                ),
            )
            persist_run(db, pipeline_run, step_log)

            step_log = update_step(step_log, "approval_creation", status="running", message="Storing validated suggestions")
            persist_run(db, pipeline_run, step_log)
            db_suggestions = []
            for validated_item in validated:
                extra = validated_item.pop("extra", {})
                suggestion = Suggestion(
                    app_id=app_id,
                    suggestion_type=validated_item["suggestion_type"],
                    field_name=validated_item["field_name"],
                    old_value=validated_item.get("old_value", ""),
                    new_value=validated_item["new_value"],
                    reasoning=validated_item.get("reasoning", ""),
                    risk_score=validated_item["risk_score"],
                    status=validated_item["status"],
                    safety_result=validated_item["safety_result"],
                    extra_data=json.dumps(extra or {}),
                    pipeline_run_id=pipeline_run.id,
                    last_transition_at=utcnow_naive(),
                )
                apply_status_log(suggestion, build_status_log(message="Suggestion created by pipeline"))
                db.add(suggestion)
                db_suggestions.append((suggestion, extra))

            db.flush()
            db.commit()
            suggestions_generated = len(db_suggestions)
            superseded_count = _supersede_old_pending_suggestions(app_id=app_id, current_pipeline_run_id=pipeline_run.id, db=db) if suggestions_generated else 0
            pipeline_run.suggestions_generated = suggestions_generated
            pipeline_run.approvals_created = suggestions_generated

            rules = auto_approve_engine.get_rules(app_id=app_id, db=db)
            if not manual_approval_required:
                for suggestion, _extra in db_suggestions:
                    if auto_approve_engine.should_auto_approve(
                        {"suggestion_type": suggestion.suggestion_type, "risk_score": suggestion.risk_score},
                        rules,
                        max_allowed_risk=auto_approve_threshold,
                    ):
                        suggestion.status = "approved"
                        suggestion.reviewed_by = "auto"
                        suggestion.publish_status = "ready"
                        suggestion.publish_message = "Auto-approved and ready for publish handling."
                        suggestion.last_transition_at = utcnow_naive()
                        suggestion_log = parse_status_log(suggestion.status_log, suggestion.created_at)
                        suggestion_log = update_status_stage(
                            suggestion_log,
                            "reviewed",
                            status="completed",
                            message="Auto-approved by rules.",
                            actor="auto",
                            occurred_at=suggestion.last_transition_at,
                        )
                        apply_status_log(suggestion, suggestion_log)
                        auto_approved += 1
                        notifier.send_auto_approve_notification(suggestion, app.name, suggestion.risk_score or 0, db)

            db.commit()
            step_log = update_step(
                step_log,
                "approval_creation",
                status="completed" if suggestions_generated else "skipped",
                message=(
                    f"Created {suggestions_generated} suggestion(s); {auto_approved} auto-approved; {superseded_count} old pending superseded"
                    if suggestions_generated
                    else "No suggestions were created, so Approvals stayed empty"
                ),
            )
            persist_run(db, pipeline_run, step_log)

            step_log = update_step(step_log, "publish_eligibility_check", status="running", message="Checking notification and publish readiness")
            persist_run(db, pipeline_run, step_log)
            high_risk = [suggestion for suggestion, _ in db_suggestions if suggestion.risk_score >= 2 and suggestion.status == "pending"]
            if high_risk:
                notifier.send_suggestion_alert(high_risk, app.name, db)

            for suggestion, _extra in db_suggestions:
                if suggestion.status == "approved":
                    celery_app.send_task(
                        "track_performance",
                        kwargs={"suggestion_id": suggestion.id, "app_id": app_id},
                        countdown=7 * 24 * 60 * 60,
                    )

            step_log = update_step(
                step_log,
                "publish_eligibility_check",
                status="completed",
                message=f"High-risk pending: {len(high_risk)}. Approved items prepared for tracking.",
            )

            pipeline_run.value_summary = (
                f"Keywords discovered: {pipeline_run.keywords_discovered}. "
                f"Suggestions created: {pipeline_run.suggestions_generated}. "
                f"Estimated provider cost: ${float(pipeline_run.estimated_cost or 0.0):.4f}."
            )
            step_log = update_step(
                step_log,
                "finalization",
                status="completed",
                message=(
                    "Pipeline finished with warnings: approvals remained empty because AI generation produced no valid suggestions."
                    if suggestions_generated == 0
                    else "Pipeline finished successfully."
                ),
            )
            pipeline_run.status = "completed_with_warnings" if suggestions_generated == 0 or pipeline_run.error_message else "completed"
            pipeline_run.status = compute_overall_status(step_log, pipeline_run.status, pipeline_run.error_message)
            pipeline_run.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
            persist_run(db, pipeline_run, step_log)

            # Pipeline completion summary to Telegram
            publish_mode_val = (config_values.get("publish_mode") or "live").strip().lower()
            pending_approval_count = suggestions_generated - auto_approved
            notifier.send_pipeline_summary(
                app_name=app.name,
                generated=suggestions_generated,
                pending_approval=max(0, pending_approval_count),
                auto_approved=auto_approved,
                publish_mode=publish_mode_val,
                manual_approval_required=manual_approval_required,
                db=db,
            )

            return {
                "status": pipeline_run.status,
                "pipeline_run_id": pipeline_run.id,
                "suggestions_generated": suggestions_generated,
                "duplicates_skipped": duplicates_skipped,
                "duplicate_reason_counts": duplicate_reason_counts,
                "auto_approved": auto_approved,
                "high_risk_count": len(high_risk),
                "superseded_count": superseded_count if suggestions_generated else 0,
                "keywords_discovered": pipeline_run.keywords_discovered,
                "estimated_cost": pipeline_run.estimated_cost,
            }

        except Exception as exc:
            error_message = str(exc)
            logger.error("[Pipeline %s] Failed: %s", pipeline_run.id if pipeline_run else "?", exc, exc_info=True)
            try:
                db.rollback()
            except Exception:
                pass
            step_log = update_step(step_log, "finalization", status="failed", message=error_message[:1000])
            if pipeline_run:
                pipeline_run.status = "failed"
                pipeline_run.error_message = error_message[:1000]
                pipeline_run.completed_at = datetime.now(timezone.utc).replace(tzinfo=None)
                persist_run(db, pipeline_run, step_log)
            notifier.send_error_alert(f"Pipeline failed for app {app_id}: {error_message[:300]}", f"App {app_id}", db)
            raise self.retry(exc=exc, countdown=60 * 10)
        finally:
            _release_pipeline_lock(redis_client, lock_key, lock_token)
