# Workbook — Base (plataforma)
Prefijo: BASE
Alcance MVP: fase 1 (el Inicio del hub; el resto de la plataforma llega por partes)
Estado de la app: en construcción (2026-10-22)

> Manual de usuario y especificación de `base`, la plataforma del Hub: siempre está, no se activa ni se
> apaga. Esta primera parte describe el **Inicio**, la pantalla a la que se llega al entrar en el negocio
> (el del hub viejo: saludo, «Mis apps», la lista de lo que falta por configurar, los paneles de las apps y
> la actividad), con lo que acompaña a cualquier pantalla: la campana, «erplora.com», «Mejorar plan» y la franja que
> avisa cuando todavía no se puede facturar. También «Apps», «Plan y límites» de Sistema y las plantillas: la
> tarjeta del Inicio y Ajustes › Datos y copias (importar, exportar, deshacer y restablecer). El acceso (entrar con la
> cuenta, con PIN o con la placa, cambiar de usuario, Mi perfil y los dispositivos) está en sus propias pantallas,
> más abajo.
> Y «Archivos»: los documentos del negocio, en carpetas; y el asistente, en su panel, al final.

## Para qué sirve y para quién

El Inicio es lo primero que ve cualquier persona del negocio al entrar. De un vistazo:

- **Sus apps**, para abrir la que necesite sin buscarla en ningún menú.
- **Lo que le falta al negocio** para funcionar del todo: cada app dice qué paso necesita y la lista los
  junta, ordenados y con lo que pasa si no se hacen; el que impide facturar va el primero y en rojo.
- **Los paneles de las apps**: cifras, listas y gráficos que se mueven solos cuando algo cambia en el
  negocio, sin recargar.
- **La actividad**: las últimas ventas.
- **Empezar con una plantilla** de un negocio como el suyo y, en «Ajustes», guardar una copia de sus datos o
  cargar la de otro negocio.
- **Los datos del negocio**, en «Ajustes»: su nombre, su país, su zona horaria, su moneda y su idioma, tal como
  los tiene erplora.com, y adónde ir para cambiarlos.
- **Los archivos del negocio**, en «Archivos»: los documentos que el equipo guarda en carpetas (facturas de
  proveedores, contratos, cartas, fotos), para abrirlos, descargarlos y ordenarlos desde cualquier dispositivo.
- **El asistente**, con los destellos de la barra de arriba: se le pregunta por el negocio, escribiendo o con la voz,
  y hace lo que la persona podría hacer con sus botones, siempre después de que ella lo confirme.

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

- **«Empieza con un negocio como el tuyo»**, solo para quien administra el negocio y mientras el negocio no
  tiene nada de lo que trae una plantilla: hasta cuatro plantillas con «Usar esta», «Ver todas las
  plantillas» y «Ahora no».
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

### «erplora.com» de la barra
Arriba a la derecha, entre «Mis apps» y los destellos del asistente: una nube y «erplora.com» («Gestionar en
erplora.com» al pasar por encima). Abre este negocio en el panel de erplora.com: en una pestaña nueva en el navegador y,
en la app instalada, en el navegador del dispositivo. Solo lo tienen el propietario, el administrador y el encargado, y
solo si entraron con su cuenta: nunca en una sesión abierta con PIN o con la placa. En la app de Google Play no está.
En un móvil va dentro de «Más opciones», la primera, como «Gestionar en erplora.com».

### La campana
Arriba a la derecha, después de «Mis apps» y de los destellos del asistente; en un móvil, las dos van dentro de
«Más opciones», que lleva su número. Su número suma los avisos pendientes; al tocarla, una fila por aviso («Eventos
caídos (2)») que lleva a su pantalla. Sin nada: «Todo al día. Sin notificaciones.».

### El menú lateral
A la izquierda (en el móvil, desde el botón de la barra): la persona arriba y las entradas de la plataforma en dos
grupos, «Inicio», «Empleados», «Archivos» · «Apps», «Sistema», «API», «Ajustes». Cada una sale solo a quien puede abrir
su pantalla: «Sistema», a quien administra el negocio; «API», mientras la documentación de la API está mostrada
(BASE-F91), y aparece o se va al cambiar el interruptor, sin recargar. Un empleado ve «Inicio», «Empleados»,
«Archivos», «Apps» y «Ajustes». Abajo, el código QR y «Mejorar plan».

### «Mejorar plan»
Al pie del menú lateral, entre el código QR y la marca. Abre la página del plan de este negocio en
erplora.com, en una pestaña nueva. Solo en el navegador: en la app instalada no está.

### El menú de usuario
Se abre tocando a la persona, arriba del menú lateral. Primero «Perfil» y, en una caja compartida de un negocio
que pide PIN, «Cambiar de usuario»; después, solo si se entró con la cuenta (nunca en una sesión de PIN), «Mi
cuenta», que abre esa página en erplora.com (en una pestaña nueva; en la app instalada, en el navegador del
dispositivo), y «Reportar un problema», que abre un formulario en una ventana sin salir del hub (BASE-F108); al
final «Tema» (claro, oscuro o el del sistema) y «Cerrar sesión». Las dos salen también en la app instalada:
ninguna vende nada.

### La franja «Todavía no puedes facturar»
Encima de cualquier pantalla mientras falta un paso que impide facturar: «No se podrá emitir ningún
tique ni factura hasta que configures esto:» y cada paso con «Configurar» (en la pantalla que lo configura,
solo su nombre). En el «Resumen» del Inicio no sale (la lista dice lo mismo un poco más abajo); en
«Actividad», sí.

### Apps
Desde «Apps» en el menú lateral. Tres pestañas abajo: «Mis apps» (las apps que el negocio tiene en marcha),
«Añadir apps» (todas las apps de ERPlora) y «De pago» (las que se contratan aparte). Arriba, cuántas apps ha elegido
el negocio frente al límite de su plan: «17 de 20 apps activadas» o, sin límite, «17 apps activadas · Sin límite».
Cada pestaña, una tabla (o tarjetas) con su buscador, el embudo de filtros, el orden y «Columnas»: «App» (icono y
nombre), «Categoría» y «Estado»; en «Añadir apps» y «De pago», además «Descripción», «Precio» y «Viene con».
«Abrir» en la fila de una app que la persona puede abrir y, para quien administra, «Activar» o «Desactivar».
Encima de la tabla, cuando toca, el aviso del límite del plan o el de por qué no se ha cambiado una app.
«De pago» y «Precio» solo salen si alguna app se contrata aparte; hoy ninguna: todas van en todos los planes.

### La pantalla de una app que no se abre
En la misma dirección de la pantalla de la app, el motivo: «Suscripción necesaria» o «Esta app no está
disponible en este negocio», con «Ir a Apps» (y «Mejorar plan» para quien administra, en el
navegador).

### Sistema · Plan y límites
Desde «Sistema» en el menú lateral, la pestaña «Plan y límites»: «Los límites de tu plan» con «Dentro del
límite» o «Cerca del límite», las tarjetas «Personas» y «Dispositivos» y dónde se gestionan los planes.

### Ajustes · Negocio
La segunda pestaña de las de abajo de «Ajustes» («General», «Negocio», «Impresión» y «Datos y copias»). La
tarjeta «Tu negocio» enseña, sin campos que rellenar, «Nombre del negocio», «País», «Zona
horaria» (con la hora que es allí), «Moneda» e «Idioma del negocio», cada uno con una línea que dice para qué
sirve. Debajo, dónde se cambian y, para el propietario y el administrador, «Cambiar en erplora.com». Más abajo,
«Datos fiscales», que abre el emisor de Facturación.

### Ajustes · Impresión
La pestaña «Impresión»: una sola fila, «Impresoras y tique», que abre la app Impresión.

### Ajustes · Datos y copias
La pestaña «Datos y copias» de «Ajustes», la última, tras «General», «Negocio» e «Impresión». Arriba, un selector
con «Importar» (lo que se abre), «Exportar» y
«Restablecer»; lo elegido queda en el enlace, así que se puede compartir y Atrás sale de Ajustes.

- **Importar**: «Elige qué cargar», con «Subir desde archivo» y las plantillas en tarjetas o en lista, con
  «Buscar plantillas»; cada una con su idioma, su país, su versión, lo que trae y «Usar plantilla». Después,
  «Revisa lo que trae» y el «Informe de la importación».
- **Exportar**: el nombre y el idioma del archivo, «¿Para qué es este archivo?», las apps con sus casillas
  «App» y «Datos», y «Exportar».
- **Restablecer**: «Deshacer una importación», con una fila por importación que se puede deshacer, y
  «Restablecer el negocio», con lo que tiene cada sección.

### Sistema · Recursos
Desde «Sistema» en el menú lateral. Cinco pestañas abajo: «Recursos», «Plan y límites», «Actualizaciones», «Eventos
caídos» y «Registros» (esta, solo para quien administra el negocio); se abre «Recursos»: «Recursos en la nube» con la
pastilla «Nube», la tarjeta «Base de datos» y por qué no hay cifras de CPU, memoria ni conexiones.

### Sistema · Actualizaciones
«Qué te hemos actualizado»: la versión que corre, cuándo se publicó y que el hub se actualiza solo.

### Sistema · Eventos caídos
Una tarjeta por aviso entre apps que agotó sus reintentos, con «Reenviar» y «Descartar»; arriba, «Reenviar todos».

### Sistema · Registros
«Registro de eventos»: la tabla «Hora», «Nivel» y «Evento» (en el móvil, una tarjeta por suceso), con «Buscar
evento…» y el filtro de nivel.

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
Lo que se abre con «Ajustes» en el menú lateral: la primera pestaña de abajo, «General», con «Este dispositivo»,
«Pinpad», para quien administra «Dispositivos» y, al final, «Documentación de la API».

### Estamos preparando tu negocio
La página que sale en la dirección de un negocio que erplora.com aún está preparando; se actualiza sola.

### Archivos
Desde «Archivos» en el menú lateral; la ve todo el equipo. A la izquierda, «Carpetas»: el árbol de carpetas del
negocio, que empieza en «Archivos» (lo de arriba del todo), con la carpeta abierta resaltada; en una pantalla
estrecha, el árbol se pliega en el selector «Carpetas». A la derecha, «Buscar archivos…», «Lista» y «Cuadrícula» y,
para quien administra el negocio, «Nueva carpeta» y «Subir archivo». Debajo, la ruta de la carpeta abierta, con ⋮ al
lado para renombrar, mover o eliminar esa carpeta; «Espacio», con lo usado y el límite del plan («{used} de {limit}»)
o «{used} usados · Sin límite»; y lo que hay en la carpeta: primero las carpetas y luego los archivos, cada uno con su
icono, su nombre, su tamaño (en la lista, también cuándo cambió) y su ⋮: «Abrir», «Descargar», «Renombrar», «Mover a…»
y «Eliminar». En la lista, cada nombre ocupa una línea: lo que no cabe se corta con «…» y la extensión se ve
siempre entera; en el móvil, el tamaño y la fecha van debajo del nombre, en gris. Pulsar un archivo lo abre en el visor, con su nombre, «Descargar» y «Cerrar» («Ampliar» y «Reducir» en
imágenes y PDF).

### Empleados · Personal
Lo que se abre con «Empleados» en el menú lateral: la primera pestaña de abajo, «Personal», con las plazas del plan,
«Invitar en erplora.com» para quien administra, «Las personas se invitan, se les cambia el rol y se quitan en
erplora.com, en «Miembros» del negocio.» y la tabla de personas (en el móvil, una tarjeta por persona). Las otras
pestañas: «Roles» y, solo para quien administra, «API keys» y «Aprobaciones»; cada una en la dirección, así que
«Atrás» sale de Empleados.

### Empleados · Roles
Los cuatro roles de erplora.com, con de dónde vienen, cuántas personas tienen y cuántos permisos dan.

### Empleados · API keys
Las llaves con las que otro sistema llama a la API del negocio: «Nueva API key», la tabla de llaves y, al pie,
«Documentación de la API».

### Empleados · Aprobaciones
El registro de lo que se aprobó con el PIN de un responsable, solo de lectura.

### Ficha de una persona
Desde una fila de **Empleados › Personal**, para quien administra, con el botón de volver: «Sus datos» (con «Abrir
en erplora.com»), «PIN» y «Placa».

### Hace falta una aprobación
Sobre la pantalla en la que se intentó la acción: qué se aprueba, «¿Quién lo aprueba?» con las caras y el teclado
(entero y sin desplazar en el móvil, la tableta y el escritorio), y «Cancelar».

### Documentación de la API
Con el botón de volver: cómo se llama a la API, «Descargar el fichero OpenAPI» y una sección por app con sus llamadas.

### Asistente
El panel que se abre con los destellos «Asistente» de la barra de arriba (en un móvil, dentro de «Más opciones»), a la
derecha. En una tableta o un ordenador se queda al lado de la pantalla y la empuja, así que se sigue trabajando con él
abierto; en un móvil la tapa, sobre un velo oscuro. Arriba, «Asistente», «Nueva conversación» cuando ya hay una y la ×
«Cerrar». En medio, la conversación: vacía, los destellos, la frase de bienvenida y los atajos de la puesta en marcha;
luego, los mensajes, cada respuesta con sus botones «Ir a …», sus avisos y los recibos de lo que se hizo. Abajo, los
avisos del pie (sin conexión, los mensajes que quedan este mes, un plan sin asistente) y el cuadro «Escribe un
mensaje…» con «Adjuntar archivo», «Dictar por voz» y «Enviar».

### Tarjeta de confirmación del asistente
Sale encima de todo, también con el panel cerrado, cuando el asistente quiere cambiar algo: «¿Ejecutar esta acción?»,
qué va a hacer, en qué app y con qué datos, y «Ejecutar» y «Cancelar» («Cancelar todo» cuando detrás esperan más). En
una acción peligrosa, cada dato en su línea y un cuadro para escribir lo que pide antes de «Ejecutar».

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | Baldosas grises en «Mis apps» («Cargando tus apps…» para el lector de pantalla), la lista en gris, «Cargando widgets…» en el tablero, la cifra de cada panel en gris y «Cargando…» en «Actividad»; «Cargando…» en el pinpad, «Cargando tu perfil…» y «Cargando los dispositivos…». |
| Vacío | «Aquí aparecerán tus apps. Añade las que necesite tu negocio.»; sin pasos, la lista no sale; «Panel vacío. Pulsa ⋮ para añadir widgets.»; un panel sin datos, «Sin datos»; la campana, «Todo al día. Sin notificaciones.»; «Todavía no ha entrado nadie desde ningún dispositivo.»; en «Cambiar de usuario», «Aquí nadie tiene PIN todavía: se pone en Mi perfil o en Empleados.». |
| Error | Cada zona falla por su cuenta: «No se han podido cargar tus apps. Recarga la página; si sigue fallando, vuelve a iniciar sesión.», «No se ha podido cargar lo que te falta por configurar» con «Reintentar», «No se han podido cargar los paneles» con «Reintentar», un panel con «No disponible» (nunca la cifra de antes), «No se han podido cargar las últimas ventas» con «Reintentar» y, en la campana, «No se han podido comprobar las notificaciones. Aparecerán cuando vuelva la conexión.». En el acceso: «No se pudo cargar el pinpad. Puedes entrar con tu cuenta.», «No se pudo cargar el perfil» con «Reintentar», «No se pudo cargar este dispositivo. Comprueba la conexión e inténtalo de nuevo.», «No se pudo cargar cómo pide el PIN el negocio. Comprueba la conexión e inténtalo de nuevo.» y «No se pudieron cargar los dispositivos. Comprueba la conexión e inténtalo de nuevo.». |
| Sin permiso | Un paso que la persona no puede hacer: sin botón y «Esto lo tiene que configurar un administrador.». Un panel o un contador que no puede ver, no sale. En Ajustes, quien no administra ve «Este dispositivo» y «Pinpad» con los controles apagados («Solo un administrador puede cambiar cómo entra la gente en este dispositivo.», «Solo un administrador puede cambiar si se pregunta.») y, en lugar de la lista, «Solo un administrador puede ver y quitar los dispositivos.». |

En la pantalla Ajustes · Negocio:

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando los datos del negocio…». |
| Vacío | Una demo no tiene nombre ni país: esas filas dicen «—», y debajo, «Esta demo no tiene un negocio en erplora.com: sus datos no se cambian.». |
| Error | «No se pudieron cargar los datos del negocio» con «Nada ha cambiado. Comprueba la conexión y vuelve a intentarlo.» y «Reintentar»; nunca la tarjeta en blanco. |
| Sin permiso | Quien no administra el negocio lo ve igual, sin «Cambiar en erplora.com» y con «Solo el propietario o un administrador los cambian, en erplora.com.»; «Datos fiscales» no le sale a quien no puede escribir el emisor. |

En el panel del asistente:

| Estado | Qué ve la persona |
|---|---|
| Cargando | Tres puntos que se mueven en la burbuja del asistente hasta que llega el primer texto («El asistente está escribiendo» para el lector de pantalla), y «Transcribiendo…» mientras se pasa a texto lo dictado. |
| Vacío | Los destellos, «Pregúntame por tus ventas, tu inventario o cualquier cosa de tu negocio.» (abierto desde la puesta en marcha, «Revisa la configuración de tu negocio. Elige una opción o escribe tu duda.») y los atajos. Una respuesta que acaba sin decir nada: «(sin respuesta)». |
| Error | En la burbuja, con su salida: «No se pudo contactar con el asistente. Comprueba la conexión y vuelve a intentarlo.», «El asistente no está disponible ahora mismo. Vuelve a intentarlo en unos minutos.» o «La respuesta se cortó.», con «Reintentar»; «Esta conversación es demasiado larga: empieza una nueva.» con «Nueva conversación»; «Tu sesión ha terminado. Vuelve a entrar para seguir hablando.» con «Volver a entrar». Sin Internet, en el pie, «Sin conexión: puedes escribir y enviar cuando vuelva.». |
| Sin permiso | Lo que la persona no puede hacer con sus botones, el asistente tampoco: no se le ofrece y, si lo intenta, el recibo dice «No se hizo, sin permiso: …». Con los mensajes del mes agotados, quien no administra ve «Pídele a quien administra el negocio que mejore el plan.» en lugar de «Mejorar plan». |

En la pantalla Ajustes · Datos y copias:

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando plantillas…»; en «Exportar» y «Restablecer», las filas en gris. |
| Vacío | «Todavía no hay plantillas para tu negocio.», «Ninguna plantilla coincide con tu búsqueda.», «Este negocio no tiene ninguna app encendida que exportar.» y «No hay nada que restablecer: ninguna sección tiene datos.». |
| Error | «No se han podido cargar las plantillas ahora mismo. Puedes importar un archivo igualmente.» con «Reintentar»; «No se han podido cargar las apps de este negocio.» y «No se ha podido calcular lo que tiene cada sección.», con «Reintentar». |
| Sin permiso | «Solo un administrador puede ver e importar plantillas.», «Solo un administrador puede exportar el negocio.» y «Solo un administrador puede deshacer importaciones o restablecer el negocio.»; la tarjeta de plantillas del Inicio no sale. |

En la pantalla Archivos:

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando archivos…»; en el visor, «Abriendo el archivo…». |
| Vacío | «Sin archivos» y, a quien administra el negocio, «Sube un archivo o arrástralo aquí.»; una búsqueda sin resultados, «Ningún archivo de esta carpeta coincide con «{search}».». |
| Error | «No se pudieron cargar los archivos» con el motivo y «Reintentar», nunca «Sin archivos»; en el visor, «No se pudo abrir el archivo» con «No llegó el contenido del archivo. Revisa la conexión e inténtalo de nuevo.». |
| Sin permiso | Quien no administra el negocio ve, abre y descarga, sin «Nueva carpeta», «Subir archivo», «Renombrar», «Mover a…» ni «Eliminar». |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| BASE-F01 | Ver lo que le falta por configurar al negocio | hecho |
| BASE-F02 | Ver el negocio de un vistazo al entrar | parcial |
| BASE-F03 | Ir a configurar desde «Termina de configurar tu negocio» | hecho |
| BASE-F04 | Ver qué pasos de la lista tiene que configurar un administrador | hecho |
| BASE-F05 | Abrir una app desde «Mis apps» | hecho |
| BASE-F06 | Ver los paneles de las apps en Inicio | hecho |
| BASE-F07 | Personalizar el tablero de paneles | hecho |
| BASE-F08 | Mantener los paneles al día sin recargar | hecho |
| BASE-F09 | Consultar la actividad reciente | hecho |
| BASE-F10 | Ver en la campana los avisos entre apps que no se entregaron | hecho |
| BASE-F11 | Ir a erplora.com a gestionar o mejorar el plan | parcial |
| BASE-F12 | Pedirle al asistente que repase la configuración | hecho |
| BASE-F13 | Perder el acceso al cambiar de rol o al salir del negocio | hecho |
| BASE-F14 | Ver las apps del negocio | hecho |
| BASE-F15 | Abrir una app desde Apps | hecho |
| BASE-F16 | Buscar una app en el catálogo | hecho |
| BASE-F17 | Saber cuánto cuesta una app antes de tenerla | hecho |
| BASE-F18 | Instalar una app | hecho |
| BASE-F19 | Saber qué más viene con una app | hecho |
| BASE-F20 | Intentar usar una app que necesita suscripción | hecho |
| BASE-F21 | Ver por qué no se ha podido activar una app y reintentarlo | parcial |
| BASE-F22 | Seguir la activación de una app mientras se navega | parcial |
| BASE-F23 | Desactivar una app | hecho |
| BASE-F24 | Activar una app | hecho |
| BASE-F25 | Ver que una app se niega a desactivarse | hecho |
| BASE-F26 | Entender por qué una app no se abre | hecho |
| BASE-F27 | Ver una app de pago bloqueada | hecho |
| BASE-F28 | Ver cuánto de los límites del plan se está usando | hecho |
| BASE-F29 | Elegir una plantilla del catálogo para importar | hecho |
| BASE-F30 | Subir un fichero para importar | hecho |
| BASE-F31 | Revisar y cargar lo que trae el fichero | hecho |
| BASE-F32 | Leer el informe de la importación | hecho |
| BASE-F33 | Volver al informe de una importación que no entró entera y reintentar | hecho |
| BASE-F34 | Deshacer una importación | hecho |
| BASE-F35 | Exportar una copia de seguridad o una plantilla | hecho |
| BASE-F36 | Elegir qué apps, datos y tablas viajan en la exportación | hecho |
| BASE-F37 | Restablecer el negocio por secciones | parcial |
| BASE-F38 | Ver Inicio al día después de importar una plantilla | hecho |
| BASE-F39 | Abrir Sistema y moverse por sus pestañas | hecho |
| BASE-F40 | Ver cuánto está usando el hub | parcial |
| BASE-F41 | Saber qué versión corre y qué se le ha actualizado | parcial |
| BASE-F42 | Ver el registro de sucesos del sistema | hecho |
| BASE-F43 | Ver los eventos caídos | hecho |
| BASE-F44 | Reenviar un evento caído | hecho |
| BASE-F45 | Reenviar todos los eventos caídos | hecho |
| BASE-F46 | Descartar un evento caído | hecho |
| BASE-F47 | Informar de un error de la pantalla sin que nadie lo pida | hecho |
| BASE-F48 | Abrir Ajustes y moverse por sus pestañas | hecho |
| BASE-F49 | Ver el país del negocio | hecho |
| BASE-F50 | Ver la moneda del negocio | parcial |
| BASE-F51 | Cambiar el idioma del negocio en erplora.com | hecho |
| BASE-F52 | Entrar con la cuenta de erplora.com | hecho |
| BASE-F53 | Entrar desde el panel de erplora.com sin volver a teclear la contraseña | hecho |
| BASE-F54 | Elegir el PIN la primera vez que se entra en una caja | hecho |
| BASE-F55 | Entrar con PIN | hecho |
| BASE-F56 | Entrar pasando la placa | hecho |
| BASE-F57 | Perder la sesión porque se abrió en otro dispositivo | hecho |
| BASE-F58 | La sesión termina mientras se trabaja | hecho |
| BASE-F59 | Cerrar la sesión de una caja que nadie toca | hecho |
| BASE-F60 | Cambiar de usuario sin perder la venta | hecho |
| BASE-F61 | Cerrar sesión | hecho |
| BASE-F62 | Decidir si este dispositivo es compartido o personal | hecho |
| BASE-F63 | Abrir un hub que todavía no está dado de alta | hecho |
| BASE-F64 | Cambiar mis datos, foto, idioma y apariencia | hecho |
| BASE-F65 | Cambiar mi PIN desde Mi perfil | hecho |
| BASE-F66 | Elegir cuántos dígitos tiene el PIN del negocio | hecho |
| BASE-F67 | Decidir si se pide PIN en la caja y cuándo se vuelve a pedir | hecho |
| BASE-F68 | Ver los dispositivos en los que se ha entrado | hecho |
| BASE-F69 | Ponerle nombre a un dispositivo | hecho |
| BASE-F70 | Quitar un dispositivo que se ha perdido | hecho |
| BASE-F71 | Quitar de golpe los dispositivos que nadie usa | hecho |
| BASE-F72 | Ver los archivos del negocio | hecho |
| BASE-F73 | Subir archivos y crear carpetas | hecho |
| BASE-F74 | Previsualizar y descargar un archivo | parcial |
| BASE-F75 | Mover y renombrar un archivo o una carpeta | hecho |
| BASE-F76 | Borrar un archivo o una carpeta | hecho |
| BASE-F77 | Llegar al tope de personas del plan | hecho |
| BASE-F78 | Retirar el PIN a una persona | hecho |
| BASE-F79 | Dar de alta o retirar la placa de una persona | hecho |
| BASE-F80 | Reincorporar a una persona que salió del negocio | hecho |
| BASE-F81 | Entender cómo entra cada persona | hecho |
| BASE-F82 | Ver los roles y encender los que trae una app | parcial |
| BASE-F83 | Asignar un rol a una persona | hecho |
| BASE-F84 | Aprobar con el PIN de un responsable | hecho |
| BASE-F85 | Consultar quién aprobó qué | hecho |
| BASE-F86 | Crear una llave de API y copiar su token | parcial |
| BASE-F87 | Rotar una llave de API | parcial |
| BASE-F88 | Revocar una llave de API | parcial |
| BASE-F89 | Ver las llaves de API y qué puede cada una | parcial |
| BASE-F90 | Consultar la documentación de la API | hecho |
| BASE-F91 | Mostrar u ocultar la documentación de la API | hecho |
| BASE-F92 | Abrir y cerrar el panel del asistente | hecho |
| BASE-F93 | Preguntar al asistente y leer cómo escribe | hecho |
| BASE-F94 | Adjuntar un archivo o dictar por voz | hecho |
| BASE-F95 | Leer la respuesta: texto, listas, tablas y enlaces | hecho |
| BASE-F96 | Ir a una pantalla desde una respuesta | hecho |
| BASE-F97 | Confirmar una acción antes de que se ejecute | hecho |
| BASE-F98 | Acciones peligrosas: escribir para confirmar, o no desde el chat | hecho |
| BASE-F99 | Comprobar lo que dice el asistente contra lo que de verdad hizo | hecho |
| BASE-F100 | Lo que el asistente puede hacer según quién pregunta: permisos y PIN de un responsable | hecho |
| BASE-F101 | Pedirle varias cosas seguidas | hecho |
| BASE-F102 | La conversación: qué se guarda, dónde y cuándo se borra | hecho |
| BASE-F103 | El asistente en la puesta en marcha | hecho |
| BASE-F104 | Ver el plan del asistente, el límite de uso y ampliarlo | hecho |
| BASE-F105 | Informar de una respuesta mala | hecho |
| BASE-F106 | El asistente sin conexión, con el servicio caído o sin plan | hecho |
| BASE-F107 | Pasar la QA maestra del Hub | hecho |
| BASE-F108 | Reportar un problema a soporte | hecho |

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
Estado: parcial — sin la fila de salud del hub (la impresora y WhatsApp con «Ver sistema»)
Actor: propietario, administrador, responsable, empleado
Pantalla: Inicio · Resumen
Pasos:
  1. Tras entrar se abre el Inicio (también desde «Inicio» en el menú lateral).
  2. Arriba, el nombre del negocio (el de erplora.com) y «Hoy» con la fecha larga en el idioma de la
     aplicación; mientras el negocio no tiene nombre, «Buenos días», «Buenas tardes» o «Buenas noches».
  3. Debajo, en este orden: «Empieza con un negocio como el tuyo» (solo mientras el negocio está vacío y
     para quien lo administra, BASE-F38), «Mis apps», «Termina de configurar tu negocio» y el tablero de
     paneles.
  4. Abajo, dos pestañas: «Resumen» (lo anterior) y «Actividad».
Entra: el nombre del negocio y la fecha del dispositivo.
Sale: nada guardado.
Si falla: una zona que no carga no tumba las demás; cada una dice lo suyo. En el móvil las zonas se
apilan y «Mis apps» se pliega.
Implicados: ninguno

### BASE-F03 Ir a configurar desde «Termina de configurar tu negocio»
<!-- origen: old-hub:HUB_SHELL-F38 -->
Estado: hecho
Actor: propietario, administrador, responsable
Pantalla: Inicio · Resumen
Pasos:
  1. En «Termina de configurar tu negocio», un paso pendiente que la persona puede hacer lleva
     «Configurar».
  2. Pulsa «Configurar»: se abre la pantalla de la app que completa ese paso.
  3. Al volver al Inicio, la lista ya cuenta el paso como hecho si se completó.
  4. Mientras el negocio está vacío, quien lo administra empieza más arriba, en «Empieza con un negocio como el
     tuyo» (BASE-F38): «Ver todas las plantillas» abre «Datos y copias», donde se carga una plantilla o una copia.
Entra: la pantalla que cada paso declara.
Sale: nada desde aquí.
Si falla: mientras esa pantalla no existe en el hub, el paso sale sin «Configurar» (un botón que lleva a
«no encontrado» es peor que ninguno).
Implicados: BASE-F38

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
<!-- origen: old-hub:HUB_SHELL-F32 old-hub:HUB_APP-F28 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Inicio · Resumen · la barra de arriba de cualquier pantalla
Pasos:
  1. En «Mis apps», una baldosa por app que esta persona puede abrir, con su icono y su nombre (si no
     cabe, el nombre entero sale al pasar por encima).
  2. Las más abiertas en este navegador van primero.
  3. Toca una baldosa: se abre la app. Una app que se está encendiendo dice «Activando…» y no abre nada.
  4. En el móvil, con seis apps o más, se ven las cuatro primeras y «Ver todas las apps», que enseña el
     resto. «Añadir apps», la última, lleva a Apps.
  5. Para salir de una app, toca «Mis apps» en la barra: la pantalla principal de una app no tiene
     «Atrás». La hoja empieza por «Inicio», que vuelve al Inicio, y sigue con las apps; tocar una la abre.
     «Inicio» está ahí aunque la lista aún cargue, esté vacía o no se haya podido leer.
  6. En la aplicación de Android, el botón atrás del móvil cierra primero lo que haya abierto encima (una
     ventana, una hoja o el menú); una ventana que no se puede cerrar así se queda. Sin nada abierto, en una
     ficha o un alta hace lo mismo que «Atrás»; en la pantalla principal de una app vuelve al Inicio,
     también si se llegó a ella por un enlace; y en el Inicio deja la aplicación en segundo plano.
Entra: las apps del menú de la persona (las mismas del botón «Mis apps» de la barra).
Sale: cuántas veces se abre cada app en este navegador (solo para ordenar).
Si falla: mientras carga, baldosas grises y «Cargando tus apps…» para el lector de pantalla. Sin apps:
«Aquí aparecerán tus apps. Añade las que necesite tu negocio.». Si no se pudo leer la lista: «No se han
podido cargar tus apps. Recarga la página; si sigue fallando, vuelve a iniciar sesión.», nunca que no
hay apps. En una aplicación de Android antigua, que aún no sabe quedarse en segundo plano, el botón atrás
vuelve a ser el del sistema.
Implicados: ninguno

### BASE-F06 Ver los paneles de las apps en Inicio
<!-- origen: old-hub:HUB_SHELL-F33 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Inicio · Resumen
Pasos:
  1. Bajo la lista está el tablero, con sus paneles desde que se abre el Inicio («Cargando widgets…» solo mientras
     no se sabe cuáles le tocan).
  2. Cada panel es una tarjeta con su título e icono: una cifra (con debajo lo que cuenta, si su app lo dice),
     una lista con barras, una cronología, un gráfico o un trozo de la pantalla de su app, con sus textos en el
     idioma de quien mira. En una lista con barras, cada barra mide lo grande que es su cifra frente a la mayor
     de la lista, sea del signo que sea; una cifra negativa, como un descuadre de caja en el que faltó dinero o
     un producto con existencias por debajo de cero, sale en rojo y con su signo (-0,40 €), y las demás
     conservan el color del panel o, si su app da un color a cada fila, el de la suya. El rojo de una cifra
     negativa gana siempre al color de su fila.
  3. En un gráfico de días, cada barra lleva debajo su día de la semana (o su fecha, si abarca más de una
     semana) y encima salen el día y su importe: los de la última barra hasta que tocas otra. Un día por debajo
     de cero tiene su barra tan alta como su cifra, en rojo; los demás conservan su color.
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
una cifra vieja o inventada. Una fila de una lista con barras (o un día de un gráfico) que no tiene cifra,
como una sesión de caja cerrada sin recuento, sale con una raya (—) y sin barra, nunca como un cero; un cero
de verdad sí sale como cero (0,00 €). Si no se puede leer el tablero: «No se han podido cargar los paneles»
con «Reintentar».
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
Estado: hecho
Actor: propietario, administrador
Pantalla: La campana
Pasos:
  1. Un aviso entre apps (por ejemplo, «venta cobrada» hacia Facturación) agotó sus reintentos.
  2. La campana de un administrador sube en el momento, sin esperar ni recargar, y al abrirla enseña
     «Eventos caídos» con cuántos hay.
  3. Al tocar la fila se abre «Sistema» en «Eventos caídos», donde se reenvían o se descartan (BASE-F43).
  4. Cuando no queda ninguno, la fila desaparece.
Entra: cuántos avisos de este negocio quedaron sin entregar, solo para quien administra el negocio.
Sale: nada.
Si falla: un empleado o un responsable no ve la fila. Si no se puede preguntar, la campana se queda con
lo último que supo; si nunca lo supo: «No se han podido comprobar las notificaciones. Aparecerán cuando
vuelva la conexión.».
Implicados: ninguno

### BASE-F11 Ir a erplora.com a gestionar o mejorar el plan
<!-- origen: old-hub:HUB_SHELL-F129 -->
Estado: parcial — sin el pase de un solo uso: si el navegador no tiene abierta la sesión de erplora.com, se entra con la cuenta al llegar
Actor: propietario, administrador, responsable, empleado
Pantalla: Menú lateral, barra de arriba
Pasos:
  1. Al pie del menú lateral, bajo el código QR y alineado con él, está «Mejorar plan». Lo ve cualquier
     perfil; lo que se puede hacer al llegar lo decide erplora.com según quién entre. Con el menú plegado a
     sus iconos (escritorio), queda solo su icono, que dice «Mejorar plan» al pasar por encima. Solo en el
     navegador: en la app instalada no está.
  2. Lo pulsa: se abre en una pestaña nueva la página del plan de este negocio en erplora.com.
  3. El propietario, el administrador o el encargado que entró con su cuenta tiene además, arriba a la derecha,
     «erplora.com», con una nube (en un móvil, «Gestionar en erplora.com», la primera de «Más opciones»).
  4. Lo pulsa: se abre este negocio en el panel de erplora.com, en una pestaña nueva; en la app instalada, en el
     navegador del dispositivo. El Hub se queda donde estaba.
Entra: el negocio en el que está.
Sale: nada guardado en el hub.
Si falla: si el hub no sabe a qué negocio pertenece, ninguno de los dos sale (nunca un botón que no hace nada). Si la
app instalada no consigue abrir el navegador, lo dice: «No se ha podido abrir esa página. Inténtalo de nuevo.». Un
empleado, una sesión abierta con PIN o con la placa y la app de Google Play no tienen «erplora.com».
Implicados: ninguno

### BASE-F12 Pedirle al asistente que repase la configuración
<!-- origen: old-hub:HUB_SHELL-F30 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Inicio · Resumen
Pasos:
  1. En «Termina de configurar tu negocio», pulsa «Pedírselo al asistente» (o pregúntaselo desde su panel).
  2. El asistente lee la misma lista del Inicio, con lo que esa persona puede ver, y le dice qué falta y
     dónde se hace; cada paso sigue teniendo su «Configurar» en la lista.
Entra: la lista de lo que falta, con los permisos de quien pregunta.
Sale: nada guardado.
Si falla: sin asistente, los pasos siguen llevando a su pantalla desde la lista.
Implicados: BASE-F103

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
     «Mejorar plan» (BASE-F20).
  3. «De pago» reúne solo las apps que se contratan aparte: una gratis nunca sale ahí. Si ninguna se vende
     aparte (hoy, todas van en todos los planes), no hay «De pago» ni «Precio», y un enlace a «De pago» abre
     «Añadir apps».
Entra: si cada app se contrata aparte y lo que el negocio tiene contratado en erplora.com.
Sale: nada guardado. El hub no cobra ni enseña importes: el precio y la compra son de erplora.com.
Si falla: sin la lista, como en «Mis apps» (BASE-F14).
Implicados: APPS-F01, APPS-F07

### BASE-F18 Instalar una app
<!-- origen: old-hub:HUB_SHELL-F109 -->
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
  1. Las apps que el negocio usa ya están en «Mis apps» y en el menú; una de pago aparece sola en los dos, sin
     recargar, en cuanto se contrata en erplora.com (BASE-F20).
  2. En «Añadir apps», quien administra busca una app que el negocio no usa, «Desactivada», y pulsa «Activar». Si
     necesita otras apps que están desactivadas, antes le pregunta nombrándolas (BASE-F19).
  3. La app pasa a «Instalada» al momento y sale en «Mis apps» y, sin recargar, en el menú de todos los
     dispositivos del negocio. El contador de arriba suma una: de «16 de 20 apps activadas» a «17 de 20 apps
     activadas».
Entra: la app elegida, las que necesita y lo que el negocio tiene contratado en erplora.com.
Sale: la app en marcha en este negocio, elegida por él: cuenta para el límite de apps de su plan.
Si falla: con el límite del plan alcanzado no se activa nada y sale «El límite de apps de tu plan»: «Has llegado al
límite de 20 apps de tu plan. Mejora el plan o desactiva una.», con «Mejorar plan» para quien administra en el
navegador (en la app instalada no sale). Una app de pago sin contratar no ofrece «Activar» (BASE-F20). Cualquier
otro fallo sale en un aviso con el nombre de la app y el motivo, que se queda hasta cerrarlo.
Implicados: APPS-F07

### BASE-F19 Saber qué más viene con una app
<!-- origen: old-hub:HUB_SHELL-F110 -->
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
  1. En «Añadir apps», la columna «Viene con» nombra las apps que necesita cada una (por ejemplo, «Ventas / TPV»
     viene con «Clientes» e «Impuestos»): quien tiene una tiene también las que trae.
  2. Una app de pago que el negocio tiene porque la necesita otra que ha contratado dice en «Precio» «Incluida
     con» y el nombre de esa otra.
  3. Al pulsar «Activar» en una app que necesita otras que están desactivadas, antes pregunta y las nombra:
     «¿Activar Reservas?» — «Reservas necesita Mesas: se activa con ella.».
  4. Al confirmar con «Activar», el aviso nombra también las que se activaron con ella: «Reservas está activada.
     También se ha activado: Mesas.». Las que llegan así no cuentan para el límite de apps del plan: solo cuenta
     la que se eligió.
Entra: lo que necesita cada app y cuáles están desactivadas.
Sale: nada guardado al preguntar; al confirmar, la app y las que necesita en marcha (BASE-F18).
Si falla: si una app de pago trae otra de pago que no se ha contratado, las dos se contratan juntas: hasta
entonces, «Necesita suscripción». Con «Cancelar», no cambia nada.
Implicados: ninguno

### BASE-F20 Intentar usar una app que necesita suscripción
<!-- origen: old-hub:HUB_SHELL-F111 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Apps
Pasos:
  1. Una app de pago que el negocio no tiene contratada sale en «Añadir apps» y en «De pago» con «Necesita
     suscripción», y no está en «Mis apps» ni en el menú.
  2. Quien administra el negocio, en el navegador, ve a su lado «Mejorar plan», que abre la Tienda de
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
Estado: parcial — hoy activar una app es inmediato y no se queda a medias, porque sus datos ya están preparados en cada negocio; prepararlos al activarla, el aviso de que no se ha podido y su «Reintentar» llegan en la fase 2, cuando cada negocio tenga sus datos aparte
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
Estado: parcial — hoy activar una app es inmediato y sale en el menú de todos los dispositivos del negocio sin recargar; falta el paso «Activando…» mientras se preparan sus datos, que llega en la fase 2, cuando cada negocio tenga sus datos aparte
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
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
  1. En «Mis apps», quien administra pulsa «Desactivar» en la fila de una app.
  2. Le pregunta siempre, con el nombre de la app: «¿Desactivar Reservas?» — «Sale del menú de todos en este
     negocio. No se borra nada: al volver a activarla, tiene sus datos.». Si con ella se van otras que llegaron solo
     por ella, las nombra: «Mesas se desactiva con ella: solo la necesitaba Reservas.».
  3. Confirma con «Desactivar»: «Reservas está desactivada. También se ha desactivado: Mesas.». Las dos salen de
     «Mis apps» y, sin recargar, del menú de todos los dispositivos del negocio; sus pantallas dicen que la app no
     está disponible (BASE-F26) y el contador de arriba resta una.
  4. En «Añadir apps» siguen, con su icono, su nombre y «Desactivada»: desde ahí se vuelven a activar (BASE-F24).
Entra: las apps del negocio, lo que necesita cada una y cuáles eligió el negocio.
Sale: la app apagada en este negocio, y las que llegaron solo con ella, con sus datos intactos.
Si falla: si otra app en marcha la necesita, o la propia app se niega, no cambia nada (BASE-F25). Con «Cancelar»,
tampoco.
Implicados: VERIFACTU-F32

### BASE-F24 Activar una app
<!-- origen: old-hub:HUB_SHELL-F123 -->
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
  1. En «Añadir apps», quien administra pulsa «Activar» en una app que apagó, que sale «Desactivada».
  2. Si necesita otras que también están desactivadas, antes le pregunta y las nombra (BASE-F19); si no, la activa
     sin preguntar.
  3. La app vuelve a «Mis apps» y al menú, sin recargar, con los datos que tenía: «Reservas está activada.» y, si
     llegó con otras, «También se ha activado: Mesas.».
Entra: lo que necesita la app y lo que el negocio tiene contratado.
Sale: la app en marcha en este negocio, elegida por él.
Si falla: con el límite de apps del plan alcanzado, el aviso de BASE-F18 con «Mejorar plan»; una app de pago sin
contratar no se puede activar (BASE-F20). Bajar de plan no apaga nada: con más apps elegidas que las del plan nuevo,
todas siguen en marcha y solo no se puede activar otra hasta quedar por debajo.
Implicados: ninguno

### BASE-F25 Ver que una app se niega a desactivarse
<!-- origen: old-hub:HUB_SHELL-F125 -->
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
  1. Quien administra pulsa «Desactivar» en una app que otra en marcha necesita (por ejemplo, «Mesas» mientras
     «Reservas» está activada), o en una que se niega mientras tiene algo suyo a medias (VeriFactu, con registros
     que la AEAT aún no ha aceptado: VERIFACTU-F32).
  2. El hub no cambia nada: encima de la tabla sale «No se ha cambiado nada» con lo que hay que hacer antes,
     «Desactiva antes Reservas.» (sin preguntar), o, tras confirmar, con el motivo de la propia app en el idioma de
     quien lo pide: «VeriFactu aún tiene 1 registro por enviar a la AEAT. Espera a que se envíe o arréglalo antes de
     desactivarla.».
  3. El aviso se queda hasta que se cierra o se activa o desactiva otra app; la app sigue «Activa».
Entra: las apps en marcha que la necesitan, o el motivo de la app que se niega.
Sale: nada.
Si falla: sin motivo propio de la app, el mismo aviso dice que no se ha podido cambiar, con el nombre de la app y lo
que ha contestado el hub.
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
     Apps» y, para quien administra en el navegador, «Mejorar plan».
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
Estado: hecho
Actor: propietario, administrador
Pantalla: Sistema · Plan y límites
Pasos:
  1. Pulsa «Sistema» en el menú lateral y, abajo, la pestaña «Plan y límites».
  2. Ve «Los límites de tu plan» con «Dentro del límite» o «Cerca del límite», la tarjeta «Personas» (las
     personas activas del negocio frente a las que permite el plan, con su barra; o «Sin límite») y la de
     «Dispositivos»: cuántos tienen ahora una sesión abierta («Con una sesión abierta ahora.») y, en su etiqueta,
     «Hasta» y el tope del plan, o «Sin límite».
  3. Con todas las plazas ocupadas: «Te estás quedando sin margen en tu plan» — «Tu plan tiene todas las plazas
     ocupadas, así que no puedes añadir a nadie más.», sin botón.
  4. Abajo: «Los planes se gestionan desde tu cuenta de ERPlora, en erplora.com.». Se pone al día solo cuando
     cambian el plan o las personas; la cifra de dispositivos, al abrir la pantalla.
Entra: los topes del plan que erplora.com le pasa al hub, las personas activas del negocio y los dispositivos con
una sesión abierta en él (los mismos que cuenta el tope de BASE-F57).
Sale: nada guardado.
Si falla: «No hemos podido leer tu plan» — «Comprueba la conexión y vuelve a intentarlo.» con «Reintentar».
Quien no administra el negocio ve «Solo quien administra el negocio ve el plan y sus límites.», sin
«Reintentar». Mientras el hub no conoce el plan: «Todavía no conocemos el plan de este negocio: aparecerá en
cuanto erplora.com lo envíe.».
Implicados: BASE-F57

### BASE-F29 Elegir una plantilla del catálogo para importar
<!-- origen: old-hub:HUB_SHELL-F175 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · Datos y copias › Importar
Pasos:
  1. Abre «Ajustes» en el menú lateral; en «Datos y copias», «Importar» es lo que se abre. Dice «Carga una
     plantilla: llena tus apps con sus datos —una carta, servicios, mesas— listos para usar.» y, debajo,
     «Elige qué cargar».
  2. Mientras llegan, «Cargando plantillas…». Después, una tarjeta por plantilla (o una fila, con la vista de
     lista): su nombre, su descripción, su «Idioma» y su «País» por su nombre, su «Versión» y lo que «Trae»
     (cuántas categorías, productos, servicios, zonas o mesas). Primero las del país del negocio y, dentro,
     las del idioma de la persona.
  3. «Buscar plantillas» busca por el nombre, la descripción o las apps que trae.
  4. Pulsa «Usar plantilla» en la que le sirva: el botón gira mientras se lee y se abre «Revisa lo que
     trae» (BASE-F31).
Entra: las plantillas del Hub, una por sector e idioma (hoy restaurante y peluquería, en español y en
inglés).
Sale: nada guardado hasta cargarla.
Si falla: «No se han podido cargar las plantillas ahora mismo. Puedes importar un archivo igualmente.» con
«Reintentar»; sin plantillas, «Todavía no hay plantillas para tu negocio.»; una búsqueda sin resultado,
«Ninguna plantilla coincide con tu búsqueda.»; si la plantilla no se puede leer, «No se pudo leer el
fichero: {reason}» y se queda en la elección. Quien no administra el negocio lee «Solo un administrador
puede ver e importar plantillas.».
Implicados: INVENTORY-F12

### BASE-F30 Subir un fichero para importar
<!-- origen: old-hub:HUB_SHELL-F176 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · Datos y copias › Importar
Pasos:
  1. En «Importar», pulsa «Subir desde archivo» y elige un .blueprint.zip: una copia de seguridad de este
     negocio o una plantilla que exportó otro.
  2. Mientras se lee, el botón gira. Después se abre «Revisa lo que trae» (BASE-F31).
  3. Tras un error se puede elegir el mismo fichero otra vez.
Entra: el fichero, de 5 MB como mucho.
Sale: nada guardado hasta cargarlo.
Si falla: «No se pudo leer el fichero: {reason}» con el motivo (no es un .blueprint.zip, está dañado, lo
hizo una versión más nueva de ERPlora o pasa de 5 MB) y se queda en la elección.
Implicados: ninguno

### BASE-F31 Revisar y cargar lo que trae el fichero
<!-- origen: old-hub:HUB_SHELL-F177 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · Datos y copias › Importar
Pasos:
  1. Tras elegir una plantilla o un fichero sale «Revisa lo que trae»: «Nombre», «Tipo» («Plantilla» o
     «Copia de seguridad»), «Idioma» y «País» por su nombre, cuántas «Apps» y, si es un fichero, cuándo se
     hizo («Creado»).
  2. Debajo, una casilla por app con lo que trae (cada parte y sus filas). Vienen marcadas las que están activadas
     en el negocio y las que la carga activa: una app de la plantilla o del fichero que está desactivada dice
     «Está desactivada en tu negocio: se activará al cargarla.». Una app que solo nombran sus datos, o que el
     plan no incluye, dice «Esta app está desactivada en tu negocio: no se cargará nada suyo.» y una que este
     negocio no tiene, «Este negocio no tiene esta app: no se cargará nada suyo.». Los clientes de
     una plantilla se quedan fuera: «Datos personales: solo se cargan desde una copia de seguridad.». Lo que
     el Hub nunca carga (personas, PIN, datos fiscales) sale en «Nunca se carga aquí».
  3. Desmarca las apps que no quiera y pulsa «Importar» («Importando…»), o «Elegir otro» para volver.
  4. Al terminar sale el informe (BASE-F32). Lo que ya había en el negocio se queda como estaba: no se
     duplica ni se sobrescribe.
Entra: la plantilla o el fichero y las apps marcadas.
Sale: las apps marcadas que estaban desactivadas, activadas antes de cargar, con las que necesitan y dentro
del tope de apps del plan, como si se activaran en Apps (`base.app.enabled`); en cada app marcada, lo que
trae y faltaba, dado de alta como si se hiciera a mano en esa app (sus categorías, productos, servicios,
zonas, mesas y, desde una copia de seguridad, clientes), y el informe guardado (`base.blueprint.imported`).
Si falla: «La importación falló: {reason}» y se queda en la revisión; sin ninguna app marcada, «Elige al
menos una app.» y no se puede importar; si ninguna de sus apps se puede activar aquí, «Nada de este fichero
puede cargarse en tu negocio: ninguna de sus apps se puede activar aquí.». Una app que no se pudo activar (el
tope de apps del plan, una app que el plan no incluye) se queda desactivada, no carga nada y el informe dice
por qué; el resto se carga.
Implicados: INVENTORY-F12

### BASE-F32 Leer el informe de la importación
<!-- origen: old-hub:HUB_SHELL-F178 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · Datos y copias › Importar
Pasos:
  1. Al terminar, «Informe de la importación» con cómo fue: «Todo ha entrado.», «No todo entró.» o «No ha
     entrado nada.».
  2. Una fila por app con su etiqueta: «Aplicado», «Ya lo tenías», «Aplicado en parte», «Falló», «Nada que
     copiar», «Descartado», «App apagada», «No está en este negocio» o «No elegida». Debajo, por cada parte,
     «{created} creadas · {already} ya estaban · {failed} fallaron» y, de lo que falló, su nombre y el
     motivo.
  3. Lo dejado fuera a propósito sale en «Se ha dejado fuera a propósito».
  4. «Ver las plantillas» vuelve al catálogo; «Ir al inicio» lleva al Inicio.
Entra: el informe de la importación.
Sale: nada; el informe queda guardado en el negocio.
Si falla: una etiqueta que la pantalla no conoce sale como «Falló» con su texto tal cual, nunca como un
éxito.
Implicados: ninguno

### BASE-F33 Volver al informe de una importación que no entró entera y reintentar
<!-- origen: old-hub:HUB_SHELL-F179 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · Datos y copias › Importar
Pasos:
  1. Al abrir «Importar», si la última importación no entró entera y no se deshizo, sale primero su informe,
     con «Este es el informe de tu última importación de {name} ({date}). No todo entró.».
  2. Si vino de una plantilla, pulsa «Reintentar lo que falta» («Reintentando…»): se vuelve a cargar la misma
     versión de la plantilla y solo entra lo que faltaba; lo que ya entró no se toca ni se duplica. Sale el
     informe nuevo.
  3. Si vino de un fichero subido a mano, el botón sale apagado con «Esta importación vino de un archivo
     subido a mano, así que no se puede reintentar sola. Vuelve a subir el archivo y elige solo lo que
     falló.»; si esa versión de la plantilla ya no está, con «La versión de la plantilla que usó esta
     importación ya no está en el catálogo, así que no se ha reintentado: otra versión podría cargar datos
     distintos.».
  4. «Ver las plantillas» deja ese informe y abre el catálogo.
Entra: la última importación y su informe.
Sale: lo que faltaba, si ahora entra, y el informe nuevo (`base.blueprint.imported`).
Si falla: «El reintento falló: {reason}» y el informe sigue a la vista.
Implicados: ninguno

### BASE-F34 Deshacer una importación
<!-- origen: old-hub:HUB_SHELL-F180 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · Datos y copias › Restablecer
Pasos:
  1. En «Restablecer», «Deshacer una importación» («Quita solo lo que trajo esa importación. Lo que hayas
     creado después se conserva.»): una fila por importación que trajo algo y no se deshizo, con su nombre,
     cuándo, quién y cuántas filas trajo, y «Deshacer».
  2. Pulsa «Deshacer»: «Deshacer «{name}»», con «Se borrarán las {n} filas que trajo esta importación. Lo que
     creaste después se conserva.». No pide escribir nada: se puede volver a importar.
  3. Confirma con «Deshacer» (o «Cancelar»).
  4. Sale «Importación deshecha:» con una línea por app («{app} — {n} filas borradas»); lo que no se pudo
     borrar (algo que otra app todavía usa) sale aparte con su motivo. Lo que tiene cada sección se pone al
     día.
Entra: la importación elegida.
Sale: borradas exactamente las filas que trajo; lo creado después se queda (`base.import.undone`).
Si falla: el motivo sale en la propia ventana, que no se cierra (en el hub viejo no se decía nada); una
importación ya deshecha, «Esta importación ya se deshizo.».
Implicados: ninguno

### BASE-F35 Exportar una copia de seguridad o una plantilla
<!-- origen: old-hub:HUB_SHELL-F173 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · Datos y copias › Exportar
Pasos:
  1. Abre «Exportar»: «Empaqueta las apps de este negocio —y, si quieres, sus datos— en un archivo que
     puedes cargar en otro negocio o guardar como copia.».
  2. Escribe el «Nombre» (viene el del negocio; sin él, el de su dirección) y elige el «Idioma»; debajo, el
     nombre final del archivo («Archivo: {file}»).
  3. Responde «¿Para qué es este archivo?»: «Copia de seguridad de este negocio» (la que viene marcada; lleva
     también los clientes) o «Plantilla para compartir» (nunca lleva clientes).
  4. Elige las apps y sus datos (BASE-F36) y pulsa «Exportar» («Exportando…»).
  5. El archivo baja con el navegador y sale «{file} descargado.».
Entra: el nombre, el idioma, para qué es y lo marcado.
Sale: un .blueprint.zip con las apps marcadas y, de las que llevan datos, sus filas; nunca personas, PIN
ni datos fiscales. En el negocio no se guarda nada.
Si falla: «La exportación falló: {reason}»; sin nombre, «Escribe un nombre para el archivo.» y no se puede
exportar. Quien no administra el negocio lee «Solo un administrador puede exportar el negocio.».
Implicados: ninguno

### BASE-F36 Elegir qué apps, datos y tablas viajan en la exportación
<!-- origen: old-hub:HUB_SHELL-F174 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · Datos y copias › Exportar
Pasos:
  1. En «Exportar», bajo «Apps» («Elige qué apps registra el archivo y si sus datos viajan con él.»), una fila
     por app encendida con dos casillas, «App» y «Datos». Vienen todas con la app marcada y sin datos; una app
     sin nada propio dice «Nada propio que copiar».
  2. Desmarcar la app desmarca sus datos. «Seleccionar todo» marca todas las apps y sus datos;
     «Deseleccionar todo» las desmarca todas.
  3. Al marcar «Datos» de una app sale debajo «Datos de {app}», con una casilla por cada parte y sus filas;
     desmarcar una la deja fuera. En una plantilla los clientes no se pueden marcar:
     «Solo en una copia de seguridad».
  4. Mientras no se desmarque ninguna parte de una app, viaja todo lo suyo, también lo que esa app traiga
     más adelante.
Entra: las apps encendidas y cuántas filas tiene cada parte.
Sale: nada guardado; lo marcado viaja al exportar.
Si falla: «No se han podido cargar las apps de este negocio.» con «Reintentar»; sin ninguna app marcada no
se puede exportar.
Implicados: ninguno

### BASE-F37 Restablecer el negocio por secciones
<!-- origen: old-hub:HUB_SHELL-F181 -->
Estado: parcial — mientras el negocio comparte su base de datos con otros negocios no se puede vaciar: la pantalla lo explica y no ofrece el botón; se podrá cuando cada negocio tenga la suya
Actor: propietario, administrador
Pantalla: Ajustes · Datos y copias › Restablecer
Pasos:
  1. En «Restablecer», «Restablecer el negocio»: «Borra definitivamente los datos que marques. No se puede
     deshacer: si dudas, exporta antes una copia.», con «Exportar una copia antes», que abre «Exportar».
  2. Dice qué no se borra nunca: «Solo se borra lo que cada sección enumera aquí. Las ventas, las facturas,
     los registros fiscales, las personas y sus accesos, los archivos y los ajustes del negocio se quedan
     siempre.».
  3. Una fila por sección (una app) que tiene algo, con lo que tiene (cada parte y sus filas) y su total.
  4. Con su propia base de datos, marca las secciones y pulsa «Restablecer el negocio»: «Esto no se puede
     deshacer», con «Se borrarán definitivamente {n} filas:» y el desglose. Escribe el nombre del negocio
     («Escribe «{name}» para confirmar») y pulsa «Borrar definitivamente» (o «Cancelar»).
  5. Sale «Negocio restablecido:» con una línea por sección («{app} — {n} filas borradas») y la lista se
     recalcula.
  6. Hoy, con la base de datos compartida, sale «Restablecer el negocio todavía no está disponible. Deshaz una
     importación o quita lo que quieras desde cada app.», sin casillas ni botón.
Entra: lo que tiene cada sección y lo marcado.
Sale: borrado definitivo de lo marcado (`base.hub.data_reset`).
Si falla: el motivo sale en la ventana, que no se cierra: un nombre que no es el del negocio, «El nombre no
coincide.». Quien no administra el negocio lee «Solo un administrador puede deshacer importaciones o
restablecer el negocio.».
Implicados: ninguno

### BASE-F38 Ver Inicio al día después de importar una plantilla
<!-- origen: old-hub:HUB_SHELL-F39 old-hub:HUB_SHELL-F26 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Inicio · Resumen
Pasos:
  1. Mientras el negocio no tiene nada de lo que trae una plantilla (un negocio nace con todas las apps
     desactivadas), quien lo administra ve arriba «Empieza con un negocio como el tuyo» («Elige el que más se
     parezca al tuyo: activamos sus apps y cargamos su catálogo de una vez. Después tendrás que poner tus
     propios datos.»): hasta cuatro plantillas, una por
     tipo de negocio y en su idioma si la hay (primero las de su país), con su descripción y «Usar esta»; «Ver todas las plantillas» abre «Datos y
     copias» y «Ahora no» cierra la tarjeta en este dispositivo.
  2. Pulsa «Usar esta»: «Preparando «{name}»…» mientras se activan sus apps y se carga, sin pantallas
     intermedias.
  3. En la misma tarjeta, «Ya tienes tus apps y tu catálogo» («Lo que queda es lo que solo puedes contestar
     tú: los datos de tu negocio. Los tienes en la lista de abajo.») con «Continuar», que la cierra.
  4. Sin recargar, el Inicio se pone al día: «Termina de configurar tu negocio» cuenta como hechos los pasos
     que resolvió la plantilla y los paneles se refrescan. Igual tras cargar una plantilla o un fichero desde
     «Datos y copias».
Entra: las plantillas y si el negocio todavía está vacío.
Sale: lo que trae la plantilla, como en BASE-F31 (`base.blueprint.imported`).
Si falla: si no entró todo, «No todo ha entrado» con «Estas no han entrado: {apps}.» (o «Hay algo más que
no ha entrado.») y «Ver el informe»; si no se pudo abrir, «No se ha podido abrir esa plantilla» con «No ha
cambiado nada en tu negocio: {reason}» e «Intentar otra vez»; si se cortó a medias, «La configuración no ha
terminado» con «Puede que parte ya esté dentro. Compruébalo en Ajustes › Datos antes de volver a
intentarlo.» y «Ver el informe», sin reintento. Si las plantillas no se pueden leer, «No se han podido
cargar las plantillas para empezar.» con «Reintentar» y «Ahora no».
Implicados: BASE-F01, INVENTORY-F12

### BASE-F39 Abrir Sistema y moverse por sus pestañas
<!-- origen: old-hub:HUB_SHELL-F135 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Sistema · Recursos
Pasos:
  1. Pulsa «Sistema» en el menú lateral, o llega desde la fila «Eventos caídos» de la campana.
  2. Abajo hay cinco pestañas, en este orden: «Recursos», «Plan y límites», «Actualizaciones», «Eventos caídos» y
     «Registros». Se abre «Recursos». La pestaña elegida queda en la dirección: un enlace o recargar abre la misma.
  3. Una pestaña que no existe abre «Recursos»; la antigua de las copias lleva a «Ajustes» › «Datos y copias».
  4. Quien no es propietario ni administrador ve cuatro: «Registros» no existe para él y, si la pide, se abre
     «Recursos». En «Recursos» lee «Solo el dueño o un administrador puede ver cuánto está usando el hub.» y en
     «Eventos caídos», «Solo el dueño o un administrador puede ver los eventos caídos.», sin «Reintentar».
Entra: el papel de la persona en el negocio; a quien no lo administra no se le pide nada que el hub le negaría.
Sale: nada guardado.
Si falla: cada pestaña dice lo suyo (BASE-F40 a BASE-F43).
Implicados: ninguno

### BASE-F40 Ver cuánto está usando el hub
<!-- origen: old-hub:HUB_SHELL-F136 -->
Estado: parcial — sin CPU, memoria ni conexiones del negocio: un solo servicio atiende a todos los negocios y ninguna cifra es solo suya; el tamaño y el uso de su base de datos llegan cuando cada negocio tenga la suya
Actor: propietario, administrador
Pantalla: Sistema · Recursos
Pasos:
  1. Abre «Sistema»: se abre «Recursos». Mientras carga: «Consultando el sistema…».
  2. El título es «Recursos en la nube», con la pastilla «Nube».
  3. La tarjeta «Base de datos» dice «PostgreSQL» y, debajo, «Base de datos compartida» (o «Base de datos propia»
     cuando el negocio tiene la suya).
  4. Debajo: «El uso de CPU, memoria y conexiones no se mide por negocio: los servidores de ERPlora atienden a todos
     los negocios a la vez y crecen solos cuando hace falta.». Nunca una cifra inventada ni un cero.
Entra: en qué base de datos está el negocio.
Sale: nada guardado.
Si falla: «No se pudo consultar el sistema» — «Las métricas y los registros no están disponibles ahora. Puedes
volver a intentarlo.» con «Reintentar».
Implicados: ninguno

### BASE-F41 Saber qué versión corre y qué se le ha actualizado
<!-- origen: old-hub:HUB_SHELL-F142 -->
Estado: parcial — la versión y su fecha sí; sin la lista de lo cambiado en cada app: todas las apps se publican juntas, en un solo despliegue y sin notas de versión
Actor: propietario, administrador
Pantalla: Sistema · Actualizaciones
Pasos:
  1. Abre la pestaña «Actualizaciones». El título es «Qué te hemos actualizado» y una pastilla dice por qué
     versión va el hub. Mientras carga: «Consultando la versión…».
  2. Debajo, el día en que se actualizó o, si no se sabe, «No sabemos cuándo se publicó esta versión.»: nunca una
     fecha inventada.
  3. Y: «Este hub se actualiza solo cuando publicamos una versión nueva, sin cortar el servicio: no tienes que
     instalar nada.». No hay botón de actualizar.
  4. Quien no administra el negocio ve el título y ese texto, sin la versión.
Entra: la versión que corre y cuándo se publicó.
Sale: nada guardado.
Si falla: «No se pudo consultar el sistema» — «Las métricas y los registros no están disponibles ahora. Puedes
volver a intentarlo.» con «Reintentar».
Implicados: ninguno

### BASE-F42 Ver el registro de sucesos del sistema
<!-- origen: old-hub:HUB_SHELL-F144 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Sistema · Registros
Pasos:
  1. Abre la pestaña «Registros»: el título es «Registro de eventos». Para quien no administra el negocio la
     pestaña no existe (BASE-F39).
  2. Ve los 50 últimos sucesos entre las apps del negocio, el más reciente primero, con «Hora», «Nivel»
     («Información», «Aviso» o «Error», en una pastilla) y «Evento»: su nombre, la app que lo anotó y qué ha pasado
     con él en su idioma (entregado, esperando, en «Eventos caídos»…). Nunca lo que llevaba dentro.
  3. Busca con «Buscar evento…», filtra por nivel y va de 20 en 20. En el móvil, cada suceso es una tarjeta
     encabezada por su hora.
  4. El registro se pone al día solo cuando un aviso cae, se reenvía o se descarta; lo demás, al volver a abrir la
     pestaña.
Entra: los últimos sucesos de este negocio, nunca los de otro.
Sale: nada guardado.
Si falla: «No se pudo cargar el registro. Comprueba la conexión y reintenta.» con «Reintentar». Sin sucesos: «Sin
eventos: todavía no ha pasado nada entre las apps de este negocio.».
Implicados: ninguno

### BASE-F43 Ver los eventos caídos
<!-- origen: old-hub:HUB_SHELL-F145 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Sistema · Eventos caídos
Pasos:
  1. Llega desde la fila «Eventos caídos» de la campana (BASE-F10) o pulsando la pestaña «Eventos caídos».
  2. Mientras carga: «Cargando los eventos caídos…». Con eventos: «Arregla la causa (un permiso, una app parada…) y
     reenvía. El evento no se edita: si la causa sigue, vuelve a caer aquí.».
  3. Cada aviso es una tarjeta con su nombre, cuántas veces se intentó, de qué app a cuál iba (por ejemplo, de
     «Ventas / TPV» para «Facturación»), cuándo pasó y su último error tal cual, con «Reenviar» y «Descartar».
     Arriba, «Reenviar todos». Si la app a la que iba ya no está activa, la tarjeta dice que no se puede reenviar
     hasta activarla, sin «Reenviar».
  4. Salen los 100 más recientes; con más, la pantalla dice cuántos se ven de cuántos.
  5. La lista y la campana se ponen al día solas cuando un aviso cae, se reenvía o se descarta.
  6. Sin ninguno: «Todo en orden» — «No hay eventos caídos. La cola de eventos vive en la base de datos: un reinicio
     nunca la pierde.».
Entra: los avisos entre apps de este negocio que agotaron sus reintentos, nunca los de otro.
Sale: nada guardado.
Si falla: «No se pudo consultar el sistema» — «No se pudo cargar la cola de eventos caídos. Comprueba la conexión y
reintenta.» con «Reintentar» a la vista: un fallo nunca sale como «Todo en orden». Quien no administra el negocio
lee «Solo el dueño o un administrador puede ver los eventos caídos.».
Implicados: ninguno

### BASE-F44 Reenviar un evento caído
<!-- origen: old-hub:HUB_SHELL-F146 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Sistema · Eventos caídos
Pasos:
  1. Quien arregló la causa (encendió la app, completó los datos del negocio…) pulsa «Reenviar» en su tarjeta; el
     botón se desactiva mientras se hace.
  2. Sale «Evento reenviado.», la tarjeta desaparece y la campana baja en el momento.
  3. El aviso vuelve a la cola con los intentos a cero y solo lo recibe la app que había fallado; si la causa
     sigue, vuelve a caer aquí.
Entra: el aviso elegido.
Sale: el aviso, otra vez en la cola; `base.failed_event.retried`.
Si falla: «No se pudo reenviar:» y el motivo: «ese evento ya no está en la cola; actualiza la lista.» (alguien lo
reenvió o lo descartó antes), «la app a la que iba ya no está activa en este negocio; actívala y vuelve a
reenviarlo.» o «solo el dueño o un administrador puede hacerlo.».
Implicados: ninguno

### BASE-F45 Reenviar todos los eventos caídos
<!-- origen: old-hub:HUB_SHELL-F147 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Sistema · Eventos caídos
Pasos:
  1. Tras un fallo que tumbó varios avisos, arregla la causa y pulsa «Reenviar todos» (solo sale con avisos en la
     lista).
  2. Confirma en «¿Reenviar todos los eventos caídos?» — «Los que se pueden reenviar vuelven a la cola; los que iban
     a una app parada se quedan aquí.» con «Reenviar todos» (o «Cancelar»: no pasa nada).
  3. Sale cuántos se reenviaron («Eventos reenviados: 2.») y la lista y la campana se vacían; si no había ninguno
     que se pudiera reenviar: «No había nada que reenviar.».
  4. Vuelven a la cola todos los reenviables del negocio, también los que no caben en la lista; los que iban a una
     app parada se quedan.
Entra: los avisos caídos de este negocio.
Sale: los avisos, otra vez en la cola; `base.failed_event.retried`, con cuántos.
Si falla: «No se pudo reenviar:» y el motivo, como en BASE-F44.
Implicados: ninguno

### BASE-F46 Descartar un evento caído
<!-- origen: old-hub:HUB_SHELL-F148 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Sistema · Eventos caídos
Pasos:
  1. Decide que un aviso no debe entregarse nunca (está repetido, ya se hizo a mano) y pulsa «Descartar» en su
     tarjeta.
  2. Se abre la ventana «¿Descartar este evento para siempre?», que dice qué aviso no llegará nunca a qué app y que
     se guarda quién lo descartó, cuándo y por qué, avisa «Si era una venta para Facturación, esa venta se queda sin
     factura.» y pide «Por qué (opcional)».
  3. Pulsa «Descartar para siempre» (o «Cancelar»: no pasa nada).
  4. Sale «Evento descartado (se guarda para auditoría).», la tarjeta desaparece y la campana baja.
Entra: el aviso elegido y, si quiere, por qué.
Sale: el aviso cerrado para siempre, con quién, cuándo y por qué; no se borra ni se vuelve a intentar.
`base.failed_event.discarded`.
Si falla: «No se pudo descartar:» y el motivo, como en BASE-F44.
Implicados: ninguno

### BASE-F47 Informar de un error de la pantalla sin que nadie lo pida
<!-- origen: old-hub:HUB_SHELL-F149 -->
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
  1. La persona no hace nada: cuando la pantalla tiene un error que nadie recogió (también al pintar una parte de la
     pantalla o en una espera que falló sin tratar), se apunta solo.
  2. Se envía al hub sin ventana, sin captura y sin preguntar, aunque la pestaña se esté cerrando.
  3. Un error idéntico no se vuelve a enviar en 30 segundos, y se recuerdan como mucho 50 distintos. Un aviso del
     propio navegador que no es un error de la pantalla, el de que dejó parte del dibujo para el momento siguiente, no
     se envía: no rompe nada y ninguna app lo puede arreglar.
  4. El hub lo deja en su registro de errores con el negocio, la persona y la pantalla donde pasó.
Entra: el mensaje del error, su traza y la pantalla, solo con sesión.
Sale: una línea en el registro de errores del hub; en el navegador no se guarda nada.
Si falla: no pasa nada visible: el envío no se reintenta ni genera otro informe. Sin sesión, o con más de 30
informes por minuto de la misma persona, el hub no lo apunta. Para contar algo a mano, «Reportar un problema» del
menú de usuario (BASE-F108).
Implicados: ninguno

### BASE-F48 Abrir Ajustes y moverse por sus pestañas
<!-- origen: old-hub:HUB_SHELL-F155 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Ajustes
Pasos:
  1. Pulsa «Ajustes» en el menú lateral, o llega desde un enlace de otra pantalla.
  2. Abajo, las pestañas «General», «Negocio», «Impresión» y «Datos y copias», en el orden del hub viejo; se abre
     «General» (BASE-F62). La pestaña elegida queda en el enlace, así que un enlace guardado vuelve a ella y Atrás
     sale de Ajustes en vez de recorrer sus pestañas. En el móvil caben las cuatro, enteras.
  3. Los enlaces antiguos siguen llevando a su sitio: el de la antigua «General» abre «General», el de la antigua
     pestaña de impuestos abre «Negocio», y el de una pestaña que ya no existe abre la primera.
  4. En «Impresión», «Impresoras y tique» («Da de alta tu impresora y configura el tique impreso y digital»)
     abre la app Impresión; si no está, dice «Instala la app Impresión para dar de alta tu impresora y configurar
     el tique» y lleva a «Apps».
Entra: las apps del negocio.
Sale: nada guardado.
Si falla: no falla: es navegación. Cada pestaña dice en ella misma si no ha podido cargar lo suyo (BASE-F49,
BASE-F29).
Implicados: PRINTING-F06, BASE-F29, BASE-F49, BASE-F62

### BASE-F49 Ver el país del negocio
<!-- origen: old-hub:HUB_SHELL-F156 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Ajustes · Negocio
Pasos:
  1. En «Negocio», «País» («El de sus impuestos y sus facturas») dice, en el idioma de la persona, el país con
     el que el negocio se dio de alta en erplora.com.
  2. Aquí no se elige: debajo pone «El país no cambia una vez listo el negocio.», porque sus facturas son de un
     país. Mientras el negocio se prepara, se cambia en erplora.com (HUBS-F15).
Entra: el país con el que erplora.com dio de alta el negocio.
Sale: nada guardado; con él, las plantillas del negocio salen primero y «Termina de configurar tu negocio» sabe
qué pasos le tocan.
Si falla: si los datos del negocio no se pueden leer, «No se pudieron cargar los datos del negocio» con
«Reintentar». Una demo no tiene país: «—».
Implicados: HUBS-F15, BASE-F01, BASE-F29

### BASE-F50 Ver la moneda del negocio
<!-- origen: old-hub:HUB_SHELL-F158 -->
Estado: parcial — el Inicio, Ventas, Caja, Facturación, Inventario, Tarifas, Impresión, Cocina y Suplementos ya van en la moneda del negocio, pero Pagos, Carrito y pago, Citas, Menús y combos y Clientes todavía en euros aunque el país del negocio pague en otra moneda: con España y Portugal cuadra, con un país de otra moneda no
Actor: propietario, administrador, responsable, empleado
Pantalla: Ajustes · Negocio; Inicio · Resumen e Inicio · Actividad
Pasos:
  1. En «Negocio», «Moneda» («La de su país, para precios y totales») dice la moneda con su código y su nombre
     en el idioma de la persona: «EUR · Euro».
  2. No se elige: es la del país del negocio, como en los terminales de cobro del mercado. Un negocio sin país
     (una demo) va en euros.
  3. En el Inicio, los importes de los paneles (como «Ventas últimos 7 días») y de «Actividad» van en esa moneda,
     con su símbolo y sus decimales, como los imprime una caja de ese país: «zł» en un negocio de Polonia, «€» en
     uno de España. Mientras el negocio no ha contestado, el importe sale sin símbolo, nunca en otra moneda.
Entra: el país del negocio.
Sale: nada guardado.
Si falla: como en BASE-F49.
Implicados: BASE-F49

### BASE-F51 Cambiar el idioma del negocio en erplora.com
<!-- origen: old-hub:HUB_SHELL-F159 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · Negocio
Pasos:
  1. En «Negocio», «Idioma del negocio» («El de quien no haya elegido el suyo») dice el idioma del negocio por su
     nombre.
  2. Pulsa «Cambiar en erplora.com»: se abren en otra pestaña los ajustes del negocio en erplora.com, donde lo
     cambia y pulsa «Guardar cambios» (HUBS-F15).
  3. Sin recargar, «Negocio» enseña el idioma nuevo en cuanto el negocio lo recibe; igual con el nombre y la zona
     horaria.
Entra: el idioma que guardó erplora.com.
Sale: nada guardado en el negocio: lo recibe de erplora.com (`base.hub.registered`). Quien no ha elegido un idioma
propio en «Mi perfil» y entra con su PIN ve el hub en el del negocio, no en el de su navegador; con su cuenta, en el
de su cuenta de erplora.com (BASE-F64).
Si falla: si el negocio no responde, erplora.com se queda con el cambio y se lo vuelve a mandar (HUBS-F08);
mientras tanto, «Negocio» sigue con el anterior. Quien no administra el negocio no ve el botón: «Solo el
propietario o un administrador los cambian, en erplora.com.». En una demo, «Esta demo no tiene un negocio en
erplora.com: sus datos no se cambian.».
Implicados: HUBS-F15, HUBS-F08, BASE-F64

### BASE-F52 Entrar con la cuenta de erplora.com
<!-- origen: old-hub:HUB_SHELL-F01 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Acceso
Pasos:
  1. Abre el negocio sin sesión. En un dispositivo que no ofrece PIN va directo a la entrada de erplora.com para
     este negocio; en una caja que sí lo ofrece sale **Acceso** y pulsa la pestaña «Cuenta» y después «Entrar con
     tu cuenta».
  2. En erplora.com entra como siempre: email y contraseña, Google o su código de verificación.
  3. Vuelve al negocio ya dentro, en la pantalla que había pedido (un enlace a una pestaña, como
     `/settings#data` o `/system#plan`, vuelve a esa pestaña) o en **Inicio**. Si este dispositivo pide PIN,
     el negocio ya entra en sus cajas con PIN y la persona aún no tiene uno, antes le pide elegirlo (BASE-F54).
Entra: la cuenta que comprueba erplora.com; este navegador.
Sale: la sesión de la persona en este negocio y este navegador convertido en un dispositivo de confianza del
negocio (sale en «Dispositivos», compartido mientras nadie diga lo contrario). La sesión dura un turno de 12 horas
en un dispositivo compartido, 30 días en uno personal y como mucho 1 hora si el negocio pide siempre el PIN.
Si falla: erplora.com dice por qué no entra (credenciales, verificación, «No tienes acceso a este hub»); el
negocio no guarda nada hasta que vuelve con la persona identificada.
Implicados: BASE-F13

### BASE-F53 Entrar desde el panel de erplora.com sin volver a teclear la contraseña
<!-- origen: old-hub:HUB_SHELL-F02 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Acceso
Pasos:
  1. En erplora.com, con la sesión abierta, pulsa entrar en su negocio.
  2. El negocio se abre con la persona ya dentro, en **Inicio**, sin pasar por ninguna pantalla de entrada.
Entra: el pase de un solo uso que da erplora.com.
Sale: lo mismo que BASE-F52: la sesión y este navegador como dispositivo de confianza del negocio, así que
después ofrece el pinpad, sale en «Dispositivos» y su modo se puede cambiar.
Si falla: un pase caducado o ya usado no abre nada: el negocio vuelve a pedir la entrada de erplora.com.
Implicados: BASE-F52

### BASE-F54 Elegir el PIN la primera vez que se entra en una caja
<!-- origen: old-hub:HUB_SHELL-F03 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Crea tu PIN de acceso
Pasos:
  1. Tras entrar con la cuenta (BASE-F52) en un dispositivo compartido de un negocio que pide PIN, donde otra
     persona ya entra con el suyo, y si la persona aún no tiene PIN, sale «Crea tu PIN de acceso» — «Con él
     entrarás en esta caja sin tu contraseña.».
  2. Teclea el PIN en el teclado de círculos: «Elige un PIN de {n} dígitos» (4 o 6, lo que diga el negocio).
  3. Repite: «Confirma tu PIN». Al acertar se guarda y entra donde iba.
  4. «Ahora no» lo deja para más tarde: entra igual y puede elegirlo en **Mi perfil** (BASE-F65).
Entra: la sesión recién abierta; los dígitos del PIN del negocio.
Sale: el PIN de la persona, guardado cifrado; su cara aparece en «Cambiar de usuario» al momento y en el pinpad
de **Acceso** en menos de un minuto.
Si falla: la repetición no coincide: «Los PIN no coinciden, inténtalo de nuevo» y vuelve al primer paso. Dígitos
repetidos o seguidos: «Ese PIN es demasiado fácil de adivinar: evita dígitos repetidos (1111) y secuencias
(1234).». Ya lo usa otra persona: «Ese PIN ya lo tiene otra persona activa: elige otro.». Sin conexión: «No se
pudo guardar el PIN. Vuelve a intentarlo.». Un negocio en el que nadie tiene PIN no lo pide al entrar: el primero
se elige en **Mi perfil**.
Implicados: BASE-F52, BASE-F65

### BASE-F55 Entrar con PIN
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
Implicados: BASE-F54, BASE-F67

### BASE-F56 Entrar pasando la placa
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
Sale: lo mismo que BASE-F55.
Si falla: una tarjeta que no es de nadie o cuyo dueño ya no está: «Esa placa no abre nada aquí. Entra con tu PIN
o pídeselo a un administrador.»; cuenta como un intento fallido. El pinpad sigue disponible.
Implicados: BASE-F55

### BASE-F57 Perder la sesión porque se abrió en otro dispositivo
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
     o amplía los dispositivos de tu plan.» con «Mejorar plan».
  4. Puede volver a entrar (y cierra la del otro) o ir a ampliar el plan a erplora.com.
Entra: los dispositivos que cubre el plan, que erplora.com le pasa al negocio.
Sale: las sesiones de los dispositivos que sobran, cerradas, y el motivo guardado en cada uno para decírselo.
Si falla: sin tope en el plan no se cierra nada.
Implicados: BASE-F11, BASE-F28

### BASE-F58 La sesión termina mientras se trabaja
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
Implicados: BASE-F13, BASE-F70

### BASE-F59 Cerrar la sesión de una caja que nadie toca
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
Implicados: BASE-F67

### BASE-F60 Cambiar de usuario sin perder la venta
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
Implicados: BASE-F55, BASE-F56

### BASE-F61 Cerrar sesión
<!-- origen: old-hub:HUB_SHELL-F10 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: El menú de usuario
Pasos:
  1. Abre la tarjeta de usuario arriba del menú lateral (en el móvil, primero el menú con el botón de la barra).
  2. Pulsa «Cerrar sesión».
  3. En una caja con pinpad vuelve a **Acceso**, lista para la siguiente persona. En otro dispositivo, erplora.com
     pregunta «¿Cerrar la sesión de erplora.com?»: «Cerrar sesión» la cierra también y erplora.com pide entrar de
     nuevo; «Seguir conectado» la deja abierta y enseña los negocios de la cuenta.
Entra: la sesión.
Sale: la sesión cerrada en el negocio; la de erplora.com, solo si la persona lo confirma.
Si falla: si el negocio no contesta, la sesión caduca sola.
Implicados: ninguno

### BASE-F62 Decidir si este dispositivo es compartido o personal
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
Implicados: BASE-F55

### BASE-F63 Abrir un hub que todavía no está dado de alta
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

### BASE-F64 Cambiar mis datos, foto, idioma y apariencia
<!-- origen: old-hub:HUB_SHELL-F21 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Mi perfil
Pasos:
  1. Abre la tarjeta de usuario del menú y pulsa «Perfil». Arriba, su cara, su nombre, «Tu identidad y tus
     preferencias personales en este negocio.» y su rol.
  2. En «Datos de la cuenta» cambia «Nombre», «Apellidos» o «Correo electrónico» («Solo para contactarte: no es el
     correo con el que entras.») y pulsa «Guardar mis datos»: «Perfil guardado», y el menú lateral ya dice el nombre nuevo, sin recargar.
  3. «Elegir imagen» sube una foto JPG, PNG o WebP de hasta 2 MB («Foto actualizada»); «Quitar» la borra («Foto
     quitada»).
  4. En «Preferencias», «Idioma» («Usar el idioma del negocio», «Español», «English») y «Apariencia» («Paleta de
     tema» y «Tema»: «Sistema (auto)», «Claro», «Oscuro») se guardan al elegir y se aplican al momento; «Usar la
     apariencia del negocio» deshace lo propio.
Entra: el perfil de quien tiene la sesión.
Sale: su nombre en este negocio (el que sale en el menú lateral, en las caras y en «Dispositivos»), su foto, su idioma
y su apariencia, que le siguen en cualquier dispositivo en el que entre, con su PIN o con su cuenta. Con «Usar el
idioma del negocio», entra con PIN en el del negocio y con su cuenta en el de su cuenta de erplora.com (BASE-F51). El
correo es solo de contacto: no cambia la cuenta de erplora.com.
Si falla: si el perfil no se pudo leer, «No se pudo cargar el perfil» — «Tus datos siguen igual. Comprueba la
conexión y vuelve a intentarlo.» con «Reintentar». Al guardar: «No se pudo guardar el perfil»; foto rechazada:
«No se pudo guardar la foto. Usa JPG, PNG o WebP de hasta 2 MB.»; preferencias: «No se pudieron guardar tus
preferencias. Comprueba la conexión e inténtalo de nuevo.».
Implicados: BASE-F51

### BASE-F65 Cambiar mi PIN desde Mi perfil
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
Implicados: BASE-F54

### BASE-F66 Elegir cuántos dígitos tiene el PIN del negocio
<!-- origen: old-hub:HUB_SHELL-F100 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · General
Pasos:
  1. Con el pinpad encendido (BASE-F67), bajo «Dígitos del PIN» elige «4 dígitos» o «6 dígitos».
  2. Se guarda al momento. Debajo: «Todo el mundo teclea el mismo número de dígitos, que es lo que permite que el
     teclado entre al último en vez de pedirte confirmar. Los PIN que ya se usan siguen funcionando hasta que su
     dueño los cambie.».
  3. Desde ese momento, el pinpad, «Crea tu PIN de acceso» y **Mi perfil** piden esa longitud.
Entra: la elección.
Sale: la longitud del PIN del negocio. No toca los PIN que ya hay.
Si falla: «No se pudo cambiar. Comprueba la conexión e inténtalo de nuevo.».
Implicados: BASE-F67

### BASE-F67 Decidir si se pide PIN en la caja y cuándo se vuelve a pedir
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
Implicados: BASE-F55, BASE-F59

### BASE-F68 Ver los dispositivos en los que se ha entrado
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
Implicados: BASE-F69, BASE-F70, BASE-F71

### BASE-F69 Ponerle nombre a un dispositivo
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
Implicados: BASE-F68

### BASE-F70 Quitar un dispositivo que se ha perdido
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
Implicados: BASE-F58, BASE-F68

### BASE-F71 Quitar de golpe los dispositivos que nadie usa
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
Sale: esos dispositivos olvidados, como BASE-F70.
Si falla: «No se pudieron quitar los dispositivos sin usar. Comprueba la conexión y vuelve a intentarlo.».
Implicados: BASE-F70

### BASE-F72 Ver los archivos del negocio
<!-- origen: old-hub:HUB_SHELL-F130 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Archivos
Pasos:
  1. Pulsa «Archivos» en el menú lateral. Mientras carga: «Cargando archivos…».
  2. Ve el árbol de carpetas a la izquierda (en una pantalla estrecha, el selector «Carpetas»), la ruta de la
     carpeta abierta, lo que hay en ella en «Cuadrícula» (lo primero que sale) o en «Lista», y «Espacio»: lo que
     ocupan los archivos del negocio y los de sus apps, contra el límite del plan («{used} de {limit}») o, si no tiene,
     «{used} usados · Sin límite».
  3. Entra en una carpeta pulsándola en el árbol, en la cuadrícula o en el selector, y vuelve por la ruta. La carpeta
     abierta queda en el enlace, así que se puede compartir con el equipo.
  4. Busca por el nombre en «Buscar archivos…», solo dentro de la carpeta abierta; sin resultados, «Ningún archivo
     de esta carpeta coincide con «{search}».».
  5. Una carpeta vacía dice «Sin archivos» (a quien administra el negocio, también «Sube un archivo o arrástralo
     aquí.»).
  6. La carpeta se pone al día sola cuando alguien del equipo sube, mueve, renombra o elimina algo, desde cualquier
     dispositivo.
Entra: los archivos y las carpetas de este negocio, nunca los de otro. Las carpetas que usan las apps para lo suyo
(las imágenes de la web) no salen aquí.
Sale: nada guardado.
Si falla: «No se pudieron cargar los archivos» con el motivo («El almacén de archivos no ha respondido. Inténtalo de
nuevo en un momento.» o «Comprueba la conexión y vuelve a intentarlo.») y «Reintentar»; un fallo nunca sale como «Sin
archivos».
Implicados: ninguno

### BASE-F73 Subir archivos y crear carpetas
<!-- origen: old-hub:HUB_SHELL-F131 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Archivos
Pasos:
  1. En la carpeta abierta pulsa «Subir archivo» y elige uno o varios, o los arrastra al gestor («Suelta los
     archivos para subirlos aquí»). Mientras suben: «Subiendo {done} de {total}…».
  2. Sale «Archivos subidos.» y aparecen en la carpeta. Si ya había uno con el mismo nombre, no se pisa: el nuevo se
     guarda como «nombre (1).ext» y sale «Se ha subido como «{name}»: ya había uno con ese nombre.».
  3. Para una carpeta nueva pulsa «Nueva carpeta», escribe el «Nombre de la carpeta» (hasta 100 caracteres) y pulsa
     «Crear carpeta». Sale «Carpeta creada.» y la carpeta aparece en el árbol y en la carpeta abierta.
Entra: los archivos, de hasta 25 MB cada uno, o el nombre de la carpeta; la carpeta abierta.
Sale: el archivo o la carpeta, en los archivos del negocio (`base.file.uploaded`, `base.file.folder_created`).
Si falla: cada archivo rechazado dice por qué, sin parar los demás: «No se pudo subir «{name}»: {reason}», con «Ese
archivo pesa más de 25 MB, lo máximo que admite Archivos.», «Los programas (.{extension}) no se pueden guardar
en Archivos: podrían dañar a quien los abra.», «No queda espacio para ese archivo: tu plan incluye {space}.» o «El
archivo no llegó entero. Vuelve a subirlo.». Lo subido y lo rechazado salen en un solo aviso: se ve un aviso a
la vez y el nuevo cierra el anterior, nunca uno encima de otro. Al crear una carpeta, el diálogo sigue abierto con el motivo: «Ese nombre
no es válido. Usa un nombre sin barras ni puntos sueltos.» o «Ya hay un archivo o una carpeta con ese nombre aquí.».
Quien no administra el negocio no ve los botones y, si lo intenta igual, lee «Solo un administrador puede modificar
los archivos.».
Implicados: ninguno

### BASE-F74 Previsualizar y descargar un archivo
<!-- origen: old-hub:HUB_SHELL-F132 -->
Estado: parcial — las hojas de Excel (xlsx) y los documentos de Word (docx) dicen «Sin vista previa» y se descargan, y un archivo de datos (.json) se ve ordenado pero sin plegar; el visor del hub viejo los enseñaba
Actor: propietario, administrador, responsable, empleado
Pantalla: Archivos
Pasos:
  1. Pulsa un archivo, o «Abrir» en su ⋮. Se abre un visor grande dentro del hub, con el nombre como título,
     «Descargar» y «Cerrar».
  2. Enseña imágenes (enteras en el visor, nunca más grandes que el original, con «Ampliar» y «Reducir»), PDF (las
     primeras 30 páginas; si es más largo, «Mostrando las primeras {shown} de {total} páginas. Descarga el archivo
     para leerlo entero.»), texto, registros y código, CSV y TSV como tabla, archivos de datos (.json) ordenados, audio y vídeo. De un texto
     muy largo, «Mostrando el principio del archivo. Descárgalo para leerlo entero.»; de una tabla de más de 500
     filas, «Mostrando las primeras {shown} filas. Descarga el archivo para verlas todas.».
  3. Cualquier otro tipo: «Sin vista previa» con «Este tipo de archivo no se puede mostrar aquí. Descárgalo para
     abrirlo con una aplicación de tu dispositivo.».
  4. «Descargar», en el visor o en el ⋮, guarda el archivo con su nombre.
Entra: el archivo, que el hub lee de su almacén con la sesión de la persona; el navegador nunca va al almacén y el
archivo no queda guardado en ninguna caché.
Sale: nada guardado.
Si falla: «No se pudo abrir el archivo» con «No llegó el contenido del archivo. Revisa la conexión e inténtalo de
nuevo.», nunca un visor en blanco; si no se pudo descargar, «No se pudo descargar «{name}»: {reason}».
Implicados: ninguno

### BASE-F75 Mover y renombrar un archivo o una carpeta
<!-- origen: old-hub:HUB_SHELL-F133 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Archivos
Pasos:
  1. Para renombrar, elige «Renombrar» (o «Renombrar carpeta») en el ⋮: un diálogo con el nombre actual ya escrito
     (hasta 255 caracteres). Pulsa «Renombrar» y sale «Renombrado.».
  2. Para mover, elige «Mover a…»: «Mover «{name}»» con las carpetas del negocio en árbol, empezando por
     «Archivos»; elige una y pulsa «Mover». También puede arrastrar el archivo o la carpeta a una carpeta del árbol o
     de la cuadrícula. Sale «Movido a «{folder}».» (a lo de arriba del todo, «Movido a «Archivos».»).
  3. Una carpeta se mueve o se renombra con todo lo que tiene. Si es la carpeta abierta (su ⋮, junto a la ruta), la
     pantalla la sigue a su sitio nuevo. Nunca se ofrece como destino de sí misma ni de las suyas.
Entra: el archivo o la carpeta y el nombre nuevo, o la carpeta de destino.
Sale: el cambio, en los archivos del negocio (`base.file.renamed`, `base.file.moved`).
Si falla: el diálogo sigue abierto con el motivo: «Ya hay un archivo o una carpeta con ese nombre aquí.», «Ya está en
esa carpeta.», «Una carpeta no se puede mover dentro de sí misma.», «Ese nombre no es válido. Usa un nombre sin barras
ni puntos sueltos.» o «Ese archivo o carpeta ya no existe. Actualiza la lista.»; al arrastrar, «No se pudo mover:
{reason}». Quien no administra el negocio no ve «Renombrar» ni «Mover a…» y, si lo intenta igual, lee «Solo un
administrador puede modificar los archivos.».
Implicados: ninguno

### BASE-F76 Borrar un archivo o una carpeta
<!-- origen: old-hub:HUB_SHELL-F134 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Archivos
Pasos:
  1. Elige «Eliminar» (o «Eliminar carpeta») en el ⋮ de un archivo, de una carpeta o de la carpeta abierta.
  2. La pantalla pregunta: «Eliminar archivo» con «Vas a eliminar «{name}». Esta acción no se puede deshacer.», o
     «Eliminar carpeta» con «Vas a eliminar «{name}» y todo su contenido. Esto no se puede deshacer.».
  3. Pulsa «Eliminar» (o «Cancelar»). Sale «Archivo eliminado.» o «Carpeta eliminada.». Si eliminó la carpeta
     abierta, la pantalla sube a la de arriba.
Entra: el archivo o la carpeta.
Sale: el archivo o la carpeta, con todo lo que tenía, fuera de los archivos del negocio; no hay papelera
(`base.file.deleted`).
Si falla: «No se pudo eliminar: {reason}», con «Ese archivo o carpeta ya no existe. Actualiza la lista.» o «Tu sesión
ha caducado. Vuelve a entrar e inténtalo otra vez.». Quien no administra el negocio no ve «Eliminar» y, si lo intenta
igual, lee «Solo un administrador puede modificar los archivos.».
Implicados: ninguno

### BASE-F77 Llegar al tope de personas del plan
<!-- origen: old-hub:HUB_SHELL-F83 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Empleados · Personal
Pasos:
  1. En **Empleados › Personal**, encima de la tabla, cuántas plazas del plan están ocupadas: «{used} de {limit}
     plazas ocupadas», «{used} personas · sin límite» o, si erplora.com no ha dicho el plan, «{used} personas».
  2. Con todas ocupadas sale «Tu plan tiene todas las plazas ocupadas» y «Quita en erplora.com a alguien que ya no
     trabaje aquí, o pasa a un plan con más plazas.»; en la web, con «Mejorar plan».
  3. Para invitar a alguien más, «Invitar en erplora.com» lleva a «Miembros» del negocio, donde se aplica el tope.
Entra: las personas del negocio y las plazas de su plan, como las manda erplora.com.
Sale: nada guardado.
Si falla: «No se pudo cargar el personal de este negocio.» con «Reintentar», nunca «Todavía no hay nadie en este
negocio.».
Implicados: BASE-F81, BASE-F83

### BASE-F78 Retirar el PIN a una persona
<!-- origen: old-hub:HUB_SHELL-F86 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ficha de una persona
Pasos:
  1. En **Empleados › Personal**, toca a la persona: se abre su ficha.
  2. En «PIN», «Tiene PIN desde el {when}.» y «Retirar el PIN».
  3. Lo pulsa: «Retirar el PIN» con «{name} dejará de entrar en las cajas con su PIN. Con su cuenta de erplora.com
     sigue entrando.». Confirma con «Retirar el PIN».
  4. Sale «PIN retirado.» y la ficha dice «Sin PIN: lo elige la propia persona en «Mi perfil» o la primera vez que
     entra en una caja.».
Entra: la persona.
Sale: la persona sin PIN: desaparece de las caras de las cajas al momento. Evento `base.person.pin_removed`.
Si falla: «No se pudo retirar el PIN.»; el acceso del propietario solo lo cambia el propietario: «Solo el
propietario cambia el acceso del propietario.».
Implicados: BASE-F81, BASE-F55

### BASE-F79 Dar de alta o retirar la placa de una persona
<!-- origen: old-hub:HUB_SHELL-F87 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ficha de una persona
Pasos:
  1. En la ficha de la persona, en «Placa»: «Pasa la tarjeta y se rellena sola: no hace falta hacer clic aquí antes.
     También puedes teclear el número, para un llavero o una etiqueta grabada.».
  2. Pasa la tarjeta por el lector (o teclea el número) y pulsa «Guardar placa»: «Placa guardada.» y «Tiene placa
     desde el {when}.».
  3. Para quitarla, «Retirar la placa»: «Placa retirada.» y «Sin placa.».
Entra: la persona y su placa.
Sale: la placa de la persona, guardada sin su número (solo lo que permite reconocerla). Eventos
`base.person.badge_set` y `base.person.badge_removed`.
Si falla: «Una placa tiene entre 4 y 64 caracteres: letras, dígitos, «-» y «_».», «Esa placa ya la lleva otra
persona. La placa dice quién está en la caja, así que no la pueden compartir dos personas.», «Demasiadas placas
probadas. Espera unos minutos y vuelve a intentarlo.», «No se pudo guardar la placa.» o «No se pudo retirar la
placa.». Nadie da de alta la suya: «Nadie da de alta su propia placa: pídeselo a otro administrador.».
Implicados: BASE-F56, BASE-F81

### BASE-F80 Reincorporar a una persona que salió del negocio
<!-- origen: old-hub:HUB_SHELL-F89 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Empleados · Personal
Pasos:
  1. Quien salió del negocio ya no está en **Empleados › Personal**: se quitó en erplora.com.
  2. Para que vuelva, «Invitar en erplora.com» y se la invita otra vez en «Miembros» del negocio, con su rol.
  3. Cuando acepta, vuelve a la lista con lo que el negocio guardaba de ella: su PIN y su placa siguen valiendo.
Entra: la invitación en erplora.com.
Sale: la persona otra vez en el negocio, con su PIN y su placa de antes.
Si falla: mientras no acepta, sale como «Aún no ha entrado».
Implicados: BASE-F77, BASE-F81

### BASE-F81 Entender cómo entra cada persona
<!-- origen: old-hub:HUB_SHELL-F90 -->
Estado: hecho
Actor: propietario, administrador, encargado, empleado
Pantalla: Empleados · Personal
Pasos:
  1. En **Empleados › Personal**, una fila por persona (en el móvil, una tarjeta): «Usuario» (con «Tú» en la suya;
     en una fila, un nombre que no cabe se corta y sale entero al pasar por encima), «Email» (solo para quien
     administra), «Rol», «Acceso» y «Estado».
  2. «Acceso» dice cómo entra: «Cuenta» siempre, y «PIN» y «Placa» si los tiene (por ejemplo, «Cuenta + PIN +
     Placa»).
  3. «Estado» dice «Activo» o, si erplora.com ya la invitó y aún no ha entrado, «Aún no ha entrado».
  4. Busca con «Buscar persona…». Quien administra toca una fila para abrir su ficha.
Entra: las personas del negocio.
Sale: nada guardado. Se pone al día sola cuando alguien elige o pierde su PIN o su placa.
Si falla: «No se pudo cargar el personal de este negocio.» con «Reintentar».
Implicados: BASE-F77, BASE-F78, BASE-F79

### BASE-F82 Ver los roles y encender los que trae una app
<!-- origen: old-hub:HUB_SHELL-F91 -->
Estado: parcial — se ven los cuatro roles de erplora.com; ninguna app trae todavía roles propios que encender
Actor: propietario, administrador, encargado, empleado
Pantalla: Empleados · Roles
Pasos:
  1. En **Empleados › Roles**: «Estos son los roles de este negocio. Cada persona recibe uno al invitarla en
     erplora.com, y allí se cambia.».
  2. Una fila por rol: «Propietario», «Administrador», «Encargado» y «Empleado», con «Básico», «Siempre
     disponible», cuántas personas lo tienen y cuántos permisos da.
  3. Quien administra tiene «Cambiar roles en erplora.com».
Entra: los roles y las personas del negocio.
Sale: nada guardado.
Si falla: «No se pudo cargar el catálogo de roles.» con «Reintentar».
Implicados: BASE-F83

### BASE-F83 Asignar un rol a una persona
<!-- origen: old-hub:HUB_SHELL-F92 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Empleados · Roles
Pasos:
  1. En **Empleados › Roles** o en la ficha de una persona, «Cambiar roles en erplora.com» o «Abrir en
     erplora.com» lleva a «Miembros» del negocio.
  2. Allí le cambia el rol.
  3. Al volver, la persona sale con su rol nuevo y lo que puede hacer cambia al momento.
Entra: el rol que se elige en erplora.com.
Sale: la persona con su rol nuevo, como lo manda erplora.com.
Si falla: lo que diga erplora.com.
Implicados: BASE-F82, BASE-F13

### BASE-F84 Aprobar con el PIN de un responsable
<!-- origen: old-hub:HUB_SHELL-F51 -->
Estado: hecho
Actor: empleado, encargado
Pantalla: Hace falta una aprobación
Pasos:
  1. Alguien intenta algo que su rol no permite y que la app deja aprobar a un responsable. En lugar de un error
     sale «Hace falta una aprobación» con «Se aprueba: {action}», en palabras de la app y en el idioma de quien lo
     pide; cuando la app lo dice con cifras, con las de eso mismo que se pide (el porcentaje o el importe de un
     descuento, en la moneda del negocio, o la cantidad), para que el responsable sepa cuánto aprueba. Si alguna
     cifra falta o es cero, la frase no la nombra.
  2. Lee «Pide a un encargado que introduzca su PIN para aprobarlo.» y «…o que pase su placa: no hace falta pulsar
     nada antes.».
  3. En «¿Quién lo aprueba?», las caras de quienes pueden hacerlo ellos mismos y tienen PIN (con una sola, su teclado
     sale ya). El responsable toca la suya y teclea su PIN en el teclado, entero a la vista sin desplazar, también el
     0 y «Borrar» («Otra persona» vuelve a las caras), o pasa su placa en cualquier momento.
  4. La acción se hace una vez y sale «Aprobado por {name}». La sesión de quien lo pidió no se cierra.
  También desde el asistente: el «sí» de su tarjeta abre el mismo diálogo, con las cifras de lo que se le pidió.
Entra: el nombre y el PIN, o la placa, de quien aprueba.
Sale: una aprobación que vale para esa acción, de esa persona, una sola vez y durante dos minutos; queda anotada en
**Empleados › Aprobaciones**. Eventos `base.approval.granted` y `base.approval.used`. Se gasta junto con la acción:
si la acción falla por un motivo del negocio, la aprobación sigue sin usar y la misma acción, repetida en esos dos
minutos, pasa con ella; si salió bien, no se repite; dos a la vez con la misma, solo pasa una. Lo que la acción
aprobada hace por el camino en otras apps (la factura rectificativa de una anulación, las sesiones de bono que
devuelve) va con la aprobación, como cuando lo hace el propio responsable; nada más: ni lo que solo se consulta ni la
acción siguiente. Quien no es del negocio recibe el rechazo de siempre, sin la pregunta de la aprobación.
Si falla: el diálogo se queda abierto con «Esos datos no aprueban esto. Revisa el nombre y el PIN, y vuelve a
intentarlo.», «Esa persona no puede aprobarlo: pídeselo a alguien que pueda hacerlo.», «Esto ya no necesita
aprobación: vuelve a hacerlo.», «Esto no se aprueba con un PIN.», la espera tras demasiados intentos o «No se pudo
enviar la aprobación. Comprueba la conexión y vuelve a intentarlo.». Sin nadie con PIN que pueda: «Aquí nadie puede
aprobarlo con un PIN. Quien pueda hacerlo puede pasar su placa.». «Cancelar» devuelve a la app su rechazo.
Implicados: BASE-F85, BASE-F55, BASE-F56, SALE-F30, SALE-F31

### BASE-F85 Consultar quién aprobó qué
<!-- origen: old-hub:HUB_SHELL-F93 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Empleados · Aprobaciones
Pasos:
  1. En **Empleados › Aprobaciones** (la pestaña solo existe para quien administra): «Cada acción que necesitó el PIN
     de un encargado: quién la pidió, quién la autorizó y para qué. Nadie, tampoco un administrador, puede editarlo
     ni borrarlo.».
  2. Una fila por aprobación, la última primero: «Cuándo», «Acción» (en palabras y en su idioma; con las cifras de
     lo que se hizo con ella, cuando la app las da: una aprobación sin usar no hizo nada y no lleva cifras),
     «Autorizado por», «Lo pidió», «Con» («PIN» o «Placa») y «Estado» («Usada» o «Sin usar»).
  3. Busca con «Buscar por persona o acción…» (también por sus cifras) y, en «Filtros» (el embudo), filtra por
     «Cuándo» (un día o unos días seguidos), «Acción» (las que hay en el registro, cada una una vez y sin cifras),
     «Con» y «Estado».
  4. «Exportar CSV» descarga un archivo con las aprobaciones que dejan la búsqueda y los filtros, también las más
     antiguas que la lista ya no enseña, con las mismas columnas en su idioma; mientras tanto dice «Exportando…».
Entra: el registro de aprobaciones.
Sale: nada; es solo lectura (el archivo exportado no cambia nada). Se pone al día sola con cada aprobación.
Si falla: «No se pudo cargar el registro de aprobaciones.» con «Reintentar»; sin ninguna, «Todavía nadie ha tenido
que autorizar nada en este negocio.» (y el archivo exportado trae solo la cabecera). Si no se puede exportar, un aviso
lo dice con su motivo y no se descarga nada.
Implicados: BASE-F84

### BASE-F86 Crear una llave de API y copiar su token
<!-- origen: old-hub:HUB_SHELL-F94 -->
Estado: parcial — un negocio que aún comparte su base de datos con otros no puede tener llaves: la pestaña dice «Todavía no disponible»
Actor: propietario, administrador
Pantalla: Empleados · API keys
Pasos:
  1. En **Empleados › API keys**: «Una llave deja que otro sistema (el de tu gestoría, tu tienda online) lea o
     escriba datos de este negocio por su API.» y «Nueva API key».
  2. En «Nueva API key», el «Nombre» («Gestoría — facturas»), las «Peticiones por minuto» («De 1 a 10.000.») y
     «Qué puede hacer esta key»: «Acceso total», «Solo lectura», «Solo escritura» o «Por app», marcando en cada app
     «Lectura» y «Escritura».
  3. Pulsa «Crear key»: sale «API key creada» con «Copia el token ahora», «Este es el único momento en que se
     muestra el secreto completo. Guárdalo en un lugar seguro: no se volverá a mostrar.» y «Copiar» (dos segundos
     dice «Copiado»). «Hecho» la cierra.
Entra: el nombre, el ritmo y lo que puede hacer.
Sale: la llave, de la que el negocio solo guarda lo que permite reconocerla. Evento `base.api_key.created`.
Si falla: «No se pudo crear la API key.», «Elige al menos una app y qué puede hacer la key en ella.», «Esa app no
publica lo que la key haría en ella.» o «No se pudo copiar al portapapeles.».
Implicados: BASE-F89, BASE-F90

### BASE-F87 Rotar una llave de API
<!-- origen: old-hub:HUB_SHELL-F95 -->
Estado: parcial — un negocio que aún comparte su base de datos con otros no puede tener llaves
Actor: propietario, administrador
Pantalla: Empleados · API keys
Pasos:
  1. En la fila de la llave, «Rotar».
  2. «Rotar la API key» con ««{name}» recibe un token nuevo. El actual deja de funcionar de inmediato.»; confirma con
     «Rotar».
  3. Sale el token nuevo, una sola vez, con «Copiar».
Entra: la llave.
Sale: la llave con un token nuevo; el anterior deja de abrir nada al momento. Evento `base.api_key.rotated`.
Si falla: «No se pudo rotar la API key.», «Esa key está revocada: no vuelve a funcionar.» o «Esa key ya no existe.
Actualiza la lista y vuelve a intentarlo.».
Implicados: BASE-F86, BASE-F89

### BASE-F88 Revocar una llave de API
<!-- origen: old-hub:HUB_SHELL-F96 -->
Estado: parcial — un negocio que aún comparte su base de datos con otros no puede tener llaves
Actor: propietario, administrador
Pantalla: Empleados · API keys
Pasos:
  1. En la fila de la llave, «Revocar».
  2. «Revocar API key» con «Vas a revocar «{name}». Cualquier sistema que use este token dejará de tener acceso de
     inmediato. Esta acción no se puede deshacer.»; confirma con «Revocar».
  3. Sale ««{name}» revocada.» y la fila queda como «Revocada», sin «Rotar» ni «Revocar».
Entra: la llave.
Sale: la llave revocada para siempre; se guarda en la lista. Evento `base.api_key.revoked`.
Si falla: «No se pudo revocar la API key.».
Implicados: BASE-F89

### BASE-F89 Ver las llaves de API y qué puede cada una
<!-- origen: old-hub:HUB_SHELL-F97 -->
Estado: parcial — un negocio que aún comparte su base de datos con otros no puede tener llaves: en su lugar sale «Todavía no disponible» y «Las API keys todavía no están disponibles en este negocio.»
Actor: propietario, administrador
Pantalla: Empleados · API keys
Pasos:
  1. En **Empleados › API keys** (la pestaña solo existe para quien administra), una fila por llave: «Nombre»,
     «Token» (solo su principio), «Permisos», «Estado» («Activa» o «Revocada»), «Creada», «Último uso» («Nunca» si
     no se ha usado) y «Límite».
  2. Busca con «Buscar API key…». Al pie, «Documentación de la API» lleva a la documentación.
Entra: las llaves del negocio.
Sale: nada guardado. Se pone al día sola al crear, rotar o revocar una.
Si falla: «No se pudieron cargar tus API keys.» con «Reintentar»; sin ninguna, «Aún no hay API keys. Crea una para
que un sistema externo pueda leer o escribir datos de tu negocio.».
Implicados: BASE-F86, BASE-F87, BASE-F88

### BASE-F90 Consultar la documentación de la API
<!-- origen: old-hub:HUB_SHELL-F98 -->
Estado: hecho
Actor: propietario, administrador, encargado, empleado
Pantalla: Documentación de la API
Pasos:
  1. Con la documentación mostrada (BASE-F91), se abre desde «API» en el menú lateral, desde **Ajustes › General**
     («Abrir la documentación de la API») o desde **Empleados › API keys** («Documentación de la API»).
  2. Lee «La API de este negocio: lo que publican sus apps para otros sistemas. Para llamarla, crea una llave en
     Empleados › API keys y envíala como «Authorization: Bearer <llave>».».
  3. Una sección por app, con sus llamadas (el método, la dirección y qué hace); al abrir una, sus «Parámetros» y su
     «Cuerpo».
  4. «Descargar el fichero OpenAPI» la guarda para llevarla a otra herramienta.
Entra: lo que publican las apps del negocio.
Sale: nada guardado. Crece o mengua con las apps del negocio.
Si falla: oculta, «La documentación de la API está oculta en este negocio.» y, para quien administra, «Muéstrala en
Ajustes › General»; si no llega, «No se pudo cargar la documentación.» con «Reintentar»; sin nada publicado,
«Ninguna app de este negocio publica todavía su API.». Si el negocio aún no puede tener llaves: «Las API keys
todavía no están disponibles para este negocio: puedes leer la documentación, pero aún ningún sistema puede
llamarla.».
Implicados: BASE-F91, BASE-F86

### BASE-F91 Mostrar u ocultar la documentación de la API
<!-- origen: old-hub:HUB_SHELL-F161 -->
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · General
Pasos:
  1. En **Ajustes › General**, en «Documentación de la API», el interruptor «Mostrar documentación de la API»
     («Añade una página con la documentación de la API, para quien conecte otro sistema.»). Viene apagado.
  2. Al encenderlo se guarda al instante y salen «Abrir la documentación de la API» y, en el menú lateral, «API»
     (entre «Sistema» y «Ajustes»), sin recargar; al apagarlo, desaparecen los dos.
Entra: el interruptor.
Sale: el ajuste del negocio. Evento `base.api_doc.settings_changed`.
Si falla: «No se pudo guardar el cambio.» y el interruptor vuelve a lo guardado; «No se pudo cargar el ajuste.» con
«Reintentar». A quien no administra le sale apagado: «Solo quien administra el negocio puede cambiarlo.».
Implicados: BASE-F90

En las pantallas de Empleados y en la Documentación de la API:

| Estado | Qué ve la persona |
|---|---|
| Cargando | La tabla en gris en «Personal», «Roles», «API keys» y «Aprobaciones»; «Cargando…» en la ficha de una persona; las caras en gris en «Hace falta una aprobación»; «Cargando la documentación…». |
| Vacío | «Todavía no hay nadie en este negocio.», «Aún no hay API keys. Crea una para que un sistema externo pueda leer o escribir datos de tu negocio.», «Todavía nadie ha tenido que autorizar nada en este negocio.», «Aquí nadie puede aprobarlo con un PIN. Quien pueda hacerlo puede pasar su placa.» y «Ninguna app de este negocio publica todavía su API.». |
| Error | «No se pudo cargar el personal de este negocio.», «No se pudo cargar el catálogo de roles.», «No se pudieron cargar tus API keys.», «No se pudo cargar el registro de aprobaciones.», «No se pudo abrir a esta persona.», «No se pudo cargar quién puede aprobarlo.» y «No se pudo cargar la documentación.», cada uno con «Reintentar»; nunca la lista vacía. |
| Sin permiso | Quien no administra no tiene las pestañas «API keys» ni «Aprobaciones» (su dirección abre «Personal»), no ve el email de nadie ni abre la ficha de una persona; en Ajustes, «Solo quien administra el negocio puede cambiarlo.». Con la documentación oculta: «La documentación de la API está oculta en este negocio.». |

### BASE-F92 Abrir y cerrar el panel del asistente
<!-- origen: old-hub:HUB_SHELL-F185 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Asistente
Pasos:
  1. Con la sesión abierta, pulsa los destellos «Asistente» de la barra de arriba, al lado de la campana. Volver a
     pulsarlos lo cierra. En un móvil, los destellos y la campana (y «erplora.com», para quien lo tiene) van juntos
     en «Más opciones» (con el número de la campana), para que el título siga centrado: ahí, «Asistente» abre el
     panel y «Notificaciones», la campana.
  2. El panel entra por la derecha. En una tableta o un ordenador ocupa una columna al lado de la pantalla y la
     empuja: se puede seguir trabajando con el panel abierto. En un móvil tapa la pantalla, sobre un velo oscuro.
  3. Se cierra con la × «Cerrar», con la tecla Esc (esté donde esté el cursor, salvo en una ventana abierta encima
     del panel), tocando el velo en el móvil, volviendo a pulsar los destellos o con «Ir a …» en una respuesta
     (BASE-F96).
  4. Si se deja abierto, sigue abierto al cambiar de pantalla y al recargar: el dispositivo recuerda solo si estaba
     abierto o cerrado.
Entra: la sesión.
Sale: al abrirlo, el panel lee los mensajes del asistente que le quedan al negocio este mes (BASE-F104) y la lista de
lo que falta por configurar, para sus atajos (BASE-F103); cerrarlo no pide nada.
Si falla: no tiene fallo propio. Sin sesión (la entrada, el PIN) no hay destellos. Cerrar el panel no corta una
respuesta que ya viene: sigue escribiéndose y, si pide confirmación, la tarjeta sale encima de la pantalla que haya
(BASE-F97).
Implicados: BASE-F93, BASE-F97, BASE-F103, BASE-F104

### BASE-F93 Preguntar al asistente y leer cómo escribe
<!-- origen: old-hub:HUB_SHELL-F186 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Asistente
Pasos:
  1. Con la conversación vacía, el panel enseña los destellos, «Pregúntame por tus ventas, tu inventario o cualquier
     cosa de tu negocio.» y los atajos de la puesta en marcha (BASE-F103).
  2. Escribe en «Escribe un mensaje…» y pulsa Intro o «Enviar». Con teclado, Mayús+Intro salta de línea; en una
     pantalla táctil, Intro salta de línea y se envía con «Enviar». «Enviar» no se activa con el cuadro vacío y sin
     adjuntos.
  3. Su mensaje sale a la derecha tal cual lo escribió. Debajo, la burbuja del asistente, con tres puntos que se
     mueven hasta que llega el primer texto.
  4. Mientras responde, «Enviar» se convierte en «Detener», «Adjuntar archivo» y «Dictar por voz» se apagan y la
     respuesta va apareciendo; la conversación baja sola hasta el final. Se puede ir escribiendo la siguiente
     pregunta, pero no se envía hasta que acaba esta.
  5. Si el asistente acaba sin decir nada, la burbuja dice «(sin respuesta)».
  6. «Detener» corta lo que faltaba: lo ya escrito se queda, con «Detenido.» debajo.
  7. Bajo cada respuesta terminada, «Leer en voz alta» la lee con la voz del propio dispositivo, si la tiene, y
     «Dejar de leer» la para.
Entra: lo que escribe la persona; la conversación entera viaja con cada pregunta (BASE-F102).
Sale: la pregunta a erplora.com, que la responde y la cuenta en los mensajes del mes (BASE-F104).
Si falla: sin conexión, con el servicio caído, sin plan o sin mensajes: BASE-F106 y BASE-F104. «Detener» no deshace
una acción que ya se había hecho.
Implicados: BASE-F102, BASE-F104, BASE-F106

### BASE-F94 Adjuntar un archivo o dictar por voz
<!-- origen: old-hub:HUB_SHELL-F187 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Asistente
Pasos:
  1. Para adjuntar, pulsa «Adjuntar archivo» y elige uno o varios: imágenes, PDF, Word, Excel, texto o CSV. Cada uno
     sale sobre el cuadro con su nombre y su × «Quitar adjunto».
  2. Se envían con el siguiente mensaje, con texto o sin él, y en la burbuja de la persona quedan con su nombre.
     Viajan una sola vez, con esa pregunta: después la conversación solo recuerda cómo se llamaban.
  3. Para dictar, pulsa «Dictar por voz» (solo sale si el dispositivo puede grabar). El navegador (en la app
     instalada, el dispositivo) pide permiso para el micrófono; mientras lo pide, otra pulsación no abre una segunda
     grabación. Mientras graba, el botón se pone rojo y se llama «Detener la grabación»; a los dos minutos para solo.
  4. Al parar sale «Transcribiendo…» y el texto cae en el cuadro, detrás de lo que hubiera escrito. **No se envía
     solo**: la persona lo revisa y pulsa «Enviar», y lo que pida pasa por su tarjeta como cualquier otra petición
     (BASE-F97).
Entra: los archivos (8 MB cada uno y 20 MB entre todos los de una pregunta) o la grabación.
Sale: el archivo viaja con la pregunta a erplora.com, que lo lee; la grabación pasa por el negocio a la
transcripción de erplora.com. El navegador nunca habla directamente con erplora.com.
Si falla: en una línea sobre el cuadro, y el archivo no se adjunta: «menu.pdf es demasiado grande: 8 MB como mucho
por archivo.», «Los archivos de una pregunta suman 20 MB como mucho.», «menu.zip no se puede adjuntar: imágenes,
PDF, Word, Excel, texto o CSV.» o «No se ha podido leer menu.pdf.». Con el micrófono denegado, «El acceso al
micrófono está denegado. Permítelo en tu navegador para dictar.» y, en la app instalada (Android o Windows), donde
no hay navegador, «El acceso al micrófono está denegado. Permítelo en los ajustes del dispositivo para dictar.»; una
grabación demasiado larga, «La grabación es demasiado larga: dicta un mensaje más corto.»; sin voz, «No se ha oído
nada. Inténtalo de nuevo más cerca del micrófono.»; y si no se puede transcribir, «No se ha podido transcribir el
audio. Inténtalo de nuevo.».
Implicados: BASE-F93, BASE-F97

### BASE-F95 Leer la respuesta: texto, listas, tablas y enlaces
<!-- origen: old-hub:HUB_SHELL-F188 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Asistente
Pasos:
  1. La respuesta se pinta con formato: negrita, cursiva, código, encabezados, listas con viñetas o numeradas y
     tablas.
  2. Una tabla cabe en la burbuja: sus celdas parten el texto en lugar de ensanchar el panel, también en un móvil.
  3. Un enlace se lee por su texto, sin corchetes ni dirección. Solo se puede pulsar si lleva a una pantalla de este
     negocio (BASE-F96); cualquier otra dirección, de fuera o inventada, se queda como texto.
  4. Lo que el panel no entiende (bloques de código, imágenes, citas) se queda como texto corriente. El mensaje de la
     persona sale siempre tal cual lo escribió.
Entra: el texto del asistente.
Sale: nada; solo se pinta. El panel nunca pinta HTML que venga en una respuesta.
Si falla: una respuesta mal escrita se lee como texto: nunca se pierde ni rompe el panel.
Implicados: BASE-F96

### BASE-F96 Ir a una pantalla desde una respuesta
<!-- origen: old-hub:HUB_SHELL-F189 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Asistente
Pasos:
  1. Si la respuesta nombra una pantalla de este negocio, bajo la burbuja sale «Ir a …» con su nombre (hasta cuatro,
     sin repetir) y la propia mención se puede pulsar.
  2. Puede llevar al Inicio, a Empleados, a Apps, a Ajustes, a Mi perfil, a Archivos (a quien los ve), a Sistema (a
     quien administra) y a las pantallas del menú de cada app encendida.
  3. El botón usa el nombre que la persona ve en el menú («Ir a Ajustes», «Ir a Inicio» y, para una app, su nombre y
     el de la pantalla), nunca la dirección.
  4. Al pulsarlo se abre esa pantalla y el panel se cierra para que se vea.
Entra: las pantallas que nombra la respuesta; las de este negocio y las de sus apps encendidas.
Sale: la pantalla abierta; no se pide nada.
Si falla: una pantalla que este negocio no tiene (la de una app apagada, una dirección inventada) no sale como botón
ni como enlace, y la respuesta lleva el aviso de BASE-F99. Si la persona no puede ver la pantalla a la que llega, se
lo dice esa pantalla.
Implicados: BASE-F92, BASE-F99

### BASE-F97 Confirmar una acción antes de que se ejecute
<!-- origen: old-hub:HUB_SHELL-F190 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Tarjeta de confirmación del asistente
Pasos:
  1. La persona le pide algo que cambia datos («crea el servicio Corte a 15 € de 30 minutos»).
  2. Antes de hacerlo sale, encima de todo, «¿Ejecutar esta acción?» con la acción, la app y sus primeros datos en una
     línea, por ejemplo «Crear en Servicios: Corte · 15,00 € · 30». Un importe sale en la moneda del negocio (nunca en
     céntimos), salvo uno de «Lo que va a pasar» que su app da en otra moneda, que sale en la suya: rectificar una
     factura emitida en euros dice «Total: -121,00 €» aunque el negocio cobre ya en złoty, y el asistente lo dice en
     la misma moneda en su respuesta. Una diferencia sale con su signo como en la pantalla de su app, para ver de un
     vistazo si sobra o falta (el cierre de caja dice «Diferencia: +137,90 €» si sobra, «-4,90 €» si falta y sin signo si cuadra); un sí o un no, como «Sí» o «No»;
     una lista, por cuántos elementos lleva, y un dato que agrupa otros, como la plantilla de un WhatsApp, por sus
     valores, sin el nombre de cada uno («Plantilla: cita_recordatorio · es · Ana, 10:00»; del recuento de una caja
     quedan los billetes y monedas contados: «50: 2»). Una fecha y una hora salen como se escriben en el idioma
     de la persona y a la hora del negocio («2 nov 2026, 10:00»; un día solo, «2 nov 2026»; una hora sola,
     «21:30»); un valor de una lista cerrada, con el nombre que le da su app («Mostrador», no el valor interno); y
     un registro, por su nombre cuando su app deja leerlo a quien pregunta («Persona: Eva Gil»): si no, la tarjeta
     no lo pone, nunca por su código. Todo sale en el idioma de la persona, también el nombre de cada dato
     cuando la tarjeta lo pone en su línea (BASE-F98): el mismo con que lo llama su app, nunca un nombre
     técnico. Una acción de la propia plataforma se nombra por la pantalla donde se hace, por ejemplo «Cambiar en
     Ajustes» o «Borrar en Archivos». Cada acción sale con su propio verbo, nunca con uno genérico: rectificar una
     factura dice «Rectificar en Facturación».
  3. «Ejecutar» lo hace con la sesión de quien preguntó, con los mismos permisos y las mismas comprobaciones que el
     botón de su pantalla. «Cancelar» o Esc no hacen nada: el asistente sabe que no se confirmó y lo dice.
  4. Lo que solo lee (ver las ventas, buscar un cliente) no pide tarjeta; cada acción que cambia algo pide la suya.
  5. Bajo la respuesta queda el recibo de cada acción del turno, con la acción nombrada como en su tarjeta: «Hecho:
     Crear en Servicios», o «No se hizo, cancelado: …», «No se hizo, falló: …» y «No se hizo, sin permiso: …». Si la
     persona cambia de idioma, los recibos de antes salen enteros en el nuevo, también el nombre de la app.
Entra: la acción, sus datos y su riesgo, tal como los declara su app; la moneda del negocio y, en «Lo que va a pasar»,
la que dé su app; la zona horaria del negocio.
Sale: si se acepta, la acción hecha en su app, con el mismo evento que si se hubiera pulsado su botón.
Si falla: una acción que su app rechaza vuelve al asistente como error y él lo cuenta; el recibo dice «No se hizo,
falló: …». Si se recarga la página con la tarjeta abierta no se hace nada, y la respuesta acaba en «La respuesta se
cortó.» con «Reintentar».
Implicados: BASE-F98, BASE-F99, BASE-F101

### BASE-F98 Acciones peligrosas: escribir para confirmar, o no desde el chat
<!-- origen: old-hub:HUB_SHELL-F191 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Tarjeta de confirmación del asistente
Pasos:
  1. Una acción que su app marca como peligrosa no se confirma con un clic: la tarjeta dice, por ejemplo, «Borrar en
     Servicios. Revisa cada dato antes de seguir.», pone cada dato en su línea con su nombre en el idioma de la
     persona y pide «Para confirmar, escribe CONFIRMAR:».
  2. Si su app lo declara, la tarjeta dice antes, bajo «Lo que va a pasar», lo que la acción va a hacer, tal como su
     app lo calcula para quien pregunta y con sus permisos. Por ejemplo, al quitar el PIN a alguien sale de quién es
     («Nombre: …» y «Correo: …»), no solo el código de la persona. Lo que la app no le enseña a esa persona tampoco
     sale en la tarjeta.
  3. Si la acción nombra los registros uno a uno, dice cuántos («Afecta a 3 registros.») y pide escribir ese número
     en lugar de la palabra.
  4. Si no los nombra (todos, o los que cumplen un filtro), no se hace desde el chat: no sale tarjeta, la respuesta dice «No puedo
     saber cuántos registros cambiaría esto, así que no lo hago desde aquí. Ábrelo en su pantalla, donde puedes
     verlos.» y el asistente explica dónde se hace.
  5. «Ejecutar» solo se puede pulsar cuando lo escrito coincide (sin importar las mayúsculas ni los espacios de los
     extremos), y el negocio lo vuelve a comprobar antes de hacerlo.
  6. Restablecer el negocio y exportar una copia nunca se hacen desde el chat: se hacen en Ajustes › Datos y copias.
Entra: el riesgo que la app declara en cada acción y sus datos; si la declara, su vista previa.
Sale: si se acepta, como BASE-F97.
Si falla: lo escrito que no coincide no deja ejecutar; cancelar no hace nada y el asistente lo cuenta como cancelado.
Si la vista previa no se puede leer (el registro ya no está, o la persona no puede verlo), no sale la tarjeta ni se
hace nada: nada se confirma a ciegas. El recibo dice «No se hizo, falló: …» o «No se hizo, sin permiso: …» y el
asistente cuenta por qué.
Implicados: BASE-F35, BASE-F37, BASE-F97

### BASE-F99 Comprobar lo que dice el asistente contra lo que de verdad hizo
<!-- origen: old-hub:HUB_SHELL-F192 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Asistente
Pasos:
  1. Al acabar cada respuesta, el panel la compara con lo que de verdad se hizo en ese turno: no se fía de lo que la
     respuesta dice de sí misma.
  2. Si dice que cambió algo («he creado…», «se ha guardado…», «has been updated…») y en el turno no se hizo ninguna
     acción (o se canceló, falló o no tenía permiso), sale, fuera de la burbuja, «El asistente ha dicho que hizo un
     cambio, pero no se ejecutó ninguna acción. No se ha modificado nada.».
  3. Si escribe un identificador que ninguna consulta del turno devolvió y que la persona no escribió: «Esta
     respuesta muestra un identificador que el asistente no ha leído de verdad. No te fíes de él.».
  4. Si señala una pantalla que este negocio no tiene: «Esta respuesta señala una pantalla que no existe aquí.», y
     sin «Ir a …» (BASE-F96).
  5. Los avisos llevan su icono de alerta, no los escribe el asistente y se quedan con el mensaje, también al
     recargar. Una respuesta limpia no lleva ninguno.
  6. Los recibos de BASE-F97 dicen qué se hizo de verdad, acción por acción.
Entra: lo que se hizo en el turno, con su resultado, y lo que devolvieron sus consultas.
Sale: los avisos y los recibos, guardados con la conversación.
Si falla: «Hecho» quiere decir que la acción de su app acabó sin error: si una app responde bien sin haber cambiado
nada, es esa acción la que tiene que decirlo. Si el turno acaba en error, la burbuja lleva su fallo (BASE-F106), los
avisos de lo que llegó a decir y los recibos de lo que sí se hizo.
Implicados: BASE-F96, BASE-F97, BASE-F106

### BASE-F100 Lo que el asistente puede hacer según quién pregunta: permisos y PIN de un responsable
<!-- origen: old-hub:HUB_SHELL-F193 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Asistente
Pasos:
  1. El asistente trabaja con la sesión de quien está delante: ve y hace lo que esa persona vería y haría con sus
     botones, en las apps encendidas del negocio, y nada más. Una acción para la que no tiene permiso no se le ofrece
     al asistente, que así se lo dice; la que su app deja aprobar a un responsable sí, igual que su botón en la
     pantalla.
  2. Esa acción sale con su tarjeta, como cualquier otra. Al pulsar «Ejecutar» se abre «Hace falta una aprobación», la
     misma de la pantalla: un responsable toca su cara y teclea su PIN, o pasa su placa, y la acción se hace una vez,
     con quien la pidió como autor. Queda anotada en **Empleados › Aprobaciones**.
  3. Si nadie la aprueba («Cancelar»), no se hace: el recibo dice «No se hizo, cancelado: …» y el asistente lo sabe.
  4. Si aun así intenta una acción sin permiso que nadie puede aprobar, no se hace: el recibo dice «No se hizo, sin
     permiso: …» y el asistente explica que no puede.
  5. Lo que el asistente cuenta (listas, cifras) es lo que esa persona puede leer.
Entra: la sesión de quien pregunta, que firma cada acción; para lo que aprueba un responsable, su PIN o su placa.
Sale: la acción hecha con esa persona como autora. La aprobación vale para esa acción de esa conversación, una sola
vez y durante dos minutos, y se gasta junto con la acción (BASE-F84).
Si falla: si el permiso se pierde entre ofrecer la acción y hacerla, su app la rechaza y el recibo lo dice. Una
aprobación ya usada o caducada no deja pasar la acción: el recibo dice «No se hizo, falló: …» y el asistente lo
cuenta.
Implicados: BASE-F13, BASE-F84, BASE-F97

### BASE-F101 Pedirle varias cosas seguidas
<!-- origen: old-hub:HUB_SHELL-F194 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Asistente
Pasos:
  1. La persona pide una cadena («crea la categoría Bebidas y el producto Caña a 2,50 €»).
  2. El asistente la resuelve por rondas: lee lo que necesita sin preguntar, pide una acción, se hace y sigue. Todo lo
     que dice va a la misma burbuja, y lo de cada ronda en su propio párrafo: nunca pegado a lo de la anterior.
  3. Cada acción que cambia algo pide su propia tarjeta (BASE-F97), una detrás de otra: aceptar la primera no acepta
     las siguientes. Si detrás esperan más, la tarjeta lleva «Cancelar todo», que cancela esta y las que faltan.
  4. Si cancela una, el asistente lo sabe y decide cómo seguir. Lo ya hecho se queda hecho.
  5. Una petición admite como mucho seis rondas: es un freno contra los bucles, no un cupo. Pasadas, «He parado: esto
     necesitaba demasiados pasos. Pídelo por partes.».
Entra: la petición; el resultado de cada acción, que vuelve al asistente.
Sale: tantas acciones como tarjetas aceptadas, cada una en su app y con su recibo.
Si falla: si una acción falla a mitad, el asistente lo recibe y lo cuenta; las anteriores no se deshacen. Con la red
cortada a mitad, BASE-F106.
Implicados: BASE-F97, BASE-F106

### BASE-F102 La conversación: qué se guarda, dónde y cuándo se borra
<!-- origen: old-hub:HUB_SHELL-F195 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Asistente
Pasos:
  1. La conversación vive solo en esa pestaña del navegador: el negocio no la guarda. Recargar la página la recupera;
     cerrar la pestaña la pierde. Cerrar el panel no la borra.
  2. Una respuesta que se estaba escribiendo al recargar se queda con lo que había llegado y «La respuesta se
     cortó.», con «Reintentar».
  3. «Nueva conversación», arriba del panel, la vacía y empieza de cero.
  4. Al cerrar sesión (también cuando la caja se cierra sola por inactividad) se borra, y se corta la respuesta que
     estuviera llegando. Al cambiar de usuario con PIN, la de quien se fue se borra con lo que hubiera escrito sin
     enviar y sus adjuntos, y quien llega encuentra el panel cerrado y vacío.
  5. Se guarda lo que escribió la persona (de sus adjuntos, solo el nombre), lo que respondió el asistente, sus avisos
     y sus recibos.
Entra: los mensajes del panel; los cierres de sesión y los cambios de usuario.
Sale: nada fuera del navegador; con cada pregunta, la conversación entera viaja para responderla.
Si falla: si el navegador no deja guardar (modo privado, almacenamiento lleno), la conversación sigue mientras la
pestaña está abierta, pero no sobrevive a una recarga. Una guardada que no se puede leer, o de otra persona, empieza
vacía. Una conversación demasiado larga dice «Esta conversación es demasiado larga: empieza una nueva.» con «Nueva
conversación».
Implicados: BASE-F59, BASE-F60, BASE-F61

### BASE-F103 El asistente en la puesta en marcha
<!-- origen: old-hub:HUB_SHELL-F196 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Asistente
Pasos:
  1. En el Inicio, mientras falta algo, «Termina de configurar tu negocio» lleva «Pedírselo al asistente». Abre el
     panel con «Revisa la configuración de tu negocio. Elige una opción o escribe tu duda.».
  2. Abierto desde la barra, la conversación vacía ofrece los mismos atajos: «¿Qué falta por configurar?» y, por cada
     paso pendiente que esta persona puede hacer (hasta cuatro, en el orden de la lista), «¿Cómo configuro «Tu
     equipo»?», con el nombre del paso tal como sale en la lista. Los pasos que solo puede hacer un administrador y los
     «Todavía no disponible» no salen como atajo.
  3. Pulsar un atajo lo pregunta en el acto.
  4. Desde la puesta en marcha (el botón o un atajo), antes de cada pregunta el asistente vuelve a leer la lista: lo
     pendiente, lo que impide facturar, lo hecho y lo que le toca a un administrador. Un negocio que se configura a
     mitad de la charla deja de describirse como sin configurar.
  5. Lo que pida hacer (encender una app, cargar una plantilla) pasa por su tarjeta (BASE-F97).
Entra: la lista de lo que falta, con lo que esa persona puede ver (BASE-F01).
Sale: la lista, para el asistente; la conversación normal.
Si falla: si la lista no se puede leer, el asistente lo sabe y no dice que el negocio está configurado, y los atajos
se quedan en «¿Qué falta por configurar?». Cada paso sigue teniendo su «Configurar» en la lista: con el asistente
caído nadie se queda sin salida.
Implicados: BASE-F01, BASE-F12, BASE-F97

### BASE-F104 Ver el plan del asistente, el límite de uso y ampliarlo
<!-- origen: old-hub:HUB_SHELL-F197 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Asistente
Pasos:
  1. Al abrir el panel se leen los mensajes del asistente que le quedan al negocio este mes. Si no se pueden leer, no
     se enseña nada: nunca un número inventado.
  2. Desde el 80 %, el pie dice, por ejemplo, «Te quedan 30 de 300 mensajes este mes.» con «Se renuevan el 1 de
     noviembre.». Por debajo del 80 %, nada.
  3. La cuenta se mueve al terminar cada respuesta, sin recargar.
  4. Agotados, la respuesta es «Has usado todos los mensajes del asistente de este mes (300 de 300).» con «Se
     renuevan el 1 de noviembre.», y no un fallo de conexión. El pie dice lo mismo, sin repetir «Mejorar plan»:
     «Has usado los 300 mensajes de este mes.» con «Se renuevan el 1 de noviembre.»; también al abrir el panel con
     el mes ya gastado.
  5. Quien administra el negocio ve, en el navegador, «Mejorar plan», que abre en otra pestaña la página del plan
     en erplora.com; en la app instalada desde la tienda no sale. Quien no administra ve «Pídele a quien administra el
     negocio que mejore el plan.». No hay paquetes de mensajes: se amplía mejorando de plan.
  6. Con un plan sin asistente, el pie dice «Tu plan no incluye el asistente.», con «Mejorar plan» para quien
     administra; el panel se abre igual.
Entra: los mensajes usados, el límite y el día en que se renuevan, de erplora.com.
Sale: la página del plan de erplora.com, en otra pestaña. El negocio no lleva su propia cuenta de mensajes.
Si falla: si no se puede leer el plan, no se enseña nada y se puede preguntar igual: lo que diga erplora.com al
responder es lo que vale.
Implicados: BASE-F11, BASE-F106

### BASE-F105 Informar de una respuesta mala
<!-- origen: old-hub:HUB_SHELL-F198 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Asistente
Pasos:
  1. Bajo cada respuesta terminada sale «Denunciar un problema»; no en la que aún se escribe ni bajo un fallo sin
     respuesta, que no es del asistente.
  2. Se abre «Denunciar esta respuesta»: «Si esta respuesta del asistente te parece incorrecta o dañina, envíanosla y
     la revisaremos.», con «¿Qué le pasa?» («Es incorrecta», ya marcada; «Es dañina u ofensiva», «No hace lo que
     pedí» u «Otra cosa») y «Comentario (opcional)».
  3. «Denunciar» la envía con la pregunta que la provocó; «Cancelar» no manda nada.
  4. Sale «Gracias, hemos recibido tu denuncia.» y se cierra.
Entra: la respuesta, la pregunta, el motivo y el comentario.
Sale: la denuncia, para que el equipo de erplora.com la revise. Cualquier persona puede denunciar.
Si falla: «No se pudo enviar la denuncia. Inténtalo de nuevo.», y la ventana sigue abierta con lo elegido y lo
escrito.
Implicados: ninguno

### BASE-F106 El asistente sin conexión, con el servicio caído o sin plan
<!-- origen: old-hub:HUB_SHELL-F199 -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Asistente
Pasos:
  1. Sin Internet en el dispositivo, el pie dice «Sin conexión: puedes escribir y enviar cuando vuelva.» y «Enviar»
     se apaga hasta que vuelve.
  2. Si la pregunta no llega a erplora.com, la burbuja dice «No se pudo contactar con el asistente. Comprueba la
     conexión y vuelve a intentarlo.» con «Reintentar».
  3. Si erplora.com o su servicio fallan, «El asistente no está disponible ahora mismo. Vuelve a intentarlo en unos
     minutos.» con «Reintentar». Si la respuesta se corta a mitad, lo escrito se queda, con «La respuesta se cortó.»
     y «Reintentar».
  4. Con demasiadas preguntas seguidas, «Demasiadas preguntas seguidas: espera 60 segundos y vuelve a intentarlo.».
  5. Si la sesión termina a mitad de la charla, «Tu sesión ha terminado. Vuelve a entrar para seguir hablando.» con
     «Volver a entrar».
  6. Quedarse sin mensajes o tener un plan sin asistente no es una avería: BASE-F104.
  7. «Reintentar» vuelve a hacer la misma pregunta: nunca se pierde.
Entra: lo que pasó con la pregunta.
Sale: el fallo, en la burbuja y guardado con la conversación (BASE-F102); al asistente no le llega como si lo hubiera
dicho él.
Si falla: un fallo sin nada escrito no deja una burbuja vacía: solo la frase con su salida.
Implicados: BASE-F93, BASE-F102, BASE-F104

### BASE-F107 Pasar la QA maestra del Hub
<!-- origen: qa:shared/qa-hub -->
Estado: hecho
Actor: el equipo de QA de ERPlora
Pantalla: todas las de la plataforma del hub
Pasos:
  1. El equipo crea en erplora.com, con una cuenta nueva, un negocio de su tipo (un restaurante): el hub lo recibe
     con su sector y en «Datos y copias» le ofrece primero la plantilla de ese sector, que deja el negocio con su
     carta y sus mesas.
  2. Recorre la plataforma como su dueño, en el móvil, la tableta y el ordenador, en español y en inglés: el Inicio
     con «Resumen» y «Actividad», «Mis apps» y la campana; «Añadir apps» y las pestañas de Apps («De pago» no sale
     mientras ninguna app se contrate aparte); las pestañas de Ajustes y las secciones de «Datos y copias»; Empleados, la ficha de una persona, los roles, las llaves y las
     aprobaciones; las cinco pestañas de Sistema; Archivos; «Mi perfil»; una dirección que no existe; y el
     asistente, que se abre y contesta.
  3. En cada pantalla comprueba que carga sin error, que nada se sale por un lado y que no queda ningún texto en el
     otro idioma ni sin traducir.
  4. El día de un restaurante o de una peluquería (abrir la caja, sentar o dar cita, pedir, cocinar, cobrar con el
     tique firmado para la AEAT, imprimir y cerrar la caja) lo prueban las apps que lo hacen, cada una con sus flujos.
Entra: un negocio nuevo creado en erplora.com y sus cuentas de prueba.
Sale: cada pantalla de la plataforma vista y comprobada en los dos idiomas y los tres tamaños.
Si falla: lo que falla en una pantalla es un fallo de la app que la tiene y se arregla allí; si erplora.com no tiene
todavía los tipos de negocio o el asistente de pruebas, la QA no empieza y dice cuál falta.
Implicados: HUBS-F01, BASE-F05, BASE-F14, BASE-F29, BASE-F38, BASE-F39, BASE-F48, BASE-F92

### BASE-F108 Reportar un problema a soporte
<!-- origen: nuevo (Ioan, 2026-10-25: «Reportar un problema» del menú de usuario en una ventana del hub, sin salir a la página de erplora.com de ACCOUNTS-F38) -->
Estado: hecho
Actor: propietario, administrador, responsable, empleado (quien entró con su cuenta de erplora.com)
Pantalla: El menú de usuario
Pasos:
  1. En el menú de usuario, «Reportar un problema». Solo sale si se entró con la cuenta: nunca en una sesión de PIN
     de una caja compartida, que no tiene una cuenta a la que responder.
  2. Se abre «Reportar un problema» en una ventana, sin salir del hub: «Cuéntanos qué ha fallado. Te responderemos
     por correo electrónico.», con «Asunto» y «¿Qué pasó?» («Describe los pasos y lo que esperabas que pasara») y,
     debajo, «Con tu informe van tu cuenta, tus negocios, la página de la que vienes y tu navegador.».
  3. «Enviar informe» espera a que los dos estén escritos; mientras se envía, la ventana no se cierra ni se envía
     dos veces.
  4. Sale «Informe enviado», con el correo al que soporte responderá, y «Cerrar».
  5. «Cancelar» o cerrar la ventana no manda nada, y lo escrito sigue ahí si se vuelve a abrir.
Entra: el asunto y lo que pasó.
Sale: un correo al buzón de soporte de erplora.com con el asunto, el texto y, debajo, la cuenta, sus negocios, este
negocio, la pantalla en la que estaba y su navegador; soporte contesta al correo de la cuenta (ACCOUNTS-F38). El hub
no guarda nada.
Si falla: tras cinco informes en una hora (los del hub y los de erplora.com juntos), «Demasiados intentos. Vuelve a
intentarlo en unos minutos.»; si erplora.com no responde o no puede enviarlo, un aviso con la dirección de soporte
para escribir directamente. En los dos casos lo escrito se queda y se puede volver a enviar.
Implicados: ACCOUNTS-F38

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
- Campana por reloj (FIX-HUB-BASE-PRINT-BELL-IGNORES-DEVICE-PRESENCE): un contador cuya cifra cambia porque pasa el
  tiempo, sin evento (un trabajo que lleva un minuto en cola sin dispositivo vivo), lo dice su módulo en
  `bell_refresh_every` de su `LiveAppConfig` (clave del contador → segundos; la forma de `scheduled_tasks` y
  `approvals`, que también lee y comprueba `base`). `base.E007` (`base/home.py`) exige claves de su propio `bell` y
  segundos enteros desde `MIN_BELL_REFRESH_SECONDS` (30, el ritmo de la campana vieja). `base.bell.counters` devuelve
  `refresh_every`, el menor de los contadores que la persona puede ver de las apps encendidas (también a cero: es el
  tiempo el que los sube), y `HubBell.vue` vuelve a leer `GET /api/home/bell` cada tantos segundos mientras la página
  está a la vista; una lectura más vieja que un resultado vivo llegado mientras tanto se descarta, y una que falla deja
  lo último. Sin `refresh_every`, la campana solo se mueve por eventos, como antes. Tests: `test_home.py`,
  `test_queries_home.py` y `HubBell.test.ts`.
- Presencia del dispositivo que imprime (misma tarea; el `heartbeat` de `print_hosts.rs` del hub viejo): la app que
  lleva los dispositivos declara en su `LiveAppConfig` `print_presence`, el nombre de una orden suya cuya entrada lleva
  `device`; `/ws/print` (`base/ws_print.py`) la ejecuta con el contexto del dispositivo en su `hello` y en cada `beat`
  mientras imprime para alguna impresora, como mucho una vez cada `PRESENCE_SECONDS` (15 s, medio latido). Si falla,
  se anota en el log y el socket sigue (contesta el latido y sigue sacando trabajos). `base.E006` comprueba al arrancar
  que es una orden de la propia app, con `device`, y que solo una app la declara. Sin declarar, el socket no avisa a
  nadie. Tests: `base/tests/test_ws_print.py` (sección «The device's presence»).
- Un panel con `operation` viva (está en un `live.py`) se sigue con `useLive`; si no, se pide una vez
  (`live` en `WidgetOut`). Un panel con `component` monta `apps/<app>/frontend/components/<Nombre>.vue`.
- Un panel `chart` cuyas etiquetas son días (`YYYY-MM-DD`: día civil de negocio, sin zona) los nombra con
  `Intl` en UTC, nunca con `new Date(<día>)` en la zona del navegador (`isoDay` y `formatDay` de
  `base/frontend/lib/home.ts`): una semana, por su día de la semana corto (`vie`); una serie más larga, por su
  fecha (`17 oct`); una etiqueta que no es un día se queda tal cual. Encima de las barras salen el día entero y el
  importe (`options.format`) de la barra elegida: la última hasta que se toca o enfoca otra (gh:hub#2392 del hub
  viejo; `tests/e2e/fix-hub-home-chart-iso-day-labels.spec.ts`).
- Un panel `bar-list` cuyo `map` declara `color` pinta cada barra con el color de su fila (`renderBarList` del hub
  viejo: `color: row[map.color]`), solo si es un hex `#rgb` o `#rrggbb` (`HEX_COLOR` de `base/frontend/lib/home.ts`):
  lo teclea una persona y va al estilo de la barra, así que cualquier otra cosa (un nombre CSS, `var(…)`, `url(…)`)
  pinta como sin `map.color`. Una barra negativa no lleva color: su rojo gana, porque una alarma pesa más que la
  categoría (las barras de datos de Excel con su relleno de negativo, el formato condicional de Power BI sobre los
  colores de categoría, los umbrales de Grafana sobre su color fijo; FIX-HUB-BASE-HOME-BAR-LIST-IGNORES-MAP-COLOR).
  Un color claro casi no se ve sobre la pista gris: el contraste es el del color que eligió quien lo tecleó. Un
  `chart` no pinta `map.color` (el hub viejo tampoco).
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
  `SAAS_URL/dashboard/store/plans?business=<id del hub>`) y `widget-list`, `base.widget.list` tal como su consulta viva se lo
  contesta a la persona (sin el permiso del Inicio no va): `WidgetBoard.vue` monta sus paneles con él, así que los
  datos de los paneles van en el mismo flujo vivo que la lista y el Inicio abre un solo `/api/live` por carga
  (antes lo reabría al llegar la lista, `net::ERR_ABORTED`, con cada consulta dos veces); manda la respuesta viva.
  Lo comprueban `test_the_shell_embeds_the_persons_panels_so_the_home_opens_one_live_stream` y
  `tests/e2e/base-home.spec.ts` («one live stream»).
- La SPA responde toda ruta sin URL propia en Django, salvo la que nombra un fichero (`base.spa.NOT_A_FILE`: el
  último segmento lleva extensión, con barra final o sin ella, como `/robots.txt`, `/favicon.ico` o
  `/wp-login.php`): esa no es ruta de la SPA (`spa_route` en `config/urls.py`) y recibe el 404 llano de Django, sin
  la SPA y sin cookie, con sesión o sin ella y acepte lo que acepte (FIX-HUB-SPA-STATIC-PROBES-SET-CSRF-COOKIE). Antes
  recibía la SPA con 200 y `csrftoken`: la web pública perdía el «sin cookies» y un buscador leía HTML como
  `robots.txt`. Un 404 en `robots.txt` es «sin reglas» (RFC 9309), así que la web de `/` sigue indexable. Es la regla
  del punto de connect-history-api-fallback y de `{*path:nonfile}` de ASP.NET Core; ninguna ruta de la SPA lleva
  punto (sus parámetros son ids). Una navegación (sin extensión) sigue igual: con sesión, la SPA y su `csrftoken`;
  sin sesión y pidiendo HTML, el salto al login del SaaS; sin pedir HTML, la SPA; `/` con web publicada, la web
  (`base/tests/test_spa.py`, `test_public_home.py`; e2e `tests/e2e/fix-hub-spa-static-probes.spec.ts`). Ese salto
  es una página propia (`base/templates/base/jump.html`, `base.auth_views.jump_page`, 200 sin caché) y no un 302: el
  navegador nunca manda al servidor lo que va tras `#`, y la vuelta por erplora.com (un POST a `/auth/callback`) lo
  perdía, así que su único script, con el nonce de la CSP, va a `/auth/login?next=<ruta>` con el `#` dentro del
  `next`, y `/auth/login` salta con su `state` nuevo; sin scripts, `<noscript>` lo hace sin el `#`. El Acceso
  (`/login`) sigue siendo un 302 de la misma petición: el navegador conserva el `#` en un salto del mismo origen
  (`nextWithHash` de `base/frontend/lib/access.ts` lo junta al `next`) y el aviso de la sesión terminada se calcula
  antes de que el middleware de sesiones borre su cookie (`base/tests/test_middleware.py`, `test_access_entry.py`;
  e2e `tests/e2e/base-deep-link.spec.ts` y BASE-G58 de `base-access.spec.ts`). Como
  `/favicon.ico` es un 404, la SPA declara los iconos del hub viejo, el de la pestaña y el de la pantalla de inicio
  (`LIVE["spa"]["icons"]` de `live.spa`, estáticos de `base` en `base/static/base/icons/`; nunca por CDN).
- Navegador: el tablero se guarda en `localStorage["dashboard-hub"]` (la clave del viejo) y el uso de
  apps en `localStorage["hub-app-usage"]`. La pestaña «Actividad» es el hash `#actividad`.
- Frontend en `base/frontend/` (rutas, catálogos `en`/`es` bajo `base`, componentes y su `lib/home.ts`);
  la campana, «Mejorar plan» y la franja se enchufan en `frontend/main.ts` por `chrome` de
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
- Plantillas y Ajustes › Datos (BASE-F29–F38, APP-BASE-2): `base/blueprint.py` (sin ORM) tiene el formato
  `.blueprint.zip` (`manifest.json` con `format` `erplora.blueprint` y `format_version` 1, más
  `data/<app>.<parte>.json`; 5 MB, 50 MB al descomprimir y 200 entradas como mucho; `BlueprintInvalid.reason`),
  el catálogo (`base/seeds/<vertical>.<idioma>.json`, sus apps = `catalog.template_apps(vertical)`) y las siete
  partes que viajan (`inventory.category`, `inventory.product`, `service.category`, `service.service`, `table.zone`,
  `table.table` y `customer.customer`, personal: solo en una copia), cada una leída y escrita por las operaciones
  de su app (nunca su ORM; las filas se enlazan por nombre, gh:hub#2626). Lo que ya existe se salta.
- Operaciones (permiso `base.administer_hub`, ruta en `base/api.py` bajo `/api/settings/data/`): consultas
  `base.blueprint.list` (con `empty`, viva), `base.blueprint.export` (GET, el fichero en base64),
  `base.import.list` (con `unfinished`, viva) y `base.dataset.list`; órdenes `base.blueprint.inspect` (no escribe;
  orden porque su entrada es un fichero), `base.blueprint.import` (plantilla, fichero o `retry_of`),
  `base.import.undo` y `base.hub.reset` (`dry_run` = el plan). Eventos `base.blueprint.imported`,
  `base.import.undone` y `base.hub.data_reset`, tras los que se re-ejecutan las consultas vivas del Inicio.
- `base.ImportBatch` (modelo de hub, migración `0009`) guarda cada importación: informe, filas creadas por parte
  (lo que deshace), origen y versión de la plantilla (lo que reintenta).
- Fase 1: los negocios comparten base de datos, así que `base.hub.reset` sin `dry_run` responde 409
  `base.reset_shared_database` (`available: false` en el plan) y «vacío» mira las filas de todos.
- Frontend: `base/frontend/pages/SettingsPage.vue` (`/settings`, pestaña en el hash `#data`; `/import` y `/export`
  del viejo llevan aquí), `components/data/*` y `lib/data.ts`; la tarjeta `components/BlueprintCard.vue` («Ahora
  no» en `localStorage["hub-blueprint-card-dismissed"]`). Tests: `base/tests/test_blueprint.py`,
  `test_services_data.py`, `test_queries_data.py`; Vitest en `base/frontend/**`; e2e `tests/e2e/base-data.spec.ts`
  (vacía lo que trae una plantilla por las operaciones de cada app antes de empezar).

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
  `SAAS_URL/dashboard/store/modules?business=<id del hub>`. La foto se aplica como la plataforma (`/internal`): tras su COMMIT,
  `base.hub.state_apply` avisa también al canal del propio negocio (`base/tests/test_hub_state_wake.py`), que es
  donde escuchan las consultas vivas que la siguen. `base.plan.usage` (`GET /api/system/plan`, `base.administer_hub`,
  viva con la foto): `plan.max_users`/`max_devices` de la foto (0 = sin tope) frente a las `Membership` activas del
  host; los dispositivos, sin cuenta. Tests: `base/tests/test_queries_apps.py`.
- Pantallas: `base/frontend/pages/AppsPage.vue` (`/apps`, pestañas por hash `#all`/`#paid`, las del hub viejo;
  reglas en `lib/apps.ts`), `SystemPage.vue` (`/system`, cinco pestañas por hash: ver «Sistema (APP-BASE-7)» abajo) y `AppBlockedPage.vue`, que monta la guarda de `lib/app-gate.ts` (`frontend/main.ts`: cada ruta
  de `apps/<id>/frontend/routes.ts` lleva `meta.app`; una app `off` en `base.session.me` monta la página por nombre
  en la misma dirección, como `NotInAppPage` del shell, y se comprueba también la primera dirección antes de montar).
  «Mejorar plan» (antes «Contratar en erplora.com») solo con `base.administer_hub` y `useSurface().isWeb`. e2e:
  `tests/e2e/base-apps.spec.ts` y `tests/e2e/base-app-activation.spec.ts`.
- Activación por negocio y tope del plan (hub#256, PLAN-HUB §9): `base.AppActivation` (por `host`; desde la ronda
  2026-10-27 un negocio nace con todo apagado, sin filas, también una demo; los hubs de antes conservan todo encendido
  con sus raíces elegidas, migración `base/0017`, y los locales `a`/`b` salen así de `seed_local_hubs`; el hub de
  ERPlora y el ámbito del worker lo tienen todo encendido siempre, `activation.is_platform`; `base/activation.py`).
  `base.blueprint.import` enciende antes de cargar las apps que lista el manifiesto (sus raíces, elegidas, por
  `base.app.enable`: tope, derechos y evento); la que no puede encender sale `inactive` con su `reason` en el
  informe. `base.app.enable`/`base.app.disable`
  (`POST /api/apps/enable|disable`, `base.administer_hub`: cierre de `requires`, 409 `base.app_required`, veto
  `can_disable` del `LiveAppConfig` → 409 `base.app_vetoed`, 402 `base.app_limit_reached` con `max_apps`/`enabled`;
  bajar de plan no apaga nada). Una app apagada da 404 `app_inactive` y sale del menú, del relay y del asistente
  (caché `base.apps_off:<host>`, olvidada al COMMIT). Falta el 202 «Activando…» (fase 2: BASE-F21, F22) y el veto de
  VeriFactu (su carril, VERIFACTU-F32). El gancho `can_disable(ctx)` corre en `translation.override(ctx.language)`: un
  `gettext` a secas ya responde en el idioma de quien pide (gh:hub#2595). En Apps, la negativa (409 o cualquier otro
  fallo al cambiar) es un `InlineFeedback` `apps-refused` que se queda hasta cerrarlo o hasta el siguiente cambio,
  nunca un toast (gh:hub#2594). Re-triados en FIX-HUB-BASE-APP-ACTIVATION-WORKBOOK-AND-FLOWS: F18, F19, F23–F25
  `hecho` (e2e `tests/e2e/base-app-activation.spec.ts`, en español y en los 3 tamaños).

- **Sistema (APP-BASE-7: BASE-F39…F47).** Pestañas por hash en `base/frontend/lib/system.ts` (`#resources`, `#plan`,
  `#updates`, `#events`, `#logs`; `#logs` solo con `base.administer_hub`, `#backups` → `/settings#data`, la pestaña
  «Datos y copias» de APP-BASE-2); a quien no
  administra no se le monta ningún componente que pida lo que el Hub le negaría (gh:hub#2519).
- Consultas (`base/queries.py`, `base.administer_hub`, `ai=`): `base.system.status` (`GET /api/system/status`: motor,
  `shared`/`own` según `Hub.db_name`, `version` y `released_at` de `base/system.py`, que lee `APP_VERSION` y
  `APP_RELEASED_AT` del entorno del despliegue; sin ellos, `dev` y `null`), `base.event.list` (`GET /api/system/events`:
  las 50 últimas `live.OutboxEvent` del host con su `EventDelivery` resumida y traducida; nunca el `payload`) y
  `base.failed_event.list` (`GET /api/system/failed-events`: las `EventDelivery` `dead` del host, hasta 100, con
  `retryable` = su app está en `relay.active_apps`). Las tres filtran por `scope_kind`/`scope_key` del contexto (test de
  dos hubs en `base/tests/test_queries_system.py`).
- Comandos (`base/services.py`, `base.administer_hub`, `ai=` con `risk`), con el id en el cuerpo:
  `base.failed_event.retry` (`POST /api/system/failed-events/retry`: `pending`, `attempts` 0, solo a su `app_label`;
  409 `base.failed_event_app_off` si la app no está activa), `base.failed_event.retry_all` (`POST
  /api/system/failed-events/retry_all`: `SKIP LOCKED`, todas las reenviables del host) y `base.failed_event.discard`
  (`POST /api/system/failed-events/discard`: estado `discarded` con `closed_at`, `closed_by` y `close_reason`, migración
  `0010_event_delivery_discard`; la fila no se borra). Una que ya no está `dead` o es de otro host: 404 `not_found`.
  Cada uno anota su evento en el outbox.
- El relay (`base/relay.py`, `relay_deliver_next` en `services.py`) avisa `base.failed_event.created` al host tras el COMMIT
  cuando se rinde (último intento o más allá de la profundidad máxima); no va al outbox (un oyente de todo evento que
  fallara en él se alimentaría solo). `base/live.py` re-ejecuta `base.failed_event.list`, `base.event.list` y
  `base.bell.counters` con `created`, `retried` y `discarded`; `base.system.status`, con `base.hub.state_applied`. Tests:
  `base/tests/test_services_system.py`, `test_relay.py`, `test_live.py`.
- Lo que una reacción o una tarea programada deja para después del COMMIT y espera a la red va por
  `base.outbound.after_commit(fn, *args)` (FIX-HUB-BASE-RELAY-BLOCKED-BY-SLOW-REACTION-CALLS): `THREADS` (4) hilos del
  worker en el contexto de BD de la operación que lo pidió (`base.tenancy.context.use_again`), `QUEUED` (1000) en
  espera, sin encolar dos veces lo que ya espera; `release()` suelta la conexión antes de esperar a la red; al parar, el
  worker da `OUTBOUND_GRACE_SECONDS` (15) a lo que corre y tira lo que espera. Un trabajo puede perderse: solo vale para
  lo que su app recupera sola (reclamo con plazo y barrido, como `flow.run.claim_call`). En los tests corre en línea
  (`conftest.py`); la marca `outbound_threads` da los hilos de verdad. Tests: `base/tests/test_outbound.py` y
  `apps/flow/tests/test_relay.py`.
- Un trabajo para otro negocio que el de la operación (una fila de otro negocio en las tablas compartidas de la fase 1:
  «Reintentar» desde la bandeja de WhatsApp) lo dice su app con `after_commit(fn, *args, scope=<Scope del negocio de la
  fila>)` (FIX-HUB-BASE-OUTBOUND-JOB-OF-ANOTHER-BUSINESS-HUB-CONTEXT-MISMATCH): `base.tenancy.context.current_for(scope)`
  le da la BD compartida de la fase 1 si quien lo pide es un hub de la fase 1 (`db_name=""`) y el negocio es otro, donde
  corren las operaciones de ese negocio, como en el barrido del worker, y sin ver nada que quien lo pide no viera ya; en
  cualquier otro caso (su propio negocio, la plataforma, un hub con BD propia) el contexto de quien lo pide, donde la
  operación de otro hub se rechaza (`HubContextMismatch`): ningún trabajo entra jamás en la BD de otro hub. El contexto
  se fija al pedirlo (`Job` inmutable). En la fase 2 cada BD solo guarda sus filas y nada cambia; S5 quita la rama de la
  fase 1 con `db_name=""`. Sin `scope`, el contexto de quien lo pide, como antes.
- Informe de errores de la pantalla: `base/frontend/lib/error-report.ts` (`error`, `unhandledrejection` y
  `app.config.errorHandler`; `navigator.sendBeacon`, el mismo error una vez cada 30 s, 50 recordados), instalado en
  `frontend/main.ts`. No envía los avisos del navegador de `BROWSER_NOTICES` («ResizeObserver loop completed with
  undelivered notifications.» y la forma vieja «ResizeObserver loop limit exceeded»): solo un `error` de `window` sin
  `Error` detrás (traza vacía) con el mensaje entero, como `ignoreErrors` de Sentry o las reglas de TrackJS; otro mensaje
  que nombre ResizeObserver, o las mismas palabras lanzadas por la app, sí se envían (`error-report.test.ts`, «the
  browser notices that are no error»). `POST /api/error-report` (`base/error_report.py`, fuera de ninja: un beacon no lleva CSRF) exige
  sesión, 30 por minuto y persona (`base.rate_limited`), cuerpo ≤ 16 KB y JSON, y escribe una línea `frontend.error
  {json}` en ERROR del logger `base.error_report` (host, usuario, pantalla, mensaje y traza recortados); el logging
  va a la consola y de ahí a CloudWatch (`config/settings.py` `LOGGING`). Tests: `base/tests/test_error_report.py`,
  `base/frontend/lib/error-report.test.ts`.
- Pantalla: `SystemPage.vue` con `SystemResources.vue`, `SystemRelease.vue`, `FailedEvents.vue` (descartar en
  `ConfirmDialog` con motivo; reenviar todos con `confirm`) y `SystemLog.vue` (`DataTable` con tarjetas en el móvil).
  e2e: `tests/e2e/base-system.spec.ts` (tres tamaños, dos hubs, campana → `#events`).

- **Ajustes del negocio (APP-BASE-6: BASE-F48…F51).** `base.business.get` (`GET /api/business`, `base.view_home`,
  viva con `base.hub.registered`): la fila del registro del ámbito, la que manda el SaaS por `PUT /internal/hubs/{id}`
  (nombre, país, zona e idioma, HUBS-F15), con la moneda del país (`base/business.py`: CLDR por Babel; sin país,
  `EUR`), los nombres en el idioma de la persona y `settings_url` = `SAAS_URL/dashboard/businesses/<id>/settings` (vacío en una
  demo). El registro se aplica como la plataforma: tras su COMMIT, `base.hub.register` avisa también al canal del
  propio negocio (`base/tests/test_business_live.py`). El Hub no guarda ni cambia nada de esto y no hay almacén
  clave/valor de ajustes: el `hub_settings` del runtime viejo se repartió entre sus dueños (país, zona e idioma en el
  registro; territorio en Impuestos, TAX-F11; emisor en Facturación, INVOICE-F21; la moneda, la del país). El hub
  propio de ERPlora (`PLATFORM_HUB_SLUG`; en la fase 1 sin fila en el registro) contesta el negocio de ERPlora, su emisor:
  `PLATFORM_ISSUER_LEGAL_NAME` y `PLATFORM_ISSUER_COUNTRY` con la moneda de ese país, la zona y el idioma del despliegue,
  `demo` falso y `settings_url` vacío (nada suyo se cambia en erplora.com), con fila o sin ella; su host sigue sin servir
  pantallas en la fase 1 (`erplora` es un slug reservado: 404). La moneda que cobra cada app es
  `base.operations.business_currency(scope)`: la de `base.business.get` leída como la plataforma (`system_context`;
  una API key solo tiene los permisos de lo que cobra) y, en un ámbito que no es de ningún hub, su `NotFound`, nunca un
  `EUR` por defecto (`base/tests/test_business_currency.py`). Un importe con su moneda lo escribe el servidor solo con
  `base.business.money_text(cents, currency)` (unidad menor → texto con los decimales de la moneda, en el idioma activo
  o el que se le pase), igual que `Intl.NumberFormat` en el navegador: el patrón de CLDR por Babel más el espaciado de
  moneda de CLDR, que Babel no aplica («PLN 15.50» con U+00A0, nunca «PLN15.50»; «€15.50»; «15,50 PLN»), y
  `grouped=False` para la exportación que su importación relee (flujo money-text). Lo usan el aviso y el tique de
  Ventas, el documento de Facturación, la exportación de Inventario, la web pública y los huecos de las aprobaciones;
  `tests/test_guardrails_money.py` no deja llamar a `format_currency` ni a `get_currency_symbol` de Babel fuera de él.
  Ventas, Facturación, Inventario, Tarifas e Impresión aún
  llevan su propia copia, `business_currency(ctx)`, que contesta lo mismo; Pagos, Carrito y pago, Citas, Menús y combos y Clientes
  aún cobran en `EUR` (BASE-F50 `parcial`). Pantallas: `SettingsPage.vue` (pestañas por hash `#business`, `#tickets`,
  `#data`; `#tax` abre Negocio; `lib/data.ts`) y `components/settings/{BusinessPanel,TicketsPanel,SettingsRow}.vue`.
  Tests: `base/tests/test_business.py`, `test_queries_business.py`, `test_business_live.py`; e2e
  `tests/e2e/base-settings-business.spec.ts`, con el Hub y el SaaS reales.
- **Acceso (APP-BASE-3: BASE-F52…F71).** Modelos de hub en `base/models.py`: `TrustedDevice` (el dispositivo:
  `token_digest` = SHA-256 del token de 256 bits de la cookie `hub_device`, httpOnly; nunca el token; `mode`
  `shared`/`personal` con quién y cuándo, `name`, `agent`, última persona y entrada, `ended_reason` `device_limit`),
  `Credential` (por `username`: `pin_hash` argon2id y `badge_digest` = HMAC-SHA256 del número con
  `AccessSettings.badge_key`), `AccessSettings` (fila única del negocio: `pin_policy` `always`/`per_shift`/`never`,
  `pin_inactivity_minutes`, `pin_length` 4/6; un valor que esta versión no entiende se lee como el de fábrica,
  `base/access.py`) y `Profile` (nombre, correo de contacto, foto, idioma, apariencia). En control, `SessionOwner`
  anota además `device_id` y `credential` (`account`, `pin`, `badge`).
- Entrar con la cuenta (BASE-F52, F53) es el canje de siempre (`/auth/callback`) más `services.trust_device` (la
  cookie `hub_device`), la duración de la sesión por dispositivo y negocio (`access.session_lifetime`: 12 h
  compartido, 30 días personal, tope de 1 h con `always`) y `_end_other_devices`, que aplica `plan.max_devices` de
  la foto (BASE-F57). El PIN y la placa son vistas de Django tras el CSRF, porque abren sesión (ninguna operación
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
  apariencia propia); `plan_url` y `account_url` solo en una sesión abierta con la cuenta
  (gh:hub#2506), y `manage_url` (`SAAS_URL/dashboard/businesses/<id del hub>`, BASE-F11) además solo con el permiso
  `base.open_management` (propietario y administrador por `base.*`; el encargado, a mano en `base/apps.py`: no tiene
  `base.administer_hub`). Lo pinta `TopbarChrome.vue` (`topbar-manage`; en el móvil, `topbar-chrome-more-manage`),
  un enlace con `target=_blank rel=noopener` que en la app instalada pasa por `openExternalLink` de
  `@erplora/ui/shell` (`open_external_url`); `base/frontend/lib/management.ts` lo oculta en la copia de Google Play
  (`device_context` → `distribution: "play"`, gh:hub#1897) y no lo enseña hasta que la app contesta. Tests:
  `base/tests/test_spa.py`, `test_access_spa.py`, `ShellChrome.test.ts`, `lib/management.test.ts`; e2e
  `tests/e2e/base-chrome.spec.ts` y `base-access.spec.ts` (BASE-G56). En `frontend/main.ts`, el menú de usuario lleva «Perfil» y «Cambiar de usuario», y `startWayIn`
  (`base/frontend/lib/access.ts`) arma el bloqueo por inactividad con esos minutos (gh:hub#2537, #2677: no hay
  lectura aparte que pueda fallar), pinta la apariencia propia y, tras un cambio de usuario (anunciado en
  `sessionStorage`), dice «Ahora atiende {name}» y olvida la apariencia anterior. Cambiar de usuario abre la sesión
  nueva sobre la vieja y recarga la pantalla en curso (`location.replace`): nada de quien se fue queda en memoria
  (gh:hub#2538, #2539); la cuenta abierta de Ventas la recuerda su app (`useCurrentCheck`). Guardar el nombre en Mi
  perfil llama a `sessionChanged()` (`lib/access.ts`) y `frontend/main.ts` vuelve a leer `base.session.me`, que es la
  sesión que pinta el shell (el menú lateral); si esa lectura falla, se queda la que había.
- «Plan y límites» (BASE-F28, `queries.plan_usage`) cuenta los dispositivos en uso con la regla del tope de BASE-F57
  (`services._end_other_devices`): los `device_id` distintos de las sesiones vivas del host (`SessionOwner`).
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
- Archivos (BASE-F72…F76) no tiene modelo ni tabla: lista el almacén `STORAGES["hub_files"]` (`base/storage.py`: S3
  con bucket, si no disco bajo `MEDIA_ROOT`) bajo `hub-<hex>/files/<ruta>` con `base/files.py` (sin ORM: nombres y
  rutas, el `.keep` de una carpeta vacía, listar, subir, carpeta, renombrar, mover, borrar y `file_response`). Las
  operaciones, todas con `ai=`: `base.file.list` y `base.file.read` (`queries.py`, `base.view_files`), y en
  `services.py` `base.file.upload`, `create_folder` y `rename` (`base.upload_files`), `move` (`base.delete_files` y
  además `base.upload_files`) y `delete` (`base.delete_files`). Rutas `/api/files`, `/api/files/raw` (los bytes con
  `Cache-Control: private, no-store`, adjunto salvo `inline` en un tipo que se puede enseñar, CSP `sandbox`; su
  descripción en JSON con `Accept: application/json`) y `/api/files/{upload,folder,rename,move,delete}`; eventos
  `base.file.*` y consulta viva `base.file.list`. Nunca por `/p/media/` (público y con caché de un año: solo las
  `PUBLIC_FOLDERS`). Topes: 25 MB por archivo (cuerpo de 35,1 MB en base64), nombre de 255 bytes, carpeta de 100
  caracteres y ruta de 980 bytes; los programas (`BLOCKED_EXTENSIONS`, la lista de Gmail) se rechazan. Subir nunca pisa:
  la escritura es condicional (`If-None-Match: *` en S3, `O_EXCL` en disco) y, si otra subida del mismo nombre llegó
  antes, toma el siguiente nombre libre. Un listado lee solo la carpeta abierta (`Delimiter` en S3); el árbol de carpetas
  y lo que ocupan los archivos salen del índice del hub, guardado en la caché (`base.files:<hex>:*`, 10 minutos como
  mucho): una subida le suma sus bytes y crear, renombrar, mover o borrar lo olvidan, así que un lote de subidas y los
  listados de después recorren los archivos una sola vez; lo que guardan las apps se cuenta en cada llamada. El espacio
  es el de todo el prefijo del hub, contra `plan.max_storage_bytes` de la foto del SaaS (sin él, «Sin límite»). Una app que
  guarde archivos lo hace en su carpeta propia del prefijo (como `website/`), fuera de `files/`, y Archivos no la
  enseña. Pantalla: `pages/FilesPage.vue`, `components/{FileTree,FilePreview}.vue` y `lib/{files,pdf}.ts` (pdf.js en el
  hilo principal). Tests: `base/tests/test_files.py`, `test_files_api.py`, el Vitest de cada pieza y el e2e
  `tests/e2e/base-files.spec.ts` (tres tamaños, el empleado y el hub B que nunca ve los de A).
- **Asistente** (APP-BASE-9, BASE-F92…F106; PLAN §30, ronda 2026-10-22b): es **plataforma** dentro de `base/`, no un
  módulo `kind="app"`: lo traen todos los planes (el cupo mensual llega en la foto; 0 = sin asistente) y sus piezas son
  del shell y del Inicio. `base/assistant.py` (sin ORM) tiene el catálogo de herramientas (`catalog`: toda
  `@operation` de las apps activas cuyo `ai=` tiene descripción y cuyo permiso tiene la persona, o que su app deja
  aprobar a un responsable (`approvals.label_of`), salvo las «Not an assistant tool» / «System only», las sin permiso,
  las de la plataforma (un permiso que ninguna app declara, `<app>.system` o `system.<app>`: sus reacciones y tareas
  programadas, que solo alcanza `*`; `declared_permissions`: ni siquiera un superusuario las recibe, diga lo que diga
  su `ai=`), las `base.assistant.*` y `NOT_FROM_CHAT` = `base.hub.reset` y `base.blueprint.export`), `relevant` (como mucho `MAX_TOOLS` = 40 por turno, por las palabras de las dos últimas
  preguntas; `base.setup.status` y `base.business.get` siempre), la tarjeta (`card`: `ai={"risk": "high"}` pide
  `CONFIRM_WORD`, «CONFIRMAR» por `pgettext` con contexto `base`, o el número de `ids`; sin `ids`, `blocked`; cada
  dato con su nombre en el idioma de la persona, `_label`: el `title` del esquema si un catálogo lo traduce, o tal
  cual en inglés; si no, el `verbose_name` del campo del mismo nombre en los modelos de su app, primero el de la
  entidad de la operación; si no, el `title` por los catálogos. Un dato sin campo de modelo lleva
  `title=gettext_noop(…)` y su `es` en el `.po` de su app, como los de Archivos, Plantillas y Personas en
  `base/schemas.py`; lo comprueba `test_no_datum_of_a_write_of_base_reaches_a_spanish_card_by_its_technical_name`;
  la app de la tarjeta y del recibo, `app_name`: la de una app por su `verbose_name`, una acción de `base` por la
  pantalla de su entidad, `BASE_SCREENS`, nunca «Base»; el recibo usa el `app_name` que manda el turno en
  `executed`; lo comprueba `test_every_action_of_base_names_its_screen`; la acción de la tarjeta y del recibo, el
  último trozo del nombre de la operación (`action`), por su verbo en `base.assistant.card.actions` de los catálogos
  `en` y `es` de `base` (`actionKey` de `lib/assistant-card.ts`, por clave exacta; sin clave, «Do this»): una app con
  una acción nueva añade ahí su verbo en los dos idiomas, y lo comprueba
  `test_every_write_the_assistant_may_call_names_its_action_in_english_and_spanish`; un dato secreto, el que su
  esquema marca `format: password` o `writeOnly` (`SecretStr`), a cualquier profundidad, sale tapado con `HIDDEN`,
  «••••••••», igual en todos los idiomas (`_hidden`, desde `_field`, el mismo en la tarjeta y en la vista previa): ni
  la pantalla ni lo que recibe el navegador lo llevan tal como se escribió, y la escritura lo recibe entero al
  aceptarla; uno vacío sale vacío; lo comprueban `test_no_operation_lets_a_secret_reach_its_card_in_clear`, que
  recorre el registro entero, y
  `test_a_secret_reaches_the_browser_hidden_on_its_card_and_its_write_as_typed`), la vista previa de una
  escritura peligrosa (BASE-F98, `preview`: su `ai=` lleva `"preview": {"operation": "<una query de su app>",
  "fields": [<datos de su respuesta>]}`; el turno la corre como la persona, `_run` con su `ctx`, con los datos de la
  escritura que su entrada toma, antes de la tarjeta; quita los vacíos y los `None`, lo que la lectura oculta; si no
  se puede leer, su error es el de la escritura y no sale tarjeta; `base.E005` comprueba al arrancar que es una
  query de la misma app, que da esos campos, que la escritura lleva toda su entrada y que es `risk="high"`; la
  tarjeta la pinta bajo «Lo que va a pasar», `AssistantConfirm.vue`; hoy la declara `base.person.pin_remove` con
  `base.person.detail`), la
  comparación del servidor (`confirmed`, como `ConfirmDialog`: sin mayúsculas ni espacios de los extremos),
  `run_tool` (la operación como la persona; `PermissionDenied`, `AppInactive` y `Unauthorized` → `refused`) y las
  puertas firmadas del SaaS (`/internal/assistant/chat/stream`, `usage`, `report` y `/internal/speech/transcribe`, con
  el HMAC de `base.signing`).
- Operaciones del asistente, todas con `base.view_home` y `ai=` «Not an assistant tool»: `base.assistant.turn`
  (command: corre las lecturas pendientes, para en la tarjeta de una escritura hasta su `decision`, corta a las
  `MAX_ROUNDS` = 6 rondas con `assistant.too_many_steps`; el «sí» a una escritura que la persona no puede hacer y un
  responsable puede aprobar responde `requires_elevation` para esa misma petición y, repetida con el pase, la corre
  con ese permiso más y gasta el pase en su transacción (`_assistant_approved` + `base.approval_spend`), y arma las
  instrucciones con las pantallas que puede enlazar
  y, con `setup`, la lista de `base.setup.status` releída), `base.assistant.usage` (query), `base.assistant.report` y
  `base.assistant.transcribe` (command). Rutas en `base/api.py` (`/api/assistant/turn`, `usage`, `report`,
  `transcribe`): el turno responde en streaming (`text/event-stream`, `turn_response`) a **una** petición `fetch` +
  `ReadableStream` que se cierra al acabar (tramas `text`, `executed`, `confirm`, `usage`, `error` y `done`), no una
  segunda SSE permanente (PLAN §14). El navegador nunca habla con la pasarela ni con un proveedor.
- Panel: `base/frontend/components/assistant/` (`AssistantPanel`, `AssistantMessage`, `AssistantMarkdown`,
  `AssistantComposer`, `AssistantConfirm` sobre `ConfirmDialog`, `AssistantReport` sobre `FormModal`, `AssistantEmpty`
  y `AssistantButton`), montado por `createShell({ chrome: { topbar: TopbarChrome, background: BackgroundChrome } })`
  en `frontend/main.ts`, sin tocar `packages/ui`. Estado por pestaña en `base/frontend/lib/assistant.ts`; la
  conversación, en `sessionStorage` (`erplora.assistant.history`, de una persona: otra empieza vacía) y el abierto o
  cerrado en `localStorage` (`erplora.assistant.open`); sin IndexedDB. `signOut()` de `frontend/main.ts` la olvida
  antes de `logout` (también el bloqueo por inactividad). Comprobaciones de la respuesta en `lib/assistant-grounding.ts`,
  formato en `lib/assistant-markdown.ts` (nunca `v-html`), adjuntos y voz en `lib/assistant-input.ts`
  (`MediaRecorder`, dos minutos), el dictado en `lib/dictation.ts` (`useDictation`: una grabación por pulsación, 2 MB,
  el texto al cuadro y el panel abierto; el mismo para el cuadro y para la app que abre el asistente dictando),
  atajos, fallos y cupo en `lib/assistant-guide.ts`. Desde 768 px el panel se ancla (clase `assistant-docked` en
  `<html>`, que empuja el pane); por debajo, velo.
- Tests: `base/tests/test_assistant.py`, `test_services_assistant.py` y `test_api_assistant.py` (con la pasarela
  falsa de `base/tests/fake_gateway.py`); Vitest de `base/frontend/lib/assistant*.test.ts`,
  `components/assistant/*.test.ts`, `SetupChecklist.test.ts`, `ShellChrome.test.ts` y `frontend/main.test.ts`; e2e
  `tests/e2e/base-assistant.spec.ts` contra un SaaS de verdad con su pasarela y el proveedor falso
  `tests/e2e/assistant-provider.ts` (un servidor HTTP en 127.0.0.1 que habla la API de OpenAI; receta en
  `tests/e2e/README.md`, «El asistente»): ningún test llega a un proveedor real.

- Personas y permisos (APP-BASE-5): las personas son `Membership` (control) más la foto de erplora.com
  (`hub.state["members"]`, `plan.max_users`); invitar, cambiar el rol y quitar son de erplora.com (HUBS-F24…F29):
  el hub enlaza a «Miembros» (`members_url` de `hub-home`). Reglas puras en `base/people.py`; operaciones
  `base.person.{list,detail,pin_remove,badge_set,badge_remove}` y `base.role.list` (rutas `/api/people…`,
  `/api/roles`). El PIN y la placa son los de APP-BASE-3 (`Credential`): mismo hash, mismos frenos.
- Llaves de API: `base.models.ApiKey` en la BD del hub (token `erpk_live_` + 256 bits, se guarda su SHA-256 y su
  principio); `base/api_keys.py` pone la puerta de la llave (`KeyDoor`) delante de la sesión en toda ruta de una
  operación `expose_api`; la llave recibe el permiso de esa operación y nada más, con su ritmo por minuto y el freno
  por dirección (`KEY_ADDRESS_LIMIT`). Solo con `hub.db_name` (BD propia): en el modo compartido de la fase 1 una
  llave abriría otros negocios, así que `base.api_key.*` responde 409 `base.api_keys_unavailable` y un `Bearer` no
  entra (test A≠B en `base/tests/test_api_keys.py`).
- Aprobación con PIN de un responsable: una app nombra sus órdenes aprobables en su `LiveAppConfig`
  (`approvals = {"sale.sale.void": _("Void a sale")}`; una consulta nunca, ni una orden `database=False`, que no abre
  transacción en la que gastar el pase: `base.E004` lo dice al arrancar). `base/approvals.py` pone su puerta
  (`ApprovalDoor`) delante de la sesión en toda orden: a quien es del negocio y le falta el permiso le responde 403
  `requires_elevation` con `approval: {operation, label, fingerprint}` (huella de negocio, método, ruta y cuerpo); a
  quien no es del negocio (sin `base.view_home`), el `permission_denied` de siempre. La frase con cifras
  (FIX-HUB-BASE-APPROVAL-LABEL-WITHOUT-DISCOUNT-FIGURE; hub#2180 y hub#2186 del hub viejo): junto a `approvals`, la
  app declara `approval_figures = {"<orden>": [_("… {campo} …"), …]}`, frases que se prueban en orden con huecos de
  la entrada de la orden: `{campo}` (texto o número), `{campo, percent}` (0–100, `format_percent`) y
  `{campo, money}` (unidades menores en la moneda del negocio, `business_currency`); gana la primera cuyos huecos se
  llenan todos (ni vacío, ni `None`, ni cero), y si ninguna, la frase fija. Las cifras salen de la entrada
  **validada** por el esquema de la orden (`approvals.figures_from`: `json.loads` + `op.input.model_validate`, como la
  ruta y el asistente), solo de los campos que nombran sus frases (`figures_of`); una entrada que no valida da la
  frase fija y el error es el de la propia orden. La huella y el gasto del pase no cambian; el pase gastado guarda
  esas cifras (`Approval.figures`, JSON, migración `0018`), y la lista y el CSV las dicen en el idioma de quien lee
  (`operation_label` es el nombre sin cifras, para el filtro «Acción»). `base.E008` comprueba la declaración al
  arrancar: orden de la propia app que su `approvals` nombra, campos que existen en su entrada, `percent` de un
  número y `money` de un entero, y los mismos huecos en `en` y `es`. Hoy la declaran `demo` (`demo.item.add_line`);
  Ventas, en su FIX (SALE-F14).
  `base.approval.approve` comprueba el PIN o la placa como la puerta del PIN (`queries.pin_owner`,
  `services.badge_owner`, `PIN_PERSON_LIMIT`/`PIN_ADDRESS_LIMIT`) y que quien aprueba tenga el permiso, y devuelve un
  pase de un uso (120 s, `X-Elevation-Token`); la puerta marca la petición con él (`Approved`), `base.operations`
  añade ese permiso a esa llamada y el pase se gasta en la transacción de la propia orden: `LIVE["operation_database"]`
  (`base/entitlement.py`) abre esa transacción en `base/approval_spend.py` y gasta el pase dentro
  (`base.approval.spend`, sin ruta, con la fila bloqueada), así que una orden que falla lo deja sin gastar, una que
  salió bien no se repite y de dos a la vez solo corre una (`base/tests/test_approval_spend.py`; excepción razonada
  en `tests/test_guardrails.py`, `APPROVAL_SPEND_REASON`).
  Lo que la orden aprobada pide a otras apps por el camino va con ella (hub#250,
  FIX-HUB-BASE-APPROVED-COMMAND-CROSS-APP-CALLS-USE-CALLER-PERMISSIONS): una app corre la operación de otra con
  `base.operations.call(ctx, name, data, unavailable=…)` (la entrada se valida como en una ruta y lo que no valida es
  el 422 del que llama; la app ausente o apagada, su `unavailable`, o `UnknownOperation`/`AppInactive` sin él), que la
  corre con `approvals.consequence_context`: mientras corre la orden aprobada de esa petición (el `current_operation`
  de live es la orden de la marca `Approved`, cuyo pase ya se gastó en su transacción), una orden (`kind="command"`) de
  **otra** app recibe su permiso. Una consulta nunca, una orden de la propia app nunca y nada fuera de la orden
  aprobada (la petición siguiente, otra herramienta del turno del asistente, que marca la petición del turno entero);
  quien ya tiene el permiso sigue con su contexto tal cual. Solo las llamadas directas de la orden aprobada: lo que
  esa otra orden llame a su vez va con el contexto que recibió. La huella y el gasto del pase no cambian
  (`base/tests/test_approved_calls.py`). Ventas aún lleva su copia (`approval_of`, `consequence_context` y `call_app`
  de `apps/sale/queries.py`) y pasa a `call` en su FIX; Reservas y Mesas, sin órdenes aprobables, llevan su
  `call_app` propio, al que no llega ninguna aprobación. En el cliente, `withApproval(() => command.run(input))` de
  `base/frontend/lib/approval.ts` abre el diálogo y repite la orden una vez (`getElevationToken` en
  `frontend/main.ts`). El registro es `base.models.Approval` (`base.approval.list`).
- Documentación de la API: `base/api_docs.py` recorta el OpenAPI de ninja a las rutas `expose_api` de las apps que
  tiene el negocio, con la llave como `bearer` y solo los esquemas que usan (`base.api_doc.get`, pedido una vez y no
  en vivo: con todas las apps pasa de 1 MB, más que el tope de un resultado vivo); el ajuste es
  `base.models.ApiSettings` (`base.api_doc.settings`, `base.api_doc.settings_update`). Sin Swagger UI: producción
  aplica Trusted Types; la página propia la lee y la descarga. La entrada «API» del menú lateral sale con el ajuste
  (`useApiDocsShown` de `base/frontend/lib/sidebar.ts`, que se suscribe a `base.api_doc.settings` solo con sesión).
- Menú lateral: `SIDEBAR` de `frontend/main.ts`; cada entrada lleva el `visible` del shell (`ShellSidebarItem`,
  `packages/ui`) con el permiso de la operación de su pantalla (`allowedTo` de `base/frontend/lib/sidebar.ts`): un
  empleado no ve «Sistema» (`base.administer_hub`).
- Tests: `base/tests/test_people.py`, `test_api_keys.py`, `test_approvals.py`, `test_approval_spend.py`, `test_approved_calls.py` y `test_api_docs.py`; Vitest de
  `base/frontend/lib/{people,approval,api-docs,sidebar}.test.ts`, `components/{PeopleList,RolesList,ApiKeysPanel,
  ApprovalDialog,ApprovalsList,ApiDocsCard}.test.ts` y `pages/{Employees,Person,ApiDocs}Page.test.ts`; e2e
  `tests/e2e/base-employees.spec.ts`.
- La QA maestra del Hub (BASE-F107 = BASE-G152, `qa:shared/qa-hub`, APP-BASE-10): el contrato de los agentes
  `qa-hub*` del hub viejo pasa a ser una e2e de `base`, `tests/e2e/base-qa-master.spec.ts`, contra el SaaS de la pila
  (alta en sus pantallas, negocio por su API con `business_type` del vertical) y su pasarela del asistente con el
  proveedor de `tests/e2e/assistant-provider.ts`. Pide al SaaS su taxonomía (`seed_taxonomy`, que corre en cada
  despliegue) y el proveedor sembrado (README de `tests/e2e`, «El asistente» y «La QA maestra»). Cada pantalla se
  comprueba contra los catálogos del propio hub (`tests/e2e/translations.ts`: los `en`/`es` de la SPA y los `.po`;
  un texto que solo escribe el otro idioma o una clave a la vista es un fallo) y deja
  `APP-BASE-10-BASE-G152-<idioma>-<pantalla>-<ancho>`.
- Del contrato viejo, lo que es de otras apps (cada flujo con su estado en su WORKBOOK y su e2e): §4 la siembra por
  vertical = BASE-F29/F31 + plantillas `base/seeds/<vertical>.<idioma>.json` (la carta con la categoría de IVA de
  cada producto y la sala, de la plantilla; la cocina y la caja, de sus apps). §5 restaurante: R-01 CASH_REGISTER-F03,
  TABLE-F09; R-02 RESERVATION-F06/F10/F11, TABLE-F28; R-03 TABLE-F10; R-04 SALE-F19, MODIFIER-F07, KITCHEN-F07;
  R-05/R-06 KITCHEN-F04/F05/F10/F18; R-07 TABLE-F15/F16/F17, SALE-F23/F24; R-08 SALE-F21, PRINTING-F09; R-09
  SALE-F01/F02/F03, INVOICE-F01/F02, VERIFACTU-F19, PRINTING-F07/F13; R-10 TABLE-F21, CASH_REGISTER-F09/F16,
  SALE-F28; R-11 SALE-F14/F15/F20/F29/F30/F31, INVOICE-F07/F09/F10. §6 peluquería: B-01 CASH_REGISTER-F03,
  APPOINTMENT-F01; B-02 APPOINTMENT-F01/F02/F04/F05/F09; B-03 APPOINTMENT-F07, CUSTOMER-F01; B-04 APPOINTMENT-F04;
  B-05 APPOINTMENT-F17, SALE-F38; B-06 como R-09; B-07 CASH_REGISTER-F09, SALE-F16/F28, STAFF-F21; B-08
  APPOINTMENT-F09, SALE-F30/F31, STAFF-F21, SERVICE-F12/F14/F22. §7 fiscal: INVOICE-F01/F02/F07/F09/F10/F15 y
  VERIFACTU-F15/F18/F19/F26/F28 (solo contra el entorno de pruebas de la AEAT). §8 impresión: PRINTING-F01/F02/F04/
  F07/F09/F10/F13/F14/F17/F18 (la cola de `/ws/print`). Sus specs: `cash-register-*`, `table-flows`, `reservation-book`,
  `sale-*` (con `sale-invoice-chain`), `modifier-till`, `kitchen-*`, `invoice-sale`, `verifactu-flows`,
  `printing-*`, `appointment-*`, `staff-commissions`, `service-flows` y `customer-flows`. Lo que aún no está entero
  es `parcial` en su app: PRINTING-F02 (buscar la impresora en la red), PRINTING-F13 (el cajón al cobrar),
  PRINTING-F18 (el dispositivo que recoge la cola), SALE-F14 (el descuento) y SERVICE-F14 (vender un bono en el TPV).
- Del contrato viejo no sigue lo que era proceso de aquella flota: §2 (método: el QA no arregla y abre issues por
  repo), §2b (el banco de pruebas en PRE con `spawn-hub.sh`), §3 (contar 25–27 módulos y sus `module.json`), §9 (la
  lista de vigilancia), §10 (el informe PASS/FAIL por escenario) y §11 (el `POST /api/command|query` del runtime en
  Rust): aquí cada flujo tiene su e2e en `tests/e2e`, el banco es la pila de su README y la API es la de django-ninja
  de cada operación. La propina sigue fuera (pm#100).
- «Reportar un problema» (BASE-F108, FIX-HUB-BASE-REPORT-PROBLEM-MODAL): la entrada `report` del menú de usuario
  (`frontend/main.ts`) es una acción (`run` de `ShellUserMenuItem`, `packages/ui`) que abre `ReportProblemDialog.vue`
  (en `BackgroundChrome.vue`, con `lib/report-problem.ts`), el `ReportProblemModal` de `@erplora/ui/components`
  sobre `FormModal`. Sale con `account_url` (la sesión abierta con la cuenta; `base/spa.py` ya no incrusta
  `report_url`). `base.support.report` (`base/services.py`, `database=False`: espera a erplora.com sin transacción
  abierta) solo acepta una sesión abierta con la cuenta (`CREDENTIAL_SESSION_KEY` de `base/access.py`, que escribe
  `_log_in` como `SessionOwner.credential`; una sesión sin ella no es de la cuenta, y el shell, `base/spa.py`, la
  copia de `SessionOwner` al cargar, así que una sesión anterior al cambio sigue igual: la de la cuenta puede, la de
  un turno con PIN no) y un usuario `saas:<id>`; si no, 403 `base.support_needs_account`. Firma v1 + v2 hacia
  `POST {SAAS_INTERNAL_URL}/internal/support/report` del SaaS (`accounts/internal.py`), que llama al mismo
  `send_support_report` que su panel (límite `SUPPORT_REPORT_RATELIMIT` por cuenta, «Reply-To» la cuenta, «From: Hub»
  y el negocio). Un 429 del SaaS es 429 `base.too_many_attempts`; caído, fuera de tiempo o cualquier otra respuesta,
  503 `base.report_not_sent` con `SUPPORT_EMAIL`. El hub no pone límite propio (el del SaaS ya va por cuenta) ni
  registra el texto. Tests: `base/tests/test_support_report.py`; Vitest de `base/frontend/lib/report-problem.test.ts`,
  `components/ReportProblemDialog.test.ts` y `frontend/main.test.ts`; e2e `tests/e2e/base-report-problem.spec.ts`
  contra el SaaS de la pila.

## Lo que NO hace, a propósito

- No inventa cifras: un panel o un paso que no se puede comprobar no sale o dice «No disponible».
- No guarda el tablero en el servidor: es de cada dispositivo, como en el hub viejo.
- No enseña nunca a un cliente los ejemplos de la app Demo.
- Importar no trae personas, PIN, datos fiscales ni los ajustes del negocio; exportar no los lleva nunca, ni
  archivos ni imágenes.
- No guarda los informes de «Reportar un problema» ni abre incidencias: los manda a erplora.com, que los envía al
  buzón de soporte con la cuenta y el negocio (BASE-F108). No acepta un informe desde una sesión de PIN, que no tiene
  una cuenta a la que responder, ni capturas adjuntas.
- No vende ni enseña importes: el precio y la compra de una app de pago son de la Tienda de erplora.com, y en la
  app instalada ni siquiera lleva a ella.
- No pregunta a erplora.com al abrir una app: usa lo último que erplora.com le pasó del negocio.
- No inventa cifras de uso: la CPU, la memoria y las conexiones no son de un negocio, así que Sistema no las enseña.
- No edita un aviso caído ni enseña lo que llevaba: se reenvía tal cual o se descarta, y el descartado se guarda.
- No cambia el nombre, el país, la zona horaria ni el idioma del negocio: los guarda erplora.com y el hub los
  recibe. Tampoco deja elegir la moneda: es la del país del negocio.
- No guarda un PIN ni el número de una placa: solo lo que permite comprobarlos, y nunca enseña el correo de nadie
  en las caras de una caja.
- No tiene contraseña propia: la cuenta es la de erplora.com; el PIN y la placa solo abren una caja en la que ya se
  entró con una cuenta.
- Archivos no enseña las carpetas que usan las apps para lo suyo (las imágenes de la web): las gestiona cada app; los
  registros del sistema están en «Sistema» › «Registros».
- Archivos no tiene papelera, no copia, no comparte por enlace ni busca en todas las carpetas a la vez; tampoco guarda
  programas ni archivos de más de 25 MB.
- No invita, no cambia el rol ni quita a nadie: es de erplora.com, que lleva las plazas del plan; el hub lo enseña y
  enlaza a «Miembros».
- No enseña nunca el token entero de una llave después de crearla o rotarla, ni guarda el PIN de quien aprueba.
- El asistente no guarda la conversación en el servidor: vive en la pestaña de quien pregunta y se olvida al cerrar
  sesión o cambiar de usuario.
- El asistente no busca en Internet ni convierte divisas (llegan con la etapa ERP), y no hace nada que la persona no
  pueda hacer con sus botones, ni sin su «Ejecutar».
- La voz con la que lee una respuesta es la del propio dispositivo; el Hub no genera audio.
