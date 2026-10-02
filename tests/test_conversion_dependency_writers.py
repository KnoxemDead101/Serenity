"""Synthetic guards for writes to owner-wide conversion dependencies."""

from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker

from models.business import Business
from models.dependent import Dependent
from models.income_profile import IncomeProfile
from schemas.business import BusinessCreate, BusinessUpdate
from schemas.dependent import DependentCreate, DependentUpdate
from schemas.income_profile import IncomeProfileCreate
from services import business_service, dependent_service, income_profile_service
from services.financial_write_lock import lock_owner_financial_writes
from storage.database import Base


OWNER_ID = "synthetic-conversion-owner"


def _income(name: str, *, notes: str | None = None) -> IncomeProfileCreate:
    return IncomeProfileCreate(
        name=name,
        income_type="Salary",
        pay_frequency="Annual",
        annual_salary="50000.00",
        notes=notes,
    )


def test_dependency_creates_lock_before_name_checks(db, monkeypatch):
    events = []

    for service in (business_service, dependent_service, income_profile_service):
        original_lock = service.lock_owner_financial_writes

        def recording_lock(session, owner_id, *, original=original_lock):
            events.append("lock")
            original(session, owner_id)

        monkeypatch.setattr(service, "lock_owner_financial_writes", recording_lock)

    original_business_check = business_service._check_name_free
    original_dependent_check = dependent_service._check_name_free

    def business_check(*args, **kwargs):
        events.append("business dependency read")
        return original_business_check(*args, **kwargs)

    def dependent_check(*args, **kwargs):
        events.append("dependent dependency read")
        return original_dependent_check(*args, **kwargs)

    monkeypatch.setattr(business_service, "_check_name_free", business_check)
    monkeypatch.setattr(dependent_service, "_check_name_free", dependent_check)

    business_service.create_business(db, BusinessCreate(name="Synthetic business"), OWNER_ID)
    dependent_service.create_dependent(db, DependentCreate(display_name="Synthetic dependent"), OWNER_ID)
    income_profile_service.create_income_profile(db, _income("Synthetic income"), OWNER_ID)

    assert events == [
        "lock",
        "business dependency read",
        "lock",
        "dependent dependency read",
        "lock",
    ]


def _assert_stale_instance_is_refreshed(
    tmp_path, monkeypatch, *, model, create, mutate_in_other_session, write, expected_note
):
    engine = create_engine(f"sqlite:///{tmp_path / 'dependency-writer.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    lock_owners = []
    original_lock = lock_owner_financial_writes

    def recording_lock(db, owner_id):
        lock_owners.append(owner_id)
        original_lock(db, owner_id)

    try:
        with sessions() as setup:
            record = create(setup)
            record_id = record.id
            setup.commit()

        stale_session = sessions()
        stale = stale_session.get(model, record_id)
        assert stale is not None

        with sessions.begin() as concurrent:
            mutate_in_other_session(concurrent, concurrent.get(model, record_id))

        # The object in stale_session still contains the pre-update value.
        assert stale.notes != expected_note
        monkeypatch.setattr(
            _service_for_model(model), "lock_owner_financial_writes", recording_lock
        )
        refreshed = write(stale_session, stale)
        assert refreshed.notes == expected_note
        assert lock_owners == [OWNER_ID]
        stale_session.close()
    finally:
        engine.dispose()


def _assert_stale_update_preserves_lifecycle(
    tmp_path, monkeypatch, *, model, create, deactivate_elsewhere, update
):
    engine = create_engine(f"sqlite:///{tmp_path / 'dependency-update.db'}")
    Base.metadata.create_all(engine)
    sessions = sessionmaker(bind=engine, expire_on_commit=False)
    lock_owners = []

    def recording_lock(db, owner_id):
        lock_owners.append(owner_id)
        lock_owner_financial_writes(db, owner_id)

    try:
        with sessions() as setup:
            record = create(setup)
            record_id = record.id
            setup.commit()

        stale_session = sessions()
        stale = stale_session.get(model, record_id)
        assert stale is not None and stale.active is True
        with sessions.begin() as concurrent:
            deactivate_elsewhere(concurrent, concurrent.get(model, record_id))

        monkeypatch.setattr(
            _service_for_model(model), "lock_owner_financial_writes", recording_lock
        )
        updated = update(stale_session, stale)
        assert updated.active is False
        assert lock_owners == [OWNER_ID]
        stale_session.close()
    finally:
        engine.dispose()


def _service_for_model(model):
    if model is Business:
        return business_service
    if model is Dependent:
        return dependent_service
    return income_profile_service


def test_business_and_dependent_lifecycle_writers_refresh_rows(tmp_path, monkeypatch):
    _assert_stale_instance_is_refreshed(
        tmp_path,
        monkeypatch,
        model=Business,
        create=lambda db: business_service.create_business(
            db, BusinessCreate(name="Business", notes="original"), OWNER_ID
        ),
        mutate_in_other_session=lambda db, row: setattr(row, "notes", "latest"),
        write=lambda db, row: business_service.set_business_active(db, row, False),
        expected_note="latest",
    )
    _assert_stale_instance_is_refreshed(
        tmp_path,
        monkeypatch,
        model=Dependent,
        create=lambda db: dependent_service.create_dependent(
            db, DependentCreate(display_name="Dependent", notes="original"), OWNER_ID
        ),
        mutate_in_other_session=lambda db, row: setattr(row, "notes", "latest"),
        write=lambda db, row: dependent_service.set_dependent_active(db, row, False),
        expected_note="latest",
    )


def test_income_profile_lifecycle_writer_refreshes_rows(tmp_path, monkeypatch):
    _assert_stale_instance_is_refreshed(
        tmp_path,
        monkeypatch,
        model=IncomeProfile,
        create=lambda db: income_profile_service.create_income_profile(
            db, _income("Income", notes="original"), OWNER_ID
        ),
        mutate_in_other_session=lambda db, row: setattr(row, "notes", "latest"),
        write=lambda db, row: income_profile_service.set_income_profile_active(
            db, row, False
        ),
        expected_note="latest",
    )


def test_update_writers_preserve_current_lifecycle_state(tmp_path, monkeypatch):
    _assert_stale_update_preserves_lifecycle(
        tmp_path,
        monkeypatch,
        model=Business,
        create=lambda db: business_service.create_business(
            db, BusinessCreate(name="Business", notes="original"), OWNER_ID
        ),
        deactivate_elsewhere=lambda db, row: setattr(row, "active", False),
        update=lambda db, row: business_service.update_business(
            db, row, BusinessUpdate(name="Updated business", notes="updated")
        ),
    )
    _assert_stale_update_preserves_lifecycle(
        tmp_path,
        monkeypatch,
        model=Dependent,
        create=lambda db: dependent_service.create_dependent(
            db, DependentCreate(display_name="Dependent", notes="original"), OWNER_ID
        ),
        deactivate_elsewhere=lambda db, row: setattr(row, "active", False),
        update=lambda db, row: dependent_service.update_dependent(
            db, row, DependentUpdate(display_name="Updated dependent", notes="updated")
        ),
    )
    _assert_stale_update_preserves_lifecycle(
        tmp_path,
        monkeypatch,
        model=IncomeProfile,
        create=lambda db: income_profile_service.create_income_profile(
            db, _income("Income", notes="original"), OWNER_ID
        ),
        deactivate_elsewhere=lambda db, row: setattr(row, "active", False),
        update=lambda db, row: income_profile_service.update_income_profile(
            db, row, _income("Updated income", notes="updated")
        ),
    )