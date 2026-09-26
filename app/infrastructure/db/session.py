"""Criação de engine e fábrica de sessão (CT-4, DA-15)."""

from sqlalchemy import Engine, create_engine
from sqlalchemy.orm import Session, sessionmaker


def create_engine_from_url(url: str) -> Engine:
    """Cria o engine sem conectar.

    `hide_parameters=True` impede que valores de parâmetros (descrições, valores)
    vazem em mensagens de erro e logs (AS-3). `pool_pre_ping=True` converte a
    queda do banco em `OperationalError` já no checkout da conexão.
    """
    return create_engine(url, hide_parameters=True, pool_pre_ping=True)


def create_session_factory(engine: Engine) -> sessionmaker[Session]:
    return sessionmaker(bind=engine, class_=Session, expire_on_commit=False)
