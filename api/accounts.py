"""
Account API routes (the URLs the frontend calls).

    POST /serenity-api/accounts          create an account
    GET  /serenity-api/accounts          list all accounts
    GET  /serenity-api/accounts/options  allowed account types and classifications
    GET  /serenity-api/accounts/{id}     get one account
    PUT  /serenity-api/accounts/{id}/transactions/{transaction_id}
    DELETE /serenity-api/accounts/{id}/transactions/{transaction_id}

Routes stay thin on purpose: receive the request, call the service,
return the result. No financial logic lives here.

`db: Session = Depends(get_db)` is FastAPI "dependency injection": it
calls get_db() for us and passes the session in as `db`.
"""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import require_session
from models.account import Account
from schemas.account import AccountCreate, AccountRead, AccountUpdate
from services import account_service
from storage.database import get_db
from utils.choices import ACCOUNT_CLASSIFICATIONS, ACCOUNT_TYPES

router = APIRouter(prefix="/serenity-api/accounts", tags=["Accounts"])


def _require_account(db: Session, account_id: int, owner_id: str) -> Account:
    account = account_service.get_account(db, account_id, owner_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.post("", response_model=AccountRead, status_code=status.HTTP_201_CREATED)
def create_account(
    data: AccountCreate,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    # By the time we get here, FastAPI has already validated `data`
    # using AccountCreate. Invalid input never reaches this line.
    account = account_service.create_account(db, data, user_id)
    return account_service.to_account_read(account)


@router.get("", response_model=list[AccountRead])
def list_accounts(
    user_id: str = Depends(require_session), db: Session = Depends(get_db)
):
    accounts = account_service.list_accounts(db, user_id)
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
def get_account(
    account_id: int,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    return account_service.to_account_read(_require_account(db, account_id, user_id))


@router.put("/{account_id}", response_model=AccountRead)
def update_account(
    account_id: int,
    data: AccountUpdate,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    account = account_service.update_account(
        db, _require_account(db, account_id, user_id), data
    )
    return account_service.to_account_read(account)


@router.post("/{account_id}/deactivate", response_model=AccountRead)
def deactivate_account(
    account_id: int,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    account = account_service.set_account_active(
        db, _require_account(db, account_id, user_id), False
    )
    return account_service.to_account_read(account)


@router.post("/{account_id}/reactivate", response_model=AccountRead)
def reactivate_account(
    account_id: int,
    user_id: str = Depends(require_session),
    db: Session = Depends(get_db),
):
    account = account_service.set_account_active(
        db, _require_account(db, account_id, user_id), True
    )
    return account_service.to_account_read(account)
