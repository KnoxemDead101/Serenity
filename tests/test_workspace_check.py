"""Publishing checker rejects owners no longer linked to a real workspace."""

import os
import sqlite3
import subprocess
import sys
from pathlib import Path

from test_migrations import run_alembic


def test_checker_rejects_orphan_financial_owner(tmp_path):
    path = tmp_path / "workspaces.db"
    run_alembic(path, "upgrade", "0011_identity_and_workspaces")
    with sqlite3.connect(path) as db:
        db.execute(
            "INSERT INTO accounts (name, account_type, classification, "
            "opening_balance_cents, active, created_at, updated_at, owner_id) "
            "VALUES ('Confidential', 'Checking', 'Personal', 700, 1, CURRENT_TIMESTAMP, "
            "CURRENT_TIMESTAMP, 'not-a-workspace')"
        )
    env = {
        **os.environ, "SERENITY_CHECK_DATABASE_URL": f"sqlite:///{path}",
        "SERENITY_DEV": "0",
        "SERENITY_CHECK_PUBLISHED_ORIGIN": "https://serenity.example.com",
        "SERENITY_AUTHORIZED_PARTIES": "https://serenity.example.com",
    }
    result = subprocess.run(
        [sys.executable, str(Path(__file__).resolve().parents[1] /
                             "scripts/check_production_rows.py")],
        env=env, capture_output=True, text=True,
    )
    assert result.returncode == 1
    assert "not linked to a workspace" in result.stdout
    assert "Confidential" not in result.stdout
    assert "700" not in result.stdout