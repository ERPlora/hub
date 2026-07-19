# TO_CHECK — Export/Import del hub (ADR-0113 + ADR-0116) · pendientes de verificar en las e2e

> Lista de verificación para la revisión e2e (Playwright + `/qa-hub`) posterior al merge de
> `feat/export-import-core`. Lo ya verificado en vivo (2026-07-12, runtime real + Vite) fue:
> widget de home → export (selección dinámica, descarga `*.blueprint.zip` con datos reales,
> placeholder `__HUB_ID__`) → import (upload → inspect → informe con Usuarios/Ajustes/taxes/
> inventory **Aplicado**). Suites: runtime 13/13 · server 22/22 · typecheck OK.
>
> **⚠️ RE-COLOCACIÓN UI (2026-07-12 tarde, ADR-0116 — decisión de Ioan):** ya NO existen las
> páginas `/export` ni `/import`. Import y export viven **JUNTOS en la pestaña «Datos» de
> Ajustes** (`/settings?tab=data`, ion-segment del footer = navegación secundaria; componentes
> `ImportPanel.vue` + `ExportPanel.vue`). Y el widget de la home ya NO es una tarjeta fija encima
> del board: es un **widget DEL `ok-widget-board`** (`id: core.blueprint`), en el catálogo y
> antepuesto a todos los presets, ocultable desde el picker como cualquier otro. Los specs
> (`DashboardPage.spec.ts`, `ExportPanel.spec.ts`, `ImportPanel.spec.ts`)
> ya expresan este contrato — se reescribieron ANTES del cambio (TDD) y quedan por CORRER
> (Playwright no está instalado en el workspace; typecheck + build prod verificados).

## 🆕 Qué verificar de la re-colocación (ADR-0116, sesión 2026-07-12 tarde)

- [ ] `/settings?tab=data` abre Ajustes con la pestaña **Datos** activa (deep-link por query);
      la pestaña también es alcanzable con el segment del footer (6ª pestaña, icono
      swap-vertical). Sin query o con query inválida → pestaña Hub como siempre.
- [ ] En la pestaña Datos aparecen **los dos paneles en la misma página**: Importar (arriba,
      `import-lead`) y Exportar (debajo, `export-lead`), con TODOS los testids de antes intactos.
- [ ] Las URLs viejas `/export` y `/import` ya no existen (vue-router sin ruta → no navegan);
      la nav principal (App.vue) ya no lista Exportar/Importar; Ajustes es la única entrada.
- [ ] Home: el widget «Configura tu hub» está **DENTRO** de `<ok-widget-board>` (no como tarjeta
      fija encima) con `data-testid=dashboard-blueprint-widget`; sus dos botones navegan ambos a
      `/settings?tab=data`.
- [ ] Con localStorage FRESCO (sin `okwb:dashboard-hub`), el widget core es visible por defecto
      (va antepuesto al primer preset y al fallback all-widgets). En hub VACÍO (0 módulos) el
      board se pinta igualmente con solo el widget core.
- [ ] El picker (⋮) permite ocultar/mostrar el widget core como a cualquier otro.
- [ ] **GOTCHA esperado:** un usuario con `okwb:dashboard-hub` YA persistido de antes NO verá el
      widget nuevo hasta activarlo en el picker (inherente a «igual que los demás» — confirmar
      que es el comportamiento aceptado, no un bug).
- [ ] First-run: el CTA de puesta en marcha navega a `/settings?tab=data` y muestra el panel de
      import (spec actualizado); la ruta `/first-run` ya no existe (retirada) — cualquier URL
      vieja cae por el catch-all a `/dashboard`.
- [ ] Cambio de idioma del shell: el título/cuerpo/botones del widget core se renderizan una vez
      (render imperativo) — verificar si tras cambiar idioma el board re-pinta o queda el texto
      anterior (limitación conocida de los render() imperativos; decidir si molesta).

## 🔴 Hallazgos de la review en vivo (verificar tras su fix o decidir)

1. **Media «Saltado» en el informe de import pese a estar seleccionada.** El motor del runtime
   marca `media` como `Skipped` (la copia la hace el server) y el informe extendido del server
   (`media.copied/failed`) no está sobrescribiendo esa entrada en lo que pinta la UI. Decidir:
   merge del informe server→runtime o mapeo en la UI. (Los ficheros SÍ se copian — verificar
   además que la imagen se sirve desde media tras el import.)
2. **Nombre custom → filename**: en la review, el segundo `fill()` de Playwright sobre el
   `ion-input` del nombre no actualizó el v-model (descargó `hub_es.blueprint.zip` en vez de
   `barberia_es…`). El primer intento SÍ funcionó. Verificar a mano y en el spec: teclear nombre
   → el fichero descargado lo lleva (puede ser artefacto de `fill` vs `ionInput`).
3. **`created_by`/`updated_by` en modo Dev**: con auth Dev, user y hub comparten el literal
   `local`, y el barrido final anti-fuga del export reemplaza TAMBIÉN las columnas de auditoría
   por `__HUB_ID__`. En Session (prod) no pasa (ids reales ≠ hub uuid). Valorar: limitar el
   reemplazo a la columna `hub_id` o aceptar el artefacto dev-only.
4. **Recargas del dev-server** (Vite/WS reconnect) perdían el estado del formulario durante la
   review. Solo entorno dev; confirmar que en build servido por el runtime no ocurre.

## ✅ Flujos a cubrir en la e2e conjunta (Playwright)

- [ ] Home: el widget core «Configura tu hub» aparece por defecto (hub vacío incluido, board con
      solo el core) y ambos CTAs navegan a `/settings?tab=data`.
- [ ] Export (Ajustes → Datos): fila por módulo con checkbox «módulo»+«datos» (datos deshabilitado
      si módulo desmarcado), «Seleccionar todo», secciones usuarios/ajustes/fiscal(OFF+aviso)/media,
      nombre+idioma → filename correcto; descarga con datos reales.
- [ ] Import (Ajustes → Datos): zip local → inspect (resumen manifest + secciones detectadas +
      módulos con «incluye datos») → selección → informe Aplicado/Saltado/Fallido con motivo.
- [ ] Import SELECTIVO: desmarcar usuarios → no crea empleados; solo un módulo → el resto intacto.
- [ ] Best-effort: zip con una sección corrupta → informe la marca en rojo y el resto aplica.
- [ ] Integridad: zip manipulado (sha256 mal) → 422 con mensaje honesto, sin efectos.
- [ ] First-run: hub vacío → CTA lleva a `/settings?tab=data` (ya no instala el módulo `setup`,
      retirado).
- [ ] Fiscal: exportar con fiscal marcado (hub con certificado) → `data/fiscal/certificate.p12`
      en el zip SIN contraseña; import lo reporta `pending` y apunta a `PUT /api/business/certificate`.

## 🚐 Smoke real cross-hub (`/qa-hub`, hubs efímeros REALES en Session mode)

- [ ] Hub A (Session/PIN): configurar → exportar `barberia_es.blueprint.zip`.
- [ ] Hub B vacío: importar → módulos instalados desde el marketplace (versiones del manifest),
      datos bajo el `hub_id` de B, imágenes servidas desde su media.
- [ ] Cross-dialecto: export de hub SQLite (Local) importado en Hub Cloud (Postgres).
- [ ] Auth: sin sesión admin → 401 en los tres endpoints (`/api/hub/export`, `…/import/inspect`,
      `…/import`).

## 📋 Decisiones abiertas que quedaron aplicadas por recomendación (revertibles en review)

- SQL portable único (no por-dialecto) · propiedad de tablas por prefijo `<module>_*` (dueño =
  id más largo) · contraseña del `.p12` NO viaja (se re-teclea en destino) · import v1 pensado
  para hub vacío (re-import idempotente por guard `NOT EXISTS (id, hub_id)`; merge real = futuro)
  · «Desde la nube» deshabilitado hasta que exista el registro/galería en el SaaS ·
  `settings_items` (ajustes ítem a ítem) aceptado por la API pero sin UI de detalle (TODO) ·
  Nombre de la pestaña de Ajustes = **«Datos»/«Data»** (Ioan dijo «setup o como consideres
  mejor»; «Datos» describe import+export y no colisiona con el setup-status de módulos —
  renombrable en un i18n key: `settings.tabData`).

## 🔭 Fuera de esta rama (tandas posteriores ya decididas)

- Distribución: registro `Blueprint` en el SaaS (Django admin + API) + galería «Desde la nube».
- Resurrección de `/solutions/` (Solución = BusinessType + blueprint + bundle de módulos).
- Reutilización del motor por el módulo `backup`.

## ⚠️ Nota de reconciliación con hub#94 (install-progress)

El working tree de esta rama contenía (y ahora COMMITEA) hunks que duplican el PR
[hub#94](https://github.com/ERPlora/hub/pull/94) (MarketplacePage columna Estado, evento WS
`module.install.progress`, install.rs/lib.rs, locales). Al rebasar `feat/export-import-core`
sobre main tras el merge de #94, esos hunks se reconcilian solos o con conflicto trivial.
