"""FastAPI application factory.

Cross-cutting concerns live here and nowhere else:

* structured JSON logging + a request-id context var (see utils.logging),
* explicit CORS origins (never a wildcard in production),
* typed error handlers: domain errors render as ``{code, message}`` with their
  own HTTP status; anything unexpected is a bare 500 with the stack kept in
  the log only,
* a lifespan that builds the container once and drains in-flight analyses on
  shutdown (graceful stop).
"""
from __future__ import annotations

import logging
import time
import uuid
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.api import routes, websocket
from app.api.deps import init_container
from app.config import get_settings
from app.domain.errors import AlphaForgeError
from app.utils.logging import configure_logging, request_id_var

log = logging.getLogger("alphaforge")


@asynccontextmanager
async def lifespan(_: FastAPI) -> AsyncIterator[None]:
    settings = get_settings()
    configure_logging("DEBUG" if settings.debug else "INFO")
    container = init_container(settings)
    log.info(
        "alphaforge starting: provider=%s persistence=%s cache=%s llm=%s",
        settings.data_provider,
        settings.persistence,
        settings.cache_backend,
        settings.llm_provider,
    )
    try:
        yield
    finally:
        log.info("alphaforge shutting down: draining analyses")
        await container.manager.close_all()
        await container.commands.shutdown()


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(
        title="AlphaForge API",
        version="0.1.0",
        description="AI 驱动的 A 股量化分析平台：多智能体定性推理 + 确定性回测",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=False,
        allow_methods=["GET", "POST", "OPTIONS"],
        allow_headers=["Content-Type", "X-Request-Id"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):  # type: ignore[no-untyped-def]
        request_id = request.headers.get("X-Request-Id") or uuid.uuid4().hex[:16]
        token = request_id_var.set(request_id)
        started = time.perf_counter()
        try:
            response = await call_next(request)
        finally:
            request_id_var.reset(token)
        elapsed_ms = (time.perf_counter() - started) * 1000
        response.headers["X-Request-Id"] = request_id
        log.info(
            "%s %s -> %s (%.1fms)",
            request.method,
            request.url.path,
            getattr(response, "status_code", "?"),
            elapsed_ms,
        )
        return response

    @app.exception_handler(AlphaForgeError)
    async def domain_error_handler(_: Request, exc: AlphaForgeError) -> JSONResponse:
        log.warning("domain error %s: %s", exc.code, exc.message)
        return JSONResponse(
            status_code=exc.http_status,
            content={"error": {"code": exc.code, "message": exc.message}},
        )

    @app.exception_handler(Exception)
    async def unhandled_error_handler(request: Request, exc: Exception) -> JSONResponse:
        log.exception("unhandled error on %s", request.url.path)
        return JSONResponse(
            status_code=500,
            content={
                "error": {
                    "code": "INTERNAL_ERROR",
                    "message": "服务器内部错误，请稍后重试",
                }
            },
        )

    app.include_router(routes.router)
    app.include_router(routes.health_router)
    app.include_router(websocket.router)
    return app


app = create_app()
