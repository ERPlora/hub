# Recorridos de QA del Hub

La funcionalidad del Hub se describe en un solo sitio: el `WORKBOOK.md` de cada app (`base/WORKBOOK.md` y
`apps/<app>/WORKBOOK.md`), con sus flujos `### <APP>-F<nn>`. La QA no la vuelve a describir: recorre **recorridos**,
lo que hace una persona real en una sesión de trabajo mezclando apps (abrir la caja y servir las comidas, cerrar el
día, preparar la carta, dar citas…), y cada paso de un recorrido solo **cita** los flujos que se hacen en él.

## Qué hay aquí

- `journeys/<recorrido>.md`: un recorrido por fichero. El nombre del fichero va en inglés y el contenido en español.
- Este README, que es el contrato.

## El formato de un recorrido

```markdown
---
title: Apertura y servicio de comidas
vertical: restaurant
roles: responsable, empleado
---

Para qué: abrir el local, servir las mesas del mediodía y cobrar.

## Punto de partida

- Lo que deja `restaurant-menu-setup.md`: la carta con suplementos y un menú del día.
- Una reserva confirmada para las 14:00 (`restaurant-reservations.md`).

## Recorrido

1. BASE-F55 — el responsable entra con su PIN en la tableta de la barra.
2. CASH_REGISTER-F03 — fondo de 150,00 €.
3. TABLE-F10, SALE-F19 — mesa 4, tres comensales.
```

- **Cabecera** entre dos líneas `---`, con tres claves `clave: valor` y ninguna vacía:
  - `title`: lo que hace la persona, dicho como lo diría ella;
  - `vertical`: el tipo de negocio que declaran las apps (`restaurant`, `hair_salon`) o `any` si vale para cualquiera;
  - `roles`: quién actúa, separado por comas (`propietario`, `administrador`, `responsable`, `empleado`, `cliente
    (sin sesión)`…).
- **Una línea `Para qué: …`** antes de las secciones.
- **Dos secciones, en este orden y ninguna más:**
  - `## Punto de partida`: el estado del negocio que hace falta antes de empezar; puede apuntar a lo que deja otro
    recorrido.
  - `## Recorrido`: los pasos numerados desde 1, uno por línea, con la forma `<n>. <ID>[, <ID>…][ — <nota>]`.
- **Un paso empieza siempre por el ID de uno o más flujos.** Varios IDs en un paso, separados por coma, se hacen en el
  mismo gesto (cobrar en efectivo y que salga el tique y se abra el cajón).
- **La nota es solo lo propio del recorrido:** el dato que se arrastra de un paso a otro («mesa 4», «la reserva de las
  14:00»), quién actúa si no es el de siempre y por qué el paso va ahí. **Nunca copia los pasos, las pantallas ni los
  textos del WORKBOOK**: lo que hay que hacer y lo que tiene que pasar se leen en el flujo citado.
- Un recorrido solo cita flujos con `Estado: hecho`. Un mismo flujo puede salir en varios recorridos.

## Qué juzga la QA en cada paso

1. **Que funciona:** el flujo citado hace lo que dice su WORKBOOK, también su «Si falla».
2. **Que se ve bien** en escritorio, tableta y móvil: nada cortado ni fuera de sitio, sin textos en el otro idioma.
3. **Que tiene sentido para el usuario:** el paso se entiende sin ayuda y encaja con el anterior y el siguiente.

Un defecto se abre como issue en el repo del Hub, con el ID del flujo y el paso del recorrido en el que salió.

## Por pantalla o hablando con el asistente

El mismo recorrido, en el mismo orden, se hace por pantalla o pidiéndole cada paso al asistente. No hay recorridos
aparte para el asistente: `journeys/assistant.md` prueba su propio panel. Cuando se hace hablando:

- **Cada paso se pide como lo pediría quien actúa en él**, en español o en inglés, con la frase entera o a medias a
  propósito. Las frases no se guardan en el recorrido: las escribe quien prueba, como lo diría el dueño o el empleado,
  sin nombrar herramientas, pantallas ni campos.
- **Con la frase a medias, lo correcto es que el asistente pregunte** lo que falta antes de hacer nada.
- **En un flujo que el asistente no hace, lo correcto es que lo diga** y mande a la pantalla donde se hace; quien prueba
  lo hace entonces en pantalla, para que el recorrido siga. Qué hace el asistente en cada flujo lo dice
  `manage.py qa_coverage --assistant` (más abajo).
- **El resultado se comprueba en pantalla o en los datos**, nunca en lo que contesta el asistente.

## La cobertura

```bash
uv run python manage.py qa_coverage
uv run python manage.py qa_coverage --ledger ~/qa/walks.csv
uv run python manage.py qa_coverage --assistant
```

- Sin opciones dice, por app, qué flujos hechos con pantalla están en algún recorrido, cuáles en ninguno y cuáles
  quedan **fuera del alcance visual**: los que no están `hecho` y los de `Pantalla: ninguna…`, que hace el sistema
  solo (su efecto se comprueba en el paso del recorrido que lo provoca).
- Con `--ledger` cruza con el **registro de pasadas**, un CSV que vive fuera del repo con una fila por flujo recorrido,
  y dice, para la pantalla y para el asistente, qué flujos no se han recorrido nunca así y cuándo fue la última pasada
  de los demás en cada canal, empezando por los más antiguos.

| Columna | Qué lleva |
|---|---|
| `flow` | el ID del flujo; también los de erplora.com y la aplicación, que el comando solo nombra al final |
| `date` | el día de la pasada, `AAAA-MM-DD` |
| `device`, `app_version` | dónde se hizo y con qué versión |
| `result` | `ok`, `partial` o `fail`: si el flujo hizo lo que dice su WORKBOOK; vacía si no llegó a hacerse |
| `issue` | la issue del defecto, `repo#N`, o vacía |
| `channel` | por dónde se hizo: `screen`, `assistant-es` o `assistant-en` |
| `phrase` | la frase, `whole` (entera) o `partial` (a medias); vacía en pantalla |
| `model_result` | `ok`, `partial` o `fail`: si el modelo entendió, preguntó cuando debía o mandó a la pantalla correcta; vacía en pantalla |

El comando se para si al registro le falta una columna y, diciendo la línea, si una fecha no es `AAAA-MM-DD` o un canal
no es uno de los tres.

- Con `--assistant` dice, por flujo hecho con pantalla, su grupo, lo que se espera al pedirlo hablando y las operaciones
  que lo respaldan, con las que son herramientas del asistente marcadas (`tool`). No hay lista escrita a mano: las
  operaciones de un flujo son las de las filas que lo nombran en la columna `Flujos` de las tablas de servicios de los
  WORKBOOK, y qué es herramienta lo dice el registro de operaciones.

| Grupo | Cuándo | Qué se espera al pedirlo hablando |
|---|---|---|
| `can` | alguna de sus escrituras es herramienta, o solo lee y todas sus lecturas lo son | lo hace, y se comprueba en pantalla o en los datos |
| `assistant only` | `Pantalla:` nombra solo al asistente | lo mismo, y no hay otro camino |
| `cannot` | cualquier otro | dice que no lo hace él y en qué pantalla se hace |

Después da lo que queda por escribir en los WORKBOOK, en tres listas: los flujos sin decidir, porque no se conoce
ninguna de sus operaciones; los que se contradicen, y las herramientas que no cita ningún flujo. Un flujo se contradice
si `Actor:` nombra al asistente y ninguna de sus operaciones es herramienta, o si lo nombra `Pantalla:` y las que se
conocen no son herramientas ni las del propio panel del asistente. Que el asistente pueda hacerlo y `Actor:` no lo nombre
no es una contradicción: lo dice su grupo.

## Cómo se mantiene

**Quien añade, borra o cambia un flujo de un WORKBOOK actualiza los recorridos en el mismo cambio.** Lo exige
`tests/test_qa_coverage.py`, que falla si:

- un recorrido cita un ID que no existe en ningún WORKBOOK o que no está `hecho`;
- un flujo `hecho` con pantalla no está en ningún recorrido;
- un recorrido no sigue el formato de arriba.

Un flujo nuevo entra en el recorrido en el que lo haría una persona, en su sitio dentro de la sesión; si ninguno
encaja, se escribe un recorrido nuevo.
