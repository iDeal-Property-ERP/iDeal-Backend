# ---- Stage 1: Builder ----
FROM ghcr.io/astral-sh/uv:python3.14-alpine3.23 AS builder

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=0 \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

WORKDIR /app

RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --locked --no-install-project --no-dev

# ---- Stage 2: Final runtime image ----
FROM python:3.14-alpine3.23 AS final

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    VIRTUAL_ENV=/app/.venv \
    PATH="/app/.venv/bin:$PATH"

RUN addgroup -S nonroot \
    && adduser -S -u 999 -G nonroot -h /home/nonroot -s /sbin/nologin nonroot

WORKDIR /app

COPY --from=builder --chown=nonroot:nonroot /app /app
COPY --chown=nonroot:nonroot ./src /app

RUN apk add --no-cache curl \
    && chmod +x /app/scripts/*.sh \
    && mkdir -p /cdn \
    && chown -R nonroot:nonroot /cdn

USER nonroot
