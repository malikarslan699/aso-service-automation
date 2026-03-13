"""API tests for suggestions endpoints: list, approve, reject."""
from datetime import datetime, timedelta, timezone
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy.ext.asyncio import AsyncSession
from app.main import app
from app.database import get_db
from app.models.app import App
from app.models.global_config import GlobalConfig
from app.models.pipeline_run import PipelineRun
from app.models.suggestion import Suggestion
from app.workers.tasks.daily_pipeline import _dedupe_suggestions


async def _get_test_db():
    """Get a test DB session (relies on conftest fixture override)."""
    from tests.conftest import test_session
    async with test_session() as session:
        yield session


@pytest_asyncio.fixture
async def test_app(auth_headers, client):
    """Create a test app and return it."""
    resp = await client.post(
        "/api/v1/apps",
        json={"name": "Test App", "package_name": "com.test.app", "store": "google_play"},
        headers=auth_headers,
    )
    assert resp.status_code == 201
    return resp.json()


@pytest_asyncio.fixture
async def test_suggestion(test_app, auth_headers):
    """Create a suggestion directly in DB for testing."""
    from tests.conftest import test_session

    async with test_session() as session:
        s = Suggestion(
            app_id=test_app["id"],
            suggestion_type="listing",
            field_name="title",
            old_value="Old Title",
            new_value="New Title",
            reasoning="Better keyword coverage",
            risk_score=0,
            status="pending",
            safety_result="{}",
        )
        session.add(s)
        await session.commit()
        await session.refresh(s)
        return {"id": s.id, "app_id": s.app_id}


class TestListSuggestions:
    async def test_list_suggestions_empty(self, client, auth_headers, test_app):
        resp = await client.get(
            f"/api/v1/apps/{test_app['id']}/suggestions",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        assert resp.json() == []

    async def test_list_suggestions_with_data(self, client, auth_headers, test_suggestion):
        resp = await client.get(
            f"/api/v1/apps/{test_suggestion['app_id']}/suggestions",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 1
        assert data[0]["field_name"] == "title"
        assert data[0]["status"] == "pending"

    async def test_list_suggestions_filter_by_status(self, client, auth_headers, test_suggestion):
        resp = await client.get(
            f"/api/v1/apps/{test_suggestion['app_id']}/suggestions?status=pending",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert all(s["status"] == "pending" for s in data)

    async def test_list_suggestions_requires_auth(self, client, test_suggestion):
        resp = await client.get(
            f"/api/v1/apps/{test_suggestion['app_id']}/suggestions"
        )
        assert resp.status_code == 403

    async def test_list_suggestions_diff_fields_present(self, client, auth_headers, test_suggestion):
        resp = await client.get(
            f"/api/v1/apps/{test_suggestion['app_id']}/suggestions",
            headers=auth_headers,
        )
        data = resp.json()
        assert len(data) >= 1
        s = data[0]
        assert "old_value" in s
        assert "new_value" in s
        assert "risk_score" in s
        assert "reasoning" in s

    async def test_list_suggestions_exposes_superseded_review_status(self, client, auth_headers, test_app):
        from tests.conftest import test_session

        async with test_session() as session:
            suggestion = Suggestion(
                app_id=test_app["id"],
                suggestion_type="listing",
                field_name="title",
                old_value="Old",
                new_value="New",
                status="superseded",
                publish_status="superseded",
                publish_message="Superseded by newer pipeline run",
                safety_result="{}",
            )
            session.add(suggestion)
            await session.commit()

        resp = await client.get(
            f"/api/v1/apps/{test_app['id']}/suggestions",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        item = next(x for x in resp.json() if x["status"] == "superseded")
        assert item["review_status"] == "superseded"
        assert item["publish_status"] == "superseded"


class TestApproveSuggestion:
    async def test_approve_suggestion(self, client, auth_headers, test_suggestion):
        resp = await client.post(
            f"/api/v1/apps/{test_suggestion['app_id']}/suggestions/{test_suggestion['id']}/approve",
            headers=auth_headers,
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "approved"

    async def test_approve_suggestion_status_changes(self, client, auth_headers, test_suggestion):
        # Approve
        await client.post(
            f"/api/v1/apps/{test_suggestion['app_id']}/suggestions/{test_suggestion['id']}/approve",
            headers=auth_headers,
        )
        # Check list
        resp = await client.get(
            f"/api/v1/apps/{test_suggestion['app_id']}/suggestions",
            headers=auth_headers,
        )
        data = resp.json()
        assert any(s["status"] == "approved" for s in data)

    async def test_approve_requires_admin(self, client, test_suggestion):
        resp = await client.post(
            f"/api/v1/apps/{test_suggestion['app_id']}/suggestions/{test_suggestion['id']}/approve"
        )
        assert resp.status_code == 403

    async def test_approve_nonexistent_suggestion(self, client, auth_headers, test_app):
        resp = await client.post(
            f"/api/v1/apps/{test_app['id']}/suggestions/9999/approve",
            headers=auth_headers,
        )
        assert resp.status_code == 404


class TestRejectSuggestion:
    async def test_reject_suggestion(self, client, auth_headers, test_suggestion):
        resp = await client.post(
            f"/api/v1/apps/{test_suggestion['app_id']}/suggestions/{test_suggestion['id']}/reject",
            headers=auth_headers,
            json={"reason": "Not aligned with brand voice"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "rejected"

    async def test_reject_suggestion_status_changes(self, client, auth_headers, test_suggestion):
        await client.post(
            f"/api/v1/apps/{test_suggestion['app_id']}/suggestions/{test_suggestion['id']}/reject",
            headers=auth_headers,
            json={"reason": "Test rejection"},
        )
        resp = await client.get(
            f"/api/v1/apps/{test_suggestion['app_id']}/suggestions",
            headers=auth_headers,
        )
        data = resp.json()
        assert any(s["status"] == "rejected" for s in data)

    async def test_reject_requires_reason(self, client, auth_headers, test_suggestion):
        resp = await client.post(
            f"/api/v1/apps/{test_suggestion['app_id']}/suggestions/{test_suggestion['id']}/reject",
            headers=auth_headers,
            json={},
        )
        assert resp.status_code == 422  # Validation error — reason is required

    async def test_reject_requires_admin(self, client, test_suggestion):
        resp = await client.post(
            f"/api/v1/apps/{test_suggestion['app_id']}/suggestions/{test_suggestion['id']}/reject",
            json={"reason": "test"},
        )
        assert resp.status_code == 403


class DummyTask:
    def __init__(self, task_id: str = "task-123"):
        self.id = task_id


class TestTriggerPipeline:
    async def test_trigger_pipeline_admin_queued(self, client, auth_headers, test_app, monkeypatch):
        from app.workers.celery_app import celery_app
        from tests.conftest import test_session

        monkeypatch.setattr(celery_app, "send_task", lambda *args, **kwargs: DummyTask())

        resp = await client.post(
            f"/api/v1/apps/{test_app['id']}/pipeline/trigger",
            headers=auth_headers,
            json={"dry_run": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert data["workflow_mode"] == "manual_approval"
        assert data["pipeline_run_id"] is not None

        async with test_session() as session:
            run = await session.get(PipelineRun, data["pipeline_run_id"])
            assert run is not None
            assert run.status == "queued"
            assert run.trigger == "manual"

    async def test_trigger_pipeline_assigned_sub_admin_queued(self, client, auth_headers, monkeypatch):
        from app.workers.celery_app import celery_app

        create_app = await client.post(
            "/api/v1/apps",
            json={"name": "Assigned App", "package_name": "com.assigned.trigger"},
            headers=auth_headers,
        )
        app_id = create_app.json()["id"]

        create_sub = await client.post(
            "/api/v1/team/users",
            json={"username": "runsub", "password": "pass1234", "email": "", "app_ids": [app_id]},
            headers=auth_headers,
        )
        assert create_sub.status_code == 201

        login_resp = await client.post(
            "/auth/login",
            json={"username": "runsub", "password": "pass1234"},
        )
        sub_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

        monkeypatch.setattr(celery_app, "send_task", lambda *args, **kwargs: DummyTask("task-456"))

        resp = await client.post(
            f"/api/v1/apps/{app_id}/pipeline/trigger",
            headers=sub_headers,
            json={"dry_run": True},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "queued"

    async def test_trigger_pipeline_unassigned_sub_admin_denied(self, client, auth_headers, monkeypatch):
        from app.workers.celery_app import celery_app

        first_app = await client.post(
            "/api/v1/apps",
            json={"name": "Visible App", "package_name": "com.visible.trigger"},
            headers=auth_headers,
        )
        second_app = await client.post(
            "/api/v1/apps",
            json={"name": "Hidden App", "package_name": "com.hidden.trigger"},
            headers=auth_headers,
        )

        create_sub = await client.post(
            "/api/v1/team/users",
            json={"username": "limitedsub", "password": "pass1234", "email": "", "app_ids": [first_app.json()["id"]]},
            headers=auth_headers,
        )
        assert create_sub.status_code == 201

        login_resp = await client.post(
            "/auth/login",
            json={"username": "limitedsub", "password": "pass1234"},
        )
        sub_headers = {"Authorization": f"Bearer {login_resp.json()['access_token']}"}

        monkeypatch.setattr(celery_app, "send_task", lambda *args, **kwargs: DummyTask("task-789"))

        resp = await client.post(
            f"/api/v1/apps/{second_app.json()['id']}/pipeline/trigger",
            headers=sub_headers,
            json={"dry_run": True},
        )
        assert resp.status_code == 403

    async def test_trigger_pipeline_blocked_when_running(self, client, auth_headers, test_app, monkeypatch):
        from tests.conftest import test_session
        from app.workers.celery_app import celery_app

        monkeypatch.setattr(celery_app, "send_task", lambda *args, **kwargs: DummyTask())

        async with test_session() as session:
            session.add(
                PipelineRun(
                    app_id=test_app["id"],
                    status="queued",
                    trigger="manual",
                    steps_completed=1,
                    total_steps=9,
                    started_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
            await session.commit()

        resp = await client.post(
            f"/api/v1/apps/{test_app['id']}/pipeline/trigger",
            headers=auth_headers,
            json={"dry_run": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "blocked_running"

    async def test_trigger_pipeline_blocked_by_cooldown(self, client, auth_headers, test_app, monkeypatch):
        from tests.conftest import test_session
        from app.workers.celery_app import celery_app

        monkeypatch.setattr(celery_app, "send_task", lambda *args, **kwargs: DummyTask())

        async with test_session() as session:
            session.add(
                PipelineRun(
                    app_id=test_app["id"],
                    status="completed",
                    trigger="manual",
                    steps_completed=9,
                    total_steps=9,
                    started_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5),
                    completed_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )
            )
            await session.commit()

        resp = await client.post(
            f"/api/v1/apps/{test_app['id']}/pipeline/trigger",
            headers=auth_headers,
            json={"dry_run": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "blocked_cooldown"
        assert data["cooldown_minutes"] == 15

    async def test_trigger_pipeline_respects_auto_rules_config(self, client, auth_headers, test_app, monkeypatch):
        from tests.conftest import test_session
        from app.workers.celery_app import celery_app

        monkeypatch.setattr(celery_app, "send_task", lambda *args, **kwargs: DummyTask())

        async with test_session() as session:
            session.add(GlobalConfig(key="manual_approval_required", value="false", description="test"))
            session.add(GlobalConfig(key="manual_trigger_cooldown_minutes", value="0", description="test"))
            await session.commit()

        resp = await client.post(
            f"/api/v1/apps/{test_app['id']}/pipeline/trigger",
            headers=auth_headers,
            json={"dry_run": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"
        assert data["workflow_mode"] == "auto_rules"

    async def test_trigger_pipeline_expires_stale_queued_run(self, client, auth_headers, test_app, monkeypatch):
        from tests.conftest import test_session
        from app.workers.celery_app import celery_app

        monkeypatch.setattr(celery_app, "send_task", lambda *args, **kwargs: DummyTask("task-stale"))

        async with test_session() as session:
            stale_run = PipelineRun(
                app_id=test_app["id"],
                status="queued",
                trigger="manual",
                steps_completed=0,
                total_steps=9,
                started_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(minutes=5),
            )
            session.add(stale_run)
            await session.commit()
            stale_run_id = stale_run.id

        resp = await client.post(
            f"/api/v1/apps/{test_app['id']}/pipeline/trigger",
            headers=auth_headers,
            json={"dry_run": True},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "queued"

        async with test_session() as session:
            old_run = await session.get(PipelineRun, stale_run_id)
            new_run = await session.get(PipelineRun, data["pipeline_run_id"])
            assert old_run.status == "failed"
            assert "Queue timeout" in (old_run.error_message or "")
            assert new_run.status == "queued"


class TestManualRunDedupe:
    def test_dedupe_skips_existing_pending_approved_and_published(self):
        validated = [
            {"field_name": "title", "old_value": "Old", "new_value": "Fresh Title"},
            {"field_name": "short_description", "old_value": "Old short", "new_value": "Brand new copy"},
            {"field_name": "title", "old_value": "Old", "new_value": "Fresh Title"},
        ]
        existing = [
            {"field_name": "title", "new_value": "Fresh Title", "status": "published"},
            {"field_name": "short_description", "new_value": "Queued already", "status": "pending"},
        ]

        deduped, skipped = _dedupe_suggestions(validated, existing)

        assert skipped == 2
        assert len(deduped) == 1
        assert deduped[0]["field_name"] == "short_description"

    def test_dedupe_skips_no_op_values(self):
        validated = [
            {"field_name": "title", "old_value": "Same Title", "new_value": "Same Title"},
            {"field_name": "title", "old_value": "Old", "new_value": "New Title"},
        ]

        deduped, skipped = _dedupe_suggestions(validated, [])

        assert skipped == 1
        assert len(deduped) == 1
        assert deduped[0]["new_value"] == "New Title"

    def test_dedupe_ignores_pending_from_older_run(self):
        validated = [
            {
                "suggestion_type": "listing",
                "field_name": "title",
                "old_value": "NetSafe VPN: Fast & Secure VPN",
                "new_value": "NetSafe VPN: Encryption & Fast",
            }
        ]
        existing = [
            {
                "field_name": "title",
                "new_value": "NetSafe VPN: Encryption & Fast",
                "status": "pending",
                "pipeline_run_id": 10,
            }
        ]

        deduped, skipped = _dedupe_suggestions(validated, existing, current_pipeline_run_id=99)

        assert skipped == 0
        assert len(deduped) == 1
