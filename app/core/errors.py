"""Erros de domínio (DA-11, CT-3, catálogo 8.3 do plan).

O domínio não conhece HTTP além de um inteiro de status. A tradução para o
corpo `ErrorResponse` fica em `app.api.errors`.
"""

from typing import Any


class AppError(Exception):
    """Erro esperado da aplicação, com código estável e mensagem ao usuário."""

    def __init__(
        self,
        code: str,
        message: str,
        http_status: int,
        details: list[Any] | None = None,
    ) -> None:
        super().__init__(message)
        self.code = code
        self.message = message
        self.http_status = http_status
        self.details = details


class EmptyFileError(AppError):
    def __init__(self) -> None:
        super().__init__("EMPTY_FILE", "O arquivo enviado não contém transações.", 422)


class InvalidCsvError(AppError):
    def __init__(self) -> None:
        super().__init__("INVALID_CSV", "Não foi possível ler o arquivo como CSV.", 422)


class MissingColumnsError(AppError):
    def __init__(self, missing: list[str]) -> None:
        super().__init__(
            "MISSING_COLUMNS",
            f"Colunas obrigatórias ausentes: {', '.join(missing)}.",
            422,
            list(missing),
        )


class FileTooLargeError(AppError):
    def __init__(self, limit_mb: int) -> None:
        super().__init__(
            "FILE_TOO_LARGE",
            f"O arquivo excede o tamanho máximo de {limit_mb} MB.",
            413,
        )


class DuplicateFileError(AppError):
    def __init__(self, import_id: int) -> None:
        super().__init__(
            "DUPLICATE_FILE",
            f"Este arquivo já foi importado (importação {import_id}).",
            409,
        )


class TransactionNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__("TRANSACTION_NOT_FOUND", "Transação não encontrada.", 404)


class CategoryNameRequiredError(AppError):
    def __init__(self) -> None:
        super().__init__("CATEGORY_NAME_REQUIRED", "O nome da categoria é obrigatório.", 422)


class CategoryAlreadyExistsError(AppError):
    def __init__(self) -> None:
        super().__init__("CATEGORY_ALREADY_EXISTS", "Já existe uma categoria com este nome.", 409)


class RuleCategoryNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__("RULE_CATEGORY_NOT_FOUND", "Categoria informada na regra não existe.", 422)


class RuleNotFoundError(AppError):
    def __init__(self) -> None:
        super().__init__("RULE_NOT_FOUND", "Regra de categorização não encontrada.", 404)


class InvalidPeriodError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "INVALID_PERIOD",
            "A data inicial deve ser anterior ou igual à data final.",
            422,
        )


class InvalidPaginationError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "INVALID_PAGINATION",
            "Parâmetros de paginação inválidos: limit deve estar entre 1 e 500 e offset "
            "não pode ser negativo.",
            422,
        )


class ServiceUnavailableError(AppError):
    def __init__(self) -> None:
        super().__init__(
            "SERVICE_UNAVAILABLE",
            "Serviço temporariamente indisponível. Tente novamente.",
            503,
        )
