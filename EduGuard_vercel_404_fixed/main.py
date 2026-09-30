"""Vercel FastAPI entrypoint for EduGuard.

The frontend is deployed as a Vite service and `/api/*` is routed to this app.
"""
from backend.api import app

__all__ = ["app"]
