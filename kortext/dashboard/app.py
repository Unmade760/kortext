"""
Kortext web dashboard: local observability and interactive graph explorer.
Concise, declarative FastAPI application entry point (<250 lines).
Port :8004 (configurable via DASHBOARD_PORT).
"""

import os
from pathlib import Path

import uvicorn
from dotenv import load_dotenv
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse
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

app = FastAPI(title="Kortext Dashboard", version="1.0.0")

STATIC_DIR.mkdir(parents=True, exist_ok=True)
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

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
    """CLI and daemon entry point."""
    uvicorn.run("kortext.dashboard.app:app", host="0.0.0.0", port=DASHBOARD_PORT, reload=False)


if __name__ == "__main__":
    main()
