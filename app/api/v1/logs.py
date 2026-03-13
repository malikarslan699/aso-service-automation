"""Project-scoped system logs endpoints."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, delete, or_
from typing import Optional
from app.database import get_db
from app.dependencies import ensure_app_access, require_any_role
from app.models.app import App
from app.models.user import User
from app.models.user_app_access import UserAppAccess
from app.models.system_log import SystemLog

router = APIRouter()


async def _accessible_app_ids(db: AsyncSession, user: User) -> list[int]:
    result = await db.execute(
        select(App.id)
        .outerjoin(
            UserAppAccess,
            (UserAppAccess.app_id == App.id) & (UserAppAccess.user_id == user.id),
        )
        .where(or_(App.owner_user_id == user.id, UserAppAccess.user_id == user.id))
        .distinct()
    )
    return list(result.scalars().all())


@router.get("")
async def list_logs(
    level: Optional[str] = Query(None),
    module: Optional[str] = Query(None),
    app_id: Optional[int] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_any_role("admin", "sub_admin")),
):
    """List project-scoped system logs."""
    query = select(SystemLog).order_by(SystemLog.id.desc())

    if level:
        query = query.where(SystemLog.level == level)
    if module:
        query = query.where(SystemLog.module == module)
    if app_id is not None:
        await ensure_app_access(db, user, app_id)
        query = query.where(SystemLog.app_id == app_id)
    else:
        accessible_app_ids = await _accessible_app_ids(db, user)
        if not accessible_app_ids:
            return []
        query = query.where(SystemLog.app_id.in_(accessible_app_ids))

    query = query.limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    return [
        {
            "id": log.id,
            "app_id": log.app_id,
            "level": log.level,
            "module": log.module,
            "message": log.message,
            "details": log.details,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]


@router.delete("")
async def clear_logs(
    level: Optional[str] = Query(None),
    module: Optional[str] = Query(None),
    app_id: Optional[int] = Query(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_any_role("admin", "sub_admin")),
):
    """Clear project-scoped logs accessible to the current user."""
    query = delete(SystemLog)
    if level:
        query = query.where(SystemLog.level == level)
    if module:
        query = query.where(SystemLog.module == module)
    if app_id is not None:
        await ensure_app_access(db, user, app_id)
        query = query.where(SystemLog.app_id == app_id)
    else:
        accessible_app_ids = await _accessible_app_ids(db, user)
        if not accessible_app_ids:
            return {"status": "ok", "deleted": 0}
        query = query.where(SystemLog.app_id.in_(accessible_app_ids))

    result = await db.execute(query)
    await db.commit()
    deleted = result.rowcount if result.rowcount is not None and result.rowcount >= 0 else 0
    return {"status": "ok", "deleted": deleted}
