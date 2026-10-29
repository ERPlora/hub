# Peticiones de UI de la app `whatsapp_inbox`

Lo que las páginas de la Bandeja de WhatsApp necesitan de `@erplora/ui` (o de la plataforma) y todavía
no está. Mientras tanto usan lo más parecido que ya existe (dicho en cada punto); se cambia en cuanto
llegue.

## Iconos

- `ion:logo-whatsapp` — icono del módulo (`apps.py` `icon`), entrada de menú y pestaña **Bandeja de
  entrada** (`frontend/tabs.ts`). Es el del bloque de ajustes del producto actual. Hoy:
  `ion:chatbubbles-outline` (el de la navegación del producto actual).
- `ion:send-outline` — botón **Enviar** del cuadro de respuesta (`components/MessageComposer.vue`).
  Hoy: botón solo con texto.
- `ion:attach-outline`, `ion:image-outline`, `ion:document-outline`, `ion:play-outline` — tipo de
  adjunto en la burbuja (`components/ThreadView.vue`). Hoy: el tipo escrito («Foto», «Documento»…).

Al registrar `logo-whatsapp`, cambiar a la vez `apps.py` (`icon` y `navigation`), `frontend/tabs.ts`,
`tests/test_apps.py` y `pnpm gen:app-icons`; `tabs.test.ts` exige que menú y pestañas lleven el mismo
icono.

## Hilo de mensajes (`ChatThread`)

- **Qué**: un componente de hilo de chat (burbujas a izquierda y derecha, notas, hora, estado de
  entrega, «Ver anteriores», desplazamiento al último) para `@erplora/ui/components`: lo usarán también
  el asistente y cualquier canal (correo, SMS).
- **Hoy**: `components/ThreadView.vue`, propio de esta app.
