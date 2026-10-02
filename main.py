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
from sqlalchemy.orm import Session

from api import (
    accounts,
    businesses,
    conversions,
    dashboard,
    dependents,
    export,
    finance,
    goal_composition,
    goals,
    income_profiles,
    instruments,
    portfolios,
    reconciliation,
    transactions,
)
from auth import (
    AUTH_COOKIE,
    bearer_token,
    ClerkUnavailableError,
    configured_clerk_issuer,
    current_user,
    issue_session,
    require_page_session,
    require_session,
    verify_clerk_token,
)
from services import identity_service
from services.write_safety import MESSAGE, WritesPaused, require_safe_write, write_state
from storage.database import get_db

FRONTEND_DIR = Path(__file__).parent / "frontend"


app = FastAPI(title="Serenity", version="0.2.0")

# --- Authentication ---
auth_router = APIRouter(prefix="/serenity-api/auth", tags=["Authentication"])


@auth_router.get("/config")
def auth_config():
    return {"publishable_key": os.getenv("CLERK_PUBLISHABLE_KEY", "")}


@auth_router.post("/session")
def create_session(request: Request, db: Session = Depends(get_db)):
    token = bearer_token(request)
    try:
        if token:
            configured_clerk_issuer()
        identity = verify_clerk_token(token) if token else None
    except ClerkUnavailableError:
        return JSONResponse({"detail": "Sign-in is temporarily unavailable"}, status_code=503)
    if identity is None:
        return JSONResponse({"detail": "Valid sign-in required"}, status_code=401)
    clerk_user_id, clerk_session_id = identity
    try:
        identity_service.workspace_for_identity(
            db, provider=identity_service.CLERK_PROVIDER,
            issuer=configured_clerk_issuer(), subject=clerk_user_id, record_sign_in=True,
        )
    except ClerkUnavailableError:
        return JSONResponse({"detail": "Sign-in is temporarily unavailable"}, status_code=503)
    except identity_service.InactiveUserError:
        return JSONResponse(
            {"detail": "This Serenity account has been deactivated"}, status_code=403,
            headers={"X-Serenity-Account-Status": "inactive"},
        )
    except identity_service.IdentityError:
        return JSONResponse({"detail": "Valid sign-in required"}, status_code=401)
    response = JSONResponse({"authenticated": True})
    response.set_cookie(
        AUTH_COOKIE,
        issue_session(clerk_user_id, clerk_session_id),
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


@auth_router.get("/me")
def auth_me(request: Request, workspace_id: str = Depends(require_session)):
    return {"user_id": current_user(request), "workspace_id": workspace_id}


app.include_router(auth_router)


@app.exception_handler(WritesPaused)
async def writes_paused_response(request: Request, error: WritesPaused):
    return JSONResponse(
        {"detail": MESSAGE, "code": "SERENITY_READ_ONLY"}, status_code=503,
        headers={"Cache-Control": "no-store", "Retry-After": "60"},
    )


def protect_api_writes(request: Request, db: Session = Depends(get_db)):
    if request.method in ("POST", "PUT", "PATCH", "DELETE"):
        require_safe_write(db)


@app.get("/serenity-api/system/write-safety")
def financial_write_safety(
    _: str = Depends(require_session), db: Session = Depends(get_db),
):
    state = write_state(db.connection())
    return JSONResponse(
        {"state": state, "writes_enabled": state == "NORMAL",
         "message": MESSAGE if state != "NORMAL" else None},
        headers={"Cache-Control": "no-store"},
    )

# --- API routes (return JSON) ---
for router in (
    accounts.router,
    transactions.router,
    dashboard.router,
    finance.router,
    goal_composition.router,
    goals.router,
    export.router,
    businesses.router,
    dependents.router,
    income_profiles.router,
    instruments.router,
    portfolios.router,
    reconciliation.router,
    conversions.router,
):
    app.include_router(
        router, dependencies=[Depends(require_session), Depends(protect_api_writes)],
    )

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


@app.get("/profit-engine", include_in_schema=False)
def profit_engine_page(_: str = Depends(require_page_session)):
    return FileResponse(FRONTEND_DIR / "profit_engine.html")


@app.get("/portfolios", include_in_schema=False)
def portfolios_page(_: str = Depends(require_page_session)):
    return FileResponse(FRONTEND_DIR / "portfolios.html")


@app.get("/goals", include_in_schema=False)
def goals_page(_: str = Depends(require_page_session)):
    return FileResponse(FRONTEND_DIR / "goals.html")


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

@app.middleware("http")
async def private_conversion_responses(request: Request, call_next):
    response = await call_next(request)
    if request.url.path.startswith((
        "/serenity-api/conversions", "/serenity-api/reconciliation",
    )):
        # Include authentication, validation and conflict responses, not only
        # successful evidence downloads.
        response.headers["Cache-Control"] = "no-store"
    return response
