"""
Serenity web application: the starting point.

Run it with:
    python main.py
Then open http://localhost:8000 in a browser.
Interactive API docs (great for testing): http://localhost:8000/docs

This file only WIRES THINGS TOGETHER. It:
1. creates the FastAPI app,
2. makes sure the database tables exist when the app starts,
3. plugs in the API routes from the api/ folder,
4. serves the HTML/CSS/JS files from the frontend/ folder.
No financial logic belongs here.
"""

import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from api import accounts, dashboard
from storage.database import init_db

FRONTEND_DIR = Path(__file__).parent / "frontend"


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Code before `yield` runs once when the server starts.
    init_db()
    yield
    # Code after `yield` would run when the server shuts down.


app = FastAPI(title="Serenity", version="0.1.0", lifespan=lifespan)

# --- API routes (return JSON) ---
app.include_router(accounts.router)
app.include_router(dashboard.router)

# --- Frontend (returns HTML/CSS/JS files) ---
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
def dashboard_page():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/accounts", include_in_schema=False)
def accounts_page():
    return FileResponse(FRONTEND_DIR / "accounts.html")


if __name__ == "__main__":
    import uvicorn

    # 0.0.0.0 lets Replit (and other machines) reach the server.
    # Replit sets the PORT environment variable; locally we default to 8000.
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run("main:app", host="0.0.0.0", port=port, reload=True)
