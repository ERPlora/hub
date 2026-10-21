# Workbook — Tareas (app)
Prefijo: TASK
Alcance MVP: transversal (peluquería y restaurante: la lista de cosas por hacer del equipo)
Estado de la app: completa (2026-10-21)
Lo que no entra todavía: ver «Lo que NO hace, a propósito».

> Manual de usuario y especificación de la app `task`. Se escribe **antes** que el código: no se
> programa nada que no esté aquí, y cada flujo pasa a `hecho` cuando sus tests están en verde (servidor
> y páginas). Parte del `WORKFLOW.md` del módulo Tareas del producto actual
> (`modules-workspace/modules/tasks`, `origin/main` `99f1c53`, v1.0.31). Hace lo mismo, se ve igual y
> conserva toda su funcionalidad salvo lo que dice «Cambios frente al producto actual», al final.

## Para qué sirve y para quién

Tareas es la **lista de cosas por hacer del equipo**: «limpiar el almacén», «pedir tinte rubio»,
«revisar la cámara frigorífica». Cada tarea tiene un título, una prioridad, una fecha límite y una
persona del equipo que se encarga; se agrupan en **proyectos** («Apertura del local», «Reforma de
verano»), se parten en **subtareas** y llevan un hilo de **comentarios**.

Es para el personal, no para los clientes: una incidencia de un cliente no es una tarea.

Quién la usa:

- El **propietario**, el **administrador** y el **responsable** ven y cambian **todas** las tareas,
  las asignan, las borran y llevan los proyectos.
- El **empleado** ve y cambia **las suyas**: las que tiene asignadas y las que ha creado él. Puede
  crear tareas (también para un compañero), empezarlas, completarlas, comentarlas y añadirles
  subtareas.
- **Automatizaciones** crea tareas cuando el negocio se lo permite: por ejemplo, las automatizaciones
  que traen **Citas** (una clienta cancela y queda una tarea para llenar el hueco) y **Reservas online**
  (entra una reserva y queda una tarea para revisarla).

El asistente lo usa por voz o por texto con la sesión de quien habla: «crea una tarea limpiar el
almacén para mañana y asígnala a Ana», «¿qué tareas tengo?», «completa la tarea limpiar almacén»,
«¿qué falta del proyecto apertura?».

## Referencia adoptada

**A quién se asigna una tarea y qué ve el empleado** (skill `market-decision`, 2026-10-14). En el
producto actual el responsable era una referencia de texto a un usuario del hub, sin vínculo con
Personal, y todos veían y cambiaban todo.

| Producto | Cómo lo resuelve | Fuente |
|---|---|---|
| Homebase | El responsable asigna tareas a personas, roles o al equipo, con fecha límite; cada empleado ve las suyas en la app | https://www.joinhomebase.com/industry/restaurant-task-management-app |
| 7shifts (7tasks) | Una tarea va a **un** empleado; si deja el turno, la tarea se desasigna y vuelve al equipo; solo el responsable crea y edita listas | https://kb.7shifts.com/hc/en-us/articles/32167431828243 |
| Deputy | «Tarea para otra persona»: título, miembro del equipo, fecha límite opcional; los grupos de tareas solo los crea el responsable | https://help.deputy.com/hc/en-au/articles/4689381399823 |
| Connecteam | Tareas a uno o varios empleados; el responsable gestiona las de su equipo y recibe aviso al verlas y completarlas | https://connecteam.com/task-management-app/ |
| Todoist | Un solo responsable por tarea, elegido entre los miembros del proyecto | https://todoist.com/help/articles/how-to-collaborate-with-others |
| Jira | El responsable es un usuario; se puede limitar que cada uno vea solo lo asignado o lo que reportó | https://support.atlassian.com/jira/kb/limit-users-to-only-browse-issues-assigned-to-reported-by-them-in-jira-cloud/ |
| Odoo Proyecto | Por defecto un usuario ve todas las tareas del proyecto; limitarlo a «las mías» lo piden en el foro y lo resuelven módulos de terceros | https://odoo.com/es/forum/ayuda-1/show-task-to-assigned-user-only-in-odoo-v15-199206 · https://apps.odoo.com/apps/modules/17.0/project_task_own_access |
| Business Central | El trabajo de un proyecto se asigna a recursos (personas) en las líneas de planificación | https://docs.staedean.com/business-central/docs/bc-create-resource-tasks |
| Square (foro) | Una lista «de todos» no la cumple nadie: hace falta un responsable por tarea | https://community.squareup.com/t5/Food-and-Beverage/What-is-everyone-using-for-managing-team-tasks/m-p/636031 |
| Asana (foro) | Borrar una tarea madre borra sus subtareas | https://forum.asana.com/t/automatically-deleting-subtasks-when-a-parent-task-is-deleted/627538 |

**Gana:** una tarea tiene **un** responsable, que es **una persona del equipo** (su ficha de Personal),
como en Homebase, 7shifts, Deputy, Todoist y Business Central; quien deja el equipo deja sus tareas
abiertas sin responsable (7shifts). El **empleado ve y cambia las suyas** (asignadas o creadas por
él) y el **responsable, todas**, que es lo que hacen las apps de equipos de sala y salón (Homebase,
7shifts, Deputy, Connecteam) y lo que en Odoo y Jira se acaba configurando a mano.
**Por qué las demás no:** el usuario de la cuenta no sirve, porque un profesional sin cuenta (el
caso normal en un salón) no podría tener tareas; «todos ven todo» no deja a nadie como dueño de la
tarea (foro de Square); varios responsables por tarea complica la lista sin que lo pida ningún
producto de este tamaño.

## Antes de empezar

1. Tareas necesita **Personal**: se asigna a fichas del equipo. Da de alta a las personas en
   **Personal** y, si van a entrar al Hub, vincula su ficha con su cuenta: así cada una ve «Mis
   tareas».
2. Si quieres agrupar, crea los **proyectos** en **Tareas → Proyectos** (TASK-F12).
3. «Hoy» (vencida, vence hoy, el número del día) es el día del negocio: en la fase 1, la zona
   horaria del Hub, **Europe/Madrid**.

## Pantallas

Tareas se abre desde el menú **Tareas** y tiene dos pestañas: **Tareas** y **Proyectos**. Lo que una
persona no puede hacer no aparece, y la app lo rechaza aunque lo intente por la API o por el
asistente.

### Tareas
Arriba, el selector **Todas / Mis tareas** («Mis tareas» solo sale a quien tiene ficha vinculada).

**Todas**: tabla con buscador «Buscar nº o título…» (nº, título, descripción, responsable o
proyecto), columnas **Nº, Título, Estado, Prioridad, Vence** y **Responsable**; **Proyecto** existe
pero sale oculta. Se ordena por cualquier columna (por defecto, las más nuevas primero) y se filtra
por Nº, Título, Estado, Prioridad (las dos eligiendo de su lista), Vence (un día), Responsable y
Proyecto: los filtros esperan tras el embudo de la barra, que se pone en color con el número de
filtros puestos; 50 por página. El empleado solo ve las suyas.

- La **prioridad** sale como etiqueta de color con su nombre: Baja (gris), Media (azul), Alta
  (ámbar), Urgente (rojo).
- **Vence** sale en el formato del idioma (`01/09/2026`): en rojo y con el texto «Vencida» si ya
  pasó, en ámbar con «Vence hoy» si es hoy; una tarea hecha o cancelada nunca sale como vencida. Sin
  fecha, un guion.
- Acciones de fila: **Detalle**, **Iniciar** (solo si está por hacer o bloqueada) y **Completar**
  (solo si sigue abierta). Iniciar y completar confirman con un aviso breve. Pulsar la fila abre la
  tarea.
- **+** abre **Nueva tarea**: **Título** (obligatorio), **Descripción**, **Prioridad** (Media por
  defecto), **Vence**, **Asignada a**, **Proyecto** y **Etiquetas**.

**Mis tareas**: las tareas **abiertas** asignadas a mí, primero las que tienen fecha (la más próxima
arriba) y después las que no, las más nuevas primero. Iniciar, asignar o comentar no mueve la
tarjeta. La que completo desde su tarjeta se queda en su sitio, como hecha y sin acciones, hasta que
cambio de pestaña.

### Tarea (hoja)
Se abre sobre la lista con: **TSK-AAAAMMDD-NNNN — Título**, su estado y su prioridad; la descripción;
**Vence**, **Completada**, **Asignada a** («Sin asignar»), **Proyecto**, **Creada** y **Creada por**.

- **Estado**: selector con Por hacer, En curso, Bloqueada, Hecha y Cancelada; **Completar**.
- **Asignar a**: el buscador de personas activas del equipo, por nombre, y **Asignar**; **Asignármela**
  (si tengo ficha y no es mía) y **Desasignar** (si tiene responsable).
- **Editar** abre el formulario de la tarea; **Borrar** pide confirmación (solo quien puede borrar).
- **Subtareas ({n})**, cada una con su nº, título, estado y **Abrir**, que entra en ella con **Volver**
  y la ruta de números arriba; debajo, «Nueva subtarea…» y **Añadir subtarea**.
- **Comentarios ({n})**, los más nuevos arriba, cada uno con su autor y su fecha; debajo, «Añadir
  comentario…» y **Comentar**. La caja se vacía en cuanto el comentario se acepta; si se rechaza, el
  texto se queda junto al motivo.

### Proyectos
Tabla con buscador «Buscar código o nombre…», columnas **Código, Nombre, Color** y **Activo** (Sí /
No, filtro de lista; Código, Nombre y Color se filtran por «contiene»; los filtros, tras el embudo de la
barra); orden por cualquier columna, 50 por página. Los contadores de tareas de un proyecto cuentan solo las que quien mira puede ver. **+** abre **Nuevo proyecto**:
**Código** (obligatorio, único: «q3-audit»), **Nombre** (obligatorio) y **Color** (opcional,
#RRGGBB). Acción de fila **Abrir**; pulsar la fila hace lo mismo. Crear, editar y borrar es del
responsable; el empleado ve la lista.

### Proyecto (hoja)
**Nombre** con su color, **Activo / Inactivo** y el **Código**; **Nombre** y **Color** editables con
**Guardar** (el código no cambia: es la clave del proyecto); **Desactivar / Activar** (no envía lo
tecleado sin guardar); **Borrar** con confirmación; **Tareas de este proyecto ({n})**, las 50 más
recientes con «Se muestran {x} de {n}. El resto, en Tareas.»; «Nueva tarea…» y **Añadir tarea**, que
la crea dentro del proyecto.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando…» mientras llega el primer resultado. |
| Vacío | «Sin tareas.», «Sin tareas abiertas asignadas a ti.», «Sin subtareas.», «Sin comentarios.», «Sin proyectos.» o «Este proyecto aún no tiene tareas.»; con búsqueda o filtro, «Sin resultados». |
| Error | El aviso de la tabla con «Reintentar». El rechazo de un formulario sale dentro del formulario, sin perder lo tecleado; el de una acción de fila, encima de la tabla; el de la hoja, dentro de la hoja. |
| Reconectando | Lo pintado se queda; una franja avisa «Reconectando…». |
| App inactiva | «Esta app no está activa en este negocio». |
| Sin permiso | No aparece lo que no puede hacer; si llega por otra puerta, «No tienes permiso». |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| TASK-F01 | Crear una tarea | hecho |
| TASK-F02 | Ver y buscar las tareas | hecho |
| TASK-F03 | Ver mis tareas | hecho |
| TASK-F04 | Abrir una tarea | hecho |
| TASK-F05 | Iniciar o cambiar el estado | hecho |
| TASK-F06 | Completar una tarea | hecho |
| TASK-F07 | Asignar, reasignar o desasignar | hecho |
| TASK-F08 | Editar una tarea | hecho |
| TASK-F09 | Añadir una subtarea | hecho |
| TASK-F10 | Comentar una tarea | hecho |
| TASK-F11 | Borrar una tarea | hecho |
| TASK-F12 | Crear un proyecto | hecho |
| TASK-F13 | Abrir y cambiar un proyecto | hecho |
| TASK-F14 | Borrar un proyecto | hecho |
| TASK-F15 | Cuando alguien deja el equipo | hecho |

### TASK-F01 Crear una tarea
<!-- origen: fi:modules/tasks#command-handler-wasm-tasks-tasks-create-create_task old:tasks/WORKFLOW.md#que-hay-hoy -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, empleado, asistente, una automatización con permiso
Pantalla: Tareas
Pasos:
1. En **Tareas**, pulsa **+**: se abre **Nueva tarea**.
2. Escribe el **Título** (obligatorio, hasta 255 caracteres). Si quieres: Descripción (hasta 5000),
   Prioridad (Baja, Media, Alta, Urgente; Media por defecto), Vence (un día), Asignada a (una
   persona activa del equipo), Proyecto (el selector ofrece los activos) y Etiquetas (hasta 20, de
   hasta 50 caracteres, separadas por comas).
3. Pulsa **Crear tarea**: la tarea sale en la lista **Por hacer**, sin fecha de completada y con su número
   `TSK-AAAAMMDD-NNNN` (el día del negocio y un contador del día que no deja huecos).
Entra: el formulario. El asistente nombra el proyecto por su código o su nombre, la tarea madre por su
número o su título y al responsable por su nombre. Una fecha con hora se toma como su día en la zona
del negocio. Creador: quien la crea, siempre de la sesión.
Sale: la tarea; Tareas avisa de que hay una nueva (`task.task.created`).
Si falla: debajo de cada campo y sin crear nada ni gastar número: título vacío, una prioridad que no
existe, una fecha que no lo es, «Ese proyecto no existe en este negocio.», «Esa tarea no existe en
este negocio.» (la madre), «Ese miembro del personal no existe en este negocio.», «Esa persona no
está activa en el equipo.» o, por nombre, varias personas o proyectos que encajan (se dicen cuáles).
Implicados: Personal (la ficha del responsable)

### TASK-F02 Ver y buscar las tareas
<!-- origen: old:tasks/WORKFLOW.md#que-hay-hoy fi:modules/tasks#query-tasks-tasks-list -->
Estado: hecho (servidor y pantalla)
Actor: todos; el empleado ve solo las suyas
Pantalla: Tareas → Todas
Pasos:
1. Abre **Tareas**: la tabla sale con las más nuevas primero.
2. Busca, ordena por cualquier columna o pulsa el embudo, elige los filtros y pulsa **Aplicar**.
Entra: búsqueda y filtros: nº, título, estado, prioridad, abiertas o cerradas, vencidas, proyecto (id,
código o nombre), responsable (id o nombre), sin responsable, tarea madre, solo las de primer nivel,
etiqueta, y rangos de vencimiento, de completada y de creación. Hasta 100 por página.
Sale: las tareas con su proyecto, su madre, su responsable, su creador, cuántas subtareas y
comentarios tienen y si quien mira puede cambiarlas.
Si falla: un filtro que no existe, «422».
Implicados: Personal (el nombre del responsable)

### TASK-F03 Ver mis tareas
<!-- origen: old:tasks/WORKFLOW.md#que-hay-hoy fi:modules/tasks#query-tasks-tasks-my -->
Estado: hecho (servidor y pantalla)
Actor: quien tiene ficha vinculada a su cuenta, asistente
Pantalla: Tareas → Mis tareas
Pasos:
1. Pulsa **Mis tareas**.
2. Salen mis tareas **abiertas** (por hacer, en curso y bloqueadas): con fecha primero, la más
   próxima arriba; luego sin fecha, las más nuevas primero.
3. La que completo desde su tarjeta se queda en su sitio como hecha hasta que cambio de pestaña.
Entra: opcionalmente, «las que vencen en los próximos N días» (solo las que tienen fecha).
Sale: las tareas, como en TASK-F02. Sin ficha vinculada, la lista está vacía.
Si falla: nada propio.
Implicados: Personal (mi ficha)

### TASK-F04 Abrir una tarea
<!-- origen: fi:modules/tasks#query-tasks-tasks-get -->
Estado: hecho (servidor y pantalla)
Actor: quien la ve
Pantalla: Tarea (hoja)
Pasos:
1. Pulsa la fila (o **Detalle**): se abre la hoja con la cabecera, la descripción y los datos.
2. Debajo, sus subtareas y sus comentarios. **Abrir** en una subtarea entra en ella; **Volver** sale.
Entra: la tarea, por id o, desde el asistente, por su número o su título.
Sale: la tarea, sus subtareas y sus comentarios; todo se sigue en vivo.
Si falla: «Esa tarea no existe en este negocio.» (también si es de otra persona y el empleado no la
ve); varias tareas que encajan con el título: se dicen cuáles.
Implicados: ninguno

### TASK-F05 Iniciar o cambiar el estado
<!-- origen: old:tasks/WORKFLOW.md#que-hay-hoy fi:modules/tasks#command-handler-wasm-tasks-tasks-update_status-update_status -->
Estado: hecho (servidor y pantalla)
Actor: quien puede cambiarla (el empleado, las suyas)
Pantalla: Tareas (acción **Iniciar**), Tarea (selector **Estado**)
Pasos:
1. **Iniciar** la pone **En curso**; el selector la lleva a cualquiera de los cinco estados.
2. Pasar a **Hecha** sella la fecha de completada; salir de **Hecha** la borra; los demás cambios no
   la tocan.
Entra: la tarea y el estado nuevo.
Sale: la tarea (`task.task.status_changed`; al llegar a Hecha, también `task.task.completed`).
Elegir el estado que ya tiene no cambia nada ni avisa.
Si falla: «Esa tarea no existe en este negocio.» (también la de otra persona, que el empleado no ve);
quien ve todas las tareas pero solo puede cambiar las suyas, «Solo puedes cambiar tus propias tareas.».
Implicados: ninguno

### TASK-F06 Completar una tarea
<!-- origen: old:tasks/WORKFLOW.md#que-hay-hoy fi:modules/tasks#command-handler-wasm-tasks-tasks-complete-complete_task -->
Estado: hecho (servidor y pantalla)
Actor: quien puede cambiarla
Pantalla: Tareas (acción **Completar**), Tarea (botón **Completar**)
Pasos:
1. En la fila de la tarea, o en su hoja, pulsa **Completar**.
2. La tarea pasa a **Hecha** con la fecha de ahora: la lista lo dice al momento y ya no sale como
   vencida.
Entra: la tarea.
Sale: la tarea (`task.task.status_changed` y `task.task.completed`).
Si falla: si ya estaba hecha o cancelada, «Esa tarea ya está cerrada, así que se ha dejado como
estaba.» (409 `task.task_already_closed`): una cancelada no se «termina» por error; para reabrirla,
se cambia el estado.
Implicados: ninguno

### TASK-F07 Asignar, reasignar o desasignar
<!-- origen: old:tasks/WORKFLOW.md#que-hay-hoy fi:modules/tasks#command-tasks-tasks-assign -->
Estado: hecho (servidor y pantalla)
Actor: quien puede cambiarla
Pantalla: Tarea
Pasos:
1. Abre la tarea, busca a la persona por su nombre en **Asignar a** y pulsa **Asignar**; o pulsa
   **Asignármela**.
2. Para dejarla sin responsable, pulsa **Desasignar**: la hoja dice «Sin asignar».
Entra: la tarea y la persona (id, nombre o «a mí»); sin persona, se desasigna. Solo personas
activas o de baja temporal; nunca una ficha dada de baja o inactiva.
Sale: la tarea (`task.task.assigned`, con el responsable nuevo o vacío). Asignar a quien ya la tiene
no cambia nada ni avisa.
Si falla: «Ese miembro del personal no existe en este negocio.», «Esa persona no está activa en el
equipo.», «No tienes ficha en Personal: no se te puede asignar.» (asignármela sin ficha).
Implicados: Personal

### TASK-F08 Editar una tarea
<!-- origen: nuevo (el producto actual no editaba una tarea) -->
Estado: hecho (servidor y pantalla)
Actor: quien puede cambiarla
Pantalla: Tarea → **Editar**
Pasos:
1. Abre la tarea y pulsa **Editar**: se abre «Editando tarea — TSK-…» con sus datos.
2. Cambia el título, la descripción, la prioridad, la fecha límite, el proyecto o las etiquetas y
   pulsa **Guardar**: se envía solo lo que cambió.
Entra: lo enviado; vacío en Vence o Proyecto los quita.
Sale: la tarea (`task.task.updated`). Guardar sin cambios no avisa.
Si falla: los mismos rechazos que al crear.
Implicados: ninguno

### TASK-F09 Añadir una subtarea
<!-- origen: old:tasks/WORKFLOW.md#que-hay-hoy fi:modules/tasks#query-tasks-tasks-subtasks -->
Estado: hecho (servidor y pantalla)
Actor: quien puede crear tareas y ve la madre
Pantalla: Tarea
Pasos:
1. Abre la tarea, escribe el título en «Nueva subtarea…» y pulsa **Añadir subtarea**: sale en la
   lista al momento, con su número, en el proyecto de la madre.
2. **Abrir** en la subtarea entra en ella, con la ruta de números arriba; **Volver** sale a la madre.
Entra: el título y la madre.
Sale: la subtarea (`task.task.created`).
Si falla: el motivo dentro de la hoja; el título tecleado se queda.
Implicados: ninguno

### TASK-F10 Comentar una tarea
<!-- origen: old:tasks/WORKFLOW.md#que-hay-hoy fi:modules/tasks#command-tasks-tasks-add_comment fi:modules/tasks#query-tasks-tasks-comments -->
Estado: hecho (servidor y pantalla)
Actor: quien puede cambiarla
Pantalla: Tarea
Pasos:
1. Abre la tarea y escribe en «Añadir comentario…».
2. Pulsa **Comentar**: el comentario entra arriba del hilo con mi nombre y la hora; la caja se vacía
   (lo que tecleé mientras se enviaba se queda).
Entra: la tarea y el texto (obligatorio, hasta 5000). El autor sale siempre de la sesión.
Sale: el comentario (`task.comment.added`). El hilo es un registro: no se edita ni se borra.
Si falla: texto vacío; «Esa tarea no existe en este negocio.».
Implicados: ninguno

### TASK-F11 Borrar una tarea
<!-- origen: nuevo (el producto actual describía el borrado sin acción) -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente (con confirmación reforzada)
Pantalla: Tarea → **Borrar**
Pasos:
1. Abre la tarea y pulsa **Borrar**: se pide confirmación.
2. Pulsa **Borrar** en el aviso: la tarea desaparece **con sus subtareas y sus comentarios**.
Entra: la tarea.
Sale: `task.task.deleted`.
Si falla: «Esa tarea no existe en este negocio.».
Implicados: ninguno

### TASK-F12 Crear un proyecto
<!-- origen: old:tasks/WORKFLOW.md#que-hay-hoy fi:modules/tasks#command-tasks-projects-create -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente
Pantalla: Proyectos
Pasos:
1. Pulsa **+**, escribe **Código** (hasta 40, único sin distinguir mayúsculas) y **Nombre** (hasta
   200); si quieres, **Color** (#RRGGBB). Por la API o el asistente, también un dueño (una persona
   del equipo).
2. Pulsa **Crear proyecto**: el proyecto sale **Activo**.
Entra: el código, el nombre y, si quieres, el color; por la API o el asistente, también el dueño.
Sale: el proyecto (`task.project.created`).
Si falla: «Ya hay un proyecto con ese código.» bajo el campo; un color que no es #RRGGBB.
Implicados: Personal (el dueño)

### TASK-F13 Abrir y cambiar un proyecto
<!-- origen: old:tasks/WORKFLOW.md#que-hay-hoy fi:modules/tasks#query-tasks-projects-list -->
Estado: hecho (servidor y pantalla)
Actor: todos lo abren; lo cambian el propietario, el administrador y el responsable
Pantalla: Proyecto (hoja)
Pasos:
1. Pulsa la fila (o **Abrir**): la hoja sale con su nombre, su estado, su código y sus tareas.
2. Cambia nombre o color y **Guardar**; **Desactivar** lo saca de uso (deja de ofrecerse al crear
   tareas, sus tareas siguen); **Activar** lo devuelve.
3. **Añadir tarea** crea una tarea dentro del proyecto.
Entra: el proyecto, por id o, desde el asistente, por su código o su nombre.
Sale: el proyecto (`task.project.updated`). Guardar sin cambios no avisa.
Si falla: «Ese proyecto no existe en este negocio.» dentro de la hoja, que sigue abierta; un nombre
vacío no se envía.
Implicados: ninguno

### TASK-F14 Borrar un proyecto
<!-- origen: nuevo (el producto actual no borraba proyectos) -->
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable, asistente (con confirmación reforzada)
Pantalla: Proyecto → **Borrar**
Pasos:
1. Abre el proyecto y pulsa **Borrar**: se pide confirmación.
2. Pulsa **Borrar** en el aviso: el proyecto desaparece; **sus tareas siguen**, sin proyecto.
Entra: el proyecto.
Sale: `task.project.deleted`.
Si falla: «Ese proyecto no existe en este negocio.».
Implicados: ninguno

### TASK-F15 Cuando alguien deja el equipo
<!-- origen: nuevo (la baja en Personal, STAFF-F06) -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un responsable da de baja en **Personal** a una persona que tiene tareas abiertas (STAFF-F06).
2. En unos segundos, sus tareas **abiertas** (por hacer, en curso o bloqueadas) se quedan **sin
   asignar**; las hechas y las canceladas conservan su nombre.
3. En **Tareas** salen como «Sin asignar», y el responsable las reparte (TASK-F07).
Entra: la baja de la persona en Personal.
Sale: un `task.task.assigned` (responsable vacío) por tarea.
Si falla: si la persona no tenía tareas abiertas, no se hace nada; una segunda entrega del mismo aviso
tampoco cambia nada.
Implicados: Personal (STAFF-F06), TASK-F07

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (por voz o por texto, con la sesión de quien
habla) y la API, con las mismas reglas y los mismos permisos. Una tarea se nombra por su id, su número
o su título; un proyecto por su id, su código o su nombre; una persona por su id o su nombre. Si un
nombre vale para varias, se dice cuáles y se pide que elija (`task.ambiguous_task`,
`task.ambiguous_project`, `staff.ambiguous_member`).

### Lo que ofrece: consultas (leen, no cambian nada; todas se pueden seguir en vivo)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Las tareas, con búsqueda, filtros y orden, en páginas de hasta 100 (el empleado, las suyas) | ver | F02 | `task.task.list` |
| Mis tareas abiertas, por vencimiento | ver | F03 | `task.task.mine` |
| Una tarea | ver | F04 | `task.task.detail` |
| Las subtareas de una tarea, en orden de alta | ver | F04, F09 | `task.task.subtasks` |
| Los comentarios de una tarea, los más nuevos primero | ver | F04, F10 | `task.comment.list` |
| Los proyectos, con búsqueda, filtros, orden y cuántas tareas tienen | ver | F12, F13 | `task.project.list` |
| Un proyecto | ver | F13 | `task.project.detail` |

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Crea una tarea o una subtarea | crear | F01, F09, F13 | `task.task.create` |
| Cambia una tarea (solo lo enviado) | cambiar | F08 | `task.task.update` |
| Cambia el estado | cambiar | F05 | `task.task.set_status` |
| Completa una tarea abierta | cambiar | F06 | `task.task.complete` |
| Asigna, reasigna o desasigna | cambiar | F07 | `task.task.assign` |
| Borra una tarea con sus subtareas y comentarios | borrar | F11 | `task.task.delete` |
| Comenta una tarea | cambiar | F10 | `task.comment.add` |
| Crea un proyecto | proyectos | F12 | `task.project.create` |
| Cambia un proyecto (nombre, color, activo, dueño) | proyectos | F13 | `task.project.update` |
| Borra un proyecto (sus tareas siguen) | proyectos | F14 | `task.project.delete` |
| Desasigna las tareas abiertas de quien deja el equipo | solo la plataforma | F15 | `task.task.release_member` |

### Lo que avisa

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Tarea nueva | Crear una tarea o una subtarea | `id`, `number`, `project_id`, `parent_id`, `assigned_to_id` | `task.task.created` |
| Tarea cambiada | Editar con algún cambio | `id` | `task.task.updated` |
| Estado cambiado | Cambiar el estado o completar | `id`, `from`, `to` | `task.task.status_changed` |
| Tarea completada | Llegar a Hecha por cualquier camino | `id` | `task.task.completed` |
| Responsable cambiado | Asignar, reasignar, desasignar o la baja de la persona | `id`, `assigned_to_id` (o vacío) | `task.task.assigned` |
| Tarea borrada | Borrar | `id`, `number` | `task.task.deleted` |
| Comentario nuevo | Comentar | `id`, `task_id` | `task.comment.added` |
| Proyecto nuevo | Crear un proyecto | `id`, `code` | `task.project.created` |
| Proyecto cambiado | Guardar, activar o desactivar con algún cambio | `id` | `task.project.updated` |
| Proyecto borrado | Borrar un proyecto | `id`, `code` | `task.project.deleted` |

Los avisos no llevan títulos, descripciones ni comentarios (texto libre que puede nombrar a un
cliente o a un compañero).

### A qué reacciona y lo que necesita de otras apps
- **Personal** (`requires = ["staff"]`): el responsable y el dueño de un proyecto son fichas de
  Personal; Tareas lee sus nombres y, al dar de baja a alguien (`staff.member.terminated`), desasigna
  sus tareas abiertas (TASK-F15: el aviso se lo entrega el relay del outbox del worker, una sola vez por
  baja). Las pantallas buscan a las personas con `staff.member.list` y
  «Asignármela» lee la ficha propia con `staff.member.mine`.
- De la plataforma: la cuenta de quien actúa (creador y autor de los comentarios) y la zona horaria
  del negocio (el «hoy»).
- Quién más la usa: **Automatizaciones** llama a `task.task.create` por su nombre, con el permiso que el
  negocio le concede; sus automatizaciones de fábrica de Citas y de Reservas online dejan una tarea
  (FLOW-F33). Tareas no sabe de ellas.

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver las tareas propias (asignadas o creadas) y los proyectos | sí | sí | sí | sí | `task.view` |
| Ver todas las tareas | sí | sí | sí | no | `task.view_all` |
| Crear tareas y subtareas | sí | sí | sí | sí | `task.add` |
| Cambiar, asignar, completar y comentar las propias | sí | sí | sí | sí | `task.change` |
| Cambiar, asignar, completar y comentar cualquiera | sí | sí | sí | no | `task.change_all` |
| Borrar tareas | sí | sí | sí | no | `task.delete` |
| Crear, cambiar y borrar proyectos | sí | sí | sí | no | `task.manage_project` |

## Para quien lo mantiene

- Anatomía completa de una app: `apps.py`, `models.py`, `schemas.py`, `queries.py`, `services.py`,
  `events.py`, `live.py`, `api.py`, `admin.py`, `locale/`, `frontend/` y un `tests/test_<fichero>.py`
  por fichero, más `tests/test_integration_staff.py` con Personal de verdad y `tests/test_relay.py`, la baja
  en Personal entregada por el relay real del worker (TASK-F15, con dos negocios).
- Modelos: `Project`, `Task` (con `parent` a sí misma, `CASCADE`; `project` y `assigned_to`,
  `SET_NULL`), `Comment` (`CASCADE` con su tarea) y `TaskCounter` (un contador por día del negocio).
  UUIDv7, sin `hub_id`. `created_by` y `Comment.author` cuelgan de `settings.AUTH_USER_MODEL`
  (`SET_NULL`), como `staff.TimeOff.approved_by`; la fase 2 los mueve con los usuarios del hub.
- **Hecha ⇔ fecha de completada**: restricción `task_task_completed_iff_done`.
- **Número sin huecos**: `TSK-AAAAMMDD-NNNN` con el día del negocio; el contador del día se crea si
  falta (`INSERT … ON CONFLICT DO NOTHING`) y se sube con un `UPDATE` que bloquea su fila hasta el
  COMMIT de la tarea, así que dos altas a la vez esperan y un alta rechazada no gasta número.
- **Lo propio**: una tarea es de alguien si la tiene asignada (su ficha de Personal, la vinculada a su
  cuenta) o la creó él. `task.view_all` y `task.change_all` quitan el filtro. Una tarea que el
  empleado no ve da «no existe», no «no tienes permiso», por cualquier puerta (id, número o título).
  Nada de ella se cuela por otra fila: ni el número ni el título de una tarea madre ajena, ni las
  subtareas ajenas en el contador, ni las tareas ajenas en los contadores de un proyecto.
- Las escrituras sobre una tarea bloquean su fila (`select_for_update`) antes de mirar su estado.
  La que nombra a una persona (responsable de una tarea o de un proyecto) bloquea antes su ficha de
  Personal (`resolve_member(…, lock=True)`) y después la tarea o el proyecto: es el orden del «Delete»
  del admin del Hub (`lock_members` de Personal y luego lo que la nombra), así que uno espera al otro y
  nunca en círculo. Si la persona ya se borró, la escritura responde «no existe» en su campo, nunca 500.
- El «hoy» es `timezone.localdate()` (zona del negocio; en la fase 1, `TIME_ZONE` = Europe/Madrid);
  las páginas calculan «vencida» y «vence hoy» en esa misma zona.
- Asistente: toda operación declara `ai={"description"…}` (`risk` solo en las acciones; `high` al
  borrar una tarea o un proyecto) y todo campo de entrada lleva `description`.
- El admin de Django del Hub tiene **CRUD completo** sobre los cuatro modelos (ronda 12, PLAN §17); una
  escritura cruda del admin no deja aviso.
- Fase 1: el ámbito es la primera parte del Host y los datos se comparten entre `a` y `b`, como en
  `demo`; lo que sí se separa son los avisos en vivo.

## Cómo son las páginas (para quien lo mantiene)

- `frontend/routes.ts`: `/task/tasks` y `/task/projects`; `frontend/tabs.ts` pinta las dos pestañas.
- Listas en vivo con `useLiveList` (ventanas de 100 filas, cada una su suscripción) y `useServerTable`
  (orden `columna`/`-columna`); escrituras con `useCommand`.
- La hoja de la tarea y la del proyecto son `ion-modal` con sus consultas en vivo; la ruta de
  subtareas abiertas (**Volver**) vive en la hoja.
- Los selectores de persona y de proyecto buscan en el servidor (`Combo` de `@erplora/ui`).
- Los iconos son los registrados en la shell: Proyectos ya lleva la carpeta del producto actual
  (`ion:folder-outline`); los otros cuatro (`checkbox-outline` del módulo y de la pestaña Tareas,
  `open-outline`, `play-circle-outline` y `checkmark-done-outline` de las acciones de fila) esperan en
  `UI-REQUESTS.md` con su sustituto.
- Las hojas no cambian la URL (como las de Servicios y Personal, y como el panel del producto actual,
  que tampoco tenía sub-ruta): no hay enlace directo a una tarea ni a un proyecto.

## Lo que NO hace, a propósito

- **No avisa a nadie**: ni correo, ni push, ni recordatorio de vencimiento.
- **No registra tiempo**, estimaciones ni informes.
- **No corre nada programado** ni persigue tareas vencidas.
- **No adjunta ficheros**.
- **No gestiona incidencias de clientes**.
- **No edita ni borra comentarios**: el hilo es un registro.

## Cambios frente al producto actual

- **El responsable es una ficha de Personal** (`requires = ["staff"]`), no una referencia de texto a
  un usuario: ver «Referencia adoptada». Lo mismo el dueño de un proyecto. La baja de una persona
  desasigna sus tareas abiertas (TASK-F15, nuevo).
- **El empleado ve y cambia las suyas**; el responsable, todas. Antes los tres papeles lo veían y
  cambiaban todo. Los **proyectos** los crea y cambia el responsable (antes también el empleado).
- **Autor y creador salen de la sesión**: antes se podían mandar en la petición y firmar como otro.
- **Nada falla en silencio**: crear con un proyecto o una madre que no existen, completar una tarea
  cerrada o tocar una que no existe dan su error y no gastan número ni avisan. Antes eran no-ops que
  a veces avisaban igual.
- **Editar una tarea** (TASK-F08), **borrar una tarea** (TASK-F11) y **borrar un proyecto** (TASK-F14)
  son nuevos: el producto actual describía el borrado pero no tenía acción.
- **Nueva tarea** pide todos los campos (antes solo título y prioridad); la lista tiene la columna
  **Responsable** y **Proyecto** (oculta).
- **La fecha límite es un día** (sin hora), en la zona del negocio; antes se guardaba como fecha y hora
  UTC y la pantalla solo enseñaba el día.
- **El número** usa el día del negocio, no el día UTC.
- **El color** de un proyecto es #RRGGBB (antes, cualquier texto, que se pintaba tal cual en el estilo).
- **Avisos**: `task.*` en vez de `tasks.*`; `task.task.completed` sale siempre que una tarea llega a
  Hecha; nuevos `task.task.updated`, `task.task.deleted` y `task.project.deleted`.
- **Nombres de servicio**: `task.task.detail` (antes `tasks.tasks.get`), `task.task.mine` (`…my`),
  `task.task.set_status` (`…update_status`), `task.comment.list` y `task.comment.add`
  (`tasks.tasks.comments`, `…add_comment`).
- Las listas paginan con hasta 100 por página; las subtareas salen en orden de alta.
- La hoja de la tarea y la del proyecto se abren en un diálogo encima de la lista (antes, un panel
  dentro de la página) y el alta en un formulario (antes, el panel lateral de la tabla): ver
  `UI-REQUESTS.md`.
