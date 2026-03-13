from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.v1.router import api_router
from app.auth.router import auth_router
from app.config import get_settings


@asynccontextmanager
async def lifespan(app: FastAPI):
    yield


app = FastAPI(
    title="ASO Service",
    description="AI-powered App Store Optimization",
    version="1.0.0",
    lifespan=lifespan,
)

_settings = get_settings()
_origins = [o.strip() for o in _settings.allowed_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth_router, prefix="/auth", tags=["auth"])
app.include_router(api_router, prefix="/api/v1")


@app.get("/health")
async def health():
    return {"status": "ok"}


@app.get("/health/detailed")
async def health_detailed():
    """Detailed health check: verifies DB, Redis, and reports AI/Google Play credential presence."""
    import asyncio
    from app.database import get_db
    from sqlalchemy import text

    results: dict = {"api": "ok", "database": "unknown", "redis": "unknown", "ai_key_set": False, "google_play_key_set": False}

    # Database check
    try:
        from app.database import async_engine
        async with async_engine.connect() as conn:
            await conn.execute(text("SELECT 1"))
        results["database"] = "ok"
    except Exception as exc:
        results["database"] = f"error: {type(exc).__name__}"

    # Redis check
    try:
        import redis.asyncio as aioredis
        r = aioredis.from_url(_settings.redis_url, socket_connect_timeout=2)
        await r.ping()
        await r.aclose()
        results["redis"] = "ok"
    except Exception as exc:
        results["redis"] = f"error: {type(exc).__name__}"

    # Credential presence (not values)
    results["ai_key_set"] = bool(_settings.anthropic_api_key or _settings.openai_api_key)
    results["google_play_key_set"] = bool(_settings.google_service_account_json)

    overall = "ok" if results["database"] == "ok" and results["redis"] == "ok" else "degraded"
    return {"status": overall, **results}
