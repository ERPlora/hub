# Automatizaciones (`flow`)

Las **reglas que trabajan solas** del negocio: «cuando pase esto, haz aquello», a una hora, en una fecha o a mano.
Una automatización es una columna de pasos (hacer algo en otra app, consultar, «solo sigue si…», esperar, mandar
un WhatsApp al cliente, llamar a otro sistema, preguntar antes a alguien o pedírselo al asistente), con sus propios
permisos, que se prueba sin efectos antes de encenderla y que cuenta en palabras qué hizo cada vez. La app es la
pantalla **y** el motor que las ejecuta. Sirve igual a la peluquería y al restaurante.

- **Estado**: completa (2026-11-01): los 39 flujos `FLOW-F01` … `F39` están `hecho`. Del registro de la migración,
  los `FLOW-G…` (el mismo flujo visto desde el Hub viejo o el módulo viejo) están `descartado` como duplicados de
  su `FLOW-F…`.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta
  «Para quien lo mantiene»). Lo que se cambie de la app se cambia antes allí.
- **Peticiones a `@erplora/ui`** que siguen abiertas (iconos): [`UI-REQUESTS.md`](UI-REQUESTS.md).

## Qué hace hoy

- **Lista y galería** (F01–F08): las automatizaciones del negocio con su búsqueda y su orden, encender o pausar una
  o varias, crear desde una tarjeta de la galería (o llegar a ella desde otra app), copiar, borrar y la guía.
- **Editor** (F09–F15): crear desde cero, elegir cuándo arranca (un aviso del negocio, un horario, una fecha o a
  mano), añadir, ordenar y rellenar los pasos con datos de antes, conceder los permisos, probar sin efectos,
  guardar, encender y ejecutar a mano.
- **Historial** (F16, F24): qué hizo cada ejecución y por qué falló, en palabras, y reanudar desde el paso que falló.
- **Asistente** (F17–F19, F37–F39): pedirle una automatización (deja un borrador que se revisa y se crea o se
  descarta), el paso «Pedírselo al asistente» y el asistente que lo hace dentro de una ejecución, atendido por el
  SaaS.
- **Motor** (F20–F23, F25): arrancar con un aviso del negocio o a su hora, seguir tras una espera, «Solo si…» y
  «Si falla, sigue» en cada paso; otra app pregunta si una automatización suya ya está montada.
- **Secretos y otros sistemas** (F26, F27): secretos que no se pueden volver a leer y la llamada a otro sistema, con
  su protección de red y sin repetirla dos veces.
- **Preguntar antes** (F28–F30): la pregunta a un rol del negocio, contestarla desde la bandeja «Esperan tu
  respuesta» y cerrar lo que nadie contestó a tiempo.
- **WhatsApp al cliente** (F31, F32): el paso «Enviar un mensaje» a la conversación del número exacto, texto en las
  24 horas y plantilla aprobada fuera, también con la foto, el vídeo o el PDF de su cabecera.
- **Recetas de otras apps** (F33–F36): encender, pausar sin borrar, restaurar la versión de fábrica y reparar una
  automatización que trae otra app (hoy, Citas, Reservas online y Bandeja de WhatsApp).

## Ficha

| Qué | Valor |
|---|---|
| `LiveAppConfig` | `kind = "app"`, icono `ion:sync-outline` (el `git-branch` del módulo viejo espera en `UI-REQUESTS.md`), categoría `organization`, gratuita (`premium = False`) |
| Verticales | `hair_salon` y `restaurant` |
| `requires` | `[]`: las acciones y consultas de otras apps se llaman por el nombre de su operación, nunca por sus modelos |
| Permisos | `flow.view`, `flow.manage` (dueño y administrador: `flow.*`), `flow.answer` (empleado) y `flow.answer_manager` (encargado) |
| Pantallas | `/flow/automations`, `/flow/automations/new`, `/flow/automations/:id` y `/flow/guide` |
| Operaciones | 15 consultas (`queries.py`) y 28 acciones (`services.py`), todas con `ai=`; 31 rutas en `/api/flow/…` (`api.py`) |
| Eventos | 18 propios (`flow.flow.*`, `flow.run.*`, `flow.draft.*`, `flow.secret.*` y `flow.question.*`; `events.py`); reacciona a los avisos de todas las apps activas (FLOW-F21) y a su propio `flow.run.parked` (FLOW-F27) |
| De otras apps | el paso «Enviar un mensaje» usa las plantillas, los archivos de cabecera y el envío estrecho de la Bandeja de WhatsApp (`whatsapp_inbox.*`, por nombre) |
| Migraciones | `0001_initial` … `0006_flowrun_error_reason` |
| Admin | Django admin en `hubs.erplora.com`: automatizaciones, ejecuciones, borradores, preguntas y secretos (sin su valor) |

Las decisiones de diseño (una columna sin bifurcaciones, permisos por automatización releídos en cada paso, lo que
nunca se automatiza, los secretos de solo escritura, las esperas y los avisos tras el COMMIT…) están en «Para quien
lo mantiene» del WORKBOOK; las de la migración, en la ronda de cierre de Automatizaciones de `PLAN-HUB.md` (raíz de
erplora-next).

## Tests

```bash
cd hub   # o tu worktree
TEST_DB_NAME=test_hub_<tema> uv run pytest -q apps/flow
pnpm test apps/flow
CI=1 pnpm e2e tests/e2e/flow-flows.spec.ts tests/e2e/flow-steps.spec.ts tests/e2e/flow-send-message.spec.ts
```

- `test_integration_apps.py` y `test_integration_assistant.py` van contra las apps reales y el asistente;
  `test_concurrency.py`, con hilos, que un aviso, un horario o una espera arrancan una sola vez y que borrar a la
  vez nunca da un error del servidor; `test_field_words.py` exige que cada
  dato de una operación tenga su palabra `flow.fields.<campo>` en `en` y `es`.
- 15 specs `tests/e2e/flow-*.spec.ts` y `fix-*flow*.spec.ts` (lista y galería, pasos, recetas, relevo, asistente,
  WhatsApp con el Graph de Meta de la e2e…); las de WhatsApp necesitan el SaaS de la pila (`tests/e2e/README.md`).

## Qué queda fuera

- **hub#497**, **hub#498**, **hub#499** y **hub#504** — fallos vistos en la migración: textos en español con las
  palabras de otra app, el importe de un paso que cobra que no se dice como dinero, y la tarjeta del asistente que
  llama «Registro» a la automatización o dice «N elementos» en sus permisos.
- Trabajo encolado del carril: la reanudación de una ejecución aparcada, y que un paso pueda pedir, confirmar, mover
  o anular una cita (hub#514 espera a lo primero de Citas).
- Lo que no hace a propósito (bifurcaciones, lienzo de nodos, encender o conceder sin confirmarlo, automatizar lo que
  necesita a una persona delante…) y lo demás que queda fuera: «Lo que NO hace, a propósito» y «Qué queda fuera» del
  WORKBOOK.
