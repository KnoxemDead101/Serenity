"""Expected revision for tests that intentionally upgrade the full current app."""

from alembic.config import Config
from alembic.script import ScriptDirectory


def current_head():
    return ScriptDirectory.from_config(Config("alembic.ini")).get_current_head()