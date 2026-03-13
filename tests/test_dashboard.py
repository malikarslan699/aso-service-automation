import json

import pytest

from app.models.pipeline_run import PipelineRun


@pytest.mark.asyncio
async def test_dashboard_returns_step_log_and_provider_analytics(client, auth_headers):
    create_resp = await client.post(
        "/api/v1/apps",
        json={"name": "Dash App", "package_name": "com.dashboard.app"},
        headers=auth_headers,
    )
    assert create_resp.status_code == 201
    app_id = create_resp.json()["id"]

    from tests.conftest import test_session

    async with test_session() as session:
        session.add(
            PipelineRun(
                app_id=app_id,
                status="completed_with_warnings",
                trigger="manual",
                steps_completed=4,
                total_steps=9,
                keywords_discovered=10,
                approvals_created=0,
                provider_name="anthropic",
                provider_status="billing_blocked",
                provider_error_class="billing_blocked",
                estimated_cost=0.014,
                input_tokens=120,
                output_tokens=34,
                value_summary="Keywords discovered: 10. Suggestions created: 0.",
                step_log=json.dumps(
                    [
                        {"key": "queue_accepted", "label": "Queue Accepted", "status": "completed", "message": "Queued"},
                        {"key": "ai_generation", "label": "Ai Generation", "status": "failed", "message": "credits low"},
                    ]
                ),
            )
        )
        await session.commit()

    resp = await client.get("/api/v1/dashboard", headers=auth_headers)
    assert resp.status_code == 200
    app_data = next(item for item in resp.json()["apps"] if item["app_id"] == app_id)
    assert app_data["last_pipeline"]["overall_status"] == "completed_with_warnings"
    assert app_data["last_pipeline"]["provider_name"] == "anthropic"
    assert len(app_data["last_pipeline"]["step_log"]) >= 2
