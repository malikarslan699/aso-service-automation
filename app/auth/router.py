from fastapi import APIRouter, Depends, HTTPException, Request, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.database import get_db
from app.models.user import User
from app.auth.security import verify_password, create_access_token
from app.dependencies import get_current_user
from app.schemas.auth import LoginRequest, TokenResponse, UserOut
from app.services.login_rate_limiter import clear_failures, is_limited, record_failure

auth_router = APIRouter()


@auth_router.post("/login", response_model=TokenResponse)
async def login(request: LoginRequest, http_request: Request, db: AsyncSession = Depends(get_db)):
    client_ip = _get_client_ip(http_request)

    if await is_limited(client_ip):
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail="Too many failed login attempts. Please try again in 60 seconds.",
        )

    result = await db.execute(select(User).where(User.username == request.username))
    user = result.scalar_one_or_none()
    if user is None or not verify_password(request.password, user.hashed_password):
        await record_failure(client_ip)
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")
    if not user.is_active:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account disabled")
    await clear_failures(client_ip)
    token = create_access_token(user.id, user.role)
    return TokenResponse(access_token=token, token_type="bearer", role=user.role)


@auth_router.get("/me", response_model=UserOut)
async def me(user: User = Depends(get_current_user)):
    return UserOut(id=user.id, username=user.username, email=user.email, role=user.role, is_active=user.is_active)


def _get_client_ip(request: Request) -> str:
    forwarded_for = request.headers.get("x-forwarded-for")
    if forwarded_for:
        first_ip = forwarded_for.split(",")[0].strip()
        if first_ip:
            return first_ip

    real_ip = request.headers.get("x-real-ip", "").strip()
    if real_ip:
        return real_ip

    if request.client and request.client.host:
        return request.client.host

    return "unknown"
