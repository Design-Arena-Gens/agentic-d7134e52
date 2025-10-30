"""
Healthcare AI Agentic System - Main FastAPI Application
Free OSS stack: FastAPI + PostgreSQL + sentence-transformers + networkx
"""
import os
from contextlib import asynccontextmanager
from fastapi import FastAPI, Depends, HTTPException, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from prometheus_client import make_asgi_app
import logging
from pythonjsonlogger import jsonlogger

from backend.config import settings
from backend.database import engine, init_db
from backend.api import auth, providers, agents, workflows, graph, rag
from backend.utils.logging_config import setup_logging

# Setup structured logging
setup_logging()
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Lifecycle manager for startup and shutdown"""
    logger.info("Starting Healthcare AI Agentic System")

    # Initialize database
    await init_db()
    logger.info("Database initialized")

    # Initialize ML models
    from backend.ml.embeddings import embedding_service
    await embedding_service.initialize()
    logger.info("Embedding models loaded")

    # Initialize agent system
    from backend.agents.meta_agent import meta_agent
    await meta_agent.initialize()
    logger.info("Agent system initialized")

    yield

    # Cleanup
    logger.info("Shutting down gracefully")
    await engine.dispose()


# Create FastAPI app
app = FastAPI(
    title="Healthcare AI Agentic System",
    description="Production-grade healthcare provider verification with AI agents",
    version="1.0.0",
    lifespan=lifespan
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Mount Prometheus metrics
metrics_app = make_asgi_app()
app.mount("/metrics", metrics_app)

# Health check
@app.get("/health")
async def health_check():
    return {
        "status": "healthy",
        "environment": settings.ENVIRONMENT,
        "version": "1.0.0"
    }

@app.get("/")
async def root():
    return {
        "message": "Healthcare AI Agentic System API",
        "docs": "/docs",
        "health": "/health",
        "metrics": "/metrics"
    }

# Include routers
app.include_router(auth.router, prefix="/auth", tags=["Authentication"])
app.include_router(providers.router, prefix="/providers", tags=["Providers"])
app.include_router(agents.router, prefix="/agents", tags=["Agents"])
app.include_router(workflows.router, prefix="/workflow", tags=["Workflows"])
app.include_router(graph.router, prefix="/graph", tags=["Trust Graph"])
app.include_router(rag.router, prefix="/rag", tags=["RAG & LLM"])

# Global exception handler
@app.exception_handler(Exception)
async def global_exception_handler(request, exc):
    logger.error(f"Unhandled exception: {exc}", exc_info=True)
    return JSONResponse(
        status_code=500,
        content={"detail": "Internal server error"}
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=8000,
        reload=settings.ENVIRONMENT == "development"
    )
