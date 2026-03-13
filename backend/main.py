"""
PraxiAlpha — FastAPI Application Entry Point
"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from backend.config import get_settings

settings = get_settings()


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application startup and shutdown events."""
    # Startup
    print("🚀 PraxiAlpha starting up...")
    print(f"   Environment: {settings.app_env}")
    print(f"   Debug: {settings.app_debug}")
    yield
    # Shutdown
    print("🛑 PraxiAlpha shutting down...")


app = FastAPI(
    title="PraxiAlpha API",
    description="Systematic trading and education platform for retail investors",
    version="0.1.0",
    lifespan=lifespan,
)

# ---- CORS Middleware ----
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"] if settings.app_debug else [],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ---- Health Check ----
@app.get("/health", tags=["System"])
async def health_check():
    """Health check endpoint."""
    return {
        "status": "healthy",
        "app": "PraxiAlpha",
        "version": "0.1.0",
        "environment": settings.app_env,
    }


@app.get("/", tags=["System"])
async def root():
    """Root endpoint."""
    return {
        "message": "Welcome to PraxiAlpha — Disciplined action that generates alpha.",
        "docs": "/docs",
    }
