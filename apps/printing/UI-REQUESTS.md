# Peticiones de UI de la app `printing`

Lo que las páginas de Impresión necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo más
parecido que ya existe; se cambia en cuanto llegue.

## Iconos

- `ion:print-outline` — icono del módulo (`apps.py`: `icon`), entrada de menú y pestaña **Impresoras**
  (`frontend/tabs.ts`), acción «Probar» de la tabla y cabecera de los ajustes. Es el icono del producto
  actual (`print`; Caja, Facturación y Ventas lo piden también). Hoy: `lucide:receipt`.

Al registrarlo, cambiar a la vez `apps.py` (`icon` y `navigation`), `frontend/tabs.ts`, la acción `test`
de `frontend/pages/PrintersPage.vue`, `frontend/components/SettingsCard.vue`, su test
(`tests/test_apps.py`, `frontend/tabs.test.ts`) y regenerar `pnpm gen:app-icons`.

## Puente con la app nativa (bloque 6)

- **Qué**: el puente JavaScript de la app Tauri en `packages/ui` (`device.ts`, `bridge-transport.ts`,
  `print*.ts`): buscar impresoras (`erplora_discover_printers`), añadir por IP (`erplora_add_network_printer`)
  y el cliente de `/ws/print` que recoge y confirma los trabajos (`printing.job.claim`, `complete`, `fail`).
- **Uso**: PRINTING-F02 (buscar sin escribir la dirección) y PRINTING-F18 (sacar el papel). El contrato está
  en `WORKBOOK.md` «Contrato con la plataforma».

## App nativa (`app/`, otro carril)

- **Ancho del papel**: `crates/peripherals/src/escpos.rs` fija `LINE_WIDTH = 32` para todo papel. El trabajo
  ya trae `paper_width` (58 u 80) en la respuesta de `printing.job.claim`; se pide que `erplora_print` lo
  tome (o un `columns` en `data`: 32 en 58 mm, 48 en 80 mm) para que una impresora de 80 mm use su ancho.
- **Nombre del negocio en la hoja de prueba**: no hace falta cambio. `render_test_page` ya pinta
  `business_name` cuando viene en `data` (si no, «ERPlora»); Impresión lo manda desde Facturación
  (`invoice.issuer.get`). Solo comprobarlo en el bloque 6 con papel real.
