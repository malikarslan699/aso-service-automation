import json
from types import SimpleNamespace
from datetime import datetime, timezone

import pytest
import pytest_asyncio
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from app.models.base import Base
from app.models.app import App
from app.models.suggestion import Suggestion
from app.services import data_fetcher
from app.services import execution
from app.services.publish_guard import recent_live_publish_block_reason, should_skip_candidate
from app.services.suggestion_tracking import build_status_log, hydrate_status_log, serialize_status_log
from app.workers.tasks.daily_pipeline import _supersede_old_pending_suggestions
from app.workers.tasks.publish_suggestion import publish_suggestion_task


@pytest_asyncio.fixture
async def test_app(client, auth_headers):
    resp = await client.post(
        "/api/v1/apps",
        json={"name": "Visibility App", "package_name": "com.visibility.app", "store": "google_play"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()


@pytest.mark.asyncio
async def test_approve_sets_queue_publish_state(client, auth_headers, test_app, monkeypatch):
    from app.workers.celery_app import celery_app
    from tests.conftest import test_session

    async with test_session() as session:
        suggestion = Suggestion(
            app_id=test_app["id"],
            suggestion_type="listing",
            field_name="title",
            old_value="Old Title",
            new_value="New Title",
            reasoning="Better keyword coverage",
            risk_score=0,
            status="pending",
            safety_result="{}",
            status_log=serialize_status_log(build_status_log()),
        )
        session.add(suggestion)
        await session.commit()
        await session.refresh(suggestion)
        suggestion_id = suggestion.id

    monkeypatch.setattr(celery_app, "send_task", lambda *args, **kwargs: SimpleNamespace(id="publish-1"))

    resp = await client.post(
        f"/api/v1/apps/{test_app['id']}/suggestions/{suggestion_id}/approve",
        headers=auth_headers,
    )
    assert resp.status_code == 200
    assert resp.json()["publish_status"] in {"queued_bundle", "waiting_safe_window"}

    list_resp = await client.get(
        f"/api/v1/apps/{test_app['id']}/suggestions",
        headers=auth_headers,
    )
    assert list_resp.status_code == 200
    item = next(row for row in list_resp.json() if row["id"] == suggestion_id)
    assert item["review_status"] == "approved"
    assert item["publish_status"] in {"queued_bundle", "waiting_safe_window"}
    assert any(step["key"] == "reviewed" and step["status"] == "completed" for step in item["status_log"])
    assert any(step["key"] == "queued_for_publish" and step["status"] == "completed" for step in item["status_log"])


@pytest.mark.asyncio
async def test_reject_marks_publish_blocked(client, auth_headers, test_app):
    from tests.conftest import test_session

    async with test_session() as session:
        suggestion = Suggestion(
            app_id=test_app["id"],
            suggestion_type="listing",
            field_name="short_description",
            old_value="Old",
            new_value="New",
            reasoning="Reasoning",
            risk_score=1,
            status="pending",
            safety_result="{}",
            status_log=serialize_status_log(build_status_log()),
        )
        session.add(suggestion)
        await session.commit()
        await session.refresh(suggestion)
        suggestion_id = suggestion.id

    resp = await client.post(
        f"/api/v1/apps/{test_app['id']}/suggestions/{suggestion_id}/reject",
        headers=auth_headers,
        json={"reason": "Brand mismatch"},
    )
    assert resp.status_code == 200

    list_resp = await client.get(
        f"/api/v1/apps/{test_app['id']}/suggestions",
        headers=auth_headers,
    )
    item = next(row for row in list_resp.json() if row["id"] == suggestion_id)
    assert item["review_status"] == "rejected"
    assert item["publish_status"] == "blocked"
    assert item["publish_message"] == "Rejected in review. Not sent to Google publish flow."


def _build_sync_db(tmp_path):
    db_path = tmp_path / "publish_visibility.sqlite"
    engine = create_engine(f"sqlite:///{db_path}")
    Base.metadata.create_all(engine)
    return engine


def test_execution_publish_dry_run_keeps_item_out_of_live_publish(tmp_path, monkeypatch):
    engine = _build_sync_db(tmp_path)

    monkeypatch.setattr(
        "app.services.data_fetcher.fetch_listing",
        lambda package_name: {"title": "Before", "short_description": "Before short", "long_description": "Before long"},
    )
    monkeypatch.setattr(
        "app.services.data_fetcher.publish_listing",
        lambda **kwargs: {"success": True, "dry_run": True, "message": "Dry run - simulated"},
    )

    with Session(engine) as session:
        app = App(name="Dry Run App", package_name="com.dry.run")
        suggestion = Suggestion(
            app_id=1,
            suggestion_type="listing",
            field_name="title",
            old_value="Old",
            new_value="New",
            status="approved",
            status_log=serialize_status_log(build_status_log()),
        )
        session.add(app)
        session.flush()
        suggestion.app_id = app.id
        session.add(suggestion)
        session.commit()
        session.refresh(suggestion)
        session.refresh(app)

        result = execution.publish(
            suggestion=suggestion,
            app=app,
            credential_json=None,
            dry_run=True,
            db=session,
        )
        session.refresh(suggestion)

    assert result["success"] is True
    assert suggestion.status == "approved"
    assert suggestion.publish_status == "dry_run_only"
    assert suggestion.published_live is False
    assert suggestion.is_dry_run_result is True
    assert suggestion.published_at is None


def test_execution_publish_blocks_missing_live_credential(tmp_path):
    engine = _build_sync_db(tmp_path)

    with Session(engine) as session:
        app = App(name="Live App", package_name="com.live.app")
        suggestion = Suggestion(
            app_id=1,
            suggestion_type="listing",
            field_name="title",
            old_value="Old",
            new_value="New",
            status="approved",
            status_log=serialize_status_log(build_status_log()),
        )
        session.add(app)
        session.flush()
        suggestion.app_id = app.id
        session.add(suggestion)
        session.commit()
        session.refresh(suggestion)

        result = execution.publish(
            suggestion=suggestion,
            app=app,
            credential_json=None,
            dry_run=False,
            db=session,
        )
        session.refresh(suggestion)

    assert result["success"] is False
    assert suggestion.publish_status == "blocked"
    assert suggestion.status == "approved"
    assert suggestion.published_live is False
    assert "Missing Google Play credential" in suggestion.publish_message


def test_execution_publish_keeps_blocked_status_from_provider(tmp_path, monkeypatch):
    engine = _build_sync_db(tmp_path)

    monkeypatch.setattr(
        "app.services.data_fetcher.fetch_listing",
        lambda package_name: {"title": "Before", "short_description": "Before short", "long_description": "Before long"},
    )
    monkeypatch.setattr(
        "app.services.data_fetcher.publish_listing",
        lambda **kwargs: {
            "success": False,
            "status": "blocked",
            "error_code": "missing_default_language_title",
            "message": "[missing_default_language_title] This app does not have a title set for the default language.",
        },
    )

    with Session(engine) as session:
        app = App(name="Blocked App", package_name="com.blocked.app")
        suggestion = Suggestion(
            app_id=1,
            suggestion_type="listing",
            field_name="short_description",
            old_value="Old",
            new_value="New short",
            status="approved",
            status_log=serialize_status_log(build_status_log()),
        )
        session.add(app)
        session.flush()
        suggestion.app_id = app.id
        session.add(suggestion)
        session.commit()
        session.refresh(suggestion)

        result = execution.publish(
            suggestion=suggestion,
            app=app,
            credential_json="{}",
            dry_run=False,
            db=session,
        )
        session.refresh(suggestion)

    assert result["success"] is False
    assert suggestion.publish_status == "blocked"
    assert suggestion.publish_message.startswith("[missing_default_language_title]")


def test_reply_to_review_blocks_missing_review_id_without_google_call(monkeypatch):
    monkeypatch.setattr(
        "app.services.data_fetcher._build_androidpublisher_service",
        lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("Google API must not be called")),
    )

    result = data_fetcher.reply_to_review(
        package_name="com.NetSafe.VPN",
        review_id="",
        reply_text="Thanks!",
        credential_json="{}",
        dry_run=False,
    )

    assert result["success"] is False
    assert result["status"] == "blocked"
    assert result["error_code"] == "missing_review_id"
    assert result["message"].startswith("[missing_review_id]")


def test_reply_to_review_uses_real_review_id(monkeypatch):
    captured = {}

    class _Exec:
        def __init__(self, payload=None):
            self.payload = payload or {}

        def execute(self):
            return self.payload

    class _Reviews:
        def reply(self, **kwargs):
            captured.update(kwargs)
            return _Exec({})

    class _Service:
        def reviews(self):
            return _Reviews()

    monkeypatch.setattr("app.services.data_fetcher._build_androidpublisher_service", lambda *args, **kwargs: _Service())

    result = data_fetcher.reply_to_review(
        package_name="com.NetSafe.VPN",
        review_id="gp-review-123",
        reply_text="Thank you for your feedback!",
        credential_json="{}",
        dry_run=False,
    )

    assert result["success"] is True
    assert captured["reviewId"] == "gp-review-123"
    assert captured["packageName"] == "com.NetSafe.VPN"


def test_publish_listing_uses_default_language_and_existing_title(monkeypatch):
    captured = {}

    class _Exec:
        def __init__(self, payload=None):
            self.payload = payload or {}

        def execute(self):
            return self.payload

    class _Listings:
        def update(self, **kwargs):
            captured["update"] = kwargs
            return _Exec({})

    class _Edits:
        def insert(self, **kwargs):
            captured["insert"] = kwargs
            return _Exec({"id": "edit-1"})

        def listings(self):
            return _Listings()

        def commit(self, **kwargs):
            captured["commit"] = kwargs
            return _Exec({})

    class _Service:
        def edits(self):
            return _Edits()

    monkeypatch.setattr("app.services.data_fetcher._build_androidpublisher_service", lambda *args, **kwargs: _Service())
    monkeypatch.setattr("app.services.data_fetcher._resolve_default_language", lambda *args, **kwargs: "en-GB")
    monkeypatch.setattr(
        "app.services.data_fetcher._read_current_listing",
        lambda *args, **kwargs: {"title": "Existing Title", "shortDescription": "Old short", "fullDescription": "Old long"},
    )

    result = data_fetcher.publish_listing(
        package_name="com.NetSafe.VPN",
        credential_json="{}",
        title=None,
        short_description="New short",
        long_description=None,
        dry_run=False,
    )

    assert result["success"] is True
    assert captured["update"]["language"] == "en-GB"
    assert captured["update"]["body"]["title"] == "Existing Title"
    assert captured["update"]["body"]["shortDescription"] == "New short"


def test_publish_listing_blocks_when_default_language_title_missing(monkeypatch):
    class _Exec:
        def __init__(self, payload=None):
            self.payload = payload or {}

        def execute(self):
            return self.payload

    class _Listings:
        def update(self, **kwargs):
            return _Exec({})

    class _Edits:
        def insert(self, **kwargs):
            return _Exec({"id": "edit-2"})

        def listings(self):
            return _Listings()

        def commit(self, **kwargs):
            return _Exec({})

    class _Service:
        def edits(self):
            return _Edits()

    monkeypatch.setattr("app.services.data_fetcher._build_androidpublisher_service", lambda *args, **kwargs: _Service())
    monkeypatch.setattr("app.services.data_fetcher._resolve_default_language", lambda *args, **kwargs: "en-US")
    monkeypatch.setattr(
        "app.services.data_fetcher._read_current_listing",
        lambda *args, **kwargs: {"title": "", "shortDescription": "Old short", "fullDescription": "Old long"},
    )

    result = data_fetcher.publish_listing(
        package_name="com.NetSafe.VPN",
        credential_json="{}",
        title=None,
        short_description="New short",
        long_description=None,
        dry_run=False,
    )

    assert result["success"] is False
    assert result["status"] == "blocked"
    assert result["error_code"] == "missing_default_language_title"


def test_publish_task_marks_limits_as_blocked(tmp_path, monkeypatch):
    engine = _build_sync_db(tmp_path)

    with Session(engine) as session:
        app = App(name="Limit App", package_name="com.limit.app")
        session.add(app)
        session.flush()
        suggestion = Suggestion(
            app_id=app.id,
            suggestion_type="review_reply",
            field_name="reply_text",
            old_value="Old",
            new_value="New",
            status="approved",
            publish_status="queued",
            status_log=serialize_status_log(build_status_log()),
        )
        session.add(suggestion)
        session.commit()
        suggestion_id = suggestion.id
        app_id = app.id

    monkeypatch.setattr(
        "app.config.get_settings",
        lambda: SimpleNamespace(database_url_sync=f"sqlite:///{tmp_path / 'publish_visibility.sqlite'}", dry_run=True),
    )
    monkeypatch.setattr(
        "app.services.execution.can_publish",
        lambda app_id, db, publish_kind="review_reply", now=None: (False, "Daily review-reply publish limit reached (1/1)"),
    )

    result = publish_suggestion_task(suggestion_id=suggestion_id, app_id=app_id)
    assert result["status"] == "blocked"

    with Session(engine) as session:
        suggestion = session.get(Suggestion, suggestion_id)
        status_log = json.loads(suggestion.status_log)
        assert suggestion.publish_status == "blocked"
        assert suggestion.publish_message == "Daily review-reply publish limit reached (1/1)"
        assert any(step["key"] == "publish_result" and step["status"] == "blocked" for step in status_log)


def test_should_skip_candidate_blocks_near_duplicate_listing_copy():
    candidate = {
        "suggestion_type": "listing",
        "field_name": "title",
        "old_value": "NetSafe VPN: Fast & Secure",
        "new_value": "NetSafe VPN: Secure & Fast",
    }
    existing = [
        {
            "field_name": "title",
            "new_value": "NetSafe VPN: Fast & Secure",
            "status": "published",
            "created_at": "2026-03-12T00:00:00",
            "published_at": "2026-03-12T00:00:00",
        }
    ]

    should_skip, reason = should_skip_candidate(candidate, existing)

    assert should_skip is True
    assert "published recently" in reason


def test_recent_live_publish_block_reason_blocks_near_duplicate_live_send(tmp_path):
    engine = _build_sync_db(tmp_path)

    with Session(engine) as session:
        app = App(name="Guard App", package_name="com.guard.app")
        session.add(app)
        session.flush()

        previous = Suggestion(
            app_id=app.id,
            suggestion_type="listing",
            field_name="short_description",
            old_value="Old short",
            new_value="Fast VPN with kill switch and split tunneling",
            status="published",
            published_at=datetime.now(timezone.utc).replace(tzinfo=None),
            published_live=True,
        )
        candidate = Suggestion(
            app_id=app.id,
            suggestion_type="listing",
            field_name="short_description",
            old_value="Old short",
            new_value="Fast VPN with split tunneling and kill switch",
            status="approved",
        )
        session.add_all([previous, candidate])
        session.commit()

        reason = recent_live_publish_block_reason(candidate, session)

    assert reason is not None
    assert "already published on Google" in reason


def test_supersede_old_pending_suggestions_marks_stale_items(tmp_path):
    engine = _build_sync_db(tmp_path)

    with Session(engine) as session:
        app = App(name="Supersede App", package_name="com.supersede.app")
        session.add(app)
        session.flush()

        stale = Suggestion(
            app_id=app.id,
            suggestion_type="listing",
            field_name="title",
            old_value="Old",
            new_value="Pending old title",
            status="pending",
            pipeline_run_id=12,
            status_log=serialize_status_log(build_status_log()),
        )
        current = Suggestion(
            app_id=app.id,
            suggestion_type="listing",
            field_name="title",
            old_value="Old",
            new_value="Pending current title",
            status="pending",
            pipeline_run_id=14,
            status_log=serialize_status_log(build_status_log()),
        )
        session.add_all([stale, current])
        session.commit()

        changed = _supersede_old_pending_suggestions(app_id=app.id, current_pipeline_run_id=14, db=session)
        session.refresh(stale)
        session.refresh(current)

    assert changed == 1
    assert stale.status == "superseded"
    assert stale.publish_status == "superseded"
    assert "Superseded by newer pipeline run #14" in (stale.publish_message or "")
    assert current.status == "pending"


def test_hydrate_pending_timeline_does_not_set_fake_started_timestamp():
    suggestion = Suggestion(
        app_id=1,
        suggestion_type="listing",
        field_name="title",
        old_value="Old",
        new_value="New",
        status="pending",
        status_log=serialize_status_log(build_status_log()),
    )

    timeline = hydrate_status_log(suggestion)
    reviewed_stage = next(item for item in timeline if item["key"] == "reviewed")

    assert reviewed_stage["status"] == "pending"
    assert reviewed_stage["started_at"] is None
    assert reviewed_stage["completed_at"] is None


@pytest.mark.asyncio
async def test_listing_merge_supersedes_older_approved_item(client, auth_headers, test_app, monkeypatch):
    from app.workers.celery_app import celery_app
    from tests.conftest import test_session

    monkeypatch.setattr(celery_app, "send_task", lambda *args, **kwargs: SimpleNamespace(id="bundle-1"))

    async with test_session() as session:
        first = Suggestion(
            app_id=test_app["id"],
            suggestion_type="listing",
            field_name="title",
            old_value="Old title",
            new_value="NetSafe VPN: Fast & Secure",
            reasoning="first",
            risk_score=0,
            status="pending",
            safety_result="{}",
            status_log=serialize_status_log(build_status_log()),
        )
        second = Suggestion(
            app_id=test_app["id"],
            suggestion_type="listing",
            field_name="title",
            old_value="Old title",
            new_value="NetSafe VPN: Secure & Fast",
            reasoning="second",
            risk_score=0,
            status="pending",
            safety_result="{}",
            status_log=serialize_status_log(build_status_log()),
        )
        session.add_all([first, second])
        await session.commit()
        await session.refresh(first)
        await session.refresh(second)

    r1 = await client.post(
        f"/api/v1/apps/{test_app['id']}/suggestions/{first.id}/approve",
        headers=auth_headers,
    )
    assert r1.status_code == 200

    r2 = await client.post(
        f"/api/v1/apps/{test_app['id']}/suggestions/{second.id}/approve",
        headers=auth_headers,
    )
    assert r2.status_code == 200

    list_resp = await client.get(f"/api/v1/apps/{test_app['id']}/suggestions", headers=auth_headers)
    assert list_resp.status_code == 200
    items = {row["id"]: row for row in list_resp.json()}
    assert items[first.id]["review_status"] == "superseded"
    assert items[first.id]["publish_status"] == "superseded"
    assert items[second.id]["publish_status"] in {"queued_bundle", "waiting_safe_window"}

    jobs_resp = await client.get(f"/api/v1/apps/{test_app['id']}/publish-jobs", headers=auth_headers)
    assert jobs_resp.status_code == 200
    assert jobs_resp.json()["items"], "listing bundle job should exist"


@pytest.mark.asyncio
async def test_retry_blocked_listing_suggestion_requeues_bundle(client, auth_headers, test_app, monkeypatch):
    from app.workers.celery_app import celery_app
    from tests.conftest import test_session

    monkeypatch.setattr(celery_app, "send_task", lambda *args, **kwargs: SimpleNamespace(id="bundle-retry"))

    async with test_session() as session:
        suggestion = Suggestion(
            app_id=test_app["id"],
            suggestion_type="listing",
            field_name="short_description",
            old_value="Old short",
            new_value="Fast VPN with encryption and one tap connect",
            reasoning="retry me",
            risk_score=0,
            status="approved",
            publish_status="blocked",
            publish_message="Blocked by test",
            publish_block_reason="Blocked by test",
            status_log=serialize_status_log(build_status_log()),
        )
        session.add(suggestion)
        await session.commit()
        await session.refresh(suggestion)
        suggestion_id = suggestion.id

    retry_resp = await client.post(
        f"/api/v1/apps/{test_app['id']}/suggestions/{suggestion_id}/retry-publish",
        headers=auth_headers,
        json={"reason": "Retry now"},
    )
    assert retry_resp.status_code == 200
    body = retry_resp.json()
    assert body["publish_status"] in {"queued_bundle", "waiting_safe_window"}
    assert body["publish_job_id"] is not None
