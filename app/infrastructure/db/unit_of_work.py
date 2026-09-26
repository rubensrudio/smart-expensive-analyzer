"""Unit of Work SQLAlchemy (CT-9, DA-2; cumpre `UnitOfWork` de CT-7).

Uma sessão por `with`. Os 5 repositórios compartilham essa sessão, então tudo que
for feito entre dois `commit()` é atômico (SEA-97). Os repositórios nunca fazem
commit: só quem usa o UoW (o serviço) chama `commit()`.
"""

from types import TracebackType
from typing import Self

from sqlalchemy.orm import Session, sessionmaker

from app.domain.ports import (
    AnomalyRepository,
    CategorizationRuleRepository,
    CategoryRepository,
    ImportRepository,
    TransactionRepository,
)
from app.infrastructure.db.repositories.anomalies import SqlAlchemyAnomalyRepository
from app.infrastructure.db.repositories.categories import SqlAlchemyCategoryRepository
from app.infrastructure.db.repositories.categorization_rules import (
    SqlAlchemyCategorizationRuleRepository,
)
from app.infrastructure.db.repositories.imports import SqlAlchemyImportRepository
from app.infrastructure.db.repositories.transactions import SqlAlchemyTransactionRepository


class SqlAlchemyUnitOfWork:
    # Tipados pelas portas: atributos de Protocol são invariantes.
    categories: CategoryRepository
    rules: CategorizationRuleRepository
    transactions: TransactionRepository
    imports: ImportRepository
    anomalies: AnomalyRepository

    def __init__(self, session_factory: sessionmaker[Session]) -> None:
        self._session_factory = session_factory
        self._session: Session | None = None

    def __enter__(self) -> Self:
        if self._session is not None:
            raise RuntimeError("Unit of Work já está aberto")
        session = self._session_factory()
        self._session = session
        self.categories = SqlAlchemyCategoryRepository(session)
        self.rules = SqlAlchemyCategorizationRuleRepository(session)
        self.transactions = SqlAlchemyTransactionRepository(session)
        self.imports = SqlAlchemyImportRepository(session)
        self.anomalies = SqlAlchemyAnomalyRepository(session)
        return self

    def __exit__(
        self,
        exc_type: type[BaseException] | None,
        exc: BaseException | None,
        tb: TracebackType | None,
    ) -> None:
        session = self._require_session()
        try:
            # Sempre descarta o que não foi commitado: cobre exceção e saída sem
            # commit(). Depois de um commit() sem novas escritas, é no-op.
            session.rollback()
        finally:
            session.close()
            self._session = None
        # Retorna None: a exceção original (se houver) é propagada.

    def commit(self) -> None:
        self._require_session().commit()

    def rollback(self) -> None:
        self._require_session().rollback()

    def _require_session(self) -> Session:
        if self._session is None:
            raise RuntimeError("Unit of Work não está aberto; use dentro de 'with'")
        return self._session
