"""Map a verified provider, issuer and subject to an owned Serenity workspace."""

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from models.account import utc_now
from models.identity import AuthIdentity, SerenityUser, Workspace, EXTERNAL_ID_MAX_LENGTH, PROVIDER_MAX_LENGTH

CLERK_PROVIDER = "clerk"


class IdentityError(ValueError):
    pass


class InactiveUserError(PermissionError):
    pass


def _part(value: str, name: str, limit: int) -> str:
    if not isinstance(value, str) or not value.strip() or len(value) > limit:
        raise IdentityError(f"Invalid {name}")
    return value


def _lookup(db: Session, provider: str, issuer: str, subject: str):
    return db.execute(
        select(Workspace.id, SerenityUser.active, AuthIdentity)
        .join(SerenityUser, Workspace.owner_user_id == SerenityUser.id)
        .join(AuthIdentity, AuthIdentity.user_id == SerenityUser.id)
        .where(AuthIdentity.provider == provider, AuthIdentity.issuer == issuer,
               AuthIdentity.subject == subject)
    ).one_or_none()


def workspace_for_identity(
    db: Session, *, provider: str, issuer: str, subject: str,
    record_sign_in: bool = False,
) -> str:
    provider = _part(provider, "provider", PROVIDER_MAX_LENGTH)
    issuer = _part(issuer, "issuer", EXTERNAL_ID_MAX_LENGTH)
    subject = _part(subject, "subject", EXTERNAL_ID_MAX_LENGTH)
    found = _lookup(db, provider, issuer, subject)
    if found is None:
        try:
            user = SerenityUser()
            db.add(user)
            db.flush()
            db.add(Workspace(owner_user_id=user.id, name="Primary"))
            db.add(AuthIdentity(user_id=user.id, provider=provider, issuer=issuer,
                                subject=subject))
            db.commit()
        except IntegrityError:
            db.rollback()
        found = _lookup(db, provider, issuer, subject)
        if found is None:
            raise IdentityError("Identity could not be provisioned")
    workspace_id, active, identity = found
    if not active:
        raise InactiveUserError("Account deactivated")
    if record_sign_in:
        identity.last_sign_in_at = utc_now()
        db.commit()
    return workspace_id


def set_user_active(db: Session, user_id: str, active: bool) -> SerenityUser:
    user = db.get(SerenityUser, user_id)
    if user is None:
        raise IdentityError("Unknown user")
    user.active = active
    db.commit()
    return user