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
  heredan vía `version.workspace = true`, así que el número **que el CI estampa desde el tag** fluye
  a runtime, server, db, etc. (no lo escribe una persona — ver «Cómo sacar una release»).
- El runtime la reporta como `CORE_VERSION`, que decide el script de build del crate
  (`crates/runtime/src/core_version.rs`): `/readyz`, `/api/hub/context`, el latido, el error-sink
  hacia el Cloud y el bloque `SistemaInformatico` que va a la AEAT.
- **En un build de fuente** (`cargo build`/`cargo test` en un checkout) ese valor **no** es el hueco
  `1.0.0` del `[workspace.package]`: el script lo sustituye por `<tag v* más nuevo del repo>-source`
  (hub#1619), para que satisfaga el suelo `compatibility.min_erplora_version` de un módulo sin
  hacerse pasar por la release del mismo nombre. Los tags se leen con `git tag --list`, no con
  `git describe`: `main` es huérfano y desde `develop` los tags de release no son alcanzables. Una
  versión ya estampada (una release, o el sufijo del canal `:dev`) no se toca jamás; dentro de la
  imagen publicada ni siquiera hay `.git`, así que ahí el script no puede cambiar nada.
- **En una release** (tag `v*`), el CI de `build-hub.yml` **reescribe** ese valor desde el tag antes
  del build (paso *Stamp Cargo version from tag*), igual que `tauri-release.yml` hace con
  `tauri.conf.json`. Así la imagen publicada reporta `1.2.3`, no `0.1.0-en-desarrollo`.

## Tags de imagen (GHCR) y canales de release (hub#1176, decisión 2026-08-25)

`build-hub.yml` publica `ghcr.io/erplora/hub` en **tres canales móviles**, siempre acompañados
del `:<sha>` inmutable (pin/rollback). La lógica vive en
[`scripts/image-tags.sh`](scripts/image-tags.sh) (tests de contrato en
[`scripts/tests/image-tags.test.sh`](scripts/tests/image-tags.test.sh); detalle completo en
[`ARQUITECTURA.md` §13.1](ARQUITECTURA.md)):

| Canal | Lo dispara | Versión horneada | Tags |
|---|---|---|---|
| **`dev`** | push/dispatch en `develop` — lo despliega **PRE** | `X.Y.Z-dev.<n>+g<sha>` — `X.Y.Z` es **un patch por encima** del tag `v*` más nuevo que el repo **tiene** (`git tag --list`, no `git describe`: `main` es huérfano y desde `develop` los tags de release no son alcanzables — hub#1625) | `:dev` |
| **`canary`** | tag `vX.Y.Z-rc.N` — candidata para un **subconjunto** de hubs de prod | `X.Y.Z-rc.N` | `:X.Y.Z-rc.N` `:canary` (NO mueve `:latest`, `:X.Y` ni `:X`) |
| **`stable` = `latest`** | tag `vX.Y.Z` final — lo que estrena todo hub nuevo | `X.Y.Z` | `:X.Y.Z` `:X.Y` `:X` `:latest` `:stable` (alias, mismo digest) |

`main` sigue publicando solo `:latest` + `:<sha>` (versión del Cargo: `main` = prod). El guard
rechaza un tag no semver, ya publicado, no monótono, o una rc de una versión ya cerrada; en
`develop` se **niega** a publicar sin `git describe` utilizable o sin un solo tag `v*` en el
repo — hornear el hueco `1.0.0` a ciegas es exactamente el bug que abrió hub#1170. Publicar un
tag de release **dispara el canario y espera su veredicto** antes de nada más (hub#1659); un tag
`-rc.N` **no** dispara `tauri-release.yml` (las stores son irreversibles). Publicar también
comprueba que **el `module-toolkit` ya conoce esa versión** — module-toolkit#226, hub#1648 — para
que el suelo `compatibility.min_erplora_version` de un módulo nunca apunte a un hub que el
toolkit todavía no sabe validar.

> **OutfitKit lo publica el propio hub** (ADR-0451, hub#1589/#1853): la variable `HUB_OUTFITKIT`
> del toolkit fija qué versión de `@erplora/outfitkit` lleva cada imagen (hub v1.1.22 → outfitkit
> 0.1.72 es el par verificado a fecha de este documento).

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

**La versión la escribe el TAG** ([ADR-0280](../architecture/00-overview/decision-log.md#adr-0280)).

1. Mergear a `develop` → `main` con `./pm/merge-pr.sh hub <nº PR>`.
2. Etiquetar: `git tag v1.2.3 && git push origin v1.2.3`.

Eso es todo lo que hace una persona. El tag dispara `build-hub.yml`, que **antes de compilar**
pasa por [`scripts/image-tags.sh`](scripts/image-tags.sh) —donde vive la guarda que impide
republicar encima de lo que ya está en producción— y estampa el número con
[`scripts/stamp-version.sh`](scripts/stamp-version.sh) desde `${GITHUB_REF_NAME#v}`.

🪦 **`Cargo.toml` NO se toca.** Aquí ponía «actualizar `[workspace.package].version`» como paso 1:
eso es el modelo **anterior a ADR-0280** y está **derogado**. Hoy lo estampa el CI, y el número que
haya en el repo se queda en el de desarrollo y da igual — tocarlo a mano no adelanta nada y hace
creer que el fichero manda.

Y no lo estampa solo en `Cargo.toml`: `stamp-version.sh` escribe **los tres** ficheros que llevan
versión (el workspace de Cargo, el `package.json` del `module-sdk` y su `version.ts`) y **se niega**
si alguno no tiene dónde escribir — estampar dos de tres y salir en verde es exactamente como los
tres números se separan.

> **Fuente canónica de esto**:
> [`architecture/hub/versioning.md` §4](../architecture/hub/versioning.md). Si este fichero y aquel
> discrepan, manda aquel — es el que se mantiene con los ADR. Este doc explica **cómo se decide el
> número** (arriba); el procedimiento de publicación vive allí.
