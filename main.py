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
from pathlib import Path

from fastapi import FastAPI
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from api import accounts, dashboard, finance, transactions

FRONTEND_DIR = Path(__file__).parent / "frontend"


app = FastAPI(title="Serenity", version="0.2.0")

# --- API routes (return JSON) ---
app.include_router(accounts.router)
app.include_router(transactions.router)
app.include_router(dashboard.router)
app.include_router(finance.router)

# --- Frontend (returns HTML/CSS/JS files) ---
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
def dashboard_page():
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/accounts", include_in_schema=False)
def accounts_page():
    return FileResponse(FRONTEND_DIR / "accounts.html")


@app.get("/finances", include_in_schema=False)
def finances_page():
    return FileResponse(FRONTEND_DIR / "finances.html")


@app.get("/favicon.ico", include_in_schema=False)
def favicon():
    return Response(status_code=204)


if __name__ == "__main__":
    import uvicorn

    # 0.0.0.0 lets Replit (and other machines) reach the server.
    # Replit sets the PORT environment variable; locally we default to 8000.
    port = int(os.getenv("PORT", "8000"))
    uvicorn.run(
        "main:app",
        host="0.0.0.0",
        port=port,
        reload=os.getenv("SERENITY_DEV") == "1",
    )
