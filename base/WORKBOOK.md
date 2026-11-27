# Workbook — Base (plataforma)
Prefijo: BASE
Alcance MVP: núcleo (la plataforma del hub: siempre está, no se activa ni se apaga)
Estado de la app: completa (2026-11-01)
Lo que no entra todavía: ver «Lo que queda fuera».

> Manual de usuario y especificación de `base`, la plataforma del Hub: siempre está, no se activa ni se
> apaga. Esta primera parte describe el **Inicio**, la pantalla a la que se llega al entrar en el negocio
> (saludo, «Mis apps», la lista de lo que falta por configurar, los paneles de las apps y
> la actividad), con lo que acompaña a cualquier pantalla: la campana con sus avisos (también el de que todavía no
> se puede facturar), «Mejorar plan» y «Gestionar en erplora.com». También «Apps», «Uso y plan» de
> Sistema y las plantillas: la tarjeta del Inicio y Ajustes › Datos y copias (importar, exportar, deshacer y
> restablecer). El acceso (entrar con la cuenta, con PIN o con la placa, cambiar de usuario, Mi perfil y los
> dispositivos) está en sus propias pantallas, más abajo.
> Y «Archivos»: los documentos del negocio, en carpetas; y el asistente, en su panel, al final.

## Para qué sirve y para quién

Es lo que el Hub trae siempre, sin activar ninguna app: el **Inicio**, las **personas** del negocio, sus **archivos**,
sus **apps**, el **sistema** y los **ajustes**. Desde aquí se abre cada app y se prepara el negocio para trabajar.

### De un vistazo

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
  plataforma («Tus apps», «Activa …» de cada app obligatoria en su país, «Tu equipo»), y en la campana ven los
  avisos entre apps que no se entregaron. Solo el **propietario** compra para el negocio (mejorar el plan o contratar
  una app de pago en erplora.com), restablece el negocio y descarga las copias de sus datos, como en erplora.com, donde el
  plan, el cobro y la propiedad son solo suyos.
- El **responsable** y el **empleado** ven sus apps, los pasos que les tocan, los paneles que pueden ver
  y la actividad. Un paso que solo puede resolver un administrador también lo ven, para saber por qué no se
  puede facturar, pero sin botón.

## Referencia adoptada

El Inicio tiene esta estructura: saludo y fecha, lanzador de apps, lista de configuración con barra de progreso, tablero de paneles y pestañas
«Resumen» y «Actividad». Sigue lo que hace el mercado: la lista de «Setup guide» de Shopify y Square
(pasos con su botón, el progreso arriba y lo hecho plegado), el lanzador de apps de Odoo, el tablero de
paneles que cada uno elige y ordena de Lightspeed y Toast, y la campana de los avisos que piden una acción, que se
quedan hasta que se resuelven y llegan arriba a la derecha (Shopify, Business Central, Stripe; el centro de
notificaciones de macOS). «Uso y plan» de Sistema sigue a «Capacity» de Business Central y a las páginas de uso de Supabase, Vercel y
Neon: cada cifra frente a lo que incluye el plan y, como Google Workspace, el aviso amarillo al 80 % y el rojo al
llenarse.

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
Arriba, el nombre del negocio y «Hoy» con la fecha larga. Debajo, en este orden:

- **Cómo está funcionando el negocio**, solo para quien lo administra: una etiqueta de color por cada app encendida que
  dice cómo está (la impresora de tiques, el número de WhatsApp), con lo que lo arregla, y «Ver sistema».
- **«Empieza con un negocio como el tuyo»**, solo para quien administra el negocio y mientras el negocio no
  tiene nada de lo que trae una plantilla.
- **«Mis apps»**: una baldosa por app que la persona puede abrir, con su icono y su nombre; las que más se abren
  en este navegador, primero.
- **«Termina de configurar tu negocio»**: cuántos pasos lleva hechos, una barra y los pasos que faltan, cada uno con
  «Configurar».
- **El tablero de paneles**, con «Personalizar panel» (⋮) arriba a la derecha.

#### Lo que trae cada parte
- **El nombre del negocio**: mientras no lo tiene, un saludo según la hora («Buenos días», «Buenas tardes», «Buenas
  noches»).
- **Las plantillas**: hasta cuatro, con «Usar esta», «Ver todas las plantillas» y «Ahora no».
- **«Mis apps»**: en el móvil, con seis apps o más, las cuatro primeras y «Ver todas las apps».
- **Cada paso por configurar**: su icono, su explicación, una etiqueta («Necesario para facturar», «Importante»,
  «Recomendado», «Hecho» o «Todavía no disponible») y «Configurar». La lista, plegada: cinco pasos (dos en el
  móvil), primero los que impiden facturar, con «Ver todo» y «Ver menos». Cuando no falta nada: «Tu negocio
  está listo».

### Inicio · Actividad
La tabla de las últimas ventas: «Fecha», «Venta», «Cliente», «Método», «Importe» y «Estado», con
«Buscar actividad…», el embudo de filtros (método y estado), el orden, la vista de tarjetas y «Columnas».
Se abre también con el enlace del Inicio terminado en #actividad.

### La campana
Arriba a la derecha, la última de la barra, después de «Mis apps», de los destellos del asistente y, en la aplicación
instalada, de «Cambiar de negocio» (HUB_APP-F04 de ERPlora/app), también en el móvil. Reúne lo que pide una acción
y sigue siendo verdad hasta que se resuelve: «Todavía no puedes facturar», una factura del plan sin pagar, los
eventos caídos, los límites del plan, los roles por revisar, las citas por confirmar, los clientes de WhatsApp
esperando respuesta, una impresora que no imprime… Ningún aviso se descarta: se va solo cuando se resuelve.

- **La campana.** Sin nada pendiente, solo la campana. Con algo, pasa a una píldora con la campana y el número, en el
  color y con el icono del aviso más grave (urgente, atención o información). Si un aviso tiene plazo, como la hora de
  la cita más próxima por confirmar, el anillo de la campana se va vaciando en la última semana antes de él.
- **La llegada.** Un aviso nuevo entra como tarjeta bajo la barra, arriba a la derecha (a lo ancho en el móvil), se
  queda unos segundos y se recoge en la campana, que late; con el asistente abierto, entra a su izquierda. Mientras
  se cobra en el TPV no sale: solo late la campana. El primer resultado al abrir la página no anuncia nada.
- **El panel.** Al tocarla se abre un panel desde la derecha, por encima de la pantalla y del asistente (a lo ancho en
  el móvil): arriba, el aviso más grave, con su frase y su botón (por ejemplo, «Configurar los datos del negocio»);
  debajo, los demás en filas («3 citas por confirmar»), y tocar una fila la pone arriba. Cada aviso lo dice la app que
  lo da, en el idioma de la persona: el problema en el titular («3 citas por confirmar»), la consecuencia en una frase
  («Tus clientes esperan a que les confirmes las citas antes de que empiecen.») y la acción en su botón («Confirmar las
  citas»). Se cierra con su ✕, con Esc o tocando fuera, y la campana recupera el foco. Sin nada: «Todo al día». Un
  aviso resuelto se queda un momento con «Resuelto» antes de irse.

### El menú lateral
A la izquierda (en el móvil, desde el botón de la barra): la persona arriba y las entradas de la plataforma en dos
grupos, «Inicio», «Empleados», «Archivos» · «Apps», «Sistema», «API», «Ajustes». Cada una sale solo a quien tiene el
permiso con el que se abre su pantalla, como en Square o Toast: «Sistema», a quien administra el negocio; «API», además,
mientras la documentación de la API está mostrada (BASE-F91), y aparece o se va al cambiar el interruptor, sin
recargar. Un empleado ve «Inicio», «Empleados», «Archivos», «Apps» y «Ajustes». Una entrada que la persona no tiene,
abierta por su dirección, dice «Sin acceso» (BASE-F118). Abajo, el código QR para abrirlo en el móvil (BASE-F132),
«Mejorar plan» (solo el propietario) y «Gestionar en erplora.com». Las entradas van antes que el pie: si el menú no tiene
alto para las dos cosas, el código se pliega a una fila que lo enseña al tocarla.

### «Mejorar plan»
Al pie del menú lateral, entre el código QR y «Gestionar en erplora.com». Abre la página del plan de este negocio en
erplora.com, en una pestaña nueva y ya dentro con su cuenta, sin volver a escribir la contraseña. Solo lo ve el
propietario, el único que cambia el plan en erplora.com, y solo en el navegador: en la app instalada no está.

### «Gestionar en erplora.com»
Al pie del menú lateral, justo debajo de «Mejorar plan» (si lo hay), con el icono de enlace externo; con el menú plegado a sus
iconos (escritorio), queda solo el icono, que dice «Gestionar en erplora.com» al pasar por encima. Abre este negocio en
el panel de erplora.com, ya dentro con su cuenta: en una pestaña nueva en el navegador y, en la app instalada, en el
navegador del dispositivo.
Solo lo tienen el propietario, el administrador y el encargado, y solo si entraron con su cuenta: nunca en una sesión
abierta con PIN o con la placa. No vende, así que también está en la app instalada, salvo en la de Google Play.

### El menú de usuario
Se abre tocando a la persona, arriba del menú lateral. Primero «Perfil» y, en una caja compartida de un negocio
que pide PIN, «Cambiar de usuario»; después, solo si se entró con la cuenta (nunca en una sesión de PIN), «Mi
cuenta», que abre esa página en erplora.com (en una pestaña nueva; en la app instalada, en el navegador del
dispositivo), y «Reportar un problema», que abre un formulario en una ventana sin salir del hub (BASE-F108); al
final «Tema» (claro, oscuro o el del sistema) y «Cerrar sesión». Las dos salen también en la app instalada:
ninguna vende nada.

### El aviso «Todavía no puedes facturar»
Mientras falta un paso que impide facturar, la campana lleva el aviso urgente «Todavía no puedes facturar», en
cualquier pantalla (también en el Inicio) y sin ocupar sitio en ninguna: «No se podrá emitir ningún tique ni factura
hasta que configures esto: Los datos de tu negocio.», con «Configurar los datos del negocio» y, si falta otro paso,
un segundo botón con el suyo («Configurar VeriFactu»). A quien no puede configurarlo le dice, sin botones, «Esto lo
tiene que configurar un administrador.». Se va solo en cuanto el paso queda hecho, en cualquier dispositivo.

### Apps
Desde «Apps» en el menú lateral. Tres pestañas abajo: «Mis apps» (las apps que el negocio tiene en marcha),
«Añadir apps» (todas las apps de ERPlora) y «De pago» (las que se contratan aparte). Arriba, cuántas apps tiene
activadas el negocio y cuántas de las que deja su plan ha elegido: «27 apps activadas · 17 de 20 de tu plan».
Cada pestaña, una tabla (o tarjetas) con su buscador, el embudo de filtros, el orden y «Columnas»: «App» (icono y
nombre), «Categoría» y «Estado»; en «Añadir apps» y «De pago», además «Descripción», «Precio» y «Viene con».
«Abrir» en la fila de una app que la persona puede abrir y, para quien administra, «Activar» o «Desactivar».
«De pago» y «Precio» solo salen si alguna app se contrata aparte; hoy ninguna: todas van en todos los planes.

#### La cuenta de apps y los avisos
Cuentan las de «Mis apps», también las que nacen activadas, como Impuestos, y las que llegaron con otra. Sin límite:
«27 apps activadas · Sin límite». Un negocio recién dado de alta: «1 app activada · 0 de 20 de tu plan» (hub#1286).
Encima de la tabla, cuando toca, el aviso del límite del plan o el de por qué no se ha cambiado una app.

### La pantalla de una app que no se abre
En la misma dirección de la pantalla de la app, el motivo: «Suscripción necesaria» o «Esta app no está
disponible en este negocio», con «Ir a Apps» (y «Mejorar plan» para el propietario, en el
navegador).

### Sin acceso
En la misma dirección de una pantalla que el rol de la persona no abre, un candado con «No tienes acceso a esta
pantalla» — «Tu rol en este negocio no la abre.», los nombres de quien puede darle acceso, cada uno con su avatar, y
«Ir al Inicio».

### Ajustes · Negocio
La segunda pestaña de las de abajo de «Ajustes» («General», «Negocio», «Impresión» y «Datos y copias»). La
tarjeta «Tu negocio» enseña, sin campos que rellenar, «Nombre del negocio», «País», «Zona
horaria» (con la hora que es allí), «Moneda» e «Idioma del negocio», cada uno con una línea que dice para qué
sirve. Debajo, dónde se cambian y, para el propietario y el administrador, «Cambiar en erplora.com» (en la app instalada, en el navegador del dispositivo; en la de Google Play no está). Más abajo,
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
- **Restablecer**: «Deshacer una importación», con una fila por importación que se puede deshacer,
  «Restablecer el negocio», con lo que tiene cada sección, y «Copias de los datos», con las copias que se guardan
  y su «Descargar».

### Sistema · Uso y plan
Desde «Sistema» en el menú lateral, que solo tiene quien administra el negocio. Cuatro pestañas abajo: «Uso y plan»,
«Actualizaciones», «Eventos caídos» y «Registros»; se abre «Uso y plan»: su plan con «Mejorar plan» (para el
propietario), una línea
que dice si le alcanza o tiene que ampliar y por qué, «Lo que incluye tu plan», de lo más lleno a lo menos, con su barra,
y «Para tu información», con las cifras que ningún plan limita.

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
foto), «Preferencias» (idioma y apariencia: paleta, tema y tamaño de interfaz del 80 al 120%, por defecto 100%) y
«PIN».

### Ajustes · General
Lo que se abre con «Ajustes» en el menú lateral: la primera pestaña de abajo, «General», con «Este dispositivo»
(en la app de ERPlora de un ordenador, también «Arrancar al iniciar sesión»), «Pinpad», para quien administra
«Dispositivos» y, al final, la tarjeta de la documentación de la API.

### Estamos preparando tu negocio
La página que sale en la dirección de un negocio que erplora.com aún está preparando; se actualiza sola.

### Archivos
Desde «Archivos» en el menú lateral; la ve todo el equipo. A la izquierda, «Carpetas»: el árbol de carpetas del
negocio, que empieza en «Archivos» (lo de arriba del todo), con la carpeta abierta resaltada; en una pantalla
estrecha, el árbol se pliega en el selector «Carpetas». A la derecha, «Buscar archivos…», «Lista» y «Cuadrícula» y,
para quien administra el negocio, «Nueva carpeta» y «Subir archivo» (solo su nube). Debajo, lo que hay en la carpeta abierta: pulsar
un archivo lo abre.

#### La carpeta abierta
Arriba, la ruta de la carpeta, con ⋮ al lado para renombrar, mover o eliminar esa carpeta; «Espacio», con lo usado y
el límite del plan («{used} de {limit}») o «{used} usados · Sin límite»; y lo que hay en la carpeta: primero las
carpetas y luego los archivos, cada uno con su icono, su nombre, su tamaño (en la lista, también cuándo cambió) y su ⋮:
«Abrir», «Descargar», «Renombrar», «Mover a…» y «Eliminar». En la lista, cada nombre ocupa una línea: lo que no cabe se
corta con «…» y la extensión se ve siempre entera; en el móvil, el tamaño y la fecha van debajo del nombre, en gris.
Pulsar un archivo lo abre en el visor, con su nombre, «Descargar» y «Cerrar» («Ampliar» y «Reducir» en imágenes y PDF).

### Empleados · Personal
Lo que se abre con «Empleados» en el menú lateral: la primera pestaña de abajo, «Personal», con las plazas del plan,
«Invitar en erplora.com» para quien administra (en la app instalada, en el navegador del dispositivo; en la de Google Play no está), «Las personas se invitan, se les cambia el rol y se quitan en
erplora.com, en «Miembros» del negocio.» y la tabla de personas (en el móvil, una tarjeta por persona). Las otras
pestañas: «Roles» y, solo para quien administra, «API keys» y «Aprobaciones»; cada una en la dirección, así que
«Atrás» sale de Empleados.

### Empleados · Roles
Los cinco roles de erplora.com y, debajo, los propios del negocio, con «Básico» o «Propio», cuántas personas los
tienen y cuántos permisos dan; uno propio con permisos nuevos lleva «Por revisar». Tocar uno abre «Qué permite». Quien
gestiona los roles tiene «Nuevo rol» arriba y, en cada fila, «Duplicar»; en los propios, también «Editar» y «Borrar»
en «⋮».

### Empleados · Roles · Qué permite
Un rol: cuántas personas lo tienen y, en un panel por app encendida, cada permiso con su frase
y si lo da («Permitido»), lo deja hacer con la aprobación de un responsable («Con aprobación») o no («No»). Es de solo
lectura, salvo uno propio para quien gestiona los roles, que ahí mismo le cambia el nombre, la descripción y lo que
permite, y pulsa «Guardar».

### Empleados · API keys
Las llaves con las que otro sistema llama a la API del negocio: «Nueva API key», la tabla de llaves y, al pie, el
enlace a la documentación de la API.

### Empleados · Aprobaciones
El registro, solo de lectura, de las acciones que pueden necesitar la aprobación de un responsable: quién la hizo y
quién se la aprobó, o que la hizo por su cuenta alguien a quien su rol se lo permite.

### Ficha de una persona
Desde una fila de **Empleados › Personal**, para quien administra, con el botón de volver: «Sus datos» (con «Abrir
en erplora.com»), «PIN» y «Placa».

### Hace falta una aprobación
Sobre la pantalla en la que se intentó la acción: qué se aprueba, «¿Quién lo aprueba?» con las caras y el teclado
(entero y sin desplazar en el móvil, la tableta y el escritorio), y «Cancelar».

### Documentación de la API
Con el botón de volver: cómo se llama a la API, «Descargar el fichero OpenAPI» y una sección por app con sus llamadas.

### Asistente
El panel que se abre con los destellos «Asistente» de la barra de arriba (en un móvil, dentro de «⋮», junto a «Mis apps»), a la
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
| Cargando | La fila de cómo está funcionando el negocio en gris, baldosas grises en «Mis apps» («Cargando tus apps…» para el lector de pantalla), la lista en gris, «Cargando widgets…» en el tablero, la cifra de cada panel en gris y «Cargando…» en «Actividad»; «Cargando…» en el pinpad, «Cargando tu perfil…» y «Cargando los dispositivos…». |
| Vacío | «Aquí aparecerán tus apps. Añade las que necesite tu negocio.»; sin pasos, la lista no sale; «Panel vacío. Pulsa ⋮ para añadir widgets.»; un panel sin datos, «Sin datos»; el panel de la campana, «Todo al día» y «No queda nada que requiera acción.»; «Todavía no ha entrado nadie desde ningún dispositivo.»; en «Cambiar de usuario», «Aquí nadie tiene PIN todavía: se pone en Mi perfil o en Empleados.». |
| Error | Cada zona falla por su cuenta: «No hemos podido comprobar cómo está funcionando tu negocio.» con «Reintentar», «No se han podido cargar tus apps. Recarga la página; si sigue fallando, vuelve a iniciar sesión.», «No se ha podido cargar lo que te falta por configurar» con «Reintentar», «No se han podido cargar los paneles» con «Reintentar», un panel con «No disponible» (nunca la cifra de antes), «No se han podido cargar las últimas ventas» con «Reintentar» y, en el panel de la campana, «No se pudieron cargar los avisos» con «Reintentar» o, si ya tenía avisos, «No se pudieron actualizar los avisos. Lo que ves puede no estar al día.» con los de antes. En el acceso: «No se pudo cargar el pinpad. Puedes entrar con tu cuenta.», «No se pudo cargar el perfil» con «Reintentar», «No se pudo cargar este dispositivo. Comprueba la conexión e inténtalo de nuevo.», «No se pudo cargar cómo pide el PIN el negocio. Comprueba la conexión e inténtalo de nuevo.» y «No se pudieron cargar los dispositivos. Comprueba la conexión e inténtalo de nuevo.». En la app de un ordenador, «No se pudo cambiar el ajuste de arranque al iniciar sesión.» (BASE-F120). |
| Sin permiso | Un paso que la persona no puede hacer: sin botón y «Esto lo tiene que configurar un administrador.». Un panel o un contador que no puede ver, no sale. En Ajustes, quien no administra ve «Este dispositivo» y «Pinpad» con los controles apagados («Solo un administrador puede cambiar cómo entra la gente en este dispositivo.», «Solo un administrador puede cambiar si se pregunta.»), salvo «Arrancar al iniciar sesión», que es del ordenador y no del negocio, y, en lugar de la lista, «Solo un administrador puede ver y quitar los dispositivos.». Una pantalla que su rol no abre, de una app o de la plataforma (como «Sistema»), abierta por su dirección: «Sin acceso» (BASE-F118). |

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
| Sin permiso | Lo que la persona no puede hacer con sus botones, el asistente tampoco: no se le ofrece y, si lo intenta, el recibo dice «No se hizo, sin permiso: …». Con los mensajes del mes agotados, quien no es el propietario ve «Pídele al propietario del negocio que mejore el plan.» en lugar de «Mejorar plan». |

En la pantalla Ajustes · Datos y copias:

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando plantillas…»; en «Exportar» y «Restablecer», las filas en gris. |
| Vacío | «Todavía no hay plantillas para tu negocio.», «Ninguna plantilla coincide con tu búsqueda.», «Este negocio no tiene ninguna app encendida que exportar.» y «No hay nada que restablecer: ninguna sección tiene datos.». |
| Error | «No se han podido cargar las plantillas ahora mismo. Puedes importar un archivo igualmente.» con «Reintentar»; «No se han podido cargar las apps de este negocio.» y «No se ha podido calcular lo que tiene cada sección.», con «Reintentar». |
| Sin permiso | Quien no administra el negocio no tiene la pestaña «Datos y copias»: su dirección le abre «General» (BASE-F48), y la tarjeta de plantillas del Inicio no sale. Un administrador, en «Restablecer», deshace importaciones y, en lugar de «Restablecer el negocio» y «Copias de los datos», lee «Solo el propietario del negocio puede restablecerlo o descargar las copias de sus datos.». |

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
| BASE-F02 | Ver el negocio de un vistazo al entrar | hecho |
| BASE-F03 | Ir a configurar desde «Termina de configurar tu negocio» | hecho |
| BASE-F04 | Ver qué pasos de la lista tiene que configurar un administrador | hecho |
| BASE-F05 | Abrir una app desde «Mis apps» | hecho |
| BASE-F06 | Ver los paneles de las apps en Inicio | hecho |
| BASE-F07 | Personalizar el tablero de paneles | hecho |
| BASE-F08 | Mantener los paneles al día sin recargar | hecho |
| BASE-F09 | Consultar la actividad reciente | hecho |
| BASE-F10 | Ver en la campana los avisos entre apps que no se entregaron | hecho |
| BASE-F11 | Ir a erplora.com a gestionar o mejorar el plan | hecho |
| BASE-F12 | Pedirle al asistente que repase la configuración | hecho |
| BASE-F13 | Cambiar de rol o salir del negocio con el hub abierto | hecho |
| BASE-F14 | Ver las apps del negocio | hecho |
| BASE-F15 | Abrir una app desde Apps | hecho |
| BASE-F16 | Buscar una app en el catálogo | hecho |
| BASE-F17 | Saber cuánto cuesta una app antes de tenerla | hecho |
| BASE-F18 | Activar una app | hecho |
| BASE-F19 | Saber qué más viene con una app | hecho |
| BASE-F20 | Intentar usar una app que necesita suscripción | hecho |
| BASE-F21 | Ver por qué no se ha podido activar una app y reintentarlo | hecho |
| BASE-F22 | Seguir la activación de una app mientras se navega | hecho |
| BASE-F23 | Desactivar una app | hecho |
| BASE-F24 | Volver a activar una app | hecho |
| BASE-F25 | Ver que una app se niega a desactivarse | hecho |
| BASE-F26 | Entender por qué una app no se abre | hecho |
| BASE-F27 | Ver una app de pago bloqueada | hecho |
| BASE-F29 | Elegir una plantilla del catálogo para importar | hecho |
| BASE-F30 | Subir un fichero para importar | hecho |
| BASE-F31 | Revisar y cargar lo que trae el fichero | hecho |
| BASE-F32 | Leer el informe de la importación | hecho |
| BASE-F33 | Volver al informe de una importación que no entró entera y reintentar | hecho |
| BASE-F34 | Deshacer una importación | hecho |
| BASE-F35 | Exportar una copia de seguridad o una plantilla | hecho |
| BASE-F36 | Elegir qué apps, datos y tablas viajan en la exportación | hecho |
| BASE-F37 | Restablecer el negocio por secciones | hecho |
| BASE-F38 | Ver Inicio al día después de importar una plantilla | hecho |
| BASE-F39 | Abrir Sistema y moverse por sus pestañas | hecho |
| BASE-F40 | Ver lo que usa el negocio y si tiene que ampliar el plan | hecho |
| BASE-F41 | Saber qué versión corre y cuándo se actualizó | hecho |
| BASE-F42 | Ver el registro de sucesos del sistema | hecho |
| BASE-F43 | Ver los eventos caídos | hecho |
| BASE-F44 | Reenviar un evento caído | hecho |
| BASE-F45 | Reenviar todos los eventos caídos | hecho |
| BASE-F46 | Descartar un evento caído | hecho |
| BASE-F47 | Informar de un error de la pantalla sin que nadie lo pida | hecho |
| BASE-F48 | Abrir Ajustes y moverse por sus pestañas | hecho |
| BASE-F49 | Ver el país del negocio | hecho |
| BASE-F50 | Ver la moneda del negocio | hecho |
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
| BASE-F74 | Previsualizar y descargar un archivo | hecho |
| BASE-F75 | Mover y renombrar un archivo o una carpeta | hecho |
| BASE-F76 | Borrar un archivo o una carpeta | hecho |
| BASE-F77 | Llegar al tope de personas del plan | hecho |
| BASE-F78 | Retirar el PIN a una persona | hecho |
| BASE-F79 | Dar de alta o retirar la placa de una persona | hecho |
| BASE-F80 | Reincorporar a una persona que salió del negocio | hecho |
| BASE-F81 | Entender cómo entra cada persona | hecho |
| BASE-F82 | Ver los roles del negocio y lo que permite cada uno | hecho |
| BASE-F83 | Asignar un rol básico a una persona | hecho |
| BASE-F84 | Aprobar con el PIN de un responsable | hecho |
| BASE-F85 | Consultar quién aprobó qué | hecho |
| BASE-F86 | Crear una llave de API y copiar su token | hecho |
| BASE-F87 | Rotar una llave de API | hecho |
| BASE-F88 | Revocar una llave de API | hecho |
| BASE-F89 | Ver las llaves de API y qué puede cada una | hecho |
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
| BASE-F109 | Borrar un negocio eliminado pasados sus 90 días | hecho |
| BASE-F110 | Abrir la web del negocio por su dominio propio | hecho |
| BASE-F111 | Esperar a la base de datos cuando se corta un momento | hecho |
| BASE-F112 | Guardar un archivo descargado dentro de la app | hecho |
| BASE-F113 | Seguir avisando con la pantalla apagada (app de Android) | hecho |
| BASE-F114 | Devolver un negocio a un momento pasado desde el admin de Hubs | hecho |
| BASE-F115 | Ver la ayuda de la pantalla en la que se está | hecho |
| BASE-F116 | Leer las novedades de ERPlora | hecho |
| BASE-F117 | Ver en la campana que el plan tiene una factura sin pagar | hecho |
| BASE-F118 | Abrir una pantalla sin permiso: «Sin acceso» y a quién pedirlo | hecho |
| BASE-F119 | Lo que se ve según los permisos de dato | hecho |
| BASE-F120 | Arrancar ERPlora al iniciar sesión en el ordenador | hecho |
| BASE-F126 | Encender o apagar el acceso de soporte de ERPlora | hecho |
| BASE-F127 | Crear un rol propio a partir de otro | hecho |
| BASE-F128 | Ajustar lo que permite un rol propio | hecho |
| BASE-F129 | Borrar un rol propio | hecho |
| BASE-F130 | Dar un rol propio a una persona | parcial |
| BASE-F131 | Ver en la campana los roles por revisar | hecho |
| BASE-F132 | Abrir el Hub en el móvil con el código del menú lateral | hecho |

### BASE-F01 Ver lo que le falta por configurar al negocio
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Inicio · Resumen, El aviso «Todavía no puedes facturar»
Pasos:
  1. Entra en el Inicio. En «Termina de configurar tu negocio» ve cuántos pasos lleva hechos y una barra.
  2. Debajo, los pasos que faltan: primero los que impiden facturar («Necesario para facturar», en rojo) y
     luego los «Importante», cada grupo en el orden que fijan las apps, también en el móvil, donde solo caben
     dos filas. Los «Recomendado» salen plegados solo si no queda otra cosa. «Ver todo» enseña todos los pasos,
     también los hechos, en el orden que fijan las apps.
  3. Los de la plataforma son «Tus apps» (encender al menos una app de negocio; Impuestos, con la que nace todo
     negocio, no cuenta, porque con ella sola el TPV no tiene nada que vender) y «Tu equipo» (añadir a las personas
     que usarán el TPV); el resto los trae cada app encendida.
  4. Además, por cada app obligatoria en el país del negocio que está desactivada, un paso «Importante» de la
     plataforma: «Activa VeriFactu» con «Es obligatoria para los negocios de España.» (VeriFactu, en España) o «Activa
     Impuestos» con el país del negocio (Impuestos, en todos). Solo lo ve quien administra el negocio, que es quien
     activa apps; «Configurar» lleva a **Apps**, a «Añadir apps». En cuanto la activa, el paso se va solo y llegan los
     de la propia app («Configura VeriFactu», «Tus impuestos»). Un negocio de otro país no ve el de VeriFactu. Un
     negocio recién dado de alta no ve «Activa Impuestos», porque nace con ella activada; en España sí ve «Activa
     VeriFactu»: VeriFactu nunca se activa sola.
  5. Un paso que solo vale para otro país, o que la persona no puede ver, no sale. Un negocio sin país (una demo, el de
     ERPlora) cuenta como España, el mercado de ERPlora: ve los pasos de España y ninguno de otro país. Un paso cuya
     comprobación falla tampoco sale: nunca se da por hecho ni por pendiente lo que no se pudo comprobar.
  6. Mientras falta un paso «Necesario para facturar», la campana lleva el aviso «Todavía no puedes facturar», con
     el botón de ese paso («Configurar los datos del negocio»), en cualquier pantalla.
  7. Cuando otra persona completa un paso en otro dispositivo, o activa una app, la lista se pone al día sola.
Entra: los pasos que declara cada app encendida, con su comprobación, su país, su permiso y su pantalla; y los
países donde cada app dice que es obligatoria.
Sale: nada guardado.
Si falla: «No se ha podido cargar lo que te falta por configurar» con «Reintentar». Un paso que es cosa
nuestra (no hay ninguna app de negocio que encender) sale como «Todavía no disponible» con «Esto es cosa
nuestra: por tu parte no hay nada que hacer aún. Estamos en ello.».
Implicados: INVENTORY-F28, BASE-F24, BASE-F25, VERIFACTU-F01, TAX-F17, BASE-F14

### BASE-F02 Ver el negocio de un vistazo al entrar
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Inicio · Resumen
Pasos:
  1. Tras entrar se abre el Inicio (también desde «Inicio» en el menú lateral).
  2. Arriba, el nombre del negocio (el de erplora.com) y «Hoy» con la fecha larga en el idioma de la
     aplicación; mientras el negocio no tiene nombre, «Buenos días», «Buenas tardes» o «Buenas noches».
  3. Para quien administra el negocio, bajo el saludo, una fila con cómo está lo que el negocio necesita para
     trabajar y «Ver sistema», que lleva a Sistema. Cada app encendida que la persona puede ver dice lo suyo en una
     etiqueta de color: verde lo que funciona, ámbar lo que hay que arreglar y gris lo que no se pudo comprobar. Con
     Impresión, «Impresora lista» si el dispositivo que saca los tiques ha dado señales en el último minuto y medio,
     «Impresora sin conectar» si está dado de alta pero no responde, o «Impresora sin configurar» si no hay ninguno;
     las dos últimas con «Configurar la impresión», que abre Impresión. Con la Bandeja de WhatsApp, «WhatsApp
     conectado», «Hay que volver a conectar WhatsApp» si WhatsApp lo pide, o «WhatsApp sin conectar» si no hay número
     conectado; las dos últimas con «Conectar WhatsApp», que abre los ajustes de la Bandeja. La fila se vuelve a
     comprobar cada vez que se vuelve al Inicio. Sin ninguna app encendida que diga cómo está, no hay fila. Quien no
     administra el negocio no la ve.
  4. Debajo, en este orden: «Empieza con un negocio como el tuyo» (solo mientras el negocio está vacío y
     para quien lo administra), «Mis apps», «Termina de configurar tu negocio» y el tablero de
     paneles.
  5. Al cambiar el idioma de la interfaz, los nombres de «Mis apps» y los textos del checklist cambian en el
     sitio, sin recargar ni reabrir la aplicación.
  6. Abajo, dos pestañas: «Resumen» (lo anterior) y «Actividad».
Entra: el nombre del negocio, la fecha del dispositivo y lo que cada app encendida dice de sí misma.
Sale: nada guardado.
Si falla: una zona que no carga no tumba las demás; cada una dice lo suyo. En el móvil las zonas se
apilan y «Mis apps» se pliega. Lo que no se pudo comprobar sale en neutro, nunca como listo y sin botón,
porque no es tarea de quien mira: «No hemos podido comprobar la impresora», «No hemos podido comprobar WhatsApp». Si
no se puede leer la fila entera: «No hemos podido comprobar cómo está funcionando tu negocio.» con «Reintentar».
Implicados: PRINTING-F21, WHATSAPP_INBOX-F01, WHATSAPP_INBOX-F02, BASE-F38

### BASE-F03 Ir a configurar desde «Termina de configurar tu negocio»
Estado: hecho
Actor: propietario, administrador, responsable
Pantalla: Inicio · Resumen
Pasos:
  1. En «Termina de configurar tu negocio», un paso pendiente que la persona puede hacer lleva
     «Configurar».
  2. Pulsa «Configurar»: se abre la pantalla de la app que completa ese paso.
  3. Al volver al Inicio, la lista ya cuenta el paso como hecho si se completó.
  4. Mientras el negocio está vacío, quien lo administra empieza más arriba, en «Empieza con un negocio como el
     tuyo»: «Ver todas las plantillas» abre «Datos y copias», donde se carga una plantilla o una copia.
Entra: la pantalla que cada paso declara.
Sale: nada desde aquí.
Si falla: mientras esa pantalla no existe en el hub, el paso sale sin «Configurar» (un botón que lleva a
«no encontrado» es peor que ninguno).
Implicados: BASE-F38

### BASE-F04 Ver qué pasos de la lista tiene que configurar un administrador
Estado: hecho
Actor: responsable, empleado
Pantalla: Inicio · Resumen, El aviso «Todavía no puedes facturar»
Pasos:
  1. Un paso que impide facturar y que esta persona no puede hacer sigue en su lista, con su etiqueta
     «Necesario para facturar», y en el aviso «Todavía no puedes facturar» de la campana.
  2. No lleva «Configurar»: dice «Esto lo tiene que configurar un administrador.».
  3. Los pasos que no impiden facturar y que esta persona no puede hacer no salen en su lista.
Entra: los permisos de la persona en este negocio.
Sale: nada.
Si falla: si no se puede comprobar ese paso, no sale.
Implicados: ninguno

### BASE-F05 Abrir una app desde «Mis apps»
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Inicio · Resumen, la barra de arriba de cualquier pantalla
Pasos:
  1. En «Mis apps», una baldosa por app que esta persona puede abrir, con su icono y su nombre (si no
     cabe, el nombre entero sale al pasar por encima). Una app sale si su rol le deja abrir al menos una de sus
     pantallas. Un empleado tiene las de su trabajo diario: Ventas / TPV, Caja, Mesas, Cocina, Reservas, Reservas
     online, Citas, Clientes, Inventario, Facturación, VeriFactu, Servicios, Personal, Control horario, Tareas,
     Carrito y pago y la Bandeja de WhatsApp, y Automatizaciones para contestar lo que le pregunta una automatización.
     Las que configuran el negocio (Impuestos, Tarifas, Suplementos, Menús y combos, Pagos, Horarios, Impresión y
     Página web) son de quien las gestiona: el empleado no las tiene, aunque el TPV y el asistente sigan usando lo que
     leen de ellas.
  2. Las más abiertas en este navegador van primero.
  3. Toca una baldosa: se abre la primera pantalla de la app que la persona puede abrir. Una app que se está
     encendiendo dice «Activando…» y no abre nada.
  4. En el móvil, con seis apps o más, se ven las cuatro primeras y «Ver todas las apps», que enseña el
     resto. «Añadir apps», la última, lleva a Apps.
  5. Para salir de una app, toca «Mis apps» en la barra: la pantalla principal de una app no tiene
     «Atrás». La hoja empieza por «Inicio», que vuelve al Inicio, y sigue con las apps; tocar una la abre.
     «Inicio» está ahí aunque la lista aún cargue, esté vacía o no se haya podido leer.
  6. En la aplicación de Android, el botón atrás del móvil cierra primero lo que haya abierto encima (una ventana, una
     hoja o el menú); una ventana que no se puede cerrar así se queda, y una de alta, de edición o de anulación con algo
     escrito sin guardar pregunta antes «¿Descartar los cambios?»: «Seguir editando», o atrás otra vez, la deja como
     estaba, y «Descartar cambios» la cierra. Esas mismas ventanas hacen la misma pregunta al pulsar «Cancelar»,
     «Cerrar», la «×» o Escape y al tocar fuera, en el móvil y en el ordenador, y sin nada escrito se cierran sin
     preguntar. Sin nada abierto, en una ficha o un alta hace lo mismo que «Atrás»; en la pantalla principal de una app
     vuelve al Inicio, también si se llegó a ella por un enlace; y en el Inicio deja la aplicación en segundo plano.
Entra: las apps del menú de la persona (las mismas del botón «Mis apps» de la barra).
Sale: cuántas veces se abre cada app en este navegador (solo para ordenar).
Si falla: mientras carga, baldosas grises y «Cargando tus apps…» para el lector de pantalla. Sin apps:
«Aquí aparecerán tus apps. Añade las que necesite tu negocio.». Si no se pudo leer la lista: «No se han
podido cargar tus apps. Recarga la página; si sigue fallando, vuelve a iniciar sesión.», nunca que no
hay apps. En una aplicación de Android antigua, que aún no sabe quedarse en segundo plano, el botón atrás
vuelve a ser el del sistema. Tras una actualización de ERPlora, una pantalla que esa pestaña aún no había abierto
se abre igual (desde una baldosa, «Mis apps», el menú o cualquier botón), en una carga nueva de la página, que ya
trae la versión nueva; nunca se queda el toque sin hacer nada. Si el servidor no responde (sin conexión o con la red
inestable), la persona se queda donde estaba y un aviso dice «No se ha podido abrir Reservas. Comprueba la conexión e
inténtalo de nuevo.» («esa página» si la pantalla no es de una app), con «Reintentar», que vuelve a probar y la abre
en cuanto el servidor responde.
Implicados: INVENTORY-F01, INVENTORY-F02, SALE-F35, TABLE-F01, KITCHEN-F01, CUSTOMER-F01, RESERVATION-F06, APPOINTMENT-F01, STAFF-F01, SERVICE-F01, ATTENDANCE-F08, CART_CHECKOUT-F01, CASH_REGISTER-F02, COMBO-F02, INVENTORY-F06, MODIFIER-F02, PAYMENT-F01, PRICING-F02, INVOICE-F03, PRINTING-F03, SCHEDULE-F04, TASK-F01, TAX-F02, WHATSAPP_INBOX-F29, BASE-F86, ONLINE_BOOKING-F05, PAYMENT-F05, PRINTING-F14, RESERVATION-F09, SERVICE-F17, VERIFACTU-F30, BASE-F73, BASE-F75, INVENTORY-F09, TASK-F09, TASK-F10, TASK-F13, CUSTOMER-F18, KITCHEN-F22, BASE-F46

### BASE-F06 Ver los paneles de las apps en Inicio
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Inicio · Resumen
Pasos:
  1. Bajo la lista está el tablero, con sus paneles desde que se abre el Inicio («Cargando widgets…» solo mientras
     no se sabe cuáles le tocan).
  2. Cada panel es una tarjeta con su título e icono: una cifra (con lo que cuenta bajo el título, si su app lo
     dice), una lista con barras, una cronología, un gráfico o un trozo de la pantalla de su app, con sus textos en
     el idioma de quien mira. Cada cifra lleva el color de su medida, el mismo en todas las pantallas: ventas,
     tickets e inventario, cada una el suyo. Las primeras cifras del tablero que tienen color lo encabezan en una
     fila de color, una por color y de dos a cuatro; las demás van en una tarjeta clara con el color en su icono,
     en el orden elegido. En el teléfono las cifras van de dos en dos. Una cifra con un estado que vigilar (la cola
     de contingencia de VeriFactu cuando algo espera o ya ha fallado) lo dice en una etiqueta naranja o roja con
     icono, sin cambiar el color de la cifra. En una lista con barras, cada barra mide lo grande que es su cifra frente a la mayor
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
  6. Solo salen los paneles de las apps encendidas que esta persona puede ver, y no sale ninguno cuya cifra es un
     dato que su rol no ve.
Entra: los paneles que declara cada app encendida; los datos de cada uno, pedidos con los permisos de
quien mira.
Sale: nada guardado en el hub.
Si falla: un panel sin datos dice «Sin datos» (una cifra, con una raya en su sitio); una cifra cuyos datos no se
pueden leer dice «No se pudo cargar» con «Reintentar», que la vuelve a pedir, y cualquier otro panel, «No
disponible»: nunca una cifra vieja o inventada. Una fila de una lista con barras (o un día de un gráfico) que no tiene cifra,
como una sesión de caja cerrada sin recuento, sale con una raya (—) y sin barra, nunca como un cero; un cero
de verdad sí sale como cero (0,00 €). Si no se puede leer el tablero: «No se han podido cargar los paneles»
con «Reintentar».
Implicados: BASE-F119

### BASE-F07 Personalizar el tablero de paneles
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
ofrezca paneles: «Ninguna app activa ofrece widgets todavía.».
Implicados: ninguno

### BASE-F08 Mantener los paneles al día sin recargar
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
Si falla: si los datos nuevos no llegan, el panel dice «No disponible» (una cifra, «No se pudo cargar» con
«Reintentar»), no el valor de antes; cuando vuelve la conexión, se pone al día solo.
Implicados: ninguno

### BASE-F09 Consultar la actividad reciente
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
     tarjetas o elige columnas; 15 por página. Una venta cobrada con varios medios dice todos en «Método»
     («Efectivo + Tarjeta»); el filtro de método ofrece cada medio una vez y la encuentra por cualquiera.
  4. Una venta cobrada en otro dispositivo aparece sola, sin recargar.
Entra: las ventas de la app Ventas, si está encendida, con los permisos de quien mira. Solo ventas: los
demás movimientos del negocio no salen aquí.
Sale: nada guardado.
Si falla: sin la app Ventas, la tabla vacía. Si no se pueden leer las ventas: «No se han podido cargar las
últimas ventas» — «Comprueba la conexión y vuelve a intentarlo.» con «Reintentar», en lugar de la tabla;
si ya había ventas en pantalla, se quedan debajo del aviso.
Implicados: SALE-F28

### BASE-F10 Ver en la campana los avisos entre apps que no se entregaron
Estado: hecho
Actor: propietario, administrador
Pantalla: La campana
Pasos:
  1. Un aviso entre apps (por ejemplo, «venta cobrada» hacia Facturación) agotó sus reintentos.
  2. La campana de un administrador sube en el momento, sin esperar ni recargar: el aviso urgente «2 eventos
     caídos», con «Una app no recibió lo que otra le mandó: lo que tenía que hacer sigue sin hacerse hasta que lo
     reenvíes.», llega como tarjeta y se recoge en ella.
  3. «Revisar los eventos» abre «Sistema» en «Eventos caídos», donde se reenvían o se descartan (BASE-F43).
  4. Cuando no queda ninguno (reenviados, descartados o ya hechos por otro camino), el aviso desaparece.
Entra: cuántos avisos de este negocio quedaron sin entregar, solo para quien administra el negocio.
Sale: nada.
Si falla: un empleado o un responsable no ve el aviso. Si no se puede preguntar, la campana se queda con
lo último que supo y su panel dice «No se pudieron actualizar los avisos. Lo que ves puede no estar al día.»; si
nunca lo supo: «No se pudieron cargar los avisos» con «Reintentar».
Implicados: BASE-F40

### BASE-F11 Ir a erplora.com a gestionar o mejorar el plan
Estado: hecho
Actor: propietario, administrador, responsable
Pantalla: El menú lateral, «Mejorar plan», «Gestionar en erplora.com»
Pasos:
  1. Al pie del menú lateral, bajo el código QR y alineado con él, está «Mejorar plan». Solo lo ve el
     propietario: en erplora.com solo el propietario cambia el plan y paga. Con el menú plegado a sus iconos
     (escritorio), queda solo su icono, que dice «Mejorar plan» al pasar por encima. Solo en el navegador: en la
     app instalada no está.
  2. Lo pulsa: se abre en una pestaña nueva la página del plan de este negocio en erplora.com, ya dentro con su
     cuenta: no vuelve a escribir la contraseña aunque ese navegador no tuviera abierta la sesión de erplora.com. Igual
     desde cualquier otro «Mejorar plan» del Hub: Sistema, Empleados, Apps, el panel del asistente y la Bandeja de WhatsApp.
  3. El propietario, el administrador o el encargado que entró con su cuenta tiene además, al pie del menú (justo
     debajo de «Mejorar plan», si lo tiene), «Gestionar en erplora.com», con el icono de enlace externo (en el menú
     plegado, solo el icono).
     No vende: también está en la app instalada, salvo en la de Google Play.
  4. Lo pulsa: se abre este negocio en el panel de erplora.com, ya dentro con su cuenta, en una pestaña nueva; en la
     app instalada, en el navegador del dispositivo. El Hub se queda donde estaba.
Entra: el negocio en el que está.
Sale: nada guardado en el hub. A erplora.com va un pase de un solo uso y de un minuto, de la cuenta de quien pulsa y de
este negocio; erplora.com vuelve a comprobar que esa cuenta es de este negocio.
Si falla: si el hub no sabe a qué negocio pertenece, ninguno de los dos sale (nunca un botón que no hace nada). Si la
app instalada no consigue abrir el navegador, lo dice: «No se ha podido abrir esa página. Inténtalo de nuevo.». Si el
pase no llega (el servidor da un error o no contesta en 8 segundos), se abre la dirección de siempre: erplora.com pide
entrar con la cuenta y sigue hasta el mismo sitio. Si el navegador bloquea la pestaña nueva, abre esa dirección el
propio enlace. Con el pase gastado o pasado el minuto, erplora.com lo dice y ofrece entrar y seguir allí; a una cuenta
que ya no es de este negocio le dice que no lo es (ACCOUNTS-F29). Un empleado, una sesión abierta con PIN o con la placa
y la app de Google Play no tienen «Gestionar en erplora.com». Quien no es el propietario no tiene «Mejorar plan» en
ningún sitio del Hub, ni la Tienda de erplora.com: el administrador, el encargado y el empleado no compran. En el negocio
propio de ERPlora, que no tiene plan ni compra nada, tampoco los tiene su propietario; «Gestionar en erplora.com», sí.
Implicados: BASE-F40, BASE-F104, WHATSAPP_INBOX-F13, ACCOUNTS-F29, BASE-F132

### BASE-F132 Abrir el Hub en el móvil con el código del menú lateral
Estado: hecho
Actor: cualquiera que haya entrado en el negocio
Pantalla: El menú lateral, «Ábrelo en el móvil»
Operaciones: ninguna
Pasos:
  1. Al pie del menú lateral, encima de «Mejorar plan» y «Gestionar en erplora.com», está el código QR de la dirección
     de este negocio, con «Ábrelo en el móvil» y cómo dejarlo en la pantalla de inicio del móvil. Sale a todo el mundo,
     sin permiso ni plan.
  2. Si el menú no tiene alto para sus entradas y el código a la vez (una tableta en horizontal, un portátil, un
     teléfono o la interfaz a un tamaño mayor en Mi perfil), las entradas se ven enteras y el código se pliega a una
     fila, «Ábrelo en el móvil», con el icono del QR. Al tocarla, el código sale encima de la página, sobre la fila; se
     cierra con Esc o tocando fuera, y el foco vuelve a la fila.
  3. Con el menú plegado a sus iconos (escritorio), queda solo el icono del QR, que dice «Ábrelo en el móvil» al pasar
     por encima; al pulsarlo, el menú se despliega.
  4. Escanea el código con la cámara del móvil y se abre la dirección de este negocio en su navegador.
Entra: la dirección del negocio.
Sale: nada guardado.
Si falla: si el código no se puede dibujar, en su lugar sale la dirección para escribirla en el móvil, también encima de
la página al tocar la fila.
Implicados: BASE-F11

### BASE-F12 Pedirle al asistente que repase la configuración
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Inicio · Resumen
Pasos:
  1. En «Termina de configurar tu negocio», pulsa «Pedírselo al asistente», sus destellos (o pregúntaselo desde su
     panel).
  2. El asistente lee la misma lista del Inicio, con lo que esa persona puede ver, y le dice qué falta y
     dónde se hace; cada paso sigue teniendo su «Configurar» en la lista. Si nombra la lista, la llama como sale
     en el Inicio, en el idioma de esa persona: «Te faltan 4 pasos de Termina de configurar tu negocio».
  3. De un paso hecho dice que está hecho, sin sacar una cifra, un nombre ni un ajuste de su texto, que dice lo que
     pide el paso y no lo que tiene el negocio: «Tu catálogo» está hecho porque ya hay productos, nunca «tienes uno».
     Si se le pregunta cuántos o cuál, lo lee en la app del paso (los productos activos, en Inventario).
Entra: la lista de lo que falta, con los permisos de quien pregunta.
Sale: nada guardado.
Si falla: sin asistente, los pasos siguen llevando a su pantalla desde la lista.
Implicados: BASE-F103, INVENTORY-F28

### BASE-F13 Cambiar de rol o salir del negocio con el hub abierto
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: cualquier pantalla del hub
Pasos:
  1. En erplora.com, quien gestiona el negocio le cambia el rol a una persona, la quita del negocio o le
     traspasa la propiedad; o en el Hub le da un rol propio o cambia lo que permite el suyo (BASE-F130, BASE-F128).
  2. Si le ha cambiado el rol, su sesión sigue abierta y lo que tiene abierto, en todos sus dispositivos,
     pasa en ese momento a lo que permite el rol nuevo, sin recargar ni volver a entrar: el menú, «Mis apps»
     y las pestañas enseñan solo lo que puede abrir; la pantalla que tiene delante pasa a «Sin acceso» si el
     rol nuevo no la abre, y la que le decía «Sin acceso» se abre si ahora puede.
  3. Si la han quitado del negocio, en ese momento se cierra su sesión en este negocio, en todos sus
     dispositivos: lo que tiene abierto deja de ponerse al día y lo siguiente que haga le pide volver a
     entrar; al volver, erplora.com le dice «No tienes acceso a este hub» y no entra. Sus sesiones en otros
     negocios siguen abiertas.
  4. Un traspaso de la propiedad cierra la sesión de las dos personas en este negocio (HUBS-F28): vuelven
     a entrar desde erplora.com y trabajan ya con su rol nuevo.
  5. Si cambia su contraseña, cierra la sesión en todas partes o borra su cuenta en erplora.com, se cierran
     todas sus sesiones del hub, en todos sus negocios.
Entra: el cambio que hizo erplora.com (quién, en qué negocio y con qué rol, o que ya no está).
Sale: su rol en el negocio, al día, y lo que tiene abierto con lo que ese rol permite; las sesiones de quien
ya no está en el negocio, cerradas.
Si falla: si el hub no responde en ese momento, erplora.com se lo vuelve a pasar al poco y el cambio llega
entonces. Un dispositivo sin conexión lo recibe al reconectar.
Implicados: HUBS-F26, HUBS-F27, HUBS-F28, BASE-F118, BASE-F128, BASE-F130

### BASE-F14 Ver las apps del negocio
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Apps
Pasos:
  1. Pulsa «Apps» en el menú lateral. Se abre en la pestaña «Mis apps»; «Añadir apps» y «De pago» tienen
     también su dirección, que se puede enlazar.
  2. Mientras llega la lista: «Cargando tus apps…». Después, una fila (o una tarjeta, a elegir) por cada app que
     el negocio tiene en marcha, con su icono y su nombre, su «Categoría» y su «Estado» («Activa»). Una app que el
     país del negocio exige lleva además, junto a su estado, «Obligatoria en España» (o el país del negocio): Impuestos
     en todos, VeriFactu en España. Un negocio recién dado de alta ya tiene Impuestos aquí, «Activa»: nace
     activada con los impuestos de su país y no cuenta para el tope de apps del plan: el contador de arriba dice
     «1 app activada · 0 de 20 de tu plan». Las demás apps nacen desactivadas, también VeriFactu, que activa el
     dueño.
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
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Apps
Pasos:
  1. En la fila de una app de «Mis apps», pulsa «Abrir».
  2. Se abre la primera pantalla de esa app que el rol de la persona le deja abrir.
Entra: el menú de la app y lo que la persona puede ver.
Sale: nada guardado.
Si falla: una app que la persona no puede abrir, o que no está en marcha, no lleva «Abrir» (no sale apagado: no
sale). Al pulsarlo se vuelve a comprobar, por si acaba de cambiar: si ya no está en marcha, no abre nada.
Implicados: ninguno

### BASE-F16 Buscar una app en el catálogo
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Apps
Pasos:
  1. En Apps, pulsa «Añadir apps» (todas las apps de ERPlora) o «De pago» (solo las que se contratan aparte).
  2. Mientras llega: «Cargando el catálogo…». Después, una fila por app con «App», «Categoría», «Descripción»,
     «Precio», «Viene con» y «Estado» («Activa» o «Necesita suscripción»), con los nombres y las
     descripciones en el idioma de quien mira. Una app que el país del negocio exige lleva «Obligatoria en España» (o
     el país del negocio) junto a su estado, también desactivada: así se ve cuál falta por activar.
  3. Busca en «Buscar apps para añadir…» (en «De pago», «Buscar apps de pago…») por nombre, descripción o
     categoría, y filtra por categoría o por estado.
Entra: las apps que trae el hub y lo que el negocio tiene contratado en erplora.com.
Sale: nada guardado.
Si falla: como en «Mis apps». Una búsqueda sin resultados: «No hay apps que coincidan con tu
búsqueda.».
Implicados: APPS-F01, BASE-F14

### BASE-F17 Saber cuánto cuesta una app antes de tenerla
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Apps
Pasos:
  1. En «Añadir apps» o «De pago», la columna «Precio» dice de cada app: «Gratis» (va con cualquier plan),
     «Incluida en tu plan», «Contratada», «Incluida con» y la app que la trae (una de pago que viene con otra que
     el negocio tiene) o «De pago».
  2. El importe de una app «De pago» está en la Tienda de erplora.com; quien administra el negocio la abre desde
     «Mejorar plan».
  3. «De pago» reúne solo las apps que se contratan aparte: una gratis nunca sale ahí. Si ninguna se vende
     aparte (hoy, todas van en todos los planes), no hay «De pago» ni «Precio», y un enlace a «De pago» abre
     «Añadir apps».
Entra: si cada app se contrata aparte y lo que el negocio tiene contratado en erplora.com.
Sale: nada guardado. El hub no cobra ni enseña importes: el precio y la compra son de erplora.com.
Si falla: sin la lista, como en «Mis apps».
Implicados: APPS-F01, APPS-F07, BASE-F14, BASE-F20

### BASE-F18 Activar una app
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
  1. Las apps que el negocio usa ya están en «Mis apps» y en el menú; una de pago aparece sola en los dos, sin
     recargar, en cuanto se contrata en erplora.com.
  2. En «Añadir apps», quien administra busca una app que el negocio no usa, «Desactivada», y pulsa «Activar». Si
     necesita otras apps que están desactivadas, antes le pregunta nombrándolas.
  3. La app pasa a «Activa» al momento y sale en «Mis apps» y, sin recargar, en el menú de todos los
     dispositivos del negocio. El contador de arriba suma las apps que se activan y una de las del plan: al activar
     Tareas, de «26 apps activadas · 16 de 20 de tu plan» a «27 apps activadas · 17 de 20 de tu plan»; las que
     llegan con ella suman a las activadas, no a las del plan.
Entra: la app elegida, las que necesita y lo que el negocio tiene contratado en erplora.com.
Sale: la app en marcha en este negocio, elegida por él: cuenta para el límite de apps de su plan.
Si falla: con el límite del plan alcanzado no se activa nada y sale «El límite de apps de tu plan»: «Has llegado al
límite de 20 apps de tu plan. Mejora el plan o desactiva una.», con «Mejorar plan» para el propietario en el
navegador (en la app instalada no sale). El límite nunca frena una app que el país del negocio exige (VeriFactu en
España): se activa aunque el plan esté en su límite. Una app de pago sin contratar no ofrece «Activar». Una app que
este negocio no puede usar tampoco: sale «No disponible» y, para quien administra, el motivo debajo («VeriFactu solo
es para negocios de España.»). Cualquier otro fallo sale en un aviso con el nombre de la app y el
motivo, que se queda hasta cerrarlo.
Implicados: APPS-F07, VERIFACTU-F01, BASE-F19, BASE-F20

### BASE-F19 Saber qué más viene con una app
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
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Apps
Pasos:
  1. Una app de pago que el negocio no tiene contratada sale en «Añadir apps» y en «De pago» con «Necesita
     suscripción», y no está en «Mis apps» ni en el menú.
  2. El propietario, en el navegador, ve a su lado «Mejorar plan», que abre la Tienda de erplora.com de este
     negocio en una pestaña nueva: allí ve el precio y la contrata.
  3. En cuanto erplora.com se lo dice al hub, la app pasa a «Activa» y aparece en «Mis apps» y en el menú, sin
     recargar.
  4. Quien no es el propietario, y cualquiera en la app instalada, ve «Se contrata en erplora.com, desde tu
     cuenta de ERPlora.» y ningún botón: el hub nunca vende, y en erplora.com solo compra el propietario.
Entra: lo que el negocio tiene contratado, tal y como erplora.com se lo pasa al hub.
Sale: nada guardado ni cobrado en el hub.
Si falla: hasta que erplora.com se lo dice al hub, la app sigue con «Necesita suscripción»; una pantalla suya
que se abra dice por qué.
Implicados: APPS-F07, BASE-F27

### BASE-F21 Ver por qué no se ha podido activar una app y reintentarlo
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
  1. Una app que se estaba preparando no termina porque sus datos no se han podido preparar. El hub lo vuelve
     a intentar solo: al minuto, a los 5 minutos, a los 15 y después cada hora.
  2. Su fila, en «Mis apps», dice «No se ha podido activar» y, a quien administra el negocio, le ofrece «Reintentar» y
     «Desactivar»; quien no lo administra ve el estado, sin botones. Mientras tanto la app no se abre y su pantalla dice
     «No se ha podido preparar Página web» — «Ve a Apps para volver a intentarlo. No se ha perdido nada del negocio.».
  3. «Reintentar» la vuelve a pedir: «Activando Página web… Estará lista en un momento.» y la fila vuelve a
     «Activándose…».
  4. Desde el asistente («Vuelve a intentar activar la web») la app se nombra como en «Volver a activar una app» y la
     tarjeta la pone con su nombre entero.
Entra: la app que no se ha podido preparar.
Sale: la activación pedida de nuevo (`base.app.activation_requested`).
Si falla: si vuelve a fallar, vuelve a decirlo con su «Reintentar». Si ya no estaba esperando, porque otro dispositivo
la ha reintentado, sale en un aviso con el nombre de la app y «Esta app no está esperando a que se vuelva a preparar.»,
que se queda hasta cerrarlo. Desde el asistente, un nombre que vale para varias apps, o para ninguna, no saca tarjeta.
Implicados: BASE-F32, BASE-F22, BASE-F24

### BASE-F22 Seguir la activación de una app mientras se navega
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
  1. Quien administra activa una app cuyos datos aún no están preparados en este negocio: una que llegó a
     ERPlora después de que el negocio naciera. Con las demás no hay espera: quedan activas al momento.
  2. Sale «Activando Página web… Estará lista en un momento.»; su fila dice «Activándose…», con «Desactivar», y en «Mis
     apps» del Inicio sale «Activando…», sin abrirse. Puede irse a otra pantalla: sigue sola. Aún no sale en el menú.
  3. Si se abre su pantalla por su dirección, dice «Se está preparando Página web» — «Se abre en un momento: esta página
     lo muestra en cuanto esté lista.».
  4. Cuando está lista se abre como cualquier otra: pasa a «Activa» con «Abrir», sale en el menú de todos los
     dispositivos del negocio sin recargar y su pantalla dice «Página web ya está lista» — «Ya se puede usar.», con
     «Abrir Página web».
Entra: cómo va la activación.
Sale: la app en marcha en este negocio (`base.app.enabled`).
Si falla: lo dice su fila y se reintenta, como en «Ver por qué no se ha podido activar una app y reintentarlo». Mientras
el personal de ERPlora tiene congelada la plataforma por una subida de la base de datos (unos minutos), la app sigue
«Activándose…» y termina sola en cuanto se descongela.
Implicados: BASE-F31, BASE-F32, BASE-F18, BASE-F21

### BASE-F23 Desactivar una app
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
  1. En «Mis apps», quien administra pulsa «Desactivar» en la fila de una app.
  2. Le pregunta siempre, con el nombre de la app: «¿Desactivar Reservas?» — «Sale del menú de todos en este
     negocio. No se borra nada: al volver a activarla, tiene sus datos.». Si con ella se van otras que llegaron solo
     por ella, las nombra: «Mesas se desactiva con ella: solo la necesitaba Reservas.». Nunca se va con ella una app
     que el país del negocio exige: al desactivar Ventas, Impuestos se queda activa y no se nombra.
  3. Confirma con «Desactivar»: «Reservas está desactivada. También se ha desactivado: Mesas.». Las dos salen de
     «Mis apps» y, sin recargar, del menú de todos los dispositivos del negocio; sus pantallas dicen que la app no
     está disponible y el contador de arriba resta las que se desactivan y, de las del plan, la que
     eligió el negocio.
  4. En «Añadir apps» siguen, con su icono, su nombre y «Desactivada»: desde ahí se vuelven a activar.
  5. Desde el asistente («Desactiva la app de reservas», o sin decir «app»: «quita Reservas del menú», «no quiero ver
     Reservas en el menú») la app se nombra como en «Volver a activar una app» y la tarjeta de riesgo alto la pone con
     su nombre entero. Antes del sí nombra también las que se van con ella, con la misma regla y las mismas palabras que
     el paso 2: «Otras apps: Horarios y Mesas se desactivan con ella: solo las necesitaba Reservas.». Si ya estaba
     desactivada, el asistente lo dice y no cambia nada.
Entra: las apps del negocio, lo que necesita cada una y cuáles eligió el negocio.
Sale: la app apagada en este negocio, y las que llegaron solo con ella, con sus datos intactos.
Si falla: si otra app en marcha la necesita, no cambia nada; si no se puede desactivar, no ofrece «Desactivar». Con
«Cancelar», tampoco cambia nada. Desde el asistente, un nombre que vale para varias apps no saca tarjeta: pregunta cuál.
Implicados: VERIFACTU-F32, BASE-F24, BASE-F25, BASE-F26

### BASE-F24 Volver a activar una app
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
  1. En «Añadir apps», quien administra pulsa «Activar» en una app que apagó, que sale «Desactivada».
  2. Si necesita otras que también están desactivadas, antes le pregunta y las nombra; si no, la activa
     sin preguntar.
  3. La app vuelve a «Mis apps» y al menú, sin recargar, con los datos que tenía: «Reservas está activada.» y, si
     llegó con otras, «También se ha activado: Mesas.».
  4. Desde el asistente («Activa la app de reservas», o sin decir «app»: «vuelve a poner Reservas en el menú») la app
     se nombra como la dice la persona: por su nombre en
     cualquier idioma del Hub, sin mirar mayúsculas ni acentos, o, si ninguna se llama así, por la única con una
     palabra de su nombre que empieza así («booking» es Reservas online). «Reservas» es Reservas, nunca Reservas online
     aunque empiece igual. La tarjeta la pone con su nombre entero, nunca con su identificador, y antes del
     sí nombra las que necesita y están desactivadas, como el aviso del paso 2: «Activar en Apps: Reservas · Otras
     apps: Reservas necesita Horarios y Mesas: se activan con ella.». Si ya estaba activada el asistente lo dice
     («Clientes ya estaba activada») en vez de «activada».
  5. Si el país del negocio la exige (VeriFactu en España), la tarjeta dice además, antes del sí, que ya no se podrá
     desactivar, con el motivo de Apps: «Activar en Apps: VeriFactu · Una vez activada: VeriFactu es obligatoria para
     los negocios de España: no se puede desactivar.». El asistente lo sabe también al preguntarle por ella.
  6. Si al asistente se le pide algo de una app desactivada diciendo su nombre, aunque no se diga «app» («quiero
     gestionar reservas», «apunta una cita»), o si lo nombra lo que el asistente busca para hacerlo, dice qué app lo
     hace, para qué sirve como lo dice Apps y que está desactivada, en vez de decir que no puede o de intentarlo con otra
     cosa. A quien administra le pone la tarjeta de activarla del paso 4; con el sí, sigue con lo que se le pidió en la
     misma conversación, ya con lo que hace esa app. A quien no puede activar apps le dice que la activa quien
     administra el negocio; de una de pago sin contratar, que se contrata en erplora.com, sin ofrecer activarla; de una
     que se está preparando o que no se pudo activar, su estado, como Apps. Lo que ya hacen las apps activadas («¿cuántos
     servicios tengo?», «sube el precio del tinte a 40 €») no le hace nombrar ninguna.
Entra: lo que necesita la app y lo que el negocio tiene contratado.
Sale: la app en marcha en este negocio, elegida por él.
Si falla: con el límite de apps del plan alcanzado, el aviso «El límite de apps de tu plan» con «Mejorar plan»; una app
de pago sin contratar no se puede activar. Bajar de plan no apaga nada: con más apps elegidas que las del plan nuevo,
todas siguen en marcha y solo no se puede activar otra hasta quedar por debajo. Desde el asistente, un nombre que vale
para varias apps («reserva»: Reservas y Reservas online) no saca tarjeta ni activa ninguna: el asistente pregunta cuál,
nombrándolas; uno que no es de ninguna: «Ninguna app tiene ese nombre o identificador.».
Implicados: BASE-F93, BASE-F97, BASE-F18, BASE-F19, BASE-F20, BASE-F25

### BASE-F25 Ver que una app se niega a desactivarse
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
  1. Una app que se niega a desactivarse no ofrece «Desactivar»: debajo de su estado, quien administra lee el motivo
     de la propia app en su idioma: «VeriFactu no se puede desactivar una vez activada: la ley obliga a que tus
     facturas sigan llegando a la AEAT.».
  2. Tampoco lo ofrecen las apps que esa necesita, que no se pueden desactivar antes, y cada una dice por cuál:
     «Facturación no se puede desactivar: hace falta para VeriFactu. VeriFactu no se puede desactivar una vez
     activada: la ley obliga a que tus facturas sigan llegando a la AEAT.».
  3. Una app activa que el país del negocio exige («Obligatoria en España») tampoco lo ofrece, y dice por
     qué: «Impuestos es obligatoria para los negocios de España: no se puede desactivar.». Lo dice ella misma aunque
     otra app la necesite, porque desactivar esa otra no cambiaría nada; una app con motivo propio (VeriFactu) dice
     el suyo. Mientras se está activando, o si no se pudo activar, todavía se puede dejar.
  4. Quien administra pulsa «Desactivar» en una app que otra en marcha necesita y que sí se puede desactivar (por
     ejemplo, «Mesas» mientras «Reservas» está activada). El hub no cambia nada: encima de la tabla sale «No se ha
     cambiado nada» con lo que hay que hacer antes, «Desactiva antes Reservas.» (sin preguntar).
  5. El aviso se queda hasta que se cierra o se activa o desactiva otra app; la app sigue «Activa».
Entra: las apps en marcha que la necesitan, el motivo de la app que se niega, o el país del negocio y las apps que
exige.
Sale: nada.
Si falla: si aun así se pide por el asistente o por la API, el hub contesta el mismo motivo y no cambia nada. Sin
motivo propio de la app, el mismo aviso dice que no se ha podido cambiar, con el nombre de la app y lo que ha
contestado el hub.
Implicados: VERIFACTU-F32, BASE-F01, BASE-F14

### BASE-F26 Entender por qué una app no se abre
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
existe, como cualquier otra. Una pantalla que el rol de la persona no abre dice «Sin acceso» (BASE-F118); si la app
entera no se abre en el negocio, manda este motivo, que vale para todos.
Implicados: BASE-F118

### BASE-F27 Ver una app de pago bloqueada
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: La pantalla de una app que no se abre
Pasos:
  1. El negocio deja de tener una app de pago (su suscripción en erplora.com termina) o alguien abre una que no
     ha contratado.
  2. Al abrir cualquier pantalla suya ve «Suscripción necesaria»: el nombre de la app y «está deshabilitada porque
     este negocio no tiene su suscripción. Tus datos están a salvo y vuelven en cuanto se contrate.», con «Ir a
     Apps» y, para el propietario en el navegador, «Mejorar plan».
  3. La app sale del menú y de «Mis apps», y el hub no hace nada de lo que se le pida a esa app, venga de esta
     pantalla, de otro dispositivo, del asistente o de una integración.
  4. Si se contrata con la pantalla abierta, cambia al nombre de la app con «ya está lista» — «Ya se puede
     usar.» y «Abrir» con su nombre, que la abre al día.
Entra: lo que el negocio tiene contratado, tal y como erplora.com se lo pasa al hub.
Sale: nada; los datos de la app no se tocan.
Si falla: si nadie avisa al hub cuando termina el periodo contratado, el hub lo nota solo al pasar la fecha. Un
negocio de demostración tiene todas las apps, también las de pago, para probarlas.
Implicados: APPS-F07

### BASE-F29 Elegir una plantilla del catálogo para importar
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · Datos y copias (Importar)
Pasos:
  1. Abre «Ajustes» en el menú lateral; en «Datos y copias», «Importar» es lo que se abre. Dice «Carga una
     plantilla: llena tus apps con sus datos —una carta, servicios, mesas— listos para usar.» y, debajo,
     «Elige qué cargar».
  2. Mientras llegan, «Cargando plantillas…». Después, una tarjeta por plantilla: su nombre de título, su
     descripción y cada dato en su línea con el icono que dice qué es: el idioma y el país por su nombre, la
     versión en palabras («Versión 1») y lo que trae (cuántas categorías, productos, servicios, zonas o mesas).
     Con la vista de lista, una fila por plantilla con esos datos en sus columnas «Idioma», «País», «Versión» y
     «Trae». Primero las del país del negocio y, dentro, las del idioma de la persona.
  3. «Buscar plantillas» busca por el nombre, la descripción o las apps que trae.
  4. Pulsa «Usar plantilla» en la que le sirva: el botón gira mientras se lee y se abre «Revisa lo que
     trae».
Entra: las plantillas del Hub, una por sector e idioma (hoy restaurante y peluquería, en español y en
inglés).
Sale: nada guardado hasta cargarla.
Si falla: «No se han podido cargar las plantillas ahora mismo. Puedes importar un archivo igualmente.» con «Reintentar»;
sin plantillas, «Todavía no hay plantillas para tu negocio.»; una búsqueda sin resultado, «Ninguna plantilla coincide
con tu búsqueda.»; si la plantilla no se puede leer, «No se pudo leer el fichero:» con el motivo y se queda en la
elección. Quien no administra el negocio lee «Solo un administrador puede ver e importar plantillas.».
Implicados: INVENTORY-F12, BASE-F31

### BASE-F30 Subir un fichero para importar
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · Datos y copias (Importar)
Pasos:
  1. En «Importar», pulsa «Subir desde archivo» y elige un .blueprint.zip: una copia de seguridad de este
     negocio o una plantilla que exportó otro.
  2. Mientras se lee, el botón gira. Después se abre «Revisa lo que trae».
  3. Tras un error se puede elegir el mismo fichero otra vez.
Entra: el fichero, de 20 MB como mucho (con las fotos propias de sus artículos y servicios, INVENTORY-F33).
Sale: nada guardado hasta cargarlo.
Si falla: «No se pudo leer el fichero:» con el motivo (no es un .blueprint.zip, está dañado, lo
hizo una versión más nueva de ERPlora o pasa de 20 MB) y se queda en la elección.
Implicados: BASE-F31

### BASE-F31 Revisar y cargar lo que trae el fichero
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · Datos y copias (Importar)
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
     el Hub nunca carga (personas, PIN, datos fiscales) sale en «Nunca se carga aquí». Ninguna plantilla del
     catálogo trae VeriFactu, tampoco en España: no sale en la revisión y la carga no la activa, porque ata el negocio
     a la AEAT y la activa el dueño desde Apps.
  3. Desmarca las apps que no quiera y pulsa «Importar» («Importando…»), o «Elegir otro» para volver.
  4. Al terminar sale el informe. Lo que ya había en el negocio se queda como estaba: no se
     duplica ni se sobrescribe. Si una app de la plantilla aún se está preparando, lo suyo entra solo en
     cuanto queda lista, sin volver ni pulsar nada.
Entra: la plantilla o el fichero y las apps marcadas.
Sale: las apps marcadas que estaban desactivadas, activadas antes de cargar y dentro del tope de apps del plan,
cada una elegida por el negocio como si se activara en Apps (`base.app.enabled`): cuentan para el límite de
apps del plan y desactivar otra no se las lleva; las que necesitan y no se marcaron llegan con ellas, e Impuestos,
que el país exige, llega con las que la necesitan sin contar para el plan, como al darse de alta. En cada app
marcada, lo que trae y faltaba, dado de alta como si se hiciera a mano en esa app (sus categorías, productos,
servicios, zonas, mesas y, desde una copia de seguridad, clientes), y el informe guardado
(`base.blueprint.imported`).
Si falla: «La importación falló:» con el motivo y se queda en la revisión; sin ninguna app marcada, «Elige al
menos una app.» y no se puede importar; si ninguna de sus apps se puede activar aquí, «Nada de este fichero
puede cargarse en tu negocio: ninguna de sus apps se puede activar aquí.». Una app que no se pudo activar (el
tope de apps del plan, una app que el plan no incluye) se queda desactivada, no carga nada y el informe dice
por qué; el resto se carga. Un fichero no se guarda: si una de sus apps aún se está preparando, su fila dice «Se está
preparando para este negocio. Vuelve a subir el archivo dentro de un minuto para traer sus datos.».
Implicados: BASE-F22, INVENTORY-F01, INVENTORY-F12, INVENTORY-F26, INVENTORY-F36, VERIFACTU-F01, BASE-F32

### BASE-F32 Leer el informe de la importación
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · Datos y copias (Importar)
Pasos:
  1. Al terminar, «Informe de la importación» con cómo fue: «Todo ha entrado.», «No todo entró.» o «No ha
     entrado nada.». Si una app de la plantilla aún se está preparando, «Aún se está cargando: lo que
     falta entrará solo en cuanto sus apps estén listas. Puedes salir de esta pantalla.», sin nada que pulsar.
  2. Una fila por app con su etiqueta: «Aplicado», «Ya lo tenías», «Aplicado en parte», «Falló», «Nada que
     copiar», «Descartado», «App desactivada», «No está en este negocio», «No elegida», «Preparándose» o «No se ha
     podido preparar». «Ya lo tenías» sale solo cuando todo lo que trae la app ya estaba en el negocio; una app de la
     que no trae nada, como las que la plantilla solo activa, dice «Nada que copiar». Debajo, por cada parte, «12
     filas nuevas · 3 ya estaban · 2 con error» y, de lo que falló, su nombre y el motivo; cada cifra va en singular
     con una sola fila («1 fila nueva · 1 ya estaba · 1 con error»).
  3. Lo dejado fuera a propósito sale en «Se ha dejado fuera a propósito».
  4. «Ver las plantillas» vuelve al catálogo; «Ir al inicio» lleva al Inicio.
  5. Cuando la app queda lista, lo suyo se carga solo y el informe se pone al día sin recargar, esté en esta pantalla
     o se haya ido: al volver, ya está dentro.
Entra: el informe de la importación.
Sale: nada; el informe queda guardado en el negocio. Lo que se cargó después cuenta en esa misma importación: se deshace
con ella (BASE-F34).
Si falla: una etiqueta que la pantalla no conoce sale como «Falló» con su texto tal cual, nunca como un éxito. Si la app
no se puede preparar, arriba dice «Aún no se ha podido preparar: Página web. Se sigue intentando sola y sus datos se
cargarán en cuanto funcione.» y su fila, «No se ha podido preparar» con «Aún no se ha podido preparar. Se sigue
intentando sola y sus datos se cargarán en cuanto funcione; «Reintentar lo que falta» lo intenta otra vez ahora.». Si
mientras tanto la app se desactiva, la importación se deshace, el negocio se restablece o cambia la versión de la
plantilla, no se carga nada suyo y su fila dice por qué. Si la carga falla ya con la app lista, la app queda activa y su
fila dice «Falló» con «Algo falló al cargar esta parte; lo demás no se ha visto afectado.», con «Reintentar lo que
falta».
Implicados: BASE-F21, BASE-F22, BASE-F33, BASE-F34

### BASE-F33 Volver al informe de una importación que no entró entera y reintentar
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · Datos y copias (Importar)
Pasos:
  1. Al abrir «Importar», si la última importación no entró entera y no se deshizo, sale primero su informe, con «Este
     es el informe de tu última importación de Restaurante (24 nov 2026, 10:30). No todo entró.» o, si aún espera a una
     app que se está preparando, con «Aún se está cargando…» y sin «Reintentar lo que falta», que no hace falta. Cuando
     entra, ese mismo informe dice «Todo ha entrado.», sin saltar al catálogo.
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
Si falla: «El reintento falló:» con el motivo y el informe sigue a la vista.
Implicados: BASE-F32

### BASE-F34 Deshacer una importación
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · Datos y copias (Restablecer)
Pasos:
  1. En «Restablecer», «Deshacer una importación» («Quita solo lo que trajo esa importación. Lo que hayas
     creado después se conserva.»): una fila por importación que trajo algo y no se deshizo, con su nombre,
     cuándo, quién y cuántas filas trajo, y «Deshacer».
  2. Pulsa «Deshacer»: «Deshacer «Restaurante»», con «Se borrarán las 120 filas que trajo esta importación. Lo que
     creaste después se conserva.». No pide escribir nada: se puede volver a importar.
  3. Confirma con «Deshacer» (o «Cancelar»).
  4. Sale «Importación deshecha:» con una línea por app («Inventario — 85 filas borradas»); lo que no se pudo
     borrar (algo que otra app todavía usa) sale aparte con su motivo. Lo que tiene cada sección se pone al
     día.
Entra: la importación elegida.
Sale: borradas exactamente las filas que trajo, también lo que entró después porque esperaba a una app, y lo que aún
esperaba ya no entra; lo creado después se queda (`base.import.undone`).
Si falla: el motivo sale en la propia ventana, que no se cierra; una
importación ya deshecha, «Esta importación ya se deshizo.».
Implicados: BASE-F32

### BASE-F35 Exportar una copia de seguridad o una plantilla
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · Datos y copias (Exportar)
Pasos:
  1. Abre «Exportar»: «Empaqueta las apps de este negocio —y, si quieres, sus datos— en un archivo que
     puedes cargar en otro negocio o guardar como copia.».
  2. Escribe el «Nombre» (viene el del negocio; sin él, el de su dirección) y elige el «Idioma»; debajo, el
     nombre final del archivo («Archivo: casa-ramon_es.blueprint.zip»).
  3. Responde «¿Para qué es este archivo?»: «Copia de seguridad de este negocio» (la que viene marcada; lleva
     también los clientes) o «Plantilla para compartir» (nunca lleva clientes).
  4. Elige las apps y sus datos y pulsa «Exportar» («Exportando…»).
  5. El archivo baja con el navegador y sale «casa-ramon_es.blueprint.zip descargado.».
  6. Pedido al asistente («Voy a abrir otro bar y quiero llevarme la carta y los clientes»), dice que se hace aquí,
     en Ajustes › Datos y copias › Exportar, con «Plantilla para compartir» o «Copia de seguridad de este negocio», y
     qué lleva: los productos y los servicios van con sus fotos propias dentro. El archivo no lo saca él.
Entra: el nombre, el idioma, para qué es y lo marcado.
Sale: un .blueprint.zip con las apps marcadas y, de las que llevan datos, sus filas: de Inventario, las categorías y los
productos, y de Servicios, las categorías y los servicios, con sus fotos propias dentro (INVENTORY-F33); de Mesas, las
zonas y las mesas; de Suplementos, los grupos, cada uno con sus opciones y con los productos (por su código) y las
categorías a los que se aplica; y, solo en una copia de seguridad, los clientes. Nunca las ventas, las personas, los PIN
ni los datos fiscales. Cargado en otro negocio, o en este mismo (BASE-F30), devuelve lo que lleva tal como era. En el
negocio no se guarda nada.
Si falla: «La exportación falló:» con el motivo; sin nombre, «Escribe un nombre para el archivo.» y no se puede
exportar. Quien no administra el negocio lee «Solo un administrador puede exportar el negocio.». El administrador
exporta igual que el propietario: lo que es solo del propietario son las copias completas que ERPlora guarda antes de
restablecer.
Implicados: BASE-F112 (dentro de la app), BASE-F37, INVENTORY-F01, INVENTORY-F26, INVENTORY-F33, INVENTORY-F36, BASE-F36

### BASE-F36 Elegir qué apps, datos y tablas viajan en la exportación
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · Datos y copias (Exportar)
Pasos:
  1. En «Exportar», bajo «Apps» («Elige qué apps registra el archivo y si sus datos viajan con él.»), una fila
     por app encendida con dos casillas, «App» y «Datos». Vienen todas con la app marcada y sin datos; una app
     sin nada propio dice «Nada propio que copiar».
  2. Desmarcar la app desmarca sus datos. «Seleccionar todo» marca todas las apps y sus datos;
     «Deseleccionar todo» las desmarca todas.
  3. Al marcar «Datos» de una app sale debajo «Datos de Inventario», con una casilla por cada parte y sus filas;
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
Estado: hecho
Actor: propietario
Pantalla: Ajustes · Datos y copias (Restablecer)
Pasos:
  1. En «Restablecer», «Restablecer el negocio»: «Borra definitivamente los datos que marques. No se puede
     deshacer: si dudas, exporta antes una copia.», con «Exportar una copia antes», que abre «Exportar».
  2. Dice qué no se borra nunca: «Solo se borra lo que cada sección enumera aquí. Las ventas, las facturas,
     los registros fiscales, las personas y sus accesos, los archivos y los ajustes del negocio se quedan
     siempre.», y «Antes de vaciar se hace una copia completa de los datos del negocio y se guarda 90 días, en
     «Copias», aquí debajo.».
  3. Una fila por sección (una app) que tiene algo, con lo que tiene (cada parte y sus filas) y su total.
  4. Marca las secciones y pulsa «Restablecer el negocio»: «Esto no se puede deshacer», con «Se borrarán
     definitivamente 120 filas:» y el desglose. Escribe el nombre del negocio («Escribe «Casa Ramón» para confirmar») y
     pulsa «Borrar definitivamente» (o «Cancelar»).
  5. Sale «Copiando los datos del negocio antes de vaciar…», con «Después se vaciará: Inventario, Clientes. Puedes salir
     de esta pantalla: sigue sola.», y luego «Vaciando: Inventario, Clientes…». Mientras tanto no se ofrece otro: «Se
     está restableciendo el negocio: espera a que termine.».
  6. Sale «Negocio restablecido:» con una línea por sección («Inventario — 85 filas borradas») y «Se guarda una copia
     completa de los datos de antes en «Copias».», y la lista se recalcula.
  7. Abajo, «Copias de los datos»: una fila por copia, con por qué se hizo («Antes de restablecer» o «Al eliminar el
     negocio»), su fecha, lo que ocupa y «Descargar». Sin ninguna: «Todavía no hay copias: se hace una antes de cada
     restablecimiento.».
Entra: lo que tiene cada sección y lo marcado.
Sale: una copia de todos los datos del negocio, guardada 90 días, y después el borrado definitivo de lo marcado
(`base.hub.data_reset`).
Si falla: el motivo sale en la ventana, que no se cierra: un nombre que no es el del negocio, «El nombre no
coincide.». Si la copia no se puede hacer, no se vacía nada: «No se ha vaciado nada», con «No se ha podido hacer la
copia de los datos, así que no se ha vaciado nada.» y «Volver a intentarlo», con las mismas secciones. Si lo que falla
es vaciar, la copia se guarda: «No se han podido vaciar las secciones, así que no se ha quitado nada. La copia de los
datos de antes se guarda.». Quien no administra el negocio lee «Solo un administrador puede deshacer importaciones o
restablecer el negocio.». Un administrador deshace importaciones, pero en lugar de «Restablecer el negocio»
y «Copias de los datos» lee «Solo el propietario del negocio puede restablecerlo o descargar las copias de sus datos.»:
restablecer, ver las copias y descargarlas es solo del propietario, también por la API y desde el asistente, que le
responden que no tiene permiso.
Implicados: BASE-F34, BASE-F35

### BASE-F38 Ver Inicio al día después de importar una plantilla
Estado: hecho
Actor: propietario, administrador
Pantalla: Inicio · Resumen
Pasos:
  1. Mientras el negocio no tiene nada de lo que trae una plantilla (un negocio nace con todas las apps
     desactivadas salvo Impuestos), quien lo administra ve arriba «Empieza con un negocio como el tuyo» («Elige el que más se
     parezca al tuyo: activamos sus apps y cargamos su catálogo de una vez. Después tendrás que poner tus
     propios datos.»): hasta cuatro plantillas, una por
     tipo de negocio y en su idioma si la hay (primero las de su país), con su descripción y «Usar esta»; «Ver todas las plantillas» abre «Datos y
     copias» y «Ahora no» cierra la tarjeta en este dispositivo.
  2. Pulsa «Usar esta»: «Preparando «Restaurante»…» mientras se activan sus apps y se carga, sin pantallas
     intermedias.
  3. En la misma tarjeta, «Ya tienes tus apps y tu catálogo» («Lo que queda es lo que solo puedes contestar tú: los
     datos de tu negocio. Los tienes en la lista de abajo.») con «Continuar», que la cierra. Si alguna app aún se está
     preparando, primero «Tus apps se están preparando» («Sus datos se cargarán solos en cuanto estén listas: Página
     web. Puedes seguir trabajando.») con «Ver el informe» y «Continuar»; la tarjeta pasa sola a «Ya tienes tus apps y
     tu catálogo» cuando entra, sin pulsar nada.
  4. Sin recargar, el Inicio se pone al día: «Termina de configurar tu negocio» cuenta como hechos los pasos
     que resolvió la plantilla y los paneles se refrescan. Igual tras cargar una plantilla o un fichero desde
     «Datos y copias».
Entra: las plantillas y si el negocio todavía está vacío.
Sale: lo que trae la plantilla, como en BASE-F31 (`base.blueprint.imported`): VeriFactu se queda desactivada
(VERIFACTU-F01).
Si falla: si no entró todo, «No todo ha entrado» con «Estas no han entrado: Página web.» (o «Hay algo más que no ha
entrado.») y «Ver el informe»; si una app no se ha podido preparar, «Una app aún no se ha podido preparar» con «Se sigue
intentando sola y sus datos se cargarán cuando lo consiga: Página web. En el informe puedes reintentarlo ahora.» y «Ver
el informe»; si no se pudo abrir, «No se ha podido abrir esa plantilla» con «No ha cambiado nada en tu negocio:» con el
motivo e «Intentar otra vez»; si se cortó a medias, «La configuración no ha terminado» con «Puede que parte ya esté
dentro. Compruébalo en Ajustes › Datos antes de volver a intentarlo.» y «Ver el informe», sin reintento. Si las
plantillas no se pueden leer, «No se han podido cargar las plantillas para empezar.» con «Reintentar» y «Ahora no».
Implicados: BASE-F01, INVENTORY-F12, VERIFACTU-F01

### BASE-F39 Abrir Sistema y moverse por sus pestañas
Estado: hecho
Actor: propietario, administrador
Pantalla: Sistema · Uso y plan
Pasos:
  1. Pulsa «Sistema» en el menú lateral, o llega desde el aviso de los eventos caídos de la campana.
  2. Abajo hay cuatro pestañas, en este orden: «Uso y plan», «Actualizaciones», «Eventos caídos» y «Registros». Se abre
     «Uso y plan». La pestaña elegida queda en la dirección: un enlace o recargar abre la misma.
  3. Una pestaña que no existe abre «Uso y plan», y también los enlaces de antes a «Recursos» y a «Plan y límites»; la
     antigua de las copias lleva a «Ajustes» › «Datos y copias».
  4. Quien no administra el negocio no tiene «Sistema» en el menú lateral: su dirección, también la de cualquiera de
     sus pestañas, le dice que no tiene acceso.
  5. Al final de «Uso y plan» salen las tarjetas que ponen ahí las apps encendidas en el negocio y que la persona puede
     ver, cada una con lo suyo: la de Impresión es «Tu impresora». Una app apagada no pone
     la suya; al encenderla o apagarla, la tarjeta aparece o se va sin recargar.
Entra: las tarjetas de las apps encendidas que la persona puede ver.
Sale: nada guardado.
Si falla: cada pestaña dice lo suyo. Si no se puede leer qué tarjetas tocan, no sale ninguna y el
resto de la pestaña sigue; una tarjeta que no carga se queda fuera y las demás salen.
Implicados: BASE-F40, BASE-F118, PRINTING-F21, BASE-F41, BASE-F42, BASE-F43

### BASE-F40 Ver lo que usa el negocio y si tiene que ampliar el plan
Estado: hecho
Actor: propietario, administrador
Pantalla: Sistema · Uso y plan
Pasos:
  1. Abre «Sistema»: se abre «Uso y plan». Mientras carga: «Consultando el sistema…». Arriba, su plan («Plan Starter»)
     y, para el propietario, «Mejorar plan», que abre la página del plan de este negocio en erplora.com; al
     administrador, en la app instalada o donde ese enlace no sale, sin botón, «Los planes se gestionan desde tu cuenta
     de ERPlora, en erplora.com.».
  2. Debajo, una línea le dice si tiene que ampliar. En verde, «Tu plan te alcanza». En ámbar, «Te conviene ampliar:» y
     el motivo, con los archivos o los mensajes del mes desde el 80 %: «casi no te quedan archivos», «casi no te quedan
     mensajes del asistente este mes» o «casi no te quedan mensajes de WhatsApp este mes». En rojo, «Tienes que
     ampliar:» y el motivo: «ya no caben más archivos», «se han acabado los mensajes del asistente de este mes», «se han
     acabado los mensajes de WhatsApp de este mes» o «tu negocio se queda sin capacidad en los momentos de más trabajo».
     Con varios motivos, gana el más grave y, a igualdad, el más lleno. El verde sale solo cuando todo lo que aplica se
     ha podido leer: sin motivos, mientras algo contesta, «Comprobando tu plan…»; si algo no se ha podido leer, «No
     hemos podido comprobarlo todo», con «Reintentar». Un motivo se dice igual, porque sigue siendo cierto, y lo que su
     plan no incluye no queda por comprobar.
  3. «Lo que incluye tu plan», de lo más lleno a lo menos: «Archivos» («1,2 GB de 5 GB», con «Medido el 24 nov 2026»),
     «Apps», «Personas» y «Dispositivos» («3 de 5»), y el asistente y, con su app encendida, «WhatsApp»
     («120 de 500 al mes»), cada uno con su barra, del color de la línea de arriba. Desde el 80 %, los archivos y
     los mensajes dicen «Cerca»; al llegar al tope, cualquiera dice «Completo».
  4. Personas, dispositivos y apps al tope no cambian el color de arriba: un negocio Gratis con 1 de 1 dispositivo está
     bien. Debajo de la línea verde se lee «Personas al completo: para añadir más, amplía el plan.».
  5. Con tope 0, «3 · Sin límite», sin barra. Los mensajes no tienen esa posibilidad: con 0, «Tu plan no incluye
     asistente» o «Tu plan no incluye WhatsApp», sin barra, y no son motivo de nada.
  6. Al final de la lista, «Capacidad»: «2 de 5 conexiones», el máximo medido hoy frente a lo que de verdad
     tiene (lo que incluye su plan o, si es menos, lo que da el servicio), con su barra. Nunca va por porcentaje, porque
     con tope 1 la primera operación del día ya es el 100 %, sino por las veces que a alguien le salió «Demasiadas
     peticiones. Inténtalo de nuevo en un momento.»: «Se quedó corta 3 veces esta semana». Entonces, si un plan
     mayor daría más, sube al principio de la lista y la línea de arriba se pone en rojo.
  7. Si su plan ya incluye toda la capacidad que da el servicio, un plan mayor no le daría más: la fila no ofrece
     ampliar, no pone rojo arriba y, cuando se queda corta, dice «Ya tienes la capacidad máxima: cuéntanoslo en «Reportar
     un problema».». Arriba tampoco sale el verde: la línea, neutra, dice «No hace falta que amplíes: ya tienes la capacidad
     máxima, pero a veces se queda corta.». Si hay otro motivo (los archivos o los mensajes), gana ese.
  8. «Para tu información», lo que ningún plan limita, sin barra ni pastilla: «Peticiones este mes», las que ha atendido
     el negocio desde el día 1; «Activas ahora», las personas con actividad en los últimos 5 minutos; «Últimos 30 días»
     y «Tamaño de la base», con «Medido el 24 nov 2026». Ni CPU ni memoria: no se pueden atribuir a un negocio, así que
     no salen, ni una frase en su lugar.
  9. Con motivos que el hub sabe sin preguntar a erplora.com (los archivos, la capacidad y WhatsApp), la campana de quien
     administra el negocio lleva el aviso «1 límite del plan por revisar», que suma uno por motivo, con «Tu negocio
     está llegando a lo que incluye su plan: algunas cosas pueden pararse o ir lentas hasta que lo amplíes.», y «Ver el
     uso del plan» abre «Sistema» en «Uso y plan». Sin ellos, el aviso desaparece.
  10. Quien administra el negocio puede preguntar lo mismo al asistente («¿cuánto espacio me queda?», «¿cuántas
      peticiones llevamos este mes?») y contesta con estas cifras. Los mensajes del asistente del mes se los puede
      preguntar cualquiera.
Entra: lo que se mide de este negocio: cada noche, lo que ocupan sus archivos y su base de datos y las personas que
tuvieron actividad; durante el día, sus peticiones, sus conexiones y quién tiene actividad. Los topes del plan que
erplora.com le pasa al hub, las apps que eligió, los mensajes del asistente que cuenta erplora.com y los de WhatsApp.
Sale: nada guardado al mirar la pantalla. Lo medido queda por negocio y día, y erplora.com lo recoge cada noche para
que el equipo de ERPlora vea lo mismo (HUBS-F22).
Si falla: «No se pudo consultar el sistema» — «Las métricas y los registros no están disponibles ahora. Puedes volver a
intentarlo.» con «Reintentar». Lo que aún no se ha medido lo dice, nunca con un cero: antes de la primera noche, «Se
mide cada noche: la primera cifra llega mañana.»; sin medida de la capacidad o de las peticiones hoy, «Todavía sin medir
hoy.»; WhatsApp antes de que erplora.com mande sus cifras, «Todavía sin medir.»; si las peticiones o las veces que se
quedó corta llevan contándose menos que su periodo, dicen «Desde el 24 nov 2026». El asistente se pregunta a erplora.com
aparte: si no contesta, su fila dice «No disponible ahora», sin cifra, y la pantalla sigue; lo mismo si no se puede leer
WhatsApp. En una demo, en lugar de todo: «En una demo no se mide el uso: sus datos se borran al terminar.». Mientras el
hub no conoce el plan: «Todavía no conocemos el plan de este negocio: aparecerá en cuanto erplora.com lo envíe.» y, bajo
«Lo que usas», las cifras sin tope, barra, pastilla ni línea de arriba. El negocio propio de ERPlora no lo tendrá nunca:
en su lugar dice «Este es el negocio de ERPlora: no tiene plan.», con las mismas cifras.
Implicados: BASE-F10, BASE-F11, BASE-F39, BASE-F57, BASE-F72, BASE-F73, BASE-F108, HUBS-F21, HUBS-F22, BASE-F104

### BASE-F41 Saber qué versión corre y cuándo se actualizó
Estado: hecho
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
Implicados: BASE-F116

### BASE-F42 Ver el registro de sucesos del sistema
Estado: hecho
Actor: propietario, administrador
Pantalla: Sistema · Registros
Pasos:
  1. Abre la pestaña «Registros»: el título es «Registro de eventos».
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
Estado: hecho
Actor: propietario, administrador
Pantalla: Sistema · Eventos caídos
Pasos:
  1. Llega desde el aviso de los eventos caídos de la campana o pulsando la pestaña «Eventos caídos».
  2. Mientras carga: «Cargando los eventos caídos…». Con eventos: «Arregla la causa (un permiso, una app parada…) y
     reenvía. El evento no se edita: si la causa sigue, vuelve a caer aquí.».
  3. Cada aviso es una tarjeta con su nombre, cuántas veces se intentó, de qué app a cuál iba (por ejemplo, de
     «Ventas / TPV» para «Facturación»), cuándo pasó y su último error tal cual, con «Reenviar» y «Descartar».
     Arriba, «Reenviar todos». Si la app a la que iba ya no está activa, la tarjeta dice que no se puede reenviar
     hasta activarla, sin «Reenviar».
  4. Salen los 100 más recientes; con más, la pantalla dice cuántos se ven de cuántos.
  5. La lista y la campana se ponen al día solas cuando un aviso cae, se reenvía o se descarta, y también cuando la
     app a la que iba hace por otro camino lo que pedía: si Facturación emite con «Emitir ahora» el documento de una
     venta, el aviso de esa venta se va solo.
  6. Sin ninguno: «Todo en orden» — «No hay eventos caídos. La cola de eventos vive en la base de datos: un reinicio
     nunca la pierde.».
Entra: los avisos entre apps de este negocio que agotaron sus reintentos, nunca los de otro.
Sale: nada guardado.
Si falla: «No se pudo consultar el sistema» — «No se pudo cargar la cola de eventos caídos. Comprueba la conexión y
reintenta.» con «Reintentar» a la vista: un fallo nunca sale como «Todo en orden».
Implicados: BASE-F10

### BASE-F44 Reenviar un evento caído
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
Si falla: «No se pudo reenviar:» y el motivo, como en «Reenviar un evento caído».
Implicados: BASE-F44

### BASE-F46 Descartar un evento caído
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
Si falla: «No se pudo descartar:» y el motivo, como en «Reenviar un evento caído».
Implicados: BASE-F44

### BASE-F47 Informar de un error de la pantalla sin que nadie lo pida
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
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Ajustes · General, Ajustes · Negocio, Ajustes · Impresión, Ajustes · Datos y copias
Operaciones: ninguna
Pasos:
  1. Pulsa «Ajustes» en el menú lateral, o llega desde un enlace de otra pantalla.
  2. Abajo, las pestañas «General», «Negocio», «Impresión» y «Datos y copias», cada una solo para quien puede usar lo
     que lleva: «Impresión», para quien configura la app Impresión (propietario, administrador y responsable), y «Datos
     y copias», para quien administra el negocio. Un empleado tiene «General» y «Negocio». Se abre «General». La pestaña
     elegida queda en el enlace, así que un enlace guardado vuelve a ella y Atrás sale de Ajustes en vez de recorrer sus
     pestañas. En el móvil caben las cuatro, enteras.
  3. Los enlaces antiguos siguen llevando a su sitio: el de la antigua «General» abre «General», el de la antigua
     pestaña de impuestos abre «Negocio», y el de una pestaña que ya no existe, o que la persona no tiene, abre la
     primera.
  4. En «Impresión», «Impresoras y tique» («Da de alta tu impresora y configura el tique impreso y digital»)
     abre la app Impresión; si no está, dice «Instala la app Impresión para dar de alta tu impresora y configurar
     el tique» y lleva a «Apps».
Entra: las apps del negocio.
Sale: nada guardado.
Si falla: no falla: es navegación. Cada pestaña dice en ella misma si no ha podido cargar lo suyo.
Implicados: PRINTING-F06, BASE-F29, BASE-F49, BASE-F62

### BASE-F49 Ver el país del negocio
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Ajustes · Negocio
Pasos:
  1. En «Negocio», «País» («El de sus impuestos y sus facturas») dice, en el idioma de la persona, el país con
     el que el negocio se dio de alta en erplora.com.
  2. Aquí no se elige: debajo pone «El país no cambia una vez listo el negocio.», porque sus facturas son de un
     país. Mientras el negocio se prepara, se cambia en erplora.com.
Entra: el país con el que erplora.com dio de alta el negocio.
Sale: nada guardado; con él, las plantillas del negocio salen primero y «Termina de configurar tu negocio» sabe
qué pasos le tocan.
Si falla: si los datos del negocio no se pueden leer, «No se pudieron cargar los datos del negocio» con
«Reintentar». Una demo no tiene país: «—».
Implicados: HUBS-F15, BASE-F01, BASE-F29

### BASE-F50 Ver la moneda del negocio
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Ajustes · Negocio, Inicio · Resumen, Inicio · Actividad
Pasos:
  1. En «Negocio», «Moneda» («La de su país, para precios y totales») dice la moneda con su código y su nombre
     en el idioma de la persona: «EUR · Euro».
  2. No se elige: es la del país del negocio, como en los terminales de cobro del mercado. Un negocio sin país
     (una demo) va en euros.
  3. En el Inicio, los importes de los paneles (como «Ventas últimos 7 días») y de «Actividad» van en esa moneda,
     con su símbolo y sus decimales, como los imprime una caja de ese país: «zł» en un negocio de Polonia, «€» en
     uno de España. Mientras el negocio no ha contestado, el importe sale como «—», nunca en otra moneda ni con
     decimales supuestos.
  4. Las apps que enseñan precios o importes van en esa misma moneda, también Citas (el precio de cada servicio
     al reservar y el «Total» de la cita) y la vista previa de Reserva online.
Entra: el país del negocio.
Sale: nada guardado.
Si falla: como en «Ver el país del negocio».
Implicados: BASE-F49

### BASE-F51 Cambiar el idioma del negocio en erplora.com
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · Negocio
Pasos:
  1. En «Negocio», «Idioma del negocio» («El de quien no haya elegido el suyo») dice el idioma del negocio por su
     nombre.
  2. Pulsa «Cambiar en erplora.com»: se abren en otra pestaña (en la app instalada, en el navegador del dispositivo)
     los ajustes del negocio en erplora.com, donde lo cambia y pulsa «Guardar cambios». En la app de
     Google Play el botón no está: se cambia en erplora.com desde un navegador.
  3. Sin recargar, «Negocio» enseña el idioma nuevo en cuanto el negocio lo recibe; igual con el nombre y la zona
     horaria.
Entra: el idioma que guardó erplora.com.
Sale: nada guardado en el negocio: lo recibe de erplora.com (`base.hub.registered`). Quien no ha elegido un idioma
propio en «Mi perfil» y entra con su PIN ve el hub en el del negocio, no en el de su navegador; con su cuenta, en el
de su cuenta de erplora.com (BASE-F64).
Si falla: si el negocio no responde, erplora.com se queda con el cambio y se lo vuelve a mandar;
mientras tanto, «Negocio» sigue con el anterior. Quien no administra el negocio no ve el botón: «Solo el
propietario o un administrador los cambian, en erplora.com.». En una demo, «Esta demo no tiene un negocio en
erplora.com: sus datos no se cambian.».
Implicados: HUBS-F15, HUBS-F08, BASE-F64

### BASE-F52 Entrar con la cuenta de erplora.com
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
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Acceso
Operaciones: ninguna
Pasos:
  1. En erplora.com, con la sesión abierta, pulsa entrar en su negocio.
  2. El negocio se abre con la persona ya dentro, en **Inicio**, sin pasar por ninguna pantalla de entrada.
Entra: el pase de un solo uso que da erplora.com.
Sale: lo mismo que BASE-F52: la sesión y este navegador como dispositivo de confianza del negocio, así que
después ofrece el pinpad, sale en «Dispositivos» y su modo se puede cambiar.
Si falla: un pase caducado o ya usado no abre nada: el negocio vuelve a pedir la entrada de erplora.com.
Implicados: BASE-F52

### BASE-F54 Elegir el PIN la primera vez que se entra en una caja
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
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Acceso
Pasos:
  1. En un dispositivo compartido de un negocio que pide PIN, **Acceso** abre en la pestaña «PIN»: «Introduce tu
     PIN», «…o pasa tu placa: no hace falta elegir tu nombre antes.» y «Elige tu usuario» con una cara por
     persona (iniciales y nombre; nunca su correo). El nombre es el de su perfil en este negocio; sin él, el de su
     ficha de Personal vinculada (STAFF-F03), y si tampoco la tiene, el de su cuenta. Con una sola persona, ya sale
     elegida.
  2. Toca tu nombre: sale «PIN de {name}» y el teclado con tantos círculos como dígitos tenga el PIN del negocio.
     La flecha («Cambiar usuario») vuelve a las caras. El teclado se ve entero, hasta el 0 y el de borrar, sin
     desplazar la pantalla: en una tablet en horizontal (también dentro de su navegador), un portátil o un móvil
     bajo, el nombre sale sin la cara grande y las teclas se juntan algo, siempre del tamaño de un dedo.
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
Implicados: BASE-F54, BASE-F67, STAFF-F03

### BASE-F56 Entrar pasando la placa
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
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Acceso
Pasos:
  1. El plan del negocio cubre un número de dispositivos a la vez (el Gratis, uno) y alguien entra en otro.
  2. La sesión del dispositivo que lleva más tiempo sin entrar se cierra en ese momento: lo que tiene abierto deja
     de ponerse al día.
  3. Su siguiente pantalla es **Acceso**, que arriba dice «Sesión abierta en otro dispositivo» — «Tu plan cubre un
     dispositivo a la vez, así que al entrar en otro se cerró la sesión de este. Vuelve a entrar para usarlo aquí,
     o amplía los dispositivos de tu plan.» con «Mejorar plan» en el navegador (en la app instalada no está: lo que
     vende solo está en la web).
  4. Puede volver a entrar (y cierra la del otro) o ir a ampliar el plan a erplora.com.
Entra: los dispositivos que cubre el plan, que erplora.com le pasa al negocio.
Sale: las sesiones de los dispositivos que sobran, cerradas, y el motivo guardado en cada uno para decírselo.
Si falla: sin tope en el plan no se cierra nada.
Implicados: BASE-F11, BASE-F40

### BASE-F58 La sesión termina mientras se trabaja
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Acceso
Pasos:
  1. La sesión termina: acaba el turno (12 horas en un dispositivo compartido, 30 días en uno personal, 1 hora si
     el negocio pide siempre el PIN), un administrador quita el dispositivo o la persona deja el negocio.
  2. Lo siguiente que abre la lleva a la entrada; si la sesión se cerró porque quitaron el dispositivo o la
     persona dejó el negocio, lo que tiene abierto se entera al momento.
  3. En una caja con pinpad, **Acceso** dice arriba «Tu sesión ha terminado» — «Caducó o se cerró. Vuelve a
     entrar.» y, debajo, el teclado entero (también en una tablet en horizontal o un móvil bajo): la siguiente
     persona entra con su PIN. En un dispositivo sin pinpad va a la entrada de erplora.com,
     que la devuelve dentro si su sesión allí sigue abierta.
Entra: la sesión que ya no existe.
Sale: nada guardado; la venta a medias la conserva su app.
Si falla: sin red, la pantalla no da la sesión por terminada.
Implicados: BASE-F13, BASE-F70

### BASE-F59 Cerrar la sesión de una caja que nadie toca
Estado: hecho
Actor: sistema
Pantalla: Acceso
Pasos:
  1. El negocio eligió en **Ajustes › General**, bajo «Volver a preguntar tras inactividad», unos minutos (1, 5,
     10, 15 o 30) y este dispositivo es compartido.
  2. Nadie toca la pantalla (ni dedo, ni tecla, ni rueda) durante esos minutos.
  3. La sesión se cierra y la caja vuelve a **Acceso**, al pinpad.
Entra: los minutos del negocio, que llegan con la propia página. Si el negocio los cambia con la caja ya abierta, o
este dispositivo deja de ser compartido, la caja cuenta con los nuevos desde ese momento, sin recargar: con «1 min»
se cierra al minuto sin tocarla y con «Hasta cerrar sesión» deja de cerrarse.
Sale: la sesión cerrada en el negocio. La cuenta abierta la conserva su app.
Si falla: con «Hasta cerrar sesión», en un dispositivo personal o donde no se pide PIN no se cierra nada; aunque
la pantalla se quede colgada, una sesión abierta mientras el negocio pide siempre el PIN no dura más de 1 hora. Si
la caja no consigue leer los minutos nuevos, sigue con los que tenía.
Implicados: BASE-F67

### BASE-F60 Cambiar de usuario sin perder la venta
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
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: El menú de usuario
Operaciones: ninguna
Pasos:
  1. Abre la tarjeta de usuario arriba del menú lateral (en el móvil, primero el menú con el botón de la barra).
  2. Pulsa «Cerrar sesión».
  3. En una caja con pinpad vuelve a **Acceso**, lista para la siguiente persona. En otro dispositivo, erplora.com
     pregunta «¿Cerrar la sesión de erplora.com?»: «Cerrar sesión» la cierra también y erplora.com pide entrar de
     nuevo; «Seguir conectado» la deja abierta y enseña los negocios de la cuenta.
Entra: la sesión.
Sale: la sesión cerrada en el negocio; la de erplora.com, solo si la persona lo confirma.
Si falla: si el negocio no contesta, la sesión caduca sola.
Implicados: BASE-F113 (en la app de Android, antes de salir deja de estar a la escucha); HUB_APP-F04 (ERPlora/app: dentro
de la aplicación, «Cambiar de negocio» de la barra cierra la sesión igual y solo después olvida el negocio)

### BASE-F62 Decidir si este dispositivo es compartido o personal
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
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Estamos preparando tu negocio
Operaciones: ninguna
Pasos:
  1. Abre la dirección de un negocio que erplora.com aún está preparando (recién creado).
  2. Sale «Estamos preparando tu negocio» — «Tarda unos segundos. Esta página se actualiza sola.».
  3. Cuando está listo, la página se actualiza y entra como siempre, con Impuestos ya activa (BASE-F14).
Entra: el estado del negocio que le pasa erplora.com.
Sale: nada guardado.
Si falla: una dirección que no es de ningún negocio no existe; un negocio dado de baja dice «Este hub ya no está
disponible.». Mientras el personal de ERPlora tiene congelada la plataforma por una subida de la base de datos
(unos minutos, hub#930), el negocio espera a prepararse: la página sigue en «Estamos preparando tu negocio» y entra
sola en cuanto se descongela y termina.
Implicados: ninguno

### BASE-F64 Cambiar mis datos, foto, idioma y apariencia
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
     tema», «Tema»: «Sistema (auto)», «Claro», «Oscuro», y «Tamaño de la interfaz»: 80, 90, 100, 110 o 120%, por
     defecto 100%) se guardan al elegir y se aplican al momento en cualquier dispositivo; «Usar la apariencia del
     negocio» deshace lo propio y devuelve el tamaño a 100%. El idioma pasa a toda la aplicación abierta, también a
     los textos que manda el servidor (el menú lateral, «Mis apps», el checklist, los paneles de Inicio y la campana),
     sin recargar ni volver a Inicio.
  5. Si se lo pide al asistente («ponme el idioma en inglés»), la tarjeta dice solo lo que ha pedido, con el nombre de
     su dato («Idioma: English», «Tamaño de la interfaz: 110%»; lo que vuelve a ser del negocio, por su nombre: «El
     idioma del negocio»). Al confirmarla cambia solo eso, y el tema, la
     paleta y el tamaño que no nombra siguen como estaban. El idioma nuevo se aplica igual que desde el selector: la
     aplicación abierta pasa a él sin recargar, y sigue en él al recargar o volver a abrirla en este dispositivo.
Entra: el perfil de quien tiene la sesión.
Sale: su nombre en este negocio (el que sale en el menú lateral, en las caras y en «Dispositivos»; sin él, el menú
lateral y las caras dicen el de su ficha de Personal vinculada, STAFF-F03), su foto, su idioma
y su apariencia, incluido el tamaño de interfaz, que le siguen en cualquier dispositivo en el que entre, con su PIN,
su placa o su cuenta. Con «Usar el idioma del negocio», entra con PIN en el del negocio y con su cuenta en el de su
cuenta de erplora.com (BASE-F51). El correo es solo de contacto: no cambia la cuenta de erplora.com.
Si falla: si el perfil no se pudo leer, «No se pudo cargar el perfil» — «Tus datos siguen igual. Comprueba la
conexión y vuelve a intentarlo.» con «Reintentar». Al guardar: «No se pudo guardar el perfil»; foto rechazada:
«No se pudo guardar la foto. Usa JPG, PNG o WebP de hasta 2 MB.»; preferencias: «No se pudieron guardar tus
preferencias. Comprueba la conexión e inténtalo de nuevo.».
Implicados: BASE-F51

### BASE-F65 Cambiar mi PIN desde Mi perfil
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
Si falla: longitud distinta: «El PIN debe tener 4 dígitos.»; los dos no coinciden: «Los dos PIN no
coinciden.»; fácil de adivinar: «Ese PIN es demasiado fácil de adivinar: evita dígitos repetidos (1111) y
secuencias (1234).»; ya lo usa otra persona: «Ese PIN ya lo tiene otra persona activa: elige otro.»; el actual no
es: «Ese no es tu PIN actual. Escríbelo bien para poder fijar uno nuevo.»; treinta intentos en una hora:
«Demasiados intentos de cambiar el PIN.» y los minutos que tiene que esperar.
Implicados: BASE-F54

### BASE-F66 Elegir cuántos dígitos tiene el PIN del negocio
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · General
Pasos:
  1. Con el pinpad encendido, bajo «Dígitos del PIN» elige «4 dígitos» o «6 dígitos».
  2. Se guarda al momento. Debajo: «Todo el mundo teclea el mismo número de dígitos, que es lo que permite que el
     teclado entre al último en vez de pedirte confirmar. Los PIN que ya se usan siguen funcionando hasta que su
     dueño los cambie.».
  3. Desde ese momento, el pinpad, la pantalla donde cada persona crea su PIN y **Mi perfil** piden esa longitud.
Entra: la elección.
Sale: la longitud del PIN del negocio. No toca los PIN que ya hay.
Si falla: «No se pudo cambiar. Comprueba la conexión e inténtalo de nuevo.».
Implicados: BASE-F67

### BASE-F67 Decidir si se pide PIN en la caja y cuándo se vuelve a pedir
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
     sesión», y debajo qué pasa («Una caja que nadie toca durante 10 minutos cierra la sesión y muestra el pinpad:
     la siguiente venta lleva el nombre de la siguiente persona.»).
  4. Cada cambio se guarda al momento, sin botón, y la tarjeta enseña lo que el negocio confirma.
  5. Por el asistente («quiero que en la caja cada uno tenga que meter su PIN para saber quién vende»), el
     asistente lee cómo está y lo dice con los nombres de esta tarjeta: con el pinpad encendido y «Hasta cerrar
     sesión», cada persona ya entra con su PIN y cada venta lleva su nombre. Para que vuelva a preguntar tras
     inactividad, antes le pregunta cuántos minutos (1, 5, 10, 15 o 30): nunca los pone él ni se quedan sin verse
     los que hubiera guardados. La tarjeta, con cada dato en su línea, dice cada control que cambia con
     su nombre y el valor que tendrá aquí: «Mostrar pinpad: Sí» y «Volver a preguntar tras inactividad: 10 min»;
     «Hasta cerrar sesión», «Mostrar pinpad: No» o «Dígitos del PIN: 6 dígitos» según el cambio. Si solo cambian
     los minutos y el negocio pregunta «Hasta cerrar sesión», dice «Volver a preguntar tras inactividad: Hasta
     cerrar sesión», que es lo que seguirá diciendo aquí.
Entra: cómo pide el PIN el negocio.
Sale: si se pide y cuándo se vuelve a pedir, para todas las cajas del negocio. Apagarlo y volver a encenderlo
vuelve a pedirlo por turno.
Si falla: «No se pudo cambiar. Comprueba la conexión e inténtalo de nuevo.». Si no se puede leer: «No se pudo
cargar cómo pide el PIN el negocio. Comprueba la conexión e inténtalo de nuevo.». Quien no administra ve los
controles apagados y «Solo un administrador puede cambiar si se pregunta.». Por el asistente, «tras
inactividad» sin sus minutos no llega a la tarjeta: vuelve al asistente, que pregunta cuántos.
Implicados: BASE-F55, BASE-F59, BASE-F97, BASE-F98

### BASE-F68 Ver los dispositivos en los que se ha entrado
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · General
Pasos:
  1. En **Ajustes**, bajo «Dispositivos»: «Los dispositivos en los que alguien ha entrado. Si pierdes uno, quítalo
     aquí: su sesión se cierra al momento y deja de poder entrar con PIN.».
  2. Una fila por dispositivo, el último en usarse primero: el nombre que le puso el negocio (o «Dispositivo sin nombre»
     y qué es, por ejemplo Chrome · Android), «El que estás usando» en el actual, el modo («Pide PIN» o «Se queda
     abierto»), «En uso ahora mismo» o «Se usó por última vez 24 nov 2026, 10:30», «Su sesión sigue abierta hasta 24 nov
     2026, 22:00» y «La última vez entró Ana». Nunca su identificador.
  3. Se pone al día sola cuando alguien cambia, nombra o quita un dispositivo.
Entra: los dispositivos del negocio.
Sale: nada guardado.
Si falla: quien no administra ve «Solo un administrador puede ver y quitar los dispositivos.», sin lista. Si no
llega: «No se pudieron cargar los dispositivos. Comprueba la conexión e inténtalo de nuevo.», nunca «Todavía no ha
entrado nadie desde ningún dispositivo.», que es solo para una lista de verdad vacía.
Implicados: BASE-F69, BASE-F70, BASE-F71

### BASE-F69 Ponerle nombre a un dispositivo
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
  4. Desde el asistente («quita el móvil que perdí esta tarde»), la tarjeta pide escribir CONFIRMAR y, bajo
     «Lo que va a pasar», dice cuándo se usó por última vez («Último uso: 22 nov 2026, 16:18»): dos dispositivos sin
     nombre se llaman igual («Chrome · Linux») y solo su último uso los distingue.
Entra: el dispositivo.
Sale: el dispositivo olvidado y sus sesiones cerradas: se corta el dispositivo, no la persona, que puede volver a
entrar en él con su cuenta.
Si falla: «No se pudo quitar este dispositivo. Comprueba la conexión e inténtalo de nuevo.» o «Ese dispositivo ya
no está registrado aquí. Actualiza la lista.»; nunca queda como hecho lo que se rechazó.
Implicados: BASE-F58, BASE-F68, BASE-F98

### BASE-F71 Quitar de golpe los dispositivos que nadie usa
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · General
Pasos:
  1. Si hay dispositivos que nadie ha usado en 30 días (nunca el que se tiene en la mano), sale «Quitar el
     dispositivo sin usar desde hace 30 días» o «Quitar los 3 dispositivos sin usar desde hace 30 días».
  2. Al pulsarlo, «¿Quitar 3 dispositivos que nadie usa desde hace 30 días?» (o «¿Quitar el dispositivo que nadie
     usa desde hace 30 días?») con «Dejan de aparecer aquí y, para volver a usar uno, alguien tendrá que entrar en
     él con su cuenta. Los usados en los últimos 30 días y el que estás usando se quedan.».
  3. Confirma con «Quitar».
  4. Desde el asistente («quita los dispositivos viejos que ya no usa nadie»), la tarjeta pide escribir CONFIRMAR y,
     bajo «Lo que va a pasar», dice cuántos va a quitar y cuáles, por su nombre, el último usado primero («Dispositivos
     que se quitan: 2» y «Cuáles: Chrome · Linux, Barra»); el que se está usando nunca está entre ellos. Si ninguno
     lleva 30 días sin usarse, no sale tarjeta y el asistente lo dice: «Ningún dispositivo lleva 30 días sin usarse, así
     que no hay nada que quitar.».
Entra: qué dispositivos lleva 30 días sin usar nadie.
Sale: esos dispositivos olvidados, como BASE-F70.
Si falla: «No se pudieron quitar los dispositivos sin usar. Comprueba la conexión y vuelve a intentarlo.».
Implicados: BASE-F70, BASE-F98

### BASE-F72 Ver los archivos del negocio
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Archivos
Pasos:
  1. Pulsa «Archivos» en el menú lateral. Mientras carga: «Cargando archivos…».
  2. Ve el árbol de carpetas a la izquierda (en una pantalla estrecha, el selector «Carpetas»), la ruta de la
     carpeta abierta, lo que hay en ella en «Cuadrícula» (lo primero que sale) o en «Lista», y «Espacio»: lo que
     ocupan los archivos del negocio y los de sus apps, contra el límite del plan («1,2 GB de 5 GB») o, si no tiene,
     «1,2 GB usados · Sin límite».
  3. Entra en una carpeta pulsándola en el árbol, en la cuadrícula o en el selector, y vuelve por la ruta. La carpeta
     abierta queda en el enlace, así que se puede compartir con el equipo.
  4. Busca por el nombre en «Buscar archivos…», solo dentro de la carpeta abierta; sin resultados, «Ningún archivo
     de esta carpeta coincide con «factura».».
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
Implicados: BASE-F40

### BASE-F73 Subir archivos y crear carpetas
Estado: hecho
Actor: propietario, administrador
Pantalla: Archivos
Pasos:
  1. En la carpeta abierta pulsa «Subir archivo» (la nube) y elige uno o varios, o los arrastra al gestor («Suelta los
     archivos para subirlos aquí»). Mientras suben: «Subiendo 2 de 5…».
  2. Sale «Archivos subidos.» y aparecen en la carpeta. Si ya había uno con el mismo nombre, no se pisa: el nuevo se
     guarda como «carta (1).pdf» y sale «Se ha subido como «carta (1).pdf»: ya había uno con ese nombre.».
  3. Para una carpeta nueva pulsa «Nueva carpeta», escribe el «Nombre de la carpeta» (hasta 100 caracteres) y pulsa
     «Crear carpeta». Sale «Carpeta creada.» y la carpeta aparece en el árbol y en la carpeta abierta.
  4. Desde el asistente se guarda igual un archivo adjunto en el chat: la persona le pide guardarlo en una carpeta, el
     asistente lo sube con su tarjeta, que lo dice por su nombre, y tras el «sí» queda en la carpeta, con las mismas
     reglas.
Entra: los archivos, de hasta 25 MB cada uno, o el nombre de la carpeta; la carpeta abierta.
Sale: el archivo o la carpeta, en los archivos del negocio (`base.file.uploaded`, `base.file.folder_created`).
Si falla: cada archivo rechazado dice por qué, sin parar los demás: «No se pudo subir «carta.pdf»:» y el motivo, «Ese
archivo pesa más de 25 MB, lo máximo que admite Archivos.», «Los programas (.exe) no se pueden guardar en Archivos:
podrían dañar a quien los abra.», «No queda espacio para ese archivo: tu plan incluye 5 GB.» o «El archivo no llegó
entero. Vuelve a subirlo.». Lo subido y lo rechazado salen en un solo aviso: se ve un aviso a la vez y el nuevo cierra
el anterior, nunca uno encima de otro. Al crear una carpeta, el diálogo sigue abierto con el motivo: «Ese nombre no es
válido. Usa un nombre sin barras ni puntos sueltos.» o «Ya hay un archivo o una carpeta con ese nombre aquí.». Quien no
administra el negocio no ve los botones y, si lo intenta igual, lee «Solo un administrador puede modificar los
archivos.».
Implicados: BASE-F40, BASE-F94

### BASE-F74 Previsualizar y descargar un archivo
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Archivos
Pasos:
  1. Pulsa un archivo, o «Abrir» en su ⋮. Se abre un visor grande dentro del hub, con el nombre como título,
     «Descargar» y «Cerrar».
  2. Enseña imágenes (enteras en el visor, nunca más grandes que el original, con «Ampliar» y «Reducir»), PDF (las
     primeras 30 páginas; si es más largo, «Mostrando las primeras 30 de 48 páginas. Descarga el archivo
     para leerlo entero.»), texto, registros y código, CSV y TSV como tabla (un CSV con sus columnas, vaya separado
     por comas o por punto y coma, como lo guarda Excel en español), audio y vídeo. De un texto muy largo,
     «Mostrando el principio del archivo. Descárgalo para leerlo entero.»; de una tabla de más de 500 filas,
     «Mostrando las primeras 500 filas. Descarga el archivo para verlas todas.».
  3. Un archivo de datos (.json) se ve como un árbol que se pliega y se despliega por partes, como el visor de JSON de
     los navegadores: los dos primeros niveles abiertos y cada objeto o lista con lo que tiene («6 campos»,
     «2 elementos»); de una rama abierta con más de 500 entradas, «120 más. Descarga el archivo para verlos
     todos.». Uno que no es JSON válido se ve tal cual, con «Este archivo no es un JSON válido: se muestra tal cual.».
  4. Una hoja de Excel (.xlsx o .xlsm) se ve como tabla, con una pestaña por hoja si tiene varias, como Excel: la
     primera fila de cabecera, los números y las fechas como los enseña la hoja, en el idioma de la persona, y las
     primeras 500 filas de cada hoja (con el mismo aviso); una hoja vacía, «Esta hoja está vacía.». Sus macros nunca
     se ejecutan.
  5. Un documento de Word (.docx) se ve como texto con su formato básico: títulos, negrita, cursiva, subrayado,
     listas, tablas, sus propias imágenes y enlaces (que se abren aparte); uno sin texto, «Este documento no tiene
     texto.». Nada del documento se ejecuta: ni código ni enlaces que no sean a una web o a un correo.
  6. Cualquier otro tipo (los .xls y .doc antiguos, presentaciones…): «Sin vista previa» con «Este tipo de archivo no
     se puede mostrar aquí. Descárgalo para abrirlo con una aplicación de tu dispositivo.».
  7. «Descargar», en el visor o en el ⋮, guarda el archivo con su nombre.
Entra: el archivo, que el hub lee de su almacén con la sesión de la persona; el navegador nunca va al almacén y el
archivo no queda guardado en ninguna caché. La hoja y el documento se leen en el propio navegador.
Sale: nada guardado.
Si falla: «No se pudo abrir el archivo» con «No llegó el contenido del archivo. Revisa la conexión e inténtalo de
nuevo.», nunca un visor en blanco; si llegó pero no se pudo leer (dañado o guardado en otro formato), «No se pudo leer
el archivo» con «Puede que esté dañado o guardado en otro formato. Descárgalo para abrirlo con una aplicación de tu
dispositivo.»; una hoja o un documento de más de 10 MB (o que al abrirlo ocuparía demasiado) ni se trae:
«Demasiado grande para la vista previa» con «La vista previa abre archivos de hasta 10 MB. Descárgalo para abrirlo
con una aplicación de tu dispositivo.». «Descargar» sigue siempre arriba. Si no se pudo descargar, «No se pudo
descargar «carta.pdf»:» y el motivo.
Implicados: BASE-F112 (dentro de la app)

### BASE-F75 Mover y renombrar un archivo o una carpeta
Estado: hecho
Actor: propietario, administrador
Pantalla: Archivos
Pasos:
  1. Para renombrar, elige «Renombrar» (o «Renombrar carpeta») en el ⋮: un diálogo con el nombre actual ya escrito
     (hasta 255 caracteres). Pulsa «Renombrar» y sale «Renombrado.».
  2. Para mover, elige «Mover a…»: «Mover «carta.pdf»» con las carpetas del negocio en árbol, empezando por
     «Archivos»; elige una y pulsa «Mover». También puede arrastrar el archivo o la carpeta a una carpeta del árbol o
     de la cuadrícula. Sale «Movido a «Facturas».» (a lo de arriba del todo, «Movido a «Archivos».»).
  3. Una carpeta se mueve o se renombra con todo lo que tiene. Si es la carpeta abierta (su ⋮, junto a la ruta), la
     pantalla la sigue a su sitio nuevo. Nunca se ofrece como destino de sí misma ni de las suyas.
Entra: el archivo o la carpeta y el nombre nuevo, o la carpeta de destino.
Sale: el cambio, en los archivos del negocio (`base.file.renamed`, `base.file.moved`).
Si falla: el diálogo sigue abierto con el motivo: «Ya hay un archivo o una carpeta con ese nombre aquí.», «Ya está en
esa carpeta.», «Una carpeta no se puede mover dentro de sí misma.», «Ese nombre no es válido. Usa un nombre sin barras
ni puntos sueltos.» o «Ese archivo o carpeta ya no existe. Actualiza la lista.»; al arrastrar, «No se pudo mover:» y el
motivo. Quien no administra el negocio no ve «Renombrar» ni «Mover a…» y, si lo intenta igual, lee «Solo un
administrador puede modificar los archivos.».
Implicados: ninguno

### BASE-F76 Borrar un archivo o una carpeta
Estado: hecho
Actor: propietario, administrador
Pantalla: Archivos
Pasos:
  1. Elige «Eliminar» (o «Eliminar carpeta») en el ⋮ de un archivo, de una carpeta o de la carpeta abierta.
  2. La pantalla pregunta: «Eliminar archivo» con «Vas a eliminar «carta.pdf». Esta acción no se puede deshacer.», o
     «Eliminar carpeta» con «Vas a eliminar «Facturas» y todo su contenido. Esto no se puede deshacer.».
  3. Pulsa «Eliminar» (o «Cancelar»). Sale «Archivo eliminado.» o «Carpeta eliminada.». Si eliminó la carpeta
     abierta, la pantalla sube a la de arriba.
Entra: el archivo o la carpeta.
Sale: el archivo o la carpeta, con todo lo que tenía, fuera de los archivos del negocio; no hay papelera
(`base.file.deleted`).
Si falla: «No se pudo eliminar:» y el motivo, «Ese archivo o carpeta ya no existe. Actualiza la lista.» o «Tu sesión
ha caducado. Vuelve a entrar e inténtalo otra vez.». Quien no administra el negocio no ve «Eliminar» y, si lo intenta
igual, lee «Solo un administrador puede modificar los archivos.».
Implicados: ninguno

### BASE-F77 Llegar al tope de personas del plan
Estado: hecho
Actor: propietario, administrador
Pantalla: Empleados · Personal
Pasos:
  1. En **Empleados › Personal**, encima de la tabla, cuántas plazas del plan están ocupadas: «3 de 5 plazas ocupadas»,
     «3 personas · sin límite» o, si erplora.com no ha dicho el plan, «3 personas». La gestoría no ocupa plaza: sale en
     la lista, pero no cuenta aquí ni en «Uso y plan» de Sistema.
  2. Con todas ocupadas sale «Tu plan tiene todas las plazas ocupadas» y «Quita en erplora.com a alguien que ya no
     trabaje aquí, o pasa a un plan con más plazas.»; en la web, y para el propietario, con «Mejorar plan».
  3. Para invitar a alguien más, «Invitar en erplora.com» lleva a «Miembros» del negocio, donde se aplica el tope
     (en la app instalada, en el navegador del dispositivo; en la de Google Play no está).
Entra: las personas del negocio y las plazas de su plan, como las manda erplora.com.
Sale: nada guardado.
Si falla: «No se pudo cargar el personal de este negocio.» con «Reintentar», nunca «Todavía no hay nadie en este
negocio.».
Implicados: BASE-F81, BASE-F83

### BASE-F78 Retirar el PIN a una persona
Estado: hecho
Actor: propietario, administrador
Pantalla: Ficha de una persona
Pasos:
  1. En **Empleados › Personal**, toca a la persona: se abre su ficha.
  2. En «PIN», «Tiene PIN desde el 24 nov 2026, 10:30.» y «Retirar el PIN».
  3. Lo pulsa: «Retirar el PIN» con «Ana dejará de entrar en las cajas con su PIN. Con su cuenta de erplora.com
     sigue entrando.». Confirma con «Retirar el PIN».
  4. Sale «PIN retirado.» y la ficha dice «Sin PIN: lo elige la propia persona en «Mi perfil» o la primera vez que
     entra en una caja.».
Entra: la persona.
Sale: la persona sin PIN: desaparece de las caras de las cajas al momento. Evento `base.person.pin_removed`.
Si falla: «No se pudo retirar el PIN.»; el acceso del propietario solo lo cambia el propietario: «Solo el
propietario cambia el acceso del propietario.».
Implicados: BASE-F81, BASE-F55

### BASE-F79 Dar de alta o retirar la placa de una persona
Estado: hecho
Actor: propietario, administrador
Pantalla: Ficha de una persona
Pasos:
  1. En la ficha de la persona, en «Placa»: «Pasa la tarjeta y se rellena sola: no hace falta hacer clic aquí antes.
     También puedes teclear el número, para un llavero o una etiqueta grabada.».
  2. Pasa la tarjeta por el lector (o teclea el número) y pulsa «Guardar placa»: «Placa guardada.» y «Tiene placa
     desde el 24 nov 2026, 10:30.».
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
Estado: hecho
Actor: propietario, administrador
Pantalla: Empleados · Personal
Pasos:
  1. Quien salió del negocio ya no está en **Empleados › Personal**: se quitó en erplora.com.
  2. Para que vuelva, «Invitar en erplora.com» y se la invita otra vez en «Miembros» del negocio, con su rol (en la
     app instalada, en el navegador del dispositivo; en la de Google Play no está).
  3. Cuando acepta, vuelve a la lista con lo que el negocio guardaba de ella: su PIN y su placa siguen valiendo.
Entra: la invitación en erplora.com.
Sale: la persona otra vez en el negocio, con su PIN y su placa de antes.
Si falla: mientras no acepta, sale como «Aún no ha entrado».
Implicados: BASE-F77, BASE-F81

### BASE-F81 Entender cómo entra cada persona
Estado: hecho
Actor: propietario, administrador, encargado, empleado, gestoría
Pantalla: Empleados · Personal
Pasos:
  1. En **Empleados › Personal**, una fila por persona (en el móvil, una tarjeta): **Usuario** (con «Tú» en la suya; en
     una fila, un nombre que no cabe se corta y sale entero al pasar por encima), **Email** (solo para quien ve el
     contacto del equipo: propietario, administrador y encargado), **Rol** (la gestoría, la última), **Acceso** y
     **Estado**.
  2. **Acceso** dice cómo entra: «Cuenta» siempre, y «PIN» y «Placa» si los tiene (por ejemplo, «Cuenta + PIN +
     Placa»).
  3. **Estado** dice «Activo» o, si erplora.com ya la invitó y aún no ha entrado, «Aún no ha entrado».
  4. Busca con «Buscar persona…». Quien administra toca una fila para abrir su ficha.
Entra: las personas del negocio.
Sale: nada guardado. Se pone al día sola cuando alguien elige o pierde su PIN o su placa.
Si falla: «No se pudo cargar el personal de este negocio.» con «Reintentar».
Implicados: BASE-F77, BASE-F78, BASE-F79, BASE-F119

### BASE-F82 Ver los roles del negocio y lo que permite cada uno
Estado: hecho
Actor: propietario, administrador, encargado, empleado, gestoría
Pantalla: Empleados · Roles; Empleados · Roles · Qué permite
Pasos:
  1. En **Empleados › Roles**: «Estos son los roles de este negocio. Cada persona recibe uno al invitarla en
     erplora.com, y allí se cambia.».
  2. Una fila por rol (en el móvil, una tarjeta): «Propietario», «Administrador», «Encargado», «Empleado» y
     «Gestoría», con «Básico», cuántas personas lo tienen y cuántos permisos da. Son los roles básicos de erplora.com:
     cada app aporta lo que da a cada rol básico en ella, y una app puede traer un rol básico propio cuando su
     funcionalidad lo pida. Debajo, por su nombre, los roles propios del negocio, con «Propio»: quien
     tiene uno cuenta en él y no en el de su invitación, salvo el propietario, que siempre es el propietario. Uno propio
     con permisos que aún no lleva dice además «Por revisar».
  3. «Gestoría» es el de la asesoría que lleva las cuentas del negocio, y solo lee: las ventas de todos, con los
     totales del negocio, y las facturas emitidas, que abre, imprime y descarga, cada una con sus impuestos y su
     registro de VeriFactu. En el menú le salen Ventas y Facturación. No vende, no cobra, no emite ni rectifica
     facturas y no cambia ningún ajuste, y no ocupa plaza del plan.
  4. Al tocar un rol se abre «Qué permite», con el nombre del rol arriba, «Lo que este rol deja hacer en este negocio,
     app por app. Se da en erplora.com y aquí no se cambia.» y «Personas con este rol: 2». Debajo, un panel por app: «El
     negocio» primero, después cada app encendida por su nombre y «Datos sensibles» al final. En cada panel, la frase de
     cada permiso y su estado: «Permitido», «Con aprobación» (lo hace si un responsable lo aprueba con su PIN en ese
     momento) o «No». Por ejemplo, el empleado ve en «Ventas / TPV» «Anular una venta» con «Con aprobación». Una app
     apagada no sale. Es solo lectura: aquí no se cambia nada. En un rol propio pone «Lo que este rol deja hacer en este
     negocio, app por app.» y sale lo que el negocio guardó; lo que no se puede dar en un rol propio, ser el propietario
     del negocio, no sale. Quien gestiona los roles lo ajusta ahí mismo.
  5. Quien gestiona los roles (el propietario y el administrador, o quien lo tenga en su rol propio) crea uno con
     «Nuevo rol» o «Duplicar» y, en «⋮», edita o borra los propios.
  6. Quien administra tiene «Cambiar roles en erplora.com» (en la app instalada, en el navegador del dispositivo; en la de Google Play no está).
Entra: los roles, las personas del negocio, las apps encendidas y lo que cada app da a cada rol.
Sale: nada guardado.
Si falla: «No se pudo cargar el catálogo de roles.» con «Reintentar»; en «Qué permite», «No se pudo cargar lo que
permite este rol.» con «Reintentar», y un rol que no es de los cinco ni de los propios, «Este rol no existe en este
negocio.».
Implicados: BASE-F83, BASE-F84, BASE-F127, BASE-F128, BASE-F129, BASE-F130, BASE-F131, BASE-F77

### BASE-F83 Asignar un rol básico a una persona
Estado: hecho
Actor: propietario, administrador
Pantalla: Empleados · Roles
Pasos:
  1. En **Empleados › Roles** o en la ficha de una persona, «Cambiar roles en erplora.com» o «Abrir en
     erplora.com» lleva a «Miembros» del negocio (en la app instalada, en el navegador del dispositivo; en la de
     Google Play no están).
  2. Allí le cambia el rol.
  3. Al volver, la persona sale con su rol nuevo. Si tiene el hub abierto, lo que ve y lo que puede hacer
     cambian al momento, sin cerrar su sesión. Si el negocio le dio un rol propio, ese sigue mandando.
Entra: el rol que se elige en erplora.com.
Sale: la persona con su rol nuevo, como lo manda erplora.com, y su sesión abierta.
Si falla: lo que diga erplora.com.
Implicados: BASE-F82, BASE-F13, BASE-F130

### BASE-F127 Crear un rol propio a partir de otro
Estado: hecho
Actor: propietario, administrador
Pantalla: Empleados · Roles; Asistente
Pasos:
  1. En **Empleados › Roles**, «Duplicar» en la fila de un rol, básico o propio, o «Nuevo rol» arriba, que parte del
     de empleado.
  2. En «Nuevo rol» escribe el «Nombre» y, si quiere otro, elige «A partir de» entre todos los roles: «Permitirá lo
     mismo que ese rol. Después ajustas lo que permite.».
  3. «Crear rol»: el rol queda creado con lo mismo que permite el otro, app por app, menos ser el propietario del
     negocio, que ningún rol propio da. Sale «Rol Cajero creado» y se abre para ajustarlo.
  4. Sale al momento en **Empleados › Roles**, con «Propio» y nadie en él; se da a una persona pidiéndoselo al asistente.
     Desde entonces no cambia con el rol del que salió.
  5. También se pide al asistente: «crea el rol Cajero a partir de Empleado», con una descripción si se quiere. La
     tarjeta dice «A partir de: Empleado» y «Nombre: Cajero», y al aceptarla queda creado igual.
Entra: el rol del que parte, el nombre (hasta 80 letras) y, si se quiere, la descripción.
Sale: el rol propio del negocio. Evento `base.role.created`. No sale del negocio: erplora.com no lo conoce.
Si falla: sin nombre, «Crear rol» no se puede pulsar (el asistente y la API: «Ponle nombre al rol.»); con el nombre de otro rol propio, sin contar mayúsculas, «Ya hay un rol
con ese nombre. Elige otro.»; un rol que no está, «Este rol no existe en este negocio.». Nadie da lo que no tiene: si
el rol del que parte permite algo que quien lo crea no puede hacer, o deja «Con aprobación» algo a lo que su propio rol
le dice «No», «Un rol no puede permitir más de lo que puedes hacer tú.» y no se crea. Lo que se rechaza se dice en
la propia ventana, que sigue abierta. A quien no gestiona roles no le salen «Nuevo rol» ni «Duplicar», el asistente no
se lo ofrece y la API contesta 403.
Implicados: BASE-F82, BASE-F97, BASE-F128, BASE-F129, BASE-F130

### BASE-F128 Ajustar lo que permite un rol propio
Estado: hecho
Actor: propietario, administrador
Pantalla: Empleados · Roles · Qué permite; Asistente
Pasos:
  1. En **Empleados › Roles**, toca un rol propio, o «Editar» en su «⋮». Arriba, «Lo que este rol deja hacer en este
     negocio, app por app. Al guardar, quien lo tiene lo nota al momento.», cuántas personas lo tienen y su «Nombre» y
     «Descripción», que se cambian ahí. Debajo, los mismos paneles de «Qué permite»: cada permiso con su frase
     y un interruptor o, en lo que un responsable puede aprobar con su PIN, «Permitido», «Con aprobación» o «No».
  2. Cambia lo que quiera y pulsa «Guardar» al final: «Rol guardado.». Sin nada cambiado, «Guardar» no se puede pulsar.
  3. Si otra persona lo guarda mientras tanto, lo que aquí no se ha tocado se pone al día.
  4. También se pide al asistente: «que el rol Cajero no pueda anular ventas», «llama Caja de tarde al rol Cajero».
     La tarjeta dice el rol, cada permiso con la misma frase de «Qué permite» y lo que pasará a hacer («Permitido»,
     «Con aprobación» o «No»), y, bajo «Lo que va a pasar», cuántas personas tienen ese rol. Pide escribir CONFIRMAR,
     y al aceptarla solo cambia lo que se pidió.
  5. Si alguien tiene el rol, lo que ve y lo que puede hacer cambian al momento en sus dispositivos, sin cerrar su
     sesión.
  6. Una app que se enciende después de guardar el rol da lo que da al rol básico del que salió; un permiso que una app
     añade después entra en «No». En los dos casos el rol queda por revisar hasta que se guarda con ellos, y la campana
     lo dice. Al abrirlo, «Permisos nuevos por revisar» arriba y «Por revisar» en cada uno: «Guardar», cambiando algo o
     sin cambiar nada, los da por revisados.
Entra: el rol y lo que cambia: el nombre, la descripción o el estado de cada permiso.
Sale: el rol cambiado. Evento `base.role.updated`.
Si falla: un rol básico no se cambia: «Este rol es de erplora.com. Duplícalo y cambia la copia.». Nadie da lo que no
tiene, tampoco «Con aprobación» lo que su propio rol le niega: «Un rol no puede permitir más de lo que puedes hacer
tú.»; y ser el propietario no se da a nadie: «Eso es solo del propietario del negocio: ningún rol lo da.». Un permiso que
no es de una app encendida, «Ese permiso no es de ninguna app encendida de este negocio.»; «Con aprobación» en algo que
un responsable no puede aprobar con su PIN, «Eso no se puede aprobar con un PIN: elige permitido o no.». El nombre, como
al crearlo. Lo que se rechaza en la pantalla se dice junto a «Guardar», con «No se pudo guardar el rol», o bajo el
nombre, y lo que se estaba cambiando sigue puesto. Quien no gestiona los roles lo ve de solo lectura.
Implicados: BASE-F13, BASE-F82, BASE-F84, BASE-F97, BASE-F98, BASE-F127, BASE-F131

### BASE-F129 Borrar un rol propio
Estado: hecho
Actor: propietario, administrador
Pantalla: Empleados · Roles; Asistente
Pasos:
  1. En **Empleados › Roles**, «Borrar» en el «⋮» de un rol propio.
  2. «¿Borrar el rol Cajero? No se puede deshacer.»: al confirmarlo, «Rol Cajero borrado», y desaparece de la lista.
  3. También se pide al asistente: «borra el rol Cajero». La tarjeta dice el rol y, bajo «Lo que va a pasar», cuántas
     personas lo tienen, y pide escribir CONFIRMAR.
  4. Quien salió del negocio con ese rol, si vuelve, entra con el de su invitación.
Entra: el rol.
Sale: el rol borrado. Evento `base.role.deleted`.
Si falla: si alguien del negocio lo tiene, no se borra: «2 personas tienen este rol. Dales otro antes de borrarlo.», en
la misma pregunta, que sigue abierta. Un rol básico no tiene «Borrar»; al asistente y a la API se les contesta «Este rol
es de erplora.com. Duplícalo y cambia la copia.».
Implicados: BASE-F82, BASE-F97, BASE-F98, BASE-F127, BASE-F130

### BASE-F130 Dar un rol propio a una persona
Estado: parcial — se da pidiéndoselo al asistente o por la API del Hub; falta su sitio en la ficha de la persona
Actor: propietario, administrador
Pantalla: Asistente
Pasos:
  1. Pide al asistente «dale a Luis el rol Cajero» o «quítale a Luis el rol Cajero».
  2. La tarjeta dice la persona y el rol por sus nombres y, bajo «Lo que va a pasar», cuántas personas tienen ese rol.
     Pide escribir CONFIRMAR (BASE-F98).
  3. Al aceptarla, la persona queda con ese rol, que manda sobre el de su invitación: lo que ve y lo que puede hacer
     cambian al momento en sus dispositivos, sin cerrar su sesión (BASE-F13), y quien ahora puede hacer algo con ese rol
     lo aprueba también con su PIN (BASE-F84). Cada persona tiene un solo rol.
  4. Para devolverla al de su invitación se le pide ese rol («Empleado»): es el que tiene desde entonces.
  5. El asistente de esa persona sabe con qué rol habla: el propio, por el nombre que le puso el negocio (BASE-F100).
Entra: la persona y el rol, uno propio del negocio o el de su invitación.
Sale: la persona con ese rol. Evento `base.role.assigned`. erplora.com no lo sabe: allí sigue con el de su invitación.
Si falla: al propietario nadie le da otro rol, «El propietario siempre es el propietario: nadie le da otro rol.»; nadie
se lo cambia a sí mismo, «Nadie se cambia su propio rol: pídeselo a alguien por encima de ti.»; ni a quien no está por
debajo en su invitación, «Solo puedes dar un rol a quien está por debajo de ti en el negocio.». Nadie da un rol que
permite más de lo que puede hacer él, tampoco el de la invitación al devolverla, ni lo que daría una app apagada, ni
«Con aprobación» lo que su propio rol le niega: «Un rol no puede permitir más de lo que puedes hacer tú.». Otro rol
básico, «Ese rol se da en erplora.com. Aquí se da uno propio del negocio.»; un rol que no está, «Este rol no existe en
este negocio.»; una persona que no es del negocio, «Esa persona no está en este negocio.». Si alguien borra el rol a la
vez, o se borra o se da, nunca las dos cosas: se oye el «Este rol no existe en este negocio.» o el «2 personas tienen
este rol. Dales otro antes de borrarlo.».
Implicados: BASE-F13, BASE-F82, BASE-F84, BASE-F97, BASE-F98, BASE-F100, BASE-F127, BASE-F129

### BASE-F131 Ver en la campana los roles por revisar
Estado: hecho
Actor: propietario, administrador
Pantalla: La campana; Empleados · Roles; Empleados · Roles · Qué permite
Pasos:
  1. Se enciende una app, o una app gana un permiso, después de guardar un rol propio: ese rol queda por revisar.
  2. La campana de quien gestiona los roles sube sin recargar con el aviso «2 roles por revisar» y su frase: «Hay una
     app encendida o un permiso nuevo que aún no llevan: mira lo que permite cada rol.».
  3. «Revisar los roles» abre **Empleados › Roles**, donde ese rol lleva «Por revisar».
  4. Al abrirlo, «Permisos nuevos por revisar» y cada uno marcado con «Por revisar». Elige qué hace el rol con cada uno y
     pulsa «Guardar», aunque no cambie nada.
  5. Al guardarlo deja de llevar la marca y de contar; sin ninguno, el aviso desaparece.
Entra: los roles propios del negocio y las apps encendidas.
Sale: nada guardado.
Si falla: quien no gestiona los roles no ve el aviso. Si no se pueden leer los avisos, la campana se queda con lo último
que supo, como con los demás avisos.
Implicados: BASE-F10, BASE-F82, BASE-F128

### BASE-F84 Aprobar con el PIN de un responsable
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
  5. A quien tiene un rol propio (BASE-F130) se le pregunta según lo que ese rol dice de esa acción: «Permitido», la
     hace sin preguntar; «Con aprobación», sale la pregunta; «No», no hay pregunta: se rechaza y ningún PIN la deja
     pasar, tampoco una aprobación que ya le hubieran dado. Si el rol cambia, vale desde la acción siguiente, sin cerrar
     la sesión (BASE-F13). Una app que se encendió después de guardar el rol pregunta como el rol básico del que salió;
     un permiso que una app añadió después está en «No» hasta que se revisa (BASE-F131). Al propietario no se le pregunta
     nunca.
  6. Quien puede hacerla por su rol no ve la pregunta: la hace y queda anotada como hecha por él, sin que nadie la
     apruebe (BASE-F85).
  También desde el asistente: el «sí» de su tarjeta abre el mismo diálogo, con las cifras de lo que se le pidió.
Entra: el nombre y el PIN, o la placa, de quien aprueba.
Sale: una aprobación que vale para esa acción, de esa persona, una sola vez y durante dos minutos; queda anotada en
**Empleados › Aprobaciones** (BASE-F85). Eventos `base.approval.granted` y `base.approval.used`; el de una acción hecha
por quien puede, `base.approval.noted`. La aprobación se gasta junto con la acción:
si la acción falla por un motivo del negocio, la aprobación sigue sin usar y la misma acción, repetida en esos dos
minutos, pasa con ella; si salió bien, no se repite; dos a la vez con la misma, solo pasa una. Lo que la acción
aprobada hace por el camino en otras apps (la factura rectificativa de una anulación, las sesiones de bono que
devuelve) va con la aprobación, como cuando lo hace el propio responsable; nada más: ni lo que solo se consulta ni la
acción siguiente. Quien no es del negocio recibe el rechazo de siempre, sin la pregunta de la aprobación.
Si falla: el diálogo se queda abierto con «Esos datos no aprueban esto. Revisa el nombre y el PIN, y vuelve a
intentarlo.», «Esa persona no puede aprobarlo: pídeselo a alguien que pueda hacerlo.» (tampoco quien lo hace «Con
aprobación»), «Esto ya no necesita aprobación: vuelve a hacerlo.», «Esto no se aprueba con un PIN.» (también si
mientras tanto el rol de quien lo pide pasó a «No»), la espera tras demasiados intentos o «No se pudo enviar la
aprobación. Comprueba la conexión y vuelve a intentarlo.». Sin nadie con PIN que pueda: «Aquí nadie puede aprobarlo con
un PIN. Quien pueda hacerlo puede pasar su placa.». «Cancelar» devuelve a la app su rechazo.
Implicados: BASE-F85, BASE-F55, BASE-F56, BASE-F100, BASE-F128, BASE-F130, SALE-F30, SALE-F31

### BASE-F85 Consultar quién aprobó qué
Estado: hecho
Actor: propietario, administrador
Pantalla: Empleados · Aprobaciones
Pasos:
  1. En **Empleados › Aprobaciones** (la pestaña solo existe para quien administra): «Cada acción que puede necesitar la
     autorización de un encargado: quién la hizo, quién la autorizó y con qué. Nadie, tampoco un administrador, puede
     editarlo ni borrarlo.».
  2. Una fila por acción, la última primero: «Cuándo», «Acción» (en palabras y en su idioma; con las cifras de lo que
     se hizo, cuando la app las da: una aprobación que nadie usó no hizo nada y no lleva cifras), «Autorizado por»,
     «Quién» (quien la hizo, o la pidió), «Con» («PIN», «Placa» o «Su rol») y «Estado» («Hecha», o «Sin hacer» si la
     aprobación no se usó).
  3. Las que hizo por su cuenta alguien a quien su rol se lo permite salen también: el encargado que anula una venta o da
     un descuento por encima del máximo, el propietario, quien lo tiene «Permitido» en su rol propio y lo
     mismo pedido al asistente, con quien dijo que sí. Dicen «Su rol» en «Con» y dejan vacío «Autorizado
     por». Una fila por acción: no sale la que se rechazó o falló, ni el reintento de una que ya se hizo, ni la que no
     cambió nada, ni lo que hace el sistema o una automatización.
  4. Busca con «Buscar por persona o acción…» (también por sus cifras) y, en «Filtros» (el embudo), filtra por
     «Cuándo» (un día o unos días seguidos), «Acción» (las que hay en el registro, cada una una vez y sin cifras),
     «Con» y «Estado».
  5. «Exportar CSV» descarga un archivo con las acciones que dejan la búsqueda y los filtros, también las más antiguas
     que la lista ya no enseña (las 500 últimas), con las mismas columnas en su idioma; mientras tanto dice
     «Exportando…».
Entra: el registro de aprobaciones.
Sale: nada; es solo lectura (el archivo exportado no cambia nada). Se pone al día sola con cada aprobación y con cada
acción.
Si falla: «No se pudo cargar el registro de aprobaciones.» con «Reintentar»; sin ninguna, «Todavía no hay ninguna acción
de este tipo en este negocio.» (y el archivo exportado trae solo la cabecera). Si no se puede exportar, un aviso lo dice
con su motivo y no se descarga nada.
Implicados: BASE-F84, BASE-F100, BASE-F128, SALE-F30, SALE-F31, BASE-F112 (dentro de la app)

### BASE-F86 Crear una llave de API y copiar su token
Estado: hecho
Actor: propietario, administrador
Pantalla: Empleados · API keys
Pasos:
  1. En **Empleados › API keys**: «Una llave deja que otro sistema (el de tu gestoría, tu tienda online) lea o
     escriba datos de este negocio por su API.» y «Nueva API key».
  2. En «Nueva API key», el «Nombre» («Gestoría — facturas»), las «Peticiones por minuto» («De 1 a 10.000.») y
     «Qué puede hacer esta key»: «Elegir apps» o «Todas las apps», con las casillas «Leer», «Crear», «Modificar» y
     «Borrar» de cada app o, en «Todas las apps», una sola vez para todas («Todas las apps de tu negocio, también las
     que añadas después.»). Solo sale la casilla de lo que quien la crea puede dar: en lo demás hay un guion, y la app
     en la que no puede dar nada no sale, ni «Todas las apps» si no puede dar nada en todas. Con «Crear key» vale lo
     marcado en la opción elegida.
  3. Pulsa «Crear key»: sale «API key creada» con «Copia el token ahora», «Este es el único momento en que se
     muestra el secreto completo. Guárdalo en un lugar seguro: no se volverá a mostrar.» y «Copiar» (dos segundos
     dice «Copiado»). «Hecho» la cierra.
  4. Lo que puede hacer una llave son cuatro acciones, en todas las apps (también las que se añadan después) o app
     por app: leer, crear, modificar y borrar, cada una por separado. Una llave con «Leer» en Inventario lee sus
     productos; crear, modificar o borrar uno, o abrir otra app, se le niega.
  5. Una llave nunca recibe más de lo que puede hacer quien la crea: en una app, una acción que no puede hacer en
     ninguna de sus llamadas; en todas las apps, una acción que no puede hacer en alguna app que la publica.
Entra: el nombre, el ritmo y lo que puede hacer.
Sale: la llave, de la que el negocio solo guarda lo que permite reconocerla, y quién la creó, que pone su techo
(BASE-F125). Evento `base.api_key.created`.
Si falla: sin nombre o sin ninguna casilla marcada, «Crear key» no se puede pulsar; sin ninguna app en la que dar
nada, «No hay ninguna app a la que puedas dar acceso.». «No se pudo crear la API key.», «Elige al menos una app y qué
puede hacer la key en ella.», «Esa app no publica lo que la key haría en ella.», «Una key no puede hacer más de lo que
puedes hacer tú.» o «No se pudo copiar al portapapeles.».
Implicados: BASE-F89, BASE-F90, BASE-F119, BASE-F125

### BASE-F87 Rotar una llave de API
Estado: hecho
Actor: propietario, administrador
Pantalla: Empleados · API keys
Pasos:
  1. En la fila de la llave, «Rotar».
  2. «Rotar la API key» con ««Tienda online» recibe un token nuevo. El actual deja de funcionar de inmediato.»; confirma
     con «Rotar».
  3. Sale el token nuevo, una sola vez, con «Copiar».
Entra: la llave.
Sale: la llave con un token nuevo; el anterior deja de abrir nada al momento. Evento `base.api_key.rotated`.
Si falla: «No se pudo rotar la API key.», «Esa key está revocada: no vuelve a funcionar.» o «Esa key ya no existe.
Actualiza la lista y vuelve a intentarlo.».
Implicados: BASE-F86, BASE-F89

### BASE-F88 Revocar una llave de API
Estado: hecho
Actor: propietario, administrador
Pantalla: Empleados · API keys
Pasos:
  1. En la fila de la llave, «Revocar».
  2. «Revocar API key» con «Vas a revocar «Tienda online». Cualquier sistema que use este token dejará de tener acceso
     de inmediato. Esta acción no se puede deshacer.»; confirma con «Revocar».
  3. Sale ««Tienda online» revocada.» y la fila queda como «Revocada», sin «Rotar» ni «Revocar».
Entra: la llave.
Sale: la llave revocada para siempre; se guarda en la lista. Evento `base.api_key.revoked`.
Si falla: «No se pudo revocar la API key.».
Implicados: BASE-F89

### BASE-F89 Ver las llaves de API y qué puede cada una
Estado: hecho
Actor: propietario, administrador
Pantalla: Empleados · API keys
Pasos:
  1. En **Empleados › API keys** (la pestaña solo existe para quien administra), una fila por llave: «Nombre»,
     «Token» (solo su principio), «Permisos», «Estado» («Activa» o «Revocada»), «Creada por», «Creada», «Último uso»
     («Nunca» si no se ha usado) y «Límite». «Permisos» dice «Acceso total», «Solo lectura» o «Solo escritura» si la
     llave lo es en todas las apps; si no, sus acciones en «Todas las apps» y app por app, con su inicial: L (leer),
     C (crear), M (modificar) y B (borrar), como «Tienda online L/C · Impuestos L». «Creada por» dice el nombre de
     quien la creó, nunca su dirección de correo.
  2. Busca con «Buscar API key…». Al pie, un enlace lleva a la documentación de la API.
Entra: las llaves del negocio.
Sale: nada guardado. Se pone al día sola al crear, rotar o revocar una.
Si falla: «No se pudieron cargar tus API keys.» con «Reintentar»; sin ninguna, «Aún no hay API keys. Crea una para
que un sistema externo pueda leer o escribir datos de tu negocio.».
Implicados: BASE-F86, BASE-F87, BASE-F88, BASE-F125

### BASE-F90 Consultar la documentación de la API
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
«Ninguna app de este negocio publica todavía su API.».
Implicados: BASE-F91, BASE-F86, BASE-F112 (dentro de la app)

### BASE-F91 Mostrar u ocultar la documentación de la API
Estado: hecho
Actor: propietario, administrador
Pantalla: Ajustes · General
Pasos:
  1. En **Ajustes › General**, en la tarjeta de la documentación de la API, el interruptor «Mostrar documentación de la
     API» («Añade una página con la documentación de la API, para quien conecte otro sistema.»). Viene apagado.
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
| Cargando | La tabla en gris en «Personal», «Roles», «API keys» y «Aprobaciones»; «Cargando…» en la ficha de una persona; «Cargando lo que permite este rol…» en «Qué permite»; las caras en gris en «Hace falta una aprobación»; «Cargando la documentación…». |
| Vacío | «Todavía no hay nadie en este negocio.», «Aún no hay API keys. Crea una para que un sistema externo pueda leer o escribir datos de tu negocio.», «Todavía no hay ninguna acción de este tipo en este negocio.», «Aquí nadie puede aprobarlo con un PIN. Quien pueda hacerlo puede pasar su placa.» y «Ninguna app de este negocio publica todavía su API.». |
| Error | «No se pudo cargar el personal de este negocio.», «No se pudo cargar el catálogo de roles.», «No se pudieron cargar tus API keys.», «No se pudo cargar el registro de aprobaciones.», «No se pudo abrir a esta persona.», «No se pudo cargar lo que permite este rol.», «No se pudo cargar quién puede aprobarlo.» y «No se pudo cargar la documentación.», cada uno con «Reintentar»; nunca la lista vacía. |
| Sin permiso | Quien no administra no tiene las pestañas «API keys» ni «Aprobaciones» (su dirección abre «Personal»), no ve el email de nadie ni abre la ficha de una persona; en Ajustes, «Solo quien administra el negocio puede cambiarlo.». Con la documentación oculta: «La documentación de la API está oculta en este negocio.». |

### BASE-F92 Abrir y cerrar el panel del asistente
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Asistente
Pasos:
  1. Con la sesión abierta, pulsa los destellos «Asistente» de la barra de arriba, al lado de la campana. Volver a
     pulsarlos lo cierra. En un móvil, los destellos y «Mis apps» van en «⋮» («Más acciones»), para que el título
     se lea entero, y la campana y el «?» de la ayuda se quedan a la vista: ahí, «Asistente» abre el panel en cuanto el
     menú termina de cerrarse, así que lo que se escribe enseguida va a la caja del chat y el Intro lo envía.
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
     mueven hasta que llega el primer texto. En español, el asistente le trata de tú o de usted como ella le escribe
     (si no se nota, de tú, como las pantallas) y lo mantiene hasta el final de la respuesta, sin mezclarlos. Todo lo
     que escribe va en el idioma de la persona, también lo que dice mientras consulta o antes de sacar una tarjeta: ni
     una frase en inglés ni palabras de otro alfabeto; los nombres de los registros, tal como están escritos.
  4. Mientras responde, «Enviar» se convierte en «Detener», «Adjuntar archivo» y «Dictar por voz» se apagan y la
     respuesta va apareciendo; la conversación baja sola hasta el final. Se puede ir escribiendo la siguiente
     pregunta, pero no se envía hasta que acaba esta.
  5. Si pregunta cómo se hace algo en ERPlora, qué significa una opción o qué incluye un plan («¿Cómo abro la caja?»),
     el asistente busca en la documentación de ERPlora (la ayuda, la de cada app y los planes) y contesta solo con lo
     que dice, y termina la respuesta con una línea «Fuente: …» que nombra la sección de la que sale (sus títulos o, si
     no los tiene, su ruta), para que la persona pueda comprobarla y leer más; si la documentación no lo cubre, lo dice
     en lugar de inventarlo.
  6. Si el asistente acaba sin decir nada, la burbuja dice «(sin respuesta)».
  7. «Detener» corta lo que faltaba: lo ya escrito se queda, con «Detenido.» debajo.
  8. Bajo cada respuesta terminada, «Leer en voz alta» la lee con la voz del dispositivo, si la tiene, y «Dejar de
     leer» la para. Si ERPlora tiene activadas sus propias voces (hoy no), la cabecera del panel deja elegir entre las
     dos del idioma de la pantalla (la primera, hasta que se elige otra; el dispositivo recuerda la elección) y la «Voz
     del dispositivo».
  9. Si le pide algo que se hace con los datos del negocio («sube un 5 % las bebidas», «da de alta la tónica a
     2,50 €»), el asistente lo hace con las mismas acciones que esa persona tiene en las pantallas de sus apps, y lo
     que cambia algo, con la confirmación de BASE-F97. Si entre las que tiene a mano para ese mensaje no está la que
     hace falta, la busca entre todas las de esa persona y la usa en el paso siguiente; solo si no existe dice en qué
     pantalla se hace. Si lo pedido lo hace una app que el negocio no tiene activada, dice qué app es y ofrece
     activarla (BASE-F24).
  10. El asistente sabe de entrada dónde está el negocio y qué hora es allí: su país, su zona horaria con la fecha y la
     hora de ese momento, el idioma del negocio y el que la persona eligió en «Mi perfil», su sector, las apps que
     tiene encendidas, a quien lo administra su plan y cuántas apps le cuenta (solo las que eligió el negocio, como
     dice Apps) y, a quien puede verlos, los ajustes de Ventas / TPV, Caja y Reservas cuando están encendidas (cómo se
     cobra, cómo se abre y se cierra la caja, si cada reserva pide teléfono); no tiene que buscarlos en cada pregunta. Toda fecha y hora que dice va en la hora del negocio, la misma que enseñan las
     pantallas, nunca en UTC: en un bar de Madrid, lo que pasó a las 16:18 lo cuenta a las 16:18, no a las 15:18. Todo
     importe que dice va en la moneda y con los decimales que enseñan las pantallas: lo que la ficha de un cliente dice
     «3,60 €» lo cuenta como 3,60 €, nunca como 360,00 €. Una opción de una lista cerrada la dice con el nombre
     que le dan las pantallas en su idioma, nunca con su código: de una clienta recién dada de alta dice que ha quedado en
     la etapa «Contacto» y con origen «En el local», no «lead» ni «walk_in».
Entra: lo que escribe la persona; la conversación entera viaja con cada pregunta (BASE-F102).
Sale: la pregunta a erplora.com, que la responde y la cuenta en los mensajes del mes (BASE-F104).
Si falla: sin conexión, con el servicio caído, sin plan o sin mensajes: BASE-F106 y BASE-F104. Si la documentación no
se puede consultar en ese momento, el asistente lo dice y no contesta de memoria. «Detener» no deshace una acción que
ya se había hecho. Si la voz de ERPlora no puede leer la respuesta en ese momento, la lee la del dispositivo; si
tampoco hay, bajo la respuesta dice «No se ha podido leer la respuesta en voz alta. Inténtalo de nuevo.».
Implicados: BASE-F24, BASE-F102, BASE-F104, BASE-F106

### BASE-F94 Adjuntar un archivo o dictar por voz
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Asistente
Pasos:
  1. Para adjuntar, pulsa «Adjuntar archivo» y elige uno o varios: imágenes, PDF, Word, Excel, texto o CSV, o la
     copia de un negocio (un .blueprint.zip, la misma que admite Ajustes · Datos y copias › Importar, BASE-F30). Cada
     uno sale sobre el cuadro con su nombre y su × «Quitar adjunto».
  2. Se envían con el siguiente mensaje, con texto o sin él, y en la burbuja de la persona quedan con su nombre.
     Viajan con la conversación mientras la página sigue abierta; al recargarla, la conversación solo recuerda cómo
     se llamaban.
  3. La copia de un negocio no la lee el asistente: si la persona le pide cargarla, el asistente la carga con su
     tarjeta, como Importar (BASE-F31, BASE-F97). Cualquier adjunto, también una foto o un PDF, lo guarda en Archivos
     si se le pide: lo sube a la carpeta con su tarjeta, que lo dice por su nombre, y en la carpeta queda el mismo
     archivo, como con «Subir archivo» (BASE-F73). Si la página se recargó antes de decir «sí», no carga ni guarda
     nada y pide adjuntarlo otra vez.
  4. Para dictar, pulsa «Dictar por voz» (solo sale si el dispositivo puede grabar). El navegador (en la app
     instalada, el dispositivo) pide permiso para el micrófono; mientras lo pide, otra pulsación no abre una segunda
     grabación. Mientras graba, el botón se pone rojo y se llama «Detener la grabación»; a los dos minutos para solo.
  5. Al parar sale «Transcribiendo…» y el texto cae en el cuadro, detrás de lo que hubiera escrito. **No se envía
     solo**: la persona lo revisa y pulsa «Enviar», y lo que pida pasa por su tarjeta como cualquier otra petición
     (BASE-F97).
Entra: los archivos (8 MB cada uno; la copia de un negocio, 20 MB como en Importar; y 20 MB entre todos los de una
pregunta) o la grabación.
Sale: el archivo viaja con la pregunta a erplora.com, que lo lee; la copia de un negocio se queda en el negocio:
erplora.com solo recibe su nombre. Lo que se carga o se guarda en Archivos es el archivo que adjuntó la persona, tal
cual. La grabación pasa por el negocio a la transcripción de erplora.com. El navegador
nunca habla directamente con erplora.com.
Si falla: en una línea sobre el cuadro, y el archivo no se adjunta: «menu.pdf es demasiado grande: 8 MB como mucho
por archivo.», «No se pudo leer el fichero: el fichero pasa de 20 MB.» (la copia de un negocio, como Importar), «Los
archivos de una pregunta suman 20 MB como mucho.», «menu.rar no se puede adjuntar: imágenes, PDF, Word, Excel, texto
o CSV.» o «No se ha podido leer menu.pdf.». Un archivo que ya no está en la conversación no se carga ni se guarda: «No hay ningún
archivo «copia.blueprint.zip» adjunto en esta conversación: vuelve a adjuntarlo.». Con el micrófono denegado, «El acceso al
micrófono está denegado. Permítelo en tu navegador para dictar.» y, en la app instalada (Android o Windows), donde
no hay navegador, «El acceso al micrófono está denegado. Permítelo en los ajustes del dispositivo para dictar.»; una
grabación demasiado larga, «La grabación es demasiado larga: dicta un mensaje más corto.»; sin voz, «No se ha oído
nada. Inténtalo de nuevo más cerca del micrófono.»; y si no se puede transcribir, «No se ha podido transcribir el
audio. Inténtalo de nuevo.».
Implicados: BASE-F73, BASE-F93, BASE-F97

### BASE-F95 Leer la respuesta: texto, listas, tablas y enlaces
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
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Tarjeta de confirmación del asistente
Pasos:
  1. La persona le pide algo que cambia datos («crea el servicio Corte a 15 € de 30 minutos»). Lo que la acción
     necesita y la persona no ha dicho, el asistente lo busca con sus herramientas; si ninguna lo da, se lo pregunta
     en una sola pregunta corta y nunca se lo inventa («¿Con qué impuesto lo vendes?»), y si la petición vale para
     varios registros, le pregunta cuál. Nunca pregunta en su texto si sigue adelante: eso lo pregunta la tarjeta.
  2. Antes de hacerlo sale, encima de todo, «¿Ejecutar esta acción?» con la acción, la app y sus primeros datos en una
     línea, por ejemplo «Crear en Servicios: Corte · Precio: 15,00 € · Duración (minutos): 30». El primero, lo que la
     acción toca (su registro o su nombre), sale solo por su valor cuando se entiende solo (un nombre, un registro, una
     fecha o unos registros por su nombre); cada dato detrás, y una cifra, un importe, un sí o un no o un valor de una
     lista cerrada en primer lugar, lleva delante el nombre de su dato, el mismo que en su pantalla, porque suelto no
     dice qué es: «Cambiar en Servicios: Mechas · Precio mínimo: 65,00 €», nunca «Mechas · 65,00 €», que se lee igual
     que su precio; «Cambiar en Mi perfil: Tamaño de la interfaz: 110%» y «Cambiar en Control horario: Radio permitido
     (m): 50 m», nunca «110%» ni «50 m» sueltos, que no dicen qué cambia; «Crear en
     Ventas / TPV: Varios · Categoría fiscal: Producto — general · 21 % · Posición: 0»; «Abrir en Mesas: Mesa: 4 · Comensales:
     3». Un importe, todo dato que su app declara como
     dinero, sale en la moneda del negocio (nunca en céntimos), también dentro de un dato que agrupa otros, y el
     asistente lo entiende igual aunque la app cambie cómo lo explica: «a 15 €» sale «15,00 €», nunca «1500». Si la
     acción nombra su propia moneda, sale en ella y con sus decimales, como en Stripe o Square: un pago en dólares dice
     «15,00 $», y en yenes, sin decimales; una moneda que no existe no se inventa: si la acción ya no la acepta en sus
     datos, no sale tarjeta (ver «Si falla»); si no, el importe sale tal como se escribió y la acción la rechaza al
     ejecutarse. Si la acción se hace sobre algo que tiene su propia moneda, sale en
     la de eso: añadir una línea a un carrito en dólares dice «12,50 $», y poner un precio en una tarifa en yenes,
     «1.500 ¥»; si eso no se puede leer (no existe o quien pregunta no puede verlo), el importe sale tal como se
     escribió y lo decide la acción. Todos los importes de una tarjeta se escriben igual, arriba o dentro de un dato
     que agrupa otros: «1,50 $» en los dos, nunca «1,50 US$» al lado. Uno de «Lo que va a pasar» que su app da en otra moneda sale en la
     suya: rectificar una factura emitida en euros dice «Total: -121,00 €» aunque el negocio cobre ya en złoty, y el asistente lo dice en
     la misma moneda en su respuesta. Una diferencia sale con su signo como en la pantalla de su app, para ver de un
     vistazo si sobra o falta (el cierre de caja dice «Diferencia: +137,90 €» si sobra, «-4,90 €» si falta y sin signo si cuadra); un sí o un no, como «Sí» o «No», con el nombre de su dato delante, también en la línea de una acción normal,
     porque solo no dice qué cambia («Exigir fondo de apertura: Sí · Exigir recuento al cierre: Sí», nunca «Sí · Sí»);
     una lista que su app (el servidor) nombra, por sus elementos uno tras otro («Impresoras: Caja, Cocina»; con más
     de cuatro, los tres primeros y cuántos más: «Caja, Cocina, Barra y 2 más»; si un elemento lleva coma, como una
     fecha, separados por punto y coma: «2 nov 2026, 10:00; 9 nov 2026, 10:00»); los permisos que se conceden a una
     automatización, por la acción de cada uno como la nombra su Historial («Permisos: Crear una tarea, Crear un
     cliente»); una plantilla del catálogo, por su nombre y su idioma, como en Importar («Plantilla: Restaurante
     (español)»), nunca por su código, y las apps que carga, por su nombre («Apps que se cargan: Ventas / TPV,
     Facturación»), también cuando no se elige ninguna y carga todas las suyas («Control horario, Caja, Menús y combos
     y 17 más»); las filas de un fichero que se importa (productos, categorías o clientes), por el nombre de cada una,
     como lo guarda la importación («Filas del fichero: Cucharas, Guisos»; una fila sin nombre cuenta entre los «más»,
     nunca por otra de sus celdas) y, en Inventario, las categorías fiscales que llevan, una vez cada una, por su nombre y su tipo
     de hoy («Categoría fiscal: Restauración — comida · 10 %»); las filas de un alta de golpe que dicta la persona,
     igual, por el nombre de cada una: cada persona de Personal por su nombre y apellidos («Crear en Personal:
     Carla Ruiz, Diego Martín, Elena Sanz»; una sin nombre o sin apellidos cuenta entre los «más») y cada servicio por
     su nombre («Servicios: Corte, Tinte»), con las categorías y las categorías fiscales que llevan aparte, una vez cada
     una;
     una lista de líneas que solo llevan
     su registro, como los servicios de una cita, igual, por el nombre de cada uno («Servicios: Corte de pelo, Tinte»;
     uno que no se puede nombrar cuenta entre los «más»), también cuando el asistente manda un servicio por su nombre
     porque no sabe cuál es («Servicios: Tinte»; si manda el servicio y además un nombre, dice el servicio que se
     reserva); una lista de lo que escribió la persona, como las opciones de un campo de selección, por cada una tal
     cual («Opciones: Terraza, Dentro»); una lista de líneas que llevan en palabras su registro, el nombre que dijo la
     persona, lo que escribió o una hora o una fecha y, al lado, solo cifras —una recepción de mercancía (producto y
     cantidad), los servicios de un bono (servicio y sesiones), los platos de una comanda hecha a mano, los tramos de
     un horario o las líneas de una factura hecha a mano—, por sus palabras seguidas de sus cifras, la cantidad como se
     escribe en el idioma de la persona, un importe como dinero y el IVA escrito a mano como porcentaje («Productos:
     Vino tinto · 6; Cerveza · 2,5»; «Servicios incluidos: Corte · 5, Tinte · 3»; «Platos: Espresso · 2, Café con
     leche · 1»; «Tramos horarios: 9:00 · 14:00»; «Líneas: Menús de cumpleaños privado · 10 % · 1 · 681,82 €»; si una
     línea no se puede nombrar, la lista dice cuántas lleva: se leería como una cifra suelta); los campos
     personalizados de una ficha, cada uno por su nombre y su valor como lo enseña la ficha: un sí o un no en el idioma
     de la persona, una fecha como se escribe en él y un campo que se vacía, con una raya («Campos personalizados:
     Preferencia de mesa · Terraza, VIP · Sí»; «VIP · —»); los días especiales que se cargan de golpe, por su fecha y
     su nombre y, si ese día abre, sus horas («1 ene 2027 · Año Nuevo, 6 ene 2027 · Epifanía del Señor, 26 mar 2027 ·
     Viernes Santo y 7 más»); una línea con dos registros que la tarjeta nombra, por los dos (el producto y quien lo
     atiende en una venta, «Champú · Bea Ruiz · 2»); y cualquier otra, como una línea con un registro que la tarjeta
     no puede nombrar, una con un sí o un no o una lista dentro o una lista de códigos, por cuántos elementos lleva;
     un cobro,
     por su total y cómo se paga, como el botón de la hoja **Cobro**: el total, tal como lo calcula el TPV para quien
     pregunta («Total: 12,50 €»), y cada forma de pago con lo que paga («Pagos: Efectivo · 12,50 €»; la que va sin
     importe paga lo que dejan las otras y, si no se dice ninguna, todo en efectivo, como cobra la acción), nunca
     «1 elemento» ni la versión de la cuenta, que solo usa la hoja **Cobro**; unos pagos que no suman el total salen
     tal como se dijeron, junto al total, y si el total no se puede calcular (la cuenta ya no está o quien pregunta no
     puede verla) no se inventa: en los dos casos la acción lo rechaza al ejecutarse; y un dato
     que agrupa otros, como la plantilla de un WhatsApp, por sus
     valores, sin el nombre de cada uno («Plantilla: cita_recordatorio · es · Ana, 10:00»; del recuento de una caja
     quedan los billetes y monedas contados: «50: 2»). Una fecha y una hora salen como se escriben en el idioma
     de la persona y a la hora del negocio («2 nov 2026, 10:00»; un día solo, «2 nov 2026»; una hora sola,
     «21:30»); un valor de una lista cerrada, con el nombre que le da su app («Mostrador», no el valor interno),
     también el de un dato que su app no llama como el campo que lo nombra («Rectificativa: resto de causas (R4)», no «R4»); y
     un registro, por su nombre cuando su app deja leerlo a quien pregunta («Persona: Eva Gil»): si no, la tarjeta
     no lo pone, nunca por su código. Una categoría fiscal lleva además el tipo que cobra hoy en el país y la región
     del negocio, como la pantalla **Secciones** («Categoría fiscal: Producto — general · 21 %»); sin una regla en
     vigor, solo su nombre, y también solo su nombre en una regla de Impuestos, que lleva su propio país y su propio
     tipo. El alta de un producto la dice en su línea, tras el nombre y el precio («Crear en Inventario: Cuchara · Precio:
     2,50 € · Categoría fiscal: Producto — general · 21 %»). Un registro que se dijo con palabras se busca como lo buscará la acción, también
     dentro de otro (un plato dentro de su menú), y sale el que encuentra («Plato: Postres caseros» cuando se dijo
     «postres»); si esas palabras valen para varios o para ninguno, salen tal como se dijeron; y si la acción no las usa
     porque llega el identificador de su registro, ni se leen ni salen. Tampoco pone la clave con que su app evita hacer dos veces lo mismo si se
     reintenta (cobrar, enviar un WhatsApp, imprimir): nadie puede juzgarla, y la acción la recibe igual al
     ejecutarse. Todo sale en el idioma de la persona, también el nombre de cada dato
     cuando la tarjeta lo pone en su línea (BASE-F98): el mismo con que lo llama su app, nunca un nombre
     técnico. Una acción de la propia plataforma se nombra por la pantalla donde se hace, por ejemplo «Cambiar en
     Ajustes» o «Borrar en Archivos». Cada acción sale con su propio verbo, nunca con uno genérico: rectificar una
     factura dice «Rectificar en Facturación». Dos acciones que se llaman igual en dos apps dicen cada una lo que
     hace: vaciar un carrito dice «Vaciar en Carrito y pago», quitar una de sus líneas «Quitar en Carrito y pago» y
     quitar la ruta de un producto en la cocina «Quitar en Cocina»; un arqueo dice «Registrar arqueo en Caja» y una
     entrada o salida de efectivo «Registrar movimiento en Caja», como sus pantallas, nunca «Añadir»; y la prueba en
     vivo de VeriFactu, como sus botones, «Probar la conexión en VeriFactu» y «Crear factura de prueba en VeriFactu»,
     nunca «Ejecutar» ni «Crear». Una acción que no lleva ningún dato que enseñar dice solo su acción y su app, acabada
     en punto y sin dos puntos vacíos detrás: «Probar la conexión en VeriFactu.».
  3. «Ejecutar» lo hace con la sesión de quien preguntó, con los mismos permisos y las mismas comprobaciones que el
     botón de su pantalla. «Cancelar» o Esc no hacen nada: el asistente sabe que la persona dijo que no y dice que no
     se hizo porque lo canceló, sin pedirle que lo confirme, porque esa tarjeta ya está cerrada. Tras «Ejecutar», el
     asistente sabe que la persona lo confirmó: lo da por hecho tal como se pidió, dice lo que quedó hecho y no propone
     deshacerlo salvo que se lo pidan.
  4. Lo que solo lee (ver las ventas, buscar un cliente) no pide tarjeta; cada acción que cambia algo pide la suya.
  5. Bajo la respuesta queda el recibo de cada acción del turno que se le propuso a la persona, con la acción nombrada
     como en su tarjeta: «Hecho: Crear en Servicios», o «No se hizo, cancelado: …», «No se hizo, falló: …» y «No se
     hizo, sin permiso: …». El de un fallo dice el motivo en una frase: si su app la rechaza, la misma que daría su
     pantalla («No se hizo, falló: Imprimir en Ventas / TPV. Ninguna impresora de tiques recibe el papel de esta
     venta: abre la venta para imprimirlo en este dispositivo.»); si lo que no valía eran los datos que envió el
     asistente (un fichero adjunto que pesa más de lo que admite la acción), cuáles, con el nombre que les da la
     tarjeta («El asistente envió datos que no valen: Archivo.»). Lo que el Hub rechaza antes de enseñar la tarjeta
     (datos que no valen, un cambio sin nada que cambiar, un registro que no encuentra) no deja recibo, como en los
     asistentes de Shopify o Intercom: a la persona no se le preguntó nada, y el asistente oye el motivo y lo corrige o
     se lo cuenta. Así, «Quita la paella de la carta» deja solo «Hecho: Cambiar en Inventario», aunque antes el
     asistente probara otra acción con datos que no valían. Si la persona cambia de idioma, los recibos de antes salen
     enteros en el nuevo, también el nombre de la app; el motivo, que se dijo en el otro idioma, ya no sale.
Entra: la acción, sus datos y su riesgo, tal como los declara su app; la moneda del negocio, la del registro sobre el
que se hace (leída como la persona) y, en «Lo que va a pasar», la que dé su app; la zona horaria del negocio; y,
si su app la declara, la comprobación que hace antes de la tarjeta, como la persona: si rechaza los datos (dar de alta a
alguien con un rol que el negocio no tiene, STAFF-F01), no sale tarjeta y el asistente lo cuenta como su error.
Sale: si se acepta, la acción hecha en su app, con el mismo evento que si se hubiera pulsado su botón.
Si falla: una acción que su app rechaza vuelve al asistente como error y él lo cuenta; el recibo dice «No se hizo,
falló: …». Unos datos que la acción no acepta (un país o una moneda que no existe, un valor fuera de su lista) no
llegan a la tarjeta ni dejan recibo: vuelven al asistente, que los corrige, y la persona confirma una sola vez. Tampoco llega un
cambio que solo nombra su registro, sin ningún dato que cambiar (nunca «Cambiar en Clientes: Lucía QA» a secas): el
asistente oye que no hay nada que cambiar y sigue con lo que se le pidió, con la acción que lo hace, o pregunta qué
quiere cambiar; si el registro no está, oye eso. «Ejecutar» vale solo
para lo que enseña la tarjeta: si antes de pulsarlo cambia —la acción encuentra por su nombre otro registro, porque
alguien ha creado uno que encaja mejor con lo dicho («Mesa» cuando la tarjeta decía «Mesa 4»), el registro cambia de
nombre, el tipo de su categoría fiscal cambia o lo que dice «Lo que va a pasar» ya no es lo mismo—, no se hace nada y sale la tarjeta nueva, para
confirmarla otra vez; si lo que encontró ya no está, no sale tarjeta y el asistente lo cuenta como su error.
«Cancelar» y lo escrito que no coincide valen igual aunque haya cambiado. Si se recarga la página con la tarjeta
abierta no se hace nada, y la respuesta acaba en «La respuesta se cortó.» con «Reintentar».
Implicados: BASE-F98, BASE-F99, BASE-F101

### BASE-F98 Acciones peligrosas: escribir para confirmar, o no desde el chat
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
hace nada: nada se confirma a ciegas, y el asistente cuenta por qué. Si el registro no está, no queda recibo, porque a
la persona no se le preguntó nada (BASE-F97); si no puede verlo, el recibo dice «No se hizo, sin permiso: …». Si deja
de poderse leer después de pulsar «Ejecutar», el recibo dice «No se hizo, falló: …».
Implicados: BASE-F35, BASE-F37, BASE-F97

### BASE-F99 Comprobar lo que dice el asistente contra lo que de verdad hizo
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
     respuesta muestra un identificador que el asistente no ha leído de verdad. No te fíes de él.». Con una dirección
     web, lo mismo: el asistente solo da las que ha consultado en el turno (una búsqueda en la web, un tipo de cambio o
     lo que devolvió una herramienta), y si escribe otra que la persona no escribió: «Esta respuesta muestra una
     dirección web que el asistente no ha consultado de verdad. No te fíes de ella.». La misma página escrita de otra
     forma (con o sin «https://», «www.» o la barra del final) cuenta como consultada.
  4. Si señala una pantalla que este negocio no tiene: «Esta respuesta señala una pantalla que no existe aquí.», y
     sin «Ir a …» (BASE-F96).
  5. Los avisos llevan su icono de alerta, no los escribe el asistente y se quedan con el mensaje, también al
     recargar. Una respuesta limpia no lleva ninguno.
  6. Los recibos de BASE-F97 dicen qué se hizo de verdad, acción por acción.
Entra: lo que se hizo en el turno, con su resultado, lo que devolvieron sus consultas y las direcciones web que
consultaron las herramientas de erplora.com.
Sale: los avisos y los recibos, guardados con la conversación.
Si falla: «Hecho» quiere decir que la acción de su app acabó sin error: si una app responde bien sin haber cambiado
nada, es esa acción la que tiene que decirlo. Si el turno acaba en error, la burbuja lleva su fallo (BASE-F106), los
avisos de lo que llegó a decir y los recibos de lo que sí se hizo.
Implicados: BASE-F96, BASE-F97, BASE-F106

### BASE-F100 Lo que el asistente puede hacer según quién pregunta: permisos y PIN de un responsable
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Asistente
Pasos:
  1. El asistente trabaja con la sesión de quien está delante: ve y hace lo que esa persona vería y haría con sus
     botones, en las apps encendidas del negocio, y nada más. Una acción para la que no tiene permiso no se le ofrece
     al asistente, que así se lo dice; la que su app deja aprobar a un responsable sí, igual que su botón en la
     pantalla, salvo que el rol propio de la persona le diga «No» (BASE-F84): esa no se le ofrece ni se le encuentra, y
     ningún PIN la deja pasar. El asistente sabe con qué rol habla (propietario, administrador, encargado o empleado,
     dicho en el idioma de la conversación, o el propio que el negocio le dio, por su nombre, BASE-F130) y que sus
     herramientas son las de ese rol: si le piden algo que ninguna hace, no busca otro camino ni cuenta el estado de otra
     cosa, sino que dice en una frase que no lo tiene disponible aquí, porque su rol no puede o porque esa app no está
     encendida, y quién puede (al empleado, un encargado o el propietario; al encargado, el propietario o un
     administrador) o en qué pantalla se hace.
  2. Esa acción sale con su tarjeta, como cualquier otra, y el asistente avisa antes de que la tarjeta pedirá la
     aprobación de un responsable. Al pulsar «Ejecutar» se abre «Hace falta una aprobación», la misma de la pantalla:
     un responsable toca su cara y teclea su PIN, o pasa su placa, y la acción se hace una vez, con quien la pidió
     como autor. Queda anotada en **Empleados › Aprobaciones**.
  3. Si nadie la aprueba («Cancelar»), no se hace: el recibo dice «No se hizo, cancelado: …» y el asistente lo sabe.
  4. Si aun así intenta una acción sin permiso que nadie puede aprobar, no se hace: el recibo dice «No se hizo, sin
     permiso: …» y el asistente explica que no puede.
  5. Lo que el asistente cuenta (listas, cifras) es lo que esa persona puede leer.
Entra: la sesión de quien pregunta, que firma cada acción; para lo que aprueba un responsable, su PIN o su placa.
Sale: la acción hecha con esa persona como autora. La aprobación vale para esa acción de esa conversación, una sola
vez y durante dos minutos, y se gasta junto con la acción (BASE-F84). La que un responsable podría aprobar y la persona
puede hacer por su rol queda también anotada, a su nombre (BASE-F85).
Si falla: si el permiso se pierde entre ofrecer la acción y hacerla, su app la rechaza y el recibo lo dice. Una
aprobación ya usada o caducada no deja pasar la acción: el recibo dice «No se hizo, falló: …» y el asistente lo
cuenta.
Implicados: BASE-F13, BASE-F84, BASE-F85, BASE-F97, BASE-F130

### BASE-F101 Pedirle varias cosas seguidas
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Asistente
Pasos:
  1. La persona pide una cadena («crea la categoría Bebidas y el producto Caña a 2,50 €»).
  2. El asistente la resuelve por rondas: lee lo que necesita sin preguntar (varias cosas en la misma ronda, si le
     hacen falta), pide una acción, se hace y sigue. Todo lo que dice va a la misma burbuja, y lo de cada ronda en su
     propio párrafo: nunca pegado a lo de la anterior.
  3. Cada acción que cambia algo pide su propia tarjeta (BASE-F97), una detrás de otra, también las que pide en la
     misma ronda: aceptar o cancelar la primera no responde por las siguientes. Si detrás esperan más, la tarjeta lleva
     «Cancelar todo», que cancela esta y las que faltan.
  4. Si cancela una, el asistente lo sabe y decide cómo seguir. Lo ya hecho se queda hecho.
  5. Una petición admite como mucho veinte rondas, cada una con todo lo que el asistente pide de una vez: es un freno
     contra los bucles, no un cupo, y una lectura y un cambio por cada día de la semana caben de sobra aunque los pida
     de uno en uno. En la vigésima el asistente ya no puede hacer
     nada más y contesta con lo que ha hecho y lo que falta, para pedirlo en otro mensaje; si aun así pide una acción,
     no se hace ni sale su tarjeta, y se le dice que conteste. Si sigue intentándolo, «He parado: esto necesitaba
     demasiados pasos. Pídelo por partes.».
Entra: la petición; el resultado de cada acción, que vuelve al asistente.
Sale: tantas acciones como tarjetas aceptadas, cada una en su app y con su recibo.
Si falla: si una acción falla a mitad, el asistente lo recibe y lo cuenta; las anteriores no se deshacen. Con la red
cortada a mitad, BASE-F106.
Implicados: BASE-F97, BASE-F106

### BASE-F102 La conversación: qué se guarda, dónde y cuándo se borra
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
     estuviera llegando. Al cambiar de usuario, con PIN o con placa, la de quien se fue se borra con lo que hubiera
     escrito sin enviar y sus adjuntos. En los dos casos, quien entra después encuentra el panel cerrado y vacío.
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
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Asistente
Pasos:
  1. En el Inicio, mientras falta algo, «Termina de configurar tu negocio» lleva «Pedírselo al asistente», sus
     destellos. Abre el
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
  5. El propietario ve, en el navegador, «Mejorar plan», que abre en otra pestaña la página del plan en
     erplora.com, ya dentro con su cuenta (BASE-F11); en la app instalada desde la tienda no sale. Quien no es el
     propietario ve «Pídele al propietario del negocio que mejore el plan.». No hay paquetes de mensajes: se amplía
     mejorando de plan.
  6. Con un plan sin asistente, el pie dice «Tu plan no incluye el asistente.», con «Mejorar plan» para el
     propietario; el panel se abre igual.
  7. Al preguntarle al asistente cuántos mensajes le quedan o cuántos lleva este mes («¿cuántos mensajes me quedan
     este mes?»), contesta con las mismas cifras que «Uso y plan» (BASE-F40) y con el día en que se renuevan. Solo
     las lee al preguntarlo; si no se pueden leer, lo dice, sin inventar un número.
Entra: los mensajes usados, el límite y el día en que se renuevan, de erplora.com.
Sale: la página del plan de erplora.com, en otra pestaña. El negocio no lleva su propia cuenta de mensajes.
Si falla: si no se puede leer el plan, no se enseña nada y se puede preguntar igual: lo que diga erplora.com al
responder es lo que vale. Si el pase de «Mejorar plan» no llega, se abre la dirección de siempre, que pide entrar (BASE-F11).
Implicados: BASE-F11, BASE-F40, BASE-F106

### BASE-F105 Informar de una respuesta mala
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Asistente
Pasos:
  1. Bajo cada respuesta terminada sale «Denunciar un problema»; no en la que aún se escribe ni bajo un fallo sin
     respuesta, que no es del asistente.
  2. Se abre «Denunciar esta respuesta»: «Si esta respuesta del asistente te parece incorrecta o dañina, envíanosla y
     la revisaremos.», con «¿Qué le pasa?» («Es incorrecta», ya marcada; «Es dañina u ofensiva», «No hace lo que
     pedí» u «Otra cosa») y «Comentario (opcional)».
  3. «Denunciar» la envía con la pregunta que la provocó y con si su turno trajo páginas de la web: el Hub lo dice al
     cerrar cada ronda del turno (también la que se para en la tarjeta de un cambio o tras demasiados pasos, que no
     trae ninguna), y el chat lo guarda con la respuesta; basta con que una ronda las trajera. «Cancelar» no manda nada.
  4. Sale «Gracias, hemos recibido tu denuncia.» y se cierra.
Entra: la respuesta, la pregunta, el motivo, el comentario y si su turno trajo páginas de la web (si el chat no lo
sabe, una respuesta de antes de la marca o una ronda que se paró escribiendo, no lo dice).
Sale: la denuncia, para que el equipo de erplora.com la revise. Cualquier persona puede denunciar. Con la búsqueda
en la web encendida, si la respuesta trajo páginas de la web o el chat no sabe de dónde vino, al equipo le llega todo
menos la respuesta: los términos del buscador no dejan guardar sus resultados.
Si falla: «No se pudo enviar la denuncia. Inténtalo de nuevo.», y la ventana sigue abierta con lo elegido y lo
escrito.
Implicados: ASSISTANT-F23

### BASE-F106 El asistente sin conexión, con el servicio caído o sin plan
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
Estado: hecho
Actor: el equipo de QA de ERPlora
Pantalla: todas las de la plataforma del hub
Operaciones: ninguna
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
Implicados: ACCOUNTS-F38, BASE-F40

### BASE-F109 Borrar un negocio eliminado pasados sus 90 días
Estado: hecho
Actor: nadie: lo hace el Hub solo, sin que nadie pulse nada
Pantalla: Ninguna; la dirección del negocio sigue diciendo «Este hub ya no está disponible.»
Pasos:
  1. Un negocio eliminado en erplora.com (HUBS-F18, HUBS-F20) cumple 90 días. Hasta ese momento su base de datos se
     queda intacta y se puede recuperar.
  2. El Hub mira si guarda documentos: ventas, facturas, registros de VeriFactu, cobros, movimientos de caja, pedidos
     de la tienda o compras de un cliente, en cualquier estado y aunque la app esté apagada. Si guarda alguno y aún no
     se pueden archivar (no hay archivo fiscal, o un registro de VeriFactu espera la respuesta de la AEAT), se detiene:
     el negocio sigue eliminado, con su base de datos, y lo vuelve a mirar al día siguiente.
  3. Hace la copia final de sus datos, que se guarda 90 días en el almacén de copias; si ya tiene una de menos de un
     día (un intento anterior que no llegó a borrar), no hace otra. Mientras se hace, el negocio aún se puede
     recuperar y erplora.com sigue viendo sus copias.
  4. Al terminar vuelve a mirar si guarda documentos, también los que entraran durante la copia, y si guarda alguno
     los escribe en el archivo fiscal, donde se guardan 6 años sin que nadie los pueda borrar: cada tabla de esos
     documentos tal como está guardada, sin rehacer nada; el PDF de cada factura tal como se entregó al cliente, en su
     idioma o en el del negocio y con el QR de VeriFactu si tiene su registro, uno por factura; y al final una
     lista que cuenta las filas y los PDF y lleva la huella de cada fichero, que solo se escribe cuando todos se han
     vuelto a leer iguales. Un archivo hecho antes de la copia final no vale: se vuelve a hacer después de ella.
  5. Borra la base de datos de ese negocio, y solo esa. Desde aquí ya no vuelve.
  6. Borra sus ficheros del almacén, los de Archivos y los que guardan sus apps, y solo los suyos.
  7. Queda solo una marca, sin nombre ni datos, para que su dirección siga diciendo «Este hub ya no está disponible.»;
     sus personas y sus sesiones se van con ella.
Entra: el negocio eliminado y sus 90 días cumplidos. Nunca una demo, que se borra a su manera al caducar, el negocio
de la plataforma ni uno que se está moviendo de servidor.
Sale: la copia final y, con documentos, su archivo fiscal (en la fila, `fiscal_archived_at`); y la base de datos y los
ficheros borrados, con el evento `base.hub.purged`; desde ahí erplora.com ya no lista sus copias. Si sus documentos no
se pueden archivar, no se borra nada: la base de datos y los ficheros se guardan y la fila dice por qué,
`fiscal_archive_missing: <apps>` donde no hay archivo fiscal, `fiscal_archive_waiting: verifactu` mientras un registro
espera a la AEAT y `fiscal_archive_failed` si el archivo no se pudo escribir entero.
Si falla: una copia que falla no borra nada, y sin almacén de copias tampoco; una copia o un borrado que falla se
reintenta (1 min, 5 min, 15 min y luego cada hora) con el error anotado en la fila, sin hacer otra copia si ya la había
de menos de un día. Si el almacén no borra sus ficheros, el negocio sigue borrándose, sin marca, con
`files_purge_failed` en la fila, y se reintenta igual. Si una app no se puede leer, la base de datos se queda. Una fila
que no nombra la base de datos propia del negocio no borra nada (`invalid_database_name`). Un negocio recuperado
durante la copia sigue abierto con su base de datos; ya borrándose, erplora.com recibe `hub_purged`. Si el Hub se apaga
a media copia, el siguiente la retoma. Si se apaga a medio archivo fiscal, el siguiente intento de esa baja aprovecha
los PDF que ya subió y no los vuelve a hacer. Si el archivo fiscal no se puede escribir entero, o un fichero no se lee
igual que se escribió, no se da por hecho y no se borra nada: la fila dice `fiscal_archive_failed` con el motivo y se
reintenta al día siguiente en otra carpeta del archivo (lo ya subido se queda, porque nadie lo puede borrar, y sin su
lista final no cuenta), con una copia final nueva si la que había tiene más de un día.
Implicados: HUBS-F18, HUBS-F19, HUBS-F20, PUBLIC-F34 (el mismo borrado de ficheros, al retirar una demo), INVOICE-F18
(el A4 de cada factura que va al archivo)

### BASE-F110 Abrir la web del negocio por su dominio propio
Estado: hecho (la dirección y lo que sirve; conectar el dominio es HUBS-F17 de erplora.com, que lo enseña en el panel)
Actor: cualquiera, sin cuenta
Pantalla: La página pública del negocio (WEBSITE-F10), en su dominio
Operaciones: ninguna
Pasos:
  1. Alguien abre el dominio del negocio (por ejemplo, www.minegocio.es) en un móvil, una tableta o un ordenador.
  2. Se ve la página publicada del negocio, con sus fotos, en el idioma del navegador.
  3. **Entrar** lleva a la dirección del negocio en erplora.com: la app y la entrada siguen solo allí.
Entra: un dominio que erplora.com ha dicho que es de ese negocio.
Sale: la web pública del negocio y sus imágenes, sin cookies; nada más: ni la app, ni la API, ni el acceso. Con la sesión
del negocio abierta en ese navegador se ve lo mismo, porque la sesión no llega a otro dominio. La página le dice al
buscador que su dirección principal es el dominio, también cuando se abre por la dirección de erplora.com, que no
redirige (WEBSITE-F10).
Si falla: un dominio que nadie ha conectado no abre nada. Si el negocio lo quita, se da de baja o está suspendido, o no
tiene una página publicada, el dominio dice que no hay nada ahí. Un negocio que se está preparando o mudando pide volver
en un momento.
Implicados: HUBS-F17, WEBSITE-F10

### BASE-F111 Esperar a la base de datos cuando se corta un momento
Estado: hecho
Actor: cualquier persona del negocio en el Hub, en la web o en la app, y cualquier programa conectado por la API
Pantalla: cualquiera del Hub, Página «Volvemos enseguida»
Operaciones: ninguna
Pasos:
  1. La persona abre una pantalla o guarda algo mientras la base de datos se corta unos segundos: un reinicio, un
     mantenimiento de AWS o el cambio de versión.
  2. Lo que estaba leyendo espera y se vuelve a pedir solo, hasta 20 segundos en total. Si la base vuelve antes, la
     pantalla llega como siempre: la persona solo nota que ha tardado.
  3. Lo que estaba guardando espera igual cuando consta que no se aplicó nada: no llegó a empezar (abrir la base del
     negocio o comprobar quién es la persona), o es un cambio que solo toca la base de datos y todavía no se había
     confirmado. Esto vale para Demo y para los comandos locales de las demás apps. Se guarda una sola vez y en su
     negocio, y el aviso a las demás pantallas sale después de confirmarse.
  4. Mientras espera no ocupa ninguna de las transacciones a la vez que da el plan del negocio: las demás personas del
     negocio siguen trabajando.
  5. Si se acaba el tiempo, quien abre la dirección del negocio en el navegador ve «Volvemos enseguida» con «ERPlora
     vuelve en un momento: inténtalo de nuevo en unos segundos.», en una página que se recarga sola. Dentro de la app,
     lo que no se pudo cargar o guardar lo dice en su sitio, como cualquier otro error.
Entra: nada: la persona no hace nada distinto.
Sale: la misma respuesta de siempre, con unos segundos de retraso; o, pasado el tiempo, una respuesta 503 con
`Retry-After` y nunca un error del servidor. Un programa recibe el código `database_unavailable`, o
`base.hub_unavailable` si lo que no responde es la base del negocio al abrirla.
Si falla: lo que pudo aplicarse no se repite nunca a ciegas, y cada resultado dice el suyo. Un comando excluido porque
numera, cobra, genera un QR, envía a la AEAT, manda un correo o un WhatsApp, llama a un tercero o escribe fuera de su
transacción (en caché, sesiones, control o el almacén de ficheros), cortado a medias o mientras se confirmaba: la
persona lee «Se ha perdido la conexión mientras se guardaba. Comprueba si se ha guardado antes de volver a intentarlo.»
y un programa, el código `database_outcome_unknown`. Si el guardado ya se había confirmado y el corte se llevó solo la
respuesta, lee «Se ha guardado, pero la conexión se ha perdido antes de llegar la respuesta. Recarga la página en unos
segundos para verlo.» (`database_answer_lost`). Lo que no es un corte (una consulta que tarda demasiado, un fallo del
programa) sigue siendo el error de siempre. Las llamadas de erplora.com a `/internal` y `/readyz` reciben su 503 al
momento, sin esperar: erplora.com reintenta por su cuenta, y `/readyz` tiene que decir que la base no está antes de que
sus sondas se cansen.
Implicados: ACCOUNTS-F50 (su gemelo de erplora.com), todas las apps con cambios locales que se repiten, las demás páginas
de espera del Hub (un negocio que se prepara o se muda de servidor: el mismo aspecto); hub#831, hub#1051 y hub#1052

### BASE-F112 Guardar un archivo descargado dentro de la app
Estado: hecho
Actor: cualquier persona del negocio que descarga un archivo en el Hub
Pantalla: las que descargan un archivo que la pantalla ya tiene: VeriFactu › Configuración (el modelo del
otorgamiento), Ajustes · Datos y copias (Exportar), Archivos, Empleados · Aprobaciones, la documentación de la API,
Fichajes, Inventario (Productos y Categorías), Clientes, «Compartir y QR» de la web y el asistente (la exportación que
se le pide)
Pasos:
  1. La persona pulsa descargar: el modelo del otorgamiento, una exportación, un archivo, un CSV, el fichero OpenAPI o
     el QR.
  2. En un navegador, el archivo baja con su nombre a las descargas del navegador, que ya lo dicen.
  3. Dentro de la app de ERPlora (ordenador o Android 10 o posterior), el Hub le da el archivo a la app, que lo guarda
     en la carpeta Descargas, y sale «Guardado en» con la ruta del archivo (en Android, «Guardado en
     Download/carta.pdf»): dentro de la app no hay barra de descargas ni otro aviso.
  4. En el asistente, al pedirle una exportación («Sácame la carta entera en un CSV»), bajo su respuesta sale
     «Descargar» con el nombre del archivo: el mismo archivo que da el botón de exportar de esa pantalla, que baja como
     en los dos pasos anteriores. El asistente dice que lo tiene ahí, sin pegar su contenido en el chat.
Entra: el archivo que la pantalla ya tiene, con su nombre.
Sale: el archivo en Descargas y, dentro de la app, el aviso con su ruta. En el Hub no se guarda nada.
Si falla: dentro de la app el botón nunca se queda sin respuesta. Sin una carpeta de descargas que la persona pueda
abrir (Android 9 o anterior, iOS): «Esta app no puede guardar archivos en un móvil o una tablet. Abre tu negocio en un
navegador para descargarlo.»; con la app enlazada a otro negocio: «No se ha podido guardar el archivo: esta app está
vinculada a otro negocio.»; una versión de la app sin esta función: «Esta versión de la app de ERPlora no puede guardar
archivos. Actualízala para descargar.»; cualquier otro fallo (un nombre que la app rechaza, sin espacio):
«No se ha podido descargar el archivo.». En esos casos la pantalla no dice que se descargó. El archivo que dio el
asistente vive en esa pestaña: tras recargar la página, en su lugar dice «El fichero «carta.csv» ya no está aquí: pídelo
otra vez para descargarlo.». Las copias que guarda
ERPlora (Datos y copias › Copias) bajan por un enlace firmado y no pasan por aquí.
Implicados: HUB_APP-F30 (ERPlora/app), BASE-F35, BASE-F74, BASE-F85, BASE-F90, VERIFACTU-F05, ATTENDANCE-F10,
INVENTORY-F11, CUSTOMER-F09, WEBSITE-F09; hub#1041

### BASE-F113 Seguir avisando con la pantalla apagada (app de Android)
Estado: hecho
Actor: sistema
Pantalla: ninguna; en Android, el aviso fijo «ERPlora está a la escucha»
Pasos:
  1. En la app de ERPlora, una persona entra en el negocio y oye algún aviso (una comanda nueva de Cocina, una cita
     que pidió la clienta, un cliente que espera respuesta en WhatsApp), y Android no tiene negados los avisos.
  2. Después de la pregunta de los avisos, si toca (HUB_APP-F07), el Hub pide a la app que se quede a la escucha, con
     las palabras de su aviso fijo en el idioma de la persona: «ERPlora está a la escucha» y «Te avisará cuando algo
     necesite tu atención, aunque la pantalla esté apagada.», en el canal «Avisos con la pantalla apagada».
  3. Con la pantalla apagada o la app en segundo plano, los avisos siguen llegando al momento (KITCHEN-F16,
     APPOINTMENT-F28).
  4. Al cerrar la sesión, también por inactividad (BASE-F61), o cuando ya no queda nada que avisar (la app que avisaba
     se desactiva), el Hub pide a la app que deje de escuchar; al cerrar la sesión, antes de salir de la página.
Entra: los avisos que oye la persona y lo que dice Android de los avisos.
Sale: la orden a la app de quedarse a la escucha o de dejarlo. En el Hub no se guarda nada.
Si falla: con los avisos negados («Ahora no» a nuestra pregunta, o negados en Android), sin nada que avisar o sin saber
qué dice Android, la app no se queda despierta. Una app sin esta orden (la 1.1.34 y la 1.1.35) la rechaza: el Hub lo anota en la
consola, no se la vuelve a pedir en esa página y la persona no ve ningún error; los avisos llegan con la app en
pantalla. Si Android no deja empezar, igual, y se vuelve a pedir en la siguiente entrada. Mientras el Hub
no sabe aún si hay algo que avisar, no pide nada a la app: recargar la página no la para ni la vuelve a encender.
Cerrar la sesión nunca espera a la app más de 2 segundos. En un navegador no hay app a la que pedírselo.
Implicados: HUB_APP-F26 (ERPlora/app), HUB_APP-F07 (ERPlora/app), KITCHEN-F16, APPOINTMENT-F28, BASE-F61; hub#836

### BASE-F114 Devolver un negocio a un momento pasado desde el admin de Hubs
Estado: hecho (la acción y la restauración, en su sitio o en una copia aparte, y recuperar desde la copia aparte los
clientes que se perdieron, los eliminados tal como eran, los productos, los servicios con sus categorías, las citas,
las citas periódicas, los precios de tarifa, los grupos de suplementos que el negocio borró, con sus opciones, las
opciones que quitó de un grupo de suplementos que conserva, los grupos de suplementos de las categorías y de los
productos, los menús que el negocio retiró y los platos que quitó de un
menú y las elecciones de menú de los productos; crear y borrar el clúster temporal es el procedimiento «Devolver un
negocio a un momento» de ERPlora/aws)
Actor: el personal de ERPlora que administra la plataforma, cuando un negocio lo pide
Pantalla: el admin de Hubs (`hubs.erplora.com/admin`) › Hubs, acciones «Restaurar desde una copia…» y «Restaurar en una
copia aparte…»; Copias aparte, acción «Recuperar en el negocio…»; y Recuperaciones
Pasos:
  1. Un negocio pide volver a cómo estaban sus datos en un momento de los últimos días. El personal crea un clúster
     temporal restaurado a ese momento y lo da de alta en Clústeres, cerrado a hubs nuevos.
  2. En Hubs elige el negocio (o varios del mismo clúster) y la acción «Restaurar desde una copia…».
  3. La página de confirmación explica lo que va a pasar, dice debajo de cada negocio el tamaño de su base de datos y
     hasta cuánto puede estar cerrado («476,8 MB: cerrado hasta 2 minutos»; varios se restauran uno tras otro) y pide
     el clúster temporal (solo salen los cerrados a hubs nuevos) y el momento con su zona horaria
     («2026-11-09T14:30:00Z es UTC»). Pulsa **Restaurarlos**.
  4. Sale «1 hub se restaurará desde <clúster> tal como estaba el 2026-11-09 14:30 UTC: cerrado mientras se restaura,
     hasta 2 minutos. Si se rechaza, su ficha dice por qué en «último error».» (con varios, el tiempo de todos). Mientras
     dura, la lista dice en la columna del clúster de dónde viene la copia («<su clúster> ← <clúster temporal>»), y quien
     abre el negocio ve que está en mantenimiento.
  5. Cuando acaba, en ese tiempo como mucho, el sistema ha copiado la base del negocio desde el clúster temporal, ha
     guardado aparte la que tenía y ha puesto la copia en su sitio. El negocio vuelve a abrirse con sus datos de ese momento y la flecha desaparece de la
     lista.
  En una copia aparte (hub#1213), para un negocio que factura con VeriFactu en producción o cuando solo se quiere
  recuperar lo perdido sin tocar lo demás:
  6. En Hubs elige el negocio y la acción «Restaurar en una copia aparte…». La misma página pide el clúster temporal y
     el momento, y explica que el negocio sigue abierto sin cambiar nada y que la copia no es un negocio: nadie la abre y
     nada de ella se envía a Hacienda. Pulsa **Hacer las copias**.
  7. Sale «1 hub tendrá una copia aparte tal como estaba el 2026-11-09 14:30 UTC, hecha desde <clúster>: el negocio
     sigue abierto tal como está. Copias aparte la lista y dice si no se pudo hacer.». El negocio no se cierra ni un
     segundo.
  8. En Copias aparte la ve «Haciéndose» y, unos minutos después, «Hecha», con su momento y hasta cuándo se guarda
     (7 días); su ficha dice además su base de datos, su clúster, quién la pidió y cuándo. Si no se pudo hacer, dice «No
     se pudo hacer» y por qué en «último error».
  Recuperar en el negocio lo que la copia aparte tiene y al negocio le falta (hub#1257):
  9. En Copias aparte elige la copia hecha y la acción «Recuperar en el negocio…». La página explica que lo que el
     negocio eliminó y aún guarda vuelve tal como era, con su historial, y que lo que ya no tiene se crea de nuevo como lo
     crea su propia pantalla, sin copiar nada; que lo que el negocio tiene, o ha vuelto a crear, se queda como está,
     salvo una cosa: una categoría que vuelve recupera lo que tenía dentro y el negocio aún conserva, sin sacarlo de
     donde el negocio lo haya puesto después; que los registros para Hacienda no se recuperan nunca y que el negocio
     sigue abierto. Y que lo que vuelve no es nada
     nuevo para el negocio: no arranca ninguna de sus automatizaciones, así que a nadie se le da la bienvenida ni se le
     avisa otra vez de una cita que ya tenía (hub#1307).
     Debajo, «Qué recuperar», con lo que se puede traer marcado (hoy, **Clientes**, **Categorías de productos,
     Productos, Enlaces de productos a categorías**, **Categorías de servicios, Servicios, Enlaces de servicios a
     categorías, Enlaces de subcategorías a categorías**, **Citas, Citas periódicas**, **Precios de tarifa**,
     **Menús, Platos de menú, Elecciones de menú de productos** y **Grupos de suplementos, Opciones de suplementos,
     Grupos de suplementos de categorías, Grupos de suplementos de productos**). Pulsa **Recuperar**.
  10. Sale «1 copia aparte devolverá Clientes, Categorías de productos, Productos, Enlaces de productos a categorías,
      Categorías de servicios, Servicios, Enlaces de servicios a categorías, Enlaces de subcategorías a categorías,
      Citas, Citas periódicas, Precios de tarifa, Menús, Platos de menú, Elecciones de menú de productos, Grupos de
      suplementos, Opciones de suplementos, Grupos de suplementos de categorías, Grupos de suplementos de productos a su
      negocio en unos minutos:
      Recuperaciones dice cómo
      fue.». En
      Recuperaciones la ve «Pedida» con la copia, qué se pidió y cuándo.
  11. Unos minutos después dice «Hecha» y qué volvió, cada cosa aparte y con su nombre: «Clientes: se restauró 1, se
      crearon 2» o «Clientes: se crearon 2, 1 sin crear». Su ficha dice además cuáles no volvieron y por qué (por su identificador en la copia, sin datos
      personales). Si uno volvió sin algo de lo que tenía, su cuenta lo dice («Servicios: se crearon 2, 1 con notas») y
      su ficha, en «notas», qué le falta y por qué, por su identificador en la copia. Un cliente que el negocio eliminó y
      aún guarda vuelve LA MISMA ficha, con sus compras y lo gastado, sus
      consentimientos, notas y actividad, sus grupos, etiquetas y campos propios y sus pedidos enlazados (CUSTOMER-F33).
      Uno que el negocio ya no tiene vuelve como ficha nueva, creada como la crea la pantalla de Clientes, con su nombre,
      contacto, NIF, dirección, fechas, origen, etapa, canal y notas, y con sus grupos, etiquetas y campos propios: el
      grupo, la etiqueta o el campo que el negocio tiene con ese nombre es ese, sin hacer otro, y el que ya no tiene se
      vuelve a crear como estaba (hub#1285); un valor de un campo que el negocio desactivó, o que su campo ya no
      admite, no vuelve, y la ficha vuelve sin él, con su nota («Clientes: se crearon 2, 1 con notas»; hub#1438). A una ficha
      eliminada que vuelve le vuelven también el grupo, la etiqueta o el campo propio que el negocio borró después, igual
      que a la ficha nueva (hub#1356); lo que el negocio aún tiene se queda como está, aunque la sacara de un grupo o le
      quitara un valor antes de eliminarla, y un valor que ya tiene en un campo que el negocio volvió a crear se queda.
      Nunca vuelve una ficha cuyos datos personales se borraron (RGPD) ni una que se unió a otra, ni se repite una que el
      negocio ya volvió a crear (el mismo nombre, teléfono y email). Con Productos, «Categorías de productos: se
      creó 1; Productos: se restauró 1, se creó 1; Enlaces de productos a categorías: se creó 1» (las categorías, los
      productos y los enlaces que volvieron, cada uno con su cuenta): primero vuelve
      cada categoría de productos que el negocio ya no tiene (la eliminó o la perdió), como una nueva, creada como la
      crea la pantalla de Categorías, con su nombre, slug, descripción, icono, color, orden y categoría fiscal; la
      eliminada sigue eliminada (INVENTORY-F07). Una que el negocio conserva, aunque la renombrara, es la misma, y una
      que ya volvió a crear (otra viva con su nombre, sin distinguir mayúsculas ni espacios, que no sea ya una de la
      copia; la más antigua si hay dos) no se repite: se usa la suya, tal como está. Después, un producto que el negocio
      eliminó y aún guarda vuelve EL MISMO y cuenta como restaurado, con su stock, sus categorías que siguen vivas, la que
      acaba de volver si la tenía en la copia, su imagen de la librería (la que tenía en la copia si lo eliminó antes de
      que eliminar se la dejara y se quedó sin ninguna) y en Movimientos su historial entero, activo y a la venta
      (INVENTORY-F34).
      Uno que el negocio ya no tiene vuelve como uno nuevo, creado como lo crea la pantalla de Productos, con su nombre,
      SKU, EAN-13, descripción, tipo, precio, coste, unidades, umbral, control de stock y categoría fiscal, activo o
      desactivado como estaba y en sus categorías: la misma si el negocio aún la tiene, y si no, la que acaba de volver
      o la que el negocio volvió a crear con su nombre; sin stock, que se cuenta (INVENTORY-F14), porque el de la copia es
      de otro día, y con la imagen de la librería que tenía (una que la librería ya no tiene, no; una foto propia,
      nunca, porque se borró con el producto). No vuelve ni se repite uno que el negocio ya volvió a dar de alta (otro
      vivo con su SKU o su EAN-13). Al final, los productos que el negocio conserva vivos y estaban en la copia en una
      categoría que acaba de volver vuelven a ella, sin perder ninguna otra (INVENTORY-F07): es lo único que la
      recuperación toca de lo que el negocio tiene, y se cuenta aparte, como «Enlaces de productos a categorías». Una
      categoría que el negocio conserva (aunque le quitara productos) o que volvió a crear a mano no se rellena. Con
      Servicios,
      «Categorías de servicios: se creó 1; Servicios: se crearon 2; Enlaces de servicios a categorías: se crearon 3;
      Enlaces de subcategorías a categorías: se creó 1» (las categorías, los servicios y lo que el negocio conservaba y
      volvió a ellas, cada uno con su cuenta): primero
      vuelve cada categoría de servicios que el negocio ya no tiene (la eliminó o la perdió), como una nueva, creada como
      la crea la pantalla de Categorías, con su nombre, descripción, icono, color y orden, dentro de su categoría padre si
      el negocio la tiene o vuelve también (si no, en la raíz); la eliminada sigue eliminada. Al final vuelve a ella lo
      que tenía dentro en la copia y el negocio conserva donde lo dejó eliminarla (SERVICE-F08): sus servicios que siguen
      sin categoría, archivados también, y sus subcategorías que siguen colgando de donde colgaba ella (la raíz, si estaba
      en la raíz), cada uno cambiado como lo cambia la pantalla: es lo que la recuperación toca de lo que el negocio
      tiene, y se cuenta aparte, como «Enlaces de servicios a categorías» y «Enlaces de subcategorías a categorías»; si
      el negocio lo mueve mientras tanto, se queda donde lo puso y se cuenta «sin crear» con su porqué
      (`service.service_moved`), y si lo cambia sin moverlo mientras vuelve la categoría (otro precio, otro icono), se
      queda como lo dejó y se cuenta igual, «sin crear» con su porqué («service.service_changed: volvió sin el servicio
      <su identificador>: el negocio lo cambió mientras tanto», o `service.subcategory_changed`). Lo que el negocio
      movió después (un servicio en otra categoría, una subcategoría en otro sitio) se queda donde está, y la cuenta de
      la categoría lo dice («Categorías de
      servicios: se creó 1, 1 con notas»), con el porqué en sus notas («service.service_moved: volvió sin el servicio <su
      identificador>: se movió a otra categoría después»). Una que el negocio ya volvió
      a crear (otra viva con su nombre, sin distinguir mayúsculas ni espacios) no se repite: se usa la suya, tal como está,
      y no se rellena, como tampoco la que trajo una recuperación anterior si se pide otra vez. Si aquella recuperación
      falló a medias, pedirla otra vez desde la misma copia termina lo que dejó: lo que el negocio conserva sin tocar
      desde que volvió la categoría vuelve a ella, contado en sus enlaces.
      Después, cada servicio que el negocio ya no tiene vuelve como uno nuevo, en oferta, creado como lo crea la pantalla
      de Servicios, con su nombre, tarifa, precios, coste, duración, márgenes, capacidad, descripciones, reservas, orden,
      destacado, SKU, código de barras y notas, su categoría fiscal y su categoría: la misma si el negocio aún la tiene,
      y si no, la que acaba de volver o la que el negocio volvió a crear con su nombre; y con los profesionales que lo
      hacían y el negocio sigue teniendo de alta, cada uno con sus minutos y su precio propios, asignados como los asigna
      Servicios (SERVICE-F31): como su servicio principal si el negocio no le ha dado otro desde entonces, y apagado si lo
      estaba. A quien Personal dio de baja, o el negocio ya no tiene, no se le asigna, porque ya no se le puede reservar,
      y Recuperaciones lo dice en las notas del servicio («service.member_terminated: volvió sin el profesional <su
      identificador>: dado de baja en Personal», o «…: ya no está en Personal»). Vuelve con la imagen de la librería que
      tenía, como la pone Servicios (SERVICE-F34): una que la librería ya no tiene, no; una foto propia, nunca, porque la
      copia aparte es de la base de datos y no de los ficheros. Uno archivado sigue
      en el negocio y no vuelve (se restaura en Servicios), tampoco uno que la copia tenía archivado, y no se repite uno
      que el negocio ya volvió a crear (otro con el mismo nombre en la misma categoría, que no sea ya uno de la copia; cada
      uno vale por uno solo, así que dos servicios con el mismo nombre vuelven los dos). Pedirlo otra vez no crea nada
      dos veces.
      Con Citas, «Citas: se restauró 1; Citas periódicas: se restauró 1» (las citas y las citas periódicas que
      volvieron, cada una con su cuenta).
      Las citas van siempre después de los clientes y los servicios, se pidan en el orden que se pidan, para que cada
      una encuentre a su clienta y sus servicios. Vuelve cada cita que aún no ha llegado y seguía reservada (pendiente o
      confirmada, sin cobrar). Una que el negocio borró y aún guarda vuelve LA MISMA y cuenta como restaurada, tal como
      estaba al borrarla: con su número, su clienta, sus servicios, su profesional, su hora, sus notas, su serie y su
      historial, que suma «Recuperada» (APPOINTMENT-F11). Una que el negocio ya no tiene vuelve reservada como la reserva
      la agenda: para la ficha de su clienta en el negocio (la misma, aquella en la que se unió o la que se volvió a
      crear), con sus servicios en el negocio como los empareja Servicios (el mismo o, si ya no está, el que se volvió a
      crear a mano o acaba de volver con Servicios: el mismo nombre en la misma categoría, el más antiguo si hay dos), su
      profesional, su hora, sus minutos y sus notas; como cita nueva, con otro número y sin su historial. Nunca se
      reserva encima de otra: una cuya hora ya está ocupada, ya no encaja en el horario del negocio o del profesional o
      está bloqueada, o cuya clienta, servicio o profesional ya no están, no vuelve y su motivo lo dice
      («appointment.slot_taken: …», «service.service_not_found: …»); una borrada que no vuelve por eso no se crea de
      nuevo. Las que ya pasaron no vuelven, y tampoco una que el negocio tiene (aunque la cancelara) o que volvió a
      reservar (la misma clienta a la misma hora, o su serie en esa fecha).
      Detrás de las citas van sus citas periódicas, las que en la copia seguían reservando (activas, con su profesional y
      sin terminar). Una que el negocio borró y aún guarda vuelve LA MISMA a Periódicas y cuenta como restaurada: activa,
      con su clienta, sus servicios, su profesional, su repetición y las citas que ya había reservado (APPOINTMENT-F15).
      No reserva nada por sí sola, así que nada se reserva dos veces: sus fechas siguientes las reserva «Reservar citas»,
      que salta las que ya tienen cita. Una que el negocio ya no tiene se crea de nuevo como la crea Periódicas
      (APPOINTMENT-F12), para la ficha de su clienta y sus servicios en el negocio como las citas, y reserva solo las
      fechas de su ventana que aún caben: ninguna en la que ya volvió una cita. Si su clienta ya no está o su profesional
      o uno de sus servicios ya no se reservan, no vuelve y su motivo lo dice; una que el negocio volvió a crear (la
      misma clienta, que se repite igual el mismo día a la misma hora) se queda como está.
      Los precios de tarifa van siempre después de los productos: «Precios de tarifa: se crearon 2». Cada precio de la
      copia que el negocio ya no tiene vuelve a su tarifa, con su precio y su «desde cantidad», puesto como lo pone el
      detalle de la tarifa, así que un producto eliminado que vuelve, el mismo o como uno nuevo, recupera sus precios en
      las tarifas donde estaba (PRICING-F15), y un servicio que vuelve como uno nuevo, también: van después de los
      servicios, al que la recuperación hizo por él (uno que el negocio volvió a crear a mano no recibe ninguno, y el
      precio dice por qué). No se repite uno cuyo sitio (la misma tarifa, el mismo producto o
      servicio y la misma «desde cantidad») el negocio ya volvió a ocupar: se queda el suyo. Uno que la tarifa no acepta hoy (desactivada, o su
      producto sigue eliminado) no vuelve y su motivo lo dice. Las reglas de descuento del producto, que eliminarlo solo
      apagó, se vuelven a encender solas con él (PRICING-F14).
      Los grupos de suplementos de los productos van también después de los productos: «Grupos de suplementos de
      productos: se crearon 2». Cada grupo que en la copia colgaba de un producto vivo allí y que el negocio ya no tiene
      enganchado a ese producto se vuelve a enganchar, como lo engancha la hoja del grupo, así que un producto eliminado
      que vuelve, el mismo o como uno nuevo, pregunta otra vez en el TPV sus salsas, su punto o sus extras
      (MODIFIER-F10). No se repite uno cuyo grupo el negocio ya volvió a enganchar a ese producto: se queda el suyo. Uno
      que la hoja del grupo no acepta hoy (su producto sigue eliminado, o el negocio ya hizo otro a mano con su SKU, o
      borró el grupo y ya hizo otro a mano con su nombre) no vuelve y su motivo lo dice. Justo antes van, contados
      aparte, los grupos de suplementos de las categorías: «Grupos de suplementos de categorías: se crearon 2». Cada
      grupo que en la copia colgaba de una categoría viva allí y que el negocio ya no tiene enganchado a ella se vuelve
      a enganchar del mismo modo: a la misma categoría si el negocio la conserva, o a la que la recuperación trajo por
      ella con su nombre, así que sus productos vuelven a preguntarlo en el TPV. Una categoría que sigue eliminada o que
      el negocio volvió a crear a mano se queda sin él, y su motivo lo dice. Antes, contadas aparte, las opciones que el
      negocio quitó de un grupo que conserva: «Opciones de suplementos: se creó 1». Cada una vuelve a su grupo, el mismo
      aunque lo renombrara, como la añade la hoja del grupo, con su suplemento, su categoría fiscal propia y su orden;
      no se repite una que el negocio ya volvió a crear con su nombre en ese grupo. Si estaba elegida por defecto y el
      grupo ya trae tantas como admite (otra, en uno de «elige una»), vuelve sin elegir, las del negocio siguen elegidas
      y su nota lo dice («Opciones de suplementos: se creó 1, 1 con notas») (MODIFIER-F10). Y antes de todo eso,
      contados aparte, los propios grupos: «Grupos de suplementos: se creó 1». Cada grupo que la copia tiene y el
      negocio ya no (lo borró, con sus opciones y sus enganches) se vuelve a crear como lo crea la pantalla de
      Suplementos, con sus opciones como las añade la hoja del grupo, y sus enganches de la copia se le hacen a ese, así
      que vuelve a salir en el TPV con sus opciones y sus suplementos (MODIFIER-F10). Uno que el negocio volvió a crear
      a mano con su nombre se queda como está, sin otro igual, y uno que conserva, con las opciones que tenga más las
      que le quitó. Una opción que la hoja del grupo no acepta hoy (su categoría fiscal propia ya no está activa en
      Impuestos) no vuelve: el grupo vuelve sin ella y su nota lo dice («Grupos de suplementos: se creó 1, 1 con
      notas»).
      Las elecciones de menú de los productos van también después de los productos: «Elecciones de menú de productos:
      se crearon 2». Cada elección que en la copia ofrecía un producto vivo allí y que el negocio ya no tiene se vuelve a
      añadir a su plato, como la añade el constructor del menú, con su suplemento y, si estaba agotada, agotada, así que
      un producto que vuelve, el mismo o como uno nuevo, sale otra vez en sus menús del TPV (COMBO-F15). No se repite una
      que el negocio aún tiene, aunque le cambiara el producto, ni una cuyo producto el negocio ya volvió a ofrecer en ese
      plato: se queda la suya. Una que el constructor no acepta hoy (su producto sigue eliminado o está desactivado, o el
      negocio ya hizo otro a mano con su SKU) no vuelve y su motivo lo dice. Justo antes van, contados aparte, los menús
      y sus platos: «Menús: se creó 1; Platos de menú: se crearon 2». Cada menú que la copia tiene y el negocio retiró
      (con sus platos y sus elecciones) se vuelve a crear como lo crea la pantalla de Menús, con su precio, su categoría
      fiscal y la imagen de la librería que tenía; después, cada plato que su menú ya no tiene (el menú acaba de volver
      o el negocio quitó el plato) se vuelve a añadir al final del menú como lo añade el constructor, y sus elecciones
      van a ese plato, así que el menú vuelve a salir en el TPV con sus platos y sus suplementos (COMBO-F15). Uno que el
      negocio volvió a crear a mano con su nombre (el menú, o el plato en su menú) se queda como está, sin otro igual, y
      lo que en la copia colgaba de él no vuelve y su motivo lo dice; lo que vuelve se reconoce aunque se renombre, así
      que pedirlo otra vez no lo repite.
Entra: los negocios elegidos, el clúster temporal con su copia y el momento; para recuperar, la copia aparte hecha y qué
recuperar.
Sale: la base del negocio como estaba en ese momento; la que tenía, guardada 7 días en su servidor; el aviso
`control.hub.restore_requested` con quién lo pidió. Los demás negocios no notan nada. En una copia aparte: el negocio
tal como estaba, sin tocarlo; una base aparte en su clúster con los datos de ese momento, cerrada a la aplicación y
guardada 7 días; el aviso `control.hub.restore_aside_requested` con quién lo pidió. Al recuperar: en el negocio, cada ficha
eliminada que aún guardaba, viva otra vez con su aviso de ficha recuperada (`customer.customer.restored`), una ficha
nueva por cada cliente que ya no tenía, con su aviso de ficha creada (`customer.customer.created`), y en las dos los de
sus grupos y etiquetas puestos (`customer.customer.groups_changed`, `customer.customer.tags_changed`), cada grupo, etiqueta o campo
propio que le faltaba hecho otra vez, con su aviso (`customer.group.created`, `customer.tag.created`,
`customer.field.created`, y `customer.group.updated` o `customer.tag.updated` si estaba desactivado), una categoría de
productos nueva por cada una que le faltaba, con su aviso de categoría creada (`inventory.category.created`) y el de cada
producto eliminado que vuelve en ella (`inventory.product.categorized`), cada producto
eliminado que aún guardaba, vivo otra vez con su aviso de producto recuperado (`inventory.product.restored`), un
producto nuevo por cada producto que ya no tenía, con su aviso de producto creado (`inventory.product.created`), una
categoría de servicios nueva por cada una que le faltaba, con su aviso de categoría creada (`service.category.created`)
y el de cada servicio o subcategoría que el negocio conservaba y vuelve a ella (`service.service.updated`,
`service.category.updated`), un servicio nuevo por cada uno que ya no tenía, con su aviso de servicio creado (`service.service.created`) y uno de
profesional asignado (`service.assignment.assigned`) por cada profesional que vuelve con él, cada cita borrada que aún
guardaba, viva otra vez con su aviso de cita recuperada (`appointment.appointment.restored`), una cita nueva por cada
una que ya no tenía, con su aviso de cita creada (`appointment.appointment.created`), cada cita periódica borrada que
aún guardaba, activa otra vez con su aviso de serie recuperada (`appointment.recurring.restored`), una cita periódica
nueva por cada una que ya no tenía, con su aviso de serie creada (`appointment.recurring.created`) y el de cada cita que
reserva, un precio de tarifa por cada uno que le faltaba, con su aviso de precio puesto (`pricing.price_item.added`),
un grupo de suplementos nuevo por cada uno que le faltaba, con su aviso de grupo creado (`modifier.group.created`) y el
de cada una de sus opciones (`modifier.option.created`), una opción por cada una que le faltaba a un grupo de
suplementos que conserva, con su aviso de opción creada (`modifier.option.created`), un grupo de suplementos enganchado
a una categoría o a un producto por cada uno que le faltaba, con su aviso de enganche hecho (`modifier.link.attached`),
un menú por cada uno que le faltaba, con su aviso de menú nuevo (`combo.combo.created`), un plato por cada uno que le
faltaba, con su aviso de plato nuevo (`combo.group.created`), y una elección de menú por cada una que le faltaba, con su aviso de elección nueva (`combo.option.created`), y nada más. Cada uno
de esos avisos dice que lo hizo la recuperación (su autor es `copy_recovery:<id>`, el de la fila de Recuperaciones), así
que ninguna automatización del negocio arranca con ellos (FLOW-F21), sea de algo creado o de algo recuperado; lo que
solo pone al día lo del negocio con ellos sigue igual (la Bandeja de WhatsApp enlaza a la ficha su conversación;
Tarifas vuelve a encender las reglas del producto que vuelve, `pricing.rule.activated`), y lo
que graba al hacerlo lleva la misma marca, así que tampoco arranca ninguna, ni de primera ni de segunda mano (la
conversación enlazada otra vez no arranca «se vincula una conversación de WhatsApp a un cliente»; hub#1365). La
copia, sin tocar; el aviso `control.copy.recovery_requested` con quién lo pidió.
Si falla: lo que la restauración no admite lo dice el aviso, negocio a negocio, y ese negocio no se toca: uno que no está
listo o no tiene base propia, una demo, uno que se está trasladando o restaurando, un clúster abierto a hubs nuevos o con
negocios vivos, el propio clúster del negocio, una copia que no está en ese clúster o que es demasiado grande, y un
momento que aún no ha llegado. Sin clúster o sin momento, la página los vuelve a pedir. Si el negocio tiene registros
VeriFactu de producción hechos, enviados o cambiados después de ese momento, no se restaura y no cambia nada, porque
volvería a usar números que la AEAT ya tiene: su ficha lo dice en «último error» («restore_fiscal_records: …»); para ese
caso está «Restaurar en una copia aparte…», que no los compara porque no toca el negocio. Cualquier otro fallo deshace la
restauración sola: el negocio sigue con su base de siempre y su ficha dice por qué. Una copia aparte admite lo mismo que
la restauración y lo que no admite lo dice el aviso igual; si falla al hacerla, no queda nada de ella y Copias aparte dice
por qué («restore_aside_<paso>: …»); el negocio no se entera. Recuperar solo se puede desde una copia hecha y una sola
vez a la vez por copia; si no, el aviso lo dice («Solo una copia aparte ya hecha devuelve algo.»), y sin nada marcado la
página lo vuelve a pedir. Lo que no se puede traer de una app lo dice su resultado y lo demás sigue: la app está apagada en
el negocio («Clientes: nada (app_inactive: …)»; en una app que devuelve varias cosas, cada una lo dice: «Categorías de
servicios: nada (app_inactive: …); Servicios: nada (app_inactive: …)»), o la copia no la tenía, le falta la migración que su lectura necesita o
tiene una que este código no conoce (`recover_not_in_copy`, `recover_copy_behind`, `recover_copy_ahead`). Lo que la
operación de crear no acepta hoy (un teléfono que ya no vale, un producto sin categoría fiscal o con una que Impuestos
ya no tiene activa, un servicio cuya categoría fiscal se desactivó (`service.tax_category_unknown`), una hora ocupada,
una clienta que ya no está, un servicio que el negocio ya no tiene ni volvió a crear) se cuenta «sin crear» con su
motivo, y lo demás vuelve; también una ficha eliminada que
entretanto se unió a otra o se borró («customer.customer_unavailable: …»). Si la copia ya no está,
la recuperación dice «No se pudo hacer» y por qué («recover_copy_unreadable: …»). Mientras el negocio se traslada o se
restaura, la recuperación espera sin hacer nada. Con la plataforma congelada para una subida de la base de datos, la restauración espera, con el negocio en
mantenimiento, hasta que se descongela. Con registros solo del entorno de pruebas, después se recupera la cadena
(VERIFACTU-F28). El personal de soporte ve la lista, Copias aparte y Recuperaciones, pero no las acciones.
Implicados: VERIFACTU-F28, BASE-F111 (la misma página de espera que un traslado), CUSTOMER-F01, CUSTOMER-F04, CUSTOMER-F06,
CUSTOMER-F07, CUSTOMER-F12, CUSTOMER-F13, CUSTOMER-F16, CUSTOMER-F29, CUSTOMER-F33, INVENTORY-F01, INVENTORY-F04,
INVENTORY-F07, INVENTORY-F30, INVENTORY-F34, SERVICE-F01, SERVICE-F04, SERVICE-F05, SERVICE-F07, SERVICE-F08,
SERVICE-F31, SERVICE-F34, APPOINTMENT-F01, APPOINTMENT-F10, APPOINTMENT-F11, APPOINTMENT-F12, APPOINTMENT-F15, PRICING-F07,
PRICING-F14, PRICING-F15, MODIFIER-F02, MODIFIER-F04, MODIFIER-F05, MODIFIER-F10, COMBO-F04, COMBO-F05, COMBO-F06, COMBO-F15, FLOW-F21, WHATSAPP_INBOX-F04; hub#1198,
hub#1213, hub#1257,
hub#1282, hub#1283, hub#1284,
hub#1285, hub#1306, hub#1307, hub#1319, hub#1320, hub#1321, hub#1322, hub#1323, hub#1326, hub#1327, hub#1341, hub#1343,
hub#1355, hub#1356, hub#1364, hub#1365, hub#1373, hub#1375, hub#1429, hub#1431, hub#1438, hub#1442, hub#1456, hub#1457,
hub#1458, hub#1459, hub#1473, hub#1474, hub#1495, hub#1505, aws#77

### BASE-F115 Ver la ayuda de la pantalla en la que se está
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: la barra de arriba de un módulo con la ayuda lista o de una pantalla del Hub (botón «?», «Ayuda») y la ventana
de ayuda
Pasos:
  1. En un módulo con la ayuda lista y en las pantallas propias del Hub (Inicio, Empleados, la ficha de una persona, lo
     que permite un rol, Archivos, Apps, Sistema, Ajustes y Mi perfil), arriba a la derecha, junto al asistente, está el
     botón «?» («Ayuda»), también al volver atrás. No sale en un módulo cuya ayuda aún no está lista, en una pantalla sin
     ayuda (la documentación de la API), en la de «Sin acceso» ni a quien no puede ver el Inicio.
  2. Al pulsarlo se abre la ventana «Ayuda · <módulo>», con el icono del módulo («Ayuda · ERPlora» en una pantalla del
     Hub), centrada en una tableta o un ordenador y desde abajo en un móvil. Nunca se abre sola, y se cierra al pasar a
     otro módulo.
  3. Arriba, el vídeo del módulo, si tiene uno, en el idioma de la persona o, si no lo hay, en español. No se pide
     nada a YouTube hasta que se pulsa, y se ve dentro de la ventana, a todo su ancho, con el reproductor de YouTube
     completo: pantalla completa, subtítulos encendidos en el idioma de la ayuda y su logotipo, que abre el vídeo en
     YouTube en otra pestaña.
  4. Debajo, «Para qué sirve», con un texto corto, de dos o tres frases, de lo que se hace en el módulo (en una pantalla
     del Hub, de lo que trae el Hub siempre), y «En esta pantalla · <pestaña>», marcado «Estás aquí», con el resumen de
     lo que enseña la pestaña en la que se está: corto y entero, sin «Ver más».
  5. «Cómo se hace» trae cada tarea terminada del módulo, agrupada por pestaña, primero las de la pestaña en la que se
     está; en una pantalla del Hub, las de las pantallas del Hub que la persona puede ver, y solo las que hace su rol: a
     un empleado no le sale cómo se activa una app. Cada tarea es una fila plegada que se abre con sus pasos y su «Si
     algo falla», una a la vez. Una tarea con
     vídeo corto lo enseña al abrirse, antes de sus pasos, con el mismo reproductor que el del módulo y en el idioma de
     la persona o, si no lo hay, en español; con varios, uno debajo de otro. Abrir la ayuda o una tarea no pide nada a
     YouTube hasta que se pulsa el vídeo. Con más de ocho tareas, arriba sale «Buscar tareas…», que filtra por el título y los pasos sin mirar acentos ni mayúsculas;
     si nada coincide, dice «Nada coincide con tu búsqueda» y «Borrar búsqueda» vuelve a enseñarlas todas.
  6. «Otras pantallas» trae las demás pestañas del módulo, o las demás pantallas del Hub que la persona puede ver,
     plegadas, cada una con su resumen corto. Un enlace de la ayuda a una pantalla del Hub lleva a ella y cierra la
     ayuda.
  7. «Pregúntale al asistente», los destellos del pie, cierra la ayuda y abre el asistente con la pregunta escrita, sin enviarla: «¿Cómo hago
     esto: <tarea>?» sobre la última tarea que se abrió o, si no se abrió ninguna, «¿Cómo uso <módulo> en
     <pantalla>?»; si ya había algo escrito, la pregunta va debajo. «Cerrar» cierra la ayuda.
Entra: el módulo, o la pantalla del Hub, y la pestaña en la que se está.
Sale: nada: la ayuda solo se lee. Es la parte del manual de uso del módulo, o de las pantallas del Hub, que lee el
cliente, en el idioma de la persona.
Si falla: mientras se lee, la ventana enseña su esqueleto; si no se puede leer, dice «No se ha podido cargar la
ayuda.» y «Reintentar» la vuelve a pedir. La ayuda ya leída se queda guardada hasta que se recarga la página: sin
conexión se vuelve a abrir, también desde otra pestaña del módulo u otra pantalla del Hub, y cada vídeo dice «Sin
conexión: el vídeo no está disponible», con el texto a la vista. Si el manual no está traducido al idioma de la persona,
o su traducción se quedó atrás, la ayuda sale en español.
Implicados: BASE-F92, BASE-F93

### BASE-F116 Leer las novedades de ERPlora
Estado: hecho
Actor: propietario, administrador; por el asistente, cualquiera del negocio
Pantalla: Sistema · Actualizaciones
Pasos:
  1. En la pestaña «Actualizaciones», debajo de la versión y su fecha, sale «Novedades»: lo que ha cambiado
     en ERPlora que el negocio nota, lo más reciente primero. Mientras carga: «Consultando las novedades…».
  2. Cada novedad dice su día, si es algo nuevo, una mejora o un arreglo («Nuevo», «Mejora» o «Arreglo»), un título
     corto y una o dos frases de lo que se puede hacer ahora, tal cual se escribieron. Son notas escritas para el
     negocio, nunca la lista de cambios del código.
  3. Salen las 20 más recientes, sin páginas.
  4. Sin ninguna, dice «Todavía no hay novedades.».
  5. Por el asistente, «¿qué hay de nuevo en ERPlora?» o «¿qué ha cambiado en la última actualización?» las lee igual,
     en el idioma de la persona. Así las lee también quien no administra el negocio, que no tiene Sistema:
     no dicen nada del negocio.
Entra: las novedades de la versión que corre: viajan con ella, así que siempre son las suyas.
Sale: nada guardado: las novedades solo se leen.
Si falla: «No se pudieron cargar las novedades» con «Reintentar»; la versión y su fecha siguen a la vista.
Implicados: BASE-F41, BASE-F39

### BASE-F117 Ver en la campana que el plan tiene una factura sin pagar
Estado: hecho
Actor: propietario, administrador
Pantalla: La campana
Pasos:
  1. erplora.com no consigue cobrar la renovación del plan del negocio y le da sus 7 días de margen (BILLING-F16): el
     negocio sigue funcionando con todo su plan.
  2. La campana de quien administra el negocio sube sin recargar con el aviso urgente «Tu plan de ERPlora tiene una
     factura sin pagar», que llega como tarjeta y se recoge en ella. Su frase dice hasta cuándo: «Págala en
     erplora.com: si no se paga antes del 24 de noviembre de 2026, el negocio se suspende. No se borra nada.», con la
     fecha en el reloj del negocio, y el anillo de la campana se va vaciando en esa última semana.
  3. «Pagar en erplora.com» abre en una pestaña nueva las facturas pendientes de este negocio en erplora.com, donde se
     paga (BILLING-F17). Solo en el navegador: en la app instalada el aviso sale igual, sin el botón, y su frase ya
     dice dónde pagarla.
  4. Si se pasa el plazo y erplora.com todavía no lo ha suspendido, el aviso lo dice en el momento, sin recargar:
     «Págala en erplora.com: su plazo terminó el 24 de noviembre de 2026 y el negocio se puede suspender en cualquier
     momento. No se borra nada.», con el anillo vacío.
  5. Al pagarla, el aviso desaparece en cuanto erplora.com se lo dice al negocio. Si se suspende, el negocio deja de
     abrirse hasta que se pague (BILLING-F16).
Entra: el estado del negocio y el momento en que se suspende, tal como los manda erplora.com en su foto del negocio
(HUBS-F31). El Hub no le pregunta a erplora.com ni cuenta los 7 días por su cuenta.
Sale: nada guardado en el Hub.
Si falla: un responsable o un empleado no ve el aviso. Si la foto no trae el plazo, el aviso sale sin fecha: «Págala en
erplora.com: si no se paga pronto, el negocio se suspende. No se borra nada.». Si no se pueden leer los avisos, la
campana se queda con lo último que supo, como en BASE-F10.
Implicados: BASE-F10, BASE-F11, BILLING-F16 (erplora.com), BILLING-F17 (erplora.com), HUBS-F31 (erplora.com)

### BASE-F118 Abrir una pantalla sin permiso: «Sin acceso» y a quién pedirlo
Estado: hecho
Actor: responsable, empleado
Pantalla: Sin acceso
Pasos:
  1. Abre por su dirección (un enlace, el historial, una pestaña que se quedó abierta o escribiéndola) una pantalla que
     su rol no abre: una entrada de una app que no sale en su menú, como «Reglas» de Impuestos para un empleado, una
     de la plataforma que no sale en su menú lateral, como «Sistema» para quien no administra el negocio, o cualquier
     pantalla que cuelgue de ellas. También la ficha de otra persona en **Empleados** para quien no administra el
     negocio, aunque llegue a ella porque la caja cambió de usuario con la ficha abierta (BASE-F60).
  2. En lugar de la pantalla, en la misma dirección, sale «Sin acceso»: «No tienes acceso a esta pantalla» — «Tu rol en
     este negocio no la abre.». Mientras busca a quién pedirlo: «Buscando quién puede darte acceso…».
  3. Debajo, «Pide acceso a una de estas personas:» y el nombre de cada una, con su avatar: quien le puede cambiar el
     rol en erplora.com (HUBS-F26). Un empleado ve al propietario y a los administradores; un responsable, solo al
     propietario. Solo el nombre: ni el email ni el teléfono. Cuentan también los invitados que aún no han entrado.
  4. «Ir al Inicio» lleva al Inicio.
Entra: la sesión de la persona, que dice qué pantallas de cada app tiene cerradas por su rol y qué permisos tiene,
los que abren cada entrada del menú lateral (las mismas que no salen en sus menús); las personas del negocio con su rol, de la última foto de erplora.com.
Sale: nada.
Si falla: si no se puede saber a quién pedirlo, «No hemos podido saber quién puede darte acceso» — «Pregunta a quien
lleva el negocio o vuelve a intentarlo.» con «Reintentar», y la pantalla sigue diciendo que no tiene acceso. Sin nadie
a quien nombrar: «Pide acceso a quien lleva el negocio.». Si la app entera no se abre en el negocio (apagada o sin su
suscripción), sale su motivo (BASE-F26). El Hub rechaza igual lo que esa pantalla pediría: «Sin acceso» solo ahorra
una pantalla de errores.
Implicados: BASE-F26, HUBS-F26 (erplora.com)

### BASE-F119 Lo que se ve según los permisos de dato
Estado: hecho
Actor: propietario, administrador, encargado, empleado, gestoría
Pantalla: Empleados · Personal, Inicio · Resumen, Ventas · Ventas, Clientes
Pasos:
  1. Además de lo que puede hacer, cada rol dice qué datos delicados ve, con cuatro permisos de dato: ver los costes,
     ver el contacto de los clientes, ver el contacto del equipo y ver los totales del negocio. El propietario, el
     administrador y el encargado tienen los cuatro; el empleado, solo el contacto de los clientes, que necesita
     para atenderlos; la gestoría, solo los totales del negocio.
  2. Quien no tiene un permiso de dato no recibe ese dato por ningún camino: ni en la pantalla, ni por la API, ni en
     lo que contesta el asistente. Donde iría, el dato llega vacío y la pantalla no lo enseña.
  3. En **Empleados › Personal**, la columna «Email» solo sale a quien ve el contacto del equipo. Un empleado no ve
     el email de nadie, tampoco el suyo, ni dentro de un nombre: una cuenta de erplora.com sin nombre sale con lo que
     va antes de la @.
  4. Un panel de Inicio cuya cifra es un dato que la persona no ve no le sale en el tablero ni entre los que puede
     añadir.
  5. Una llave de API ve los datos que ve hoy quien la creó: una llave del propietario o de un
     administrador, que los ven todos, lee y escribe el coste de un producto como antes.
  6. Los totales del negocio son las cifras de todo el negocio, más allá de lo que hace cada uno: con las ventas de
     todos, las cifras de **Ventas** y sus paneles de Inicio son las del negocio entero; sin ellos, las de las ventas
     de la persona. En **Clientes**, «Ingresos» solo sale a quien los ve.
Entra: el rol de la persona en este negocio.
Sale: nada guardado.
Si falla: una petición por la API o al asistente que filtra u ordena por un dato que la persona no ve se rechaza como si
no tuviera permiso, sin hacer nada.
Implicados: BASE-F06, BASE-F07, BASE-F81, BASE-F82, BASE-F86, BASE-F125, SALE-F28, CUSTOMER-F31

### BASE-F125 Una llave deja de servir si su creador ya no puede
Estado: hecho
Actor: API (otro programa), propietario, administrador
Pantalla: ninguna (se ve en lo que la API contesta al otro programa)
Pasos:
  1. Cada llave recuerda quién la creó. Una llave creada antes de que se guardara pasa a nombre del propietario del
     negocio con la siguiente foto de erplora.com, que llega como mucho cada noche; hasta entonces puede lo mismo que
     el propietario, como antes.
  2. Una llave nunca hace más que quien la creó, con lo que esa persona puede hoy en el negocio: abre una operación
     solo si su creador tiene su permiso; recibe un dato delicado (los costes, el contacto, los totales del negocio)
     solo si su creador lo ve, y si no le llega vacío (BASE-F119); y en lo que tiene dueño (las ventas, las cajas,
     las facturas, las citas, las comisiones) lee todo solo si su creador lo ve todo, y si no, solo lo de su creador.
     Al dar una cita o atender a una clienta, la llave sigue del lado de la clienta, como hasta hoy.
  3. Si a quien la creó le cambian el rol en erplora.com y pierde un permiso, la llave lo pierde a la vez, sin
     tocarla: lo que lo necesita contesta 403 `permission_denied`, y el dato que ya no ve llega vacío.
  4. Si quien la creó deja el negocio, la llave deja de abrir nada: cada petición contesta 403
     `base.api_key_owner_gone`, «Quien creó esta API key ya no está en el negocio. Crea una nueva.». La llave sigue
     en **Empleados › API keys**: quien lleva el negocio la revoca (BASE-F88) y crea otra (BASE-F86).
Entra: la llave con la que llama el otro programa y el rol de hoy de quien la creó, de la última foto de erplora.com.
Sale: nada guardado.
Si falla: el 403 dice si a quien la creó le falta el permiso (`permission_denied`) o si ya no está en el negocio
(`base.api_key_owner_gone`); lo demás que rechaza una llave no cambia: lo que la propia llave no puede hacer, 403
`base.api_key_scope`, y pasada de sus peticiones por minuto, 429 `base.api_key_rate_limited`.
Implicados: BASE-F86, BASE-F88, BASE-F89, BASE-F119, HUBS-F26 (erplora.com)

### BASE-F120 Arrancar ERPlora al iniciar sesión en el ordenador
Estado: hecho
Actor: propietario, administrador, responsable, empleado
Pantalla: Ajustes · General
Operaciones: ninguna
Pasos:
  1. En la app de ERPlora de un ordenador, **Ajustes › General** lleva en «Este dispositivo» el interruptor
     «Arrancar al iniciar sesión» («Abre ERPlora al iniciar sesión en este ordenador, para que los tiques siempre
     tengan dónde imprimirse.»), apagado de fábrica. En un navegador y en la app de Android no sale.
  2. Al moverlo, el Hub se lo pide a la app, que lo apunta en el sistema y vuelve a leer qué dice;
     mientras tanto, el interruptor espera.
  3. El interruptor queda donde dice el sistema, no donde se movió.
Entra: el interruptor, en el propio ordenador.
Sale: el arranque del sistema de este ordenador, no del negocio. En el Hub no se guarda nada.
Si falla: debajo, «No se pudo cambiar el ajuste de arranque al iniciar sesión.», y el interruptor vuelve a lo que
dice el sistema. Una app anterior a esta orden no lo enseña.
Implicados: HUB_APP-F27 (ERPlora/app), BASE-F62

### BASE-F126 Encender o apagar el acceso de soporte de ERPlora
Estado: hecho
Actor: propietario, administrador, personal de soporte de ERPlora
Pantalla: Ajustes · General, la página «Este negocio no deja entrar a soporte»
Pasos:
  1. Cuando el negocio quiere que el personal de soporte de ERPlora entre para ayudarle a configurarlo (cargar los
     productos, ajustar sus apps), el propietario o un administrador enciende «Dejar entrar al soporte de ERPlora» en
     la tarjeta «Acceso de soporte», la última de Ajustes › General. Viene apagado. También se enciende y se apaga por
     la API o pidiéndoselo al asistente, que lo confirma antes de cambiarlo.
  2. El cambio se guarda al instante, con quién lo hizo y cuándo, y lo confirma un aviso: «Acceso de soporte
     encendido: el soporte de ERPlora puede entrar.» o «Acceso de soporte apagado: el soporte de ERPlora ya no puede
     entrar.». No caduca: sigue encendido hasta que alguien del negocio lo apaga, porque una puesta en marcha puede
     durar varios días.
  3. Cualquiera del negocio ve en la tarjeta si está encendido, quién lo cambió por última vez y cuándo («Último
     cambio: Ana, 24/11/2026, 10:30.») y, en «Últimas entradas de soporte», las 10 últimas entradas de soporte (quién y
     cuándo), la más reciente primero; lo mismo da la API. Mientras nadie de soporte haya entrado, dice «Nadie del
     soporte de ERPlora ha entrado todavía.». A quien no administra el negocio el interruptor le sale desactivado, con
     «Solo quien administra el negocio puede cambiarlo.».
  4. Con el acceso encendido, una persona del soporte de ERPlora entra en el negocio con «Entrar como soporte», en el
     admin de erplora.com, con su propia cuenta, y llega como un administrador: puede hacer
     todo menos lo que solo hace el propietario (comprar para el negocio, reiniciarlo, sus copias). No sale en Empleados
     ni entre quienes pueden dar acceso, no entra en las cajas con PIN ni con tarjeta, no ocupa plaza ni cuenta en el
     uso del plan y su navegador no se queda como dispositivo del negocio: ni cierra la sesión de otro dispositivo ni se
     la cierra la entrada de otro. Cada entrada se suma al momento a la lista de las últimas entradas, y lo
     que hace queda a su nombre en los registros.
  5. Con el acceso apagado no entra: ve «Este negocio no deja entrar a soporte» — «El propietario o un administrador
     de este negocio tiene que encender el acceso de soporte de ERPlora para que puedas entrar. Pídeselo y vuelve a
     intentarlo.» con «Volver a intentarlo».
  6. Cuando alguien del negocio lo apaga, las sesiones de soporte abiertas en el negocio se cierran al momento y lo
     que tienen abierto se entera; las del resto del equipo siguen.
Entra: encendido o apagado; la cuenta de soporte que comprueba erplora.com.
Sale: el ajuste del negocio, con quién lo cambió y cuándo. Evento `base.support_access.changed`. Cada entrada de
soporte, con quién y cuándo. Evento `base.support_access.entered`.
Si falla: a quien no administra el negocio se le rechaza el cambio y el ajuste se queda como
estaba; al consultarlo, le sale que no puede cambiarlo. Si el cambio no se puede guardar, debajo sale «No se pudo
guardar el cambio.» y el interruptor vuelve a lo guardado; si la tarjeta no puede leer el ajuste, «No se pudo cargar
el acceso de soporte.» con «Reintentar». Con el acceso apagado, soporte no abre sesión ni deja entrada (la página del
paso 5).
Implicados: BASE-F52, BASE-F57, BASE-F97, BASE-F100, HUBS-F38 (erplora.com)

## Para quien lo mantiene

- **Permisos de dato** (BASE-F119; `base/sensitive.py`, `base/visibility.py`, `live.sensitive`): un campo de un
  esquema se marca con `Field(json_schema_extra=COSTS)` (o `CUSTOMER_CONTACT`, `TEAM_CONTACT`, `BUSINESS_TOTALS`) y, en
  una respuesta, admite nulo (`live.E026`). live lo pone a nulo a quien no tiene el permiso en `Operation.__call__`,
  también cuando una operación corre dentro de otra: un cálculo con costes los lee por su propia puerta, nunca llamando
  a otra operación con el contexto de la persona. Una entrada que rellena un campo marcado (un filtro, el orden) se
  rechaza con 403 `permission_denied`. Un panel de Inicio no sale a quien no tiene el permiso de un campo marcado que
  lee su `map` (`visibility.widget_open`). `tests/test_guardrails_sensitive.py` exige la marca en todo campo de
  respuesta con nombre de coste, contacto o sueldo, o su entrada en `UNMARKED` con su motivo (la lista solo encoge), y
  la misma marca en el filtro o el orden de una lectura que lo nombra. Una lectura de cifras (`stats`, `summary`,
  `report`, `by_staff`… o en un módulo `figures`) marca sus importes (`BUSINESS_TOTALS` los de todo el negocio) o está
  en `UNMARKED_FIGURES` con su motivo: las de Ventas suman con `Owned.counted`, que ya cuenta solo lo propio a quien
  no tiene los totales.
- **Dominio propio de un negocio** (BASE-F110, HUBS-F17, PLAN-SAAS §37 punto 2; `base/custom_domains.py`,
  `base.middleware.CustomDomainMiddleware`): `ALLOWED_HOSTS` no cambia. El SaaS nombra el dominio en la foto
  (`custom_domain`: minúsculas, sin puerto, sin punto final, en su forma ASCII; `null`, vacío o ausente, ninguno, porque la
  foto es entera), que lo guarda en `Hub.custom_domain`, y nunca se le pregunta por petición. Cada proceso guarda en memoria qué
  dominio es de quién y lo relee cada 30 s (al momento en el proceso que aplicó la foto): un host desconocido sigue siendo
  el 400 de `CommonMiddleware` **sin una sola lectura** y sin línea en el registro (hub#817: `django.security.DisallowedHost`
  va a un `NullHandler` en `LOGGING`; el 400 queda en la línea de acceso de daphne y cualquier otro `django.security` sigue
  en ERROR; `config/tests/test_security_logging.py`), y uno de los hosts del Hub ni pregunta. Un host conocido se
  responde en ese middleware, antes de `CommonMiddleware`, y no sigue por la cadena: `/` (la web, `base.public_home`),
  `/p/media/<su id>/` (sus imágenes públicas) y `/.well-known/erplora-hub` (la sonda del SaaS: `{"hub_id": …}`, sin lectura);
  cualquier otra ruta es 404 sin lectura, `/api` con su sobre, y nunca se lee la sesión. La página y sus imágenes releen la
  fila del negocio, como cualquier otro host: `base/tenancy/connections.py` necesita fresco dónde está su base de datos y
  una fila vieja devolvería el alias a un servidor anterior a una mudanza; esa lectura se hace una vez, y la página lee lo
  mismo que en su dirección. Un dominio que nombran dos negocios (se está moviendo entre ellos: sus dos fotos llegan en
  cualquier orden) no es de nadie hasta que el que lo deja manda la suya: se avisa con `base.custom_domain_taken`, no se
  rechaza ninguna foto y nunca se sirve la web equivocada. `custom_domains.served_on(hub)` dice en qué dominio abre la
  puerta la web de un negocio ahora (el de su fila, si el mapa se lo da a él), y es lo que su página nombra como
  dirección principal (WEBSITE-F10, hub#818).
- **Orden de una lista** (`base/ordering.py`): `list_order(*columnas, descending=…,
  nulls_last=…)` devuelve lo que necesita `order_by`, con todas las columnas y después el `id` en la dirección de la
  lista: la descendente es la ascendente leída al revés, empates incluidos, y las páginas ni repiten ni pierden filas.
  `list_order_for(sort, *desempates, columns=…, nulls_last=…)` es lo mismo para un `sort` que dice su dirección con un
  «-» delante, y `columns` dice qué columnas ordena cuando no es la de su nombre. Una columna puede ser una expresión
  (`Lower("name")`), y la nombrada dos veces cuenta donde aparece primero. Una app no escribe su propia copia; solo
  Facturación y Verifactu conservan la suya, en zona fiscal validada (hub#789). Sus pruebas por lista usan
  `base/tests/ordering.py`.
- Las tres consultas vivas del Inicio son de `base/queries/`, con permiso `base.view_home` y ruta ninja en
  `base/api/home.py` (`GET /api/home/setup`, `/home/widgets`, `/home/bell`): `base.setup.status` (también
  herramienta del asistente, `ai=`), `base.widget.list` y `base.bell.counters`. Las reglas puras viven en
  `base/home/` (sin ORM).
- Punto de extensión: cada módulo declara en su `LiveAppConfig` `setup` (`SetupStep`), `widgets`
  (`Widget`) y `bell` (`BellCounter`), dataclasses de `live.meta` comprobadas por `live.checks`
  (E009–E016). Cada consulta que nombran es un `kind="query"` de la propia app; base la ejecuta como la
  persona (`run_hook`).
- País: un paso con `countries` solo sale en un hub de esos países (`home.setup_steps.applies_to_country`); el país del hub
  se lee con `base.business.country_or_market`, la única lectura de la plataforma: sin país (una demo, el hub de
  ERPlora sin fila) es `MARKET_COUNTRY`, España, el mercado de ERPlora, como lo cuenta VeriFactu
  (`queries.outside_spain` la usa), hub#682.
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
- Campana por reloj: un contador cuya cifra cambia porque pasa el
  tiempo, sin evento (un trabajo que lleva un minuto en cola sin dispositivo vivo), lo dice su módulo en
  `bell_refresh_every` de su `LiveAppConfig` (clave del contador → segundos; la forma de `scheduled_tasks` y
  `approvals`, que también lee y comprueba `base`). `base.E007` (`base/home/bell_counters.py`) exige claves de su propio `bell` y
  segundos enteros desde `MIN_BELL_REFRESH_SECONDS` (30). `base.bell.counters` devuelve
  `refresh_every`, el menor de los contadores que la persona puede ver de las apps encendidas (también a cero: es el
  tiempo el que los sube), y `base/frontend/lib/bell-counters.ts` vuelve a leer `GET /api/home/bell` cada tantos
  segundos mientras la página está a la vista; una lectura más vieja que un resultado vivo llegado mientras tanto se
  descarta, y una que falla deja lo último. Sin `refresh_every`, la campana solo se mueve por eventos. Tests:
  `test_bell_counters.py`, `test_queries_home_bell.py` y `bell-counters.test.ts`.
- El centro de avisos: la campana, la tarjeta de llegada y el panel son de `@erplora/ui` y los monta el shell; el Hub
  solo le da su fuente, `useHubActionNotices` (`base/frontend/lib/action-notices.ts`), en `actionNotices` de
  `createShell`. Cada contador de `base.bell.counters` por encima de cero es un aviso con lo que dice el servidor
  (`id` = su `key`, su icono, su gravedad, su `title` como fila y titular, su `body`, su número, su plazo `due` y una
  acción con su `action_label` a su `route`, sin acción si el Hub no tiene esa pantalla; una `route` que es una
  dirección de otro sitio, `http(s)://…`, es un enlace fuera del Hub y solo sale en el navegador), y `base.setup.status` da
  `base.blocking`, urgente, mientras queda un ⛔ pendiente (`blockingItems` de `lib/home.ts`): «Configurar» a los dos
  primeros pasos que la persona puede hacer, o «Esto lo tiene que configurar un administrador.» si no puede ninguno.
  La pantalla no pone palabras a un contador. La hoja
  de cobro del TPV (`CheckoutSheet.vue`) retiene las tarjetas mientras está abierta (`useQuietActionNotices`).
  Tests: `action-notices.test.ts`, `frontend/main.chrome.test.ts`, `CheckoutSheet.test.ts`; e2e
  `tests/e2e/base-action-center.spec.ts`.
- Lo que dice cada contador de la campana: su `BellCounter` (`live.meta`) declara, todo opcional, la gravedad
  (`severity`: `danger`, `warning` o `info`), el titular (`title`), la frase con la consecuencia (`body`) y el texto del
  botón (`action_label`), textos traducibles rellenados con `%(count)d` y `%(label)s` (el plural, con
  `ngettext_lazy(…, "count")`), y `due`, el campo de la primera fila de su consulta con el plazo (Citas declara
  `earliest`, el comienzo de la cita pendiente más próxima). `base/bell.py` es el único sitio de los valores por
  defecto (atención, «{etiqueta} ({número})», sin frase, «Abrir» y el icono de la campana) y de los dos contadores
  de la plataforma (`FAILED_EVENTS`, urgente, y `PLAN_LIMITS`); `base.bell.counters` los devuelve en el idioma de la
  persona, y un plazo que no es una fecha y hora ISO deja el contador fuera, como un número que no es entero.
  `live.E024` comprueba la gravedad, los textos y que `due` nombre un campo de la respuesta. El esquema vive en
  `base/schemas/bell.py` y sus tipos en `base/frontend/operations-bell.ts`. Tests: `test_bell.py` (también que cada
  contador de los módulos dice sus palabras en inglés y en español y que los tipos siguen al esquema),
  `test_queries_home_bell.py` y los de cada app (`test_integration_home.py` de Citas e Impresión, `test_home_hooks.py`
  de WhatsApp).
- Factura del plan sin pagar (BASE-F117): `base/unpaid_plan.py` da a quien administra el negocio la fila
  `base.payment_pending` de `base.bell.counters` mientras la foto de erplora.com guardada en `Hub.state` dice
  `status: past_due`; su plazo es `suspends_on` de la misma foto, tal cual (el Hub no cuenta los 7 días), y uno que no
  es un instante con zona se queda sin fecha y se anota en el log como `base.unpaid_plan_bad_deadline`. La frase,
  con la fecha en la zona del negocio, cambia cuando el plazo pasa: `refresh_every` pide leer otra vez la campana en
  ese momento (entre 30 s y un día, o antes si una app lo pide). Su `route` son las facturas pendientes del negocio
  en erplora.com (`/dashboard/billing/invoices?business=<id>&status=open`). La foto aplicada
  (`base.hub.state_applied`) ya vuelve a calcular la campana: el aviso llega y se va sin recargar. Tests:
  `test_unpaid_plan.py` y `action-notices.test.ts`.
- Presencia del dispositivo que imprime (misma tarea): la app que
  lleva los dispositivos declara en su `LiveAppConfig` `print_presence`, el nombre de una orden suya cuya entrada lleva
  `device`; `/ws/print` (`base/ws_print/`) la ejecuta con el contexto del dispositivo en su `hello` y en cada `beat`
  mientras imprime para alguna impresora, como mucho una vez cada `PRESENCE_SECONDS` (15 s, medio latido). Si falla,
  se anota en el log y el socket sigue (contesta el latido y sigue sacando trabajos). `base.E006` comprueba al arrancar
  que es una orden de la propia app, con `device`, y que solo una app la declara. Sin declarar, el socket no avisa a
  nadie. Tests: `base/tests/test_ws_print_presence.py`.
- Un panel con `operation` viva (está en un `live.py`) se sigue con `useLive`; si no, se pide una vez
  (`live` en `WidgetOut`). Un panel con `component` monta `apps/<app>/frontend/components/<Nombre>.vue`, que carga
  `frontend/lib/app-components.ts`, la única puerta de `base/frontend` hacia `apps/` (`platform-boundary.test.ts`).
- Tarjetas de Sistema (hub#683, BASE-F39): una app declara en su `LiveAppConfig` `system_cards`, una lista de
  `{"key", "component"}` y, si no la ve todo el mundo, `"permission"`. `base.E015` (`base/home/system_cards.py`) comprueba al arrancar
  que cada clave es única, que el componente es un nombre (nunca una ruta) con su fichero en
  `apps/<app>/frontend/components/` y que el permiso es de la app. `base.system.cards` (viva: la foto y
  encender o apagar una app la re-ejecutan; `GET /api/system/cards`) lista las de las apps encendidas que la persona
  puede ver, y `SystemAppCards.vue` las monta al final de «Uso y plan».
  Lo que dice una tarjeta es de su app. Las puertas de erplora.com a la app de ERPlora de cada sistema
  (`/app/download/<windows|linux|android>/`) van en `hub-home.app_downloads` (`base/spa.py`) para cualquier sesión, y
  `lib/app-downloads.ts` las ofrece solo en un navegador. Tests: `test_system_cards.py`, `test_queries_home.py`, `test_spa.py`,
  `SystemAppCards.test.ts` y `app-downloads.test.ts`.
- La fila de salud del Inicio (hub#573, BASE-F02): una app declara en su `LiveAppConfig` `health`, un diccionario con
  `operation` (una consulta suya cuya primera fila dice `state`: `ok`, `no_signal` o `not_configured`), `params`, el
  `permission` que hace falta para verla, `route` y `action` (dónde se arregla y con qué texto) y `titles`, el texto
  traducible de cada estado y de `unknown`. `base.E021` (`base/home_health.py`) comprueba al arrancar que la consulta
  existe y su salida tiene `state`, que el permiso es de la app, que la ruta empieza por `/` y que hay un título por
  estado, ni uno más. `base.health.list` (`GET /api/home/health`, en `base/api_home_health.py`, que monta
  `config/api.py`; no es herramienta del asistente) ejecuta la consulta de cada app encendida como la persona, solo
  para quien tiene `base.administer_hub` (para el resto, lista vacía: el Inicio la pide para todos) y solo de las apps
  cuyo permiso tiene. Devuelve `{key, app, state, title, action, route}`; `action` y `route` solo con `no_signal` o
  `not_configured`. Si la consulta falla o contesta un estado que no conoce, `unknown` con el título de la app y sin
  acción, y se anota en el log. No es viva: cambia con el paso del tiempo, sin evento. Impresión la declara con
  `printing.device.health` de los tiques, la misma lectura que tiene la tarjeta «Tu impresora»; la Bandeja de WhatsApp,
  con `whatsapp_inbox.channel.health` (el estado del número de la foto de erplora.com). En pantalla la pinta
  `components/HomeHealthRow.vue`, bajo el saludo, solo si la sesión tiene `base.administer_hub` (si no, ni la pide),
  y la vuelve a pedir cuando la ruta vuelve al Inicio: en la pila de Ionic la página sigue montada mientras se va a
  otra pantalla, y `onIonViewWillEnter` solo llega a la página, no a sus piezas. Una lectura que falla quita la de
  antes, que podría decir «lista» cuando ya no lo está. Los colores e iconos de cada estado son `HEALTH_PILLS`
  (`lib/home-health.ts`), los mismos que usa «Tu impresora». Tests: `test_home_health.py`, `test_queries_health.py`,
  `test_api_health.py` (también el tipo `HomeHealthItem` de `operations/home.ts` contra el esquema),
  `apps/printing/tests/test_integration_home_health.py`, `apps/whatsapp_inbox/tests/test_integration_home_health.py`,
  `HomeHealthRow.test.ts`, `home-health.test.ts` y `tests/e2e/home-health.spec.ts`.
- Apps obligatorias por país (hub#997, BASE-F01): una app declara en su `LiveAppConfig`
  `mandatory = {"countries": "all" | ["ES", …], "platform_turns_on": bool}`: dónde tiene que estar encendida y si la
  plataforma puede encenderla sola al alta (Impuestos: `"all"`, sí; VeriFactu: `["ES"]`, nunca, porque ata al negocio
  con la AEAT). `base.E016` (`base/home/mandatory_apps.py`) comprueba al arrancar la forma: `"all"` o códigos ISO 3166-1 alfa-2 en
  mayúsculas sin repetir (nunca una lista vacía, que leería «en ninguno» o «en todos») y `platform_turns_on`
  booleano. `base` la lee con `getattr` sin nombrar ninguna app: `home.mandatory_apps.mandatory_steps` da un paso `base.mandatory.<app>`
  (nivel `functional`, orden 15, ruta `/apps#all`, el icono con que el shell pinta la app: el de su primera entrada de
  menú, `home.shown_modules.shell_icon`, nunca el de la tienda, que `HubIcon` rechazaría) por cada una obligatoria en el país del negocio
  (`country_or_market`: sin país, España) que no está encendida, solo a quien tiene `base.administer_hub`, dentro de
  `base.setup.status`, que ya se re-ejecuta al encender o apagar una app (`APP_EVENTS`). Mientras se crean sus tablas
  (`creating`) el paso sigue: todavía no está encendida. Tests:
  `test_mandatory_apps.py` y `test_queries_home.py` (con apps de paja), `apps/verifactu/tests/test_mandatory_in_spain.py` (dos
  hubs reales) y `apps/tax/tests/test_apps.py`.
  Una vez encendida no se apaga en ese país (hub#997, parte 2; BASE-F14, F16, F23 y F25): `activation.mandatory_on`
  da las obligatorias del país que están `on` (no `creating` ni `failed`, que aún no atan y se pueden dejar), que
  `activation.disabling` nunca apaga en cascada (ni lo que necesitan: siguen queriéndolo) y a las que
  `activation.refusals` da el motivo de `base` (`MANDATORY_OFF`, con el nombre de la app y el del país en el idioma
  de quien pregunta) cuando la app no da uno propio (VeriFactu da el suyo, VERIFACTU-F32). `base.app.disable` y
  `base.app.list` leen el país de la fila del negocio (`Hub.country`); `queries.apps.app_off_refusal` pone el motivo
  propio de la app por delante del de las que la necesitan, porque desactivarlas no la apagaría. `base.app.list` trae
  `mandatory` por app y `country_name` (CLDR, `business.country_name`), y Apps pinta «Obligatoria en {país}» con un
  `StatusPill` de `@erplora/ui` junto al estado. Lo que se va o llega con una app lo dice cada fila de `base.app.list`
  (`along_said`, de `base/app_switch.py`, la misma frase que la tarjeta del asistente), que deja fuera la obligatoria
  encendida. Tests: `test_activation.py` (las reglas), `test_app_activation.py` (409, cascada y dos hubs reales),
  `test_app_switch.py`, `test_assistant_app_cascade.py`, `test_queries_apps.py`,
  `apps/verifactu/tests/test_app_disable.py`, `pages/AppsPage.test.ts` y las e2e
  `tests/e2e/base-app-activation.spec.ts` y `tests/e2e/base-assistant-app-card.spec.ts`.
  Al alta nacen encendidas (hub#997, parte 3; BASE-F63, F14, F01): `activation.born_on(país)` da las obligatorias del
  país que dicen `platform_turns_on`, y `activation.born_apps(país)` les suma lo que necesitan. `provision._prepare` hace
  sus tablas en `migrating` (junto a las del vertical) y, en `seeding`, tras la semilla y antes de la foto del SaaS
  (cuyos bloques son de las apps encendidas), `services.turn_on_born_apps` escribe todas las filas del negocio: esas
  `on` y sin elegir (no gastan `max_apps`), las demás `off`, y olvida lo que la caché guardaba de sus apps. Si la semilla
  ya escribió filas (los hubs locales `a` y `b`, todo encendido) o la preparación se repite, no toca nada. Una demo
  nace igual (sin país: España). Los hubs que ya existían no cambian. «Tus apps» (`queries.home._platform_steps`) no cuenta
  las de `born_apps`: con ellas solas el TPV no vende nada. Tests: `test_activation.py`, `test_queries_home.py` (con
  apps de paja), `base/tenancy/tests/test_provision_apps.py` (dos BD reales: España, Portugal, sin país, una demo, dos
  negocios a la vez y una app de paja obligatoria solo en Portugal), `apps/tax/tests/test_apps.py` y la e2e
  `tests/e2e/base-sign-up-taxes-on.spec.ts`.
- Un panel `chart` cuyas etiquetas son días (`YYYY-MM-DD`: día civil de negocio, sin zona) los nombra con
  `Intl` en UTC, nunca con `new Date(<día>)` en la zona del navegador (`isoDay` y `formatDay` de
  `base/frontend/lib/home.ts`): una semana, por su día de la semana corto (`vie`); una serie más larga, por su
  fecha (`17 oct`); una etiqueta que no es un día se queda tal cual. Encima de las barras salen el día entero y el
  importe (`options.format`) de la barra elegida: la última hasta que se toca o enfoca otra (`tests/e2e/fix-hub-home-chart-iso-day-labels.spec.ts`).
- Un panel `bar-list` cuyo `map` declara `color` pinta cada barra con el color de su fila (`color: row[map.color]`), solo si es un hex `#rgb` o `#rrggbb` (`HEX_COLOR` de `base/frontend/lib/home.ts`):
  lo teclea una persona y va al estilo de la barra, así que cualquier otra cosa (un nombre CSS, `var(…)`, `url(…)`)
  pinta como sin `map.color`. Una barra negativa no lleva color: su rojo gana, porque una alarma pesa más que la
  categoría (las barras de datos de Excel con su relleno de negativo, el formato condicional de Power BI sobre los
  colores de categoría, los umbrales de Grafana sobre su color fijo).
  Un color claro casi no se ve sobre la pista gris: el contraste es el del color que eligió quien lo tecleó. Un
  `chart` no pinta `map.color`.
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
  Una sola regla, `base.home.shown_modules.shown_modules`, para `base.session.me` y los ganchos del Inicio.
- Cada entrada del menú de un módulo (`Nav` de su `apps.py`) declara el permiso que la abre (`permission`, uno de los
  del propio módulo; `live.E025` lo exige). `base.session.me` lleva en `menu` solo las entradas abiertas a la persona y
  solo los módulos con alguna (`_can_see` de `base/queries/apps.py`), y «Mis apps» (`useMyApps` de `@erplora/ui`) sale
  de ese menú; la primera entrada abierta es la que abre una baldosa y el «Abrir» de Apps. `apps` sigue listando todo
  módulo del que la persona tiene algún permiso (`_may_use`): otras pantallas leen de ahí si una app está encendida,
  como el TPV con Suplementos y Menús, que un empleado usa sin abrir esas apps. Toda ruta con sesión de
  `apps/<id>/frontend/routes.ts` cuelga de una entrada de su app (el prefijo de `path` más largo), salvo las de fondo
  (`meta.background`) y las de solo desarrollo; lo comprueba `tests/test_guardrails_navigation.py`, y por eso los
  ajustes de cada app son una entrada más (`settings`, con el permiso que los guarda).
- Qué abre cada rol (skill `market-decision`, 2026-11-21): una entrada de trabajo diario se abre con el permiso que
  usa quien atiende (vender, cobrar, la caja, las mesas, la cocina, las reservas, la agenda, los clientes, fichar);
  una de configurar (ajustes, catálogos de estaciones, zonas, mesas, grupos, etiquetas y campos, series y emisor,
  franjas de reservas) y las apps de configurar el negocio (Impuestos, Tarifas, Suplementos, Menús y combos, Pagos,
  Horarios, VeriFactu, Impresión y Página web) se abren con el permiso que las cambia, no con el de leer que necesita
  el TPV. Automatizaciones se abre con `flow.answer`: ahí contesta cada persona lo que le pregunta una automatización
  (FLOW-F29).

  | Producto | Qué abre el rol más bajo | Fuente |
  |---|---|---|
  | Square | El nivel «Standard» es para cobrar en el TPV (cajeros, baristas, sala); el resto se da permiso a permiso | https://square.com/help/us/en/article/6455-setting-up-your-employees-with-square-for-retail |
  | Toast | El puesto de camarero lleva solo «POS Access»; el de cajero, además, el cajón; la trastienda es aparte | https://doc.toasttab.com/doc/platformguide/adminExampleConfigurationForEnterprises.html |
  | Lightspeed | Roles por zona (TPV y trastienda); solo el administrador crea y cambia roles | https://o-series-support.lightspeedhq.com/hc/en-us/sections/30076369973787-User-and-staff-management |
  | Odoo | El usuario del TPV cobra y lleva la caja, sin informes ni configuración; una app sin derecho no sale en su menú | https://www.odoo.com/blog/business-hacks-1/point-of-sale-user-access-rights-1808 |
  | Fresha | La agenda: solo la suya o la de todo el equipo, según su rol | https://www.fresha.com/help-center/knowledge-base/team/100687-create-permission-roles |
  | Shopify POS | Rol por defecto «Associate», ajustable; la configuración del canal es de quien gestiona | https://help.shopify.com/en/manual/sell-in-person/shopify-pos/staff-management/pos-roles |
  | Clover | El empleado ficha, vende y cobra; lo demás lo activa el propietario | https://www.stitchflow.com/user-management/clover/manual |
  | Business Central | El menú de cada persona sale de su perfil y de sus permisos | https://learn.microsoft.com/en-us/training/modules/users-security-dynamics-365-business-central/5-understand |
  | Booksy | El profesional básico ve y reserva solo en su agenda | https://support.booksy.com/hc/en-ie/articles/16535688940946-How-do-I-manage-staff-permissions |
- `base/spa.py` incrusta `hub-home` (`name` del registro y `plan_url` =
  `SAAS_URL/dashboard/store/plans?business=<id del hub>`) y `widget-list`, `base.widget.list` tal como su consulta viva se lo
  contesta a la persona (sin el permiso del Inicio no va): `WidgetBoard.vue` monta sus paneles con él, así que los
  datos de los paneles van en el mismo flujo vivo que la lista y el Inicio abre un solo `/api/live` por carga
  (sin él lo reabriría al llegar la lista, `net::ERR_ABORTED`, con cada consulta dos veces); manda la respuesta viva.
  Lo comprueban `test_the_shell_embeds_the_persons_panels_so_the_home_opens_one_live_stream` y
  `tests/e2e/base-home.spec.ts` («one live stream»).
- Las piezas de base en el marco (`CHROME` de `frontend/main.ts`: los destellos del asistente, las apps seguidas
  junto al panel y «Mejorar plan») van cada una en su trozo, que la SPA carga a la vez que la primera pantalla, y
  monta cuando han llegado (o han fallado: una que no carga lo vuelve a intentar al pintarse y Vue lo pasa al informe
  de errores de base), y como mucho 3 s (`CHROME_WAIT_MS`): un trozo que la red deja colgado nunca deja la página en
  blanco; monta sin él, lo avisa en la consola y la pieza se pinta cuando llega. Así sus consultas vivas (`base.app.list`) van en el
  mismo `/api/live` de la pantalla. Montadas al llegar su trozo, con un equipo lento (la CPU de la pestaña ×6)
  llegarían más de 150 ms después que las de la pantalla y reabrirían el flujo (`net::ERR_ABORTED`). Se precargan con el cargador del propio componente de Vue: otro `import()` de un módulo ya cargado se
  resuelve en otra tarea, cuando el flujo ya ha abierto. Lo comprueban `frontend/main.chrome.test.ts`, `frontend/main.chrome-wait.test.ts` y
  `tests/e2e/base-home.spec.ts` («when base's chrome arrives late»: cada pieza llega un segundo tarde).
- La SPA responde toda ruta sin URL propia en Django, salvo la que nombra un fichero (`base.spa.NOT_A_FILE`: el
  último segmento lleva extensión, con barra final o sin ella, como `/robots.txt`, `/favicon.ico` o
  `/wp-login.php`): esa no es ruta de la SPA (`spa_route` en `config/urls.py`) y recibe el 404 llano de Django, sin
  la SPA y sin cookie, con sesión o sin ella y acepte lo que acepte. Así la
  web pública sigue «sin cookies» y un buscador no lee HTML como `robots.txt`. Un 404 en `robots.txt` es «sin reglas» (RFC 9309), así que la web de `/` sigue indexable. Es la regla
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
  `/favicon.ico` es un 404, la SPA declara sus iconos, el de la pestaña y el de la pantalla de inicio
  (`LIVE["spa"]["icons"]` de `live.spa`, estáticos de `base` en `base/static/base/icons/`; nunca por CDN).
- Navegador: el tablero se guarda en `localStorage["dashboard-hub"]` y el uso de
  apps en `localStorage["hub-app-usage"]`. La pestaña «Actividad» es el hash `#actividad`.
- Frontend en `base/frontend/` (rutas, catálogos `en`/`es` bajo `base`, componentes y su `lib/home.ts`);
  los destellos y «Mejorar plan» se enchufan en `frontend/main.ts` por `chrome` de `createShell`, y los avisos de la
  campana por `actionNotices`. La ruta `/` de base (`base-home`) gana a la rejilla del shell (`home`).
- Tests: los `base/tests/test_<módulo>.py` de cada módulo de `base/home/`, `test_queries_home.py`, `test_live.py`, `test_api.py`, `test_spa.py`;
  Vitest en `base/frontend/**`; e2e `tests/e2e/base-home.spec.ts` y `base-home-activity.spec.ts`.
- BASE-F13: cada login anota de quién y dónde es su sesión (`base.SessionOwner`, en control junto a las
  sesiones de Django; `CASCADE` con la sesión). `POST /internal/sessions/revoke {user_id, hub_id?}`
  (`base.internal.sessions_revoke` → `base.session.revoke`, firmada como todo `/internal`) borra por ese
  índice, sin descodificar ninguna sesión: las del negocio y las que no anotaron host (de antes de la regla),
  o sin `hub_id` todas, las del admin incluidas; idempotente, un negocio desconocido responde `{ended: 0}` y
  un cuerpo fuera de contrato, 422 `internal.payload_invalid`. La foto (`base.hub.state_apply`) aplica
  `members` en su transacción, sin crear copias locales; de la del negocio propio de ERPlora, nada más que eso
  (`base/tests/test_platform_hub_people.py`). Una baja borra la `Membership` y cierra las sesiones de
  ese negocio; tras el COMMIT se despierta el host (`_wake_open_apps`): el stream vivo re-ejecuta,
  `HubContextBuilder.refresh` ve la sesión borrada (`SessionEnded`, 401) y acaba con `bye`; `/ws/print`
  relee la sesión en cada mensaje. Un rol nuevo cambia la `Membership` y no cierra nada: tras el COMMIT también se
  despierta el host, cada stream re-ejecuta con los permisos del rol nuevo (`refresh` los relee) y
  `base.session.access` (una huella de los permisos, del nombre del rol y de lo aprobable, con `base.view_home`, que
  tienen todos los roles) cambia.
  `AccessFollower` (en `BackgroundChrome`, junto a `AppsFollower`) llama entonces a `sessionChanged()` y, si la
  sesión releída abre o cierra la pantalla de delante, la vuelve a pasar por la guarda (`gateAgain`,
  `lib/app-gate.ts`). Tests: `base/tests/test_session_revoke.py`, `test_hub_state_members.py`,
  `test_queries_sessions.py`, `test_migrations.py` (relleno de 0008); Vitest `AccessFollower.test.ts`; e2e
  `tests/e2e/base-role-change.spec.ts` y, con el SaaS real, `tests/e2e/base-session-revoke.spec.ts`.
- Plantillas y Ajustes › Datos (BASE-F29–F38): el paquete `base/blueprint/` (sin ORM) tiene el formato
  `.blueprint.zip` (`manifest.json` con `format` `erplora.blueprint` y `format_version` 1, más
  `data/<app>.<parte>.json`, más las fotos propias en `media/<nombre>`, WebP de 2 MB como mucho; 20 MB, 100 MB al
  descomprimir y 1 000 entradas como mucho, para que quepan 300 fotos de 60 KB; `BlueprintInvalid.reason`),
  el catálogo (`base/seeds/<vertical>.<idioma>.json`, sus apps = `catalog.verticals.template_apps(vertical)`) y las siete
  partes que viajan (`inventory.category`, `inventory.product`, `service.category`, `service.service`, `table.zone`,
  `table.table` y `customer.customer`, personal: solo en una copia), cada una leída y escrita por las operaciones
  de su app (nunca su ORM; las filas se enlazan por nombre, gh:hub#2626). Lo que ya existe se salta.
- Operaciones (permiso `base.administer_hub`, ruta en `base/api/data.py` bajo `/api/settings/data/`): consultas
  `base.blueprint.list` (con `empty`, viva), `base.blueprint.export` (GET, el fichero en base64),
  `base.import.list` (con `unfinished`, viva) y `base.dataset.list`; órdenes `base.blueprint.inspect` (no escribe;
  orden porque su entrada es un fichero), `base.blueprint.import` (plantilla, fichero o `retry_of`),
  `base.import.undo` y `base.hub.reset` (`dry_run` = el plan; en el negocio propio de ERPlora, 409
  `base.platform_hub_kept`: no se vacía nunca). Eventos `base.blueprint.imported`,
  `base.import.undone` y `base.hub.data_reset`, tras los que se re-ejecutan las consultas vivas del Inicio.
- `base.ImportBatch` (modelo de hub, migración `0009`) guarda cada importación: informe, filas creadas por parte
  (lo que deshace), origen y versión de la plantilla (lo que reintenta).
- Una plantilla espera a sus apps (hub#609; BASE-F31–F33, F38): una app `creating` queda en su informe como `waiting`, y
  esa fila de `ImportBatch` es todo el estado (sin columna, ni cola, ni migración; el idioma de quien cargó va en
  `report["language"]` mientras espera). Lo que le toca entra en la misma transacción que la enciende:
  `base.app.activation_settle` (o `base.app.enable`, si tenía las tablas) llama a `services.blueprints._load_what_waited` →
  `blueprint.loads.finish_waiting`, que reusa `apply`, con su orden y sus operaciones, en el hub activo. Si el worker muere, no
  ha pasado ninguna de las dos cosas y el siguiente pase, o el barrido de las visitas del worker (`base.hub_visits`) si se perdió el aviso, hace las
  dos: por eso sobrevive a un reinicio sin nada más. Cómo va la preparación (`setup_failed`) nunca se escribe: se lee de
  la fila de la app al describir la carga (`describe_load`). Lo que corta la espera: desactivar la app, deshacer la
  carga, reintentarla (la nueva toma el relevo) y restablecer el negocio (`services.blueprints._stop_waiting`). Un fichero no se
  guarda, así que no espera. Una carga que rompe deja la app encendida y su fila en `failed`: una app no se queda sin
  encender por sus datos. `base.import.list` se re-ejecuta también con `APP_EVENTS`, y `ImportPanel` y
  `BlueprintCardPending` siguen esa lista. Tests: `base/tests/test_blueprint_waits_for_apps.py`, con dos BD reales y el
  worker de verdad; e2e `tests/e2e/base-template-waits-for-apps.spec.ts`.
- Frontend: `base/frontend/pages/SettingsPage.vue` (`/settings`, pestaña en el hash `#data`; `/import` y `/export`
  llevan aquí), `components/data/*` y `lib/data.ts`; la tarjeta `components/BlueprintCard.vue` («Ahora
  no» en `localStorage["hub-blueprint-card-dismissed"]`). Tests: `base/tests/test_blueprint.py`,
  `test_services_data.py`, `test_queries_data.py`; Vitest en `base/frontend/**`; e2e `tests/e2e/base-data.spec.ts`
  (vacía lo que trae una plantilla por las operaciones de cada app antes de empezar).

- **Apps (BASE-F14…F28).** `base/entitlement.py` aplica el derecho de uso (PLAN §20.4–§20.5): un
  módulo con `premium = False` siempre lo tiene; uno con `premium = True` necesita su id en `modules[]` de la última
  foto (`Hub.state`, `source` `plan` o `purchase`, con `valid_until` leído contra el reloj) o el de un módulo que lo
  requiere (cierre por `requires`, que solo conoce el Hub); un slug sin módulo se ignora y queda en el log; un hub de
  demo tiene todos. Lo bloqueado: 402 `app_entitlement_blocked` en toda operación de esa app
  (`LIVE["operation_database"] = base.entitlement.operation_database`, que delega en el de la tenencia), fuera de
  `base.apps_on.active_apps` (relay e Inicio), `off` y sin menú en `base.session.me`. Sin ningún módulo de pago en el
  despliegue (hoy) no se lee nada. Tests: `base/tests/test_entitlement.py` (dos hubs, demo, fin del derecho, 402).
- `base.app.list` (`GET /api/apps`, `base.view_home`, viva con `base.hub.state_applied`): los módulos de
  `home.shown_modules.shown_modules` desde su `LiveAppConfig` (nunca el catálogo del SaaS), con `right`, `state`, `path` (primera
  entrada del menú si la persona ve la app), `icon` (el de la primera entrada del menú, el que pinta el shell, como el
  lanzador y «Mis apps»: el `icon` del módulo es el de la Tienda, horneado aparte, y `HubIcon` rechaza un nombre no
  registrado, que dejaba la pantalla en blanco), `requires` (cierre) y `required_by`, y `store_url` =
  `SAAS_URL/dashboard/store/modules?business=<id del hub>`. La foto se aplica como la plataforma (`/internal`): tras su COMMIT,
  `base.hub.state_apply` avisa también al canal del propio negocio (`base/tests/test_hub_state_wake.py`), que es
  donde escuchan las consultas vivas que la siguen. `base.plan.usage` (`GET /api/system/plan`, `base.administer_hub`,
  viva con la foto): `plan.max_users`/`max_devices` de la foto (0 = sin tope) frente a las `Membership` activas del
  host; los dispositivos, sin cuenta. Tests: `base/tests/test_queries_apps.py`.
- `base.app.get` (`GET /api/apps/detail?app=…`, `base.view_home`, no es viva; hub#539): qué app del negocio nombra
  `app`, como la dice la persona (`queries.apps.find_app`): su id; si no, la que se llama exactamente así en cualquier idioma
  del Hub, sin mirar mayúsculas ni acentos («reservas» es Reservas, nunca Reservas online); si no, la única con una
  palabra de su nombre que empieza así («booking»). Devuelve `id`, `name` y `summary` (en el idioma de quien pide; para
  qué sirve, el `summary` de su config, como en Apps), `state` como lo dice la pantalla de Apps: `on`, `off`, `blocked` (de pago sin derecho de uso), `creating` o `failed` (mientras la BD
  del hub recibe sus tablas), y `mandatory`, como `base.app.list`: el país del negocio la exige y, una vez activada,
  no se desactiva. La tarjeta de `base.app.enable` de una así añade el dato `mandatory` con el motivo de Apps
  (`activation.mandatory_off`, el mismo `MANDATORY_OFF`). Tests: `base/tests/test_assistant_mandatory_apps.py`. Si no es de ninguna, 404 «Ninguna app tiene ese nombre o identificador.» (la plataforma no
  es una app); si vale para varias («reserva»), 409 `base.app_ambiguous` nombrándolas en el idioma de quien pide.
  `base.app.enable`, `base.app.disable` y `base.app.retry` resuelven `AppChangeIn.app` con la misma `find_app` y declaran
  `"check": "base.app.get"` en su `ai=` (hub#542): el asistente la lee antes de la tarjeta, y un nombre de varias apps o
  de ninguna no saca tarjeta, vuelve al modelo, que pregunta cuál. `AppChangeIn.app` la marca `REFERS`, así que la
  tarjeta nombra la app por su nombre entero, nunca por su id. Tests: `base/tests/test_app_activation.py`,
  `test_app_activation_tables.py` y `test_api.py`.
- Las apps no activadas en el asistente (BASE-F24 paso 6, hub#2178; `base/assistant/apps_not_on.py`): el catálogo de
  un turno sigue siendo solo de las apps activas. `named` nombra una app no activada de `home.shown_modules.shown_modules` cuando las
  palabras de la petición abierta o las búsquedas del modelo dicen su nombre en el idioma de la persona (`_names`: las
  raíces de su `verbose_name`, comparadas con las palabras tal como se dicen, sin el vocabulario de `live`, que haría
  de «precio» una palabra de Tarifas) y tiene una herramienta en los `PLACES` puestos de ese turno contra el catálogo
  que la persona tendría con todas las apps encendidas (`relevance.relevant`); como mucho `NAMED` = 3, la mejor
  primero, con lo que lee `base.app.get` (nombre, estado y `summary`), tras lo que se sabe del negocio. Si no se dice
  ninguna, no se clasifica nada más. A quien tiene el permiso de `base.app.enable` se le ofrece esa herramienta antes de
  la búsqueda (`with_switch`, solo si alguna está `off`), sin mover ninguna de las ofrecidas. Tras una escritura de
  `SWITCHES` (encender, apagar o reintentar), el resto del turno lee las apps de sus filas, aún sin COMMIT
  (`activation.changing`): la ronda siguiente ofrece las herramientas de la app encendida y ya no las de la apagada, y
  no nombra ninguna app (lo que está activado se acaba de decidir). Medido con el tokenizador o200k_base: las frases de
  uso diario de una peluquería y un restaurante no nombran ninguna (0 tokens más); las seis de la issue, de 145 a 513
  más. Tests: `base/tests/test_apps_not_on.py`.
- «Uso y plan» (BASE-F40, hub#603). `SystemUsage.vue` lee `base.plan.usage` y, aparte,
  `base.assistant.usage`, que espera a erplora.com; `lib/plan-usage.ts` saca de ahí la línea de arriba y las filas, sin
  estado. La fila de la campana (`base.plan_limits` de `base.bell.counters`) la calcula `queries.usage._plan_motives`, sin
  preguntar a erplora.com, con los mismos umbrales. Una app dice qué incluye su plan declarando `plan_meter` en su
  `LiveAppConfig` (`home.plan_meters.plan_meters`, comprobado por `base.E013`): `base` no lee tablas de otra app. `base/meter.py`
  cuenta en la memoria de cada proceso que atiende peticiones y lo vuelca cada 60 s y al salir
  (`services.usage.activity_recorded`, `services.usage.people_seen`): peticiones en `HubDatabaseMiddleware`, personas en
  `HubContextBuilder.from_request`, pico en `Limiter.take`, fuera de su lock. «Sin hueco» solo cuando llega a un cliente
  (`HubBusy.reached_client`, gancho de `live`): nunca un reintento del ejecutor vivo. Solo lo arranca `config/asgi.py`: lo
  que hace el worker no es la petición de nadie. Una lectura suma lo que su proceso aún no ha volcado (`meter.unflushed`).
  El tope es el efectivo (`PGBOUNCER_MAX_DB_CONNECTIONS`, `limits.plan_limits`), también en el semáforo. El hub de
  ERPlora (`Hub.is_platform`) no tiene plan y su foto solo trae a sus personas: es su fila la que le da
  `limits.PLATFORM`, 6 a la vez dentro de ese tope y `statement_timeout` de 30 s, con la misma función en el semáforo y
  en esta pantalla (`limits.hub_limits`), y nunca se le ofrece ampliar (`limits.bigger_plan_gives_hub_more`). `known` sigue
  en falso porque no hay plan que leer, y `platform` dice que no lo habrá: la pantalla lo cuenta en vez de prometer uno.
  Tests: `base/tests/test_meter.py`, `test_meter_requests.py`, `test_plan_usage_figures.py` y
  `test_platform_hub_no_plan.py`, y `SystemUsage.platform.test.ts`.
- Una transacción que va a esperar una respuesta de fuera lo dice con `base.operations.allow_idle_wait(segundos)`:
  `SET LOCAL idle_in_transaction_session_timeout` en el alias activo (`base.tenancy.connections.allow_idle_wait`), solo
  para esa transacción (PgBouncer en modo transacción); todas las demás siguen con los 30 s del clúster. Test:
  `base/tenancy/tests/test_limits.py`.
- Pantallas: `base/frontend/pages/AppsPage.vue` (`/apps`, pestañas por hash `#all`/`#paid`;
  reglas en `lib/apps.ts`), `SystemPage.vue` (`/system`, cinco pestañas por hash: ver «Sistema» abajo) y `AppGatePage.vue`, que monta la guarda de `lib/app-gate.ts` (`frontend/main.ts`: cada ruta
  de `apps/<id>/frontend/routes.ts` lleva `meta.app`; la página va por nombre en la misma dirección, como `NotInAppPage`
  del shell, y se comprueba también la primera dirección antes de montar). Pinta `AppBlockedPage.vue` cuando la app no
  está `on` en `base.session.me` y `NoAccessPage.vue` («Sin acceso», BASE-F118) cuando la entrada de menú más larga de
  la app que cubre la dirección está en `locked` de la sesión (las rutas de las entradas `Nav` que la persona no
  abre); la decide `gateVerdict`, nunca la lista `apps`, que lleva toda app de la que la persona tiene algún permiso.
  Una ruta de base, sin `meta.app`, la juzga con el `permission` de la entrada de `SIDEBAR` (`lib/sidebar.ts`) más
  larga que cubre la dirección, segmento a segmento; la que ninguna cubre (el Inicio, «Mi perfil») se abre.
  Los nombres salen de `base.access.grantors` (`base/queries/access_rights.py`): quien puede subirle el rol en
  erplora.com, solo el nombre.
  «Mejorar plan» y la Tienda, solo con `useMayBuy` (`base/frontend/lib/plan-link.ts`). e2e:
  `tests/e2e/base-apps.spec.ts` y `tests/e2e/base-app-activation.spec.ts`.
- Activación por negocio y tope del plan (hub#256, PLAN-HUB §9): `base.AppActivation` (por `host`, la dirección web, que
  al cambiar se lleva las apps como estaban: `base.services.address_change`; un negocio nace con todo
  apagado, también una demo, salvo las obligatorias de su país que la plataforma
  enciende sola, con sus filas escritas al nacer (Impuestos, hub#997); un hub sin filas lo tiene todo apagado; los hubs
  anteriores a la migración `base/0017` conservan todo encendido con sus raíces elegidas, y los locales `a`/`b` salen así de `seed_local_hubs`; el hub de
  ERPlora y el ámbito del worker lo tienen todo encendido siempre, `activation.is_platform`; `base/activation.py`).
  `base.blueprint.import` enciende antes de cargar las apps que lista el manifiesto, cada una elegida, por
  `base.app.enable` y primero lo que necesita cada una (tope, derechos y evento), salvo las que la plataforma enciende
  al darse de alta (`activation.born_on`: Impuestos), que van al final y llegan sin elegir con las que las necesitan;
  la que ya estaba encendida se queda como estaba, y los negocios montados antes con una plantilla o una copia las
  tienen elegidas desde la migración `base/0033`. La que no puede encender sale `inactive` con su `reason` en el
  informe. La que nunca se enciende en este negocio (`can_enable`) no se promete en la revisión (`inactive`, no `turns_on`)
  y, sin filas suyas en el blueprint, no deja la carga a medias ni ofrece un reintento que no cambiaría nada (hub#694). `base.app.enable`/`base.app.disable`
  (`POST /api/apps/enable|disable`, `base.administer_hub`: cierre de `requires`, 409 `base.app_required`, negativas
  `can_disable` y `can_enable` del `LiveAppConfig` → 409 `base.app_vetoed`, que `base.app.list` adelanta en el `refusal`
  de cada fila, con cada gancho una sola vez por lista (hub#618, hub#694), y la de una app que otra en marcha necesita
  dice el motivo de esa otra, nunca «Desactiva antes» (`app_off_refusal`, hub#619), 402 `base.app_limit_reached` con `max_apps`/`enabled`,
  nunca para una app que el país del negocio exige, `mandatory_in`; bajar de plan no apaga nada). Una app apagada da 404 `app_inactive` y sale del menú, del relay y del asistente
  (caché `base.apps_off:<host>`, olvidada al COMMIT). Una app cuyas tablas la BD del hub aún no tiene (`Hub.schema_apps`;
  las plantillas traen las de todas las portables, así que solo pasa con la que llega con un código posterior) da 202
  `creating` (el OpenAPI documenta 200 y 202 con el mismo esquema, hub#705): el worker las crea (`_activations`, `base.app.activation_settle`) o la deja `failed` con `attempts`,
  `last_error` y `next_attempt_at` (1, 5 y 15 min, luego cada hora), y `base.app.retry` la vuelve a pedir (BASE-F21, F22;
  hub#601). Fuera de una operación (un `events.py`, el admin, una tarea) tocar un modelo de esa app da el mismo 404: el `TenantRouter`
  lanza `AppNotCreated` antes de mandar SQL (hub#608). Lo decide `base.activation.has_tables`: lo que lista la fila que el
  contexto ya tiene pasa sin consulta ni caché; lo que no lista se pregunta a control por `base.apps_created:<host>`,
  olvidada con `activation.forget` y al acabar `ensure_schema`, porque esa fila puede ser de antes de crear las tablas. Una
  fila sin confirmar (sin `base`) no niega nada, y el alias `__ddl` del migrador nunca pregunta. El índice del admin deja
  fuera esas apps y su página vuelve al índice con el aviso. No cubre SQL crudo ni el JOIN de un `select_related`. Borrar un registro del que cuelga una de esas apps lo borra con normalidad: el `Collector` de Django recorre las relaciones con `.using()` y no pasa por el router, así que `base.tenancy.deletion` deja fuera del recorrido las de una app sin tablas según esa misma lectura, solo en el alias del contexto activo, nunca en `__ddl` ni en otro negocio. Una app con tablas conserva PROTECT, CASCADE y SET_NULL, y si la lista va por detrás de una tabla recién creada, la clave ajena de la BD rechaza el COMMIT (hub#778). `last_error` no llega a la pantalla, que dice «No se ha podido activar»: se queda en la fila, y el
  evento `base.app.activation_failed` lleva su código. La sesión da `activating` a la que se prepara y `off` a la que falló, y ninguna
  de las dos sale en el menú. El veto de VeriFactu está en su app (VERIFACTU-F32). Los ganchos `can_disable(ctx)` y `can_enable(ctx)` corren en `translation.override(ctx.language)`: un
  `gettext` a secas ya responde en el idioma de quien pide (gh:hub#2595). En Apps, la negativa (409 o cualquier otro
  fallo al cambiar) es un `InlineFeedback` `apps-refused` que se queda hasta cerrarlo o hasta el siguiente cambio,
  nunca un toast (gh:hub#2594). F18, F19 y F23–F25 los prueba la e2e
  `tests/e2e/base-app-activation.spec.ts`, en español y en los 3 tamaños.

- **Sistema (BASE-F39…F47).** Pestañas por hash en `base/frontend/lib/system.ts` (`#resources`, `#plan`,
  `#updates`, `#events`, `#logs`; `#backups` → `/settings#data`, la pestaña «Datos y copias» de Ajustes). La pantalla
  no tiene vista para quien no administra el negocio: la guarda le dice «Sin acceso» antes de montarla (BASE-F118).
- Consultas (`base/queries/`, `base.administer_hub`, `ai=`): `base.system.status` (`GET /api/system/status`: motor,
  `shared`/`own` según `Hub.db_name`, `version` y `released_at` de `base/system.py`, que lee `APP_VERSION` y
  `APP_RELEASED_AT` del entorno del despliegue; sin ellos, `dev` y `null`), `base.event.list` (`GET /api/system/events`:
  las 50 últimas `live.OutboxEvent` del host con su `EventDelivery` resumida y traducida; nunca el `payload`) y
  `base.failed_event.list` (`GET /api/system/failed-events`: las `EventDelivery` `dead` del host, hasta 100, con
  `retryable` = su app está en `base.apps_on.active_apps`). Las tres filtran por `scope_kind`/`scope_key` del contexto
  (test de dos hubs en `base/tests/test_queries_system.py`).
- Novedades (BASE-F116): `base.release_note.list` (`GET /api/system/release-notes`, `base.view_home`,
  `database=False`, `ai=`) devuelve una página (`limit` hasta 100, 20 por defecto; `offset`; `total`) de las notas que
  trae la imagen, la más reciente primero, en el idioma de la persona (sin él, en inglés). Cada nota es un fichero de
  `base/release-notes/` llamado `<AAAA-MM-DD>-<nombre-en-minúsculas>.toml` (el día en que el cambio llega a los
  negocios), con `kind` (`new`, `improved` o `fixed`) y una tabla por idioma del despliegue con `title` (hasta 80
  caracteres) y `body` (hasta 400), en texto llano. `base/release_notes.py` las lee una vez por proceso (con `DEBUG`, en
  cada llamada) y rechaza la que no lo cumple; `base/tests/test_release_notes.py` lee todas las del repositorio, así
  que una nota rota no llega a la imagen. Se escribe una por cambio que nota un negocio (algo nuevo, una mejora o un
  arreglo que se ve), en su lenguaje: nunca el título del commit ni los cambios internos. La pantalla
  (`base/frontend/components/SystemReleaseNotes.vue`) la pide una vez con la página por defecto, y otra vez si la
  persona cambia de idioma, porque el Hub contesta en el suyo.
- Comandos (`base/services/`, `base.administer_hub`, `ai=` con `risk`), con el id en el cuerpo:
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
- Lo que una reacción graba como el sistema al contestar un aviso cuyo autor se pasa (`base.relay.carried`) lleva ese
  autor, de primera y de segunda mano; lo que graba como alguien propio conserva el suyo. Se pasan el de una
  recuperación (`copy_recovery:<id>`, BASE-F114) y los que una app declara en `carried_actors` de su `LiveAppConfig`
  (`<label>:` o `<label>_<nombre>:`; hoy Automatizaciones, para que su guarda de bucles siga una cadena a través de
  otra app). Una declaración que no es de la propia app (vacía, `system`, la de otra) la rechaza `base.E017` al
  arrancar y no se usa. Tests: `base/tests/test_relay_carried.py`.
- Lo que una reacción o una tarea programada deja para después del COMMIT y espera a la red va por
  `base.outbound.after_commit(fn, *args)`: `THREADS` (4) hilos del
  worker en el contexto de BD de la operación que lo pidió (`base.tenancy.context.use_again`), `QUEUED` (1000) en
  espera, sin encolar dos veces lo que ya espera; `release()` suelta la conexión antes de esperar a la red; al parar, el
  worker da `OUTBOUND_GRACE_SECONDS` (15) a lo que corre y tira lo que espera. Un trabajo puede perderse: solo vale para
  lo que su app recupera sola (reclamo con plazo y barrido, como `flow.run.claim_call`). En los tests corre en línea
  (`conftest.py`); la marca `outbound_threads` da los hilos de verdad. Tests: `base/tests/test_outbound.py` y
  `apps/flow/tests/test_relay.py`.
- Un trabajo corre en el contexto de quien lo pide, fijado al pedirlo (`Job` inmutable): cada BD solo guarda sus
  filas, la operación de otro hub se rechaza (`HubContextMismatch`) y ningún trabajo entra jamás en la BD de otro hub
  (hub#1053).
- Informe de errores de la pantalla: `base/frontend/lib/error-report.ts` (`error`, `unhandledrejection` y
  `app.config.errorHandler`; `navigator.sendBeacon`, el mismo error una vez cada 30 s, 50 recordados), instalado en
  `frontend/main.ts`. No envía los avisos del navegador de `BROWSER_NOTICES` («ResizeObserver loop completed with
  undelivered notifications.» y la forma vieja «ResizeObserver loop limit exceeded»): solo un `error` de `window` sin
  `Error` detrás (traza vacía) con el mensaje entero, como `ignoreErrors` de Sentry o las reglas de TrackJS; otro mensaje
  que nombre ResizeObserver, o las mismas palabras lanzadas por la app, sí se envían (`error-report.test.ts`, «the
  browser notices that are no error»). `POST /api/error-report` (`base/error_report.py`, fuera de ninja: un beacon no lleva CSRF) exige
  sesión, 30 por minuto y persona (`base.rate_limited`), cuerpo ≤ 16 KB y JSON, y escribe una línea `frontend.error
  {json}` en ERROR del logger `base.error_report` (host, usuario, pantalla, mensaje y traza recortados); el logging
  va a la consola y de ahí a CloudWatch (`config/settings/observability.py` `LOGGING`). Tests: `base/tests/test_error_report.py`,
  `base/frontend/lib/error-report.test.ts`.
- Pantalla: `SystemPage.vue` con `SystemUsage.vue`, `SystemRelease.vue`, `FailedEvents.vue` (descartar en
  `ConfirmDialog` con motivo; reenviar todos con `confirm`) y `SystemLog.vue` (`DataTable` con tarjetas en el móvil).
  e2e: `tests/e2e/base-system.spec.ts` (tres tamaños, dos hubs, campana → `#events`).

- **Ajustes del negocio (BASE-F48…F51).** `base.business.get` (`GET /api/business`, `base.view_home`,
  viva con `base.hub.registered`): la fila del registro del ámbito, la que manda el SaaS por `PUT /internal/hubs/{id}`
  (nombre, país, zona e idioma, HUBS-F15), con la moneda del país (`base/business.py`: CLDR por Babel; sin país,
  `EUR`), los nombres en el idioma de la persona y `settings_url` = `SAAS_URL/dashboard/businesses/<id>/settings` (vacío en una
  demo). El registro se aplica como la plataforma: tras su COMMIT, `base.hub.register` avisa también al canal del
  propio negocio (`base/tests/test_business_live.py`). El Hub no guarda ni cambia nada de esto y no hay almacén
  clave/valor de ajustes: cada ajuste es de su dueño (país, zona e idioma en el registro; territorio en Impuestos, TAX-F11; emisor en Facturación, INVOICE-F21; la moneda, la del país). El hub
  propio de ERPlora (`PLATFORM_HUB_SLUG`; una fila del registro con BD propia, de `create_platform_hub`)
  contesta el negocio de ERPlora, su emisor:
  `PLATFORM_ISSUER_LEGAL_NAME` y `PLATFORM_ISSUER_COUNTRY` con la moneda de ese país, la zona y el idioma del despliegue,
  `demo` falso y `settings_url` vacío (nada suyo se cambia en erplora.com, y `BusinessPanel` dice en todos los roles que
  esos datos los pone ERPlora en su servidor, sin enlace), con fila o sin ella; su host es el de
  `PLATFORM_HUB_SLUG` (`erp`), el único nombre reservado que se sirve (`base/tests/test_platform_hub_host.py`). La moneda
  que cobra cada app (BASE-F50, hub#577) es
  `base.operations.business_currency(scope)`: la de `base.business.get` leída como la plataforma (`system_context`;
  una API key solo tiene los permisos de lo que cobra) y, en un ámbito que no es de ningún hub, su `NotFound`, nunca un
  `EUR` por defecto (`base/tests/test_business_currency.py`). Un importe con su moneda lo escribe el servidor solo con
  `base.business.money_text(cents, currency)` (unidad menor → texto con los decimales de la moneda, en el idioma activo
  o el que se le pase), igual que `Intl.NumberFormat` en el navegador: el patrón de CLDR por Babel más el espaciado de
  moneda de CLDR, que Babel no aplica («PLN 15.50» con U+00A0, nunca «PLN15.50»; «€15.50»; «15,50 PLN»), y
  `grouped=False` para la exportación que su importación relee (flujo money-text). Lo usan el aviso y el tique de
  Ventas, el documento de Facturación, la exportación de Inventario, la web pública y los huecos de las aprobaciones;
  `tests/test_guardrails_money.py` no deja llamar a `format_currency` ni a `get_currency_symbol` de Babel fuera de él.
  Ventas, Facturación, Inventario, Tarifas, Impresión, Pagos y
  Carrito y pago la leen con `base.operations.business_currency(ctx.scope)`, sin copia propia (las `business_currency(ctx)`
  de `apps/sale/queries/business.py` y `apps/cart_checkout/queries.py` solo la llaman); en pantalla, Pagos, Carrito y pago,
  Clientes, Menús y combos, Citas y la vista previa de Reserva online la leen con `useBusinessMoney` (ninguna fija
  una moneda; la ficha de prueba de `base.business.get` es `base/frontend/__tests__/business.ts`). Pantallas: `SettingsPage.vue` (pestañas por hash `#business`, `#tickets`,
  `#data`; `#tax` abre Negocio; `lib/settings-tabs.ts`) y `components/settings/{BusinessPanel,TicketsPanel,SettingsRow}.vue`.
  Tests: `base/tests/test_business.py`, `test_queries_business.py`, `test_business_live.py`; e2e
  `tests/e2e/base-settings-business.spec.ts`, con el Hub y el SaaS reales.
- **La hora del negocio** (hub#687): la zona la lee un solo sitio, `base.business.business_zone()`: la del hub en el que se
  trabaja (`control.Hub.timezone`, la manda el SaaS), la del despliegue en la plataforma o si no tiene una que Python
  conozca (`zone_of`); sin contexto, `HubContextMissing`, como un modelo de hub. La usan la tarjeta del asistente, los
  avisos del Inicio y los textos de las automatizaciones (`base.home.device_notices.moment`), el CSV de autorizaciones y las apps; una
  lectura nueva del reloj del despliegue la para `tests/test_guardrails_zone.py`. En pantalla, `useBusinessZone`
  (`base/frontend/lib/zone.ts`), que también siguen Fichajes, Tareas y la bandeja de WhatsApp (hub#779). Las fechas de
  la factura, el día y el número de una venta, el «hoy» de Impuestos y las horas de VeriFactu (la de generación de cada
  registro, con su huso) van juntos en ese reloj, porque llegan a un registro fiscal (lo congela
  `tests/test_guardrails_fiscal_clock.py`). Solo Ajustes › Negocio del hub de plataforma dice a propósito la zona del
  despliegue.
- **Acceso (BASE-F52…F71).** Modelos de hub en el paquete `base/models/`: `TrustedDevice` (el dispositivo:
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
  de esa persona. La entrada deja la cookie del idioma de la persona (gh:hub#2639). Cada freno guarda en la caché la
  cuenta y el final de su ventana, y los lee y los olvida en una sola llamada: su clave va entre llaves
  (`base.throttle:{limit:pin:<hub>:<persona>}` y `…}:until`) para que el clúster de Valkey de AWS las guarde en la
  misma ranura. Sin eso el clúster rechazaba la lectura (`CROSSSLOT`), el freno se apartaba y el pinpad aceptó
  nueve PIN erróneos seguidos en producción (hub#440).
- `way_in` (sin sesión, pidiendo HTML): al Acceso (`/login`) si el dispositivo ofrece el pinpad
  (`queries.access.pin_door_open`), con `notice=ended` si llegó la cookie de una sesión que ya no existe, o si otra entrada
  cerró la suya (`notice=device_limit`); si no, el salto de siempre a la entrada de erplora.com, que devuelve dentro
  mientras su sesión vive (BASE-F13, `tests/e2e/helpers-login-hub-session.spec.ts`). `/auth/logout` en una caja con
  pinpad vuelve a `/login`.
- Operaciones (`base/queries/`, `base/services/`; rutas en `base/api/access.py` y `frontend/generated/operations.json`):
  `base.access.door` (sin sesión: la cookie decide; nunca da caras a quien el PIN no dejaría entrar, ni correos:
  `queries.people.face_name`, gh:hub#2536), `base.access.faces` (viva, `base.view_home`), `base.pin.set` (freno
  `PIN_CHANGE_LIMIT`, 30 en 1 h; 409 `base.pin_taken`, 403 `base.pin_current_wrong`), `base.device.current` y
  `base.device.mode_set`, `base.device.list|rename|remove|prune` y `base.access.settings|settings_update`
  (`base.administer_hub`), y `base.profile.get|update|preferences_set|avatar_set|avatar_remove` (`preferences_set` cambia solo lo
  que se le manda, y sin el idioma no deja su cookie; la foto, en `avatars/` del almacén del hub, servida solo a una
  sesión: `AVATARS_FOLDER` de `base/media.py`). Eventos
  `base.pin.set`, `base.device.mode_changed|renamed|removed|pruned`, `base.access.settings_changed` y
  `base.profile.updated`; `base/live.py` sigue con ellos las caras, los dispositivos, el dial y el perfil.
- El pase a erplora.com (BASE-F11; ACCOUNTS-F29 del SaaS): `base.saas_pass.create` (`base/services/`, `ai=INTERNAL`:
  en un chat se quedaría en su historial; `database=False`) firma al pulsar, nunca en el HTML de `hub-home`, donde
  caducaría en un minuto y lo leería cualquier script: `signing.dumps({user, hub, next, nonce}, key=INTERNAL_SHARED_SECRET,
  salt="erplora.hub-pass.v1")`, y devuelve `SAAS_URL/hub-pass/?pass=…`. Solo en una sesión abierta con la cuenta
  (`_session_account`; si no, `base.saas_pass_needs_account`: nunca PIN, placa ni demo); `next=business`, además, con
  `base.open_management` (`base.saas_pass_needs_management`); `next=plan`, nunca en el hub de ERPlora (409
  `base.saas_pass_no_plan`); sin secreto, 503 `base.saas_pass_unavailable`, porque el
  firmante de Django caería en `SECRET_KEY`. No se consulta al SaaS (PLAN-SAAS §2) y el pase no va a ningún log.
  `base/frontend/lib/saas-pass.ts` (`useSaasPass`) es la segunda puerta de salida del Hub: abre `about:blank` dentro del
  clic (tras un `await` el navegador la bloquea), le quita `opener` y le pone la dirección al llegar; en la app instalada
  la saca por `openExternalLink`. Un error u 8 s sin respuesta (`SIGN_TIMEOUT_MS`: `client.api.call` no tiene tiempo
  límite) abren la dirección de siempre, que sigue en el `href`. Todo «Mejorar plan» con pase es una sola pieza,
  `base/frontend/components/PlanUpgradeLink.vue` (`plan`; hub#853): recibe la dirección (`url`), dice «Mejorar plan» o lo
  que su sitio le pone dentro, y quien la coloca decide su clase y `data-testid`. Si sale lo decide una sola regla,
  `useMayBuy` de `base/frontend/lib/plan-link.ts`: en la web y con `base.own_business`, porque en erplora.com solo el
  propietario compra (`usePlanLink` la aplica a la dirección de `hub-home`; `canUpgrade` del asistente y los enlaces a
  la Tienda de `AppsPage` y `AppBlockedPage`, también). Las direcciones de los planes y de la Tienda las da
  `base/saas_store.py`, vacías en el hub de ERPlora (`platform_hub.is_platform_slug`): sin dirección no sale ninguno
  (`base/tests/test_saas_store.py`, `test_platform_hub_no_plan.py`). La colocan
  `UpgradePlanLink` (pie del menú, con su icono), `SystemUsage`, `PeopleList`, `AppsPage` y la Bandeja de WhatsApp
  (`InboxPage`, `MessageComposer`, `ChannelSettings`, con su «Mejorar el plan»); su test prohíbe que un `.vue` vuelva a
  escribir a mano `openSaasPass('plan', …)`. Además usan `useSaasPass` `ManageLink` (`business`) y `openPlan` de
  `lib/assistant-hub.ts`, que recibe el clic de «Mejorar plan» del panel de `@erplora/ui` (`plan`) y pasa el cliente del
  panel a `useSaasPass`, porque ese clic corre fuera del `setup` de un componente. Tests: `base/tests/test_saas_pass.py`,
  `lib/saas-pass.test.ts`, `components/PlanUpgradeLink.test.ts`, `lib/assistant-hub.test.ts`,
  `frontend/external-links.test.ts`; e2e
  `tests/e2e/base-chrome.spec.ts`, `tests/e2e/base-assistant.spec.ts` y `tests/e2e/whatsapp-inbox-plan-cap.spec.ts`.
- `base/spa.py` incrusta en `hub-home` `access` (`credential`, `switch_user`, `idle_minutes`) y `preferences` (la
  apariencia propia); `plan_url` y `account_url` solo en una sesión abierta con la cuenta
  (gh:hub#2506), y `manage_url` (`SAAS_URL/dashboard/businesses/<id del hub>`, BASE-F11) además solo con el permiso
  `base.open_management` (propietario y administrador por `base.*`; el encargado, a mano en `base/apps.py`: no tiene
  `base.administer_hub`). Lo que es solo del propietario es `base.own_business` (`OWNER_ONLY` de `base/permissions.py`):
  `permissions_of_role` da al propietario todo lo declarado y al administrador todo menos eso, y ninguna app lo da a
  otro rol (`base/tests/test_permissions.py`). Lo exigen `base.hub.reset`, `base.hub.dumps` y `base.hub.dump_link`, y
  en la pantalla, «Mejorar plan», la Tienda y «Restablecer el negocio» con «Copias de los datos»
  (`components/data/ResetPanel.vue`). Lo pinta `ManageLink.vue` (`menu-manage`, `ion:open-outline`) al pie del menú lateral,
  justo debajo de «Mejorar plan» (`UpgradePlanLink.vue`): los dos van en `SidebarFooter.vue`, la pieza
  `sidebarFooter` de `createShell` en `frontend/main.ts`; la barra de arriba solo lleva los destellos y la campana. Es
  un enlace con `target=_blank rel=noopener` que al pulsarlo lleva el pase y en la app instalada sale por
  `openExternalLink` de `@erplora/ui/shell` (`open_external_url`); `base/frontend/lib/management.ts` lo oculta en la copia
  de Google Play (`device_context` → `distribution: "play"`, gh:hub#1897) y no lo enseña hasta que la app contesta. Esos
  son los dos únicos caminos de salida del Hub (gh:hub#439): todo enlace `_blank` de `base/frontend` y de las apps llama a
  `openExternalLink` u `openSaasPass` en su `@click` (o en la función que nombra), los que llevan al panel de erplora.com («Invitar»,
  «Cambiar roles», «Abrir en erplora.com», «Cambiar en erplora.com») llevan además `managementOffered()`, y lo que
  vende («Mejorar plan» del acceso, de WhatsApp…) va con `isWeb`; lo vigila `frontend/external-links.test.ts`, con
  su lista de espera por issue, hoy vacía. Tests:
  `base/tests/test_spa.py`, `test_access_spa.py`, `ManageLink.test.ts`, `SidebarFooter.test.ts`,
  `ShellChrome.test.ts`, `lib/management.test.ts`; e2e
  `tests/e2e/base-chrome.spec.ts` y `base-access.spec.ts` (BASE-G56). En `frontend/main.ts`, el menú de usuario lleva «Perfil» y «Cambiar de usuario», y `startWayIn`
  (`base/frontend/lib/access.ts`) arma el bloqueo por inactividad con esos minutos (gh:hub#2537, #2677: no hay
  lectura aparte que pueda fallar), pinta la apariencia propia y, tras un cambio de usuario (anunciado en
  `sessionStorage`), dice «Ahora atiende {name}» y olvida la apariencia anterior. Cambiar de usuario abre la sesión
  nueva sobre la vieja y recarga la pantalla en curso (`location.replace`): nada de quien se fue queda en memoria
  (gh:hub#2538, #2539); la cuenta abierta de Ventas la recuerda su app (`useCurrentCheck`). Guardar el nombre en Mi
  perfil llama a `sessionChanged()` (`lib/access.ts`) y `frontend/main.ts` vuelve a leer `base.session.me`, que es la
  sesión que pinta el shell (el menú lateral); si esa lectura falla, se queda la que había.
- «Uso y plan» (BASE-F40, `queries.usage.plan_usage`) cuenta los dispositivos en uso con la regla del tope de BASE-F57
  (`services._end_other_devices`): los `device_id` distintos de las sesiones vivas del host (`SessionOwner`).
- `TrustedDevice`, `Credential`, `AccessSettings` y `Profile` viven en la BD de cada negocio, y no hay ninguno en una
  compartida: la lista de dispositivos, el dial y «Quitar» son de ese negocio. Las caras y los PIN se
  filtran además por las personas del negocio (`Membership`, en control). El e2e devuelve el dial al de fábrica al
  acabar.
- Tests: `base/tests/test_access*.py` y `test_api.py`; Vitest de `base/frontend/lib/access.test.ts`,
  `components/{PinPad,PinDoor,DeviceModeCard,PinPolicyCard,DevicesCard}.test.ts`,
  `pages/{Login,PinSetup,SwitchUser,Profile,Settings}Page.test.ts` y `frontend/main.test.ts`; e2e
  `tests/e2e/base-access.spec.ts` (dos personas, dos dispositivos, plan Gratis, una cuenta de Ventas abierta durante
  el cambio de usuario).
- Archivos (BASE-F72…F76) no tiene modelo ni tabla: lista el almacén `STORAGES["hub_files"]` (`base/storage.py`: S3
  con bucket, si no disco bajo `MEDIA_ROOT`) bajo `hub-<hex>/files/<ruta>` con `base/files/` (sin ORM: nombres y
  rutas, el `.keep` de una carpeta vacía, listar, subir, carpeta, renombrar, mover, borrar y `file_response`). Las
  operaciones, todas con `ai=`: `base.file.list` y `base.file.read` (`queries.py`, `base.view_files`), y en
  `services.py` `base.file.upload`, `create_folder` y `rename` (`base.upload_files`), `move` (`base.delete_files` y
  además `base.upload_files`) y `delete` (`base.delete_files`). Rutas `/api/files`, `/api/files/raw` (los bytes con
  `Cache-Control: private, no-store`, adjunto salvo `inline` en un tipo que se puede enseñar, CSP `sandbox`; su
  descripción en JSON con `Accept: application/json`) y `/api/files/{upload,folder,rename,move,delete}`; eventos
  `base.file.*` y consulta viva `base.file.list`. Nunca por `/p/media/` (solo sirve las carpetas que declaran las apps,
  abajo, y las fotos de las personas). Topes: 25 MB por archivo (cuerpo de 35,1 MB en base64), nombre de 255 bytes, carpeta de 100
  caracteres y ruta de 980 bytes; los programas (`BLOCKED_EXTENSIONS`, la lista de Gmail) se rechazan. Subir nunca pisa:
  la escritura es condicional (`If-None-Match: *` en S3, `O_EXCL` en disco) y, si otra subida del mismo nombre llegó
  antes, toma el siguiente nombre libre. Un listado lee solo la carpeta abierta (`Delimiter` en S3); el árbol de carpetas
  y lo que ocupan los archivos salen del índice del hub, guardado en la caché (`base.files:{<hex>}:*`: el hub entre
  llaves, para que sus tres claves caigan en una ranura del clúster; 10 minutos como mucho): una subida le suma sus
  bytes y crear, renombrar, mover o borrar lo olvidan, así que un lote de subidas y los
  listados de después recorren los archivos una sola vez; lo que guardan las apps se cuenta en cada llamada. El espacio
  es el de todo el prefijo del hub, contra `plan.max_storage_bytes` de la foto del SaaS (sin él, «Sin límite»). Una app que
  guarde archivos lo hace en su carpeta propia del prefijo (como `website/`), fuera de `files/`, y Archivos no la
  enseña; antes de guardar uno nuevo pasa por la misma comprobación del espacio que Archivos,
  `base.queries.files.refuse_past_the_plans_space(ctx, store, size)` (el plan del hub de `ctx`, en su idioma): el límite, el
  409 `base.file_no_space` y su frase viven solo en `base.files.space.refuse_past_the_space`, nunca copiados en una app.
  Pantalla: `pages/FilesPage.vue`, `components/{FileTree,FilePreview}.vue` y `lib/{files,pdf}.ts` (pdf.js en el
  hilo principal). Tests: `base/tests/test_files.py`, `test_files_api.py`, el Vitest de cada pieza y el e2e
  `tests/e2e/base-files.spec.ts` (tres tamaños, el empleado y el hub B que nunca ve los de A) y
  `tests/e2e/fix-base-plan-space-check.spec.ts` (el tope en español: Archivos y la web dicen la misma frase).
- Al purgar un hub, `base.files.delete_hub.delete_hub_files` borra su prefijo entero (`base.storage.hub_prefix`) y ningún otro: lo
  llaman `base.services.demos.purge_demo_data` (demo, PUBLIC-F34) y `base.tenancy.offboarding` (baja, BASE-F109), siempre tras el
  `DROP` (PLAN-DB §6 «Baja», paso 4), fuera de toda transacción y antes de la fila. Un fallo es `HubFilesNotDeleted`, también
  las claves que `DeleteObjects` rechaza dentro de un 200: el hub sigue `dropping` con el error en `last_error`
  (`drop_failed: HubFilesNotDeleted: …`, `files_purge_failed: …`) y se reintenta; nunca queda `purged` con ficheros. El
  bucket tiene versionado: la clave deja su marcador de borrado y la versión antigua se va a los 90 días por la regla
  `noncurrent` de aws (`s3.tf`). Tests: `base/tests/test_files_delete_hub.py`, `test_offboarding.py`,
  `test_provision_demos.py`.
- Lo que dejaron las purgas de antes de hub#781 (una fila `purged` no vuelve a pasar por la purga) se borra una vez con
  `manage.py delete_leftover_hub_files` (hub#785): busca en el almacén las carpetas de arriba con forma de prefijo de hub
  (`base.files.delete_hub.hubs_in_store`, `hub-<hex>`) y, después de listarlas, lee el registro (`base.services.demos.gone_hubs`): solo
  cuenta un hub `purged` o sin fila (la lápida de una demo, olvidada a los `DEMO_TOMBSTONE_DAYS`) cuyo prefijo aún guarda
  claves. Cualquier otro estado conserva sus ficheros, `shared/`, `_inventory/` y lo que no es un prefijo de hub no se
  miran, y no abre la base de datos de ningún hub. Sin `--delete` solo lista (prefijo, motivo, claves y bytes); con él
  borra cada uno con `delete_hub_files`, y un prefijo que falla no para a los demás y deja el comando en error. Corre como
  tarea suelta de la familia `worker`, la que borra del bucket. Test: `base/tests/test_delete_leftover_hub_files.py`.
- **`/p/media/<hex>/<nombre>`** (`base/media.py`): sirve, desde el
  host de su hub y nunca el de otro, solo las carpetas del almacén que declara cada app en su `LiveAppConfig`:
  `public_media` (cualquiera; caché pública de un año: `website/img/`, las imágenes de la web) y `members_media` (solo una
  sesión de este hub, caché `private`: `whatsapp_inbox/samples/`, el archivo de la cabecera de una plantilla); las fotos de
  las personas (`AVATARS_FOLDER`, `avatars/`) son de `base`, para las sesiones. Un visitante que pide un archivo de
  miembros recibe el 404 de uno que no existe; una carpeta de miembros dentro de una pública sigue siendo de miembros, y
  una app apagada en el negocio (`base.activation.off_apps`) no sirve ninguna de las suyas. Cada carpeta empieza por la
  etiqueta de su app y una `/`, acaba en `/` y no sube (`..`, `.`, segmento vacío, `\`): una app nunca abre la carpeta de
  otra. Lo que no cumple no se sirve y `base.E010` lo dice al arrancar. Una app que guarde archivos para enseñarlos los
  declara ahí, sin tocar `base/`. Tests: `base/tests/test_media.py` (miembro, visitante, otro hub, app apagada, `..` y la
  carpeta de otra app) y, por app, el suyo (`apps/whatsapp_inbox/tests/test_template_header_file.py`).
- **La puerta pública `/p/<slug>/<página>`** (`base/public_door.py`): las páginas sin sesión que una app da a los
  clientes del negocio, en el host de su hub. La app la pide en su `LiveAppConfig` con `public_pages = {"<página>":
  "<permiso>"}`, un permiso suyo (uno de otra app, o que no declara, no abre nada: la puerta se lo da a cualquiera; ni
  una página que también da otra app; `base.E020` lo dice al arrancar);
  hoy, Reservas online (`{"book": "online_booking.public"}`). `GET /p/<slug>/<página>` es el HTML del shell
  (`base.spa.shell`), con el dinero del negocio en el bloque `public-door`, y la ruta de la app de ese camino pinta la
  página; `GET /p/<slug>/<página>/<clave>` (un solo segmento de letras, cifras, `-` y `_`: el enlace personal de una
  clienta) es el mismo HTML, para la ruta de la página que lee la clave; la puerta no la lee ni dice si abre algo, y la
  ruta va antes de las de `/p/media` y `/p/catalog` para que un negocio que se llame así también abra la suya; `POST /p/<slug>/api/<operación>` corre en el proceso una operación de esa app que pide justo ese permiso,
  como nadie (`actor=None`) y con ese permiso y ningún otro, también con una sesión abierta, con la entrada en el
  cuerpo JSON (nunca en la query) y la respuesta o el sobre de error del API, en el idioma del visitante; lleva el
  token CSRF del HTML. El negocio es el del Host: un `<slug>` que no es el suyo, una página que ninguna app da, una
  operación fuera de la página o la app apagada en el negocio, 404. Tests: `base/tests/test_public_door.py` (otro
  negocio por slug y por host, app apagada, permiso ajeno, CSP, CSRF, el visitante por `X-Forwarded-For`, y el enlace
  personal: su HTML, el de otro negocio y el token de otro negocio, que da lo mismo que uno inventado) y el e2e
  `tests/e2e/online-booking-public-page.spec.ts`.
- **Asistente** (BASE-F92…F106): es **plataforma** dentro de `base/`, no un
  módulo `kind="app"`: lo traen todos los planes (el cupo mensual llega en la foto; 0 = sin asistente) y sus piezas son
  del shell y del Inicio. Las mecánicas que no dependen de la pasarela son de `live.assistant` (las mismas del panel
  del SaaS; `knowledge/raw/plans/2026-10-30-asistente-saas.md` §2 de la raíz) y `base/assistant/` (sin ORM) les añade
  lo suyo, un módulo por pieza (`_Words`, pantallas, `ALWAYS`, `NOT_FROM_CHAT`, checks y pasarela): el catálogo de herramientas (`catalog`:
  toda `@operation` de las apps activas cuyo `ai=` es una herramienta (`Operation.ai_spec()` es un `AI`) y cuyo permiso
  tiene la persona, o que su app deja aprobar a un responsable (`approvals.label_of`) y el rol propio de la persona no
  le niega (`permissions.refused_outright`). Toda operación declara `ai=`
  (`live.E017`): `AI(description=…, risk=…)` o `ai=INTERNAL`; un `dict` se sigue aceptando y `ai_spec()` lo lee como
  `INTERNAL` si no tiene descripción, si dice «Not an assistant tool» / «System only» o si es de la plataforma (sin
  permiso, o con uno que ninguna app declara, `<app>.system` o `system.<app>`: sus reacciones y tareas programadas, que
  solo alcanza `*`; `live.meta.declared_permissions`: ni siquiera un superusuario las recibe, diga lo que diga su
  `ai=`). Fuera también las `base.assistant.*` y `NOT_FROM_CHAT` = `base.hub.reset` y `base.blueprint.export`; que el
  catálogo de dueño, encargado, empleado y superusuario no se movió con E017 lo guarda
  `base/tests/test_catalog_unchanged_by_e017.py`), `relevant` (solo las que nombran las palabras, en los `PLACES` = 15 puestos de un turno, y la búsqueda `base.assistant.find_tools` al final, por las
  palabras de la petición que sigue abierta: lo que la persona escribió desde que el modelo pidió su última escritura,
  con sus respuestas a las preguntas del asistente, y nunca menos de sus dos últimos mensajes; `base.setup.status` y
  `base.business.get` siempre; `ranking` lo ordena con las palabras propias del Hub: las de la plataforma, `SYNONYMS`
  («placa», «empleado»), y las que cada app declara en `assistant_synonyms` de su `LiveAppConfig`, con su forma comprobada por `base.E018`; las de `base`, en el suyo, salen de los nombres de las
  apps de la tienda en `en` y `es` (cada uno de los dos de «Ventas / TPV» o «Menús y combos»): el nombre junto a «del
  menú», «en el menú», «al menú» o «disponible en el menú», delante o detrás («quita Tareas del menú», «quita del menú
  Tareas», «put Tasks back on the menu»), es la app (`base.app`), y lo que sale del menú la apaga y lo que entra o
  está en él la enciende; nunca la frase suelta, porque «los postres del menú vegano» o «quita la tarta del menú» son
  de Menús y combos. Lo comprueba `base/tests/test_assistant_synonyms.py`; cuentan en todo turno, salvo las de una app fuera de
  la tienda, `listed = False` como Demo, que solo cuentan donde se ofrecen sus herramientas), la tarjeta (`card`: `ai={"risk": "high"}` pide
  `CONFIRM_WORD`, «CONFIRMAR» por `pgettext` con contexto `assistant` del catálogo de `live`, o el número de `ids`; sin `ids`, `blocked`; cada
  dato con su nombre en el idioma de la persona, `_label`: el `title` del esquema si un catálogo lo traduce, o tal
  cual en inglés; si no, el `verbose_name` del campo del mismo nombre en los modelos de su app, primero el de la
  entidad de la operación; si no, el `title` por los catálogos. Un dato sin campo de modelo lleva
  `title=gettext_noop(…)` y su `es` en el `.po` de su app, como los de Archivos, Plantillas y Personas en
  `base/schemas/`; lo comprueba `test_no_datum_of_a_write_of_base_reaches_a_spanish_card_by_its_technical_name`;
  la app de la tarjeta y del recibo, `app_name`: la de una app por su `verbose_name`, una acción de `base` por la
  pantalla de su entidad, `BASE_SCREENS`, nunca «Base»; el recibo usa el `app_name` que manda el turno en
  `executed`; lo comprueba `test_every_action_of_base_names_its_screen`; la acción de la tarjeta y del recibo, el
  último trozo del nombre de la operación (`action`), por su verbo en `base.assistant.card.actions` de los catálogos
  `en` y `es` de `base` (`actionKey` de `lib/assistant-hub.ts`, que recibe el nombre entero de la operación, por clave
  exacta; sin clave, «Do this»): una app con una acción nueva añade ahí su verbo en los dos idiomas, y lo comprueba
  `test_every_write_the_assistant_may_call_names_its_action_in_english_and_spanish`; antes que el de su acción va el
  verbo de la operación entera, `base.assistant.card.operations.<app>.<entidad>.<acción>`, para la que el de su acción
  no dice lo que hace (`cart_checkout.cart.clear` vacía
  el carrito, «Vaciar», mientras `kitchen.routing.clear` quita una ruta, «Quitar»; `cash_register.count.add` y
  `cash_register.movement.add` registran un arqueo y un movimiento, no añaden nada): lo comprueban
  `test_a_write_whose_actions_verb_does_not_say_what_it_does_is_named_by_its_own` y
  `test_each_verb_of_its_own_names_a_write_the_assistant_may_call_in_english_and_spanish` (una clave que no nombra una
  escritura del asistente, o sin palabras en un idioma, caería en silencio al verbo de su acción); un dato secreto, el que su
  esquema marca `format: password` o `writeOnly` (`SecretStr`), a cualquier profundidad, sale tapado con `HIDDEN`,
  «••••••••», igual en todos los idiomas (`_hidden`, desde `_field`, el mismo en la tarjeta y en la vista previa): ni
  la pantalla ni lo que recibe el navegador lo llevan tal como se escribió, y la escritura lo recibe entero al
  aceptarla; uno vacío sale vacío; lo comprueban `test_no_operation_lets_a_secret_reach_its_card_in_clear`, que
  recorre el registro entero, y
  `test_a_secret_reaches_the_browser_hidden_on_its_card_and_its_write_as_typed`); una clave de intento
  (idempotencia: la que el llamador crea una vez y repite en cada reintento), la que su esquema marca
  `json_schema_extra={"attempt_key": True}` (`ATTEMPT_KEY`, siempre sobre un texto; en un tipo anotado, como
  `AttemptKey` de Ventas, vale en cada uso), no sale ni en la tarjeta ni en la vista previa, a cualquier profundidad y
  aunque vaya vacía (`_said` la deja fuera como `_LEFT_OUT`), y la escritura la recibe entera; lo comprueban
  `test_an_attempt_key_its_schema_marks_never_reaches_the_card_at_any_depth`,
  `test_the_yes_runs_the_write_with_its_attempt_keys_as_sent` y el trinquete
  `test_every_attempt_key_of_a_write_is_marked_but_the_known_ones` (`UNMARKED_ATTEMPT_KEYS`, que solo baja: detecta
  por el nombre, `idempotency_key`, `job_key`, `submit_key`, `client_<x>_id` o con «idempoten»/«attempt_key», un
  texto sin la marca; hoy queda Bandeja de WhatsApp), con `test_an_attempt_key_is_marked_only_on_a_text`
  (`base/tests/test_assistant_card_values_attempt_keys.py`); un importe, el que su esquema marca `json_schema_extra={"money": True}`
  (`MONEY`, siempre sobre un entero en la unidad menor de su moneda; en un tipo anotado, como `Cents` de Servicios,
  vale en cada uso), sale arriba como `kind="money"` (lo pinta la pantalla en la moneda del negocio o, en la vista
  previa, en la que dé su lectura) y, dentro de un objeto o de una lista, igual: el servidor lo manda como dinero
  (`_Words.amount`: `{"kind": "money", "value": …, "money"?: …}`) y la pantalla lo escribe como el de arriba
  (`card.ts` del chat compartido, `isAmount` y `formatMoney` con `narrowSymbol`: un mismo símbolo en toda la tarjeta, «1,50 $» y
  no «1,50 US$» al lado; `money_text` queda para correos, PDF y avisos, donde «US$» desambigua); las palabras de su descripción no cuentan
  («in minor units», «in whole cents»), ni su nombre (hub#917: un `…_cents` sin la marca
  no es un importe, arriba, dentro de un objeto o en una lista; lo fijan
  `test_a_name_in_cents_alone_makes_no_amount_its_mark_does` y, en Automatizaciones,
  `test_each_datum_of_the_change_comes_as_the_chat_card_says_it`), `signed` exige la marca (`base.E005`, también a un
  `…_cents` sin ella: `test_a_preview_marks_signed_only_an_amount`) y las instrucciones del turno
  dicen al modelo que un dato marcado `"money": true` va en la unidad menor y que un importe de un resultado llega ya
  en su moneda y lo dice tal cual; lo comprueban
  `test_an_amount_its_schema_marks_is_money_whatever_its_words_at_any_depth`,
  `test_the_model_is_told_an_amount_by_its_mark_whatever_its_description_says`,
  `test_no_amount_the_card_painted_as_money_stops_being_one` y el trinquete
  `test_every_amount_the_assistant_shows_or_fills_is_marked_but_the_known_ones` (`UNMARKED_AMOUNTS`, que solo baja:
  detecta un entero llamado `amount`, `price` (o acabado en `_amount`, `_price` o `_cents`) o `price_delta`, o cuya
  descripción habla de «cents», «minor unit» o «céntimos», sin la marca y salvo los decimales de una moneda, en la
  entrada de cada herramienta y en los datos de su vista previa; hoy vacío), el de lo que responde cada herramienta
  (`test_every_amount_a_tool_answers_is_marked`, con la misma detección; hoy vacío), con
  `test_an_amount_is_marked_only_on_a_whole_number`; la moneda de esos importes, la que nombra el dato de su
  escritura que su esquema marca `json_schema_extra={"currency": True}` (`CURRENCY`, siempre sobre un texto; vale
  para los importes de su mismo objeto y de lo que cuelga de él; hoy `currency` de `payment.payment.create`) o, sobre
  el dato que nombra un registro con moneda propia, la lectura de su app que la da
  (`base.schemas.assistant.in_currency_of("<query>", by="<su entrada>", code="<el dato de su respuesta>")`, que es
  `{"currency": {"read", "by", "code"}}`; hoy `cart_id`, `session_token` y `customer` de las escrituras de Carrito y
  pago, con `cart_checkout.cart.get`; `price_list_id` y `price_list` de `pricing.price_item.add`, con
  `pricing.price_list.get`, e `id` de `pricing.price_item.update`, con `pricing.price_item.get`), corrida como la persona (`_run`, como el nombre de un registro) solo si el objeto lleva
  algún importe (`_sends_amount`) y del primer dato marcado que venga relleno; tomada como la toman las escrituras
  (sin espacios, en mayúsculas, un código ISO 4217 que `pycountry` conoce) y con los decimales de esa moneda
  (`currency_decimals`: ninguno en yenes): arriba y dentro de un objeto va en el `money` del importe; vacía o sin ese
  dato, la del negocio; una que no lo es, o un registro cuya moneda no se puede leer (no existe, la persona no puede
  leerlo, su respuesta no es una moneda o no hay persona, como en una automatización), no se inventa: sus importes
  salen tal cual (arriba, `kind="text"`) y lo decide la escritura; `base.E011` comprueba al arrancar que cada marca
  `currency` es `True` o una query de su app, de `base` o de una que requiere, que toma ese dato y da ese código; las
  instrucciones dicen al modelo que la unidad menor es la de esa moneda, también la del registro; lo comprueban
  `test_an_amount_of_a_write_on_a_record_is_in_that_records_currency` (por id, por nombre y en yenes),
  `test_an_amount_only_inside_an_object_is_also_in_the_records_currency`,
  `test_an_amount_on_a_record_whose_currency_cannot_be_read_is_shown_as_sent`,
  `test_without_the_person_a_records_currency_is_never_read`,
  `test_a_record_is_read_only_for_its_amounts_and_one_not_named_leaves_the_businesss`,
  `test_a_currency_mark_is_checked_at_start`, `test_the_model_is_told_an_amount_on_a_record_is_in_that_records_currency`,
  los de Carrito y pago y Tarifas en su `tests/test_integration_assistant.py` (un carrito y una tarifa en dólares y en
  yenes, de verdad), el trinquete
  `test_every_amount_on_a_record_in_a_currency_of_its_own_says_how_to_read_it_but_the_known_ones`
  (`UNPRICED_RECORD_AMOUNTS`, que solo baja: un importe de una escritura cuya descripción dice «<x>'s currency», salvo
  la del negocio, sin marca `currency` en su objeto ni encima; hoy ninguno),
  `test_an_amount_of_a_write_that_names_its_currency_is_in_that_currency` (dólares, yenes y « usd »),
  `test_an_amount_in_a_currency_that_is_none_is_shown_as_sent_never_in_another`,
  `test_inside_an_object_the_currency_it_names_is_the_one_of_its_amounts`, el trinquete
  `test_every_currency_a_write_names_beside_its_amount_is_marked_but_the_known_ones` (`UNMARKED_CURRENCIES`, que
  solo baja: un texto llamado `currency` o `<x>_currency`, o cuya descripción dice ISO 4217, junto a un importe
  marcado de una escritura, sin la marca; hoy vacío) y `test_a_currency_is_marked_only_on_a_text`; la vista previa de una
  escritura peligrosa (BASE-F98, `preview`: su `ai=` lleva `"preview": {"operation": "<una query de su app>",
  "fields": [<datos de su respuesta>]}`; el turno la corre como la persona, `_run` con su `ctx`, con los datos de la
  escritura que su entrada toma, antes de la tarjeta; quita los vacíos y los `None`, lo que la lectura oculta; si no
  se puede leer, su error es el de la escritura y no sale tarjeta; `base.E005` comprueba al arrancar que es una
  query de la misma app, que da esos campos, que la escritura lleva toda su entrada y que es `risk="high"`; la
  tarjeta la pinta bajo «Lo que va a pasar», `AssistantConfirm.vue`; hoy la declara `base.person.pin_remove` con
  `base.person.detail`), la
  comparación del servidor (`confirmed`, como `ConfirmDialog`: sin mayúsculas ni espacios de los extremos),
  `run_tool` (la operación como la persona; `PermissionDenied`, `AppInactive` y `Unauthorized` → `refused`) y las
  puertas firmadas del SaaS (`/internal/assistant/chat/stream`, `usage`, `report`, `docs/search`,
  `/internal/speech/transcribe` y `/internal/speech/synthesize`, con el HMAC de `base.signing`).
- **La tarjeta es la confirmación** (hub#1140, hub#1175): ninguna descripción `ai=` de una herramienta manda preguntar,
  confirmar o esperar un sí en el chat antes de llamarla («Ask first.», «confirm it first», «tell the person…, then…»
  y, en la lectura previa de una escritura, «Read it before … and tell the person …»): con esa frase el modelo pregunta
  en el chat y la tarjeta no sale (Reservas, hub#1105; Mesas; Caja, hub#1138; Facturación, hub#1102). Lo que se cuenta
  antes de una escritura va en la misma respuesta que su llamada. Lo guarda `tests/test_guardrails_assistant.py` sobre
  todas las herramientas del Hub, sin excepciones (hub#1175 arregló las nueve que quedaban en Control horario,
  Automatizaciones, Personal y Facturación); lo citado («…», `código`, nombres con punto) y lo negado no cuentan.
- Operaciones del asistente, todas con `base.view_home` y `ai=` «Not an assistant tool»: `base.assistant.turn`
  (command: corre las lecturas pendientes, para en la tarjeta de una escritura hasta su `decision`; una respuesta del
  modelo puede pedir varias herramientas y es una sola ronda (`rounds` de live): sus lecturas corren seguidas en la
  misma vuelta y cada escritura espera su tarjeta, de una en una, con un sí o un no que vale solo para la llamada que
  nombra (`base/tests/test_services_assistant.py`, `…_in_one_answer_…`); la ronda que llega
  a `MAX_ROUNDS` = 20 (de live) va a la pasarela sin herramientas y con `LAST_ROUND` en las
  instrucciones, para que el modelo conteste con lo hecho y lo que falta; lo que pide después no corre ni saca tarjeta
  ni recibo, y vuelve con `base.assistant_out_of_steps` (`OUT_OF_STEPS`) para que conteste, y si aun así pide otra
  cosa, corta con `assistant.too_many_steps`; la llamada que espera su tarjeta vuelve con `shown`, la
  huella de lo que enseñó (`assistant.fingerprint`: sus datos y «Lo que va a pasar» como los ve la persona, más el id
  de cada registro que leyó, por sus datos marcados con `names(…)` —por id o por nombre— y por su `check`), y el
  panel la devuelve tal cual con el «sí»; con él la tarjeta se vuelve a dibujar y, si la huella no coincide (o no
  viene), no corre nada y sale la tarjeta nueva (hub#1208; lo comprueba `base/tests/test_assistant_yes_for_its_card.py`).
  Una escritura que toma su registro por el nombre sin marcarlo ni comprobarlo no queda fijada: su tarjeta tiene que
  leerlo (patrón de Demo, hub#1206); el «sí» a una escritura que la persona no puede hacer y un
  responsable puede aprobar responde `requires_elevation` para esa misma petición y, repetida con el pase, la corre
  con ese permiso más y gasta el pase en su transacción (`_assistant_approved` + `base.approval_spend`; si su rol propio
  dice «No», la herramienta no está en su catálogo y no corre ni con pase), y arma las
  instrucciones con las pantallas que puede enlazar, lo que sabe del negocio (`base/assistant/business_facts.py`: país,
  zona y hora de allí, el idioma del negocio y el de «Mi perfil» de la persona (`base.profile.get`), sector, apps
  encendidas, con `base.administer_hub` el plan de la foto con las apps que cuenta, `activation.chosen_on` contra
  `plan.max_apps`, y los ajustes de cada app encendida que los declara en `assistant_settings` de su `LiveAppConfig`
  (Ventas, Caja y Reservas), tal como los contesta esa lectura por `base.assistant.tools.run` y solo si la persona
  puede correrla; una línea corta por dato) y, con `setup`, la lista de `base.setup.status` releída; lo que
  el modelo lee de una herramienta sale de `base.assistant.tools.run`, que llama a `run_tool` de `live` con
  `zone=business_zone()` y `money`, así que sus horas van en la zona del negocio y no en UTC, y cada importe marcado
  como dinero va como lo escriben las pantallas en el idioma de la persona («3,60 €» en español, «€3.60» en inglés:
  lo escribe `base.business.money_text`), en la moneda del objeto que la nombra (`currency`) o en la del negocio,
  nunca en la unidad menor: lo comprueban
  `base/tests/test_business_facts.py`, también con dos negocios en zonas distintas, y
  `base/tests/test_assistant_result_amounts.py`; cada valor de una lista cerrada que nombran las pantallas lleva
  además ese nombre en el idioma de la persona, una vez por dato y valor, bajo `screen_names` (`live.assistant`, con
  la etiqueta de las opciones del modelo que usa la tarjeta, `choice_label`): lo comprueban
  `base/tests/test_assistant_screen_names.py` (toda lista cerrada que devuelve una herramienta, la que declara su
  esquema y la que solo tiene opciones en el modelo, como los días de la semana; las que aún no nombra ninguna app o
  que el esquema no declara van por herramienta en `assistant_closed_lists_known.json`, que solo encoge),
  `apps/customer/tests/test_assistant_screen_names.py` y `apps/staff/tests/test_assistant_schedule_days.py`; los
  catorce alérgenos los nombra la plataforma (`base.allergens.NAMED`); el paso del asistente de Automatizaciones lo
  lee igual), `base.assistant.usage` (query), `base.assistant.report`,
  `base.assistant.transcribe` y `base.assistant.speak` (command). Rutas en `base/api/assistant.py` (`/api/assistant/turn`,
  `usage`, `report`, `transcribe`, `speak`): el turno responde en streaming (`text/event-stream`, `turn_response`) a
  **una** petición `fetch` + `ReadableStream` que se cierra al acabar (tramas `text`, `executed`, `confirm`, `usage`,
  `error` y `done`), no una segunda SSE permanente (PLAN §14). El navegador nunca habla con la pasarela ni con un
  proveedor.
- **Leer en voz alta con la voz del servidor** (PLAN-HUB §73; dormida: `ASSISTANT_SERVER_VOICE`, apagado por defecto, la enciende; apagado, `hub-home.server_voice` es `false`, el panel no
  recibe `speak` —ni selector de voz ni petición— y lee con la voz del dispositivo, y la operación responde 503
  `base.assistant_speech_unavailable` sin llamar a erplora.com): `base.assistant.speak` (`database=False`)
  pide a erplora.com el mp3 de una respuesta (`text` de 1 a 4096 caracteres, sin espacios de los extremos; `language`,
  `es` o `en`, la de la pantalla si no viene y el inglés para cualquier otra; `voice`, una voz del motor de
  erplora.com, o ninguna: la suya del idioma; `@erplora/ui` no nombra voces, saas#242). Espera hasta 65 s (`SPEECH_TIMEOUT`, más que los 60 s
  que erplora.com espera al proveedor). La ruta devuelve el mp3 (`audio/mpeg`, `no-store`), o la salida JSON (el mp3 en
  base64) a quien solo acepta JSON. Sin voz configurada en erplora.com (`assistant.speech_unavailable`,
  `assistant.provider_not_configured`) responde 503 `base.assistant_speech_unavailable`; cualquier otro fallo (4xx,
  5xx, tiempo agotado, una respuesta que no es audio), 503 `base.assistant_speech_failed`; los dos dejan su línea en el
  log. El panel lo reproduce desde un `blob:` (CSP `media-src 'self' blob:` y el origen del SaaS) y, si falla, lee con
  la voz del dispositivo (`hubAssistant(doc).speak` = `speakAloud`, `base/frontend/lib/assistant-hub.ts`).
- **La ayuda de un módulo** (BASE-F115): `base.help.get` (query, `base.view_home`, `database=False`, `ai=AI(…)`, en
  `base/queries/app_help.py`; su ruta, `GET /api/help`, en `base/api_help.py`, que monta `config/api.py`) lee la parte
  del cliente del WORKBOOK del módulo con `base/workbook_help.py`, sin tocar la base de datos. Un módulo tiene la ayuda
  lista cuando declara `help = Help(…)` (`live.meta.Help`, con un vídeo de YouTube opcional por idioma, que valida
  `live.E023`), y el JSON `hub-home` de `base/spa.py` nombra esas apps en `help_apps`. Con ellas, `HelpEntry.vue`
  pinta el «?» en la barra de la página visible y abre `HelpWindow.vue` (con `HelpContent.vue` y `HelpFlowList.vue`, en
  `base/frontend/components/`); `base/frontend/lib/help.ts` guarda lo leído por módulo e idioma hasta que se recarga la
  página, y `tests/e2e/base-help.spec.ts` la recorre en tres tamaños (`tests/e2e/base-help-video.spec.ts`, con el
  vídeo de Inventario en el reproductor de YouTube de verdad). El idioma es `ctx.language`:
  el original, `SOURCE_LANGUAGE` (`es`), se lee de `WORKBOOK.md`, y cualquier otro de `WORKBOOK.<idioma>.md` solo si
  lleva, bajo cada encabezado, la marca con la huella del mismo apartado de la parte española
  (`base/workbook_sections.py`; `manage.py translate_workbooks --check` dice cuáles faltan); si no, el de su idioma base
  (`en` para `en-gb`), y si tampoco, el español; `language` dice cuál salió. El vídeo, igual. Lo leído se guarda en
  memoria por módulo e idioma (`_READ`): los WORKBOOK solo cambian con una imagen nueva; con `DEBUG` se relee en cada
  llamada. De la primera
  sección («Para qué sirve») se publica solo lo que va antes de su primer `###` (toda la sección, si no tiene ninguno):
  dos o tres frases; desde el primer `###` (quién lo usa, lo que no hace) se queda en el fichero y nunca se publica.
  Cada `###` bajo el encabezado de las pantallas es
  la pestaña del menú que tiene esa etiqueta en el idioma del fichero, más la de ajustes (`/<módulo>/settings`) si el
  menú no la trae. De cada pestaña se publica solo su resumen: lo que va entre su `###` y su primer `####` (o el final
  de la sección, si no tiene ninguno). Desde el primer `####` es detalle para quien mantiene el módulo: se queda en el
  fichero y nunca se publica; cada `####` es una ventana de esa pestaña y su título sirve de lugar para la `Pantalla:`
  de un flujo. De los flujos se publican los que están hechos (lo que
  sigue en `Estado:` a una raya, dos puntos o un paréntesis es una nota) y cuya `Pantalla:` (partida por «,» y «;»)
  nombra una pestaña o una de sus ventanas, sin lo que va entre paréntesis en un lado ni en el otro; y de ellos solo el
  título sin el id, los pasos y «Si falla:», que empiezan con mayúscula. El encabezado, las claves de un flujo y «hecho» son el
  vocabulario `pgettext("workbook", …)` del `.po` de `base`, así que el código no nombra más idioma que el original.
  Un párrafo o un elemento de lista que el fichero parte en varias líneas sale en una sola, salvo tras un salto forzado
  (dos espacios o una barra al final de la línea), porque la pantalla respeta cada salto de línea y su `parseMarkdown`
  cierra un elemento en su primera línea. La CSP deja `frame-src 'self' https://www.youtube-nocookie.com` (`live.csp.with_frames`;
  `'self'` es la vista previa del editor de la web). `tests/test_help_workbooks.py` vigila cada módulo con la ayuda
  lista en cada idioma: cada entrada del menú con su `###`, una sola vez, y cada `###` una pestaña; «Para qué sirve»,
  que no está vacío y no pasa de 500 caracteres; cada pestaña, con
  un resumen que no está vacío y no pasa de 900 caracteres (dos o tres frases y, si la pantalla la tiene, una lista
  corta como la leyenda de colores); lo publicado (y solo eso: el detalle bajo un `###` de la primera sección o un
  `####` de una pestaña no se vigila), sin
  código, sin referencias a issues, sin tamaños en px, sin ids de flujo ni nombres de operación o de evento; cada flujo
  publicado, con sus pasos; ningún flujo que se lea como hecho en una pestaña, fuera; y cada traducción, con las mismas
  pestañas y flujos que el original.
- **La ayuda de las pantallas propias del Hub** (BASE-F115): `base.help.get` con `app=base` la sirve igual que la de un
  módulo, por la misma ruta y con el mismo permiso. `base` declara `help = Help()`, y `base/platform_screens.py` dice
  cada pantalla (una por pestaña, si la página las tiene) con la etiqueta de su `###` en los dos idiomas (msgids
  `pgettext("workbook", …)`), su ruta en el router de la SPA (sin leer sus parámetros y con el `#` de su pestaña) y el
  permiso que pide su página. Quien no tiene ese permiso no recibe su ayuda: el filtro se aplica en cada llamada, fuera
  de lo guardado en `_READ`. Un `###` que no es una de esas pantallas (la campana, el menú lateral, el asistente) se
  queda en el fichero. Los flujos se publican como los de un módulo, en las pantallas que la persona ve y solo si su rol
  los hace: de los roles que nombra `Actor:` (gestoría, empleado, responsable, administrador y propietario, `ROLES` de
  `base/platform_screens.py`, msgids `pgettext("workbook", …)`), `permission_of` toma el que menos puede y pide lo que
  tiene ese rol y no tienen los de abajo (`base.view_home`, `base.open_management`, `base.administer_hub` o
  `base.own_business`); lo que no es un rol (soporte, el sistema, cualquiera del negocio) no cuenta, y un flujo sin
  ninguno le sale a quien ve su pantalla. Un rol propio recibe los flujos de lo que puede, por el mismo permiso. La
  ayuda de un módulo no mira el `Actor:`: la recibe entera quien lo abre. Las rutas de `base` no llevan `meta.app`: las que tienen ayuda llevan `help: true`
  en su `meta` (`base/frontend/routes.ts`), así que ni una pantalla sin ayuda ni la de «Sin acceso» enseñan el «?», y la
  ventana sabe en cuál está por la ruta del router y el `#` (`resolvePlatformScreen`, en `base/frontend/lib/help.ts`).
  `tests/test_help_workbooks.py` exige de cada pantalla su `###`, una sola vez, y las mismas reglas de texto y de tareas
  que a un módulo; `base/tests/test_queries_app_help.py`, las tareas de cada rol; `base/tests/test_platform_screens.py`,
  que cada tarea pida lo mismo en todos los idiomas, que cada dirección exista en la SPA, que las rutas con `help: true` sean
  justo las de esas pantallas y que su permiso sea el de la operación que lee; `tests/e2e/base-help-platform.spec.ts` la
  recorre en tres tamaños y en los dos idiomas.
- **La documentación de ERPlora** (saas ASSISTANT-F28): `base.docs.search` (query, `base.view_home`, `database=False`, `ai=AI(…)`; herramienta
  `base__docs__search`, en `ALWAYS` porque una pregunta de «cómo se hace» no comparte palabras con ella) pregunta al
  único índice de erplora.com (`assistant.DocChunk`: la ayuda pública, la documentación de cada app, los WORKBOOK del
  panel y los planes) por `POST /internal/assistant/docs/search` (`assistant.docs_search`: `hub`, `query`, `language`
  —`es` para cualquier español, si no `en`— y `limit`, ≤ 12, 8 por defecto). El Hub no guarda índice ni llama a
  `/internal/assistant/embeddings`. Dentro de un turno la espera no puede quedar en su transacción (PLAN §14.2): la
  ruta pregunta antes (`assistant.prepare` → `prepare_docs`, solo con sesión y `base.view_home` y solo lo que el
  esquema acepta) y el turno lee esa respuesta (`prepared_docs`, `searched_docs`); fuera de un turno pregunta en el
  momento. Lo que la pasarela no contesta (409 sin proveedor, 503, 429, una respuesta que no es el contrato, sin red)
  es 503 `base.assistant_unavailable`, «Ahora no se puede buscar en la documentación de ERPlora.», que el modelo
  cuenta: nunca fragmentos inventados. Cada extracto vuelve con su `cite`, la línea con la que la respuesta lo cita,
  escrita por el Hub en el idioma de la persona: «Fuente: <heading>» (`pgettext("assistant answer", "Source")`), o su
  `path` si no trae títulos (hub#1079: la respuesta daba los pasos sin nombrar ningún extracto). Las instrucciones
  mandan contestar el «cómo se hace» solo con lo que devuelve y terminar la respuesta con el `cite` de cada extracto
  usado, al menos uno, tal cual y en su propia línea, y decir que la documentación no lo cubre si no devuelve nada; la
  regla de no inventar un registro sigue. Su pantalla de recibo es `help` («Ayuda»; el chat solo pinta recibos de escrituras). Necesita la
  puerta de ERPlora/saas#178 desplegada: sin ella contesta 503.
- Panel: el chat compartido de `@erplora/ui/components` (`packages/ui/src/components/Assistant/`; el SaaS
  monta el mismo con sus herramientas): `AssistantPanel`, `AssistantMessage`, `AssistantMarkdown`,
  `AssistantComposer`, `AssistantConfirm` sobre `ConfirmDialog`, `AssistantReport` sobre `FormModal`, `AssistantEmpty`
  y `AssistantButton`, montado por `createShell({ chrome: { topbar: TopbarChrome, background: BackgroundChrome } })`
  en `frontend/main.ts`. El Hub lo configura con `configureAssistant(HUB_ASSISTANT)` (`base/frontend/lib/assistant-hub.ts`:
  ruta del turno, `base.assistant.usage`/`transcribe`/`report`, `base.view_home` para usarlo, `base.administer_hub` y
  el `plan_url` de `hub-home` para mejorar el plan, la aprobación de encargado y los verbos y pantallas del catálogo de
  `base`) al arrancar y en los helpers de test que montan sus piezas (`mountBase`, `mount-sale`), y le pone su
  conversación vacía con los atajos de la configuración (`AssistantSetupEmpty.vue`, en el slot `empty` del panel). Los textos propios del chat son
  `assistantMessages` del paquete (raíz `assistant`, `en` + `es`), que `appMessages` de `frontend/main.ts` mezcla con
  los de las apps; en `base.assistant` quedan solo los del Hub (`empty`, `setupIntro`, `shortcuts`, `setup`,
  `card.actions`, `card.operations` y `screens`). Estado por pestaña en `state.ts` del paquete; la conversación, en
  `sessionStorage` (`erplora.assistant.history`, de una persona: otra empieza vacía) y el abierto o cerrado en
  `localStorage` (`erplora.assistant.open`); sin IndexedDB. Quien deja la caja se lleva su conversación y deja el
  panel cerrado (`handOverAssistant()` de `lib/sign-out.ts`): `signOut()` de `frontend/main.ts` lo hace antes de
  `logout` (también el bloqueo por inactividad) y «Cambiar de usuario» antes de recargar la pantalla para quien entra,
  con PIN y con placa. El abierto o cerrado es del dispositivo y, sin eso, pasaría a la persona siguiente. Comprobaciones de la respuesta en `grounding.ts`, formato en
  `markdown.ts` (nunca `v-html`), adjuntos y voz en `input.ts` (`MediaRecorder`, dos minutos), el dictado en
  `dictation.ts` (`useDictation`: una grabación por pulsación, 2 MB, el texto al cuadro y el panel abierto; el mismo
  para el cuadro y para la app que abre el asistente dictando), fallos y cupo en `guide.ts`, todos en
  `packages/ui/src/components/Assistant/`. Desde 768 px el panel se ancla (clase `assistant-docked` en `<html>`, que
  empuja el pane); por debajo, velo.
- **El registro cuando la pasarela falla** (ERPlora/saas#167): el panel dice cada fallo con sus palabras (BASE-F94,
  BASE-F106), así que el motivo solo queda en el registro. Cada llamada a erplora.com que no sale deja una línea
  `WARNING` del logger `base.assistant` con la puerta (`path`) y el negocio (`hub`): `base.assistant.gateway_refused`
  (`status` y el `code` del sobre de error; `-` si no lo trae, la página de un proxy),
  `base.assistant.gateway_unreachable` (`kind`, la clase del fallo de `httpx`), `base.assistant.gateway_failed` (el
  proveedor falló a mitad del turno: su `code` y `retriable`) o `base.assistant.gateway_cut` (el turno se cortó:
  `kind`, la excepción o `no_done`). Nunca lo que la persona dijo, dictó o se le contestó. El 30/10 una producción
  sin proveedores contestaba 503 `assistant.no_model` y `assistant.provider_not_configured` a todo, y el Hub no lo
  decía.
- Ningún test del asistente llega a un proveedor real: los de Python hablan con una pasarela falsa y los e2e, con un
  SaaS de verdad y su pasarela, detrás de la cual hay un proveedor falso que habla la API de OpenAI (receta en
  `tests/e2e/README.md`, «El asistente»).
- **Resumen propio de una escritura** (hub#693): `ai["summary"]` es un callable
  `(ctx, arguments, fields) -> list[dict]`; `base.assistant.cards.card` lo ejecuta solo con `ctx`, como esa persona y bajo
  `translation.override(language)`, con `fields` ya en ese idioma, y pone exactamente los campos que devuelve. Sin
  `ctx` o sin callable, deja el detalle normal. `website.site.save` es el primer uso; su contrato está en
  `base/tests/test_assistant.py`.

- Personas y permisos: las personas son `Membership` (control) más la foto de erplora.com
  (`hub.state["members"]`, `plan.max_users`); invitar, cambiar el rol y quitar son de erplora.com (HUBS-F24…F29):
  el hub enlaza a «Miembros» (`members_url` de `hub-home`). Reglas puras en `base/people.py`; operaciones
  `base.person.{list,detail,pin_remove,badge_set,badge_remove}` y `base.role.{list,detail,create,update,delete,assign}`
  (rutas `/api/people…`, `/api/roles`, `/api/roles/{detail,update,delete,assign}`). El PIN y la placa son los de Acceso
  (`Credential`): mismo hash, mismos frenos.
- Roles propios (`base.models.roles.BusinessRole`, en la BD del negocio): `base/roles.py` dice sin ORM lo que permite
  uno hoy y lo que queda por revisar; `base.permissions.permissions_of_business_role` es el único cálculo, el mismo de
  quien lo tiene (`access_for`), y `base/services/roles.py` mide la escalada con `queries.roles.states_of`: solo lo que
  sube (`roles.raised`: de «No» a «Con aprobación» o de cualquiera a «Permitido»), en todas las apps de este despliegue,
  también las apagadas (una app que se encienda da lo de su rol de origen). Lo «Permitido» lo da quien lo tiene; lo «Con
  aprobación», quien lo tiene o lo hace también con aprobación: sin eso, quien gestiona roles se quitaría a sí mismo el
  «No» que le puso el dueño. Guardar `states` escribe lo que llega; si llega algo de una app que el rol no había
  guardado, se escribe la app entera con lo que ya daba, para que nombrar un permiso no apague los demás. `base.role.update`
  despierta todas las consultas vivas del negocio tras el COMMIT (`_wake_open_apps`). El nombre es único sin contar
  mayúsculas (`base_businessrole_name_unique`), como en Shopify POS, Lightspeed, Odoo, NetSuite, Business Central y
  WordPress; y solo quien está en el negocio impide borrarlo, como en Square y Lightspeed. `base.role.assign` escribe
  `HubUser.business_role` (nulo es el rol de la invitación) con la regla de rangos de `base.people.role_refusal`, mide
  lo que el rol da con la misma vara y bloquea la fila del rol hasta el COMMIT, para que borrarlo a la vez espere
  (`base/tests/test_role_assign_race.py`). `base.permissions.role_held` dice el rol de la invitación y el propio que
  manda: lo leen `access_for`, `base.session.me` (el nombre del rol y los permisos que un responsable puede aprobar),
  la huella de `base.session.access` y el asistente. Los «Roles por revisar» los cuenta
  `base.queries.roles.roles_to_review` en `base.bell.counters`. `base.role.detail` dice de cada permiso si un responsable
  puede aprobarlo (`approvable`) y si queda por revisar (`to_review`). En la SPA, `RolesList.vue` es la lista, `NewRoleModal.vue`
  el alta y `RolePage.vue` la página de un rol, que pinta `RoleEditor.vue` (con `useSettingsForm`) en uno propio para
  quien tiene `base.manage_roles`; al cambiar algo de lo que permite manda todos los permisos que enseña, y así queda revisado.
- Llaves de API: `base.models.api_keys.ApiKey` en la BD del hub (token `erpk_live_` + 256 bits, se guarda su SHA-256 y su
  principio); `base/api_keys.py` pone la puerta de la llave (`KeyDoor`) delante de la sesión en toda ruta de una
  operación `expose_api`; la llave recibe el permiso de esa operación y nada más, con su ritmo por minuto y el freno
  por dirección (`KEY_ADDRESS_LIMIT`). La llave vive en la BD del negocio, así que la de uno nunca abre otro (test
  A≠B en `base/tests/test_api_keys.py`); un negocio sin BD propia no se sirve y su dirección responde 503
  `base.hub_maintenance`, con llave o sin ella. Crear una llave con más de lo que puede quien la crea (BASE-F86) responde
  403 `base.api_key_beyond_maker`. «Nueva API key» solo ofrece lo que dice `grantable` de `base.api_key.list` y manda lo
  marcado que siga ahí (`askedScopes`, `base/frontend/lib/api-key-scopes.ts`).
- Aprobación con PIN de un responsable: una app nombra sus órdenes aprobables en su `LiveAppConfig`
  (`approvals = {"sale.sale.void": _("Void a sale")}`; una consulta nunca, ni una orden `database=False`, que no abre
  transacción en la que gastar el pase: `base.E004` lo dice al arrancar). `base/approvals.py` pone su puerta
  (`ApprovalDoor`) delante de la sesión en toda orden: a quien es del negocio y le falta el permiso le responde 403
  `requires_elevation` con `approval: {operation, label, fingerprint}` (huella de negocio, método, ruta y cuerpo); a
  quien no es del negocio (sin `base.view_home`) y a quien su rol propio le dice «No»
  (`permissions.refused_outright`, leído en cada petición), el `permission_denied` de siempre, también con un pase: el
  pase no se marca ni se gasta. `base.approval.approve` tampoco lo da (`base.approval_not_offered`). Un rol básico no
  dice «No»: lo que no da y su app deja aprobar es «Con aprobación». La frase con cifras:
  junto a `approvals`, la
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
  número y `money` de un entero, y los mismos huecos en `en` y `es`. Hoy la declaran `demo` (`demo.item.add_line`) y
  Ventas (los descuentos y el cobro por encima del máximo de SALE-F14, y el precio libre de SALE-F09).
  `base.approval.approve` comprueba el PIN o la placa como la puerta del PIN (`queries.access.pin_owner`,
  `services.devices.badge_owner`, `PIN_PERSON_LIMIT`/`PIN_ADDRESS_LIMIT`) y que quien aprueba tenga el permiso, y devuelve un
  pase de un uso (120 s, `X-Elevation-Token`); la puerta marca la petición con él (`Approved`), `base.operations`
  añade ese permiso a esa llamada y el pase se gasta en la transacción de la propia orden: `LIVE["operation_database"]`
  (`base/entitlement.py`) abre esa transacción en `base/approval_spend.py` y gasta el pase dentro
  (`base.approval.spend`, sin ruta, con la fila bloqueada), así que una orden que falla lo deja sin gastar, una que
  salió bien no se repite y de dos a la vez solo corre una (`base/tests/test_approval_spend.py`; excepción razonada
  en `tests/test_guardrails.py`, `APPROVAL_SPEND_REASON`).
  Lo que la orden aprobada pide a otras apps por el camino va con ella (hub#250):
  una app corre la operación de otra con
  `base.operations.call(ctx, name, data, unavailable=…)` (la entrada se valida como en una ruta y lo que no valida es
  el 422 del que llama; la app ausente o apagada, su `unavailable`, o `UnknownOperation`/`AppInactive` sin él), que la
  corre con `approvals.consequence_context`: mientras corre la orden aprobada de esa petición (el `current_operation`
  de live es la orden de la marca `Approved`, cuyo pase ya se gastó en su transacción), una orden (`kind="command"`) de
  **otra** app recibe su permiso. Una consulta nunca, una orden de la propia app nunca y nada fuera de la orden
  aprobada (la petición siguiente, otra herramienta del turno del asistente, que marca la petición del turno entero);
  quien ya tiene el permiso sigue con su contexto tal cual. Solo las llamadas directas de la orden aprobada: lo que
  esa otra orden llame a su vez va con el contexto que recibió. La huella y el gasto del pase no cambian
  (`base/tests/test_approved_calls.py`). Ventas aún lleva su copia (`approval_of`, `consequence_context` y `call_app`
  de `apps/sale/queries/other_apps.py`) y pasa a `call` en su FIX; Reservas y Mesas, sin órdenes aprobables, llevan su
  `call_app` propio, al que no llega ninguna aprobación. En el cliente, `withApproval(() => command.run(input))` de
  `base/frontend/lib/approval.ts` abre el diálogo y repite la orden una vez (`getElevationToken` en
  `frontend/main.ts`). Para decirlo antes de empezar, `useAccess(permiso)` de `base/frontend/lib/use-access.ts` da
  `allowed`, `approval` o `no` desde `permissions` y `approvable` de `base.session.me`, que se vuelve a leer al cambiar el
  rol; lo usa Ventas (SALE-F30, SALE-F31). El registro es `base.models.approvals.Approval` (`base.approval.list`).
  Lo que hizo quien ya podía lo anota `base.approval_note.note`, que live llama dentro de la transacción de cada orden
  cuando su cuerpo ha contestado (`LIVE["after_command"]`): una fila con `way = "role"`, sin pase, sin límite de tiempo y
  sin quien la apruebe, y el evento `base.approval.noted`. No anota lo que dejó pasar un pase ni lo que la orden
  aprobada llama por el camino, una orden que no registró ningún evento (la respuesta repetida de una clave de
  reintento), ni a quien no es una persona o una API key (la plataforma, una automatización). Ninguna orden aprobable
  se publica hoy en la API; si una app publica una, la llave queda con su nombre («API · …»).
- Documentación de la API: `base/api_docs.py` recorta el OpenAPI de ninja a las rutas `expose_api` de las apps que
  tiene el negocio, con la llave como `bearer` y solo los esquemas que usan (`base.api_doc.get`, pedido una vez y no
  en vivo: con todas las apps pasa de 1 MB, más que el tope de un resultado vivo). Cada esquema llega al documento
  con el nombre de la app dueña delante (`table.SettingsOut`, `base.DeviceOut`; un paquete ajeno, con el suyo:
  `pydantic.JsonValue`), puesto en un solo sitio, `config/openapi.py`: así dos apps con un esquema del mismo nombre
  no se pisan y cada ruta enseña el suyo; `tests/test_guardrails_openapi_schema_names.py` cae si dos clases acaban
  con el mismo nombre o un nombre llega con dos cuerpos distintos. El ajuste es
  `base.models.api_keys.ApiSettings` (`base.api_doc.settings`, `base.api_doc.settings_update`). Sin Swagger UI: producción
  aplica Trusted Types; la página propia la lee y la descarga. La entrada «API» del menú lateral sale con el ajuste
  (`useApiDocsShown` de `base/frontend/lib/sidebar.ts`, que se suscribe a `base.api_doc.settings` solo con sesión).
- Acceso de soporte (BASE-F126): el ajuste es `base.models.support_access.SupportAccess`, de una sola fila como
  `ApiSettings` (sin fila, apagado), y cada entrada de soporte, una fila de `SupportVisit`; los dos, en la base de datos
  del negocio. `base.support_access.get` (`base/queries/support_access.py`) da el estado, quién lo cambió y cuándo, si
  quien pregunta puede cambiarlo y las 10 últimas entradas, y se sigue en vivo con `base.support_access.changed`;
  `base.support_access.update` (`base/services/support_access.py`, con `base.administer_hub`) lo guarda y deja ese
  evento en el outbox en la misma transacción (sin ese permiso, 403 `permission_denied`). Rutas en
  `base/api/access.py`; tests en `base/tests/test_support_access.py`. La entrada de soporte (`base/services/support_entry.py`, tests en
  `base/tests/test_support_entry.py`): erplora.com manda el rol `hub_support`, un valor de `Membership` que no es un rol
  del negocio (`Membership.Role` no lo lleva); `/auth/callback` abre la sesión en la copia `saas-support:<id>` con la
  forma de entrar `support`, y la operación interna `base.support_access.enter` anota la visita
  (`base.support_access.entered`) o, apagado, la rechaza con `base/templates/base/support_access_off.html`. El equipo del
  negocio es `Membership.objects.team(host)`, que deja fuera a soporte: quien liste personas lo usa. Al apagar, el mismo
  `base.support_access.update` cierra sus sesiones. La tarjeta es `base/frontend/components/SupportAccessCard.vue` (e2e
  en `tests/e2e/base-support-access.spec.ts`); su interruptor, como el de `ApiDocsCard`, se guarda al moverlo con
  `useSavedSwitch` (`base/frontend/lib/saved-switch.ts`), que lo vuelve a pintar en lo guardado si falla.
- Ventanas que preguntan «¿Descartar los cambios?» antes de cerrarse con algo escrito sin guardar (BASE-F05; hub#1015,
  hub#1020, hub#1023, hub#1031, hub#1046, hub#1156): el alta y la edición de producto de Inventario y las ventanas de alta
  y edición de Ventas, Mesas, Cocina, Clientes, Reservas, Citas, Personal, Servicios, Control horario, Carrito y pago,
  Caja, Menús, Suplementos, Pagos, Tarifas, Facturación, Impresión, Horarios, Tareas, Impuestos y la Bandeja de WhatsApp;
  las de categoría y stock de Inventario; «Nueva API key»; las anulaciones con motivo de Reservas online, Pagos,
  Impresión, Reservas, Servicios, VeriFactu y Cocina (cancelar una comanda); el motivo de «Descartar» un evento caído;
  «Nueva carpeta» y «Renombrar» de Archivos; los pasos de importar productos; las fichas de Tarea y Proyecto y el alta
  rápida de cliente del TPV (hub#1233), y las de abrir el turno, entrada o salida, contar y cerrar de Caja (hub#1234).
- Menú lateral: `SIDEBAR` de `base/frontend/lib/sidebar.ts`; cada entrada declara `permission`, el de la operación de
  su pantalla, y `shellSidebar` lo convierte en el `visible` del shell (`ShellSidebarItem`, `packages/ui`); «API» lleva
  además `shownWhile` (la documentación mostrada). Un empleado no ve «Sistema» (`base.administer_hub`), y su dirección
  le dice «Sin acceso» (`gateVerdict` de `lib/app-gate.ts`, con el mismo `permission`).
- Pestañas de Ajustes: `SETTINGS_TABS` de `base/frontend/lib/settings-tabs.ts`, cada una con el permiso de lo que
  lleva («Impresión», `printing.manage_settings`, el de la app a la que lleva; «Datos y copias», `base.administer_hub`);
  `settingsTab` abre la del hash solo si la persona la tiene y, si no, la primera suya.
- Tests: `base/tests/test_people.py`, `test_api_keys.py`, `test_approvals.py`, `test_approval_spend.py`, `test_approved_calls.py` y `test_api_docs.py`; Vitest de
  `base/frontend/lib/{people,approval,api-docs,sidebar}.test.ts`, `components/{PeopleList,RolesList,ApiKeysPanel,
  ApprovalDialog,ApprovalsList,ApiDocsCard}.test.ts` y `pages/{Employees,Person,ApiDocs}Page.test.ts`; e2e
  `tests/e2e/base-employees.spec.ts` y `tests/e2e/base-api-keys.spec.ts` (crear, copiar, usar, rotar y revocar una
  llave que solo lee Inventario en el hub `a`, con su BD propia, en los tres tamaños; borra lo que crea).
- La QA maestra del Hub (BASE-F107 = BASE-G152) es una e2e de `base`, `tests/e2e/base-qa-master.spec.ts`,
  contra el SaaS de la pila
  (alta en sus pantallas, negocio por su API con `business_type` del vertical) y su pasarela del asistente con el
  proveedor de `tests/e2e/assistant-provider.ts`. Pide al SaaS su taxonomía (`seed_taxonomy`, que corre en cada
  despliegue) y el proveedor sembrado (README de `tests/e2e`, «El asistente» y «La QA maestra»). Cada pantalla se
  comprueba contra los catálogos del propio hub (`tests/e2e/translations.ts`: los `en`/`es` de la SPA y los `.po`;
  un texto que solo escribe el otro idioma o una clave a la vista es un fallo) y deja
  `APP-BASE-10-BASE-G152-<idioma>-<pantalla>-<ancho>`.
- Lo que el día de cada vertical recorre en otras apps (cada flujo con su estado en su WORKBOOK y su e2e): la
  siembra por vertical = BASE-F29/F31 + plantillas `base/seeds/<vertical>.<idioma>.json` (la carta con la categoría de
  IVA de cada producto y la sala, de la plantilla; la cocina y la caja, de sus apps). Restaurante: CASH_REGISTER-F03,
  TABLE-F09; RESERVATION-F06/F10/F11, TABLE-F28; TABLE-F10; SALE-F19, MODIFIER-F07, KITCHEN-F07;
  KITCHEN-F04/F05/F10/F18; TABLE-F15/F16/F17, SALE-F23/F24; SALE-F21, PRINTING-F09; SALE-F01/F02/F03,
  INVOICE-F01/F02, VERIFACTU-F19, PRINTING-F07/F13; TABLE-F21, CASH_REGISTER-F09/F16, SALE-F28;
  SALE-F14/F15/F20/F29/F30/F31, INVOICE-F07/F09/F10. Peluquería: CASH_REGISTER-F03, APPOINTMENT-F01;
  APPOINTMENT-F01/F02/F04/F05/F09; APPOINTMENT-F07, CUSTOMER-F01; APPOINTMENT-F04; APPOINTMENT-F17, SALE-F38; el
  cobro como en el restaurante; CASH_REGISTER-F09, SALE-F16/F28, STAFF-F21; APPOINTMENT-F09, SALE-F30/F31, STAFF-F21,
  SERVICE-F12/F14/F22. Fiscal: INVOICE-F01/F02/F07/F09/F10/F15 y VERIFACTU-F15/F18/F19/F26/F28 (solo contra el
  entorno de pruebas de la AEAT). Impresión: PRINTING-F01/F02/F04/F07/F09/F10/F13/F14/F17/F18 (la cola de
  `/ws/print`). Sus specs: `cash-register-*`, `table-flows`, `reservation-book`,
  `sale-*` (con `sale-invoice-chain`), `modifier-till`, `kitchen-*`, `invoice-sale`, `verifactu-flows`,
  `printing-*`, `appointment-*`, `staff-commissions`, `service-flows` y `customer-flows`. Lo que aún no está entero
  lo dice su app: PRINTING-F02 (buscar la impresora en la red) es `parcial` (la app la barre también sin salida a
  internet desde la 1.1.34, pero falta probarlo en un dispositivo con una impresora de verdad), y de SERVICE-F14 la
  venta del bono en el
  TPV está en «Lo que queda fuera» de Servicios. La propina queda fuera (pm#100).
- «Reportar un problema» (BASE-F108): la entrada `report` del menú de usuario
  (`frontend/main.ts`) es una acción (`run` de `ShellUserMenuItem`, `packages/ui`) que abre `ReportProblemDialog.vue`
  (en `BackgroundChrome.vue`, con `lib/report-problem.ts`), el `ReportProblemModal` de `@erplora/ui/components`
  sobre `FormModal`. Sale con `account_url` (la sesión abierta con la cuenta; `base/spa.py` no incrusta
  `report_url`). `base.support.report` (`base/services/`, `database=False`: espera a erplora.com sin transacción
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

- **La caché es un clúster** (hub#440): en AWS es ElastiCache Serverless, un Valkey en modo clúster, que rechaza
  con `CROSSSLOT` una llamada con varias claves de ranuras distintas (`get_many`, `set_many`, `delete_many`). Las
  claves que van juntas comparten una etiqueta de hash: lo que va entre la primera `{` y la siguiente `}`
  (`base.files:{<hex>}:…`, `website:home:{<slug>}:…`). Sin Valkey la caché aplica esa misma regla con el
  mismo error, así que lo que fallaría en AWS falla antes en local o en el test: en local es
  `base.cache.ClusterFileBasedCache`, una carpeta del disco por BD de control (`<tmp>/erplora-hub-cache/<DB_NAME>`) que
  comparten el `runserver` y el worker como comparten Valkey en AWS, y lo que uno olvida al confirmar un cambio (una app
  que el worker deja encendida) ya no lo lee el otro (hub#707); en los tests es `base.cache.ClusterLocMemCache`, la
  memoria del proceso. La carpeta sobrevive a reiniciar el `runserver`, como Valkey a un despliegue: lo guardado caduca
  con su plazo, y para vaciarla basta borrarla.

- **`Hub.cluster` vacío es el servidor por defecto** (hub#614), el de los settings: es un valor válido, no un dato por
  rellenar, y con él conecta, migra, mide y se traslada el hub (`base.tenancy.connections`, `credentials`, `migrator`,
  `control.hub.move`). Por eso ese servidor no se da de alta como fila `Cluster`: una fila cambia el camino de conexión
  de sus hubs (y sus credenciales, si lleva secreto), y desde la primera ningún hub nuevo cae ya en el de los settings
  (`place_hub`). El admin de Hubs lo dice con palabras en la lista, su filtro y la ficha (`control/admin.py`), salvo en
  un hub sin BD hecha (`base.registry.database_is_made`): en preparación, cancelado antes de estar listo o ya borrado.

- **«Mover a otro clúster…» de madrugada** (hub#1508, parte de hub#931) es `control.admin.HubAdmin.move_to_cluster`
  con «Cuándo»: «En su próxima madrugada» (marcada de entrada, como la «próxima ventana de mantenimiento» de RDS) o
  «Ahora» (lo de siempre; también lo que hace `control.hub.move` sin `when`). La de madrugada deja en el hub
  `move_scheduled_to` y `move_scheduled_for` (`control.services.move.night_start`: arranca entre las 03:00 y las 05:00 de
  su `Hub.timezone`, o de la del despliegue si no tiene una válida; dentro de esa franja, en el acto) y el negocio
  sigue abierto: la lista de Hubs lo dice en la columna del clúster, con la hora en su reloj. La franja acota el
  arranque, no el final, como la ventana de AWS; sale del mercado (Square actualiza a las 03:00 de la hora del
  negocio; Business Central y Azure SQL ponen su ventana en la hora local del entorno; RDS, «Apply immediately» o
  «next maintenance window»). La arranca el worker al principio de `base.tenancy.move.worker_pass.run_due`
  (`launch_due`), con el arriendo del hub (`claim_hub`, el de `HubDue`) y en una transacción sobre su fila bloqueada
  (`control.services.worker_move.start_scheduled_move`): si en su reloj ya no es de madrugada (el worker estuvo parado, la zona
  cambió) la deja para la siguiente; si una comprobación de `control.hub.move` la rechaza en ese momento (clúster
  cerrado o lleno, base que no está en su servidor, en restauración…), la quita y lo dice en `Hub.last_error`
  (`move_not_started: <código>: …`); si no, pone `moving_to` y el mismo pase la mueve. Cuenta para el hueco del
  clúster destino y lo protege de borrarse. «Cancelar el traslado» la quita mientras no ha empezado
  (`control.hub.scheduled_move_cancelled`), sin cerrar nada. Tests:
  `control/tests/test_services_move_at_night.py::TestTheNight` y `::TestMoveAtNight`,
  `base/tenancy/tests/test_move.py::TestAMoveAskedForTheNight` (dos BD reales y el arriendo) y
  `control/tests/test_admin_move.py::TestMoveToCluster` y `::TestCancelTheMove`. El sondeo firmado de erplora.com
  (`base.hub.get`, `GET /internal/hubs/{id}`) dice cuándo empieza, en `move_scheduled_for` (un instante en UTC; `null`
  sin traslado, una vez arrancado o cancelado), junto a la congelación de `maintenance` y sin decir adónde va ni cambiar
  `state_version` (`base/tests/test_internal_scheduled_move.py`); erplora.com aún no se lo enseña al dueño (hub#1510).
- **Un negocio de cualquier tamaño se traslada** (hub#1509): la copia pasa por el bucket de volcados
  (`HUB_DUMPS_BUCKET`), nunca por el disco del worker, así que `control.hub.move` no rechaza por tamaño (solo
  comprueba que la base está en su servidor). El negocio está en mantenimiento mientras dura la copia, y por eso se
  pide de madrugada. `pg_dump` sube la copia en
  partes según la hace (`base.tenancy.dumps.stream_to_bucket`, partes de 32 MiB, una en memoria), y la subida solo se
  completa si `pg_dump` acabó bien: si falla, se para o se pasa de tiempo, se aborta y no queda nada. En el destino,
  `pg_restore` lee la copia desde el bucket por su entrada (`dumps.stream_from_bucket` en `move._restore_from_bucket`:
  primero su índice y después la restauración en una transacción, las dos sin fichero). Cada mitad tiene una hora
  (`move.COPY_TIMEOUT_SECONDS`): de madrugada acaba antes de las 07:00 y una hora da para decenas de GiB; se puede
  cancelar en cualquier momento. La copia queda en `<hex>/<AAAAMMDDTHHMMSSZ>-move.dump` los 90 días del bucket, sin
  fila `HubDump` (no es una copia del negocio para descargar; el worker no puede borrar del bucket). Sin bucket no se
  cierra nada: el traslado acaba con `move_dump_failed` en `Hub.last_error` y el negocio sigue donde estaba. La
  restauración a un momento y la copia aparte (BASE-F114) copian con las mismas piezas (hub#1524, nota siguiente).
  Tests: `base/tenancy/tests/test_dumps.py` (los `stream`),
  `base/tenancy/tests/test_move_bucket.py::TestTheCopyGoesThroughTheBucket` y `::TestFeedingAProgram` (dos BD reales y el S3
  de moto), `control/tests/test_services_move.py::TestMove` y
  `control/tests/test_admin_move.py::test_its_confirmation_page_promises_no_refusal_by_size`.
- **«Restaurar desde una copia…»** (BASE-F114, hub#1198) es `control.admin.HubAdmin.restore_from_a_copy`: su página de
  confirmación (`RestoreFromACopyForm`, la plantilla `action_confirmation.html` que comparte con «Mover a otro
  clúster…») y, por cada hub, `control.hub.restore` con el actor del personal; el admin no comprueba nada que la
  operación compruebe. Restaura el worker (`base.tenancy.restore`), y su negativa fiscal (`restore_fiscal_records`, con
  el gancho `fiscal_record_states` de cada app que presenta a Hacienda) queda en `Hub.last_error`, que la ficha enseña
  tal cual. Tests: `control/tests/test_admin_restore.py::TestRestoreFromACopy` y, de punta a punta con el worker y dos BD
  reales, `base/tenancy/tests/test_restore.py::TestAskedInTheHubAdmin`.
- **Cuánto puede estar cerrado el negocio** (hub#1527): las páginas de «Mover a otro clúster…» y «Restaurar desde una
  copia…» dicen debajo de cada hub el tamaño de su base (el que mide la lista, `control.cluster.sizes`, una vez por
  petición) y hasta cuánto puede estar cerrado (`base.tenancy.move.bucket.longest_closure`: las dos mitades de la
  copia a `COPY_SLOWEST_BYTES_PER_SECOND`, 10 MB/s, cada una con su `COPY_TIMEOUT_SECONDS`, en minutos enteros; un
  tamaño que no se lee cuenta como el plazo entero), y el aviso suma los elegidos, que se copian uno tras otro: cada
  uno se cierra al pedirlo y espera cerrado su turno (hub#1532). La copia aparte no cierra nada y no lo dice. Tests:
  `base/tenancy/tests/test_move_closure.py` y `control/tests/test_admin_closure.py`.
- **Un negocio de cualquier tamaño se restaura o se copia aparte** (hub#1524): la copia del clúster temporal pasa por el
  bucket de volcados como la de un traslado, nunca por el disco del worker: `pg_dump` la sube según la hace
  (`move._dump_to_bucket`) y `pg_restore` la lee desde allí por su entrada (`move._restore_from_bucket`), así que
  `control.hub.restore` y `control.hub.restore_aside` no miran el tamaño: solo comprueban que la copia está en el
  clúster temporal. La
  restauración en su sitio vuelca a `<hex>/<AAAAMMDDTHHMMSSZ>-restore.dump` antes de cerrar el negocio, así que sin
  bucket no se cierra nada y acaba con `restore_dump_failed` en `Hub.last_error`; la copia aparte vuelca a
  `<hex del hub>/<AAAAMMDDTHHMMSSZ>-aside-<hex de la fila>.dump` (lleva el arriendo de su fila y no el del hub, así que
  dos copias del mismo negocio pueden volcarse en el mismo segundo y ninguna lee la de otra) y sin bucket la fila falla
  con `restore_aside_dump_failed`. Cada mitad tiene `move.COPY_TIMEOUT_SECONDS`; en la restauración en su sitio el
  negocio está en mantenimiento desde que se pide (`registry.is_copying`) y su base se cierra a la app antes de la
  segunda. Una subida que falla o se para se aborta y no deja nada; la copia queda los 90 días del bucket, sin fila
  `HubDump`. Tests: `base/tenancy/tests/test_restore.py::TestTheCopyGoesThroughTheBucket`,
  `base/tenancy/tests/test_restore_aside.py::TestTheCopyGoesThroughTheBucket` (dos BD reales y el S3 de moto) y
  `control/tests/test_services_restore.py::TestRestore` y `::TestRestoreAside`, con
  `control/tests/test_services_restore_any_size.py::test_a_copy_of_any_size_is_asked`.
- **«Restaurar en una copia aparte…»** (BASE-F114, hub#1213, capa 1) es `control.admin.HubAdmin.restore_aside`: el mismo
  formulario y la misma página (`HubAdmin.from_a_copy`), con `control.hub.restore_aside`, que comprueba lo mismo que
  `control.hub.restore` (`control.services.restore._restorable`) y escribe una fila `control.RestoredCopy` con su nombre
  `<control>_copy_<hex de la fila>` (`base.tenancy.names.copy_db_name`). El worker la hace en el hilo de los traslados
  (`base.tenancy.restore.run_aside_due`), una por pasada y con el arriendo de la propia fila, nunca el del hub: vuelca la
  copia al bucket, clona sin conceder nada (`ops.clone_database(aside=True)`), vacía, `pg_restore` desde el bucket,
  comprueba la identidad, la cierra otra vez y suelta el clúster temporal. El envío a Hacienda está apagado por construcción: ninguna fila de `base_hub` la nombra
  (el worker sirve solo las del registro), ningún rol de la app conecta y su nombre es de copia que queda atrás
  (`names.is_left_behind`), así que `connections.register_hub_alias` se niega a darle alias. Se borra con su fila a los
  `move.MOVED_COPY_DAYS` (`restore.drop_old_aside_copies`); mientras se hace cuenta en `control.freeze.get`. Su esquema
  es el del momento. Tests: `base/tenancy/tests/test_restore_aside.py` (dos BD reales, la guarda de red y
  `TestSendingToTheTaxAuthorityIsOffInTheCopy`, que nunca puede caer),
  `control/tests/test_services_restore.py::TestRestoreAside` y
  `control/tests/test_admin_restore.py::TestRestoreToASeparateCopy`.
- **«Recuperar en el negocio…»** (BASE-F114, hub#1257, capa 2a) es `control.admin.RestoredCopyAdmin.recover_into_the_business`:
  su página (`RecoverForm`, la misma `action_confirmation.html` de las acciones de Hubs, con `AsksFirst`) y, por cada
  copia, `control.copy.recover`, que escribe una fila `control.CopyRecovery` con las apps pedidas y el idioma del personal.
  La hace el worker en el hilo de los traslados (`base.tenancy.recovery.run_due`), una por pasada, con el arriendo de la
  propia fila (`still_recovering` lo renueva antes de cada ficha). La web no puede leer la copia: no tiene el rol del
  migrador y la copia está cerrada a los de la app. El worker la lee con la conexión directa del migrador
  (`ops.connect_ops`) con `default_transaction_read_only`, nunca con un alias de hub (`names.is_left_behind`): ni tareas ni
  cola de VeriFactu corren en ella. Antes de leer lo de cada app mira su `django_migrations` en la copia. Qué devuelve lo
  dice cada app con el gancho `recoverable_from_copy` de su `LiveAppConfig` (una lista de `base.recovery.Recoverable`:
  `label`, `reads_since`, `read(conn)` por SQL sobre los nombres del modelo en su `queries.py`, `missing(records)` en su
  `queries.py` y `create`, la operación que crea cada uno; y, los dos o ninguno, `deleted(records)` en su `queries.py` y
  `restore`, la operación que devuelve lo que el negocio guarda eliminado, hub#1306, que recibe del registro leído lo
  que declara su entrada: el `id` y, si quiere devolverle lo que el negocio le quitó después, lo demás que nombre,
  hub#1356; la de Inventario, además, la imagen que el producto tenía en la copia, hub#1431; las de Citas, solo el
  `id`); `base/` no nombra ninguna. La imagen de lo que vuelve (productos, servicios) la lleva la entrada con
  `base.recovery.ImageInCopyIn` y se queda lo que deja `base.images.from_copy`: la de la librería, salvo una que la
  librería dice que ya no tiene; nunca una foto propia; con la librería sin leer, tal como estaba, para no dejar el
  registro fuera. Primero vuelve lo eliminado y después se crea lo que falta, con las operaciones de la app, en el contexto del
  sistema y en el idioma del personal, dentro de `use_hub`; un `InvalidPayload` o un `NotFound` es de ese registro y los
  demás siguen, cualquier otro rechazo para la app. Mientras devuelve, `base.recovery.at_work()` dice el actor de la
  recuperación en marcha (fuera de una, `None`): con él la lectura de una app distingue lo que trajo esta misma
  recuperación de lo que dejó una anterior (Servicios, hub#1494). Clientes responde con `recoverable_cards_in_copy`,
  `cards_deleted_in_business` con `customer.customer.restore`, que le devuelve lo que el negocio borró después
  (hub#1356), y `cards_not_in_business` (con `has_live_twin`, la regla de la importación) con
  `customer.customer.recover`, que rehace la ficha con sus grupos, etiquetas y campos (hub#1285). Ninguna app cuyos
  registros llegan a Hacienda responde (contrato en `test_recovery.py`). Tests: `base/tenancy/tests/test_recovery.py`
  (dos BD reales: la copia y el negocio), `apps/customer/tests/test_recovery.py`,
  `control/tests/test_services_recover.py::TestRecover`, `control/tests/test_admin_restore.py::TestRecoverIntoTheBusiness`
  y `tests/e2e/base-recover-from-copy.spec.ts`.

### Operaciones y sus flujos

Cada operación de la plataforma, y la de otra app que pide un flujo de la plataforma, con los flujos que la usan; las que no
usa ningún flujo del Hub dicen quién las llama.

| Servicios | Flujos |
|---|---|
| `base.setup.status` | F01, F03, F04, F12, F103 |
| `base.health.list` | F02 |
| `base.widget.list` | F06, F07, F08 |
| `base.bell.counters` | F10, F117 |
| `base.notice.list` | F113, KITCHEN-F16 |
| `base.session.me` | F05, F13, F118 |
| `base.session.access` | F13 |
| `base.access.grantors` | F118 |
| `base.saas_pass.create` | F11 |
| `base.hub.state_apply` | ninguno: erplora.com, cada vez que cambia algo del negocio |
| `base.session.revoke` | ninguno: erplora.com, al cerrar las sesiones de una persona |
| `base.app.list` | F14–F17, F19, F20, F22, F26, F27 |
| `base.app.get` | F18, F21, F23, F24, F97 |
| `base.app.enable` | F18, F19, F24, F31, VERIFACTU-F01 |
| `base.app.retry` | F21 |
| `base.app.activation_settle` | ninguno: el worker, al terminar de preparar los datos de una app |
| `base.app.disable` | F23, F25, VERIFACTU-F32 |
| `base.blueprint.list` | F29, F38, INVENTORY-F12, INVENTORY-F33 |
| `base.blueprint.inspect` | F30, F31, INVENTORY-F12, INVENTORY-F33 |
| `base.blueprint.import` | F31, F33, F38, F94, INVENTORY-F12, INVENTORY-F33 |
| `base.import.list` | F32, F33, F34, F38 |
| `base.import.detail` | F33, F34, F97 |
| `base.import.undo` | F34 |
| `base.blueprint.export` | F35, F36, INVENTORY-F33 |
| `base.dataset.list` | F36 |
| `base.hub.reset`, `base.hub.dumps`, `base.hub.dump_link` | F37 |
| `base.hub.reset_apply` | ninguno: el worker, al vaciar lo que pidió un restablecimiento |
| `base.system.cards` | F39 |
| `base.plan.usage` | F40, F77 |
| `base.assistant.usage` | F40, F104 |
| `base.system.status` | F41 |
| `base.event.list` | F42 |
| `base.failed_event.list` | F43 |
| `base.failed_event.retry` | F44 |
| `base.failed_event.retry_all` | F45 |
| `base.failed_event.discard` | F46 |
| `base.failed_event.detail` | F44, F46, F97 |
| `base.business.get` | F49, F50, F51 |
| `base.access.door` | F52, F55, F56, F57, F58, F59 |
| `base.hub_user.sync` | ninguno: erplora.com, al mandar las personas del negocio |
| `base.pin.set` | F54, F65 |
| `base.access.faces` | F60 |
| `base.device.current`, `base.device.mode_set` | F62 |
| `base.hub.register` | ninguno: erplora.com, al crear el negocio |
| `base.profile.get` | F54, F64, F65 |
| `base.profile.update`, `base.profile.preferences_set`, `base.profile.avatar_set`, `base.profile.avatar_remove` | F64 |
| `base.access.settings`, `base.access.settings_update` | F66, F67 |
| `base.device.list` | F68 |
| `base.device.rename` | F69 |
| `base.device.remove` | F70 |
| `base.device.detail` | F69, F70, F97 |
| `base.device.prune` | F71 |
| `base.file.list` | F72 |
| `base.file.upload`, `base.file.create_folder` | F73 |
| `base.file.read` | F74 |
| `base.file.move`, `base.file.rename` | F75 |
| `base.file.delete` | F76 |
| `base.person.list` | F77, F80, F81, F119 |
| `base.person.detail` | F78, F79 |
| `base.person.pin_remove` | F78 |
| `base.person.badge_set`, `base.person.badge_remove` | F79 |
| `base.role.list` | F82, F83, F127, F129, F130, F131 |
| `base.role.detail` | F82, F97, F128, F129, F130, F131 |
| `base.role.create` | F127 |
| `base.role.update` | F128, F131 |
| `base.role.delete` | F129 |
| `base.role.assign` | F130 |
| `base.approval.approvers`, `base.approval.approve`, `base.approval.spend` | F84 |
| `base.approval.list`, `base.approval.export` | F85 |
| `base.api_key.create` | F86 |
| `base.api_key.rotate` | F87 |
| `base.api_key.revoke` | F88 |
| `base.api_key.detail` | F87, F88, F97 |
| `base.api_key.list` | F89 |
| `base.api_doc.get` | F90 |
| `base.api_doc.settings` | F90, F91 |
| `base.api_doc.settings_update` | F91 |
| `base.support_access.get`, `base.support_access.update` | F126 |
| `base.assistant.turn` | F93, F97, F101 |
| `base.assistant.find_tools`, `base.assistant.speak`, `base.docs.search` | F93 |
| `base.assistant.transcribe` | F94 |
| `base.assistant.report` | F105 |
| `base.support.report` | F108 |
| `base.hub.cancel` | ninguno: erplora.com, al eliminar un negocio o darlo de baja por impago |
| `base.hub.purge` | F109 |
| `base.help.get` | F115 |
| `base.release_note.list` | F116 |
| `base.hub.restore` | ninguno: erplora.com, al recuperar un negocio eliminado |
| `base.hub.dump_list` | ninguno: erplora.com, al enseñar las copias de un negocio |
| `base.hub.get` | ninguno: erplora.com, al esperar a que el negocio esté listo y al enseñar su estado |
| `base.usage.list` | ninguno: erplora.com, cada noche |
| `base.demo.create`, `base.demo.code_create` | ninguno: erplora.com, al crear una demo y entrar en ella |
| `base.demo.expire` | ninguno: el admin de Hubs y `manage.py demo_expire` |
| `base.demo.get` | ninguno: `manage.py demo_expire` |
| `base.demo.purge` | ninguno: el worker, al retirar una demo vencida |
| `base.catalog_image.search`, `base.catalog_image.get` | INVENTORY-F30, SERVICE-F34, COMBO-F14 |
| `control.hub.restore`, `control.hub.restore_aside`, `control.copy.recover` | F114 |
| `sale.sale.list` | F09 |
| `sale.sale.stats` | F119 |
| `inventory.product.export`, `inventory.category.export`, `customer.customer.export`, `invoice.invoice.export` | F112 |
| `base.hub_user.get` | F97, en las tarjetas de Personal y de la Bandeja de WhatsApp |
| `base.location.list` | F93 |
| `base.hub.cut_finish` | ninguno: `manage.py cut_shared_hubs` y el migrador, al dar a un negocio su propia base de datos |
| `base.hub.by_slugs`, `base.hub.seed_local` | ninguno: `manage.py seed_local_hubs`, solo en desarrollo |
| `base.hub.platform_rename` | ninguno: `manage.py create_platform_hub --rename`, el nombre del negocio propio de ERPlora |

## Lo que queda fuera

- **Avisar por correo al dueño cuando debe ampliar (BASE-F40)**: el mercado lo da por supuesto, pero lo manda erplora.com
  (PLAN-SAAS §28) y lleva su flujo y su issue allí.
- **La cola de PgBouncer de cada negocio en CloudWatch**, hub#572.
- **Peticiones a `@erplora/ui`** que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md) (los iconos de documento de
  Archivos, los del cuadro del asistente y `useI18n` en el shell).

## Lo que NO hace, a propósito

- No inventa cifras: un panel o un paso que no se puede comprobar no sale o dice «No disponible».
- No guarda el tablero en el servidor: es de cada dispositivo.
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
- No cambia, borra ni apaga un rol básico: son los de erplora.com, que se dan al invitar; cada app aporta lo que da a
  cada uno en ella y puede traer uno propio cuando su funcionalidad lo pida. Lo que un negocio quiere distinto lo hace
  en un rol propio, a partir de otro (BASE-F127); ninguno da ser el propietario.
- No enseña nunca el token entero de una llave después de crearla o rotarla, ni guarda el PIN de quien aprueba.
- El asistente no guarda la conversación en el servidor: vive en la pestaña de quien pregunta y se olvida al cerrar
  sesión o cambiar de usuario.
- El asistente no busca en Internet ni convierte divisas (llegan con la etapa ERP), y no hace nada que la persona no
  pueda hacer con sus botones, ni sin su «Ejecutar».
- La voz con la que lee una respuesta es la del propio dispositivo; el Hub no genera audio.
