from fastapi import Depends, HTTPException, status, Header
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import Optional
from app.database import get_db
from app.auth.security import decode_token
from app.models.user import User
from app.models.app import App
from app.models.user_app_access import UserAppAccess

security = HTTPBearer()


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db),
) -> User:
    token = credentials.credentials
    payload = decode_token(token)
    if payload is None:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
    result = await db.execute(select(User).where(User.id == int(payload["sub"])))
    user = result.scalar_one_or_none()
    if user is None or not user.is_active:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or inactive")
    return user


def require_role(role: str):
    async def check_role(user: User = Depends(get_current_user)):
        if user.role != role:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Requires {role} role")
        return user
    return check_role


def require_any_role(*roles: str):
    async def check_role(user: User = Depends(get_current_user)):
        if user.role not in roles:
            joined = ", ".join(roles)
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=f"Requires one of: {joined}")
        return user
    return check_role


async def user_has_app_access(db: AsyncSession, user: User, app_id: int) -> bool:
    if user.role == "admin":
        return True
    app_result = await db.execute(select(App).where(App.id == app_id))
    app = app_result.scalar_one_or_none()
    if app is None:
        return False
    if app.owner_user_id == user.id:
        return True
    result = await db.execute(
        select(UserAppAccess).where(
            UserAppAccess.user_id == user.id,
            UserAppAccess.app_id == app_id,
        )
    )
    return result.scalar_one_or_none() is not None


async def ensure_app_access(db: AsyncSession, user: User, app_id: int) -> App:
    result = await db.execute(select(App).where(App.id == app_id))
    app = result.scalar_one_or_none()
    if app is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="App not found")
    if not await user_has_app_access(db, user, app_id):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="No access to this project")
    return app


async def get_current_app(
    x_app_id: Optional[str] = Header(None),
    db: AsyncSession = Depends(get_db),
    user: User = Depends(get_current_user),
) -> App:
    if not x_app_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="X-App-Id header required")
    try:
        app_id = int(x_app_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid X-App-Id")
    return await ensure_app_access(db, user, app_id)
