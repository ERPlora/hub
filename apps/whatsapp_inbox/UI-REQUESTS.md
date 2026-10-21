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

## Adjuntos dentro del hilo (CSP)

- **Qué**: para enseñar fotos y reproducir notas de voz y vídeos dentro del hilo (WHATSAPP_INBOX-F06,
  como el producto actual), la CSP del Hub tiene que permitir el origen de erplora.com en `img-src` y
  `media-src` (en `config/settings.py`, como ya hace con `form-action`), o `packages/live` añadir
  `media-src 'self' blob:` si se sirven por el Hub.
- **Hoy**: el adjunto se abre en una pestaña nueva servida por erplora.com («Abrir el adjunto»).

## Ventana de Meta para conectar el número (COOP)

- **Qué**: para que la ventana de Meta que abre **Conectar WhatsApp** (WHATSAPP_INBOX-F01, F02) pueda
  devolver su resultado a Ajustes, las páginas del Hub no pueden cortar las ventanas que abren:
  `SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin-allow-popups"` en `config/settings.py` (hoy, el
  `same-origin` de Django por defecto). Y de erplora.com, la página a la que Meta devuelve el código
  (WORKBOOK, «Contrato con el SaaS», puertas 10 y 11).
- **Hoy**: **Tu número** dice «Todavía no se puede conectar el número desde aquí.» en vez de ofrecer
  **Conectar WhatsApp**; **Desconectar** sí funciona.

## Muestra de la cabecera de una plantilla (archivo)

- **Qué**: para crear desde el Hub plantillas con foto, vídeo o documento en la cabecera
  (WHATSAPP_INBOX-F29; el producto actual lo hacía), la plataforma tiene que ofrecer subir un archivo
  (almacenamiento y una ruta de subida fuera de una operación con transacción) que erplora.com entregue a
  Meta como muestra.
- **Hoy**: esas plantillas se hacen en WhatsApp Manager; en **Ajustes → Plantillas de Meta** se ven, pero
  no se editan ni se ofrecen para enviar.
