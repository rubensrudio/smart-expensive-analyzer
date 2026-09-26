"""Ambiente do Alembic (CT-5).

URL do banco: `sqlalchemy.url` se definida programaticamente (fixtures de teste),
senão `DATABASE_URL` validada por `load_settings_or_exit()`. A URL nunca é logada.
"""

from logging.config import fileConfig

from alembic import context
from app.core.config import load_settings_or_exit
from app.infrastructure.db.models import Base
from app.infrastructure.db.session import create_engine_from_url

config = context.config

if config.config_file_name is not None:
    # Preserva loggers já criados pela aplicação.
    fileConfig(config.config_file_name, disable_existing_loggers=False)

target_metadata = Base.metadata


def _database_url() -> str:
    url = config.get_main_option("sqlalchemy.url")
    if url:
        return url
    return load_settings_or_exit().database_url


def run_migrations_offline() -> None:
    """Gera o SQL sem conectar ao banco (`alembic upgrade head --sql`)."""
    context.configure(
        url=_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """Aplica as migrations numa conexão real, dentro de uma transação."""
    engine = create_engine_from_url(_database_url())
    try:
        with engine.connect() as connection:
            context.configure(connection=connection, target_metadata=target_metadata)
            with context.begin_transaction():
                context.run_migrations()
    finally:
        engine.dispose()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
