"""
Serenity web application: the starting point.

Run it with:
    python main.py
Then open http://localhost:8000 in a browser.
Interactive API docs (great for testing): http://localhost:8000/docs

This file only WIRES THINGS TOGETHER. It:
1. creates the FastAPI app,
2. plugs in the API routes from the api/ folder,
3. serves the HTML/CSS/JS files from the frontend/ folder.
No financial logic belongs here. Alembic migrations own the database schema;
application startup never creates or alters tables.
"""

import os
from pathlib import Path

from fastapi import APIRouter, Depends, FastAPI, Request
from fastapi.responses import FileResponse, JSONResponse, Response
from fastapi.staticfiles import StaticFiles

from api import (
    accounts,
    businesses,
    dashboard,
    dependents,
    export,
    finance,
    income_profiles,
    transactions,
)
from auth import (
    AUTH_COOKIE,
    bearer_token,
    issue_session,
    require_page_session,
    require_session,
    verify_clerk_token,
)

FRONTEND_DIR = Path(__file__).parent / "frontend"


app = FastAPI(title="Serenity", version="0.2.0")

# --- Authentication ---
auth_router = APIRouter(prefix="/serenity-api/auth", tags=["Authentication"])


@auth_router.get("/config")
def auth_config():
    return {"publishable_key": os.getenv("CLERK_PUBLISHABLE_KEY", "")}


@auth_router.post("/session")
def create_session(request: Request):
    token = bearer_token(request)
    identity = verify_clerk_token(token) if token else None
    if identity is None:
        return JSONResponse({"detail": "Valid sign-in required"}, status_code=401)
    response = JSONResponse({"authenticated": True})
    response.set_cookie(
        AUTH_COOKIE,
        issue_session(*identity),
        httponly=True,
        secure=os.getenv("SERENITY_DEV") != "1",
        samesite="lax",
        max_age=12 * 60 * 60,
    )
    return response


@auth_router.delete("/session")
def delete_session():
    response = JSONResponse({"authenticated": False})
    response.delete_cookie(AUTH_COOKIE)
    return response


@auth_router.get("/me", dependencies=[Depends(require_session)])
def auth_me(request: Request):
    return {"user_id": require_session(request)}


app.include_router(auth_router)

# --- API routes (return JSON) ---
for router in (
    accounts.router,
    transactions.router,
    dashboard.router,
    finance.router,
    export.router,
    businesses.router,
    dependents.router,
    income_profiles.router,
):
    app.include_router(router, dependencies=[Depends(require_session)])

# --- Frontend (returns HTML/CSS/JS files) ---
app.mount("/static", StaticFiles(directory=FRONTEND_DIR / "static"), name="static")


@app.get("/", include_in_schema=False)
def dashboard_page(_: str = Depends(require_page_session)):
    return FileResponse(FRONTEND_DIR / "index.html")


@app.get("/accounts", include_in_schema=False)
def accounts_page(_: str = Depends(require_page_session)):
    return FileResponse(FRONTEND_DIR / "accounts.html")


@app.get("/finances", include_in_schema=False)
def finances_page(_: str = Depends(require_page_session)):
    return FileResponse(FRONTEND_DIR / "finances.html")


@app.get("/income", include_in_schema=False)
def income_page(_: str = Depends(require_page_session)):
    return FileResponse(FRONTEND_DIR / "incomes.html")


@app.get("/setup", include_in_schema=False)
def setup_page(_: str = Depends(require_page_session)):
    return FileResponse(FRONTEND_DIR / "setup.html")


@app.get("/sign-in", include_in_schema=False)
def sign_in_page():
    return FileResponse(FRONTEND_DIR / "sign-in.html")


@app.get("/sign-out", include_in_schema=False)
def sign_out_page():
    return FileResponse(FRONTEND_DIR / "sign-out.html")


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
