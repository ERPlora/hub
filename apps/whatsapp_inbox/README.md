# Bandeja de WhatsApp (`whatsapp_inbox`)

El WhatsApp del negocio dentro del Hub: cada conversación con sus mensajes, fotos, notas de voz y documentos, quién
la lleva, en qué estado está y sus notas internas; contestar con texto libre dentro de las 24 horas o con una plantilla
aprobada fuera de ellas; las plantillas, que se crean, editan y borran desde aquí; el número, que se conecta, se
vuelve a conectar y se desconecta desde Ajustes; y las respuestas automáticas que reservan, cambian o anulan la mesa
de quien escribe tras tu «Aprobar». El Hub nunca habla con Meta: erplora.com es la única pasarela y le empuja lo que
llega por `/internal` (el contrato está en «Para quien lo mantiene» del WORKBOOK).

- **Estado**: completa (2026-11-01): 35 de sus 38 flujos, `WHATSAPP_INBOX-F01` … `F38`, están `hecho`;
  `WHATSAPP_INBOX-F14`, `F21` y `F22` (pedir, mover o anular una cita por WhatsApp) están `descartado` con su issue
  (hub#514).
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones** a `@erplora/ui` que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **El número** (F01, F02, F13): conectarlo con la ventana de Meta, volver a conectarlo o desconectarlo desde
  Ajustes, y ver el consumo del mes con su aviso desde el 80 % y el tope que corta los envíos.
- **La bandeja** (F03–F09, F32–F38): recibir, leer, ver adjuntos, contestar con texto o plantilla, saber si llegó y
  se leyó, asignar, cambiar el estado, dejar notas internas, unir la conversación a una ficha o crearla, y ver quién
  espera respuesta (la campana y los avisos del dispositivo). Lo que se contesta desde el móvil también se ve.
- **Los datos de una persona** (F10–F12): borrar los de un número sin ficha, los de una clienta desde su ficha
  (erplora.com olvida el número) y seguir a la ficha que queda al unir dos.
- **Las plantillas** (F27–F31): verlas con lo que dice Meta, traer las de WhatsApp Manager y crearlas, editarlas o
  borrarlas desde el Hub, con la foto, el vídeo o el documento de la cabecera.
- **Las respuestas automáticas** (F15–F20, F23–F26): **Reservar mesa** contesta sola con el asistente y reserva,
  cambia o anula la mesa de quien escribe tras tu «Aprobar» en «Esperan tu respuesta»; entiende «el 2» de la última
  lista de horas que se le ofreció (F19); cuando no puede contestar, se disculpa y marca la conversación «Necesita
  atención»; y los avisos de la cita y de la mesa confirmadas salen por WhatsApp.

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:chatbubbles-outline` (a la espera de `ion:logo-whatsapp`, `UI-REQUESTS.md`), categoría `organization`, gratuita (`premium = False`) |
| Verticales | `hair_salon` y `restaurant` |
| `requires` | `customer` |
| La usan | Automatizaciones (sus recetas de fábrica: `recipes.py`, y el paso «Mandar un mensaje», FLOW-F31), Citas y Reservas (sus avisos de confirmación), Clientes (la ficha que borra, une o crea), `base` (las puertas `/internal/whatsapp/*` de erplora.com, el Inicio y la campana) |
| Pantallas | `/whatsapp_inbox/inbox` (la bandeja, con la conversación en `?conversation=<id>`) y `/whatsapp_inbox/settings` (el número, el consumo, las respuestas automáticas y las plantillas) |
| Operaciones | 13 consultas (`queries.py`) y 35 acciones (`services.py`), todas con `ai=`; las que llama erplora.com o el sistema, con `ai=INTERNAL` |
| Permisos | `view`, `reply`, `assign`, `configure` y `erase` (`whatsapp_inbox.*`); el empleado lee y contesta |
| Hooks del Inicio | `bell` «Clientes de WhatsApp esperando respuesta» y `notices` (un aviso del dispositivo por cliente sin contestar), con `conversation.count_awaiting_reply` y `conversation.notices` |
| Tarea programada | `whatsapp_inbox.delivery.resume`, cada 5 minutos: vuelve a dar a erplora.com los mensajes, borrados, plantillas y borrados de plantillas cuya entrega tras el COMMIT no terminó |
| Eventos | 18, `whatsapp_inbox.<entidad>.<hecho>` (`events.py`), solo con identificadores |
| Migraciones | `0001_initial` … `0010_hub_users` |
| Admin | Django admin de conversaciones, mensajes, notas, plantillas y canal en `hubs.erplora.com` (PLAN §17–§18) |

Las decisiones de diseño (el contrato con erplora.com, las puertas, el modelo, la retención y las respuestas
automáticas) están en «Para quien lo mantiene» del WORKBOOK; las de la migración, en la ronda de
CLOSE-WHATSAPP_INBOX de `PLAN-HUB.md` (raíz de erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/whatsapp_inbox base/tests/test_internal_whatsapp.py
pnpm test apps/whatsapp_inbox
pnpm e2e tests/e2e/whatsapp-inbox.spec.ts tests/e2e/whatsapp-inbox-erplora.spec.ts tests/e2e/whatsapp-internal.spec.ts \
  tests/e2e/whatsapp-inbox-offered-options.spec.ts tests/e2e/fix-whatsapp-inbox-table-cancel.spec.ts
```

- Las e2e de WhatsApp usan el erplora.com de la pila y el Graph de Meta de la ejecución, y las de respuestas
  automáticas, además, el proveedor falso del asistente: `tests/e2e/README.md`, «WhatsApp» y «El asistente».
- `test_relay_auto_replies.py` lleva las respuestas automáticas de punta a punta por el relevo real del worker,
  el motor de Automatizaciones y las puertas de erplora.com (`base.tests.fake_gateway`), con el asistente
  guionizado: la mesa reservada, cambiada o anulada tras el «Aprobar», nunca en la ficha de otra persona, y el
  «el 2» de la última lista ofrecida.
- `test_services_*.py` llevan cada acción con sus errores; `test_concurrency.py`, las carreras de la entrega.

## Qué queda fuera

- `WHATSAPP_INBOX-F14`, `F21` y `F22` (pedir, mover o anular una cita por WhatsApp, hub#514), los textos de
  hub#569, hub#570 y hub#571, y los iconos y el hilo de chat pedidos a `@erplora/ui`: «Lo que queda fuera» del
  WORKBOOK y [`UI-REQUESTS.md`](UI-REQUESTS.md).
- Relacionada, de otras apps: el Inicio no dice de un vistazo si WhatsApp funciona (hub#573, BASE-F02).
