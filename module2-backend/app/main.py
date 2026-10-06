"""
SAIV Backend API - Module 2

Stub authentication, RBAC, and Redis rate limiting for the login UI.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .routers import auth, observability, rbac_stubs, users
from contextlib import asynccontextmanager
from fastapi import FastAPI
from database import engine, Base
import models # Import your models so metadata registers them

@asynccontextmanager
async def lifespan(app: FastAPI):
    # --- Startup: Initialize database schema ---
    Base.metadata.create_all(bind=engine)
    yield
    # --- Shutdown: Clean up resources if needed ---


app = FastAPI(
    lifespan=lifespan,
    title="SAIV Backend API",
    description="Secure Attendance & Identity Verification System",
    version="1.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:3000", "http://localhost:8501"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(auth.router, prefix="/api/v1")
app.include_router(users.router, prefix="/api/v1")
app.include_router(observability.router, prefix="/api/v1")
app.include_router(rbac_stubs.router, prefix="/api/v1")




@app.get("/health")
async def health_check():
    """Basic health check endpoint."""
    return {"status": "healthy"}
