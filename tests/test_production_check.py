"""The pre-publish database ownership report is read-only and count-only."""

import os
from pathlib import Path
import sqlite3
import subprocess
import sys
import pytest

from test_migrations import run_alembic

SCRIPT = str(Path(__file__).resolve().parents[1] / "scripts" / "check_production_rows.py")


def run_check(database_path):
    env = {**os.environ, "SERENITY_CHECK_DATABASE_URL": f"sqlite:///{database_path}",
           "SERENITY_DEV": "0",
           "SERENITY_CHECK_PUBLISHED_ORIGIN": "https://serenity.example.com",
           "SERENITY_AUTHORIZED_PARTIES": "https://serenity.example.com"}
    return subprocess.run([sys.executable, SCRIPT], env=env, capture_output=True, text=True)


def test_checker_reports_empty_migrated_database(tmp_path):
    path = tmp_path / "empty.db"
    run_alembic(path, "upgrade", "head")
    result = run_check(path)
    assert result.returncode == 0, result.stderr
    assert "no financial rows" in result.stdout


def test_checker_reports_legacy_unowned_rows_without_exposing_data(tmp_path):
    path = tmp_path / "legacy.db"
    run_alembic(path, "upgrade", "0007_business_and_dependents")
    connection = sqlite3.connect(path)
    connection.execute(
        "INSERT INTO accounts (id, name, account_type, classification, "
        "opening_balance_cents, active, created_at, updated_at) "
        "VALUES (1, 'Secret Savings', 'Savings', 'Personal', 99999, 1, "
        "'2026-09-23 12:00:00', '2026-09-23 12:00:00')"
    )
    connection.commit()
    connection.close()
    result = run_check(path)
    assert result.returncode == 1
    assert "no owner" in result.stdout
    assert "Secret Savings" not in result.stdout
    assert "99999" not in result.stdout
    connection = sqlite3.connect(path)
    assert connection.execute("SELECT COUNT(*) FROM accounts").fetchone()[0] == 1
    connection.close()


def test_checker_requires_explicit_database_url():
    env = {key: value for key, value in os.environ.items()
           if key != "SERENITY_CHECK_DATABASE_URL"}
    result = subprocess.run([sys.executable, SCRIPT], env=env, capture_output=True, text=True)
    assert result.returncode == 2


def run_auth(**overrides):
    env = {**os.environ, "SERENITY_DEV": "0",
           "SERENITY_CHECK_PUBLISHED_ORIGIN": "https://serenity.example.com",
           "SERENITY_AUTHORIZED_PARTIES": "https://serenity.example.com",
           **overrides}
    script = str(Path(SCRIPT).with_name("check_production_auth.py"))
    return subprocess.run([sys.executable, script], env=env,
                          capture_output=True, text=True)


@pytest.mark.parametrize("origin", [
    "", " ", "https://other.example.com", "*", "https://*.example.com",
    "http://serenity.example.com", "https://serenity.example.com/",
    "https://serenity.example.com/path", "https://serenity.example.com?token=secret",
    "https://user:secret@serenity.example.com", "https://serenity.example.com#secret",
    "https://preview.replit.dev", "https://localhost", "https://127.0.0.1",
    "https://serenity.example.com:bad", "https://serenity.example.com:443",
    "https://serenity.example.com,", "https://serenity.example.com,https://x.replit.dev",
])
def test_auth_rejects_unsafe_or_missing_origins_without_echoing_values(origin):
    result = run_auth(SERENITY_AUTHORIZED_PARTIES=origin)
    assert result.returncode == 1
    assert "AUTH BLOCKED" in result.stdout
    assert "secret" not in result.stdout + result.stderr
    if origin.strip():
        assert origin not in result.stdout + result.stderr


def test_auth_accepts_explicit_multiple_origins():
    result = run_auth(SERENITY_AUTHORIZED_PARTIES=
                      " https://serenity.example.com , https://custom.example.com:8443 ")
    assert result.returncode == 0
    assert "not a live sign-in test" in result.stdout


@pytest.mark.parametrize("overrides", [
    {"SERENITY_DEV": "1"},
    {"SERENITY_CHECK_PUBLISHED_ORIGIN": ""},
    {"SERENITY_CHECK_PUBLISHED_ORIGIN": "https://preview.replit.dev"},
    {"SERENITY_CHECK_PUBLISHED_ORIGIN": "https://different.example.com"},
    {"SERENITY_AUTHORIZED_PARTIES": "", "REPLIT_DOMAINS": "serenity.example.com",
     "REPLIT_DEV_DOMAIN": "serenity.example.com"},
])
def test_auth_does_not_infer_production_trust(overrides):
    assert run_auth(**overrides).returncode == 1


def test_combined_check_fails_even_with_empty_database_when_auth_missing(tmp_path):
    path = tmp_path / "empty.db"
    run_alembic(path, "upgrade", "head")
    env = {**os.environ, "SERENITY_CHECK_DATABASE_URL": f"sqlite:///{path}",
           "SERENITY_AUTHORIZED_PARTIES": ""}
    result = subprocess.run([sys.executable, SCRIPT], env=env,
                            capture_output=True, text=True)
    assert result.returncode == 1
    assert "AUTH BLOCKED" in result.stdout
    assert "no financial rows" in result.stdout