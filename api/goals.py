"""Thin authenticated Goal Core routes; business rules live in the service."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import require_session
from schemas.goal import GoalCreate, GoalRead, GoalStatusChange, GoalUpdate
from services import goal_service
from storage.database import get_db

router = APIRouter(prefix="/serenity-api/goals", tags=["Goals"])


def _call(operation, *args):
    try:
        return operation(*args)
    except goal_service.GoalNotFound as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except goal_service.GoalConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


def _read(operation, *args):
    return goal_service.to_goal_read(_call(operation, *args))


@router.get("/options")
def get_goal_options():
    return goal_service.get_goal_options()


@router.post("", response_model=GoalRead, status_code=status.HTTP_201_CREATED)
def create_goal(
    data: GoalCreate, owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _read(goal_service.create_goal, db, data, owner_id)


@router.get("", response_model=list[GoalRead])
def list_goals(
    active_only: bool = True,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return [
        goal_service.to_goal_read(goal)
        for goal in goal_service.list_goals(db, owner_id, active_only=active_only)
    ]


@router.get("/{goal_id}", response_model=GoalRead)
def get_goal(
    goal_id: int, owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    goal = goal_service.get_goal(db, goal_id, owner_id)
    if goal is None:
        raise HTTPException(status_code=404, detail="Goal not found")
    return goal_service.to_goal_read(goal)


@router.put("/{goal_id}", response_model=GoalRead)
def update_goal(
    goal_id: int, data: GoalUpdate,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _read(goal_service.update_goal, db, goal_id, data, owner_id)


@router.delete("/{goal_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal(
    goal_id: int, owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    _call(goal_service.delete_goal, db, goal_id, owner_id)


@router.post("/{goal_id}/deactivate", response_model=GoalRead)
def deactivate_goal(
    goal_id: int, owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _read(goal_service.set_goal_active, db, goal_id, False, owner_id)


@router.post("/{goal_id}/reactivate", response_model=GoalRead)
def reactivate_goal(
    goal_id: int, owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _read(goal_service.set_goal_active, db, goal_id, True, owner_id)


@router.post("/{goal_id}/status", response_model=GoalRead)
def change_goal_status(
    goal_id: int, data: GoalStatusChange,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _read(goal_service.change_goal_status, db, goal_id, data.status, owner_id)