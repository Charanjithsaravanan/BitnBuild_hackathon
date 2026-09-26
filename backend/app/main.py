from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from sqlalchemy import text
from fastapi.responses import JSONResponse

from .config import get_settings
from .db import Base, engine
from .routers_auth import router as auth_router
from .routers_experiments import router as experiments_router
from .routers_public import router as public_router

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Local/demo uses metadata.create_all. Production runs Alembic before workers start.
    if settings.environment.lower() != "production":
        Base.metadata.create_all(bind=engine)
    yield


app = FastAPI(
    title=settings.app_name,
    version="2.0.0",
    description=(
        "Research-oriented SaaS API for browser behavioral experiments, with "
        "versioning, secure participant sessions, reproducible randomization, "
        "timing diagnostics, consent records, and exports."
    ),
    lifespan=lifespan,
)

if settings.trusted_host_list:
    app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_host_list)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origin_list,
    allow_credentials=False,
    allow_methods=["GET", "POST", "PUT", "PATCH", "OPTIONS"],
    allow_headers=["Authorization", "Content-Type"],
)


@app.middleware("http")
async def security_and_body_middleware(request: Request, call_next):
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > settings.max_body_bytes:
                return JSONResponse(status_code=413, content={"detail": "Request body too large"})
        except ValueError:
            return JSONResponse(status_code=400, content={"detail": "Invalid Content-Length"})

    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    response.headers["Cache-Control"] = "no-store" if request.url.path.startswith("/api/") else "no-cache"
    if settings.environment.lower() == "production" and settings.require_https_in_production:
        response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"
    return response


@app.get("/health", tags=["System"])
def health():
    return {"status": "ok", "service": settings.app_name, "environment": settings.environment}


@app.get("/ready", tags=["System"])
def ready():
    with engine.connect() as connection:
        connection.execute(text("SELECT 1"))
    return {"status": "ready", "service": settings.app_name}


app.include_router(auth_router, prefix="/api/v1")
app.include_router(experiments_router, prefix="/api/v1")
app.include_router(public_router, prefix="/api/v1")
