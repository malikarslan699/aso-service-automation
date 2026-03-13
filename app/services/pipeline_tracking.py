import json
from datetime import datetime, timezone


DEFAULT_PIPELINE_STEPS = [
    "queue_accepted",
    "run_started",
    "app_data_fetch",
    "keyword_discovery",
    "duplicate_filtering",
    "ai_generation",
    "approval_creation",
    "publish_eligibility_check",
    "finalization",
]


def build_step_log() -> list[dict]:
    return [
        {
            "key": step,
            "label": step.replace("_", " ").title(),
            "status": "pending",
            "started_at": None,
            "completed_at": None,
            "message": "",
            "provider": None,
            "estimated_cost": 0.0,
            "input_tokens": 0,
            "output_tokens": 0,
        }
        for step in DEFAULT_PIPELINE_STEPS
    ]


def parse_step_log(raw_value: str | None) -> list[dict]:
    if not raw_value:
        return build_step_log()
    try:
        data = json.loads(raw_value)
        if isinstance(data, list):
            return data
    except Exception:
        pass
    return build_step_log()


def serialize_step_log(steps: list[dict]) -> str:
    return json.dumps(steps)


def update_step(
    steps: list[dict],
    key: str,
    *,
    status: str,
    message: str | None = None,
    provider: str | None = None,
    estimated_cost: float | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
) -> list[dict]:
    now = datetime.now(timezone.utc).replace(tzinfo=None).isoformat()
    for step in steps:
        if step.get("key") != key:
            continue
        if status == "running" and not step.get("started_at"):
            step["started_at"] = now
        if status in {"completed", "failed", "skipped"}:
            if not step.get("started_at"):
                step["started_at"] = now
            step["completed_at"] = now
        step["status"] = status
        if message is not None:
            step["message"] = message
        if provider is not None:
            step["provider"] = provider
        if estimated_cost is not None:
            step["estimated_cost"] = round(float(estimated_cost), 6)
        if input_tokens is not None:
            step["input_tokens"] = int(input_tokens)
        if output_tokens is not None:
            step["output_tokens"] = int(output_tokens)
        break
    return steps


def compute_overall_status(step_log: list[dict], current_status: str, error_message: str | None = None) -> str:
    if current_status in {"queued", "running", "blocked"}:
        return current_status
    if any(step.get("status") == "failed" for step in step_log):
        if current_status == "failed":
            return "failed"
        return "completed_with_warnings"
    if error_message:
        return "completed_with_warnings"
    return current_status


def current_step_label(step_log: list[dict], fallback: str | None = None) -> str | None:
    running = next((step for step in step_log if step.get("status") == "running"), None)
    if running:
        return running.get("label")

    failed = next((step for step in step_log if step.get("status") == "failed"), None)
    if failed:
        return failed.get("message") or failed.get("label")

    completed = [step for step in step_log if step.get("status") == "completed"]
    if completed:
        return completed[-1].get("label")

    return fallback
