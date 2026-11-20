FROM python:3.13.7-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_CACHE_DIR=/tmp/uv-cache
WORKDIR /srv/workforce
COPY services/workforce/ /srv/workforce/
COPY fixtures/wave-1/ /srv/fixtures/wave-1/
ENV FIXTURE_DIR=/srv/fixtures/wave-1 PATH=/srv/workforce/.venv/bin:$PATH

FROM base AS runtime
RUN uv sync --locked --no-dev --python /usr/local/bin/python \
    && useradd --uid 10001 --create-home workforce \
    && mkdir -p /var/lib/workforce/files \
    && chown -R workforce:workforce /var/lib/workforce
USER workforce
EXPOSE 8101
CMD ["uvicorn", "workforce.api:create_app", "--factory", "--host", "0.0.0.0", "--port", "8101"]

FROM base AS tests
RUN uv sync --locked --python /usr/local/bin/python
CMD ["python", "-m", "pytest", "-q"]
