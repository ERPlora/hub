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

- **Hecho aquí**: buscar impresoras (PRINTING-F02) llama a `erplora_discover_printers` con el puente global
  de Tauri desde `frontend/lib/discovery.ts`; la impresora encontrada se da de alta en el servidor
  (`printing.printer.create`), no con `erplora_add_network_printer`. Si el puente de `packages/ui` llega,
  `discovery.ts` pasa a usarlo sin cambiar lo que ve la persona.
- **Qué falta**: el cliente de `/ws/print` en `packages/ui` (`device.ts`, `bridge-transport.ts`, `print*.ts`)
  que recoge y confirma los trabajos (`printing.job.claim`, `complete`, `fail`) y se los pasa a
  `erplora_print`. Su `deviceId` es el mismo `X-Device-Id` del SDK (`erplora.device_id`): solo recoge un
  dispositivo dado de alta en **Impresión → Dispositivos** (PRINTING-F18), y sus impresoras son las de su alta
  (`printing.device.list`, fila `this_device`); y la entrada de las apps por erplora.com que vincula la app al negocio (sin ella, la
  búsqueda contesta `not_the_linked_hub` y la ventana lo dice).
- **Uso**: PRINTING-F02 y PRINTING-F18 (sacar el papel). El contrato está en `WORKBOOK.md` «Contrato con la
  plataforma».

## App nativa (`app/`, otro carril)

- **Ancho del papel**: `crates/peripherals/src/escpos.rs` fija `LINE_WIDTH = 32` para todo papel. El trabajo
  ya trae `paper_width` (58 u 80) en la respuesta de `printing.job.claim`; se pide que `erplora_print` lo
  tome (o un `columns` en `data`: 32 en 58 mm, 48 en 80 mm) para que una impresora de 80 mm use su ancho.
- **Nombre del negocio en la hoja de prueba**: no hace falta cambio. `render_test_page` ya pinta
  `business_name` cuando viene en `data` (si no, «ERPlora»); Impresión lo manda desde Facturación
  (`invoice.issuer.get`; la hoja A4 de la impresora del equipo la firma el servidor, con su test). Solo
  comprobarlo en el bloque 6 con papel real.
