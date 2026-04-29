"""
FastAPI application for the Ishikawa Knowledge System.
Main entry point for the REST API server.
"""

from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .routers.v1 import router, service as v1_service
from .root_cause.routes import router as root_cause_router, service as root_cause_service
from ..utils.config import get_config
from ..utils.logging import setup_logging, get_logger

logger = get_logger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Application lifespan manager for startup and shutdown."""
    logger.info("Starting Ishikawa Knowledge System API")

    config = get_config()
    logger.info(f"API configured for {config.api.host}:{config.api.port}")

    yield

    for service_name, svc in (("api.v1", v1_service), ("api.root_cause", root_cause_service)):
        try:
            svc.close()
            logger.info("Released shared resources for %s service", service_name)
        except Exception as exc:
            logger.warning("Failed to close shared resources for %s service: %s", service_name, exc)

    logger.info("Shutting down Ishikawa Knowledge System API")


def create_application() -> FastAPI:
    """Create and configure the FastAPI application."""

    config = get_config()

    # Create FastAPI app
    app = FastAPI(
        title="Ishikawa Knowledge System API",
        description="AI-powered root cause analysis using Ishikawa (Fishbone) methodology",
        version="1.0.0",
        lifespan=lifespan
    )

    # Configure CORS
    app.add_middleware(
        CORSMiddleware,
        allow_origins=config.api.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Global exception handler
    @app.exception_handler(Exception)
    async def global_exception_handler(request: Request, exc: Exception):
        logger.error(f"Unhandled exception: {exc}", exc_info=True)
        return JSONResponse(
            status_code=500,
            content={
                "error": "Internal server error",
                "message": str(exc),
                "path": str(request.url)
            }
        )

    # Include API routes
    app.include_router(router)
    app.include_router(root_cause_router)

    # Health check endpoint (simple)
    @app.get("/health")
    async def health():
        """Simple health check endpoint."""
        return {"status": "healthy", "service": "Ishikawa Knowledge System API"}

    logger.info("FastAPI application created")
    return app


# Create the application instance
app = create_application()


if __name__ == "__main__":
    import uvicorn

    config = get_config()

    setup_logging(level=config.log_level)

    uvicorn.run(
        "src.api.app:app",
        host=config.api.host,
        port=config.api.port,
        reload=config.debug,
        log_level=config.log_level.lower()
    )