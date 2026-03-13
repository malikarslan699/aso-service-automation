from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select, or_
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth.security import hash_password, verify_password
from app.database import get_db
from app.dependencies import get_current_user, require_role
from app.models.app import App
from app.models.user import User
from app.models.user_app_access import UserAppAccess

router = APIRouter()


class CreateSubAdminRequest(BaseModel):
    username: str
    password: str
    email: str | None = None
    app_ids: list[int] = []


class UpdateSubAdminRequest(BaseModel):
    password: str | None = None
    email: str | None = None
    app_ids: list[int] | None = None


class UpdateAssignmentsRequest(BaseModel):
    app_ids: list[int]


class UpdateStatusRequest(BaseModel):
    is_active: bool


def _normalize_optional_email(email: str | None) -> str | None:
    if email is None:
        return None
    email = email.strip()
    return email or None


async def _get_sub_admin_or_404(db: AsyncSession, user_id: int) -> User:
    result = await db.execute(select(User).where(User.id == user_id))
    target = result.scalar_one_or_none()
    if target is None or target.role != "sub_admin":
        raise HTTPException(status_code=404, detail="Sub-admin not found")
    return target


async def _validate_app_ids(db: AsyncSession, app_ids: list[int], actor: User | None = None) -> list[App]:
    if not app_ids:
        return []
    query = select(App).where(App.id.in_(app_ids)).order_by(App.name.asc())
    if actor and actor.role in {"admin", "sub_admin"}:
        query = (
            select(App)
            .outerjoin(
                UserAppAccess,
                (UserAppAccess.app_id == App.id) & (UserAppAccess.user_id == actor.id),
            )
            .where(App.id.in_(app_ids))
            .where(or_(App.owner_user_id == actor.id, UserAppAccess.user_id == actor.id))
            .order_by(App.name.asc())
            .distinct()
        )
    apps = (await db.execute(query)).scalars().all()
    if len(apps) != len(set(app_ids)):
        raise HTTPException(status_code=400, detail="One or more apps were not found or are not accessible")
    return apps


async def _replace_user_access(db: AsyncSession, user_id: int, apps: list[App]) -> None:
    existing = await db.execute(select(UserAppAccess).where(UserAppAccess.user_id == user_id))
    for row in existing.scalars().all():
        await db.delete(row)
    for app in apps:
        db.add(UserAppAccess(user_id=user_id, app_id=app.id))


async def _serialize_sub_admins(db: AsyncSession) -> list[dict]:
    users = (await db.execute(select(User).where(User.role == "sub_admin").order_by(User.id.asc()))).scalars().all()
    accesses = (await db.execute(select(UserAppAccess))).scalars().all()
    apps = (await db.execute(select(App).order_by(App.name.asc()))).scalars().all()
    app_map = {app.id: app for app in apps}

    assigned_map: dict[int, list[App]] = {}
    for access in accesses:
        app = app_map.get(access.app_id)
        if app:
            assigned_map.setdefault(access.user_id, []).append(app)

    owned_map: dict[int, list[App]] = {}
    for app in apps:
        if app.owner_user_id is not None:
            owned_map.setdefault(app.owner_user_id, []).append(app)

    payload = []
    for item in users:
        assigned_apps = sorted(assigned_map.get(item.id, []), key=lambda app: app.name.lower())
        owned_apps = sorted(owned_map.get(item.id, []), key=lambda app: app.name.lower())
        payload.append(
            {
                "id": item.id,
                "username": item.username,
                "email": item.email,
                "role": item.role,
                "is_active": item.is_active,
                "app_ids": [app.id for app in assigned_apps],
                "assigned_projects": [
                    {"id": app.id, "name": app.name, "package_name": app.package_name}
                    for app in assigned_apps
                ],
                "owned_projects": [
                    {"id": app.id, "name": app.name, "package_name": app.package_name}
                    for app in owned_apps
                ],
            }
        )
    return payload


@router.get("/users")
async def list_sub_admins(
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    return await _serialize_sub_admins(db)


@router.post("/users", status_code=status.HTTP_201_CREATED)
async def create_sub_admin(
    body: CreateSubAdminRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    username = body.username.strip()
    if not username:
        raise HTTPException(status_code=400, detail="Username is required")
    if username.lower() == "admin":
        raise HTTPException(status_code=400, detail="Reserved username")
    if not body.password.strip():
        raise HTTPException(status_code=400, detail="Password is required")

    email = _normalize_optional_email(body.email)

    existing = await db.execute(select(User).where(User.username == username))
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail="Username already exists")

    apps = await _validate_app_ids(db, body.app_ids, actor=user)

    sub_admin = User(
        username=username,
        email=email,
        hashed_password=hash_password(body.password),
        role="sub_admin",
        is_active=True,
    )
    db.add(sub_admin)
    await db.flush()

    for app in apps:
        db.add(UserAppAccess(user_id=sub_admin.id, app_id=app.id))

    await db.commit()
    return next(item for item in await _serialize_sub_admins(db) if item["id"] == sub_admin.id)


@router.patch("/users/{user_id}")
async def update_sub_admin(
    user_id: int,
    body: UpdateSubAdminRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    target = await _get_sub_admin_or_404(db, user_id)

    if body.password is not None:
        password = body.password.strip()
        if not password:
            raise HTTPException(status_code=400, detail="Password cannot be empty")
        target.hashed_password = hash_password(password)

    if body.email is not None:
        target.email = _normalize_optional_email(body.email)

    if body.app_ids is not None:
        apps = await _validate_app_ids(db, body.app_ids, actor=user)
        await _replace_user_access(db, target.id, apps)

    await db.commit()
    return {"status": "ok", "user_id": target.id}


@router.put("/users/{user_id}/apps")
async def update_sub_admin_assignments(
    user_id: int,
    body: UpdateAssignmentsRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    target = await _get_sub_admin_or_404(db, user_id)
    apps = await _validate_app_ids(db, body.app_ids, actor=user)
    await _replace_user_access(db, target.id, apps)
    await db.commit()
    return {"status": "ok", "user_id": target.id, "app_ids": sorted(body.app_ids)}


@router.patch("/users/{user_id}/status")
async def update_sub_admin_status(
    user_id: int,
    body: UpdateStatusRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    target = await _get_sub_admin_or_404(db, user_id)
    target.is_active = body.is_active
    await db.commit()
    return {"status": "ok", "user_id": target.id, "is_active": target.is_active}


@router.delete("/users/{user_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_sub_admin(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(require_role("admin")),
):
    target = await _get_sub_admin_or_404(db, user_id)
    await db.delete(target)
    await db.commit()


class ChangePasswordRequest(BaseModel):
    current_password: str
    new_password: str


@router.patch("/me/password")
async def change_own_password(
    body: ChangePasswordRequest,
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
):
    """Allow any logged-in user (admin or sub_admin) to change their own password."""
    if not verify_password(body.current_password, user.hashed_password):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")
    if len(body.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters.")
    user.hashed_password = hash_password(body.new_password)
    await db.commit()
    return {"status": "ok", "message": "Password changed successfully."}
