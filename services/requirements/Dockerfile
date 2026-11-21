FROM python:3.13-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    UV_LINK_MODE=copy \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN pip install --no-cache-dir uv

COPY pyproject.toml uv.lock README.md alembic.ini ./
COPY migrations ./migrations
COPY src ./src
COPY fixtures ./fixtures

RUN uv sync --locked --no-dev

EXPOSE 8102

CMD ["sh", "-c", "alembic upgrade head && python -m requirements_service.seed && uvicorn requirements_service.main:app --host 0.0.0.0 --port 8102"]
