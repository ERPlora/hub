# syntax=docker/dockerfile:1
# Image of the hub: the web (Daphne), the worker and the one-off tasks, plus the PgBouncer sidecar
# of hub and worker (same image, command `pgbouncer-entrypoint`). Contract with the infra:
# aws-next/README.md, «Imagen». Needs the packages/live and packages/ui submodules checked out.
#   docker buildx build --platform linux/arm64 --provenance=false -t erplora/hub .
#   bash docker/image.test.sh erplora/hub

ARG PYTHON_IMAGE=python:3.14-slim

FROM ghcr.io/astral-sh/uv:0.11 AS uv

# 1) The SPA, built on the builder's own platform: its output is plain files.
FROM --platform=$BUILDPLATFORM node:24-slim AS web
ARG PNPM_VERSION=10.34.7
ENV COREPACK_ENABLE_DOWNLOAD_PROMPT=0
RUN corepack enable && corepack prepare "pnpm@${PNPM_VERSION}" --activate
WORKDIR /app
# @erplora/ui is the packages/ui submodule, a member of this repo's pnpm workspace.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY patches patches
COPY packages/ui/package.json packages/ui/package.json
RUN pnpm install --frozen-lockfile
COPY packages/ui packages/ui
COPY tsconfig.json vite.config.ts ./
COPY frontend frontend
COPY apps apps
# Build-time scripts (gen:app-icons): vue-tsc checks the tests that import them.
COPY scripts scripts
RUN pnpm build

# 2) The virtualenv, the compiled catalogues and the collected static files; no database, no secrets.
FROM ${PYTHON_IMAGE} AS build
COPY --from=uv /uv /usr/local/bin/uv
RUN apt-get update \
 && apt-get install -y --no-install-recommends gettext \
 && rm -rf /var/lib/apt/lists/*
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    UV_PROJECT_ENVIRONMENT=/app/.venv \
    PATH="/app/.venv/bin:${PATH}"
WORKDIR /app/project
# Dependencies first, so code changes reuse this layer. live is installed as a wheel: its
# catalogues are compiled before, so the installed package carries them.
COPY pyproject.toml uv.lock ./
COPY packages/live packages/live
RUN find packages/live/live -name '*.po' -exec sh -c 'msgfmt --check-format -o "${1%.po}.mo" "$1"' _ {} \; \
 && uv sync --frozen --no-dev --no-editable
COPY . .
COPY --from=web /app/frontend/dist frontend/dist
# register_apps --check (round 16, spec §4.3): no image with invalid module metadata, icons or
# documentation; it reads only files (no database, no network).
RUN DEBUG=1 python manage.py compilemessages --ignore=packages \
 && DEBUG=1 python manage.py collectstatic --noinput \
 && DEBUG=1 python manage.py register_apps --check \
 && rm -rf packages

# 3) Runtime: read-only filesystem except /tmp (the sidecar writes its config there).
FROM ${PYTHON_IMAGE}
# PgBouncer and the PostgreSQL 18 client (pg_isready, the sidecar's healthcheck) from PGDG.
ADD --chmod=644 https://www.postgresql.org/media/keys/ACCC4CF8.asc /usr/share/keyrings/pgdg.asc
RUN . /etc/os-release \
 && echo "deb [signed-by=/usr/share/keyrings/pgdg.asc] https://apt.postgresql.org/pub/repos/apt ${VERSION_CODENAME}-pgdg main" \
      > /etc/apt/sources.list.d/pgdg.list \
 && apt-get update \
 && apt-get install -y --no-install-recommends pgbouncer postgresql-client-18 \
 && rm -rf /var/lib/apt/lists/*
# CA bundle of RDS: TLS verify-full of the app (DB_SSLROOTCERT) and of PgBouncer towards Aurora.
ADD --chmod=644 https://truststore.pki.rds.amazonaws.com/global/global-bundle.pem /etc/ssl/certs/rds-global-bundle.pem
COPY --chmod=755 docker/pgbouncer-entrypoint.sh /usr/local/bin/pgbouncer-entrypoint
RUN useradd --system --uid 10001 --home-dir /app app
COPY --from=build /app/.venv /app/.venv
COPY --from=build /app/project /app/project
WORKDIR /app/project
# The release travels with the image (round 16, spec §4.3): deploy.yml passes the commit's sha and its
# time (ISO 8601); register_apps refuses to write without them in production. Late, for the cache.
ARG APP_VERSION=""
ARG APP_RELEASED_AT=""
ENV APP_VERSION=${APP_VERSION} \
    APP_RELEASED_AT=${APP_RELEASED_AT}
ENV PATH="/app/.venv/bin:${PATH}" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    DJANGO_SETTINGS_MODULE=config.settings
USER 10001
EXPOSE 8000
# The ALB idle timeout is 120 s; Twisted keeps idle connections far longer, so the ALB always
# closes first (no 502s). --proxy-headers trusts X-Forwarded-For from the ALB.
CMD ["daphne", "--bind", "0.0.0.0", "--port", "8000", "--proxy-headers", "config.asgi:application"]
