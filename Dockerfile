# Imagem da API (TASK-030; SEA-01, DA-13).
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

# Instala só as dependências de runtime (sem extras de dev).
COPY pyproject.toml README.md ./
COPY app/ ./app/
RUN pip install .

# Migrations não entram no wheel: copiadas para `alembic upgrade head` no start.
COPY alembic.ini ./
COPY alembic/ ./alembic/

RUN useradd --uid 10001 --no-create-home --shell /usr/sbin/nologin appuser
USER appuser

EXPOSE 8000

# DA-13: migra e sobe a API. Sem DATABASE_URL o alembic sai com código 1 (SEA-03).
CMD ["sh", "-c", "alembic upgrade head && exec uvicorn app.main:create_app --factory --host 0.0.0.0 --port 8000 --no-access-log"]
