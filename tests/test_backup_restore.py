"""Disposable, database-native restore rehearsal safety and integrity."""

import json
import os
from pathlib import Path
import sqlite3
import subprocess
import sys

import pytest

from scripts import rehearse_database_restore as rehearsal


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "rehearse_database_restore.py"


def test_sqlite_native_roundtrip_and_owner_scoped_reads():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--backend", "sqlite"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["backend"] == "sqlite"
    assert summary["revision"] == rehearsal.head_revision()
    assert summary["table_rows"]["accounts"] == 4
    assert summary["table_rows"]["transactions"] == 6
    assert summary["table_rows"]["transaction_corrections"] == 4
    assert summary["table_rows"]["income_profiles"] == 2
    assert summary["table_rows"]["reconciliation_approvals"] == 2
    assert summary["table_rows"]["opening_positions"] == 2
    assert summary["table_rows"]["valuation_eligibility"] == 2
    assert summary["table_rows"]["cash_reconciliation_entries"] == 4
    assert summary["table_rows"]["conversion_events"] == 4
    assert summary["owner_balances"] == {
        "rehearsal-owner-a": "163.00", "rehearsal-owner-b": "163.00",
    }
    assert "all_table_rows" in summary["checks"]
    assert "owner_isolation" in summary["checks"]
    assert "income_projections" in summary["checks"]
    assert "correction_history" in summary["checks"]
    assert "conversion_audit_history" in summary["checks"]
    assert "sqlite_integrity_and_foreign_keys" in summary["checks"]
    assert "sqlite://" not in result.stdout


def test_row_mismatch_detected_including_revision_and_history():
    original = {
        "alembic_version": [{"version_num": "0010_income_profiles"}],
        "transaction_corrections": [{"id": 1, "owner_id": "a", "before": {"amount_cents": 200}}],
    }
    tampered = {
        **original,
        "transaction_corrections": [
            {"id": 1, "owner_id": "a", "before": {"amount_cents": 201}}
        ],
    }
    with pytest.raises(rehearsal.RehearsalError, match="transaction_corrections"):
        rehearsal.assert_same(original, tampered)
    with pytest.raises(rehearsal.RehearsalError, match="revision"):
        rehearsal.check_revision({"alembic_version": []}, "0010_income_profiles")
    with pytest.raises(rehearsal.RehearsalError, match="table set"):
        rehearsal.assert_same(original, {"alembic_version": original["alembic_version"]})


def test_ambient_database_url_is_never_used(tmp_path):
    protected = tmp_path / "existing.db"
    protected.write_bytes(b"existing database sentinel; never open")
    url = f"sqlite:///{protected}"
    env = {**os.environ, "DATABASE_URL": url}
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--backend", "sqlite"],
        cwd=ROOT, env=env, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    assert protected.read_bytes() == b"existing database sentinel; never open"
    assert str(protected) not in result.stdout + result.stderr
    assert url not in result.stdout + result.stderr


def test_failed_migration_removes_temporary_resources(monkeypatch, tmp_path):
    created = []
    original = rehearsal.tempfile.TemporaryDirectory

    def directory(*args, **kwargs):
        kwargs["dir"] = tmp_path
        context = original(*args, **kwargs)
        created.append(Path(context.name))
        return context

    def fail(_url):
        assert not any(key.startswith("PG") for key in os.environ)
        raise rehearsal.RehearsalError("synthetic migration failure")

    monkeypatch.setattr(rehearsal.tempfile, "TemporaryDirectory", directory)
    monkeypatch.setattr(rehearsal, "migrate_source", fail)
    monkeypatch.setenv("DATABASE_URL", "sqlite:///should-not-be-used.db")
    monkeypatch.setenv("PGHOST", "untrusted-host")
    monkeypatch.setenv("PGPASSWORD", "sensitive-value")
    with pytest.raises(rehearsal.RehearsalError, match="synthetic migration failure"):
        rehearsal.rehearse("sqlite")
    assert len(created) == 1
    assert not created[0].exists()
    assert os.environ["DATABASE_URL"] == "sqlite:///should-not-be-used.db"
    assert os.environ["PGHOST"] == "untrusted-host"
    assert os.environ["PGPASSWORD"] == "sensitive-value"


def test_postgres_native_roundtrip_when_required():
    if os.getenv("SERENITY_REQUIRE_POSTGRES_RESTORE") != "1":
        pytest.skip("Set SERENITY_REQUIRE_POSTGRES_RESTORE=1 to require PostgreSQL restore")
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--backend", "postgresql"],
        cwd=ROOT, capture_output=True, text=True, timeout=120,
    )
    assert result.returncode == 0, result.stderr
    summary = json.loads(result.stdout)
    assert summary["backend"] == "postgresql"
    assert summary["revision"] == rehearsal.head_revision()
    assert summary["table_rows"]["accounts"] == 4
    assert summary["table_rows"]["transaction_corrections"] == 4
    assert summary["table_rows"]["reconciliation_approvals"] == 2
    assert summary["table_rows"]["opening_positions"] == 2
    assert summary["table_rows"]["valuation_eligibility"] == 2
    assert summary["table_rows"]["cash_reconciliation_entries"] == 4
    assert summary["table_rows"]["conversion_events"] == 4
    assert summary["owner_balances"] == {
        "rehearsal-owner-a": "163.00", "rehearsal-owner-b": "163.00",
    }
    assert "generated_id_sequence" in summary["checks"]
    assert "conversion_audit_history" in summary["checks"]


def test_no_existing_database_location_accepted():
    result = subprocess.run(
        [sys.executable, str(SCRIPT), "--backend", "sqlite",
         "--database-url", "sqlite:///existing.db"],
        cwd=ROOT, capture_output=True, text=True, timeout=15,
    )
    assert result.returncode != 0
    assert not (ROOT / "existing.db").exists()


def test_sqlite_foreign_key_check_rejects_corrupt_backup(tmp_path):
    path = tmp_path / "bad.db"
    with sqlite3.connect(path) as connection:
        connection.execute("CREATE TABLE parent (id INTEGER PRIMARY KEY)")
        connection.execute(
            "CREATE TABLE child (parent_id INTEGER REFERENCES parent(id))"
        )
        connection.execute("INSERT INTO child (parent_id) VALUES (42)")
    with pytest.raises(rehearsal.RehearsalError, match="foreign key"):
        rehearsal.sqlite_integrity(path)


def test_postgres_subprocess_environment_strips_all_ambient_pg_variables(monkeypatch):
    monkeypatch.setenv("PGHOST", "untrusted")
    monkeypatch.setenv("PGPASSWORD", "not-for-rehearsal")
    monkeypatch.setenv("PGSERVICE", "untrusted")
    monkeypatch.setenv("DATABASE_URL", "postgresql://untrusted")
    env = rehearsal.isolated_env("sqlite:////disposable/source.db")
    assert not any(key.startswith("PG") for key in env)
    assert env["DATABASE_URL"] == "sqlite:////disposable/source.db"