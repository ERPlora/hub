# BACKLOG — hub (Fase 1: POS + AI)

Espejo legible del trabajo pendiente. La fuente única de seguimiento es el **GitHub Project**;
este fichero se actualiza desde él. Plan completo en `ARQUITECTURA.md` + el plan maestro.

**Reparto (CLAUDE.md):** `[TÚ]` humano · `[IA]` asistente · `[TÚ·IA guía]` humano con guía.
**Prioridades:** `P0` bloqueante · `P1` Fase 1 · `P2` deseable Fase 1.

## Hecho
- ✅ `db` → sqlx async + Paso 6 (runtime/server/vector/installer compilan, 96 tests).
- ✅ Bloque `ai`/`agent` en los 99 `module.json` (inglés) + schema limpio + routing §9.2b documentado.
- ✅ `Manifest` del runtime parsea `agent`/`ai_context`/`ai` (la IA ya es legible por el runtime).

## Workstream A — Repos & subida ordenada
- [ ] `P0` `[IA]` Higiene `.gitignore` + commits del core por área (no uno gigante) → push `hub`.
- [ ] `P1` `[TÚ decide]` Distribución de `guest-sdk` + `module-stencil` para repos por módulo
      (registry privado vs git submódulo vs vendoring) — **bloquea el split**.
- [ ] `P1` `[IA automatiza]` Script de split de los módulos POS a `ERPlora-module-<id>` (+ release workflow).

## Workstream B — Gestión de tareas
- [ ] `P0` `[IA]` BACKLOG.md (este fichero) + GitHub Project + issues de Fase 1 etiquetados.

## Workstream C — Acabar el hub (núcleo)
- [ ] `P0` `[TÚ·IA guía]` **Frontend↔backend**: `apps/web` inicializa `module-sdk` → `globalThis.erplora`
      (`apps/web/src/lib/sdk.ts` + `main.tsx`). Gap bloqueante: hoy los WC no llaman al backend.
- [ ] `P1` `[TÚ·IA guía]` Wire **Tier-2 WASM** en `execute_command` (`runtime` ↔ `wasm-host`).
- [ ] `P1` `[IA]` Axum **sirve el frontend** (static `dist/`) + `/health` + shutdown SIGTERM.
- [ ] `P1` `[TÚ]` **Auth** usuario/rol/PIN (Argon2) + device-trust + `/api/auth/refresh`.
- [ ] `P2` `[TÚ]` Resolver `depends_on` (topo-sort) en install.
- [ ] `P2` `[IA]` Decode tipos Postgres en `db` (NUMERIC/TIMESTAMPTZ/UUID/JSONB).

## Workstream D — CI/CD & artefactos
- [ ] `P1` `[IA]` **Docker real** (`docker/Dockerfile`) + workflow `build→ECR` (`erplora-hub:latest`).
- [ ] `P1` `[IA]` CI **ejecutables Tauri → S3 privado** (confirmar bucket) — requiere `apps/tauri`.
- [ ] `P1` `[IA]` CI **zips de módulos → S3 marketplace** (por repo de módulo; usa `pack`+`sign`).

## Workstream E — Módulos POS
- [ ] `P0` `[TÚ decide]` Definir el **set POS exacto** (inventory, sales/pos, invoice/verifactu,
      customers, cash_register, taxes, payments, tables/kitchen…).
- [ ] `P1` `[TÚ·IA guía]` SQL/UI reales por módulo POS + flujo cross-módulo (venta→stock→factura).
- [ ] `P1` `[IA]` CLI `create/pack/sign/publish` + coordinar **endpoint vendor de subida en Cloud**.

## Workstream F — AI + shells
- [ ] `P1` `[TÚ·IA guía]` **Tool-assembly**: assembler (parse `ai`/`agent` + filtro permiso + formato Cloud)
      → router (embed query → búsqueda vectorial → top módulos).
- [ ] `P1` `[TÚ·IA guía]` **cloud-client AI**: `embeddings` + `chat`/tool-call loop + auth (§9.3).
- [ ] `P1` `[TÚ·IA guía]` Registro de embeddings de `agent.description` al instalar (§9.6).
- [ ] `P1` `[TÚ·IA guía]` **`apps/tauri`** (Tauri v2 + `invoke` → runtime; reusa `IpcTransport`).

## Fuera de Fase 1 (`fase:later`)
~90 módulos no-POS · RAG de docs (`ai_context`) · `PgVectorStore` · firma asimétrica de módulos ·
migración legacy (§13) · Bridge/periféricos multi-dispositivo.

## Decisiones pendientes (humano)
1. Distribución de `guest-sdk`/`module-stencil` para repos por módulo.
2. Bucket exacto para los ejecutables Tauri ("S3 privado para comercialización").
3. Lista exacta del set POS.
4. Endpoint vendor de subida en el Cloud (no existe; coordinar con `cloud/`).
