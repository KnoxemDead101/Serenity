"""Authenticated routes for goal items, milestones, and checkpoints."""

from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from auth import require_session
from schemas.goal_composition import (
    GoalCheckpointCreate, GoalCheckpointRead, GoalCheckpointUpdate,
    GoalCompositionRead, GoalItemCreate, GoalItemRead, GoalItemStatusChange,
    GoalItemUpdate, GoalMilestoneCreate, GoalMilestoneRead,
    GoalMilestoneStatusChange, GoalMilestoneUpdate,
)
from services import goal_composition_service as service
from services import goal_service
from storage.database import get_db

router = APIRouter(prefix="/serenity-api/goals", tags=["Goal Composition"])


def _call(operation, *args):
    try:
        return operation(*args)
    except (goal_service.GoalNotFound, service.CompositionNotFound) as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except goal_service.GoalConflict as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/composition/options")
def get_composition_options():
    return service.get_composition_options()


@router.get("/{goal_id}/composition", response_model=GoalCompositionRead)
def get_goal_composition(
    goal_id: int, active_only: bool = True,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _call(service.get_goal_composition, db, goal_id, owner_id, active_only)


@router.get("/{goal_id}/items", response_model=list[GoalItemRead])
def list_goal_items(
    goal_id: int, active_only: bool = True,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _call(service.list_goal_items, db, goal_id, owner_id, active_only)


@router.post(
    "/{goal_id}/items", response_model=GoalItemRead,
    status_code=status.HTTP_201_CREATED,
)
def create_goal_item(
    goal_id: int, data: GoalItemCreate,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _call(service.create_goal_item, db, goal_id, data, owner_id)


@router.get("/{goal_id}/items/{record_id}", response_model=GoalItemRead)
def get_goal_item(
    goal_id: int, record_id: int,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _call(service.get_goal_item, db, goal_id, record_id, owner_id)


@router.put("/{goal_id}/items/{record_id}", response_model=GoalItemRead)
def update_goal_item(
    goal_id: int, record_id: int, data: GoalItemUpdate,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _call(service.update_goal_item, db, goal_id, record_id, data, owner_id)


@router.delete("/{goal_id}/items/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal_item(
    goal_id: int, record_id: int,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    _call(service.delete_goal_item, db, goal_id, record_id, owner_id)


@router.post("/{goal_id}/items/{record_id}/status", response_model=GoalItemRead)
def change_goal_item_status(
    goal_id: int, record_id: int, data: GoalItemStatusChange,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _call(service.change_goal_item_status, db, goal_id, record_id, data.status, owner_id)


@router.post("/{goal_id}/items/{record_id}/deactivate", response_model=GoalItemRead)
def deactivate_goal_item(
    goal_id: int, record_id: int,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _call(service.set_goal_item_active, db, goal_id, record_id, False, owner_id)


@router.post("/{goal_id}/items/{record_id}/reactivate", response_model=GoalItemRead)
def reactivate_goal_item(
    goal_id: int, record_id: int,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _call(service.set_goal_item_active, db, goal_id, record_id, True, owner_id)


@router.get("/{goal_id}/milestones", response_model=list[GoalMilestoneRead])
def list_goal_milestones(
    goal_id: int,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _call(service.list_goal_milestones, db, goal_id, owner_id)


@router.post(
    "/{goal_id}/milestones", response_model=GoalMilestoneRead,
    status_code=status.HTTP_201_CREATED,
)
def create_goal_milestone(
    goal_id: int, data: GoalMilestoneCreate,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _call(service.create_goal_milestone, db, goal_id, data, owner_id)


@router.get("/{goal_id}/milestones/{record_id}", response_model=GoalMilestoneRead)
def get_goal_milestone(
    goal_id: int, record_id: int,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _call(service.get_goal_milestone, db, goal_id, record_id, owner_id)


@router.put("/{goal_id}/milestones/{record_id}", response_model=GoalMilestoneRead)
def update_goal_milestone(
    goal_id: int, record_id: int, data: GoalMilestoneUpdate,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _call(service.update_goal_milestone, db, goal_id, record_id, data, owner_id)


@router.delete("/{goal_id}/milestones/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal_milestone(
    goal_id: int, record_id: int,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    _call(service.delete_goal_milestone, db, goal_id, record_id, owner_id)


@router.post("/{goal_id}/milestones/{record_id}/status", response_model=GoalMilestoneRead)
def change_goal_milestone_status(
    goal_id: int, record_id: int, data: GoalMilestoneStatusChange,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _call(service.change_goal_milestone_status, db, goal_id, record_id, data.status, owner_id)


@router.get("/{goal_id}/checkpoints", response_model=list[GoalCheckpointRead])
def list_goal_checkpoints(
    goal_id: int,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _call(service.list_goal_checkpoints, db, goal_id, owner_id)


@router.post(
    "/{goal_id}/checkpoints", response_model=GoalCheckpointRead,
    status_code=status.HTTP_201_CREATED,
)
def create_goal_checkpoint(
    goal_id: int, data: GoalCheckpointCreate,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _call(service.create_goal_checkpoint, db, goal_id, data, owner_id)


@router.get("/{goal_id}/checkpoints/{record_id}", response_model=GoalCheckpointRead)
def get_goal_checkpoint(
    goal_id: int, record_id: int,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _call(service.get_goal_checkpoint, db, goal_id, record_id, owner_id)


@router.put("/{goal_id}/checkpoints/{record_id}", response_model=GoalCheckpointRead)
def update_goal_checkpoint(
    goal_id: int, record_id: int, data: GoalCheckpointUpdate,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    return _call(service.update_goal_checkpoint, db, goal_id, record_id, data, owner_id)


@router.delete("/{goal_id}/checkpoints/{record_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_goal_checkpoint(
    goal_id: int, record_id: int,
    owner_id: str = Depends(require_session), db: Session = Depends(get_db),
):
    _call(service.delete_goal_checkpoint, db, goal_id, record_id, owner_id)