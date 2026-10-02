"""Wave 0 must require recovery without accepting an operator-selected database."""

import os
from pathlib import Path
import shutil
import subprocess

ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "serenity_next_check.sh"


def run_baseline(tmp_path, downstream_exit=0):
    scripts = tmp_path / "scripts"
    scripts.mkdir()
    shutil.copy(SCRIPT, scripts / SCRIPT.name)
    (scripts / "prepublish_check.sh").write_text(
        "#!/usr/bin/env bash\n"
        '[[ "$SERENITY_REQUIRE_POSTGRES_RESTORE" == "1" ]] || exit 21\n'
        '[[ -z "${TEST_POSTGRESQL_URL+x}" ]] || exit 22\n'
        f"exit {downstream_exit}\n"
    )
    return subprocess.run(
        ["bash", str(scripts / SCRIPT.name)], cwd=tmp_path,
        env={**os.environ, "SERENITY_REQUIRE_POSTGRES_RESTORE": "0",
             "TEST_POSTGRESQL_URL": "postgres://synthetic.invalid/do-not-connect"},
        capture_output=True, text=True, timeout=10,
    )


def test_next_gate_requires_recovery_and_removes_inherited_test_target(tmp_path):
    result = run_baseline(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "engineering baseline passed" in result.stdout
    assert "NOT certified" in result.stdout
    assert "synthetic.invalid" not in result.stdout + result.stderr


def test_next_gate_does_not_report_success_after_a_failed_check(tmp_path):
    result = run_baseline(tmp_path, downstream_exit=9)
    assert result.returncode == 9
    assert "engineering baseline passed" not in result.stdout


def test_financial_lock_test_cannot_accept_ambient_database_target():
    source = (ROOT / "tests" / "test_conversion_locking.py").read_text()
    assert "TEST_POSTGRESQL_URL" not in source
    assert "def test_postgresql_owner_financial_writes" in source
    assert '"/isolated-money-pg"' in source