"""Notifications endpoints."""
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import or_, select
from app.database import get_db
from app.dependencies import ensure_app_access, get_current_user
from app.models.app import App
from app.models.user import User
from app.models.notification import Notification
from app.models.user_app_access import UserAppAccess

router = APIRouter()


async def _accessible_app_ids(db: AsyncSession, user: User) -> list[int]:
    rows = await db.execute(
        select(App.id)
        .outerjoin(
            UserAppAccess,
            (UserAppAccess.app_id == App.id) & (UserAppAccess.user_id == user.id),
        )
        .where(or_(App.owner_user_id == user.id, UserAppAccess.user_id == user.id))
        .distinct()
    )
    return list(rows.scalars().all())


@router.get("")
async def list_notifications(
    app_id: Optional[int] = None,
    page: Optional[int] = Query(None, ge=1),
    limit: int = Query(50, ge=1, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List notifications for one app or all accessible apps, newest first."""
    query = select(Notification).order_by(Notification.id.desc())
    if app_id is not None:
        await ensure_app_access(db, user, app_id)
        query = query.where(Notification.app_id == app_id)
    else:
        app_ids = await _accessible_app_ids(db, user)
        if not app_ids:
            return {"items": [], "total": 0, "page": page, "limit": limit, "has_more": False} if page is not None else []
        query = query.where(Notification.app_id.in_(app_ids))

    total = None
    if page is not None:
        count_query = select(Notification.id)
        if app_id is not None:
            count_query = count_query.where(Notification.app_id == app_id)
        else:
            app_ids = await _accessible_app_ids(db, user)
            if not app_ids:
                return {"items": [], "total": 0, "page": page, "limit": limit, "has_more": False}
            count_query = count_query.where(Notification.app_id.in_(app_ids))
        total = len((await db.execute(count_query)).scalars().all())
        query = query.offset((page - 1) * limit).limit(limit)
    else:
        query = query.limit(limit)

    result = await db.execute(query)
    notifications = result.scalars().all()
    payload = [
        {
            "id": n.id,
            "app_id": n.app_id,
            "title": n.title,
            "message": n.message,
            "notification_type": n.notification_type,
            "is_read": n.is_read,
            "created_at": n.created_at.isoformat() if n.created_at else None,
        }
        for n in notifications
    ]
    if page is None:
        return payload

    return {
        "items": payload,
        "total": total or 0,
        "page": page,
        "limit": limit,
        "has_more": (page * limit) < (total or 0),
    }


@router.patch("/{notification_id}/read")
async def mark_notification_read(
    notification_id: int,
    app_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Mark a notification as read."""
    query = select(Notification).where(Notification.id == notification_id)
    if app_id is not None:
        await ensure_app_access(db, user, app_id)
        query = query.where(Notification.app_id == app_id)

    result = await db.execute(query)
    notification = result.scalar_one_or_none()
    if not notification:
        raise HTTPException(status_code=404, detail="Notification not found")

    if app_id is None:
        app_ids = set(await _accessible_app_ids(db, user))
        if notification.app_id not in app_ids:
            raise HTTPException(status_code=404, detail="Notification not found")

    notification.is_read = True
    await db.commit()
    return {"status": "ok", "notification_id": notification_id}
