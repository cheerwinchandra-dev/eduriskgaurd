"""EduGuard backend entry point.

Run locally from the project root:  python -m uvicorn backend.api:app --host 127.0.0.1 --port 8765
For Vercel, backend/main.py exposes the same FastAPI app as the `backend` service entrypoint.
"""
import hmac
import json
import os
import threading
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .router import router, state
from .utilities import bootstrap
from .utilities.common import clean, get_logger, load_config

log = get_logger("api")


class SafeJSON(JSONResponse):
    """JSON that never emits NaN (browsers reject it)."""

    def render(self, content) -> bytes:
        return json.dumps(clean(content), ensure_ascii=False, allow_nan=False, separators=(",", ":")).encode("utf-8")


def _boot():
    try:
        state["message"] = "Preparing student data and the risk model..."
        bootstrap.ensure_ready()
        state["ready"] = True
        state["message"] = "Ready"
        log.info("EduGuard backend is ready")
    except Exception as exc:  # surfaced to the UI instead of crashing silently
        log.exception("Start-up failed")
        state["error"] = f"Start-up failed: {exc}"


@asynccontextmanager
async def lifespan(app):
    threading.Thread(target=_boot, daemon=True).start()
    yield


cfg = load_config()
app = FastAPI(title=cfg["app_name"], version=cfg["version"], default_response_class=SafeJSON, lifespan=lifespan)


@app.middleware("http")
async def require_session_token(request: Request, call_next):
    """Electron gives the backend a random token; anything without it (for example a web page in a browser) is refused."""
    # Electron uses a per-session header. Web deployments are already same-origin behind Vercel,
    # so they use the normal application session token without requiring the desktop-only header.
    token = os.environ.get("EDUGUARD_TOKEN")
    if token and request.method != "OPTIONS" and request.url.path != "/api/health":
        supplied = request.headers.get("x-eduguard-token", "")
        if not hmac.compare_digest(supplied.encode(), token.encode()):
            return JSONResponse({"detail": "Unauthorized"}, status_code=401)
    return await call_next(request)


# Added last so it is the outermost layer and answers browser pre-flight requests before the token check.
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"],
                   expose_headers=["Content-Disposition"])
app.include_router(router)

if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host=cfg["host"], port=cfg["port"], log_level="warning")
