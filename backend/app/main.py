import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from slowapi import _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded

from app.core.config import settings
from app.core.rate_limit import limiter
from app.players.router import router as players_router
from app.rooms.manager import manager
from app.rooms.router import router as rooms_router

if len(settings.jwt_secret) < 32:
    raise RuntimeError(
        "JWT_SECRET is missing or too weak: set at least 32 random characters in .env "
        '(python -c "import secrets; print(secrets.token_urlsafe(48))").'
    )


@asynccontextmanager
async def lifespan(app: FastAPI):
    cleanup_task = asyncio.create_task(manager.cleanup_loop())
    yield
    cleanup_task.cancel()


app = FastAPI(
    title="Nine to One API", docs_url=None, redoc_url=None, openapi_url=None, lifespan=lifespan
)

app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(players_router)
app.include_router(rooms_router)


@app.get("/api/health")
async def health() -> dict[str, str]:
    return {"status": "ok"}
