from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, pool

import models.account  # noqa: F401
import models.bill  # noqa: F401
import models.business  # noqa: F401
import models.debt  # noqa: F401
import models.dependent  # noqa: F401
import models.investment  # noqa: F401
import models.transaction  # noqa: F401
import models.transaction_correction  # noqa: F401
from storage.database import Base, get_database_url

config = context.config
config.set_main_option("sqlalchemy.url", get_database_url().replace("%", "%%"))

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    context.configure(
        url=get_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )
    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            render_as_batch=connection.dialect.name == "sqlite",
            compare_type=True,
        )
        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()