# Versionado del Hub

> hub#515 · ADR-0269 (modelo de actualización). Fuente única de verdad de la versión del hub y
> criterio de qué cuenta como MAJOR/MINOR/PATCH para este producto.

## Por qué versión semántica

El modelo de actualización (`start-first`, ADR-0269) decidió que la flota se actualiza **sola**: un
parche de seguridad se aplica sin que el dueño pulse nada, y un salto mayor lo decide el dueño. Esa
frase no es expresable sin semver: dos digests distintos no dicen si el salto es un parche o una
versión nueva. Tampoco se puede ofrecer «vuelve a la última `1.x`» ni comparar versiones en el panel.

## Fuente única de verdad

- **`[workspace.package].version`** en `Cargo.toml` es la versión del hub. Todos los crates la
  heredan vía `version.workspace = true`, así que bumpar ese valor fluye a runtime, server, db, etc.
- El runtime la reporta con `env!("CARGO_PKG_VERSION")`: `/api/system` → `hubVersion`, y el
  error-sink hacia el Cloud.
- **En `main`** ese valor es la versión «en desarrollo» (la siguiente).
- **En una release** (tag `v*`), el CI de `build-hub.yml` **reescribe** ese valor desde el tag antes
  del build (paso *Stamp Cargo version from tag*), igual que `tauri-release.yml` hace con
  `tauri.conf.json`. Así la imagen publicada reporta `1.2.3`, no `0.1.0-en-desarrollo`.

## Tags de imagen (GHCR)

`build-hub.yml` publica, en un tag `v1.2.3`:

| Tag | Movilidad | Para qué |
|-----|-----------|----------|
| `:latest` | móvil | el que consume el provisioning (Cloud/Dokploy) |
| `:<git-sha>` | inmutable | pin/rollback exacto por commit |
| `:1.2.3` | inmutable | la release concreta |
| `:1.2` | móvil | «la última 1.2.x» — para parches dentro de una minor |
| `:1` | móvil | «la última 1.x» — la línea de mantenimiento |

En `main` (entre releases) solo se publican `:latest` y `:<sha>`.

## Criterio MAJOR / MINOR / PATCH

La convención es **«Contrato = MAJOR»**: el salto de versión mayor se reserva para lo que rompe un
contrato que alguien externo depende. Todo lo demás es iteración fluida.

| Tipo | Cuándo | Ejemplos |
|------|--------|----------|
| **MAJOR** (x.0.0) | Romper un **contrato** que un consumidor externo no controla | Cambio incompatible en el contrato de módulo (`module.json`), en el esquema de BD de un módulo, o en la API HTTP pública. Eliminar un endpoint o cambiar el tipo de un campo público. |
| **MINOR** (0.x.0) | Nueva funcionalidad o cambio **hacia atrás compatible** | Nueva feature, nueva pantalla del TPV, nuevo endpoint (aditivo), nueva tabla de módulo (sin tocar las existentes). |
| **PATCH** (0.0.x) | **Bugfix** compatible | Corregir un bug, parche de seguridad, refactor interno sin cambio de contrato. |

### Matices de este producto

- **Una pantalla nueva del TPV NO es MAJOR.** Es MINOR: no rompe ningún contrato, solo añade
  capacidad. El dueño la descubre al actualizar; no tiene que decidir nada.
- **Un cambio de contrato de módulo SÍ es MAJOR**, aunque sea «solo» un campo. Los módulos
  instalados en la flota dependen de ese contrato; romperlo los deja sin cargar.
- **Un parche de seguridad es PATCH** (o MINOR si añade superficie). Es justo el caso que el modelo
  auto-update aplica solo: `1.0.0 → 1.0.1` no requiere decisión del dueño.
- **Cuando dudes, MINOR.** MAJOR es caro (el dueño tiene que decidir actualizar); reservarlo para
  roturas reales de contrato evita la fatiga de «otra versión mayor».

## Cómo sacar una release

1. Actualizar `[workspace.package].version` en `Cargo.toml` (la nueva versión «en desarrollo»).
2. Tras mergear a `main`, crear el tag `vX.Y.Z` (igual que el valor que acabas de poner).
3. El CI publica la imagen con los tags semver y estampa la versión en el binario.

> El bump de versión va en el mismo PR que introduce el cambio de contrato/feature, no en uno
> aparte: así el tag apunta exactamente al commit que lo introdujo.
