# One independently locked Python environment per service.
FROM python:3.13.7-slim AS runtime
COPY --from=ghcr.io/astral-sh/uv:0.13.9 /uv /usr/local/bin/uv
ARG SERVICE_PATH=.
ARG SERVICE_ID=legacy
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 UV_LINK_MODE=copy \
    UV_CACHE_DIR=/tmp/uv-cache PATH=/srv/service/.venv/bin:$PATH \
    SERVICE_ID=${SERVICE_ID} FIXTURE_DIR=/srv/fixtures/wave-1
WORKDIR /srv/service
COPY ${SERVICE_PATH}/ /srv/service/
COPY fixtures/wave-1/ /srv/fixtures/wave-1/
COPY deploy/runtime.py /srv/runtime.py
RUN uv sync --locked --no-dev --python /usr/local/bin/python \
    && rm -rf /tmp/uv-cache \
    && useradd --uid 10001 --create-home app \
    && mkdir -p /data/files \
    && chown -R app:app /data
USER app
ENV FORWARDED_ALLOW_IPS=*
EXPOSE 8000
ENTRYPOINT ["python", "/srv/runtime.py"]
