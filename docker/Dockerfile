# ==============================================================================
# ERPlora Hub — imagen del runtime del tenant (modo cloud). ARQUITECTURA.md §11.
# ==============================================================================
#
# Multi-stage:
#   (1) frontend  — build del shell web (pnpm + Vite) → apps/web/dist
#   (2) builder   — build del binario Rust en release → erplora-server
#   (3) runtime   — debian-slim con el binario + el dist del web
#
# El runtime (crates/server) sirve:
#   - /api, /ws, /healthz        → router Axum
#   - el resto                   → ServeDir sobre HUB_WEB_DIR (dist de Vite) con fallback SPA
# (combo cloud + web-PWA, ARQUITECTURA.md §3). Sin HUB_WEB_DIR no sirve estáticos (modo Tauri).
#
# Bind: por defecto el server escucha en 127.0.0.1:8787 (dev). En contenedor lo forzamos a
# 0.0.0.0:8787 vía HUB_BIND para que el ALB/ECS pueda alcanzarlo.
#
# NOTA módulos: el shell NO hornea módulos (se descargan del marketplace en runtime). El paso
# `prebuild` (sync-modules.mjs) copia módulos de un workspace externo que NO está en esta imagen;
# emite warnings y los salta — es correcto (ver apps/web/sync-modules.mjs). public/modules queda
# vacío en la imagen; el runtime sirve los módulos instalados desde el marketplace.
#
# Build context = raíz del repo (`hub/`). Ejecutar con: docker build -f docker/Dockerfile .
# ==============================================================================

# ------------------------------------------------------------------------------
# (1) Frontend — pnpm + Vite. Versión de pnpm pineada por package.json (pnpm@10).
# ------------------------------------------------------------------------------
FROM node:22-bookworm-slim AS frontend
WORKDIR /app
ENV CI=1
# Corepack activa la versión de pnpm declarada en package.json (packageManager).
RUN corepack enable
# Copiamos manifests primero para cachear `pnpm install` mientras no cambien.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml .npmrc ./
COPY apps/web/package.json ./apps/web/
COPY packages ./packages
# `hub/modules` es el dir reservado para módulos INSTALADOS en runtime: está vacío en git (0
# ficheros trackeados), así que NO se copia (un `COPY modules` fallaría en el checkout de CI).
# Solo creamos el dir vacío para satisfacer el glob `modules/*` de pnpm-workspace.yaml.
RUN mkdir -p modules
RUN pnpm install --frozen-lockfile
# Ahora el código del shell web.
COPY apps/web ./apps/web
COPY scripts ./scripts
# OutfitKit SIEMPRE a la última publicada en npm. El tag `latest` lo mueve la GitHub Action de
# release de `outfitkit` en cada publish, así que el Hub debe reflejar lo último que haya ahí
# (DECISIÓN de producto, 2026-06-22). El `pnpm install --frozen-lockfile` de arriba deja el RESTO
# de deps pineadas/reproducibles; aquí re-resolvemos SOLO outfitkit a `@latest`, ignorando el pin
# del lockfile. El ARG cambia en cada build de CI (github.run_id, vía build-hub.yml) para invalidar
# la caché de esta capa y forzar la re-descarga de la última versión en CADA imagen.
# (apps/web importa `@erplora/outfitkit/...` desde npm; el viejo `packages/outfitkit` de workspace
#  ya no se usa ni está versionado.)
ARG OUTFITKIT_CACHEBUST=local
# OJO: hay que REFERENCIAR el ARG en el RUN. En Docker un ARG declarado pero NO usado no invalida
# la caché; al imprimirlo aquí, su valor único por build (github.run_id) entra en la clave de caché
# de esta capa → `pnpm add @latest` (+ el build de Vite de abajo) se re-ejecuta en CADA imagen y
# coge SIEMPRE la última OutfitKit, incluso sin cambios de source.
RUN echo "outfitkit cachebust=${OUTFITKIT_CACHEBUST}" \
 && pnpm --filter @erplora/web add @erplora/outfitkit@latest
# Versión de la app para el footer (vite.config.ts la lee de APP_VERSION o git tag).
# En CI (build-hub.yml) se pasa desde el tag git; en dev local, vite.config.ts hace
# fallback a `git describe` o package.json. Default "0.0.0" solo si no hay ni tag ni env.
ARG APP_VERSION=0.0.0
ENV APP_VERSION=${APP_VERSION}
# Build de producción del shell (vue-tsc + vite build → apps/web/dist).
# prebuild (sync-modules.mjs) busca módulos en un workspace externo ausente aquí: warn+skip (ok).
RUN pnpm -F @erplora/web build

# ------------------------------------------------------------------------------
# (2) Builder — Rust release del servidor del runtime.
# Toolchain "stable" (rust-toolchain.toml). El target wasm32 es solo para guests Tier 2;
# el binario del servidor no lo necesita, así que usamos la imagen oficial de Rust tal cual.
# ------------------------------------------------------------------------------
FROM rust:1-bookworm AS builder
WORKDIR /app
# Todo el workspace Cargo (crates + apps + Cargo.toml/lock). El builder necesita el árbol completo
# porque erplora-server depende de varios crates por path (runtime, db, verifactu, …).
COPY Cargo.toml Cargo.lock rust-toolchain.toml ./
COPY crates ./crates
COPY apps ./apps
COPY schemas ./schemas
# Build release SOLO del binario del servidor.
RUN cargo build --release -p erplora-server

# ------------------------------------------------------------------------------
# (3) Runtime — imagen final mínima.
# debian:bookworm-slim: el binario se linka contra glibc + necesita certificados CA
# (reqwest rustls-tls-native-roots confía en el trust store del SO → instalamos ca-certificates).
# ------------------------------------------------------------------------------
FROM debian:bookworm-slim AS runtime
WORKDIR /app

# ca-certificates: TLS hacia el Cloud Portal (descarga de módulos, proxy del asistente).
# curl: usado por el HEALTHCHECK contra /healthz.
RUN apt-get update \
    && apt-get install -y --no-install-recommends ca-certificates curl \
    && rm -rf /var/lib/apt/lists/*

# Usuario sin privilegios.
RUN useradd --system --uid 10001 --create-home --home-dir /app erplora

# Binario del servidor + dist del shell web.
COPY --from=builder /app/target/release/erplora-server /usr/local/bin/erplora-server
COPY --from=frontend /app/apps/web/dist /app/web

# Config por defecto del contenedor (sobreescribible por ECS/env).
#   HUB_BIND     — escuchar en todas las interfaces (no solo loopback) para el ALB.
#   HUB_WEB_DIR  — servir el shell web horneado en la imagen.
#   HOME=/tmp    — el usuario `erplora` no puede escribir en /app (root-owned), y
#                  wasmtime/extism crea su cache de compilación en $HOME/.cache/wasmtime.
#                  Sin esto, los handlers WASM de los módulos fallan ("failed to create
#                  cache directory"). /tmp es escribible. Aplica a TODOS los hubs.
ENV HUB_BIND=0.0.0.0:8787 \
    HUB_WEB_DIR=/app/web \
    HOME=/tmp

USER erplora
EXPOSE 8787

# Healthcheck contra el endpoint /healthz del router Axum.
# Apunta a /readyz, NO a /healthz (hub#538). `/healthz` es un literal «ok»: un hub sin BD, con las
# migraciones a medias o sin un solo módulo cargado lo pasaba igual. Y esto no es cosmético — con el
# blue/green de ADR-0269 este HEALTHCHECK es el ÚNICO criterio de `failure_action: rollback`: si da
# verde a una tarea rota, Swarm mata la vieja que sí funcionaba y no hay vuelta atrás.
#
# `start-period` sube de 10s a 90s: /readyz no responde UP hasta tener BD, migraciones aplicadas y
# los módulos de `hub_module` registrados, y eso incluye re-descargarlos del marketplace en el
# contrato stateless de Swarm. Con 10s el arranque normal contaba como fallo. El número definitivo
# sale de MEDIR el arranque real (hub#520), no de estimarlo.
HEALTHCHECK --interval=30s --timeout=5s --start-period=90s --retries=3 \
    CMD curl -fsS http://127.0.0.1:8787/readyz || exit 1

ENTRYPOINT ["/usr/local/bin/erplora-server"]
