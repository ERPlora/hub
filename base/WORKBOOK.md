# Workbook — Base (plataforma)
Prefijo: BASE
Alcance MVP: fase 1 (el Inicio del hub; el resto de la plataforma llega por partes)
Estado de la app: en construcción (2026-10-22)

> Manual de usuario y especificación de `base`, la plataforma del Hub: siempre está, no se activa ni se
> apaga. Esta primera parte describe el **Inicio**, la pantalla a la que se llega al entrar en el negocio
> (el del hub viejo: saludo, «Mis apps», la lista de lo que falta por configurar, los paneles de las apps y
> la actividad), con lo que acompaña a cualquier pantalla: la campana, «Actualizar plan» y la franja que
> avisa cuando todavía no se puede facturar. Las plantillas y Ajustes › Datos llegan en la parte siguiente.

## Para qué sirve y para quién

El Inicio es lo primero que ve cualquier persona del negocio al entrar. De un vistazo:

- **Sus apps**, para abrir la que necesite sin buscarla en ningún menú.
- **Lo que le falta al negocio** para funcionar del todo: cada app dice qué paso necesita y la lista los
  junta, ordenados y con lo que pasa si no se hacen; el que impide facturar va el primero y en rojo.
- **Los paneles de las apps**: cifras, listas y gráficos que se mueven solos cuando algo cambia en el
  negocio, sin recargar.
- **La actividad**: las últimas ventas.

Quién lo usa:

- El **propietario** y el **administrador** ven todo y son quienes pueden resolver los pasos de la
  plataforma («Tus apps», «Tu equipo»), y en la campana ven los avisos entre apps que no se entregaron.
- El **responsable** y el **empleado** ven sus apps, los pasos que les tocan, los paneles que pueden ver
  y la actividad. Un paso que solo puede resolver un administrador también lo ven, para saber por qué no se
  puede facturar, pero sin botón.

## Referencia adoptada

Es el Inicio del hub viejo de ERPlora, el mismo que ya usan los negocios, con su estructura: saludo y
fecha, lanzador de apps, lista de configuración con barra de progreso, tablero de paneles y pestañas
«Resumen» y «Actividad». Sigue lo que hace el mercado: la lista de «Setup guide» de Shopify y Square
(pasos con su botón, el progreso arriba y lo hecho plegado), el lanzador de apps de Odoo, el tablero de
paneles que cada uno elige y ordena de Lightspeed y Toast, y la campana con contadores de cualquier
backoffice.

## Antes de empezar

- Se entra con la cuenta de ERPlora; el Hub no tiene entrada propia.
- Lo que cada persona ve depende de su papel en el negocio y de las apps que el negocio tiene encendidas.
- Las apps declaran sus pasos, sus paneles y sus contadores; el Inicio solo los junta. Mientras una app no
  declara los suyos, no aparece nada suyo en la lista ni en el tablero.
- La app de ejemplo (Demo) sale en el menú, en «Mis apps» y con un paso, un panel y un contador de ejemplo
  en el Inicio solo en desarrollo, en las pruebas y en un negocio de demostración: nunca en el de un cliente.

## Pantallas

### Inicio · Resumen
Arriba, el nombre del negocio y «Hoy» con la fecha larga; mientras el negocio no tiene nombre, un saludo
según la hora («Buenos días», «Buenas tardes», «Buenas noches»). Debajo, en este orden:

- **«Mis apps»**: una baldosa por app, con su icono y su nombre; las que más se abren en este navegador,
  primero. En el móvil, con seis apps o más, las cuatro primeras y «Ver todas las apps».
- **«Termina de configurar tu negocio»**: cuántos pasos lleva hechos, una barra y los pasos que faltan,
  cada uno con su icono, su explicación, una etiqueta («Necesario para facturar», «Importante»,
  «Recomendado», «Hecho» o «Todavía no disponible») y «Configurar». Plegada: cinco pasos (dos en el
  móvil), con «Ver todo» y «Ver menos». Cuando no falta nada: «Tu negocio está listo».
- **El tablero de paneles**, con «Personalizar panel» (⋮) arriba a la derecha.

### Inicio · Actividad
La tabla de las últimas ventas: «Fecha», «Venta», «Cliente», «Método», «Importe» y «Estado», con
«Buscar actividad…», el embudo de filtros (método y estado), el orden, la vista de tarjetas y «Columnas».
Se abre también con el enlace del Inicio terminado en `#actividad`.

### La campana
Arriba a la derecha, después de «Mis apps». Su número suma los avisos pendientes; al tocarla, una fila
por aviso («Eventos caídos (2)») que lleva a su pantalla. Sin nada: «Todo al día. Sin notificaciones.».

### «Actualizar plan»
Al pie del menú lateral, entre el código QR y la marca. Abre la página del plan de este negocio en
erplora.com, en una pestaña nueva. Solo en el navegador: en la app instalada no está.

### El menú de usuario
Se abre tocando a la persona, arriba del menú lateral. Primero «Mi cuenta» y «Reportar un problema», que
abren esas páginas en erplora.com (en una pestaña nueva; en la app instalada, en el navegador del
dispositivo); después «Tema» (claro, oscuro o el del sistema) y «Cerrar sesión». Las dos primeras salen
también en la app instalada: ninguna vende nada.

### La franja «Todavía no puedes facturar»
Encima de cualquier pantalla mientras falta un paso que impide facturar: «No se podrá emitir ningún
ticket ni factura hasta que configures esto:» y cada paso con «Configurar». En el «Resumen» del Inicio no
sale (la lista dice lo mismo un poco más abajo); en «Actividad», sí.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | Baldosas grises en «Mis apps» («Cargando tus apps…» para el lector de pantalla), la lista en gris, «Cargando widgets…» en el tablero, la cifra de cada panel en gris y «Cargando…» en «Actividad». |
| Vacío | «Aquí aparecerán tus apps. Añade las que necesite tu negocio.»; sin pasos, la lista no sale; «Panel vacío. Pulsa ⋮ para añadir widgets.»; un panel sin datos, «Sin datos»; la campana, «Todo al día. Sin notificaciones.». |
| Error | Cada zona falla por su cuenta: «No se han podido cargar tus apps. Recarga la página; si sigue fallando, vuelve a iniciar sesión.», «No se ha podido cargar lo que te falta por configurar» con «Reintentar», «No se han podido cargar los paneles» con «Reintentar», un panel con «No disponible» (nunca la cifra de antes), «No se han podido cargar las últimas ventas» con «Reintentar» y, en la campana, «No se han podido comprobar las notificaciones. Aparecerán cuando vuelva la conexión.». |
| Sin permiso | Un paso que la persona no puede hacer: sin botón y «Esto lo tiene que configurar un administrador.». Un panel o un contador que no puede ver, no sale. |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| BASE-F01 | Ver lo que le falta por configurar al negocio | hecho |
| BASE-F02 | Ver el negocio de un vistazo al entrar | parcial |
| BASE-F03 | Ir a configurar desde el panel «Configura tu negocio» | parcial |
| BASE-F04 | Ver qué pasos de la lista tiene que configurar un administrador | hecho |
| BASE-F05 | Abrir una app desde «Mis apps» | parcial |
| BASE-F06 | Ver los paneles de las apps en Inicio | hecho |
| BASE-F07 | Personalizar el tablero de paneles | hecho |
| BASE-F08 | Mantener los paneles al día sin recargar | hecho |
| BASE-F09 | Consultar la actividad reciente | hecho |
| BASE-F10 | Ver en la campana los avisos entre apps que no se entregaron | parcial |
| BASE-F11 | Ir a erplora.com a gestionar o mejorar el plan | parcial |
| BASE-F12 | Pedirle al asistente que repase la configuración | parcial |
| BASE-F13 | Perder el acceso al cambiar de rol o al salir del negocio | hecho |

### BASE-F01 Ver lo que le falta por configurar al negocio
<!-- origen: fi:hub/app-web#setup-status-estado-de-configuracion-de-modulos-adr-0063 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Inicio · Resumen
Pasos:
  1. Entra en el Inicio. En «Termina de configurar tu negocio» ve cuántos pasos lleva hechos y una barra.
  2. Debajo, los pasos que faltan, en el orden que fijan las apps: primero los que impiden facturar
     («Necesario para facturar», en rojo), luego los «Importante» y al final los «Recomendado».
  3. Los de la plataforma son «Tus apps» (encender al menos una app de negocio) y «Tu equipo» (añadir a
     las personas que usarán el TPV); el resto los trae cada app encendida.
  4. Un paso que solo vale para otro país, o que la persona no puede ver, no sale. Un paso cuya
     comprobación falla tampoco sale: nunca se da por hecho ni por pendiente lo que no se pudo comprobar.
  5. Mientras falta un paso «Necesario para facturar», la franja «Todavía no puedes facturar» sale encima
     de las demás pantallas.
  6. Cuando otra persona completa un paso en otro dispositivo, la lista se pone al día sola.
Entra: los pasos que declara cada app encendida, con su comprobación, su país, su permiso y su pantalla.
Sale: nada guardado.
Si falla: «No se ha podido cargar lo que te falta por configurar» con «Reintentar». Un paso que es cosa
nuestra (no hay ninguna app de negocio que encender) sale como «Todavía no disponible» con «Esto es cosa
nuestra: por tu parte no hay nada que hacer aún. Estamos en ello.».
Implicados: INVENTORY-F28

### BASE-F02 Ver el negocio de un vistazo al entrar
<!-- origen: old-hub:HUB_SHELL-F25 -->
Estado: parcial — sin la fila de salud del hub (la impresora y WhatsApp con «Ver sistema») ni la propuesta de plantilla, que llega con las plantillas
Actor: propietario, administrador, responsable, empleado
Pantalla: Inicio · Resumen
Pasos:
  1. Tras entrar se abre el Inicio (también desde «Inicio» en el menú lateral).
  2. Arriba, el nombre del negocio (el de erplora.com) y «Hoy» con la fecha larga en el idioma de la
     aplicación; mientras el negocio no tiene nombre, «Buenos días», «Buenas tardes» o «Buenas noches».
  3. Debajo, en este orden: «Mis apps», «Termina de configurar tu negocio» y el tablero de paneles.
  4. Abajo, dos pestañas: «Resumen» (lo anterior) y «Actividad».
Entra: el nombre del negocio y la fecha del dispositivo.
Sale: nada guardado.
Si falla: una zona que no carga no tumba las demás; cada una dice lo suyo. En el móvil las zonas se
apilan y «Mis apps» se pliega.
Implicados: ninguno

### BASE-F03 Ir a configurar desde el panel «Configura tu negocio»
<!-- origen: old-hub:HUB_SHELL-F38 -->
Estado: parcial — los «Configurar» de cada paso de la lista llevan ya a su pantalla; el panel «Configura tu negocio» y su destino (Ajustes › Datos y copias) llegan con las plantillas
Actor: propietario, administrador, responsable
Pantalla: Inicio · Resumen
Pasos:
  1. En «Termina de configurar tu negocio», un paso pendiente que la persona puede hacer lleva
     «Configurar».
  2. Pulsa «Configurar»: se abre la pantalla de la app que completa ese paso.
  3. Al volver al Inicio, la lista ya cuenta el paso como hecho si se completó.
Entra: la pantalla que cada paso declara.
Sale: nada desde aquí.
Si falla: mientras esa pantalla no existe en el hub, el paso sale sin «Configurar» (un botón que lleva a
«no encontrado» es peor que ninguno).
Implicados: ninguno

### BASE-F04 Ver qué pasos de la lista tiene que configurar un administrador
<!-- origen: old-hub:HUB_SHELL-F29 -->
Estado: hecho
Actor: responsable, empleado
Pantalla: Inicio · Resumen
Pasos:
  1. Un paso que impide facturar y que esta persona no puede hacer sigue en su lista y en la franja, con
     su etiqueta «Necesario para facturar».
  2. No lleva «Configurar»: dice «Esto lo tiene que configurar un administrador.».
  3. Los pasos que no impiden facturar y que esta persona no puede hacer no salen en su lista.
Entra: los permisos de la persona en este negocio.
Sale: nada.
Si falla: si no se puede comprobar ese paso, no sale.
Implicados: ninguno

### BASE-F05 Abrir una app desde «Mis apps»
<!-- origen: old-hub:HUB_SHELL-F32 -->
Estado: parcial — «Añadir apps» sale en cuanto el hub tenga la pantalla Apps
Actor: propietario, administrador, responsable, empleado
Pantalla: Inicio · Resumen
Pasos:
  1. En «Mis apps», una baldosa por app que esta persona puede abrir, con su icono y su nombre (si no
     cabe, el nombre entero sale al pasar por encima).
  2. Las más abiertas en este navegador van primero.
  3. Toca una baldosa: se abre la app. Una app que se está encendiendo dice «Activando…» y no abre nada.
  4. En el móvil, con seis apps o más, se ven las cuatro primeras y «Ver todas las apps», que enseña el
     resto. «Añadir apps», la última, lleva a Apps.
Entra: las apps del menú de la persona (las mismas del botón «Mis apps» de la barra).
Sale: cuántas veces se abre cada app en este navegador (solo para ordenar).
Si falla: mientras carga, baldosas grises y «Cargando tus apps…» para el lector de pantalla. Sin apps:
«Aquí aparecerán tus apps. Añade las que necesite tu negocio.». Si no se pudo leer la lista: «No se han
podido cargar tus apps. Recarga la página; si sigue fallando, vuelve a iniciar sesión.», nunca que no
hay apps.
Implicados: ninguno

### BASE-F06 Ver los paneles de las apps en Inicio
<!-- origen: old-hub:HUB_SHELL-F33 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Inicio · Resumen
Pasos:
  1. Bajo la lista está el tablero («Cargando widgets…» mientras llega).
  2. Cada panel es una tarjeta con su título e icono: una cifra, una lista con barras, una cronología, un
     gráfico o un trozo de la pantalla de su app.
  3. De entrada salen los que cada app marca como recomendados para el sector del negocio.
  4. Solo salen los paneles de las apps encendidas que esta persona puede ver.
Entra: los paneles que declara cada app encendida; los datos de cada uno, pedidos con los permisos de
quien mira.
Sale: nada guardado en el hub.
Si falla: un panel sin datos dice «Sin datos»; uno cuyos datos no se pueden leer, «No disponible», nunca
una cifra vieja o inventada. Si no se puede leer el tablero: «No se han podido cargar los paneles» con
«Reintentar».
Implicados: ninguno

### BASE-F07 Personalizar el tablero de paneles
<!-- origen: old-hub:HUB_SHELL-F34 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Inicio · Resumen
Pasos:
  1. Pulsa ⋮ («Personalizar panel») sobre el tablero.
  2. En «Empezar desde un preset», «Recomendado» vuelve a los paneles recomendados.
  3. En «Activos · arrastra para reordenar» ordena o quita; en «Disponibles» añade.
  4. «Cerrar» deja el tablero como quedó.
Entra: los paneles que esta persona puede poner.
Sale: el tablero elegido, guardado en este navegador: lo comparten las personas que usan este dispositivo
y no viaja a otro.
Si falla: un panel guardado cuya app se apagó desaparece del tablero sin aviso. Sin ninguna app que
ofrezca paneles: «Ninguna app instalada ofrece widgets todavía.».
Implicados: ninguno

### BASE-F08 Mantener los paneles al día sin recargar
<!-- origen: old-hub:HUB_SHELL-F35 -->
Estado: hecho
Actor: sistema
Pantalla: Inicio · Resumen
Pasos:
  1. Cada panel dice qué avisos de su app lo cambian (una venta, un movimiento de caja, un recuento).
  2. Cuando pasa uno de esos avisos en cualquier dispositivo del negocio, el panel recibe sus datos nuevos
     solo, sin vaciarse mientras tanto.
  3. Un panel cuyos datos no se siguen en vivo se pinta una vez al entrar y no se mueve hasta volver a
     cargar el Inicio.
Entra: los avisos del negocio que declara cada panel.
Sale: nada guardado.
Si falla: si los datos nuevos no llegan, el panel dice «No disponible», no el valor de antes; cuando
vuelve la conexión, se pone al día solo.
Implicados: ninguno

### BASE-F09 Consultar la actividad reciente
<!-- origen: old-hub:HUB_SHELL-F36 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Inicio · Actividad
Pasos:
  1. En el Inicio, pestaña «Actividad».
  2. «Cargando…» y después una tabla con las últimas 100 ventas: «Fecha» (con la hora), «Venta»,
     «Cliente», «Método», «Importe» (con euros: 1,50 € sale «1,50 €») y «Estado», con las palabras del
     historial de Ventas: «Completada» en verde, «Anulada» en rojo, «Devuelta» en ámbar y «Otro» en gris
     para un estado que esta pantalla aún no conoce.
  3. Busca con «Buscar actividad…» (venta, cliente o método), filtra por método o estado, ordena, cambia a
     tarjetas o elige columnas; 15 por página.
  4. Una venta cobrada en otro dispositivo aparece sola, sin recargar.
Entra: las ventas de la app Ventas, si está encendida, con los permisos de quien mira. Solo ventas: los
demás movimientos del negocio no salen aquí.
Sale: nada guardado.
Si falla: sin la app Ventas, la tabla vacía. Si no se pueden leer las ventas: «No se han podido cargar las
últimas ventas» — «Comprueba la conexión y vuelve a intentarlo.» con «Reintentar», en lugar de la tabla;
si ya había ventas en pantalla, se quedan debajo del aviso.
Implicados: SALE-F28

### BASE-F10 Ver en la campana los avisos entre apps que no se entregaron
<!-- origen: old-hub:HUB_SHELL-F62 -->
Estado: parcial — la fila aún no lleva a ningún sitio: la pantalla Sistema, donde se reenvían o descartan, llega más adelante
Actor: propietario, administrador
Pantalla: La campana
Pasos:
  1. Un aviso entre apps (por ejemplo, «venta cobrada» hacia Facturación) agotó sus reintentos.
  2. La campana de un administrador sube en el momento, sin esperar ni recargar, y al abrirla enseña
     «Eventos caídos» con cuántos hay.
  3. Cuando no queda ninguno, la fila desaparece.
Entra: cuántos avisos de este negocio quedaron sin entregar, solo para quien administra el negocio.
Sale: nada.
Si falla: un empleado o un responsable no ve la fila. Si no se puede preguntar, la campana se queda con
lo último que supo; si nunca lo supo: «No se han podido comprobar las notificaciones. Aparecerán cuando
vuelva la conexión.».
Implicados: ninguno

### BASE-F11 Ir a erplora.com a gestionar o mejorar el plan
<!-- origen: old-hub:HUB_SHELL-F129 -->
Estado: parcial — un enlace normal, sin el pase de un solo uso, solo en el navegador (no en la app instalada) y sin el botón «erplora.com» de la barra
Actor: propietario, administrador, responsable, empleado
Pantalla: Menú lateral
Pasos:
  1. Al pie del menú lateral, bajo el código QR y alineado con él, está «Actualizar plan». Lo ve cualquier
     perfil; lo que se puede hacer al llegar lo decide erplora.com según quién entre. Con el menú plegado a
     sus iconos (escritorio), queda solo su icono, que dice «Actualizar plan» al pasar por encima.
  2. Lo pulsa: se abre en una pestaña nueva la página del plan de este negocio en erplora.com.
Entra: el negocio en el que está.
Sale: nada guardado en el hub.
Si falla: si el hub no sabe a qué negocio pertenece, el botón no sale (nunca un botón que no hace nada).
Implicados: ninguno

### BASE-F12 Pedirle al asistente que repase la configuración
<!-- origen: old-hub:HUB_SHELL-F30 -->
Estado: parcial — el Hub aún no tiene el chat del asistente: la lista ya está al alcance del asistente, pero no hay botón «Pedírselo al asistente»
Actor: propietario, administrador, responsable, empleado
Pantalla: Inicio · Resumen
Pasos:
  1. Desde el asistente, la persona le pide que repase la configuración del negocio.
  2. El asistente lee la misma lista del Inicio, con lo que esa persona puede ver, y le dice qué falta y
     dónde se hace; cada paso sigue teniendo su «Configurar» en la lista.
Entra: la lista de lo que falta, con los permisos de quien pregunta.
Sale: nada guardado.
Si falla: sin asistente, los pasos siguen llevando a su pantalla desde la lista.
Implicados: ninguno

### BASE-F13 Perder el acceso al cambiar de rol o al salir del negocio
<!-- origen: old-saas:SAAS_AUTH-F22 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: cualquier pantalla del hub
Pasos:
  1. En erplora.com, quien gestiona el negocio le cambia el rol a una persona, la quita del negocio o le
     traspasa la propiedad.
  2. En ese momento se cierra la sesión de esa persona en este negocio, en todos sus dispositivos: lo que
     tiene abierto deja de ponerse al día y lo siguiente que haga le pide volver a entrar. Sus sesiones en
     otros negocios siguen abiertas.
  3. Si sigue en el negocio, vuelve a entrar desde erplora.com y trabaja ya con su rol nuevo: aparece lo
     que el rol nuevo permite y desaparece lo que no.
  4. Si la han quitado, al volver erplora.com le dice «No tienes acceso a este hub» y no entra.
  5. Si cambia su contraseña, cierra la sesión en todas partes o borra su cuenta en erplora.com, se cierran
     todas sus sesiones del hub, en todos sus negocios.
Entra: el cambio que hizo erplora.com (quién, en qué negocio y con qué rol, o que ya no está).
Sale: las sesiones de esa persona cerradas; su rol en el negocio, al día.
Si falla: si el hub no responde en ese momento, erplora.com lo vuelve a intentar al poco; mientras, la
siguiente vez que erplora.com le pase al hub el estado del negocio también se cierran esas sesiones.
Implicados: HUBS-F26, HUBS-F27, HUBS-F28

## Para quien lo mantiene

- Las tres consultas vivas del Inicio son de `base/queries.py`, con permiso `base.view_home` y ruta ninja en
  `base/api.py` (`GET /api/home/setup`, `/home/widgets`, `/home/bell`): `base.setup.status` (también
  herramienta del asistente, `ai=`), `base.widget.list` y `base.bell.counters`. Las reglas puras viven en
  `base/home.py` (sin ORM): las del `setup_status.rs` del hub viejo.
- Punto de extensión: cada módulo declara en su `LiveAppConfig` `setup` (`SetupStep`), `widgets`
  (`Widget`) y `bell` (`BellCounter`), dataclasses de `live.meta` comprobadas por `live.checks`
  (E009–E016). Cada consulta que nombran es un `kind="query"` de la propia app; base la ejecuta como la
  persona (`run_hook`).
- Nivel: ⛔ `legal` solo para `LEGAL_STEPS` (`invoice.business_identity`); si no, `required` →
  `functional` y si no `recommended`. Un ⛔ cuya consulta la persona no puede leer se evalúa como sistema
  (`system_context`) y sale `actionable: false`; un paso cuya consulta falla se omite y se anota en el log.
- Pasos de plataforma (solo con `base.administer_hub`): `base.apps` (orden 10; `unavailable` si no hay
  ninguna app de negocio en el catálogo) y `base.team` (orden 80; hecho con dos personas activas).
- `base/live.py`: cada consulta se re-ejecuta tras los eventos de `refresh_on` de su gancho más
  `base.hub.state_applied` (la foto del SaaS puede encender o apagar apps). Escribir en el hub B no avisa
  al A (test de dos hubs en `base/tests/test_queries_home.py`).
- Un panel con `operation` viva (está en un `live.py`) se sigue con `useLive`; si no, se pide una vez
  (`live` en `WidgetOut`). Un panel con `component` monta `apps/<app>/frontend/components/<Nombre>.vue`.
- `demo` (módulo no listado) sale en el menú, en «Mis apps» y con su ejemplo en el Inicio solo con
  `SHOW_UNLISTED_MODULES` (por defecto, `DEBUG`) o en un hub de demo (`Hub.is_demo`); nunca en el de un cliente.
  Una sola regla, `base.home.shown_modules`, para `base.session.me` y los ganchos del Inicio.
- `base/spa.py` incrusta `hub-home` (`name` del registro y `plan_url` =
  `SAAS_URL/store/plans?business=<id del hub>`).
- Navegador: el tablero se guarda en `localStorage["dashboard-hub"]` (la clave del viejo) y el uso de
  apps en `localStorage["hub-app-usage"]`. La pestaña «Actividad» es el hash `#actividad`.
- Frontend en `base/frontend/` (rutas, catálogos `en`/`es` bajo `base`, componentes y su `lib/home.ts`);
  la campana, «Actualizar plan» y la franja se enchufan en `frontend/main.ts` por `chrome` de
  `createShell`. La ruta `/` de base (`base-home`) gana a la rejilla del shell (`home`).
- Tests: `base/tests/test_home.py`, `test_queries_home.py`, `test_live.py`, `test_api.py`, `test_spa.py`;
  Vitest en `base/frontend/**`; e2e `tests/e2e/base-home.spec.ts` y `base-home-activity.spec.ts`.
- BASE-F13: cada login anota de quién y dónde es su sesión (`base.SessionOwner`, en control junto a las
  sesiones de Django; `CASCADE` con la sesión). `POST /internal/sessions/revoke {user_id, hub_id?}`
  (`base.internal.sessions_revoke` → `base.session.revoke`, firmada como todo `/internal`) borra por ese
  índice, sin descodificar ninguna sesión: las del negocio y las que no anotaron host (de antes de la regla),
  o sin `hub_id` todas, las del admin incluidas; idempotente, un negocio desconocido responde `{ended: 0}` y
  un cuerpo fuera de contrato, 422 `internal.payload_invalid`. La foto (`base.hub.state_apply`) aplica
  `members` en su transacción: rol nuevo o baja → `Membership` al día y sesiones de ese negocio cerradas; no
  crea copias locales. Tras el COMMIT se despierta el host (`_wake_open_apps`): el stream vivo re-ejecuta,
  `HubContextBuilder.refresh` ve la sesión borrada (`SessionEnded`, 401) y acaba con `bye`; `/ws/print`
  relee la sesión en cada mensaje. Tests: `base/tests/test_session_revoke.py`, `test_hub_state_members.py`,
  `test_migrations.py` (relleno de 0008); e2e con el SaaS real `tests/e2e/base-session-revoke.spec.ts`.

## Lo que NO hace, a propósito

- No inventa cifras: un panel o un paso que no se puede comprobar no sale o dice «No disponible».
- No guarda el tablero en el servidor: es de cada dispositivo, como en el hub viejo.
- No enseña nunca a un cliente los ejemplos de la app Demo.
- No tiene formulario de soporte propio: «Reportar un problema» abre el de erplora.com, que manda el aviso
  con la cuenta y el negocio; el hub no guarda nada.
