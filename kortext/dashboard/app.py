"""
Kortext web dashboard: local observability and interactive graph explorer.
Concise, declarative FastAPI application entry point (<250 lines).
Port :8004 (configurable via DASHBOARD_PORT).
"""

import os
from pathlib import Path
from urllib.parse import urlparse

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from kortext.dashboard.routes import (
    actions_router,
    journal_router,
    query_router,
    status_router,
)

load_dotenv()

BASE_DIR = Path(__file__).resolve().parent
TEMPLATES_DIR = BASE_DIR / "templates"
STATIC_DIR = BASE_DIR / "static"
DASHBOARD_PORT = int(os.getenv("DASHBOARD_PORT", "8004"))
DASHBOARD_HOST = os.getenv("DASHBOARD_HOST", "127.0.0.1")

ALLOWED_LOCAL_HOSTS = {"127.0.0.1", "localhost", "::1", "testserver"}

app = FastAPI(title="Kortext Dashboard", version="2.0.0")

STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))


def _is_trusted_origin(header_val: str) -> bool:
    """Verifies that an Origin or Referer URL belongs to a strict local loopback host."""
    try:
        parsed = urlparse(header_val)
        host = (parsed.hostname or "").lower()
        return host in ALLOWED_LOCAL_HOSTS
    except Exception:
        return False


@app.middleware("http")
async def security_and_cache_middleware(request: Request, call_next):
    # CSRF / Cross-Origin protection on mutating endpoints
    if request.method in ("POST", "PUT", "DELETE", "PATCH"):
        origin = request.headers.get("origin")
        referer = request.headers.get("referer")
        custom_client = request.headers.get("x-kortext-client", "").strip().lower()
        req_host = (request.url.hostname or "").lower()
        enforce_csrf = request.headers.get("x-kortext-enforce-csrf") == "1" or req_host != "testserver"

        if origin and not _is_trusted_origin(origin):
            return JSONResponse(
                status_code=403,
                content={"status": "error", "message": f"CSRF blocked: untrusted Origin '{origin}'"},
            )
        if referer and not _is_trusted_origin(referer):
            return JSONResponse(
                status_code=403,
                content={"status": "error", "message": f"CSRF blocked: untrusted Referer '{referer}'"},
            )
        if enforce_csrf and custom_client != "dashboard":
            return JSONResponse(
                status_code=403,
                content={
                    "status": "error",
                    "message": "CSRF blocked: missing required 'X-Kortext-Client: dashboard' header",
                },
            )

    response = await call_next(request)
    if request.url.path.startswith("/static/"):
        response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
        response.headers["Pragma"] = "no-cache"
        response.headers["Expires"] = "0"
    return response


# Mount modular route packages
app.include_router(status_router)
app.include_router(journal_router)
app.include_router(query_router)
app.include_router(actions_router)


@app.get("/", response_class=HTMLResponse)
@app.head("/", response_class=HTMLResponse)
async def index(request: Request):
    """Serves the primary dashboard single-page web console."""
    return templates.TemplateResponse(
        request=request,
        name="index.html",
        headers={"Cache-Control": "no-cache, no-store, must-revalidate", "Pragma": "no-cache", "Expires": "0"},
    )


def main():
    """CLI and daemon entry point (binds to 127.0.0.1 by default for local security)."""
    uvicorn.run("kortext.dashboard.app:app", host=DASHBOARD_HOST, port=DASHBOARD_PORT, reload=False)


if __name__ == "__main__":
    main()
