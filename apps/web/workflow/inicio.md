# WORKFLOW — Hub · pantallas · Inicio y puesta en marcha

Prefijo: HUB_SHELL

> Detalle del área «Inicio y puesta en marcha» (oleada 3): la primera pantalla tras entrar, la lista
> «Termina de configurar tu negocio», la franja que avisa de que todavía no se puede facturar, la
> plantilla de sector, «Mis apps», los paneles de las apps, la actividad y la salud. Lo que calcula
> el servidor (qué pasos hay y cuándo están hechos, qué datos da cada panel) está en `HUB`
> (HUB-F34, HUB-F35) y en cada app; aquí solo lo que se ve. Las pantallas que se citan en
> `Pantalla:` son las de `## Pantallas` del índice `apps/web/WORKFLOW.md`.

## Referencia adoptada

- **Inicio con una guía de puesta en marcha que se cierra sola al terminar, y un empuje inicial con
  plantilla de sector**: las guías de arranque de Shopify, Odoo y Square (hub#368, hub#372).
- **Tablero de paneles que aportan las apps, con presets por sector**: ADR-0054.

## Flujos

### HUB_SHELL-F25 Ver el negocio de un vistazo al entrar
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Inicio
Pasos:
1. Tras entrar se abre **Inicio** (también desde el menú, «Inicio», o el logo del pie del menú).
2. Arriba, el nombre del negocio (la razón social de Ajustes › Negocio) y «Hoy, martes, 22 de julio»; mientras el negocio no tiene nombre, un saludo según la hora («Buenos días», «Buenas tardes», «Buenas noches»).
3. Debajo, en este orden: la propuesta de plantilla si el negocio está vacío (HUB_SHELL-F26), «Mis apps» (HUB_SHELL-F32), «Termina de configurar tu negocio» (HUB_SHELL-F27), los paneles (HUB_SHELL-F33) y la salud del hub (HUB_SHELL-F37).
4. Abajo, dos pestañas: «Resumen» (lo anterior) y «Actividad» (HUB_SHELL-F36). Se puede enlazar directo a `/dashboard#actividad`.
Entra: la razón social de los ajustes del negocio; la fecha del dispositivo en el idioma de la aplicación.
Sale: nada guardado. Cada zona pide lo suyo por separado y falla por separado.
Si falla: una zona que no carga no tumba las demás; cada una dice lo suyo (ver sus flujos). En el móvil las zonas se apilan y la cuadrícula de apps se pliega a dos filas.
Implicados: REC_ALTA-F07
QA: BD-01, qa-hub-restaurant §7.00

### HUB_SHELL-F26 Empezar con una plantilla de un negocio como el tuyo
Estado: parcial — si no se puede leer el catálogo de plantillas la tarjeta simplemente no sale, sin decir por qué; «Ahora no» no se recuerda (vuelve a salir al recargar mientras el negocio siga vacío); no se puede elegir traer la plantilla sin sus datos de ejemplo
Actor: administrador
Pantalla: Inicio
Pasos:
1. En un negocio sin apps, quien lo administra ve arriba «Empieza con un negocio como el tuyo» — «Elige el que más se parezca al tuyo y te dejamos sus apps y su catálogo listos de una vez. Después tendrás que poner tus propios datos.» y «Trae además datos de ejemplo —clientes, citas— para que veas cómo funciona todo.».
2. Hasta cuatro plantillas (primero las del país del negocio, después las de su idioma), cada una con su nombre, su descripción y «Usar esta». Al lado, «Ver todas las plantillas» (lleva a Ajustes › Datos y copias) y «Ahora no» (cierra la tarjeta).
3. Pulsa «Usar esta»: «Preparando «{name}»…» mientras se descarga, se comprueba y se importa, sin pantallas intermedias.
4. Resultado en la misma tarjeta: «Ya tienes tus apps y tu catálogo» — «Lo que queda es lo que solo puedes contestar tú: los datos de tu negocio. Los tienes en la lista de abajo.» y «Los datos de ejemplo están para que trastees. Puedes quitarlos cuando quieras desde Ajustes › Datos.»; «Continuar» la cierra.
Entra: el catálogo de plantillas de erplora.com (a través del hub), el país y el idioma del negocio, el permiso de administrar.
Sale: pide al hub importar la plantilla (apps, ajustes del negocio, imágenes y datos de las apps; nunca personas ni datos fiscales). Después refresca el menú de apps, la lista de configuración, los paneles, la salud y la actividad, y, si la plantilla trae apps que piden permisos, abre la pregunta de permisos (HUB_SHELL, Ajustes y datos).
Si falla: apps que hay que añadir al plan: «Estas hay que añadirlas antes a tu plan: {apps}». Algo que no entró: «Estas no han entrado: {apps}…», «Esto no ha entrado: {parts}…» o «Hay algo más que no ha entrado…», con «Ver el informe» (Ajustes › Datos y copias). No se pudo empezar: «No se ha podido abrir esa plantilla» — «No ha cambiado nada en tu negocio…» con el motivo y «Intentar otra vez». Cortado a medias: «La configuración no ha terminado» — «Puede que parte ya esté dentro. Compruébalo en Ajustes › Datos antes de volver a intentarlo.», sin reintento.
Implicados: HUB-F234, HUB-F235, HUB-F239, REC_ALTA-F08
QA: BD-01, qa-hub-restaurant §7.00

### HUB_SHELL-F27 Seguir la lista «Termina de configurar tu negocio»
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Termina de configurar tu negocio
Pasos:
1. En **Inicio** sale la tarjeta «Termina de configurar tu negocio» con «{done} de {total} hechos» y una barra de progreso.
2. Los pasos propios del hub son cuatro, por este orden: «Tus apps», «Los datos de tu negocio» (razón social y NIF), «Configura la impresora» y «Tu equipo» (más de una persona activa); después, los de las apps (HUB_SHELL-F31). Cada fila: icono, título, descripción y su etiqueta: «Necesario para facturar» (rojo), «Importante» (ámbar), «Recomendado» (gris), «Hecho» (verde) o «Todavía no disponible» (azul). Sin desplegar se ven los pendientes más importantes (cinco; dos en el móvil) y lo heredado de una plantilla («Vino de la plantilla que usaste. Merece un vistazo: tu sala y tus precios son tuyos.»).
3. Pulsa «Configurar» en una fila: lleva a la pantalla donde se hace (Ajustes › Negocio, la impresora, Empleados, o la pantalla de la app).
4. Hazlo allí. Al volver (cualquier cambio de pantalla relee la lista) la fila sale «Hecho» y el contador sube. Nadie marca un paso a mano.
5. «Ver todo» despliega la lista entera, con lo hecho; «Ver menos» la recoge. Con todo hecho la tarjeta dice «Tu negocio está listo» — «No queda nada pendiente en la checklist.»; un paso «Recomendado» pendiente (o uno «Todavía no disponible») basta para que no salga.
Entra: la lista que calcula el hub para esta persona (`hub.setup.status`): solo los pasos que puede hacer, salvo los que bloquean la facturación, que ven todos.
Sale: nada guardado; se relee al entrar, al cambiar de pantalla, al cambiar de idioma y al instalar, activar, desactivar o quitar una app.
Si falla: si no llega respuesta, la tarjeta no sale (o se queda con la última que llegó); nunca dice «listo» sin respuesta. Cerrar sesión no borra la última lista leída: si la lectura de la persona siguiente falla, ve la de la anterior hasta que una lectura funcione. Un paso que no es de esta persona: «Esto lo tiene que configurar un administrador.» sin botón. Un paso «Todavía no disponible»: «Esto es cosa nuestra: por tu parte no hay nada que hacer aún. Estamos en ello.» sin botón. «Tus apps» no sale en Inicio porque ya lo ofrece «Mis apps»; con «Ver todo» sí.
Implicados: HUB-F35, REC_ALTA-F07
QA: BD-01, BD-02

### HUB_SHELL-F28 Ver qué falta para poder facturar
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Franja «Todavía no puedes facturar»
Pasos:
1. Mientras falte algo sin lo que el hub rechazaría un tique o una factura —los datos del negocio (razón social y NIF) siempre y, fuera del entorno de pruebas (también mientras el perfil fiscal no está resuelto) y sin vía hasta la AEAT, el paso de la app que pide el certificado (VeriFactu)—, en todas las pantallas con menú sale bajo la barra la franja roja «Todavía no puedes facturar» — «No se podrá emitir ningún ticket ni factura hasta que configures esto:».
2. Debajo, una línea por cosa que falta, cada una con su «Configurar» (o, si no te toca, «Esto lo tiene que configurar un administrador.»).
3. En un móvil apaisado la franja se pliega a una línea con «Ver qué falta» / «Ocultar».
4. La franja no se puede cerrar: desaparece sola cuando ya no falta nada. En la pestaña «Resumen» de **Inicio** no sale, porque la lista entera ya está a la vista.
Entra: el contador de pasos que bloquean y esos pasos, de la misma lista de HUB_SHELL-F27.
Sale: nada guardado; se relee en cada cambio de pantalla, así aparece también si a mitad de sesión se instala una app que pide certificado.
Si falla: sin respuesta del hub no hay franja (una lectura rota no es una respuesta). La franja no sale en Acceso.
Implicados: HUB-F35, HUB-F313, HUB-F317, VERIFACTU-F01, REC_ALTA-F07
QA: BD-02

### HUB_SHELL-F29 Dar a una app el permiso que le falta desde la lista
Estado: hecho
Actor: administrador
Pantalla: Termina de configurar tu negocio
Pasos:
1. Una fila de app que espera un permiso dice «Esta app necesita un permiso que aún no le has dado. Sin él, no puede hacer su trabajo.».
2. Su botón dice «Dar permiso» y lleva a **Ajustes → Permisos**.
3. Concede el permiso allí; al volver, la fila se relee.
Entra: los permisos que pide la app y aún no tiene, que da el hub en el paso.
Sale: nada desde aquí; el permiso se concede en Ajustes › Permisos.
Si falla: sin ser administrador, la fila no tiene botón y dice quién puede hacerlo.
Implicados: HUB-F32, REC_ALTA-F10
QA: BD-03

### HUB_SHELL-F30 Pedirle al asistente que repase la configuración
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Termina de configurar tu negocio
Pasos:
1. Al pie de la tarjeta, pulsa «Pedírselo al asistente».
2. Se abre el asistente con el tema de la configuración: «Revisa la configuración de tu negocio. Elige una opción o escribe tu duda.».
3. El asistente lee la misma lista del hub; cada fila sigue teniendo su propio «Configurar».
Entra: nada más que el tema; el asistente lee la lista por su cuenta.
Sale: abre el asistente (área del asistente de este documento).
Si falla: sin asistente disponible, las filas siguen llevando a su pantalla.
Implicados: HUB-F273
QA: ninguno

### HUB_SHELL-F31 Ver los pasos que aportan las apps
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Termina de configurar tu negocio
Pasos:
1. Cada app instalada, activa, incluida en el plan y que aplica al país del negocio puede añadir su paso a la lista: «Tu catálogo» (Inventario), «Confirma tu horario» (Horarios), «Tus mesas» (Mesas), «Tu numeración de facturas» (Facturación), los primeros pasos de Caja, «Configura VeriFactu»…
2. El paso sale con el título y la descripción que da la app, en el idioma de quien mira, y con la etiqueta que decide la app («Importante» o «Recomendado»); «Necesario para facturar» solo lo pone el hub.
3. «Configurar» abre la pantalla de la app que dice el paso.
4. Lo que se hace en esa pantalla (añadir un producto, pulsar «Sí, este es mi horario», crear la serie) deja el paso hecho la próxima vez que se relee la lista.
Entra: los pasos de las apps que añade el hub a la lista.
Sale: nada guardado.
Si falla: un paso cuya comprobación no se puede hacer (sin permiso, una lectura rota) no sale. Un título que la app no traduce sale en inglés.
Implicados: CASH_REGISTER-F01, HUB-F35, INVENTORY-F28, INVOICE-F14, SCHEDULES-F03, TABLES-F02, VERIFACTU-F01
QA: BD-01, BD-02

### HUB_SHELL-F32 Abrir una app desde «Mis apps»
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Inicio
Pasos:
1. En **Inicio**, la tarjeta «Mis apps» enseña una baldosa por app que esta persona puede abrir, con su icono y su nombre (si no cabe, el nombre entero sale al pasar por encima).
2. Las más usadas en este navegador van primero.
3. Toca una baldosa: se abre la app.
4. «Añadir apps», siempre la última, lleva a **Apps**. En el móvil, con seis apps o más se ven las cuatro primeras, «Ver todas las apps» y «Añadir apps».
Entra: la lista de apps del menú que da el hub (la misma del lanzador de la barra).
Sale: cuenta en este navegador cuántas veces se abre cada app (solo para ordenar).
Si falla: mientras carga, baldosas grises y «Cargando tus apps…» para el lector de pantalla. Sin apps de verdad: «Aquí aparecerán tus apps. Añade las que necesite tu negocio.». Si la lista no se pudo pedir: «No se han podido cargar tus apps. Recarga la página; si sigue fallando, vuelve a iniciar sesión.», nunca «no tienes apps».
Implicados: HUB-F31
QA: BD-03

### HUB_SHELL-F33 Ver los paneles de las apps en Inicio
Estado: parcial — la pantalla no filtra los paneles por permiso: quien no puede ver uno (un empleado y «Caja (sesión actual)») lo encuentra en el catálogo y, si está puesto, sale «No disponible»; las apps cuyo menú no ve esa persona no aportan paneles; instalar una app desde Apps (o el asistente, u otro dispositivo) no vuelve a leer los paneles: aparecen al recargar Inicio (al volver con «Atrás» no se releen; volviendo por el menú, sin confirmar)
Actor: administrador, responsable, empleado
Pantalla: Paneles de Inicio
Pasos:
1. En **Inicio**, bajo la lista de configuración, está el tablero de paneles («Cargando widgets…» mientras llega).
2. Cada panel es una tarjeta con su título e icono: una cifra, una lista con barras, una cronología, un gráfico o un trozo de la pantalla de la app.
3. Los que salen de primeras son los que la app marca como recomendados para el sector del negocio; si el negocio no tiene sector, hasta seis recomendados, repartidos entre apps.
4. Mientras el negocio está vacío hay además el panel «Configura tu negocio» — «Carga una plantilla para tu negocio o restaura una copia para empezar.» con «Configurar», que lleva a Ajustes › Datos y copias; desaparece del catálogo en cuanto hay apps.
Entra: el bloque `widgets` del `module.json` de cada app activa, del plan y con menú visible para quien mira; los datos de cada panel, pedidos por la puerta normal de consultas con los permisos de quien mira, como mucho cuatro a la vez.
Sale: nada guardado en el hub.
Si falla: panel sin filas: «Sin datos». Consulta rechazada o rota: «No disponible», nunca una cifra vieja o inventada. Si no se pueden leer los manifiestos, no hay paneles de apps y el tablero dice «Panel vacío. Pulsa ⋮ para añadir widgets.».
Implicados: CASH_REGISTER-F12, HUB-F34, INVENTORY-F17, VERIFACTU-F31
QA: R-01, qa-hub-restaurant §7.12

### HUB_SHELL-F34 Personalizar el tablero de paneles
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Paneles de Inicio
Pasos:
1. Pulsa ⋮ («Personalizar panel») en el tablero.
2. En «Empezar desde un preset» elige «Recomendado» (si el negocio tiene sector); en «Activos · arrastra para reordenar» ordena o quita; en «Disponibles» añade.
3. «Cerrar» deja el tablero como quedó.
Entra: el catálogo de paneles de HUB_SHELL-F33.
Sale: el tablero elegido, guardado en este navegador: lo comparten todas las personas que usan este dispositivo y no viaja a otro.
Si falla: un panel guardado que ya no está en el catálogo (su app se quitó) desaparece del tablero sin aviso.
Implicados: HUB-F34
QA: ninguno

### HUB_SHELL-F35 Mantener los paneles al día sin recargar
Estado: hecho
Actor: sistema
Pantalla: Paneles de Inicio
Pasos:
1. Cada panel declarativo (cifra, lista, cronología, gráfico) puede declarar qué avisos de su app lo cambian (una venta, un movimiento de caja, un recuento).
2. Cuando el hub emite en vivo uno de esos avisos, el panel vuelve a pedir sus datos a los 0,8 s (varios avisos seguidos cuentan como uno), sin vaciarse mientras tanto.
3. Un panel sin avisos declarados se pinta una vez al entrar y no se mueve hasta volver a cargar Inicio. Un panel que es un trozo de la pantalla de la app se pinta una vez y solo se refresca si la app lo hace por su cuenta.
Entra: los avisos en vivo del hub que el panel declara (`refresh_on`).
Sale: nada guardado.
Si falla: el refresco que falla deja «No disponible», no el valor de antes. Un panel no se refresca con un aviso que su app no declara (por ejemplo, el stock tras una venta).
Implicados: CASH_REGISTER-F12, HUB-F34, HUB-F60, INVENTORY-F17, VERIFACTU-F31
QA: qa-hub-restaurant §7.12

### HUB_SHELL-F36 Consultar la actividad reciente
Estado: parcial — en tableta (unos 820 px) la columna «Fecha» de la tabla corta la hora de la venta (hub#2637)
Actor: administrador, responsable, empleado
Pantalla: Inicio
Pasos:
1. En **Inicio**, pestaña «Actividad».
2. «Cargando…» y después una tabla con las últimas 100 ventas: «Fecha», «Venta», «Cliente», «Método» (con el nombre del historial de Ventas: los métodos de fábrica traducidos, «Efectivo» y «Tarjeta»; los que creó o renombró el negocio, con su nombre), «Importe» (con la moneda del negocio: 12,50 € sale «12,50 €») y «Estado», con las palabras del historial de Ventas: «Completada» en verde, «Anulada» en rojo, «Devuelta» en ámbar, «Pendiente» y «Borrador» en gris, y «Otro» en gris para un estado que esta pantalla aún no conoce.
3. Busca con «Buscar actividad…» (venta, cliente o método), filtra por método o estado, ordena, cambia a tarjetas o elige columnas; 15 por página.
Entra: las ventas de la app Ventas (`sales.list`, con el total en céntimos, que se pintan con `formatMoney`), si está activa, con los permisos de quien mira, y las palabras de sus métodos de fábrica del catálogo de la propia app Ventas (`locales/<idioma>.json`, el mismo que usa su historial), en el idioma en pantalla. Solo ventas: los demás movimientos del negocio (caja, citas) no salen aquí.
Sale: nada guardado.
Si falla: sin la app Ventas, la tabla vacía. Si no se puede leer el catálogo de Ventas, el método sale con el nombre guardado («Cash»), nunca en blanco. Si no se pueden leer las ventas: «No se han podido cargar las últimas ventas» — «Comprueba la conexión y vuelve a intentarlo.» con «Reintentar», en lugar de la tabla; si ya había ventas en pantalla (un refresco tras importar una plantilla), se quedan debajo del aviso.
Implicados: SALES-F28
QA: ninguno

### HUB_SHELL-F37 Ver si la impresora y WhatsApp funcionan
Estado: parcial — el detalle de cada aviso solo se lee pasando el ratón por encima (en una tableta no se ve); «No hemos podido comprobar la impresora» promete «Volveremos a comprobarlo solos» y solo se relee al volver a Inicio
Actor: administrador, responsable, empleado
Pantalla: Inicio
Pasos:
1. Al pie de «Resumen», una fila con lo que el hub sabe de sí mismo y «Ver sistema», que lleva a **Sistema**.
2. Con la app Impresión activa: «Impresora lista» (alguien está imprimiendo tiques), «Impresora sin conectar» con «Configurar la impresión», o «No hemos podido comprobar la impresora».
3. Con la app de WhatsApp activa y un número que dejó de funcionar solo: «WhatsApp ha dejado de funcionar» con «Volver a conectar WhatsApp», que lleva a sus Ajustes.
4. Arreglado lo que sea, al volver a **Inicio** la fila se relee.
Entra: la cobertura de impresión del hub (quién imprime tiques ahora), la lista de apps instaladas y, solo con WhatsApp, sus números a través de erplora.com.
Sale: nada guardado.
Si falla: sin app de impresión o de WhatsApp no hay aviso de esa cosa. Si no se puede saber qué hay instalado, o leer los números de WhatsApp, no se dice nada (no se sabe ≠ caído).
Implicados: HUB-F202, HUB-F261, WHATSAPP_INBOX-F02
QA: ninguno

### HUB_SHELL-F38 Ir a configurar desde el panel «Configura tu negocio»
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Paneles de Inicio
Pasos:
1. Mientras el negocio no tiene apps, el tablero trae el panel «Configura tu negocio» — «Carga una plantilla para tu negocio o restaura una copia para empezar.».
2. Pulsa «Configurar»: lleva a **Ajustes → Datos y copias**, donde se carga una plantilla o se restaura una copia.
3. Como cualquier panel, se puede quitar con ⋮.
Entra: si el negocio está vacío, según la lista de HUB_SHELL-F27.
Sale: nada guardado.
Si falla: sin respuesta de la lista, el panel no se añade hasta que llegue.
Implicados: ninguno
QA: BD-01

### HUB_SHELL-F39 Ver Inicio al día después de importar una plantilla
Estado: hecho
Actor: administrador
Pantalla: Inicio
Pasos:
1. Termina una importación desde la tarjeta de plantillas o desde Ajustes › Datos y copias.
2. Sin recargar, **Inicio** vuelve a leer la lista de configuración, los paneles (el de «Configura tu negocio» se va si ya hay apps), la salud y la actividad; «Mis apps» y el lanzador enseñan las apps nuevas.
3. El informe de lo que entró y lo que no queda en Ajustes › Datos y copias, al que lleva «Ver el informe».
Entra: el aviso de fin de importación de la propia pantalla.
Sale: nada guardado.
Si falla: lo que no se pudo leer conserva lo último que se leyó; la actividad, además, dice que no pudo (HUB_SHELL-F36).
Implicados: HUB-F239
QA: BD-01

## Cobertura contra la referencia

| Elemento de la referencia | Estado | Flujo |
|---|---|---|
| Guía de puesta en marcha con progreso | hecho | F27 |
| Pasos que nadie marca a mano: se comprueban | hecho | F27, F31 |
| Bloqueo legal visible en todas las pantallas | hecho | F28 |
| Delegar un paso que no es tuyo | hecho («Esto lo tiene que configurar un administrador.») | F27 |
| Plantilla de sector de un clic | parcial: fallo del catálogo mudo; «Ahora no» no se recuerda | F26 |
| Datos de ejemplo opcionales | no hecho: vienen siempre con la plantilla | F26 |
| Paneles por app con presets por sector | parcial: sin filtro por permiso en la pantalla | F33, F34 |
| Tablero guardado por persona | no hecho: se guarda por navegador | F34 |
| Paneles en vivo | hecho para lo que la app declara | F35 |
| Actividad reciente | parcial: solo ventas (caja y citas no salen); en tableta la fecha corta la hora (hub#2637) | F36 |
| Estado de la impresora y de WhatsApp | parcial: detalle solo al pasar el ratón | F37 |

## Datos: de quién es cada dato

La lista de puesta en marcha y los paneles son del hub y de cada app (HUB-F34, HUB-F35). Lo que esta
área guarda en el navegador del dispositivo:

| Dónde (navegador) | Qué guarda | Dato personal | Cuándo se borra |
|---|---|---|---|
| `erplora.apps.usage` | cuántas veces se abre cada app | no | nunca |
| tablero de paneles (`okwb:dashboard-hub`) | qué paneles y en qué orden | no | nunca; compartido por quien use el navegador |

En memoria (no en el navegador) queda, tras cerrar sesión, la última lista de puesta en marcha.

## Reglas que no se rompen

- La franja «Todavía no puedes facturar» no se puede cerrar y solo sale con un paso «Necesario para
  facturar» pendiente.
- Un panel que falla dice «No disponible»: nunca un valor viejo ni inventado.

## Dudas abiertas

Se resuelven con `market-decision`; no las decide el worker.

- **Tablero por persona o por dispositivo.** Hoy se guarda en el navegador y lo comparten todos los de
  una caja (HUB_SHELL-F34).

## Fuentes contrastadas

- Manual 02: «el tablero incluye una entrada de datos del núcleo»: solo mientras el negocio no tiene
  apps (hub#2199).
- `cash_register` CASH_REGISTER-F12 dice que el empleado no ve «Caja (sesión actual)»: la pantalla no
  filtra paneles por permiso (`DashboardPage.vue`, `hasPermission: () => null`); lo ve en el catálogo
  y, si está puesto, sale «No disponible».
- `src/i18n/locales/es.ts`: `dashboard.noWidgets` («Ninguna app instalada ofrece widgets todavía.»)
  no lo usa ninguna pantalla.
- `system.health.printerUnknownDetail` promete «Volveremos a comprobarlo solos»; Inicio solo lo relee
  al volver a la pantalla.
- `src/lib/dashboard-activity.test.ts` alimentaba `total: '12.5'` (euros) cuando `sales.list` da
  céntimos, y por eso no detectó el importe ×100 de HUB_SHELL-F36 (hub#2505); hoy usa céntimos y lo
  vigilan `lib/dashboard-activity.hub2505.test.ts` y `views/dashboard-activity.hub2505.test.ts`.
- QA `qa-hub-restaurant` §7.00 pide «recargar y volver a entrar: no reaparece onboarding»: la tarjeta
  de plantillas reaparece al recargar mientras el negocio siga sin apps («Ahora no» no se recuerda).
- Dos textos de la tarjeta de plantillas («Puedes quitarlos cuando quieras desde Ajustes › Datos.» y
  «Compruébalo en Ajustes › Datos antes de volver a intentarlo.») nombran la pestaña como «Datos»; su
  rótulo es «Datos y copias».
