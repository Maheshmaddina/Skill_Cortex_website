import logging
from typing import Annotated

from fastapi import Depends, FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import Settings, get_settings
from app.database import get_db
from app.routes import (
    admin_bookings,
    admin_dashboard,
    admin_departments,
    admin_notifications,
    admin_payments,
    admin_reminder_rules,
    admin_slots,
    admin_users,
    admin_webinars,
    auth,
    bookings,
    departments,
    internal,
    notifications,
    payments,
    users,
    webinars,
)
from app.services.errors import ServiceError

logger = logging.getLogger("uvicorn.error")

ROUTERS = (
    auth,
    users,
    departments,
    webinars,
    bookings,
    payments,
    notifications,
    admin_dashboard,
    admin_users,
    admin_departments,
    admin_webinars,
    admin_slots,
    admin_bookings,
    admin_payments,
    admin_notifications,
    admin_reminder_rules,
    internal,
)

SECURITY_HEADERS = {
    "X-Content-Type-Options": "nosniff",
    "X-Frame-Options": "DENY",
    "Referrer-Policy": "no-referrer",
    "Permissions-Policy": "camera=(), microphone=(), geolocation=(), payment=()",
    "Cross-Origin-Opener-Policy": "same-origin",
}
# The API only returns JSON; the interactive docs (disabled in production) need scripts and styles.
API_CSP = "default-src 'none'; frame-ancestors 'none'"
DOCS_PATHS = ("/docs", "/redoc", "/openapi.json")


def create_app(settings: Settings | None = None) -> FastAPI:
    settings = settings or get_settings()
    docs = not settings.is_production
    app = FastAPI(
        title="Skill Cortex API",
        version="1.0.0",
        docs_url="/docs" if docs else None,
        redoc_url="/redoc" if docs else None,
        openapi_url="/openapi.json" if docs else None,
    )

    @app.middleware("http")
    async def security_middleware(request: Request, call_next):
        declared_length = request.headers.get("content-length", "")
        if declared_length.isdigit() and int(declared_length) > settings.max_request_body_bytes:
            response = JSONResponse(status_code=413, content={"detail": "Request body is too large."})
        else:
            response = await call_next(request)
        for name, value in SECURITY_HEADERS.items():
            response.headers.setdefault(name, value)
        if not request.url.path.startswith(DOCS_PATHS):
            response.headers.setdefault("Content-Security-Policy", API_CSP)
        if settings.cookie_secure:
            response.headers.setdefault("Strict-Transport-Security", "max-age=31536000; includeSubDomains")
        return response

    # Added after the security middleware so CORS headers are applied outermost (even to 413s).
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origin_list,
        allow_credentials=True,  # refresh token cookie
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.exception_handler(ServiceError)
    async def service_error_handler(request: Request, exc: ServiceError) -> JSONResponse:
        return JSONResponse(
            status_code=exc.status_code, content={"detail": exc.message}, headers=getattr(exc, "headers", None)
        )

    @app.exception_handler(Exception)
    async def unexpected_error_handler(request: Request, exc: Exception) -> JSONResponse:
        # Never leak internals; the traceback is still logged by the server.
        logger.error("Unhandled error on %s %s", request.method, request.url.path, exc_info=exc)
        return JSONResponse(status_code=500, content={"detail": "Something went wrong on our side. Please try again."})

    for module in ROUTERS:
        app.include_router(module.router)

    @app.get("/health", tags=["system"])
    def health(db: Annotated[Session, Depends(get_db)]) -> dict[str, str]:
        try:
            db.execute(text("SELECT 1"))
        except SQLAlchemyError:
            raise HTTPException(status_code=503, detail={"status": "degraded", "database": "unavailable"})
        return {"status": "ok", "database": "ok"}

    return app


app = create_app()
