# TO_CHECK — Export/Import del hub (ADR-0113) · pendientes de verificar en las e2e

> Lista de verificación para la revisión e2e (Playwright + `/qa-hub`) posterior al merge de
> `feat/export-import-core`. Lo ya verificado en vivo (2026-07-12, runtime real + Vite) fue:
> widget de home → `/export` (selección dinámica, descarga `*.blueprint.zip` con datos reales,
> placeholder `__HUB_ID__`) → `/import` (upload → inspect → informe con Usuarios/Ajustes/taxes/
> inventory **Aplicado**). Suites: runtime 13/13 · server 22/22 · typecheck OK.

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

- [ ] Home: el widget core «Configura tu hub» aparece SIEMPRE (hub vacío incluido) y navega a
      `/import` y `/export`.
- [ ] `/export`: fila por módulo con checkbox «módulo»+«datos» (datos deshabilitado si módulo
      desmarcado), «Seleccionar todo», secciones usuarios/ajustes/fiscal(OFF+aviso)/media,
      nombre+idioma → filename correcto; descarga con datos reales.
- [ ] `/import`: zip local → inspect (resumen manifest + secciones detectadas + módulos con
      «incluye datos») → selección → informe Aplicado/Saltado/Fallido con motivo.
- [ ] Import SELECTIVO: desmarcar usuarios → no crea empleados; solo un módulo → el resto intacto.
- [ ] Best-effort: zip con una sección corrupta → informe la marca en rojo y el resto aplica.
- [ ] Integridad: zip manipulado (sha256 mal) → 422 con mensaje honesto, sin efectos.
- [ ] First-run: hub vacío → CTA lleva a `/import` (ya no instala el módulo `setup`, retirado).
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
  `settings_items` (ajustes ítem a ítem) aceptado por la API pero sin UI de detalle (TODO).

## 🔭 Fuera de esta rama (tandas posteriores ya decididas)

- Distribución: registro `Blueprint` en el SaaS (Django admin + API) + galería «Desde la nube».
- Resurrección de `/solutions/` (Solución = BusinessType + blueprint + bundle de módulos).
- Reutilización del motor por el módulo `backup`.
- Retirada física de `FirstRunPage`/guard si se decide (hoy solo redirige a `/import`).
