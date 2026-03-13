import json
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, UploadFile, File, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, or_
from typing import List
from pydantic import BaseModel
from app.database import get_db
from app.dependencies import get_current_user, require_any_role, require_role, ensure_app_access
from app.models.user import User
from app.models.app import App
from app.models.app_credential import AppCredential
from app.models.global_config import GlobalConfig
from app.models.user_app_access import UserAppAccess
from app.schemas.app import AppCreate, AppOut, AppUpdate
from app.utils.encryption import encrypt_value, decrypt_value
from app.config import get_settings
from app.services.data_fetcher import verify_google_play_connection, resolve_google_discovery_url

router = APIRouter()

TEXT_CREDENTIAL_TYPES = {"anthropic_api_key", "openai_api_key"}


class TextCredentialRequest(BaseModel):
    credential_type: str
    value: str


@router.get("", response_model=List[AppOut])
async def list_apps(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    query = (
        select(App)
        .outerjoin(
            UserAppAccess,
            (UserAppAccess.app_id == App.id) & (UserAppAccess.user_id == user.id),
        )
        .where(or_(App.owner_user_id == user.id, UserAppAccess.user_id == user.id))
        .order_by(App.created_at.desc())
        .distinct()
    )
    result = await db.execute(query)
    return result.scalars().all()


@router.post("", response_model=AppOut, status_code=status.HTTP_201_CREATED)
async def create_app(
    data: AppCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_any_role("admin", "sub_admin")),
):
    existing = await db.execute(select(App).where(App.package_name == data.package_name))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Package name already exists")
    app = App(name=data.name, package_name=data.package_name, store=data.store, owner_user_id=user.id)
    db.add(app)
    await db.commit()
    await db.refresh(app)
    return app


@router.get("/{app_id}", response_model=AppOut)
async def get_app(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    return await ensure_app_access(db, user, app_id)


@router.patch("/{app_id}", response_model=AppOut)
async def update_app(
    app_id: int,
    data: AppUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_any_role("admin", "sub_admin")),
):
    app = await ensure_app_access(db, user, app_id)
    if data.name is not None:
        app.name = data.name
    if data.status is not None and user.role == "admin":
        app.status = data.status
    await db.commit()
    await db.refresh(app)
    return app


@router.post("/{app_id}/credentials")
async def upload_credential(
    app_id: int,
    credential_type: str = Query("service_account_json"),
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_any_role("admin", "sub_admin")),
):
    await ensure_app_access(db, user, app_id)

    content = await file.read()
    try:
        content_text = content.decode("utf-8")
    except UnicodeDecodeError:
        raise HTTPException(status_code=400, detail="Credential file must be valid UTF-8")

    if credential_type == "service_account_json":
        try:
            parsed = json.loads(content_text)
        except json.JSONDecodeError as exc:
            raise HTTPException(status_code=400, detail=f"Invalid JSON file: {exc.msg}")
        if not isinstance(parsed, dict):
            raise HTTPException(status_code=400, detail="Credential JSON must be an object")
        content_text = json.dumps(parsed)

    encrypted = encrypt_value(content_text)

    # Upsert credential
    existing = await db.execute(
        select(AppCredential).where(
            AppCredential.app_id == app_id,
            AppCredential.credential_type == credential_type,
        )
    )
    cred = existing.scalar_one_or_none()
    if cred:
        cred.value = encrypted
    else:
        cred = AppCredential(app_id=app_id, credential_type=credential_type, value=encrypted)
        db.add(cred)

    await db.commit()
    return {"status": "ok", "credential_type": credential_type}


@router.put("/{app_id}/credentials/text")
async def upsert_text_credential(
    app_id: int,
    body: TextCredentialRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_any_role("admin", "sub_admin")),
):
    await ensure_app_access(db, user, app_id)
    credential_type = body.credential_type.strip().lower()
    if credential_type not in TEXT_CREDENTIAL_TYPES:
        raise HTTPException(status_code=400, detail=f"Unsupported credential_type. Allowed: {', '.join(sorted(TEXT_CREDENTIAL_TYPES))}")

    value = body.value.strip()
    existing = await db.execute(
        select(AppCredential).where(
            AppCredential.app_id == app_id,
            AppCredential.credential_type == credential_type,
        )
    )
    cred = existing.scalar_one_or_none()

    if not value:
        if cred:
            await db.delete(cred)
            await db.commit()
        return {"status": "ok", "credential_type": credential_type, "configured": False}

    encrypted = encrypt_value(value)
    if cred:
        cred.value = encrypted
    else:
        db.add(AppCredential(app_id=app_id, credential_type=credential_type, value=encrypted))
    await db.commit()
    return {"status": "ok", "credential_type": credential_type, "configured": True}


@router.get("/{app_id}/credentials/status")
async def get_credential_status(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    await ensure_app_access(db, user, app_id)
    rows = (
        await db.execute(
            select(AppCredential.credential_type).where(AppCredential.app_id == app_id)
        )
    ).scalars().all()
    configured = set(rows)
    return {
        "app_id": app_id,
        "service_account_json": "service_account_json" in configured,
        "anthropic_api_key": "anthropic_api_key" in configured,
        "openai_api_key": "openai_api_key" in configured,
    }


@router.get("/{app_id}/connections/google-play")
async def check_google_play_connection(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    app = await ensure_app_access(db, user, app_id)

    cred_row = await db.execute(
        select(AppCredential).where(
            AppCredential.app_id == app_id,
            AppCredential.credential_type == "service_account_json",
        )
    )
    credential = cred_row.scalar_one_or_none()
    if credential is None:
        return {
            "connected": False,
            "provider": "google_play",
            "package_name": app.package_name,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "message": "Google Play service account credential not configured",
            "endpoint": _resolve_google_discovery_url(None),
        }

    try:
        credential_json = decrypt_value(credential.value)
    except Exception:
        return {
            "connected": False,
            "provider": "google_play",
            "package_name": app.package_name,
            "checked_at": datetime.now(timezone.utc).isoformat(),
            "message": "Stored credential could not be decrypted",
            "endpoint": _resolve_google_discovery_url(None),
        }

    discovery_url = await _get_google_discovery_url(db)
    check = verify_google_play_connection(
        package_name=app.package_name,
        credential_json=credential_json,
        discovery_url=discovery_url,
    )

    return {
        "connected": bool(check.get("success")),
        "provider": "google_play",
        "package_name": app.package_name,
        "checked_at": datetime.now(timezone.utc).isoformat(),
        "message": check.get("message", ""),
        "endpoint": _resolve_google_discovery_url(discovery_url),
    }


def _resolve_google_discovery_url(discovery_url: str | None) -> str:
    if discovery_url:
        return resolve_google_discovery_url(discovery_url) or "default"
    settings = get_settings()
    return resolve_google_discovery_url(settings.google_api_discovery_url) or "default"


async def _get_google_discovery_url(db: AsyncSession) -> str | None:
    result = await db.execute(
        select(GlobalConfig).where(GlobalConfig.key == "google_api_discovery_url")
    )
    row = result.scalar_one_or_none()
    if row is None or not row.value:
        return None

    # Backward compatibility: value can be plain text or encrypted.
    try:
        return decrypt_value(row.value)
    except Exception:
        return row.value
