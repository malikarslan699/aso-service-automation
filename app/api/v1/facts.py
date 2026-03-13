"""App Facts endpoints: CRUD for verified app features."""
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from pydantic import BaseModel
from app.database import get_db
from app.dependencies import get_current_user, require_any_role, ensure_app_access
from app.models.user import User
from app.models.app_fact import AppFact

router = APIRouter()


class FactCreate(BaseModel):
    fact_key: str
    fact_value: str
    verified: bool = False


class FactUpdate(BaseModel):
    fact_key: Optional[str] = None
    fact_value: Optional[str] = None
    verified: Optional[bool] = None


@router.get("/{app_id}/facts")
async def list_facts(
    app_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """List all app facts."""
    await ensure_app_access(db, user, app_id)
    result = await db.execute(
        select(AppFact).where(AppFact.app_id == app_id).order_by(AppFact.fact_key)
    )
    facts = result.scalars().all()
    return [
        {
            "id": f.id,
            "fact_key": f.fact_key,
            "fact_value": f.fact_value,
            "verified": f.verified,
            "updated_at": f.updated_at.isoformat() if f.updated_at else None,
        }
        for f in facts
    ]


@router.post("/{app_id}/facts", status_code=status.HTTP_201_CREATED)
async def create_fact(
    app_id: int,
    data: FactCreate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_any_role("admin", "sub_admin")),
):
    """Add a new app fact."""
    await ensure_app_access(db, user, app_id)
    fact = AppFact(
        app_id=app_id,
        fact_key=data.fact_key,
        fact_value=data.fact_value,
        verified=data.verified,
    )
    db.add(fact)
    await db.commit()
    await db.refresh(fact)
    return {"id": fact.id, "fact_key": fact.fact_key, "fact_value": fact.fact_value, "verified": fact.verified}


@router.patch("/{app_id}/facts/{fact_id}")
async def update_fact(
    app_id: int,
    fact_id: int,
    data: FactUpdate,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_any_role("admin", "sub_admin")),
):
    """Update an existing app fact."""
    await ensure_app_access(db, user, app_id)
    result = await db.execute(
        select(AppFact)
        .where(AppFact.id == fact_id)
        .where(AppFact.app_id == app_id)
    )
    fact = result.scalar_one_or_none()
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")

    if data.fact_key is not None:
        fact.fact_key = data.fact_key
    if data.fact_value is not None:
        fact.fact_value = data.fact_value
    if data.verified is not None:
        fact.verified = data.verified

    await db.commit()
    return {"id": fact.id, "fact_key": fact.fact_key, "fact_value": fact.fact_value, "verified": fact.verified}


@router.delete("/{app_id}/facts/{fact_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_fact(
    app_id: int,
    fact_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_any_role("admin", "sub_admin")),
):
    """Delete an app fact."""
    await ensure_app_access(db, user, app_id)
    result = await db.execute(
        select(AppFact)
        .where(AppFact.id == fact_id)
        .where(AppFact.app_id == app_id)
    )
    fact = result.scalar_one_or_none()
    if not fact:
        raise HTTPException(status_code=404, detail="Fact not found")
    await db.delete(fact)
    await db.commit()
