from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from models.account import Account
from schemas.transaction import TransactionCorrectionRead, TransactionCreate, TransactionRead, TransactionUpdate
from services import account_service, transaction_service
from storage.database import get_db
from utils.choices import ACCOUNT_CLASSIFICATIONS, TRANSACTION_CATEGORIES, TRANSACTION_TYPES

router = APIRouter(prefix="/serenity-api", tags=["Transactions"])


def _require_account(db: Session, account_id: int) -> Account:
    account = account_service.get_account(db, account_id)
    if account is None:
        raise HTTPException(status_code=404, detail="Account not found")
    return account


@router.get("/transactions/options")
def get_transaction_options():
    return {"transaction_types": TRANSACTION_TYPES, "classifications": ACCOUNT_CLASSIFICATIONS,
            "categories": TRANSACTION_CATEGORIES}


@router.post("/accounts/{account_id}/transactions", response_model=TransactionRead,
             status_code=status.HTTP_201_CREATED)
def create_transaction(account_id: int, data: TransactionCreate, db: Session = Depends(get_db)):
    return transaction_service.to_transaction_read(
        transaction_service.create_transaction(db, _require_account(db, account_id), data)
    )


@router.get("/accounts/{account_id}/transactions", response_model=list[TransactionRead])
def list_transactions(account_id: int, db: Session = Depends(get_db)):
    _require_account(db, account_id)
    return [transaction_service.to_transaction_read(t)
            for t in transaction_service.list_transactions(db, account_id)]


@router.get("/accounts/{account_id}/transaction-corrections",
             response_model=list[TransactionCorrectionRead])
def list_transaction_corrections(account_id: int, db: Session = Depends(get_db)):
    _require_account(db, account_id)
    return [transaction_service.to_correction_read(c)
            for c in transaction_service.list_corrections(db, account_id)]


@router.put("/accounts/{account_id}/transactions/{transaction_id}", response_model=TransactionRead)
def update_transaction(account_id: int, transaction_id: int, data: TransactionUpdate,
                       db: Session = Depends(get_db)):
    transaction = transaction_service.get_transaction(db, account_id, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    return transaction_service.to_transaction_read(
        transaction_service.update_transaction(db, transaction, data)
    )


@router.delete("/accounts/{account_id}/transactions/{transaction_id}",
               status_code=status.HTTP_204_NO_CONTENT)
def delete_transaction(account_id: int, transaction_id: int, db: Session = Depends(get_db)):
    transaction = transaction_service.get_transaction(db, account_id, transaction_id)
    if transaction is None:
        raise HTTPException(status_code=404, detail="Transaction not found")
    transaction_service.delete_transaction(db, transaction)