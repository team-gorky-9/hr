FROM python:3.13.7-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.13.5 /uv /usr/local/bin/uv
ENV PYTHONUNBUFFERED=1 UV_LINK_MODE=copy UV_CACHE_DIR=/tmp/uv-cache
WORKDIR /srv/hiring
COPY services/hiring/ /srv/hiring/
COPY fixtures/wave-1/ /srv/fixtures/wave-1/
ENV FIXTURE_DIR=/srv/fixtures/wave-1 PATH=/srv/hiring/.venv/bin:$PATH

FROM base AS runtime
RUN uv sync --locked --no-dev --python /usr/local/bin/python \
    && useradd --uid 10003 --create-home hiring \
    && mkdir -p /var/lib/hiring/files \
    && chown -R hiring:hiring /var/lib/hiring
USER hiring
ENV FILE_ROOT=/var/lib/hiring/files
EXPOSE 8103
CMD ["python", "-m", "hiring", "serve", "--host", "0.0.0.0", "--port", "8103"]

FROM base AS tests
RUN uv sync --locked --python /usr/local/bin/python
CMD ["python", "-m", "pytest", "-q"]
