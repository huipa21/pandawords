ARG PYTHON_IMAGE=docker.io/library/python:3.14-slim-trixie
ARG UV_IMAGE=ghcr.io/astral-sh/uv:0.11.18

FROM ${UV_IMAGE} AS uv
FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_PYTHON_DOWNLOADS=never \
    UV_LINK_MODE=copy
WORKDIR /app/backend
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-cache

FROM ${PYTHON_IMAGE} AS runtime
ENV PATH="/app/backend/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    APP_ENV=production \
    MEDIA_DIR=/data/media \
    LEXICON_DIR=/data/lexicon
# Keep media copy-up nonempty so a later nginx mount cannot reinitialize it as root.
RUN groupadd --gid 10001 pandawords \
    && useradd --uid 10001 --gid pandawords --no-create-home pandawords \
    && mkdir -p /data/media /data/lexicon \
    && touch /data/media/.initialized \
    && chown -R pandawords:pandawords /data
WORKDIR /app/backend
COPY --from=build /app/backend/.venv .venv
COPY app ./app
USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "1"]
