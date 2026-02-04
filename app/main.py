from __future__ import annotations

from contextlib import asynccontextmanager

import sentry_sdk
from fastapi import FastAPI, Request
from fastapi.responses import ORJSONResponse

from app.api.v1.routes import users
from app.core.config import settings
from app.core.logging import setup_logging
from app.services.http_client import OrientatiException

sentry_sdk.init(
    dsn=settings.SENTRY_DSN,
    send_default_pii=True,
    release=settings.SENTRY_RELEASE,
)
sentry_sdk.set_tag("service.name", settings.SERVICE_NAME)


@asynccontextmanager
async def lifespan(app: FastAPI):
    setup_logging()
    yield


app = FastAPI(
    title=settings.SERVICE_NAME,
    default_response_class=ORJSONResponse,
    version=settings.SERVICE_VERSION,
    lifespan=lifespan,
)


@app.exception_handler(OrientatiException)
async def orientati_exception_handler(request: Request, exc: OrientatiException):
    return ORJSONResponse(
        status_code=exc.status_code,
        content=exc.details if exc.details else {"message": exc.message},
    )


# Routers
app.include_router(users.router, prefix="/api/v1/users", tags=["users"])


@app.get("/health", tags=["health"])
def health():
    return {"status": "ok", "service": settings.SERVICE_NAME}
