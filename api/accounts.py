"""
Account API routes (the URLs the frontend calls).

    POST /api/accounts          create an account
    GET  /api/accounts          list all accounts
    GET  /api/accounts/options  allowed account types and classifications
    GET  /api/accounts/{id}     get one account

Routes stay thin on purpose: receive the request, call the service,
return the result. No financial logic lives here.

`db: Session = Depends(get_db)` is FastAPI "dependency injection": it
calls get_db() for us and passes the session in as `db`.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from schemas.account import AccountCreate, AccountRead
from services import account_service
from storage.database import get_db
from utils.choices import ACCOUNT_CLASSIFICATIONS, ACCOUNT_TYPES

router = APIRouter(prefix="/api/accounts", tags=["Accounts"])


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account(data: AccountCreate, db: Session = Depends(get_db)):
    # By the time we get here, FastAPI has already validated `data`
    # using AccountCreate. Invalid input never reaches this line.
    account = account_service.create_account(db, data)
    return account_service.to_account_read(account)


@router.get("", response_model=list[AccountRead])
def list_accounts(db: Session = Depends(get_db)):
    accounts = account_service.list_accounts(db)
    return [account_service.to_account_read(account) for account in accounts]


# This route must be defined BEFORE "/{account_id}". Otherwise FastAPI
# would try to read the word "options" as an account id.
@router.get("/options")
def get_account_options():
    """Lets the frontend build its dropdowns from the backend's lists."""
    return {
        "account_types": ACCOUNT_TYPES,
        "classifications": ACCOUNT_CLASSIFICATIONS,
    }


@router.get("/{account_id}", response_model=AccountRead)
def get_account(account_id: int, db: Session = Depends(get_db)):
    account = account_service.get_account(db, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return account_service.to_account_read(account)
