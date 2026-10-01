"""Regression coverage for the isolated, fail-closed publishing gate."""

import os
from pathlib import Path
import shutil
import subprocess

SCRIPT = Path(__file__).resolve().parents[1] / "scripts/prepublish_check.sh"
BASH = shutil.which("bash")


def run_gate(tmp_path, missing=None):
    tools = tmp_path / "bin"
    tools.mkdir()
    shutil.copy(shutil.which("dirname"), tools / "dirname")
    for name in ("initdb", "postgres", "alembic", "python", "pytest", "chromium"):
        if name == missing:
            continue
        body = "exit 0"
        if name == "pytest":
            body = """
[[ "$DATABASE_URL" == "sqlite://" ]] || exit 11
[[ "$SERENITY_REQUIRE_POSTGRES" == 1 ]] || exit 12
[[ "$SERENITY_REQUIRE_BROWSER" == 1 ]] || exit 13
[[ -z "${PGHOST+x}${PGPASSWORD+x}${PGSERVICE+x}" ]] || exit 14
echo isolated-pytest
"""
        if name in ("alembic", "initdb", "postgres"):
            body = "echo unexpected-direct-database-command; exit 99"
        tool = tools / name
        tool.write_text(f"#!{BASH}\n{body}\n")
        tool.chmod(0o755)
    return subprocess.run(
        [BASH, str(SCRIPT)], cwd=tmp_path,
        env={**os.environ, "PATH": str(tools),
             "DATABASE_URL": "postgres://fake:fake@must-not-connect.invalid/test",
             "PGHOST": "must-not-connect.invalid", "PGPASSWORD": "fake",
             "PGSERVICE": "fake", "SERENITY_REQUIRE_POSTGRES": "0",
             "SERENITY_REQUIRE_BROWSER": "0"},
        text=True, capture_output=True, timeout=10,
    )


def test_gate_isolates_database_and_requires_both_suites(tmp_path):
    result = run_gate(tmp_path)
    assert result.returncode == 0, result.stderr
    assert "isolated-pytest" in result.stdout
    assert "unexpected-direct-database-command" not in result.stdout


def test_gate_fails_clearly_without_postgres(tmp_path):
    result = run_gate(tmp_path, missing="initdb")
    assert result.returncode != 0
    assert "Required test tool missing: initdb" in result.stderr
    assert "isolated-pytest" not in result.stdout


def test_gate_preserves_required_browser_toolchain(tmp_path):
    result = run_gate(tmp_path, missing="chromium")
    assert result.returncode != 0
    assert "Required browser test tool missing: Chromium" in result.stderr
    assert "isolated-pytest" not in result.stdout