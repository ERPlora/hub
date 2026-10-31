# Peticiones de UI de la app `printing`

Lo que las páginas de Impresión necesitan de `@erplora/ui` o de la app nativa y todavía no está. Mientras
tanto usan lo más parecido que ya existe; se cambia en cuanto llegue. Revisado el 2026-10-31 (CLOSE-PRINTING)
contra `@erplora/ui` `origin/main` `667b7fb` y `ERPlora/app` `origin/main` `da472ca`.

## Iconos

- `ion:print-outline` — icono del módulo (`apps.py`: `icon`), entrada de menú y pestaña **Impresoras**
  (`frontend/tabs.ts`), acción «Probar» de la tabla, cabecera de los ajustes y, en el Inicio, el paso
  «Configura la impresora» y las filas «Nadie está imprimiendo «…»» de la campana (`apps.py`: `setup` y
  `bell`; el viejo pintaba ahí `print-outline`). Es el icono del producto actual (`print`; Caja, Facturación
  y Ventas lo piden también). Hoy: `lucide:receipt`. Sigue sin estar en `packages/ui/src/shell/icons.ts`
  (solo `finger-print-outline`).

Al registrarlo, cambiar a la vez `apps.py` (`icon`, `navigation`, `setup` y `bell`), `frontend/tabs.ts`, la
acción `test` de `frontend/pages/PrintersPage.vue`, `frontend/components/SettingsCard.vue`, sus tests
(`tests/test_apps.py`, `tests/test_integration_home.py`, `frontend/tabs.test.ts`) y regenerar `pnpm gen:app-icons`.

## App nativa (`ERPlora/app`, otro carril)

- **Ancho del papel**: `crates/peripherals/src/escpos.rs` fija `LINE_WIDTH = 32` para todo papel. El trabajo
  ya trae `paper_width` (58 u 80) en la respuesta de `printing.job.claim`; se pide que `erplora_print` lo
  tome (o un `columns` en `data`: 32 en 58 mm, 48 en 80 mm) para que una impresora de 80 mm use su ancho.
  Mientras tanto, «Nueva impresora» lo dice bajo «Ancho de papel».
- **Buscar en una red sin salida a internet** (PRINTING-F02): app#17.

## Ya resuelto (fuera de la lista)

- **El cliente de `/ws/print`** que recoge y confirma los trabajos: `print-channel.ts` del SDK y
  `device-printer.ts` y `print-host.ts` del shell de `@erplora/ui`, montados por `frontend/components/PrintHost.vue`
  (PRINTING-F18; WORKBOOK, «Contrato con la plataforma», punto 7).
- **La entrada de las apps por erplora.com** que vincula la app nativa al negocio: el SaaS abre el negocio desde
  la app con `?shell=1` (`/shell/`, saas#66) y la app lo vincula (`hub_link.rs`); otro negocio sigue recibiendo
  `not_the_linked_hub`, y la ventana de «Buscar impresoras» lo dice.
- **El puente de la app en `@erplora/ui`** (`nativeBridge` de `@erplora/ui/shell`): `frontend/lib/discovery.ts`
  conserva su `nativeInvoke`, que lee el mismo `window.__TAURI__.core.invoke` y solo necesita eso; no hace falta
  cambio.
- **Nombre del negocio en la hoja de prueba**: no hace falta cambio. `render_test_page` ya pinta
  `business_name` cuando viene en `data` (si no, «ERPlora»); Impresión lo manda desde Facturación
  (`invoice.issuer.get`; la hoja A4 de la impresora del equipo la firma el servidor, con su test). Verlo con
  papel real es del QA en el dispositivo.
