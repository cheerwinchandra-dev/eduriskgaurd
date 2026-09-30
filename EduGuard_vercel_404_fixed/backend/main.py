"""Vercel/FastAPI service entrypoint for EduGuard.

This module is loaded as ``main:app`` when the Vercel backend service root is
``backend/``.  The repository root is added to ``sys.path`` so the package can
still be imported consistently when running locally or under Vercel.
"""
from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from backend.api import app  # noqa: E402

__all__ = ["app"]
