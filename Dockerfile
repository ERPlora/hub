# syntax=docker/dockerfile:1
###############################################################################
# Imagen del Hub — runtime Rust (erplora-server) + frontend estático (apps/web).
#
#   Stage `frontend`: pnpm + Vite → apps/web/dist (VITE_RUNTIME_URL="" ⇒ mismo origen).
#   Stage `builder` : cargo build --release -p erplora-server (cache BuildKit de deps).
#   Stage final     : debian:bookworm-slim + curl (healthcheck ECS), usuario no-root.
#
# Contrato de despliegue (aws/terraform/ecs_demo.tf + providers/aws.py):
#   - containerPort 8000  → default HUB_BIND=0.0.0.0:8000
#   - healthCheck `curl http://localhost:8000/health` → alias de /healthz en el server
#   - env: HUB_ID (¡no HUB_HUB_ID!), HUB_CLOUD_API_URL, HUB_CLOUD_API_TOKEN,
#     HUB_AUTH=session, HUB_MODULE_CACHE, HUB_SQLITE_PATH…
#   - persistencia: SQLite en HUB_SQLITE_PATH (default /data/erplora.db) → montar volumen /data.
#     (Adapter Postgres per-tenant: pendiente; HUB_DATABASE_URL del taskdef legacy NO aplica.)
#
# Migraciones: NO hay paso `migrate` separado. El server crea sus tablas de sistema al
# arrancar (`ensure_system_tables`, outbox/identidad) y las migraciones SQL de cada módulo
# las aplica el runtime al instalarlo. El `command` override legacy (`hf migrate && uvicorn…`)
# del taskdef del demo debe ELIMINARSE: esta imagen arranca con su ENTRYPOINT.
###############################################################################

########## Stage 1 — frontend (Vite + pnpm workspace) ##########
FROM node:22-bookworm-slim AS frontend
WORKDIR /src
RUN corepack enable pnpm
COPY pnpm-lock.yaml pnpm-workspace.yaml package.json ./
COPY apps/web/ apps/web/
COPY packages/ packages/
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile
# OutfitKit exporta desde dist/ → compilarlo antes del typecheck/build del shell.
RUN pnpm -F @erplora/outfitkit build
# VITE_RUNTIME_URL="" ⇒ el shell habla con el runtime del MISMO origen (este binario lo sirve).
# sync-modules (prebuild) no encuentra modules-workspace en el contexto: avisa y sigue (OK,
# en prod los módulos los sirve/instala el runtime desde el marketplace, no van horneados).
ENV VITE_RUNTIME_URL=""
RUN pnpm -F @erplora/web build

########## Stage 2 — binario Rust (erplora-server) ##########
FROM rust:1-bookworm AS builder
WORKDIR /src
# NO se copia rust-toolchain.toml: pide el target wasm32 (guests WASM, no hace falta para
# compilar el server) y forzaría su descarga en cada build limpio.
COPY Cargo.toml Cargo.lock ./
COPY crates/ crates/
# Miembros del workspace que cargo necesita parsear aunque no se compilen (-p erplora-server).
COPY apps/bridge/ apps/bridge/
COPY apps/tauri/src-tauri/ apps/tauri/src-tauri/
# liblzma estática (vendored) → la imagen final no necesita liblzma5 del sistema.
ENV LZMA_API_STATIC=1
# `extra_ca` (opcional): CA extra para builds locales detrás de un proxy TLS corporativo
# (p. ej. Netskope intercepta crates.io). Pásala con `--secret id=extra_ca,src=<ca.pem>`.
# En CI (GitHub Actions) no se pasa y el mount queda vacío → no-op.
RUN --mount=type=secret,id=extra_ca \
    --mount=type=cache,target=/usr/local/cargo/registry \
    --mount=type=cache,target=/src/target \
    { [ -s /run/secrets/extra_ca ] && cat /run/secrets/extra_ca >> /etc/ssl/certs/ca-certificates.crt || true; } \
    && cargo build --release --locked -p erplora-server \
    && cp target/release/erplora-server /erplora-server

########## Stage final — runtime slim, no-root ##########
FROM debian:bookworm-slim
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --system --create-home --uid 10001 hub \
    && mkdir -p /data /app/static /var/cache/erplora-modules \
    && chown -R hub:hub /data /app /var/cache/erplora-modules
WORKDIR /app
COPY --from=builder /erplora-server /app/erplora-server
COPY --from=frontend /src/apps/web/dist/ /app/static/
USER hub
# Defaults de la imagen — el despliegue (taskdef ECS) los sobreescribe por env.
ENV HUB_BIND=0.0.0.0:8000 \
    HUB_SQLITE_PATH=/data/erplora.db \
    HUB_STATIC_DIR=/app/static \
    HUB_MODULE_CACHE=/var/cache/erplora-modules \
    HUB_AUTH=session
EXPOSE 8000
ENTRYPOINT ["/app/erplora-server"]
