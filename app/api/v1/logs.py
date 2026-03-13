"""System logs endpoint (admin only)."""
from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from app.database import get_db
from app.dependencies import require_role
from app.models.user import User
from app.models.system_log import SystemLog

router = APIRouter()


@router.get("")
async def list_logs(
    level: Optional[str] = Query(None),
    module: Optional[str] = Query(None),
    limit: int = Query(50, le=200),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    """List system logs. Admin only."""
    query = select(SystemLog).order_by(SystemLog.id.desc())

    if level:
        query = query.where(SystemLog.level == level)
    if module:
        query = query.where(SystemLog.module == module)

    query = query.limit(limit)
    result = await db.execute(query)
    logs = result.scalars().all()

    return [
        {
            "id": log.id,
            "level": log.level,
            "module": log.module,
            "message": log.message,
            "details": log.details,
            "created_at": log.created_at.isoformat() if log.created_at else None,
        }
        for log in logs
    ]
