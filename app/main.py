import logging
from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app.config import settings
from app.core.exceptions import TrackingError
from app.routers import tracking
from app.services import cache_service

logging.basicConfig(
    level=getattr(logging, settings.log_level.upper(), logging.INFO),
    format="%(asctime)s %(levelname)s %(name)s — %(message)s",
)


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    yield
    await cache_service.close()


app = FastAPI(
    title="Cargo Tracking API",
    description="AI agent for tracking air cargo (AWB) and sea containers",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)


@app.exception_handler(TrackingError)
async def tracking_error_handler(request: Request, exc: TrackingError) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={"error": exc.code, "message": exc.message, "source": exc.source},
    )


@app.exception_handler(Exception)
async def generic_error_handler(request: Request, exc: Exception) -> JSONResponse:
    logging.getLogger(__name__).exception("Unhandled error")
    return JSONResponse(status_code=500, content={"error": "INTERNAL_ERROR", "message": "An unexpected error occurred"})


@app.get("/health", tags=["health"])
async def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


app.include_router(tracking.router, prefix="/api/v1")
