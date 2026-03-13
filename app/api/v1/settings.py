import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from pydantic import BaseModel
import httpx
from app.database import get_db
from app.dependencies import get_current_user, require_any_role, require_role, ensure_app_access
from app.models.user import User
from app.models.global_config import GlobalConfig
from app.models.app import App
from app.models.app_credential import AppCredential
from app.schemas.settings import GlobalConfigOut, GlobalConfigUpdate
from app.utils.encryption import encrypt_value, decrypt_value, mask_value
from app.config import get_settings
from app.services.data_fetcher import verify_google_play_connection, resolve_google_discovery_url
from app.services.ai_provider import check_anthropic_inference, check_openai_inference

router = APIRouter()

SENSITIVE_KEYS = {
    "anthropic_api_key",
    "openai_api_key",
    "telegram_bot_token",
    "serpapi_key",
    "google_service_account_json",
}


class IntegrationCheckRequest(BaseModel):
    provider: str = "all"  # all, anthropic, telegram, serpapi, google_play
    app_id: Optional[int] = None


def _default_configs() -> list[dict]:
    settings = get_settings()
    return [
        {"key": "anthropic_api_key", "value": "", "description": "Claude API key for AI suggestions and reasoning"},
        {"key": "openai_api_key", "value": "", "description": "Optional GPT fallback key used only when Claude inference fails"},
        {"key": "telegram_bot_token", "value": "", "description": "Telegram bot token for alerts and confirmations"},
        {"key": "telegram_chat_id", "value": "", "description": "Telegram chat ID that receives notifications"},
        {"key": "serpapi_key", "value": "", "description": "Optional SerpAPI key for external search signals"},
        {"key": "google_service_account_json", "value": "", "description": "Optional global Google Play service account JSON fallback"},
        {"key": "google_play_package_name", "value": settings.google_play_package_name, "description": "Default package name used for Google Play checks"},
        {"key": "google_api_discovery_url", "value": "androidpublisher.googleapis.com", "description": "Optional Google discovery host or full URL override"},
        {"key": "dry_run", "value": str(settings.dry_run).lower(), "description": "Demo mode switch. True simulates actions, false allows live publish"},
        {"key": "max_publish_per_day", "value": str(settings.max_publish_per_day), "description": "Safety limit for how many changes can publish in one day"},
        {"key": "max_publish_per_week", "value": str(settings.max_publish_per_week), "description": "Safety limit for how many changes can publish in one week"},
        {"key": "listing_publish_max_per_day", "value": str(settings.max_publish_per_day), "description": "Listing bundle live-send cap per day"},
        {"key": "listing_publish_max_per_week", "value": str(settings.max_publish_per_week), "description": "Listing bundle live-send cap per week"},
        {"key": "review_reply_max_per_day", "value": "25", "description": "Review reply publish cap per day (separate from listing bundles)"},
        {"key": "review_reply_max_per_week", "value": "120", "description": "Review reply publish cap per week (separate from listing bundles)"},
        {"key": "listing_publish_min_gap_minutes", "value": "60", "description": "Minimum enforced gap between listing bundle publishes"},
        {"key": "listing_publish_jitter_min_seconds", "value": "90", "description": "Minimum random jitter added before listing dispatch"},
        {"key": "listing_publish_jitter_max_seconds", "value": "480", "description": "Maximum random jitter added before listing dispatch"},
        {"key": "listing_publish_window_start_hour_utc", "value": "9", "description": "Safe window start hour (UTC) for listing dispatch"},
        {"key": "listing_publish_window_end_hour_utc", "value": "22", "description": "Safe window end hour (UTC) for listing dispatch"},
        {"key": "listing_recent_change_cooldown_hours", "value": "12", "description": "Block near-identical listing churn inside this cooldown (hours)"},
        {"key": "listing_churn_max_per_24h", "value": "2", "description": "Maximum listing bundle executions allowed in the last 24 hours"},
        {"key": "auto_approve_threshold", "value": "0", "description": "Maximum risk score allowed for auto-approval when manual approval is off"},
        {"key": "manual_approval_required", "value": "true", "description": "If true, every suggestion waits for human approval first"},
        {"key": "publish_after_approval", "value": "true", "description": "If true, approved suggestions are queued for publish automatically"},
        {"key": "manual_trigger_cooldown_minutes", "value": "15", "description": "Minimum wait time between manual Run now actions for the same project"},
    ]


def _decode_value(key: str, raw_value: str) -> str:
    if not raw_value:
        return ""
    if key in SENSITIVE_KEYS:
        # Backward compatibility: if an old value is plain text, return it.
        try:
            return decrypt_value(raw_value)
        except Exception:
            return raw_value
    return raw_value


def _encode_value(key: str, plain_value: str) -> str:
    return encrypt_value(plain_value) if key in SENSITIVE_KEYS else plain_value


def _integration_key(provider: str, app_id: Optional[int]) -> str:
    if provider == "google_play" and app_id is not None:
        return f"integration_check_google_play_app_{app_id}"
    return f"integration_check_{provider}"


def _parse_last_check(raw_value: str) -> Optional[dict]:
    if not raw_value:
        return None
    try:
        data = json.loads(raw_value)
        if isinstance(data, dict):
            return data
    except Exception:
        pass
    return None


async def _ensure_defaults(db: AsyncSession) -> None:
    result = await db.execute(select(GlobalConfig.key))
    existing = set(result.scalars().all())
    to_create = []
    for item in _default_configs():
        if item["key"] not in existing:
            to_create.append(
                GlobalConfig(
                    key=item["key"],
                    value=_encode_value(item["key"], item["value"]),
                    description=item["description"],
                )
            )
    if to_create:
        db.add_all(to_create)
        await db.commit()


async def _load_configs(db: AsyncSession) -> dict[str, GlobalConfig]:
    result = await db.execute(select(GlobalConfig))
    rows = result.scalars().all()
    return {row.key: row for row in rows}


def _plain_config_values(config_map: dict[str, GlobalConfig]) -> dict[str, str]:
    out: dict[str, str] = {}
    for key, row in config_map.items():
        out[key] = _decode_value(key, row.value)
    return out


async def _set_last_check(db: AsyncSession, provider: str, app_id: Optional[int], payload: dict) -> None:
    key = _integration_key(provider, app_id)
    stored_payload = {
        **payload,
        "checked_at": datetime.now(timezone.utc).isoformat(),
    }

    result = await db.execute(select(GlobalConfig).where(GlobalConfig.key == key))
    row = result.scalar_one_or_none()
    if row:
        row.value = json.dumps(stored_payload)
        row.description = "Last integration connectivity check"
    else:
        db.add(
            GlobalConfig(
                key=key,
                value=json.dumps(stored_payload),
                description="Last integration connectivity check",
            )
        )


async def _check_anthropic(api_key: str) -> dict:
    return await check_anthropic_inference(api_key)


async def _check_openai(api_key: str) -> dict:
    return await check_openai_inference(api_key)


async def _check_telegram(config_values: dict[str, str]) -> tuple[bool, str]:
    token = config_values.get("telegram_bot_token", "")
    chat_id = config_values.get("telegram_chat_id", "")
    if not token:
        return False, "telegram_bot_token not configured"
    if not chat_id:
        return False, "telegram_chat_id not configured"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            me_resp = await client.get(f"https://api.telegram.org/bot{token}/getMe")
            if me_resp.status_code >= 300 or not me_resp.json().get("ok"):
                return False, f"getMe failed (HTTP {me_resp.status_code})"

            chat_resp = await client.get(
                f"https://api.telegram.org/bot{token}/getChat",
                params={"chat_id": chat_id},
            )
            if chat_resp.status_code >= 300 or not chat_resp.json().get("ok"):
                return False, f"getChat failed (HTTP {chat_resp.status_code})"

        return True, "Connected"
    except Exception as exc:
        return False, str(exc)


async def _check_serpapi(config_values: dict[str, str]) -> tuple[bool, str]:
    api_key = config_values.get("serpapi_key", "")
    if not api_key:
        return False, "serpapi_key not configured"

    try:
        async with httpx.AsyncClient(timeout=15) as client:
            response = await client.get(
                "https://serpapi.com/account.json",
                params={"api_key": api_key},
            )
        if response.status_code < 300:
            return True, "Connected"
        return False, f"HTTP {response.status_code}"
    except Exception as exc:
        return False, str(exc)


async def _check_google_play(db: AsyncSession, config_values: dict[str, str], app_id: Optional[int]) -> tuple[bool, str]:
    package_name = config_values.get("google_play_package_name", "")
    credential_json = config_values.get("google_service_account_json", "")

    if app_id is not None:
        app_result = await db.execute(select(App).where(App.id == app_id))
        app = app_result.scalar_one_or_none()
        if app is None:
            return False, f"App not found (id={app_id})"
        package_name = app.package_name

        cred_result = await db.execute(
            select(AppCredential).where(
                AppCredential.app_id == app_id,
                AppCredential.credential_type == "service_account_json",
            )
        )
        app_cred = cred_result.scalar_one_or_none()
        if app_cred is not None:
            try:
                credential_json = decrypt_value(app_cred.value)
            except Exception:
                return False, "App credential exists but decryption failed"

    if not package_name:
        return False, "google_play_package_name is missing"
    if not credential_json:
        return False, "service account JSON is missing"

    check = verify_google_play_connection(
        package_name=package_name,
        credential_json=credential_json,
        discovery_url=config_values.get("google_api_discovery_url", ""),
    )
    return bool(check.get("success")), check.get("message", "")


@router.get("/global", response_model=List[GlobalConfigOut])
async def list_global_config(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _ensure_defaults(db)

    result = await db.execute(select(GlobalConfig).order_by(GlobalConfig.key))
    configs = result.scalars().all()
    config_map = {c.key: c for c in configs}

    ordered: list[GlobalConfigOut] = []
    default_keys = [item["key"] for item in _default_configs()]

    for key in default_keys:
        cfg = config_map.get(key)
        if not cfg:
            continue
        value = _decode_value(cfg.key, cfg.value)
        display_value = mask_value(value) if cfg.key in SENSITIVE_KEYS else value
        ordered.append(GlobalConfigOut(key=cfg.key, value=display_value, description=cfg.description))

    extra = [c for c in configs if c.key not in default_keys and not c.key.startswith("integration_check_")]
    for cfg in extra:
        value = _decode_value(cfg.key, cfg.value)
        display_value = mask_value(value) if cfg.key in SENSITIVE_KEYS else value
        ordered.append(GlobalConfigOut(key=cfg.key, value=display_value, description=cfg.description))

    return ordered


@router.put("/global")
async def update_global_config(
    data: GlobalConfigUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    result = await db.execute(select(GlobalConfig).where(GlobalConfig.key == data.key))
    config = result.scalar_one_or_none()

    encoded = _encode_value(data.key, data.value)

    if config:
        config.value = encoded
        if data.description is not None:
            config.description = data.description
    else:
        config = GlobalConfig(
            key=data.key,
            value=encoded,
            description=data.description or "",
        )
        db.add(config)

    await db.commit()
    return {"status": "ok", "key": data.key}


@router.get("/integrations/status")
async def get_integrations_status(
    app_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await _ensure_defaults(db)
    if app_id is not None:
        await ensure_app_access(db, user, app_id)
    config_map = await _load_configs(db)
    config_values = _plain_config_values(config_map)

    def last_check(provider: str) -> Optional[dict]:
        key = _integration_key(provider, app_id)
        row = config_map.get(key)
        if row is None:
            return None
        return _parse_last_check(row.value)

    google_endpoint = resolve_google_discovery_url(config_values.get("google_api_discovery_url", "")) or "default"

    has_app_credential = False
    has_app_anthropic_key = False
    has_app_openai_key = False
    if app_id is not None:
        cred_result = await db.execute(
            select(AppCredential.credential_type).where(AppCredential.app_id == app_id)
        )
        cred_types = set(cred_result.scalars().all())
        has_app_credential = "service_account_json" in cred_types
        has_app_anthropic_key = "anthropic_api_key" in cred_types
        has_app_openai_key = "openai_api_key" in cred_types

    integrations = [
        {
            "provider": "anthropic",
            "name": "Anthropic",
            "endpoint": "api.anthropic.com",
            "configured": has_app_anthropic_key or bool(config_values.get("anthropic_api_key")),
            "last_check": last_check("anthropic"),
        },
        {
            "provider": "openai",
            "name": "OpenAI",
            "endpoint": "api.openai.com",
            "configured": has_app_openai_key or bool(config_values.get("openai_api_key")),
            "last_check": last_check("openai"),
        },
        {
            "provider": "telegram",
            "name": "Telegram",
            "endpoint": "api.telegram.org",
            "configured": bool(config_values.get("telegram_bot_token")) and bool(config_values.get("telegram_chat_id")),
            "last_check": last_check("telegram"),
        },
        {
            "provider": "serpapi",
            "name": "SerpAPI",
            "endpoint": "serpapi.com",
            "configured": bool(config_values.get("serpapi_key")),
            "last_check": last_check("serpapi"),
        },
        {
            "provider": "google_play",
            "name": "Google Play",
            "endpoint": google_endpoint,
            "configured": has_app_credential or bool(config_values.get("google_service_account_json")),
            "last_check": last_check("google_play"),
            "app_id": app_id,
        },
    ]

    return {"integrations": integrations}


@router.post("/integrations/check")
async def check_integrations(
    body: IntegrationCheckRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_any_role("admin", "sub_admin")),
):
    await _ensure_defaults(db)
    if body.app_id is not None:
        await ensure_app_access(db, user, body.app_id)
    config_map = await _load_configs(db)
    config_values = _plain_config_values(config_map)
    app_overrides: dict[str, str] = {}
    if body.app_id is not None:
        app_cred_rows = (
            await db.execute(
                select(AppCredential).where(
                    AppCredential.app_id == body.app_id,
                    AppCredential.credential_type.in_(("anthropic_api_key", "openai_api_key")),
                )
            )
        ).scalars().all()
        for row in app_cred_rows:
            try:
                app_overrides[row.credential_type] = decrypt_value(row.value)
            except Exception:
                continue

    requested = body.provider.lower().strip()
    providers = ["anthropic", "openai", "telegram", "serpapi", "google_play"] if requested == "all" else [requested]

    results: list[dict] = []
    for provider in providers:
        if provider == "anthropic":
            anthropic_key = app_overrides.get("anthropic_api_key") or config_values.get("anthropic_api_key", "")
            result = await _check_anthropic(anthropic_key)
            connected = result["connected"]
            message = result["message"]
        elif provider == "openai":
            openai_key = app_overrides.get("openai_api_key") or config_values.get("openai_api_key", "")
            result = await _check_openai(openai_key)
            connected = result["connected"]
            message = result["message"]
        elif provider == "telegram":
            connected, message = await _check_telegram(config_values)
            result = {
                "provider": provider,
                "connected": connected,
                "message": message,
                "status": "inference_healthy" if connected else "provider_error",
                "provider_error_class": None if connected else "provider_error",
                "endpoint": "api.telegram.org",
                "provider_name": "Telegram",
                "estimated_cost": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "key_suffix": None,
            }
        elif provider == "serpapi":
            connected, message = await _check_serpapi(config_values)
            result = {
                "provider": provider,
                "connected": connected,
                "message": message,
                "status": "inference_healthy" if connected else "provider_error",
                "provider_error_class": None if connected else "provider_error",
                "endpoint": "serpapi.com",
                "provider_name": "SerpAPI",
                "estimated_cost": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "key_suffix": None,
            }
        elif provider == "google_play":
            connected, message = await _check_google_play(db, config_values, body.app_id)
            result = {
                "provider": provider,
                "connected": connected,
                "message": message,
                "status": "inference_healthy" if connected else "provider_error",
                "provider_error_class": None if connected else "provider_error",
                "endpoint": google_endpoint if (google_endpoint := resolve_google_discovery_url(config_values.get("google_api_discovery_url", "")) or "default") else "default",
                "provider_name": "Google Play",
                "estimated_cost": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "key_suffix": None,
            }
        else:
            connected, message = False, f"Unknown provider: {provider}"
            result = {
                "provider": provider,
                "connected": connected,
                "message": message,
                "status": "provider_error",
                "provider_error_class": "provider_error",
                "endpoint": provider,
                "provider_name": provider.title(),
                "estimated_cost": 0.0,
                "input_tokens": 0,
                "output_tokens": 0,
                "key_suffix": None,
            }

        await _set_last_check(db, provider, body.app_id, result)
        results.append(
            {
                "provider": provider,
                "connected": connected,
                "message": message,
                "status": result.get("status"),
                "provider_error_class": result.get("provider_error_class"),
                "estimated_cost": result.get("estimated_cost", 0.0),
                "input_tokens": result.get("input_tokens", 0),
                "output_tokens": result.get("output_tokens", 0),
                "key_suffix": result.get("key_suffix"),
                "checked_at": datetime.now(timezone.utc).isoformat(),
            }
        )

    await db.commit()
    return {"results": results}
