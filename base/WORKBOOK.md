# Workbook — Base (plataforma)
Prefijo: BASE
Alcance MVP: fase 1 (el Inicio del hub; el resto de la plataforma llega por partes)
Estado de la app: en construcción (2026-10-22)

> Manual de usuario y especificación de `base`, la plataforma del Hub: siempre está, no se activa ni se
> apaga. Esta primera parte describe el **Inicio**, la pantalla a la que se llega al entrar en el negocio
> (el del hub viejo: saludo, «Mis apps», la lista de lo que falta por configurar, los paneles de las apps y
> la actividad), con lo que acompaña a cualquier pantalla: la campana, «Actualizar plan» y la franja que
> avisa cuando todavía no se puede facturar. Las plantillas y Ajustes › Datos llegan en la parte siguiente.
> El acceso (entrar con la cuenta, con PIN o con la placa, cambiar de usuario, Mi perfil y los dispositivos) está
> en sus propias pantallas, más abajo.

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

- Se entra con la cuenta de ERPlora; el Hub no tiene entrada propia. En una caja compartida, después, cada persona
  entra con su PIN o con su placa.
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
Se abre tocando a la persona, arriba del menú lateral. Primero «Perfil» y, en una caja compartida de un negocio
que pide PIN, «Cambiar de usuario»; después, solo si se entró con la cuenta (nunca en una sesión de PIN), «Mi
cuenta» y «Reportar un problema», que abren esas páginas en erplora.com (en una pestaña nueva; en la app
instalada, en el navegador del dispositivo); al final «Tema» (claro, oscuro o el del sistema) y «Cerrar sesión».
Las de erplora.com salen también en la app instalada: ninguna vende nada.

### La franja «Todavía no puedes facturar»
Encima de cualquier pantalla mientras falta un paso que impide facturar: «No se podrá emitir ningún
ticket ni factura hasta que configures esto:» y cada paso con «Configurar» (en la pantalla que lo configura,
solo su nombre). En el «Resumen» del Inicio no sale (la lista dice lo mismo un poco más abajo); en
«Actividad», sí.

### Apps
Desde «Apps» en el menú lateral. Tres pestañas abajo: «Mis apps» (las apps que el negocio tiene en marcha),
«Añadir apps» (todas las apps de ERPlora) y «De pago» (las que se contratan aparte). Cada una, una tabla (o
tarjetas) con su buscador, el embudo de filtros, el orden y «Columnas»: «App» (icono y nombre), «Categoría» y
«Estado»; en «Añadir apps» y «De pago», además «Descripción», «Precio» y «Viene con». «Abrir» en la fila de una
app que la persona puede abrir.

### La pantalla de una app que no se abre
En la misma dirección de la pantalla de la app, el motivo: «Suscripción necesaria» o «Esta app no está
disponible en este negocio», con «Ir a Apps» (y «Contratar en erplora.com» para quien administra, en el
navegador).

### Sistema · Plan y límites
Desde «Sistema» en el menú lateral, la pestaña «Plan y límites»: «Los límites de tu plan» con «Dentro del
límite» o «Cerca del límite», las tarjetas «Personas» y «Dispositivos» y dónde se gestionan los planes.

### Acceso
La entrada de una caja compartida, o de un dispositivo al que otra entrada le cerró la sesión, sin menú ni barra:
el logo, «Entra en tu negocio», el aviso de lo que pasó si lo hay y una tarjeta con dos pestañas, «PIN» (las
caras, el teclado y la placa) y «Cuenta» («Entrar con tu cuenta», que lleva a erplora.com). Al pie, «ERPlora ·
dispositivo de confianza»; arriba a la derecha, el cambio entre claro y oscuro.

### Crea tu PIN de acceso
Tras entrar con la cuenta en una caja: el teclado de círculos para elegir el PIN y repetirlo, y «Ahora no».

### Cambiar de usuario
Sobre la pantalla en curso, sin menú: «La venta sigue abierta. A partir de ahora queda a nombre de quien entre
aquí.», «¿Quién se pone?» con las caras, el teclado y «Cancelar».

### Mi perfil
Desde «Perfil» del menú de usuario. Arriba, la persona (cara, nombre y rol); debajo, «Datos de la cuenta» (con la
foto), «Preferencias» (idioma y apariencia) y «PIN».

### Ajustes · General
Desde «Ajustes» en el menú lateral. Hoy, una sola sección (las pestañas de abajo salen cuando haya dos): «Este
dispositivo», «Pinpad» y, para quien administra, «Dispositivos».

### Estamos preparando tu negocio
La página que sale en la dirección de un negocio que erplora.com aún está preparando; se actualiza sola.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | Baldosas grises en «Mis apps» («Cargando tus apps…» para el lector de pantalla), la lista en gris, «Cargando widgets…» en el tablero, la cifra de cada panel en gris y «Cargando…» en «Actividad»; «Cargando…» en el pinpad, «Cargando tu perfil…» y «Cargando los dispositivos…». |
| Vacío | «Aquí aparecerán tus apps. Añade las que necesite tu negocio.»; sin pasos, la lista no sale; «Panel vacío. Pulsa ⋮ para añadir widgets.»; un panel sin datos, «Sin datos»; la campana, «Todo al día. Sin notificaciones.»; «Todavía no ha entrado nadie desde ningún dispositivo.»; en «Cambiar de usuario», «Aquí nadie tiene PIN todavía: se pone en Mi perfil o en Empleados.». |
| Error | Cada zona falla por su cuenta: «No se han podido cargar tus apps. Recarga la página; si sigue fallando, vuelve a iniciar sesión.», «No se ha podido cargar lo que te falta por configurar» con «Reintentar», «No se han podido cargar los paneles» con «Reintentar», un panel con «No disponible» (nunca la cifra de antes), «No se han podido cargar las últimas ventas» con «Reintentar» y, en la campana, «No se han podido comprobar las notificaciones. Aparecerán cuando vuelva la conexión.». En el acceso: «No se pudo cargar el pinpad. Puedes entrar con tu cuenta.», «No se pudo cargar el perfil» con «Reintentar», «No se pudo cargar este dispositivo. Comprueba la conexión e inténtalo de nuevo.», «No se pudo cargar cómo pide el PIN el negocio. Comprueba la conexión e inténtalo de nuevo.» y «No se pudieron cargar los dispositivos. Comprueba la conexión e inténtalo de nuevo.». |
| Sin permiso | Un paso que la persona no puede hacer: sin botón y «Esto lo tiene que configurar un administrador.». Un panel o un contador que no puede ver, no sale. En Ajustes, quien no administra ve «Este dispositivo» y «Pinpad» con los controles apagados («Solo un administrador puede cambiar cómo entra la gente en este dispositivo.», «Solo un administrador puede cambiar si se pregunta.») y, en lugar de la lista, «Solo un administrador puede ver y quitar los dispositivos.». |

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
| BASE-F14 | Ver las apps del negocio | hecho |
| BASE-F15 | Abrir una app desde Apps | hecho |
| BASE-F16 | Buscar una app en el catálogo | hecho |
| BASE-F17 | Saber cuánto cuesta una app antes de tenerla | hecho |
| BASE-F18 | Instalar una app | parcial |
| BASE-F19 | Saber qué más viene con una app | parcial |
| BASE-F20 | Intentar usar una app que necesita suscripción | hecho |
| BASE-F21 | Ver por qué no se ha podido activar una app y reintentarlo | parcial |
| BASE-F22 | Seguir la activación de una app mientras se navega | parcial |
| BASE-F23 | Desactivar una app | parcial |
| BASE-F24 | Activar una app | parcial |
| BASE-F25 | Ver que una app se niega a desactivarse | parcial |
| BASE-F26 | Entender por qué una app no se abre | hecho |
| BASE-F27 | Ver una app de pago bloqueada | hecho |
| BASE-F28 | Ver cuánto de los límites del plan se está usando | parcial |
| BASE-F29 | Entrar con la cuenta de erplora.com | hecho |
| BASE-F30 | Entrar desde el panel de erplora.com sin volver a teclear la contraseña | hecho |
| BASE-F31 | Elegir el PIN la primera vez que se entra en una caja | hecho |
| BASE-F32 | Entrar con PIN | hecho |
| BASE-F33 | Entrar pasando la placa | hecho |
| BASE-F34 | Perder la sesión porque se abrió en otro dispositivo | hecho |
| BASE-F35 | La sesión termina mientras se trabaja | hecho |
| BASE-F36 | Cerrar la sesión de una caja que nadie toca | hecho |
| BASE-F37 | Cambiar de usuario sin perder la venta | hecho |
| BASE-F38 | Cerrar sesión | hecho |
| BASE-F39 | Decidir si este dispositivo es compartido o personal | hecho |
| BASE-F40 | Abrir un hub que todavía no está dado de alta | hecho |
| BASE-F41 | Cambiar mis datos, foto, idioma y apariencia | hecho |
| BASE-F42 | Cambiar mi PIN desde Mi perfil | hecho |
| BASE-F43 | Elegir cuántos dígitos tiene el PIN del negocio | hecho |
| BASE-F44 | Decidir si se pide PIN en la caja y cuándo se vuelve a pedir | hecho |
| BASE-F45 | Ver los dispositivos en los que se ha entrado | hecho |
| BASE-F46 | Ponerle nombre a un dispositivo | hecho |
| BASE-F47 | Quitar un dispositivo que se ha perdido | hecho |
| BASE-F48 | Quitar de golpe los dispositivos que nadie usa | hecho |

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
  2. Cada panel es una tarjeta con su título e icono: una cifra (con debajo lo que cuenta, si su app lo dice),
     una lista con barras, una cronología, un gráfico o un trozo de la pantalla de su app, con sus textos en el
     idioma de quien mira.
  3. En un gráfico de días, cada barra lleva debajo su día de la semana (o su fecha, si abarca más de una
     semana) y encima salen el día y su importe: los de la última barra hasta que tocas otra.
  4. En una cronología, cada entrada dice cuándo pasó, en la hora del dispositivo: solo la hora si fue hoy
     (9:15); si fue ayer, Ayer delante (Ayer 18:10); si no, la fecha corta con la hora (20 oct, 18:10), con
     el año si es de otro. Al dejar el puntero encima sale la fecha entera. Con el Inicio abierto, lo de hoy
     pasa a ayer al cambiar el día.
  5. De entrada salen los que cada app marca como recomendados para el sector del negocio.
  6. Solo salen los paneles de las apps encendidas que esta persona puede ver.
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

### BASE-F14 Ver las apps del negocio
<!-- origen: old-hub:HUB_SHELL-F105 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Apps
Pasos:
  1. Pulsa «Apps» en el menú lateral. Se abre en la pestaña «Mis apps»; «Añadir apps» y «De pago» tienen
     también su dirección, que se puede enlazar.
  2. Mientras llega la lista: «Cargando tus apps…». Después, una fila (o una tarjeta, a elegir) por cada app que
     el negocio tiene en marcha, con su icono y su nombre, su «Categoría» y su «Estado» («Activa»).
  3. Busca en «Buscar en tus apps…» (nombre, descripción o categoría), filtra por categoría con el embudo,
     ordena o elige columnas.
  4. Cuando el negocio contrata una app en erplora.com o deja de tenerla, la lista se pone al día sola, sin
     recargar.
Entra: las apps que trae el hub y lo que el negocio tiene contratado en erplora.com.
Sale: nada guardado.
Si falla: «No hemos podido leer tus apps» — «No ha habido respuesta, o esta sesión ya no es válida: vuelve a
entrar si sigue pasando.» con «Reintentar»; la lista que ya había se queda debajo (un fallo nunca dice que no
hay apps). Sin ninguna app: «Aún no tienes apps. Abre «Añadir apps» para verlas todas.».
Implicados: ninguno

### BASE-F15 Abrir una app desde Apps
<!-- origen: old-hub:HUB_SHELL-F106 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Apps
Pasos:
  1. En la fila de una app de «Mis apps», pulsa «Abrir».
  2. Se abre la primera pantalla de esa app que la persona puede ver.
Entra: el menú de la app y lo que la persona puede ver.
Sale: nada guardado.
Si falla: una app que la persona no puede abrir, o que no está en marcha, no lleva «Abrir» (no sale apagado: no
sale). Al pulsarlo se vuelve a comprobar, por si acaba de cambiar: si ya no está en marcha, no abre nada.
Implicados: ninguno

### BASE-F16 Buscar una app en el catálogo
<!-- origen: old-hub:HUB_SHELL-F107 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Apps
Pasos:
  1. En Apps, pulsa «Añadir apps» (todas las apps de ERPlora) o «De pago» (solo las que se contratan aparte).
  2. Mientras llega: «Cargando el catálogo…». Después, una fila por app con «App», «Categoría», «Descripción»,
     «Precio», «Viene con» y «Estado» («Instalada» o «Necesita suscripción»), con los nombres y las
     descripciones en el idioma de quien mira.
  3. Busca en «Buscar apps para añadir…» (en «De pago», «Buscar apps de pago…») por nombre, descripción o
     categoría, y filtra por categoría o por estado.
Entra: las apps que trae el hub y lo que el negocio tiene contratado en erplora.com.
Sale: nada guardado.
Si falla: como en «Mis apps» (BASE-F14). Una búsqueda sin resultados: «No hay apps que coincidan con tu
búsqueda.».
Implicados: APPS-F01

### BASE-F17 Saber cuánto cuesta una app antes de tenerla
<!-- origen: old-hub:HUB_SHELL-F108 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Apps
Pasos:
  1. En «Añadir apps» o «De pago», la columna «Precio» dice de cada app: «Gratis» (va con cualquier plan),
     «Incluida en tu plan», «Contratada», «Incluida con» y la app que la trae (una de pago que viene con otra que
     el negocio tiene) o «De pago».
  2. El importe de una app «De pago» está en la Tienda de erplora.com; quien administra el negocio la abre desde
     «Contratar en erplora.com» (BASE-F20).
  3. «De pago» reúne solo las apps que se contratan aparte: una gratis nunca sale ahí. Si ninguna se vende
     aparte: «Ninguna app se vende aparte: todas vienen con tu plan.».
Entra: si cada app se contrata aparte y lo que el negocio tiene contratado en erplora.com.
Sale: nada guardado. El hub no cobra ni enseña importes: el precio y la compra son de erplora.com.
Si falla: sin la lista, como en «Mis apps» (BASE-F14).
Implicados: APPS-F01, APPS-F07

### BASE-F18 Instalar una app
<!-- origen: old-hub:HUB_SHELL-F109 -->
Estado: parcial — en esta fase todas las apps de ERPlora vienen ya en marcha en cada negocio (las de pago, en cuanto se contratan): encender o apagar una app por negocio llega con la activación de apps
Actor: administrador
Pantalla: Apps
Pasos:
  1. Las apps gratis ya están en «Mis apps» y en el menú; una de pago aparece sola en los dos, sin recargar, en
     cuanto se contrata en erplora.com (BASE-F20).
  2. En «Añadir apps», quien administra activa una app que el negocio no usa: mientras se prepara, la fila dice
     «Activando…»; después pasa a «Instalada» y la app sale en «Mis apps» y en el menú.
Entra: la app elegida y lo que el negocio tiene contratado en erplora.com.
Sale: la app en marcha en este negocio.
Si falla: BASE-F21.
Implicados: APPS-F07

### BASE-F19 Saber qué más viene con una app
<!-- origen: old-hub:HUB_SHELL-F110 -->
Estado: parcial — Apps ya dice lo que trae cada app y con qué app viene una de pago; el aviso al encenderla, que nombra lo que se encendió con ella, llega con la activación de apps por negocio
Actor: administrador
Pantalla: Apps
Pasos:
  1. En «Añadir apps», la columna «Viene con» nombra las apps que necesita cada una (por ejemplo, «Ventas / TPV»
     viene con «Clientes» e «Impuestos»): quien tiene una tiene también las que trae.
  2. Una app de pago que el negocio tiene porque la necesita otra que ha contratado dice en «Precio» «Incluida
     con» y el nombre de esa otra.
  3. Al encender una app que necesita otras, el aviso nombra también las que se encendieron con ella.
Entra: lo que necesita cada app.
Sale: nada guardado.
Si falla: si una app de pago trae otra de pago que no se ha contratado, las dos se contratan juntas: hasta
entonces, «Necesita suscripción».
Implicados: ninguno

### BASE-F20 Intentar usar una app que necesita suscripción
<!-- origen: old-hub:HUB_SHELL-F111 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Apps
Pasos:
  1. Una app de pago que el negocio no tiene contratada sale en «Añadir apps» y en «De pago» con «Necesita
     suscripción», y no está en «Mis apps» ni en el menú.
  2. Quien administra el negocio, en el navegador, ve a su lado «Contratar en erplora.com», que abre la Tienda de
     erplora.com de este negocio en una pestaña nueva: allí ve el precio y la contrata.
  3. En cuanto erplora.com se lo dice al hub, la app pasa a «Instalada» y aparece en «Mis apps» y en el menú, sin
     recargar.
  4. Quien no administra el negocio, y cualquiera en la app instalada, ve «Se contrata en erplora.com, desde tu
     cuenta de ERPlora.» y ningún botón: el hub nunca vende.
Entra: lo que el negocio tiene contratado, tal y como erplora.com se lo pasa al hub.
Sale: nada guardado ni cobrado en el hub.
Si falla: hasta que erplora.com se lo dice al hub, la app sigue con «Necesita suscripción»; una pantalla suya
que se abra dice por qué (BASE-F27).
Implicados: APPS-F07

### BASE-F21 Ver por qué no se ha podido activar una app y reintentarlo
<!-- origen: old-hub:HUB_SHELL-F112 -->
Estado: parcial — en esta fase todas las apps de ERPlora vienen ya en marcha en cada negocio (las de pago, en cuanto se contratan): encender o apagar una app por negocio llega con la activación de apps
Actor: administrador
Pantalla: Apps
Pasos:
  1. La activación de una app no termina: sus datos no se han podido preparar.
  2. Su fila dice que no se ha podido activar y ofrece «Reintentar», que la vuelve a pedir; mientras tanto la app
     no se abre.
Entra: el motivo que da el hub.
Sale: nada; la app sigue como estaba.
Si falla: si vuelve a fallar, vuelve a decirlo con su «Reintentar».
Implicados: ninguno

### BASE-F22 Seguir la activación de una app mientras se navega
<!-- origen: old-hub:HUB_SHELL-F113 -->
Estado: parcial — en esta fase todas las apps de ERPlora vienen ya en marcha en cada negocio (las de pago, en cuanto se contratan): encender o apagar una app por negocio llega con la activación de apps
Actor: administrador
Pantalla: Apps
Pasos:
  1. Quien administra activa una app (BASE-F18) y se va a otra pantalla.
  2. La app sale «Activando…» en «Mis apps» y en el menú hasta que está lista; entonces se abre como cualquier
     otra, en todos los dispositivos del negocio, sin recargar.
Entra: cómo va la activación.
Sale: nada guardado.
Si falla: BASE-F21.
Implicados: ninguno

### BASE-F23 Desactivar una app
<!-- origen: old-hub:HUB_SHELL-F122 -->
Estado: parcial — en esta fase todas las apps de ERPlora vienen ya en marcha en cada negocio (las de pago, en cuanto se contratan): encender o apagar una app por negocio llega con la activación de apps
Actor: administrador
Pantalla: Apps
Pasos:
  1. En «Mis apps», quien administra desactiva una app.
  2. Le pregunta, con el nombre de la app, y nombra las apps que se apagan con ella porque la necesitan.
  3. Confirma: la app y las que la necesitan salen del menú y de «Mis apps». No se borra nada: al volver a
     activarla queda como estaba.
Entra: las apps del negocio y lo que necesita cada una.
Sale: la app apagada en este negocio, con sus datos intactos.
Si falla: BASE-F25.
Implicados: VERIFACTU-F32

### BASE-F24 Activar una app
<!-- origen: old-hub:HUB_SHELL-F123 -->
Estado: parcial — en esta fase todas las apps de ERPlora vienen ya en marcha en cada negocio (las de pago, en cuanto se contratan): encender o apagar una app por negocio llega con la activación de apps
Actor: administrador
Pantalla: Apps
Pasos:
  1. En «Añadir apps», quien administra vuelve a activar una app que apagó.
  2. Le pregunta y nombra las apps que se encienden con ella porque las necesita; confirma y la app vuelve al menú
     con los datos que tenía.
Entra: lo que necesita la app y lo que el negocio tiene contratado.
Sale: la app en marcha en este negocio.
Si falla: una app de pago sin contratar no se puede activar: BASE-F20.
Implicados: ninguno

### BASE-F25 Ver que una app se niega a desactivarse
<!-- origen: old-hub:HUB_SHELL-F125 -->
Estado: parcial — en esta fase todas las apps de ERPlora vienen ya en marcha en cada negocio (las de pago, en cuanto se contratan): encender o apagar una app por negocio llega con la activación de apps
Actor: administrador
Pantalla: Apps
Pasos:
  1. Quien administra intenta desactivar una app que otra en marcha necesita, o VeriFactu con registros que la
     AEAT aún no ha aceptado.
  2. El hub se niega, no cambia nada y dice por qué, con lo que hay que hacer antes.
Entra: el motivo de la app que se niega.
Sale: nada.
Si falla: sin motivo propio de la app, un aviso de que no se ha podido cambiar.
Implicados: VERIFACTU-F32

### BASE-F26 Entender por qué una app no se abre
<!-- origen: old-hub:HUB_SHELL-F41 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: La pantalla de una app que no se abre
Pasos:
  1. Abre una pantalla de una app (desde un enlace, el historial o una pestaña que se quedó abierta) que en este
     negocio no se puede usar ahora.
  2. En lugar de la app, en la misma dirección, mientras lo comprueba: «Comprobando por qué no se abre esta
     app…».
  3. Después, el motivo: «Suscripción necesaria» (BASE-F27), o «Esta app no está disponible en este negocio» —
     «Búscala en Apps, o abre otra desde el menú.»; los dos con «Ir a Apps».
Entra: lo que el negocio tiene de cada app.
Sale: nada.
Si falla: «No se ha podido comprobar por qué no se abre esta app» — «Comprueba la conexión y vuelve a
intentarlo.» con «Reintentar»: nunca un motivo inventado. Una dirección que no existe en el hub dice que no
existe, como cualquier otra. Una app que la persona no puede ver se abre igual y cada pantalla dice que no tiene
permiso.
Implicados: ninguno

### BASE-F27 Ver una app de pago bloqueada
<!-- origen: old-hub:HUB_SHELL-F49 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: La pantalla de una app que no se abre
Pasos:
  1. El negocio deja de tener una app de pago (su suscripción en erplora.com termina) o alguien abre una que no
     ha contratado.
  2. Al abrir cualquier pantalla suya ve «Suscripción necesaria»: el nombre de la app y «está deshabilitada porque
     este negocio no tiene su suscripción. Tus datos están a salvo y vuelven en cuanto se contrate.», con «Ir a
     Apps» y, para quien administra en el navegador, «Contratar en erplora.com».
  3. La app sale del menú y de «Mis apps», y el hub no hace nada de lo que se le pida a esa app, venga de esta
     pantalla, de otro dispositivo, del asistente o de una integración.
  4. Si se contrata con la pantalla abierta, cambia al nombre de la app con «ya está lista» — «Ya se puede
     usar.» y «Abrir» con su nombre, que la abre al día.
Entra: lo que el negocio tiene contratado, tal y como erplora.com se lo pasa al hub.
Sale: nada; los datos de la app no se tocan.
Si falla: si nadie avisa al hub cuando termina el periodo contratado, el hub lo nota solo al pasar la fecha. Un
negocio de demostración tiene todas las apps, también las de pago, para probarlas.
Implicados: APPS-F07

### BASE-F28 Ver cuánto de los límites del plan se está usando
<!-- origen: old-hub:HUB_SHELL-F128 -->
Estado: parcial — sin cuántos dispositivos se usan: el hub aún no lleva la cuenta de sus dispositivos (llega con los dispositivos de confianza); la memoria, la CPU y la base de datos ya no se miden por negocio (el uso lo mide erplora.com)
Actor: propietario, administrador
Pantalla: Sistema · Plan y límites
Pasos:
  1. Pulsa «Sistema» en el menú lateral: se abre «Plan y límites».
  2. Ve «Los límites de tu plan» con «Dentro del límite» o «Cerca del límite», la tarjeta «Personas» (las
     personas activas del negocio frente a las que permite el plan, con su barra; o «Sin límite») y la de
     «Dispositivos» («Hasta» y el tope del plan, o «Sin límite»).
  3. Con todas las plazas ocupadas: «Te estás quedando sin margen en tu plan» — «Tu plan tiene todas las plazas
     ocupadas, así que no puedes añadir a nadie más.», sin botón.
  4. Abajo: «Los planes se gestionan desde tu cuenta de ERPlora, en erplora.com.». Se pone al día solo cuando
     cambian el plan o las personas.
Entra: los topes del plan que erplora.com le pasa al hub y las personas activas del negocio.
Sale: nada guardado.
Si falla: «No hemos podido leer tu plan» — «Comprueba la conexión y vuelve a intentarlo.» con «Reintentar».
Quien no administra el negocio ve «Solo quien administra el negocio ve el plan y sus límites.», sin
«Reintentar». Mientras el hub no conoce el plan: «Todavía no conocemos el plan de este negocio: aparecerá en
cuanto erplora.com lo envíe.».
Implicados: ninguno

### BASE-F29 Entrar con la cuenta de erplora.com
<!-- origen: old-hub:HUB_SHELL-F01 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Acceso
Pasos:
  1. Abre el negocio sin sesión. En un dispositivo que no ofrece PIN va directo a la entrada de erplora.com para
     este negocio; en una caja que sí lo ofrece sale **Acceso** y pulsa la pestaña «Cuenta» y después «Entrar con
     tu cuenta».
  2. En erplora.com entra como siempre: email y contraseña, Google o su código de verificación.
  3. Vuelve al negocio ya dentro, en la pantalla que había pedido o en **Inicio**. Si este dispositivo pide PIN,
     el negocio ya entra en sus cajas con PIN y la persona aún no tiene uno, antes le pide elegirlo (BASE-F31).
Entra: la cuenta que comprueba erplora.com; este navegador.
Sale: la sesión de la persona en este negocio y este navegador convertido en un dispositivo de confianza del
negocio (sale en «Dispositivos», compartido mientras nadie diga lo contrario). La sesión dura un turno de 12 horas
en un dispositivo compartido, 30 días en uno personal y como mucho 1 hora si el negocio pide siempre el PIN.
Si falla: erplora.com dice por qué no entra (credenciales, verificación, «No tienes acceso a este hub»); el
negocio no guarda nada hasta que vuelve con la persona identificada.
Implicados: BASE-F13

### BASE-F30 Entrar desde el panel de erplora.com sin volver a teclear la contraseña
<!-- origen: old-hub:HUB_SHELL-F02 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Acceso
Pasos:
  1. En erplora.com, con la sesión abierta, pulsa entrar en su negocio.
  2. El negocio se abre con la persona ya dentro, en **Inicio**, sin pasar por ninguna pantalla de entrada.
Entra: el pase de un solo uso que da erplora.com.
Sale: lo mismo que BASE-F29: la sesión y este navegador como dispositivo de confianza del negocio, así que
después ofrece el pinpad, sale en «Dispositivos» y su modo se puede cambiar.
Si falla: un pase caducado o ya usado no abre nada: el negocio vuelve a pedir la entrada de erplora.com.
Implicados: BASE-F29

### BASE-F31 Elegir el PIN la primera vez que se entra en una caja
<!-- origen: old-hub:HUB_SHELL-F03 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Crea tu PIN de acceso
Pasos:
  1. Tras entrar con la cuenta (BASE-F29) en un dispositivo compartido de un negocio que pide PIN, donde otra
     persona ya entra con el suyo, y si la persona aún no tiene PIN, sale «Crea tu PIN de acceso» — «Con él
     entrarás en esta caja sin tu contraseña.».
  2. Teclea el PIN en el teclado de círculos: «Elige un PIN de {n} dígitos» (4 o 6, lo que diga el negocio).
  3. Repite: «Confirma tu PIN». Al acertar se guarda y entra donde iba.
  4. «Ahora no» lo deja para más tarde: entra igual y puede elegirlo en **Mi perfil** (BASE-F42).
Entra: la sesión recién abierta; los dígitos del PIN del negocio.
Sale: el PIN de la persona, guardado cifrado; su cara aparece en «Cambiar de usuario» al momento y en el pinpad
de **Acceso** en menos de un minuto.
Si falla: la repetición no coincide: «Los PIN no coinciden, inténtalo de nuevo» y vuelve al primer paso. Dígitos
repetidos o seguidos: «Ese PIN es demasiado fácil de adivinar: evita dígitos repetidos (1111) y secuencias
(1234).». Ya lo usa otra persona: «Ese PIN ya lo tiene otra persona activa: elige otro.». Sin conexión: «No se
pudo guardar el PIN. Vuelve a intentarlo.». Un negocio en el que nadie tiene PIN no lo pide al entrar: el primero
se elige en **Mi perfil**.
Implicados: BASE-F29, BASE-F42

### BASE-F32 Entrar con PIN
<!-- origen: old-hub:HUB_SHELL-F04 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Acceso
Pasos:
  1. En un dispositivo compartido de un negocio que pide PIN, **Acceso** abre en la pestaña «PIN»: «Introduce tu
     PIN», «…o pasa tu placa: no hace falta elegir tu nombre antes.» y «Elige tu usuario» con una cara por
     persona (iniciales y nombre; nunca su correo). Con una sola persona, ya sale elegida.
  2. Toca tu nombre: sale «PIN de {name}» y el teclado con tantos círculos como dígitos tenga el PIN del negocio.
     La flecha («Cambiar usuario») vuelve a las caras.
  3. Teclea el PIN: entra solo al último dígito, sin botón.
  4. Entras en la pantalla que habías pedido o en **Inicio**. El pie dice «ERPlora · dispositivo de confianza».
Entra: las personas del negocio con PIN, releídas cada minuto y al volver a la pantalla: quien recibe un PIN
aparece y quien se va desaparece sin recargar. Solo las ve un dispositivo compartido del negocio que las dejaría
entrar.
Sale: la sesión de esa persona en este dispositivo, por un turno (como mucho 1 hora si el negocio pide siempre el
PIN), en su idioma desde el primer momento. Funciona aunque erplora.com no responda.
Si falla: PIN erróneo: los círculos se vacían y debajo «PIN incorrecto.». Cinco PIN erróneos seguidos para una
persona, o demasiados desde la misma conexión: «Demasiados intentos fallidos.» y los minutos que tiene que esperar.
Un dispositivo en el que nunca se entró con una cuenta, o que un administrador quitó: «En este dispositivo
todavía no funciona el PIN. Entra una vez con tu cuenta aquí y a partir de entonces sí funcionará.». Sin
conexión, «No se pudo entrar. Comprueba la conexión e inténtalo de nuevo.»; si no se puede leer quién trabaja
aquí, «No se pudo cargar el pinpad. Puedes entrar con tu cuenta.».
Implicados: BASE-F31, BASE-F44

### BASE-F33 Entrar pasando la placa
<!-- origen: old-hub:HUB_SHELL-F05 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Acceso
Pasos:
  1. En la pestaña «PIN» de **Acceso** (con persona elegida o sin ella), pasa la tarjeta por el lector. No hace
     falta tocar ningún campo.
  2. La pantalla reconoce la ráfaga del lector por su velocidad (una persona tecleando nunca es una placa).
  3. Entras como el dueño de la tarjeta.
Entra: el número que lee el lector. Solo se atiende en la pestaña «PIN» de un dispositivo que ofrece el pinpad y
en **Cambiar de usuario**; en «Cuenta» o mientras se elige el PIN, no.
Sale: lo mismo que BASE-F32.
Si falla: una tarjeta que no es de nadie o cuyo dueño ya no está: «Esa placa no abre nada aquí. Entra con tu PIN
o pídeselo a un administrador.»; cuenta como un intento fallido. El pinpad sigue disponible.
Implicados: BASE-F32

### BASE-F34 Perder la sesión porque se abrió en otro dispositivo
<!-- origen: old-hub:HUB_SHELL-F06 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Acceso
Pasos:
  1. El plan del negocio cubre un número de dispositivos a la vez (el Gratis, uno) y alguien entra en otro.
  2. La sesión del dispositivo que lleva más tiempo sin entrar se cierra en ese momento: lo que tiene abierto deja
     de ponerse al día.
  3. Su siguiente pantalla es **Acceso**, que arriba dice «Sesión abierta en otro dispositivo» — «Tu plan cubre un
     dispositivo a la vez, así que al entrar en otro se cerró la sesión de este. Vuelve a entrar para usarlo aquí,
     o amplía los dispositivos de tu plan.» con «Actualizar plan».
  4. Puede volver a entrar (y cierra la del otro) o ir a ampliar el plan a erplora.com.
Entra: los dispositivos que cubre el plan, que erplora.com le pasa al negocio.
Sale: las sesiones de los dispositivos que sobran, cerradas, y el motivo guardado en cada uno para decírselo.
Si falla: sin tope en el plan no se cierra nada.
Implicados: BASE-F11

### BASE-F35 La sesión termina mientras se trabaja
<!-- origen: old-hub:HUB_SHELL-F07 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Acceso
Pasos:
  1. La sesión termina: acaba el turno (12 horas en un dispositivo compartido, 30 días en uno personal, 1 hora si
     el negocio pide siempre el PIN), un administrador quita el dispositivo o la persona deja el negocio.
  2. Lo siguiente que abre la lleva a la entrada; si la sesión se cerró porque quitaron el dispositivo o la
     persona dejó el negocio, lo que tiene abierto se entera al momento.
  3. En una caja con pinpad, **Acceso** dice arriba «Tu sesión ha terminado» — «Caducó o se cerró. Vuelve a
     entrar.» y la siguiente persona entra con su PIN. En un dispositivo sin pinpad va a la entrada de erplora.com,
     que la devuelve dentro si su sesión allí sigue abierta.
Entra: la sesión que ya no existe.
Sale: nada guardado; la venta a medias la conserva su app.
Si falla: sin red, la pantalla no da la sesión por terminada.
Implicados: BASE-F13, BASE-F47

### BASE-F36 Cerrar la sesión de una caja que nadie toca
<!-- origen: old-hub:HUB_SHELL-F08 -->
Estado: hecho
Actor: sistema
Pantalla: Acceso
Pasos:
  1. El negocio eligió en **Ajustes › General**, bajo «Volver a preguntar tras inactividad», unos minutos (1, 5,
     10, 15 o 30) y este dispositivo es compartido.
  2. Nadie toca la pantalla (ni dedo, ni tecla, ni rueda) durante esos minutos.
  3. La sesión se cierra y la caja vuelve a **Acceso**, al pinpad.
Entra: los minutos del negocio, que llegan con la propia página (no hay una lectura aparte que pueda fallar).
Sale: la sesión cerrada en el negocio. La cuenta abierta la conserva su app.
Si falla: con «Hasta cerrar sesión», en un dispositivo personal o donde no se pide PIN no se cierra nada; aunque
la pantalla se quede colgada, una sesión abierta mientras el negocio pide siempre el PIN no dura más de 1 hora.
Implicados: BASE-F44

### BASE-F37 Cambiar de usuario sin perder la venta
<!-- origen: old-hub:HUB_SHELL-F09 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Cambiar de usuario
Pasos:
  1. En una caja compartida de un negocio que pide PIN, abre la tarjeta de usuario del menú y pulsa «Cambiar de
     usuario» (no sale en ningún otro caso).
  2. Sobre la pantalla en curso se abre **Cambiar de usuario**: «La venta sigue abierta. A partir de ahora queda a
     nombre de quien entre aquí.» y «¿Quién se pone?» con una cara por persona.
  3. Toca la tuya y teclea el PIN, o pasa tu placa. La flecha («Otra persona») vuelve a las caras; «Cancelar»
     vuelve sin cambiar nada.
  4. Sale «Ahora atiende {name}» y la pantalla sigue donde estaba, cargada de nuevo para quien entró: lo que se ve
     es lo que su rol permite, y volver atrás ya no lleva a las pantallas de quien se fue. La cuenta abierta de la caja
     sigue en pantalla, con sus líneas, y lo siguiente queda a nombre de quien entró.
Entra: el nombre y el PIN (o la placa) de quien entra; la sesión de quien sale.
Sale: la sesión de quien entra; la de quien sale se cierra solo cuando la nueva está abierta. La apariencia de
quien se fue se olvida, y erplora.com no queda a nombre de nadie en una sesión de PIN.
Si falla: PIN erróneo: «PIN incorrecto.» y quien estaba dentro sigue dentro. Demasiados intentos: «Demasiados
intentos fallidos.» y los minutos que tiene que esperar. Nadie con PIN: «Aquí nadie tiene PIN todavía: se
pone en Mi perfil o en Empleados.». Sin poder leer quién trabaja aquí: «No se pudo cargar quién trabaja aquí.
Comprueba la conexión e inténtalo de nuevo.».
Implicados: BASE-F32, BASE-F33

### BASE-F38 Cerrar sesión
<!-- origen: old-hub:HUB_SHELL-F10 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: El menú de usuario
Pasos:
  1. Abre la tarjeta de usuario arriba del menú lateral (en el móvil, primero el menú con el botón de la barra).
  2. Pulsa «Cerrar sesión».
  3. En una caja con pinpad vuelve a **Acceso**, lista para la siguiente persona. En otro dispositivo, la sesión
     de erplora.com también se cierra (erplora.com pide confirmarlo).
Entra: la sesión.
Sale: la sesión cerrada en el negocio.
Si falla: si el negocio no contesta, la sesión caduca sola.
Implicados: ninguno

### BASE-F39 Decidir si este dispositivo es compartido o personal
<!-- origen: old-hub:HUB_SHELL-F11 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · General
Pasos:
  1. Desde el propio dispositivo, abre **Ajustes**; en «Este dispositivo»: «Cómo pregunta este dispositivo quién lo
     está usando. Cada dispositivo del negocio se decide por separado.».
  2. Elige «Compartido — una caja o tablet que usan varias personas» («Pide PIN al entrar y lo olvida al acabar el
     turno, así que cada venta queda atribuida a quien la hizo.») o «Personal — un dispositivo que solo usas tú»
     («La sesión se queda abierta y nunca pide PIN.»).
  3. Se guarda al momento; la marca se mueve cuando el negocio lo confirma.
  4. La entrada de este dispositivo cambia en consecuencia: pinpad en compartido, solo la cuenta en personal.
Entra: el dispositivo desde el que se pide (nunca otro).
Sale: el modo del dispositivo, con quién y cuándo lo eligió.
Si falla: quien no administra ve las opciones apagadas y «Solo un administrador puede cambiar cómo entra la gente
en este dispositivo.». Un navegador en el que nunca se entró con la cuenta: «Este navegador todavía no es un
dispositivo del negocio: entra una vez aquí con tu cuenta y podrás elegir.». Sin conexión: «No se pudo cambiar
este dispositivo. Comprueba la conexión e inténtalo de nuevo.».
Implicados: BASE-F32

### BASE-F40 Abrir un hub que todavía no está dado de alta
<!-- origen: old-hub:HUB_SHELL-F12 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Estamos preparando tu negocio
Pasos:
  1. Abre la dirección de un negocio que erplora.com aún está preparando (recién creado).
  2. Sale «Estamos preparando tu negocio» — «Tarda unos segundos. Esta página se actualiza sola.».
  3. Cuando está listo, la página se actualiza y entra como siempre.
Entra: el estado del negocio que le pasa erplora.com.
Sale: nada guardado.
Si falla: una dirección que no es de ningún negocio no existe; un negocio dado de baja dice «Este hub ya no está
disponible.».
Implicados: ninguno

### BASE-F41 Cambiar mis datos, foto, idioma y apariencia
<!-- origen: old-hub:HUB_SHELL-F21 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Mi perfil
Pasos:
  1. Abre la tarjeta de usuario del menú y pulsa «Perfil». Arriba, su cara, su nombre, «Tu identidad y tus
     preferencias personales en este negocio.» y su rol.
  2. En «Datos de la cuenta» cambia «Nombre», «Apellidos» o «Correo electrónico» («Solo para contactarte: no es el
     correo con el que entras.») y pulsa «Guardar mis datos»: «Perfil guardado».
  3. «Elegir imagen» sube una foto JPG, PNG o WebP de hasta 2 MB («Foto actualizada»); «Quitar» la borra («Foto
     quitada»).
  4. En «Preferencias», «Idioma» («Usar el idioma del negocio», «Español», «English») y «Apariencia» («Paleta de
     tema» y «Tema»: «Sistema (auto)», «Claro», «Oscuro») se guardan al elegir y se aplican al momento; «Usar la
     apariencia del negocio» deshace lo propio.
Entra: el perfil de quien tiene la sesión.
Sale: su nombre en este negocio (el que sale en las caras y en «Dispositivos»), su foto, su idioma
y su apariencia, que le siguen en cualquier dispositivo en el que entre. El correo es solo de contacto: no cambia
la cuenta de erplora.com.
Si falla: si el perfil no se pudo leer, «No se pudo cargar el perfil» — «Tus datos siguen igual. Comprueba la
conexión y vuelve a intentarlo.» con «Reintentar». Al guardar: «No se pudo guardar el perfil»; foto rechazada:
«No se pudo guardar la foto. Usa JPG, PNG o WebP de hasta 2 MB.»; preferencias: «No se pudieron guardar tus
preferencias. Comprueba la conexión e inténtalo de nuevo.».
Implicados: ninguno

### BASE-F42 Cambiar mi PIN desde Mi perfil
<!-- origen: old-hub:HUB_SHELL-F22 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Mi perfil
Pasos:
  1. En **Mi perfil**, tarjeta «PIN»: «El PIN con el que entras en la caja. Cámbialo cuando quieras — no hace
     falta que lo haga nadie más.» (sin PIN: «Todavía no tienes un PIN. Establece uno para poder entrar también
     desde la caja.»).
  2. Si ya tiene PIN, escribe «PIN actual».
  3. Escribe «PIN nuevo» y «Repite el PIN nuevo» y pulsa «Cambiar PIN» (o «Establecer PIN»): «PIN actualizado».
Entra: la sesión; los dígitos del PIN del negocio.
Sale: el PIN nuevo, guardado cifrado; las cajas lo aceptan al momento.
Si falla: longitud distinta: «El PIN debe tener {n} dígitos.»; los dos no coinciden: «Los dos PIN no
coinciden.»; fácil de adivinar: «Ese PIN es demasiado fácil de adivinar: evita dígitos repetidos (1111) y
secuencias (1234).»; ya lo usa otra persona: «Ese PIN ya lo tiene otra persona activa: elige otro.»; el actual no
es: «Ese no es tu PIN actual. Escríbelo bien para poder fijar uno nuevo.»; treinta intentos en una hora:
«Demasiados intentos de cambiar el PIN.» y los minutos que tiene que esperar.
Implicados: BASE-F31

### BASE-F43 Elegir cuántos dígitos tiene el PIN del negocio
<!-- origen: old-hub:HUB_SHELL-F100 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · General
Pasos:
  1. Con el pinpad encendido (BASE-F44), bajo «Dígitos del PIN» elige «4 dígitos» o «6 dígitos».
  2. Se guarda al momento. Debajo: «Todo el mundo teclea el mismo número de dígitos, que es lo que permite que el
     teclado entre al último en vez de pedirte confirmar. Los PIN que ya se usan siguen funcionando hasta que su
     dueño los cambie.».
  3. Desde ese momento, el pinpad, «Crea tu PIN de acceso» y **Mi perfil** piden esa longitud.
Entra: la elección.
Sale: la longitud del PIN del negocio. No toca los PIN que ya hay.
Si falla: «No se pudo cambiar. Comprueba la conexión e inténtalo de nuevo.».
Implicados: BASE-F44

### BASE-F44 Decidir si se pide PIN en la caja y cuándo se vuelve a pedir
<!-- origen: old-hub:HUB_SHELL-F99 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · General
Pasos:
  1. En **Ajustes**, bajo «Pinpad», ve «Mostrar pinpad»: «Si se muestra el pinpad y se pregunta quién está en la
     caja. Vale para todo el negocio: además, cada dispositivo decide por su cuenta, arriba.».
  2. Lo enciende o lo apaga. Debajo, la consecuencia. Encendido: «El personal elige su nombre y teclea su PIN, así
     que cada venta lleva el nombre de quien la hizo.». Apagado: «Nadie teclea un PIN. Quien abriera la caja por la
     mañana es el nombre de todas las ventas hasta que acabe el turno, las hiciera quien las hiciera: no podrás
     saber quién vendió qué ni quién hizo un descuento. El personal que solo tiene PIN y no tiene cuenta no podrá
     entrar.».
  3. Con el pinpad encendido, «Volver a preguntar tras inactividad»: 1, 5, 10, 15 o 30 min, o «Hasta cerrar
     sesión», y debajo qué pasa («Una caja que nadie toca durante {n} minutos cierra la sesión y muestra el pinpad:
     la siguiente venta lleva el nombre de la siguiente persona.»).
  4. Cada cambio se guarda al momento, sin botón, y la tarjeta enseña lo que el negocio confirma.
Entra: cómo pide el PIN el negocio.
Sale: si se pide y cuándo se vuelve a pedir, para todas las cajas del negocio. Apagarlo y volver a encenderlo
vuelve a pedirlo por turno.
Si falla: «No se pudo cambiar. Comprueba la conexión e inténtalo de nuevo.». Si no se puede leer: «No se pudo
cargar cómo pide el PIN el negocio. Comprueba la conexión e inténtalo de nuevo.». Quien no administra ve los
controles apagados y «Solo un administrador puede cambiar si se pregunta.».
Implicados: BASE-F32, BASE-F36

### BASE-F45 Ver los dispositivos en los que se ha entrado
<!-- origen: old-hub:HUB_SHELL-F101 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · General
Pasos:
  1. En **Ajustes**, bajo «Dispositivos»: «Los dispositivos en los que alguien ha entrado. Si pierdes uno, quítalo
     aquí: su sesión se cierra al momento y deja de poder entrar con PIN.».
  2. Una fila por dispositivo, el último en usarse primero: el nombre que le puso el negocio (o «Dispositivo sin
     nombre» y qué es, por ejemplo Chrome · Android), «El que estás usando» en el actual, el modo («Pide PIN» o
     «Se queda abierto»), «En uso ahora mismo» o «Se usó por última vez {when}», «Su sesión sigue abierta hasta
     {when}» y «La última vez entró {who}». Nunca su identificador.
  3. Se pone al día sola cuando alguien cambia, nombra o quita un dispositivo.
Entra: los dispositivos del negocio.
Sale: nada guardado.
Si falla: quien no administra ve «Solo un administrador puede ver y quitar los dispositivos.», sin lista. Si no
llega: «No se pudieron cargar los dispositivos. Comprueba la conexión e inténtalo de nuevo.», nunca «Todavía no ha
entrado nadie desde ningún dispositivo.», que es solo para una lista de verdad vacía.
Implicados: BASE-F46, BASE-F47, BASE-F48

### BASE-F46 Ponerle nombre a un dispositivo
<!-- origen: old-hub:HUB_SHELL-F102 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · General
Pasos:
  1. En la fila del dispositivo, pulsa «Ponerle nombre».
  2. Debajo sale un campo: «Ponle el nombre del sitio: Barra, Cocina, Portátil del despacho» (hasta 60
     caracteres).
  3. Escribe y pulsa «Guardar» (o «Dejarlo» para cerrar). La fila pasa a titularse con ese nombre.
Entra: el nombre.
Sale: el nombre del dispositivo, el único dato de la fila que decide el negocio.
Si falla: «No se pudo cambiar el nombre. Comprueba la conexión e inténtalo de nuevo.» o «Ese nombre es demasiado
largo. Ponle uno más corto y vuelve a guardar.».
Implicados: BASE-F45

### BASE-F47 Quitar un dispositivo que se ha perdido
<!-- origen: old-hub:HUB_SHELL-F103 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · General
Pasos:
  1. En la fila del dispositivo, pulsa el icono «Quitar este dispositivo».
  2. Debajo sale «¿Quitar este dispositivo?» con la consecuencia: «Su sesión se cierra al momento. Para volver a
     usarlo, alguien tiene que entrar en él con su cuenta.». Si es el que está usando: «Es el dispositivo que estás
     usando: al quitarlo se cerrará tu sesión y tendrás que volver a entrar.».
  3. Confirma con «Quitar este dispositivo» (o «Dejarlo»). La fila desaparece y su sesión se cierra al momento. Si
     era el suyo, sale del negocio.
Entra: el dispositivo.
Sale: el dispositivo olvidado y sus sesiones cerradas: se corta el dispositivo, no la persona, que puede volver a
entrar en él con su cuenta.
Si falla: «No se pudo quitar este dispositivo. Comprueba la conexión e inténtalo de nuevo.» o «Ese dispositivo ya
no está registrado aquí. Actualiza la lista.»; nunca queda como hecho lo que se rechazó.
Implicados: BASE-F35, BASE-F45

### BASE-F48 Quitar de golpe los dispositivos que nadie usa
<!-- origen: old-hub:HUB_SHELL-F104 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · General
Pasos:
  1. Si hay dispositivos que nadie ha usado en 30 días (nunca el que se tiene en la mano), sale «Quitar el
     dispositivo sin usar desde hace 30 días» o «Quitar los {n} dispositivos sin usar desde hace 30 días».
  2. Al pulsarlo, «¿Quitar {n} dispositivos que nadie usa desde hace 30 días?» (o «¿Quitar el dispositivo que nadie
     usa desde hace 30 días?») con «Dejan de aparecer aquí y, para volver a usar uno, alguien tendrá que entrar en
     él con su cuenta. Los usados en los últimos 30 días y el que estás usando se quedan.».
  3. Confirma con «Quitar».
Entra: qué dispositivos lleva 30 días sin usar nadie.
Sale: esos dispositivos olvidados, como BASE-F47.
Si falla: «No se pudieron quitar los dispositivos sin usar. Comprueba la conexión y vuelve a intentarlo.».
Implicados: BASE-F47

## Para quien lo mantiene

- Las tres consultas vivas del Inicio son de `base/queries.py`, con permiso `base.view_home` y ruta ninja en
  `base/api.py` (`GET /api/home/setup`, `/home/widgets`, `/home/bell`): `base.setup.status` (también
  herramienta del asistente, `ai=`), `base.widget.list` y `base.bell.counters`. Las reglas puras viven en
  `base/home.py` (sin ORM): las del `setup_status.rs` del hub viejo.
- Punto de extensión: cada módulo declara en su `LiveAppConfig` `setup` (`SetupStep`), `widgets`
  (`Widget`) y `bell` (`BellCounter`), dataclasses de `live.meta` comprobadas por `live.checks`
  (E009–E016). Cada consulta que nombran es un `kind="query"` de la propia app; base la ejecuta como la
  persona (`run_hook`).
- Nivel: ⛔ `legal` para `LEGAL_STEPS` (`invoice.business_identity`) y, donde la primera fila de su propia
  consulta dice que el hub presenta en producción, para `LEGAL_IN_PRODUCTION` (`verifactu.sending_route`, con
  `environment` de `verifactu.config.get`: sin vía lista en producción se rechaza toda venta; en pruebas se vende
  sin ella y sigue `functional`, gh:hub#1726); si no, `required` → `functional` y si no `recommended`. Un ⛔ (o un
  paso de `LEGAL_IN_PRODUCTION`) cuya consulta la persona no puede leer se evalúa como sistema (`system_context`) y,
  si sale ⛔ pendiente, `actionable: false`; si no es ⛔, se omite como cualquier otro paso. Un paso cuya consulta
  falla se omite y se anota en el log.
- Pasos de plataforma (solo con `base.administer_hub`): `base.apps` (orden 10; `unavailable` si no hay
  ninguna app de negocio en el catálogo) y `base.team` (orden 80; hecho con dos personas activas).
- `base/live.py`: cada consulta se re-ejecuta tras los eventos de `refresh_on` de su gancho más
  `base.hub.state_applied` (la foto del SaaS puede encender o apagar apps). Escribir en el hub B no avisa
  al A (test de dos hubs en `base/tests/test_queries_home.py`).
- Un panel con `operation` viva (está en un `live.py`) se sigue con `useLive`; si no, se pide una vez
  (`live` en `WidgetOut`). Un panel con `component` monta `apps/<app>/frontend/components/<Nombre>.vue`.
- Un panel `chart` cuyas etiquetas son días (`YYYY-MM-DD`: día civil de negocio, sin zona) los nombra con
  `Intl` en UTC, nunca con `new Date(<día>)` en la zona del navegador (`isoDay` y `formatDay` de
  `base/frontend/lib/home.ts`): una semana, por su día de la semana corto (`vie`); una serie más larga, por su
  fecha (`17 oct`); una etiqueta que no es un día se queda tal cual. Encima de las barras salen el día entero y el
  importe (`options.format`) de la barra elegida: la última hasta que se toca o enfoca otra (gh:hub#2392 del hub
  viejo; `tests/e2e/fix-hub-home-chart-iso-day-labels.spec.ts`).
- Un panel `timeline` dice cuándo pasó cada entrada con `formatMoment` de `base/frontend/lib/home.ts` (`Intl`, en
  la zona del dispositivo: el Hub aún no tiene la del negocio en el navegador, gh:hub#1212): de hoy, la hora sola;
  de ayer, la palabra de `Intl.RelativeTimeFormat` y la hora; antes, la fecha corta y la hora (con el año si es de
  otro). Un día civil `YYYY-MM-DD` dice hoy, ayer o su fecha, en UTC y sin hora; lo que no es un ISO se pinta tal
  cual y fuera de `<time>`. Cada entrada va en un `<time>` con el ISO del servidor en `datetime` y la fecha entera
  (`formatDateTime` de `@erplora/ui`) en `title`; el panel relee la hora cada minuto (solo un `timeline`, y lo
  para al desmontarse) para pasar lo de hoy a ayer a medianoche
  (`tests/e2e/fix-hub-home-timeline-raw-utc-time.spec.ts`).
- `demo` (módulo no listado) sale en el menú, en «Mis apps» y con su ejemplo en el Inicio solo con
  `SHOW_UNLISTED_MODULES` (por defecto, `DEBUG`) o en un hub de demo (`Hub.is_demo`); nunca en el de un cliente.
  Una sola regla, `base.home.shown_modules`, para `base.session.me` y los ganchos del Inicio.
- `base/spa.py` incrusta `hub-home` (`name` del registro y `plan_url` =
  `SAAS_URL/store/plans?business=<id del hub>`).
- La SPA responde toda ruta sin URL propia en Django, salvo la que nombra un fichero (`base.spa.NOT_A_FILE`: el
  último segmento lleva extensión, con barra final o sin ella, como `/robots.txt`, `/favicon.ico` o
  `/wp-login.php`): esa no es ruta de la SPA (`spa_route` en `config/urls.py`) y recibe el 404 llano de Django, sin
  la SPA y sin cookie, con sesión o sin ella y acepte lo que acepte (FIX-HUB-SPA-STATIC-PROBES-SET-CSRF-COOKIE). Antes
  recibía la SPA con 200 y `csrftoken`: la web pública perdía el «sin cookies» y un buscador leía HTML como
  `robots.txt`. Un 404 en `robots.txt` es «sin reglas» (RFC 9309), así que la web de `/` sigue indexable. Es la regla
  del punto de connect-history-api-fallback y de `{*path:nonfile}` de ASP.NET Core; ninguna ruta de la SPA lleva
  punto (sus parámetros son ids). Una navegación (sin extensión) sigue igual: con sesión, la SPA y su `csrftoken`;
  sin sesión y pidiendo HTML, el salto al login del SaaS; sin pedir HTML, la SPA; `/` con web publicada, la web
  (`base/tests/test_spa.py`, `test_public_home.py`; e2e `tests/e2e/fix-hub-spa-static-probes.spec.ts`). Como
  `/favicon.ico` es un 404, la SPA declara los iconos del hub viejo, el de la pestaña y el de la pantalla de inicio
  (`LIVE["spa"]["icons"]` de `live.spa`, estáticos de `base` en `base/static/base/icons/`; nunca por CDN).
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

- **Apps (APP-BASE-4: BASE-F14…F28).** `base/entitlement.py` aplica el derecho de uso (PLAN §20.4–§20.5): un
  módulo con `premium = False` siempre lo tiene; uno con `premium = True` necesita su id en `modules[]` de la última
  foto (`Hub.state`, `source` `plan` o `purchase`, con `valid_until` leído contra el reloj) o el de un módulo que lo
  requiere (cierre por `requires`, que solo conoce el Hub); un slug sin módulo se ignora y queda en el log; un hub de
  demo tiene todos. Lo bloqueado: 402 `app_entitlement_blocked` en toda operación de esa app
  (`LIVE["operation_database"] = base.entitlement.operation_database`, que delega en el de la tenencia), fuera de
  `base.relay.active_apps` (relay e Inicio), `off` y sin menú en `base.session.me`. Sin ningún módulo de pago en el
  despliegue (hoy) no se lee nada. Tests: `base/tests/test_entitlement.py` (dos hubs, demo, fin del derecho, 402).
- `base.app.list` (`GET /api/apps`, `base.view_home`, viva con `base.hub.state_applied`): los módulos de
  `home.shown_modules` desde su `LiveAppConfig` (nunca el catálogo del SaaS), con `right`, `state`, `path` (primera
  entrada del menú si la persona ve la app), `icon` (el de la primera entrada del menú, el que pinta el shell, como el
  lanzador y «Mis apps»: el `icon` del módulo es el de la Tienda, horneado aparte, y `HubIcon` rechaza un nombre no
  registrado, que dejaba la pantalla en blanco), `requires` (cierre) y `required_by`, y `store_url` =
  `SAAS_URL/store/modules?business=<id del hub>`. La foto se aplica como la plataforma (`/internal`): tras su COMMIT,
  `base.hub.state_apply` avisa también al canal del propio negocio (`base/tests/test_hub_state_wake.py`), que es
  donde escuchan las consultas vivas que la siguen. `base.plan.usage` (`GET /api/system/plan`, `base.administer_hub`,
  viva con la foto): `plan.max_users`/`max_devices` de la foto (0 = sin tope) frente a las `Membership` activas del
  host; los dispositivos, sin cuenta. Tests: `base/tests/test_queries_apps.py`.
- Pantallas: `base/frontend/pages/AppsPage.vue` (`/apps`, pestañas por hash `#all`/`#paid`, las del hub viejo;
  reglas en `lib/apps.ts`), `SystemPage.vue` (`/system`, hoy solo «Plan y límites»; las demás pestañas de Sistema
  llegan con su parte) y `AppBlockedPage.vue`, que monta la guarda de `lib/app-gate.ts` (`frontend/main.ts`: cada ruta
  de `apps/<id>/frontend/routes.ts` lleva `meta.app`; una app `off` en `base.session.me` monta la página por nombre
  en la misma dirección, como `NotInAppPage` del shell, y se comprueba también la primera dirección antes de montar).
  «Contratar en erplora.com» solo con `base.administer_hub` y `useSurface().isWeb`. e2e: `tests/e2e/base-apps.spec.ts`.
- Fase 1: no hay activación por negocio (`AppActivation`, `base.app.*`, 202 «Activando…», 409 `base.app_required`,
  el veto de VeriFactu): BASE-F18, F19 (su aviso), F21–F25 quedan `parcial` hasta la fase 2 (FIX-BASE-APP-TURN-OFF-VETO).

- **Acceso (APP-BASE-3: BASE-F29…F48).** Modelos de hub en `base/models.py`: `TrustedDevice` (el dispositivo:
  `token_digest` = SHA-256 del token de 256 bits de la cookie `hub_device`, httpOnly; nunca el token; `mode`
  `shared`/`personal` con quién y cuándo, `name`, `agent`, última persona y entrada, `ended_reason` `device_limit`),
  `Credential` (por `username`: `pin_hash` argon2id y `badge_digest` = HMAC-SHA256 del número con
  `AccessSettings.badge_key`), `AccessSettings` (fila única del negocio: `pin_policy` `always`/`per_shift`/`never`,
  `pin_inactivity_minutes`, `pin_length` 4/6; un valor que esta versión no entiende se lee como el de fábrica,
  `base/access.py`) y `Profile` (nombre, correo de contacto, foto, idioma, apariencia). En control, `SessionOwner`
  anota además `device_id` y `credential` (`account`, `pin`, `badge`).
- Entrar con la cuenta (BASE-F29, F30) es el canje de siempre (`/auth/callback`) más `services.trust_device` (la
  cookie `hub_device`), la duración de la sesión por dispositivo y negocio (`access.session_lifetime`: 12 h
  compartido, 30 días personal, tope de 1 h con `always`) y `_end_other_devices`, que aplica `plan.max_devices` de
  la foto (BASE-F34). El PIN y la placa son vistas de Django tras el CSRF, porque abren sesión (ninguna operación
  lo hace): `POST /auth/pin {person, pin, next}` y `POST /auth/badge {badge, next}` (`base/auth_views.py`), en este
  orden: freno por dirección (`PIN_ADDRESS_LIMIT`, 20 en 15 min), dispositivo compartido de un negocio que pregunta
  (403 `base.device_not_trusted`, `base.pin_not_offered`), freno por persona (`PIN_PERSON_LIMIT`, 5 en 5 min; la
  placa, por su número) y la credencial de una persona activa del negocio (401 `base.pin_incorrect`,
  `base.badge_unknown`; 429 `base.too_many_attempts` con `Retry-After`). Lo aceptado no cuenta y reinicia el freno
  de esa persona. La entrada deja la cookie del idioma de la persona (gh:hub#2639).
- `way_in` (sin sesión, pidiendo HTML): al Acceso (`/login`) si el dispositivo ofrece el pinpad
  (`queries.pin_door_open`), con `notice=ended` si llegó la cookie de una sesión que ya no existe, o si otra entrada
  cerró la suya (`notice=device_limit`); si no, el salto de siempre a la entrada de erplora.com, que devuelve dentro
  mientras su sesión vive (BASE-F13, `tests/e2e/helpers-login-hub-session.spec.ts`). `/auth/logout` en una caja con
  pinpad vuelve a `/login`.
- Operaciones (`base/queries.py`, `base/services.py`; rutas en `base/api.py` y `frontend/generated/operations.json`):
  `base.access.door` (sin sesión: la cookie decide; nunca da caras a quien el PIN no dejaría entrar, ni correos:
  `queries.face_name`, gh:hub#2536), `base.access.faces` (viva, `base.view_home`), `base.pin.set` (freno
  `PIN_CHANGE_LIMIT`, 30 en 1 h; 409 `base.pin_taken`, 403 `base.pin_current_wrong`), `base.device.current` y
  `base.device.mode_set`, `base.device.list|rename|remove|prune` y `base.access.settings|settings_update`
  (`base.administer_hub`), y `base.profile.get|update|preferences_set|avatar_set|avatar_remove` (la foto, en
  `avatars/` del almacén del hub, servida solo a una sesión: `MEMBERS_FOLDERS` de `base/media.py`). Eventos
  `base.pin.set`, `base.device.mode_changed|renamed|removed|pruned`, `base.access.settings_changed` y
  `base.profile.updated`; `base/live.py` sigue con ellos las caras, los dispositivos, el dial y el perfil.
- `base/spa.py` incrusta en `hub-home` `access` (`credential`, `switch_user`, `idle_minutes`) y `preferences` (la
  apariencia propia); `plan_url`, `account_url` y `report_url` solo en una sesión abierta con la cuenta
  (gh:hub#2506). En `frontend/main.ts`, el menú de usuario lleva «Perfil» y «Cambiar de usuario», y `startWayIn`
  (`base/frontend/lib/access.ts`) arma el bloqueo por inactividad con esos minutos (gh:hub#2537, #2677: no hay
  lectura aparte que pueda fallar), pinta la apariencia propia y, tras un cambio de usuario (anunciado en
  `sessionStorage`), dice «Ahora atiende {name}» y olvida la apariencia anterior. Cambiar de usuario abre la sesión
  nueva sobre la vieja y recarga la pantalla en curso (`location.replace`): nada de quien se fue queda en memoria
  (gh:hub#2538, #2539); la cuenta abierta de Ventas la recuerda su app (`useCurrentCheck`).
- Fase 1 (tablas compartidas, `docs/plans/2026-10-22-fase-2-tenencia.md` §5): `TrustedDevice`, `Credential`,
  `AccessSettings` y `Profile` son de todo el despliegue hasta la BD por hub, así que la lista de dispositivos, el
  dial y «Quitar» alcanzan a todos los negocios (como `Customer.objects.all()` en las apps); las caras y los PIN sí
  se filtran por las personas del negocio (`Membership`, en control). El e2e devuelve el dial al de fábrica al
  acabar.
- Tests: `base/tests/test_access*.py` y `test_api.py`; Vitest de `base/frontend/lib/access.test.ts`,
  `components/{PinPad,PinDoor,DeviceModeCard,PinPolicyCard,DevicesCard}.test.ts`,
  `pages/{Login,PinSetup,SwitchUser,Profile,Settings}Page.test.ts` y `frontend/main.test.ts`; e2e
  `tests/e2e/base-access.spec.ts` (dos personas, dos dispositivos, plan Gratis, una cuenta de Ventas abierta durante
  el cambio de usuario).

## Lo que NO hace, a propósito

- No inventa cifras: un panel o un paso que no se puede comprobar no sale o dice «No disponible».
- No guarda el tablero en el servidor: es de cada dispositivo, como en el hub viejo.
- No enseña nunca a un cliente los ejemplos de la app Demo.
- No tiene formulario de soporte propio: «Reportar un problema» abre el de erplora.com, que manda el aviso
  con la cuenta y el negocio; el hub no guarda nada.
- No vende ni enseña importes: el precio y la compra de una app de pago son de la Tienda de erplora.com, y en la
  app instalada ni siquiera lleva a ella.
- No pregunta a erplora.com al abrir una app: usa lo último que erplora.com le pasó del negocio.
- No guarda un PIN ni el número de una placa: solo lo que permite comprobarlos, y nunca enseña el correo de nadie
  en las caras de una caja.
- No tiene contraseña propia: la cuenta es la de erplora.com; el PIN y la placa solo abren una caja en la que ya se
  entró con una cuenta.
