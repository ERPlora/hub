# Workbook — Página web (app)
Prefijo: WEBSITE
Alcance MVP: transversal (peluquería y restaurante: la página del negocio en su propia dirección)
Estado de la app: completa (2026-10-22)
Lo que no entra todavía: ver «Lo que NO hace, a propósito».

> Manual de usuario y especificación de la app `website`. Nace en la ronda 2026-10-21 (PLAN §29, con su ampliación del
> 2026-10-22): no es un porte del producto actual, que no tenía página pública por negocio. Cada flujo está `hecho`
> con sus tests de servidor, de pantalla y de punta a punta en verde; dónde están, en «Para quien lo mantiene».

## Para qué sirve y para quién

Página web le da a cada negocio una página sencilla en su propia dirección de ERPlora (tu-negocio.erplora.com). El
propietario elige uno de cuatro diseños, rellena sus secciones (nombre y logotipo, título y foto de portada, unas
palabras sobre el negocio, su catálogo, una galería de fotos, sus reseñas de Google, cómo contactar, dónde está) y sus
colores, esconde lo que no usa y publica. Quien abre esa dirección sin haber entrado ve la página; el equipo entra
desde su botón **Entrar**, que todas las plantillas llevan y no se puede quitar. Mientras la página no está publicada
(o se ha desconectado), la dirección sigue llevando al acceso del equipo, como siempre.

Está pensada como las páginas de Square Online, Wix o Squarespace, pero reducida a lo que un salón o un restaurante
necesita: secciones fijas, sin arrastrar bloques, sin HTML ni código del usuario. Cambiar de diseño no pierde nada:
el contenido y el diseño se guardan por separado.

## Referencia adoptada

- **Square Online, Wix y Squarespace**: plantillas intercambiables que no pierden el contenido, secciones que se
  muestran u ocultan, vista previa real al lado del editor en un ordenador y en su propia pestaña en un móvil,
  borrador frente a lo publicado, y **Publicar** y **Desconectar** («Unpublish») con confirmación. De aquí también las
  paletas con nombre, con su versión clara y oscura, y el fondo automático que sigue al dispositivo.
- **Square Online y Shopify**: el catálogo de la web sale de los productos y servicios del propio TPV, por categorías
  y con su precio, sin escribirlos dos veces; ninguna categoría elegida = todas.
- **Fresha y Booksy** (salones): la página del negocio con la galería de sus trabajos, el horario con **hoy**
  resaltado, WhatsApp como botón principal y cómo llegar.
- **Perfil de Empresa de Google**: la valoración, el número de reseñas, **Escribir una reseña** y las reseñas tal y
  como las da Google, con su autor y su fecha, como piden sus normas de atribución
  (https://developers.google.com/maps/documentation/places/web-service/policies).
- **El QR de Square y el de Toast**: un PNG para imprimir y un SVG para ampliar sin perder calidad, y el enlace para
  copiar.

## Antes de empezar

- La app está en la categoría **Organización** y no necesita ninguna otra. Si el negocio tiene **Inventario** o
  **Servicios** activos, la sección Catálogo puede mostrar sus productos a la venta o sus servicios ofrecidos.
- Solo el **propietario** y el **administrador** cambian, publican o desconectan la página; el **responsable** la ve
  y comparte su dirección y su QR; el **empleado** no la ve.
- Para las **reseñas de Google**, el negocio necesita su ficha en Google Maps (su Perfil de Empresa de Google): se
  pega el enlace de esa ficha y ERPlora lee de Google su valoración y sus reseñas.

## Pantallas

### Página web
Arriba, el estado: «Tu página web aún no está en línea. Publícala para que tus clientes puedan verla.» (nunca
publicada), «Tu página web está fuera de línea. Publícala para volver a ponerla en línea.» (desconectada) o «Tu página
web está en línea en …» (con la dirección), y «Tienes cambios que aún no están publicados.» cuando el borrador ha
cambiado desde la última publicación. Al lado, **Guardar**, **Publicar**, **Desconectar** (solo en línea) y
**Compartir y QR**, y si todo está guardado o no.

Debajo, el editor y la vista previa. En un ordenador, uno al lado del otro; en una tableta o un móvil, una pestaña
**Editar / Vista previa** cambia entre los dos.

- **Diseño**: cuatro tarjetas con un dibujo de cada plantilla en los colores de la paleta: **Clásica** (centrada y
  cálida: la foto de portada a todo el ancho bajo un velo, título con serifa sobre una raya del color secundario y
  cada sección centrada), **Moderna** (cabecera partida: título, lema y botones al lado de la foto enmarcada, letra sin
  serifa gruesa y apretada, rejilla marcada), **Minimalista** (una sola columna estrecha con mucho aire, letra de
  lectura con serifa, títulos ligeros, líneas finas entre secciones y la foto ancha debajo del título) y **Llamativa**
  (barra oscura, cabecera a todo el ancho en el color principal, con la foto teñida de ese color, mayúsculas enormes y
  botones fuertes). Las cuatro sirven para un restaurante, una peluquería, una tienda o un servicio.
- **Colores**: ocho paletas en tarjetas con sus colores sobre el fondo claro y el oscuro, la elegida resaltada:
  **Océano**, **Bosque**, **Terracota**, **Pizarra**, **Rosa**, **Arena**, **Medianoche** y **Oliva**. Debajo, dos
  campos de color (**Color principal** y **Color secundario**) con los de la paleta elegida: cambiarlos hace tuya la
  paleta, y entonces aparece **Restablecer colores**, que vuelve a los de la paleta. Elegir otra paleta muestra los
  suyos (los cambios de la anterior se descartan). Cada paleta trae su versión clara y oscura y se lee bien en las dos
  (WCAG AA: textos, enlaces y botones); con colores cambiados, el fondo, las franjas y el texto salen de los dos
  colores y un color que no se leería se ajusta lo justo.
- **Fondo de la página**: **Claro**, **Oscuro** o **Automático** (por defecto): automático sigue el dispositivo de
  cada visitante, oscuro si está en modo oscuro y claro si no; lo dice una nota debajo.
- **Secciones**, en este orden, cada una plegable (las ocultas dicen «Oculta» bajo su nombre):
  - **Barra superior** (siempre en la página): nombre del negocio (hasta 80) y logotipo; **Entrar** siempre.
  - **Cabecera** (siempre): título (hasta 80), lema (hasta 160) y foto de portada.
  - **Sobre nosotros**: interruptor **Mostrar**, encabezado (vacío = «Sobre nosotros»), texto (hasta 4000, con
    **negrita**, listas y enlaces en Markdown; nada de HTML) y una foto.
  - **Catálogo**: **Mostrar**, encabezado (vacío = «Nuestros productos» o «Nuestros servicios»), **Qué mostrar**
    (Nada, Productos o Servicios; solo los de las apps activas en el negocio), las **Categorías** (ninguna elegida =
    todas) y **Mostrar precios**.
  - **Galería**: **Mostrar**, encabezado (vacío = «Galería») y hasta 12 fotos, en el orden en que se verán: cada una
    con **Cambiar imagen** y **Quitar** y las flechas **Subir** y **Bajar**; **Añadir una foto** pone otra al final
    mientras haya sitio, y un contador dice cuántas lleva («3 de 12 fotos»).
  - **Reseñas de Google**: **Mostrar**, encabezado (vacío = «Lo que dicen nuestros clientes») y **Enlace de Google
    Maps o Place ID**: el enlace de la ficha del negocio en Google Maps (el de la barra de direcciones o el de su botón
    **Compartir**) o su Place ID (empieza por ChIJ). Debajo, una nota dice cómo están (WEBSITE-F12).
  - **Contacto**: **Mostrar**, encabezado, teléfono, WhatsApp (con prefijo), correo, Instagram, Facebook, TikTok y X
    (enlaces seguros, que empiezan por https) y, si se activa **Mostrar el horario**, el horario de la semana: cada día
    abierto o cerrado y hasta tres franjas (una hora de cierre anterior a la de apertura pasa de medianoche).
  - **Ubicación**: **Mostrar**, encabezado, hasta cuatro líneas de dirección y un enlace al mapa (seguro, se abre
    aparte).
  - **Pie de página** (siempre): una línea de texto (por ejemplo, la razón social) y **Entrar**. Debajo va la firma
    «© <año> ERPlora», enlazada a erplora.com: es la misma en todas las webs y no se edita.
- Las imágenes (jpeg, png o webp, hasta 5 MB y 8000 px por lado) se suben desde cada campo de imagen: **Elegir
  imagen**, y después su miniatura, **Cambiar imagen** y **Quitar**.
- **Vista previa**: la página tal y como la verán los clientes con el diseño y el borrador de ahora, a ancho de
  **Ordenador** o de **Móvil**, y **Recargar la vista previa**. Se recarga sola tras cada guardado.

### Compartir y QR
La dirección de la página web con **Copiar enlace**, su código QR y **Descargar PNG** (para imprimir) y
**Descargar SVG** (para ampliar sin perder calidad). Avisa de que, en el dispositivo donde se ha entrado, la
dirección abre la app (para ver la página: el móvil o una ventana privada) y, si la página no está en línea, de que
la dirección aún lleva al acceso del equipo.

### La página pública
La plantilla elegida con lo publicado, en la dirección del negocio (rediseño moderno del 2026-10-22): barra superior
fija y translúcida con el logotipo, el nombre, el menú de secciones (plegado en un móvil) y **Entrar** (botón de
contorno redondeado); cabecera con la foto de portada (o, sin foto, un degradado suave de la paleta, nunca vacía), el
título en letra grande, el lema y dos botones redondeados: **Escríbenos por WhatsApp** (o **Contáctanos**, a la
sección de contacto, si no hay WhatsApp) y **Cómo llegar** (a la dirección); sin contacto ni dirección, uno a la
primera sección. Cada sección lleva una línea pequeña encima del título («Quiénes somos», «Lo que ofrecemos», «Echa un
vistazo», «Reseñas de Google», «Hablemos», «Visítanos») y su contenido en tarjetas redondeadas: Sobre nosotros con su
foto enmarcada al lado del texto; el catálogo en una rejilla de tarjetas (un degradado con la inicial, porque los
productos no traen foto; el precio en una píldora; píldoras para saltar de categoría si hay dos o más); la galería en
una rejilla de fotos cuadradas y redondeadas (dos por fila en el móvil, tres en una tableta, cuatro en un ordenador)
que crecen un poco al pasar el ratón y se abren enteras aparte; las reseñas de Google con la valoración en grande, sus
estrellas (redondeadas a la media estrella) y «128 reseñas en Google», los botones **Ver en Google** y **Escribir una
reseña** (se abren en Google) y hasta cinco tarjetas con la inicial y el nombre del autor (enlazado a su perfil),
cuándo la escribió (enlazado a la reseña), sus estrellas y su texto tal cual lo escribió (cortado a 280 caracteres,
entero al pasar el ratón), y debajo «Valoración y reseñas de Google Maps. Las más relevantes primero, como las ordena
Google.»; el contacto en fichas con icono (teléfono, correo), WhatsApp como botón y las redes como píldoras; el horario
en una lista con **hoy** resaltado (el día del negocio, en la zona horaria del hub; sin zona, la de Madrid); la
dirección en una tarjeta con **Abrir el mapa**. Pie en columnas: nombre y la línea del pie, enlaces a las secciones y
**Entrar**, y al final la firma «© <año> ERPlora» (se abre aparte). Solo hay transiciones al pasar el ratón (y ninguna
si el sistema pide menos movimiento). La pestaña del navegador lleva el logotipo o, sin él, la inicial del nombre en
el color principal. Se adapta a móvil, tableta y ordenador (Bootstrap 5.3) sin desplazamiento lateral, con la paleta
elegida en claro o en oscuro; en automático, sigue el dispositivo del visitante y cambia si este cambia con la página
abierta (sin JavaScript, se ve en claro). El catálogo se pinta con lo publicado y, al abrir la página, se refresca con
los productos o servicios de ese momento y sus precios en el idioma del visitante. El resto de textos de la página
(Entrar, los días, los encabezados por defecto) sale en el idioma del navegador (inglés o español); lo que escribe el
propietario, tal cual.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando tu página web…» con un indicador; la vista previa, su indicador hasta que llega la página. |
| Nunca publicada | El aviso «Tu página web aún no está en línea. Publícala para que tus clientes puedan verla.» |
| Fuera de línea | «Tu página web está fuera de línea. Publícala para volver a ponerla en línea.» |
| En línea | «Tu página web está en línea en …» y, con cambios sin publicar, «Tienes cambios que aún no están publicados.» |
| Guardando | «Guardando…»; luego «Todos los cambios guardados», o «Cambios sin guardar» mientras hay cambios. |
| Vacío | Sin Inventario ni Servicios activos, Catálogo dice «Activa Inventario o Servicios para mostrar aquí tus productos o servicios.»; la galería sin fotos, «Aún no hay fotos: añade la primera. Se muestran en este orden.»; sin enlace de Google, «Pega el enlace para mostrar tu valoración y tus reseñas de Google.» |
| Error | Al cargar: «No se pudo cargar la página web» con el motivo. Al guardar: «No se pudo guardar la página web» y el mensaje bajo cada campo, sin perder lo escrito. Al publicar o desconectar: un aviso. La vista previa que no llega: «No se pudo cargar la página web» con **Recargar la vista previa**. Un catálogo cuyas categorías no se pueden leer: «No se pudieron cargar las categorías» bajo el selector. |
| App inactiva | «Esta app no está activa en este negocio». |
| Sin permiso | Sin permiso de ver: «Solo el propietario o un administrador pueden cambiar la página web.» Con el de ver (responsable): el estado, **Compartir y QR** y ese mismo aviso, sin editor. |

## Flujos

| ID | Flujo | Estado |
|---|---|---|
| WEBSITE-F01 | Rellenar y guardar el borrador | hecho |
| WEBSITE-F02 | Elegir el diseño, la paleta y el fondo | hecho |
| WEBSITE-F03 | Mostrar u ocultar una sección | hecho |
| WEBSITE-F04 | Subir una imagen | hecho |
| WEBSITE-F05 | Mostrar el catálogo | hecho |
| WEBSITE-F06 | Ver la vista previa | hecho |
| WEBSITE-F07 | Publicar | hecho |
| WEBSITE-F08 | Desconectar la página | hecho |
| WEBSITE-F09 | Compartir la dirección y el QR | hecho |
| WEBSITE-F10 | Visitar la página pública | hecho |
| WEBSITE-F11 | Mostrar una galería de fotos | hecho |
| WEBSITE-F12 | Mostrar las reseñas de Google | hecho |

### WEBSITE-F01 Rellenar y guardar el borrador
<!-- origen: nuevo (editor de secciones fijas con borrador y autoguardado, como Square Online, Wix, Squarespace y Shopify; PLAN §29) -->
Estado: hecho (servidor, pantalla y e2e)
Actor: propietario, administrador, asistente, API
Pantalla: Página web
Pasos:
1. Abre **Página web** y despliega una sección.
2. Escribe: el borrador se guarda solo dos segundos después del último cambio, o al pulsar **Guardar**; también al
   salir de la pantalla si quedaba algo.
3. Arriba se lee «Guardando…» y después «Todos los cambios guardados» («Cambios sin guardar» mientras quedan
   cambios).
Entra: la plantilla, los colores y el contenido completo de las nueve secciones. Las imágenes se nombran por su
subida (WEBSITE-F04); la dirección donde se sirven la pone el servidor.
Sale: el borrador guardado; los clientes no ven nada hasta publicar (WEBSITE-F07). Aviso `website.site.updated`
(solo si algo cambió).
Si falla: «No se pudo guardar la página web» y el motivo bajo cada campo, sin perder lo escrito: textos demasiado
largos, un enlace que no empieza por https, «Escribe un teléfono: números, espacios y, si quieres, un + delante.»,
«Escribe un correo electrónico válido.», «La hora de apertura y la de cierre no pueden ser la misma.», «Cada día solo
puede aparecer una vez.», «Pega el enlace de tu negocio en Google Maps, o su Place ID.» o «Esta imagen no se subió a
la página web de este negocio: vuelve a subirla.».
Implicados: WEBSITE-F02, WEBSITE-F03, WEBSITE-F04, WEBSITE-F11, WEBSITE-F12

### WEBSITE-F02 Elegir el diseño, la paleta y el fondo
<!-- origen: nuevo (plantillas intercambiables sin perder el contenido y paletas claras y oscuras, como Squarespace, Wix y Square Online; ampliación de PLAN §29 del 2026-10-22) -->
Estado: hecho (servidor, pantalla y e2e)
Actor: propietario, administrador, asistente, API
Pantalla: Página web
Pasos:
1. En **Diseño**, pulsa una de las cuatro tarjetas: **Clásica**, **Moderna**, **Minimalista** o **Llamativa**.
2. En **Colores**, pulsa una de las ocho paletas y, si quieres, cambia **Color principal** y **Color secundario**;
   **Restablecer colores** vuelve a los de la paleta.
3. En **Fondo de la página**, elige **Claro**, **Oscuro** o **Automático**. Se guarda como en WEBSITE-F01 y la vista
   previa lo enseña.
Entra: la plantilla, la paleta, los dos colores propios (o ninguno: los de la paleta) y el fondo.
Sale: el mismo contenido con otro diseño o con otros colores; nada se pierde al cambiar. Aviso
`website.site.updated`.
Si falla: un color mal escrito no se guarda y el campo lo dice:
«Escribe el color como #RRGGBB, por ejemplo #1A73E8.».
Implicados: WEBSITE-F01, WEBSITE-F06

### WEBSITE-F03 Mostrar u ocultar una sección
<!-- origen: nuevo (secciones fijas que se ocultan en vez de borrarse, como las de Square Online y Wix; PLAN §29) -->
Estado: hecho (servidor, pantalla y e2e)
Actor: propietario, administrador, asistente, API
Pantalla: Página web
Pasos:
1. Despliega **Sobre nosotros**, **Catálogo**, **Galería**, **Reseñas de Google**, **Contacto** o **Ubicación**.
2. Enciende o apaga su interruptor **Mostrar** (apagada, la lista dice «Oculta» bajo su nombre) y guarda como en
   WEBSITE-F01. La **Barra superior**, la **Cabecera** y el **Pie de página** no tienen interruptor: siempre están.
Entra: qué secciones se muestran.
Sale: lo oculto no se pinta en la página ni sale para los visitantes; se conserva para volver a mostrarlo. Una sección
que se muestra pero no tiene nada (sin texto ni foto, sin catálogo, sin fotos en la galería, sin reseñas de Google,
sin datos de contacto, sin dirección ni mapa) tampoco se pinta, ni su enlace en el menú. Aviso
`website.site.updated`.
Si falla: como al guardar (WEBSITE-F01); ocultar nunca borra lo escrito.
Implicados: WEBSITE-F01, WEBSITE-F10

### WEBSITE-F04 Subir una imagen
<!-- origen: nuevo (imágenes en el almacén de ficheros del negocio, servidas desde su dirección; PLAN §29 y PLAN-HUB bloque 7) -->
Estado: hecho (servidor, pantalla y e2e)
Actor: propietario, administrador, API
Pantalla: Página web
Pasos:
1. En el logotipo (**Barra superior**), la foto de portada (**Cabecera**), la foto de **Sobre nosotros** o una foto
   de la **Galería**, pulsa **Elegir imagen** y escoge el archivo.
2. Aparece su miniatura con **Cambiar imagen** y **Quitar**; **Quitar** deja el campo vacío (en la galería, saca la
   foto de la lista). Se guarda como en WEBSITE-F01.
Entra: un archivo jpeg, png o webp de hasta 5 MB y 8000 píxeles por lado; se comprueba su contenido, no solo su
nombre.
Sale: la imagen guardada en el almacén de ficheros del negocio bajo un nombre sacado de su contenido (la misma imagen
dos veces es un solo fichero), servida desde la propia dirección del negocio y guardada un año en el navegador. Aviso
`website.image.uploaded`.
Si falla: bajo el campo: «El archivo no llegó entero: vuelve a elegirlo.», «El archivo está vacío.», «La imagen puede
pesar 5 MB como mucho.», «Este archivo no es una imagen PNG.» (o JPEG, WEBP) o «La imagen puede medir 8000 píxeles
por lado como mucho.».
Implicados: WEBSITE-F01, WEBSITE-F11

### WEBSITE-F05 Mostrar el catálogo
<!-- origen: nuevo (el catálogo de la web sale de los productos y servicios del TPV, como en Square Online y Shopify; PLAN §29) -->
Estado: hecho (servidor, pantalla y e2e)
Actor: propietario, administrador, asistente, API
Pantalla: Página web
Pasos:
1. Despliega **Catálogo** y enciende **Mostrar**.
2. En **Qué mostrar**, elige **Productos** (los de Inventario a la venta: activos y no agotados) o **Servicios** (los
   ofrecidos); solo salen los de las apps activas en el negocio.
3. Si quieres, elige las **Categorías** (ninguna = **Todas las categorías**) y si se ven los precios con **Mostrar
   precios**. Se guarda como en WEBSITE-F01.
Entra: la fuente, las categorías elegidas y si se ven los precios.
Sale: en la vista previa y, al publicar, en la página: el catálogo agrupado por categoría en su orden (lo que no tiene
categoría, al final), hasta 200 elementos, con píldoras para saltar de categoría si hay dos o más. Precios: «15,00 €»,
«Desde 40,00 €», «20,00 € / hora» o «Gratis»; un precio variable no se muestra. Al publicar se guarda una copia, y la
página la refresca al abrirse con los productos o servicios de ese momento. Aviso `website.site.updated`.
Si falla: sin Inventario ni Servicios activos, la nota «Activa Inventario o Servicios para mostrar aquí tus productos
o servicios.»; si la fuente guardada es de una app que se ha apagado, «Inventario no está activa en este negocio: tu
página no muestra el catálogo hasta que la actives o elijas otra fuente.» (o Servicios) y la página no lleva catálogo,
nunca un error; si las categorías no se pueden leer, «No se pudieron cargar las categorías» bajo el selector.
Implicados: INVENTORY-F27, SERVICE-F10, WEBSITE-F07, WEBSITE-F10

### WEBSITE-F06 Ver la vista previa
<!-- origen: nuevo (vista previa real al lado del editor y en su pestaña en el móvil, como Squarespace, Wix y Shopify; PLAN §29) -->
Estado: hecho (servidor, pantalla y e2e)
Actor: propietario, administrador
Pantalla: Página web
Pasos:
1. En un ordenador, la vista previa está al lado del editor; en una tableta o un móvil, pulsa la pestaña **Vista
   previa** (**Editar** vuelve al editor).
2. **Ordenador** o **Móvil** cambia su ancho y **Recargar la vista previa** la vuelve a pedir; se recarga sola tras
   cada guardado.
Entra: el borrador guardado.
Sale: el borrador pintado por el mismo código que la página pública, con el diseño, los colores y el catálogo de ese
momento; los enlaces no se siguen y los buscadores no la indexan. Sin reseñas guardadas, dice dónde saldrán.
Si falla: mientras llega, su indicador; si no llega, «No se pudo cargar la página web» con **Recargar la vista
previa**.
Implicados: WEBSITE-F01, WEBSITE-F02, WEBSITE-F05, WEBSITE-F12

### WEBSITE-F07 Publicar
<!-- origen: nuevo (borrador frente a lo publicado, con confirmación, como Square Online, Wix y Squarespace; PLAN §29) -->
Estado: hecho (servidor, pantalla y e2e)
Actor: propietario, administrador, asistente, API
Pantalla: Página web
Pasos:
1. Pulsa **Publicar**: si había algo sin guardar, se guarda antes.
2. «¿Publicar tu página web?» dice «Quien abra {url} verá esta versión, con tu catálogo tal y como está ahora.»; pulsa
   **Publicar** (si cancelas, no se publica nada).
3. Arriba se lee «Tu página web está en línea en …» con la dirección.
Entra: el borrador de ahora.
Sale: lo publicado = el borrador (diseño, colores, contenido y la copia del catálogo), una versión más y la página en
línea; cambiar después el borrador no toca lo publicado, y lo dice «Tienes cambios que aún no están publicados.».
Aviso `website.site.published` (con la versión).
Si falla: «No se pudo publicar la página web» y lo publicado sigue como estaba.
Implicados: WEBSITE-F05, WEBSITE-F10, WEBSITE-F12

### WEBSITE-F08 Desconectar la página
<!-- origen: nuevo (despublicar sin perder nada, como «Unpublish» de Wix y Square Online; PLAN §29) -->
Estado: hecho (servidor, pantalla y e2e)
Actor: propietario, administrador, asistente, API
Pantalla: Página web
Pasos:
1. Con la página en línea, pulsa **Desconectar**.
2. «¿Desconectar tu página web?» avisa de que la dirección volverá a mostrar la página de acceso del equipo y de que
   no se pierde nada; pulsa **Desconectar**.
3. Arriba se lee «Tu página web está fuera de línea. Publícala para volver a ponerla en línea.».
Entra: nada: es la página en línea del negocio.
Sale: la dirección vuelve a llevar al acceso del equipo; nada se pierde y publicar de nuevo sigue con la versión
siguiente. Aviso `website.site.unpublished`. Ya desconectada, no hace nada (ni avisa).
Si falla: «No se pudo desconectar la página web» y la página sigue en línea.
Implicados: WEBSITE-F07, WEBSITE-F10

### WEBSITE-F09 Compartir la dirección y el QR
<!-- origen: nuevo (QR para imprimir y enlace para copiar, como el QR de Square y el de Toast; PLAN §29) -->
Estado: hecho (servidor, pantalla y e2e)
Actor: propietario, administrador, responsable, API
Pantalla: Compartir y QR
Pasos:
1. En **Página web**, pulsa **Compartir y QR**.
2. **Copiar enlace** copia la dirección («Enlace copiado»); **Descargar PNG** baja el QR para imprimirlo y
   **Descargar SVG** para ampliarlo sin perder calidad.
3. **Cerrar** vuelve al editor.
Entra: nada: la dirección es la del negocio.
Sale: la dirección pública del negocio, la suya en erplora.com tal y como la ve el navegador, y su QR. Avisa de que en ese
dispositivo la dirección abre la app (para ver la página: el móvil o una ventana privada) y, si la página no está en
línea, de que aún lleva al acceso del equipo.
Si falla: si no se puede copiar, «No se pudo copiar el enlace: selecciónalo y cópialo a mano.».
Implicados: WEBSITE-F07, WEBSITE-F10

### WEBSITE-F10 Visitar la página pública
<!-- origen: nuevo (la web del negocio en su propia dirección, con «Entrar» para el equipo; PLAN §29, decisión de Ioan del 21/10) -->
Estado: hecho (servidor, página pública y e2e)
Actor: cualquiera, sin cuenta
Pantalla: La página pública
Pasos:
1. Abre la dirección del negocio (tu-negocio.erplora.com) en un móvil, una tableta o un ordenador.
2. Se ve la página publicada en el idioma del navegador (inglés o español), con lo que escribió el propietario tal
   cual.
3. **Entrar** lleva al acceso de ERPlora y, al entrar, a la app; con la sesión abierta, la dirección abre la app como
   siempre.
Entra: la dirección del negocio.
Sale: la página publicada, con su propia política de seguridad (sin scripts del usuario: solo el paquete de la
página), sin cookies y guardada un minuto en el navegador; la pestaña lleva el logotipo o la inicial del nombre.
Si falla: sin publicar, desconectada o con la app apagada, la dirección lleva al acceso del equipo; quien hace más de
60 lecturas por minuto desde una misma conexión espera un momento.
Implicados: WEBSITE-F07, WEBSITE-F08, WEBSITE-F05, WEBSITE-F11, WEBSITE-F12

### WEBSITE-F11 Mostrar una galería de fotos
<!-- origen: nuevo (galería de trabajos del salón, como las de Fresha, Booksy y Square Online; ampliación de PLAN §29 del 2026-10-22) -->
Estado: hecho (servidor, pantalla y e2e)
Actor: propietario, administrador, asistente (ordenar o quitar fotos ya subidas), API
Pantalla: Página web
Pasos:
1. Despliega **Galería** y pulsa **Añadir una foto** (una a una, hasta 12; «3 de 12 fotos» dice cuántas lleva).
2. **Subir** o **Bajar** cambian su orden y **Quitar** la saca; con 12, «La galería está completa (12 fotos): quita
   una para añadir otra.».
3. Se guarda como en WEBSITE-F01 y se ve al publicar.
Entra: las fotos subidas (WEBSITE-F04), en su orden.
Sale: en la página, una rejilla de fotos cuadradas en ese orden (2, 3 o 4 por fila según la pantalla), servidas desde
la dirección del negocio y guardadas un año en el navegador; cada una se abre entera en otra pestaña. Sin fotos, o con
la galería oculta, no hay sección (ni enlace en el menú). Aviso `website.site.updated`.
Si falla: más de 12 fotos no se guardan; una foto que no es una subida de este negocio: «Esta imagen no se subió a la
página web de este negocio: vuelve a subirla.» bajo la galería.
Implicados: WEBSITE-F04, WEBSITE-F10

### WEBSITE-F12 Mostrar las reseñas de Google
<!-- origen: nuevo (valoración y reseñas del Perfil de Empresa de Google con «Escribir una reseña», como Fresha, Square Online y Wix; ampliación de PLAN §29 del 2026-10-22) -->
Estado: hecho (servidor, pantalla y e2e)
Actor: propietario, administrador, asistente (el enlace), API
Pantalla: Página web
Pasos:
1. En Google Maps, abre la ficha del negocio, pulsa **Compartir** y copia su enlace (o su Place ID).
2. Despliega **Reseñas de Google** y pégalo en **Enlace de Google Maps o Place ID**; se guarda como en WEBSITE-F01.
3. La nota de debajo dice cómo están: «Se preguntará a Google por este sitio en cuanto se guarde.» (sin guardar),
   «Tus reseñas aparecerán aquí y en tu página en cuanto Google responda por este sitio.» (aún sin respuesta) o
   «Valoración 4,7 de 5 · reseñas en Google: 128» (listas).
Entra: el enlace de la barra de direcciones de Google Maps, el de su botón **Compartir**, uno que lleve el Place ID
dentro, o el Place ID solo (empieza por ChIJ).
Sale: ERPlora pregunta a Google desde su servidor, nunca el navegador del visitante: al guardar un enlace nuevo, al
publicar y al pintar la página si no tiene nada guardado; un enlace por nombre se busca con ese nombre y la dirección
de **Ubicación**. La respuesta vale un día y la última buena se guarda 30 días, así que si Google falla se sigue
viendo. En la página: la valoración con sus estrellas, «128 reseñas en Google», **Ver en Google**, **Escribir una
reseña** y hasta cinco reseñas (las más relevantes, como las ordena Google). Sin enlace, oculta o sin nada de Google,
no hay sección; la vista previa dice dónde saldrán. Aviso `website.site.updated`.
Si falla: un enlace que no es de Google Maps ni un Place ID no se guarda: «Pega el enlace de tu negocio en Google
Maps, o su Place ID.». Si Google no responde (5 segundos como mucho), rechaza la clave o no encuentra el sitio: «Google
no respondió por este sitio. Revisa el enlace: se volverá a intentar en unos minutos.», y se reintenta a los 10
minutos; sin la clave de Google en el servidor: «Las reseñas de Google aún no están disponibles: tu enlace se guarda y
aparecerán en cuanto lo estén.».
Implicados: WEBSITE-F01, WEBSITE-F07, WEBSITE-F10

## Servicios: lo que entra y lo que sale

Todo se puede pedir por las pantallas, el asistente (por voz o por texto, con la sesión de quien habla) y la API, con
las mismas reglas y los mismos permisos.

### Lo que ofrece: consultas (leen, no cambian nada)

| Qué da | Quién puede | Flujos | Servicio |
|---|---|---|---|
| El borrador, su estado de publicación y la dirección pública (se sigue en vivo) | ver | F01–F03, F07, F08 | `website.site.get` |
| El borrador pintado como la página pública (HTML, para la vista previa) | gestionar | F06 | `website.site.preview` |
| Las categorías de Inventario o de Servicios para elegir | gestionar | F05 | `website.catalog.categories` |
| El QR de la dirección pública, en PNG o SVG | ver | F09 | `website.qr.get` |
| Lo publicado, sin las secciones ocultas (sin sesión) | cualquiera | F10 | `website.public.site` |
| El catálogo publicado, leído en ese momento y con los precios en el idioma de quien pregunta (sin sesión) | cualquiera | F05, F10 | `website.public.catalog` |
| Las reseñas de Google guardadas del sitio publicado, con sus textos en el idioma de quien pregunta (sin sesión; nunca pregunta a Google) | cualquiera | F10, F12 | `website.public.reviews` |

Las tres públicas responden solo con la página en línea (si no, 404 `website.not_published`) y cuentan a cada
visitante: 60 lecturas por minuto y dirección, después 429 `base.rate_limited`. El catálogo público se guarda un
minuto.

### Lo que ofrece: acciones (cambian datos)

| Qué hace | Quién puede | Flujos | Servicio |
|---|---|---|---|
| Guarda el borrador (plantilla, paleta y fondo, contenido) | gestionar | F01–F03, F05 | `website.site.save` |
| Publica el borrador con la copia del catálogo | gestionar | F07 | `website.site.publish` |
| Desconecta la página | gestionar | F08 | `website.site.unpublish` |
| Sube una imagen (base64, hasta 5 MB) | gestionar | F04 | `website.image.upload` |

### Asistente
El asistente (por voz o por texto) usa, con la sesión y los permisos de quien habla, `website.site.get`,
`website.site.save`, `website.site.publish`, `website.site.unpublish` y `website.catalog.categories`. Cada campo del
borrador lleva su descripción (nombre, lema, texto de Sobre nosotros, galería, enlace de las reseñas de Google,
contacto, horario, ubicación, plantilla, paleta y fondo), y la descripción de guardar le dice que el borrador se manda entero: lo lee primero con `website.site.get`,
cambia solo lo pedido y lo devuelve. Ejemplo: «Ponme en la web el horario de lunes a viernes de 9 a 20» → lee el
borrador, pone en `contact.hours` los cinco días con la franja `09:00`–`20:00` (deja el resto como estaba) y llama a
`website.site.save`; si además dice «y publícala», `website.site.publish`. No son herramientas del asistente, a
propósito: la vista previa (`website.site.preview`, una página HTML), la subida de imágenes (`website.image.upload`,
un fichero en base64 de hasta 5 MB) y el QR (`website.qr.get`, una imagen en base64), que se usan desde la pantalla, ni
las tres lecturas públicas de los visitantes (`website.public.*`).

### Lo que avisa

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Borrador guardado | Guardar con algún cambio | `id` | `website.site.updated` |
| Página publicada | Publicar | `id`, `version` | `website.site.published` |
| Página desconectada | Desconectar una página en línea | `id`, `version` | `website.site.unpublished` |
| Imagen subida | Subir una imagen | `id` | `website.image.uploaded` |

### A qué reacciona y lo que necesita de otras apps
- No reacciona a avisos de otras apps y no requiere ninguna (`requires = []`).
- **Inventario** y **Servicios**, solo si están activas en el negocio: el catálogo los lee por el nombre de sus
  consultas (`inventory.product.list_for_sale`, `inventory.category.list`, `inventory.product_category.list`,
  `service.service.list_for_sale`, `service.category.list`; INVENTORY-F27 y SERVICE-F10), con un contexto que solo
  puede leerlos; con la app apagada o sin ella, el catálogo sale vacío, nunca un error, y el editor lo dice.
- De la plataforma: el registro del hub (su id, para el almacén de ficheros; `base.operations.hub_id`), el almacén
  `storages["hub_files"]` y la vista `/p/media/…` (`base.storage`, `base.media`), el límite por visitante
  (`base.throttle`) y la entrada `/` (`base.public_home`, que llama al proveedor de la app).
- De fuera: la **Places API (New) de Google**, con la clave de la plataforma (`GOOGLE_PLACES_API_KEY`), solo desde el
  servidor: Text Search (solo el id: Google no lo cobra) y Place Details con reseñas (Google lo cobra como «Place
  Details Enterprise + Atmosphere»: 1000 al mes gratis y después unos 25 $ cada 1000; con la caché de un día, unas 30
  al mes por negocio con reseñas).

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver el estado, compartir la dirección y el QR | sí | sí | sí | no | `website.view` |
| Cambiar, subir imágenes, previsualizar, publicar y desconectar | sí | sí | no | no | `website.manage` |

## Para quien lo mantiene

- **Una fila por hub (andamiaje de la fase 1, PLAN §29)**: hasta la fase 2 las tablas las comparten todos los hubs,
  así que `Site` e `Image` llevan `hub_id` (el `Hub.id` del registro, `base.operations.hub_id`; sin clave foránea,
  porque en la fase 2 el registro vive en la BD de control). `Site.hub_id` es único: un hub tiene una sola web. Toda
  operación lee y escribe solo la fila del hub de la petición (guardar, publicar, desconectar, subir, previsualizar,
  leer), y `/` y la API pública solo enseñan la web publicada de su propio hub: lo que publica un hub nunca sale en
  otro, y el equipo de un hub no lee ni cambia la web de otro. La primera escritura de un hub crea su fila
  (`get_or_create` y después `select_for_update`): dos primeras escrituras a la vez no fallan, la segunda espera a la
  primera. En la fase 2 cada BD de hub guarda su única fila y la columna se queda, siempre con el mismo valor. Las
  claves del almacén (`hub-<id>/website/img/…`) y de la caché (`website:home:<slug>:…`) también llevan el hub. La e2e
  desconecta la página al terminar para no dejar `/` de `a` con ella (las demás e2e esperan el salto al login).
- **El catálogo, solo de una app activa** (APP-WEBSITE, 2026-10-22): `queries._source_on` pregunta a
  `base.relay.active_apps` (la misma pregunta que la guarda de lo público), no a `apps.is_installed`: en la fase 1 toda
  app instalada está activa, y en la fase 2 una app apagada en el hub no tiene sus tablas creadas. Con la fuente
  apagada, `read_catalog` y `website.catalog.categories` devuelven vacío, nunca un error, y el editor lista la fuente
  guardada sin dejar elegirla, con la nota `fields.sourceOff*` (`WebsitePage.test.ts`, «a catalog saved from an app
  that is off…»).
- **El icono de la página** (APP-WEBSITE, 2026-10-22): `render._icon` escribe `<link rel="icon">` con el logotipo o,
  sin él, la inicial en un SVG `data:` con los colores de la paleta (la inicial, escapada). Sin él, el navegador pedía
  `/favicon.ico` al hub, que es la SPA de `base` y le dejaba una cookie `csrftoken` al visitante: la página dejaba de
  ser «sin cookies» (lo cazó `website-flows.spec.ts`, WEBSITE-F10).
- **Una sola guarda para lo público**: `/` (`public_home.is_published`) y la API pública (`website.public.*`) pasan por
  `queries._live`: el módulo encendido en el hub (en la fase 1, toda app instalada, `base.relay.active_apps`; con él
  apagado la API responde 404 `app_inactive` y `/` salta al login) y una publicación en línea de ese hub (si no,
  404 `website.not_published`).
- Anatomía completa: `apps.py`, `models.py`, `schemas.py`, `render.py`, `csp.py`, `public_home.py`, `storage.py`,
  `qr.py`, `reviews.py`, `queries.py`, `services.py`, `events.py`, `live.py`, `api.py`, `admin.py`, `locale/`, `templates/website/`
  y `frontend/`, con un `tests/test_<fichero>.py` por fichero. **Sin `views.py` ni `urls.py`** (PLAN §29): `/` es de
  `base` y `/p/media/…` también.
- Modelos: `Site` (una por hub, `hub_id` único: `template`, `theme`, `content` = borrador; `published_content` =
  plantilla, tema, contenido y la copia del catálogo de la última publicación; `published_version`, `published_at`,
  `is_live`; `reviews_snapshot` = la última respuesta buena de Google para la sección de reseñas) e `Image` (`hub_id` con índice, `key` única, `sha256`, tipo, ancho, alto y tamaño). UUIDv7.
- **Contenido = JSON validado** por `schemas.Content` (nueve secciones cerradas; topbar, hero y footer sin
  `hidden`); `render_site` lo valida otra vez antes de pintar: una fila escrita a mano no cuela marcado. Lo que
  escribe el propietario pasa por el escape de Django, y el texto de Sobre nosotros por `live.markdown` (nh3, sin
  imágenes). Los enlaces solo `https://`.
- **Render y caché**: `public_home.respond` pinta la plantilla con lo publicado, en el idioma de `Accept-Language`
  (nunca una cookie), y guarda el HTML una hora en
  `website:home:<slug>:<versión>:<idioma>:<día>:<APP_VERSION>` (el día es el del negocio, `render.local_day` con la
  zona horaria del hub o `Europe/Madrid` si no tiene: el horario resalta hoy, así que cada día tiene su página; la
  vista previa usa el mismo día, `queries.business_day`): publicar cambia la versión y un despliegue cambia los
  ficheros del paquete, así que nunca se sirve una página rancia; tras el COMMIT de publicar o desconectar se borran
  las entradas de la versión anterior. `Cache-Control: public, max-age=60`, sin cookies, y `Vary: Accept-Language,
  Cookie`: «Entrar» vuelve a `/` con sesión, y el navegador no puede servirle la página que guardó para el visitante
  (con sesión, `/` es la SPA).
- **Límite por visitante**: 60 lecturas públicas por minuto por hub y dirección (`base.throttle`). La dirección es la
  entrada de `X-Forwarded-For` que añadió el proxy de confianza (`base.throttle.client_address`, la que está
  `TRUSTED_PROXY_HOPS` posiciones desde el final: 1 = el ALB en AWS, 0 = sin proxy en local, que usa
  `REMOTE_ADDR`), nunca la primera, que la escribe el cliente (y que Daphne con `--proxy-headers` pone en
  `REMOTE_ADDR`).
- **CSP** (`csp.py`): la página pública y la vista previa no llevan nonce (su HTML se cachea y se comparte):
  `script-src 'self'`, sin `strict-dynamic` ni Trusted Types; `frame-ancestors 'none'` en la pública y `'self'` en la
  vista previa (que además lleva `X-Frame-Options: SAMEORIGIN` y `Cache-Control: no-store`). Con DEBUG, el servidor
  de Vite.
- **Paquete público**: `frontend/website.ts` (entrada `website` de Vite): Bootstrap 5.3, su `collapse` (el menú de la
  barra, por atributos `data-bs-*`) y `apps/website/frontend/public/{site.css,mode.ts,catalog.ts,reviews.ts}`. El
  refresco del catálogo y el de las reseñas reconstruyen su bloque con `createElement`/`textContent`, nunca
  `innerHTML`; si fallan, se queda lo que pintó el servidor.
- **Imágenes**: `services.upload_image` valida con Pillow (tipo real, tamaño, píxeles), guarda en
  `storages["hub_files"]` con clave por contenido y responde la URL de `base.media` (`/p/media/<hex>/website/img/…`,
  caché de un año). `base.media` solo sirve las carpetas públicas (`PUBLIC_FOLDERS`, hoy `website/img/`): el almacén
  guarda también documentos privados de otros módulos, que nunca salen por ahí; un nombre que es una carpeta en disco
  responde 404. Al guardar, cada imagen del contenido tiene que ser una subida de este hub y su URL la escribe el
  servidor.
- **Reseñas de Google** (`reviews.py`, ronda 2026-10-22, decisión de Ioan: del servidor, sin JS de terceros, que la
  CSP prohíbe): `reviews.parse` lee la entrada (Place ID `ChIJ…`; enlace de Google Maps con `place_id=`,
  `query_place_id=`, `q=place_id:` o `!19sChIJ…`; `/maps/place/<nombre>/@lat,lng`, `/maps/search/<texto>/`, `q=<texto>`
  o `query=<texto>`, que se buscan por nombre; enlace corto `maps.app.goo.gl` o `goo.gl/maps`) y `schemas` rechaza lo
  demás. `reviews.load` pregunta con `httpx` (5 s por llamada): el enlace corto se
  sigue una vez (su redirección), el nombre se busca con Text Search (`POST
  https://places.googleapis.com/v1/places:searchText`, `X-Goog-FieldMask: places.id`, `pageSize` 1, `locationBias` de
  1 km alrededor del punto del enlace, `textQuery` = nombre + líneas de la Ubicación) y después Place Details (`GET
  https://places.googleapis.com/v1/places/{id}`, `X-Goog-Api-Key` y `X-Goog-FieldMask:
  id,displayName,rating,userRatingCount,reviews,googleMapsUri`). Se guarda el texto original de cada reseña
  (`originalText`, si no `text`), sin tocarlo; la fecha relativa la escribe el Hub en el idioma del visitante (desde
  `publishTime`), así una sola respuesta sirve para todos los idiomas. Solo se guardan enlaces `https://`.
  Caché: `website:reviews:<slug>:<place id>` un día (o `failed` 10 minutos), `website:place:<slug>:<hash>` el sitio
  encontrado por nombre o enlace corto, y `website:reviews-lock:…` (30 s) para que pregunte un solo proceso. Nunca dentro
  de una transacción: `services.refresh_reviews` corre tras el COMMIT de guardar un sitio nuevo y de publicar (este
  borra antes lo guardado) y en `public_home.respond` cuando la página no está en caché y no hay nada guardado; una
  respuesta nueva se guarda también en `Site.reviews_snapshot`, que vale 30 días y solo para su sitio. La vista previa,
  `website.site.get` (la nota del editor) y `website.public.reviews` solo leen. El bloque se pinta igual en el servidor
  (`sections/reviews.html`) y en el paquete (`frontend/public/reviews.ts`, que rehace el resumen y las tarjetas):
  `frontend/public/reviews.fixture.json` guarda ese marcado y lo comprueban los dos lados. Sin foto del autor (la CSP
  solo deja imágenes del Hub) ni logotipo: «Google Maps» va en texto, con `translate="no"`, como piden las normas de
  Google. **Clave**: `GOOGLE_PLACES_API_KEY` (`config/settings.py`, `.env.example`); en AWS va en Secrets Manager y en la
  definición de tarea del Hub (Terraform, pendiente en `aws/`). Restringirla a la Places API (New).
- **Migración 0004** (`0004_site_reviews_snapshot`, reversible): añade `Site.reviews_snapshot` (JSON, `{}` por defecto).
- La subida va en base64 dentro del JSON de la operación (como el certificado de VeriFactu), con
  `accept_body_up_to(7 100 000)` en su ruta: una sola puerta para la SPA, las API keys y el asistente.
- El QR es `qrcode` (la misma librería del QR de VeriFactu), corrección media y zona tranquila de cuatro módulos.
- El admin del Hub (`hubs.erplora.com/admin`) es de solo lectura salvo `is_live` (desconectar una página por
  soporte): no se añade ni se borra nada desde allí, y esa escritura no deja aviso.
- Asistente: las cinco operaciones que usa (`website.site.get`, `website.site.save`, `website.site.publish`,
  `website.site.unpublish` y `website.catalog.categories`) declaran `ai={"description"…}`, con `risk` `normal` en las
  acciones; las seis que no son herramienta, a propósito, no lo llevan: la vista previa (HTML para el marco del
  editor), el QR (una imagen en base64), la subida (un fichero en base64 de hasta 5 MB) y las tres lecturas públicas de
  los visitantes, sin sesión. Esas seis esperan al marcador `INTERNAL` y al check `live.E017` de la ronda 2026-10-22b
  (PLAN §30), que aún no existen en `packages/live`. Lo comprueba `tests/test_apps.py`, que también exige descripción
  en cada campo de `SaveIn`.
- **Paletas** (`palettes.json` + `palettes.py`, ronda 2026-10-22): las ocho paletas, cada una con su juego claro y
  oscuro (principal, página, franjas, texto, enlaces y bordes) y el color secundario; el editor lee el mismo fichero.
  `tests/test_palettes.py` comprueba WCAG AA (4,5:1) en los dos modos para texto, texto atenuado, enlaces, botones y
  el color secundario; los dos colores del propietario sobre cualquier paleta (`custom`) se derivan en `palettes._derived` (fondo blanco y uno oscuro teñido
  del color, texto AAA, enlaces y botones movidos hacia negro o blanco solo lo que haga falta) y pasa la misma prueba
  con colores difíciles (amarillo, gris medio, blanco, negro, neón). El tema es `{palette, custom, mode}`: `custom` son
  los dos colores cambiados sobre la paleta, `null` = los de la paleta (el servidor guarda como `null` el par propio
  de la paleta, y el editor lo pone a `null` al elegir otra paleta o con «Restablecer colores»).
- **Pintar la paleta**: `render._theme` escribe un solo `<style>` con las variables de Bootstrap 5.3 (`--bs-primary`,
  `--bs-body-bg`, `--bs-body-color`, `--bs-link-color`, `--bs-tertiary-bg`, `--bs-border-color`… y sus `-rgb`) para
  `data-bs-theme="light"` y para `"dark"`, más tres `--ws-*` que Bootstrap no tiene (el texto sobre el color principal
  y sobre el secundario, y el tono del principal al pasar el ratón). `<html>` lleva `data-bs-theme` (claro para
  automático) y `data-ep-mode`; `frontend/public/mode.ts` (en el paquete público, nada en línea) pone el modo del
  dispositivo y lo sigue. La vista previa es la misma página y se comporta igual.
- **Solo Bootstrap en las plantillas**: el marcado usa los componentes y utilidades de Bootstrap 5.3 (rejilla, navbar
  con collapse, card, list-group, `ratio`, `object-fit-cover`…). `frontend/public/site.css` es la única hoja propia:
  pasa la paleta a las variables de los botones primarios, de `text-bg-*` y de la navbar (donde Bootstrap escribe un
  color fijo) y dibuja con ganchos `ws-*` lo que Bootstrap no tiene: la barra translúcida (`ws-glass`; no se llama
  `ws-nav` porque `nav` ya es una clase de Bootstrap y el test lo prohíbe), el velo de la portada (`ws-hero-overlay`),
  el degradado sin portada (`ws-hero-glow`), la inicial (`ws-monogram`), los títulos enormes (`ws-mega`), el botón
  fantasma (`ws-btn-ghost`), la línea sobre los títulos (`ws-eyebrow`), las secciones (`ws-section`, `ws-rule`), las
  fichas y sus iconos (`ws-chip`, `ws-glyph`, `ws-icon` y `ws-icon-<nombre>`), las tarjetas que suben al pasar el ratón
  (`ws-lift`), el degradado del catálogo (`ws-thumb`), el panel del mapa (`ws-map`), el marco de la foto
  (`ws-frame`), el zum de las fotos de la galería (`ws-zoom`) y la media estrella de las reseñas (`ws-star-half`; la
  estrella es `ws-icon-star`), además de la letra de cada plantilla. Los iconos son
  de Ionicons (MIT, el juego `ion:`) tal como los
  trae `@erplora/ui`, escritos en `site.css` como máscaras CSS (la página no tiene script para pintarlos ni red para
  pedirlos): `frontend/public/icons.test.ts` comprueba que cada uno es exactamente el de `ionicons/icons` y que es
  relleno (los de contorno dibujan su trazo con clases de `ion-icon` que una máscara no ve). El catálogo se pinta igual
  en el servidor (`sections/catalog.html`) y en el paquete (`catalog.ts`): `frontend/public/catalog.fixture.json`
  guarda ese marcado y lo comprueban los dos lados (`tests/test_render.py` y `catalog.test.ts`).
  `frontend/public/classes.test.ts` recorre
  todas las plantillas y el catálogo que reconstruye el paquete: cada clase es de Bootstrap (leída del `bootstrap.css`
  instalado) o un gancho `ws-*` definido en `site.css`, ningún gancho sobra ni sustituye a una utilidad que exista, y
  ninguna clase se calcula con `{{ … }}`. Letras: solo pilas del sistema (CSP, nada por CDN), elegidas para macOS,
  iOS, Windows y Android.
- **Plantillas: inspiración y licencias**: se tomaron ideas de composición, no ficheros; las cuatro son plantillas
  Django propias. **Clásica**, de «Business Casual» de Start Bootstrap; **Moderna**, de «Agency» de Start Bootstrap y
  de los ejemplos «Heroes» y «Features» de Bootstrap; **Minimalista**, de «Clean Blog» de Start Bootstrap;
  **Llamativa**, de «Grayscale» y «One Page Wonder» de Start Bootstrap. Licencia MIT en todos (Start Bootstrap LLC;
  The Bootstrap Authors); registro en `docs/licences.md` de la raíz de erplora-next.
- **Migración 0002** (`0002_theme_palettes`, reversible, solo JSON): el tema de antes `{primary, accent, mode}` del
  borrador y de lo publicado pasa a `{palette: "custom", custom: {primary, accent}, mode}`, así que ninguna página
  cambia de colores; a la inversa, una paleta vuelve a sus dos colores (congelados en la migración) y automático a
  claro.
- **Migración 0003** (`0003_theme_overrides`, reversible, solo JSON): «Tus colores» deja de ser una paleta; un tema
  `{palette: "custom", custom}` pasa a `ocean` con los mismos dos colores (se pinta igual: la página sale de ellos sea
  cual sea la paleta) y los colores que una paleta guardaba para un «Tus colores» posterior se descartan (nunca se
  pintaron y ahora se pintarían). Borrador y publicado por igual.
- **Escribir en el editor** (regresión de 2026-10-22): el grupo de secciones (`ion-accordion-group`) guarda las
  abiertas en el estado de la página (`openSections`) y solo atiende a su propio `ionChange`. Antes llevaba un valor
  fijo y Vue lo volvía a poner en cada pulsación: la sección abierta se plegaba, el campo perdía el foco y la página
  saltaba. Lo cubren `WebsitePage.test.ts` («a section opened by hand stays open…») y la e2e, que escribe tecla a
  tecla y cruza un autoguardado.
- **Tests por flujo** (cierre de la migración, APP-WEBSITE): servidor en `apps/website/tests/` (un `test_<fichero>.py`
  por fichero), pantallas en `frontend/**/*.test.ts` y, de punta a punta, `tests/e2e/website-flows.spec.ts` (un test
  por flujo con su clave en el título, en 390, 834 y 1440 px, capturas `APP-WEBSITE-<clave>-<ancho>`) y
  `tests/e2e/website.spec.ts` (las cuatro plantillas en claro y oscuro, la paleta y la regresión de escribir tecla a
  tecla). Las e2e nunca preguntan a Google: `website-flows.spec.ts` se niega a correr con `GOOGLE_PLACES_API_KEY` y
  WEBSITE-F12 enseña las reseñas desde una última respuesta buena escrita en la fila del sitio.

## Lo que NO hace, a propósito

- Una sola página por negocio: sin páginas adicionales ni `/p/<página>`.
- Sin dominio propio por negocio (ADR-0502), sin HTML, CSS ni JS del usuario y sin más plantillas que las cuatro.
- El horario no se importa de Horarios; no hay enlace de reservas hasta que exista la página de Reservas online en
  `/p/…`.
- Las imágenes se guardan tal cual (sin variantes de tamaño ni recorte, y sin quitarles los metadatos EXIF); no se
  borran las que dejan de usarse ni las versiones antiguas.
- Sin sitemap ni robots más allá de la etiqueta `noindex` de la vista previa.
- La galería no lleva textos por foto ni un visor a pantalla completa: cada foto se abre entera en otra pestaña.
- Las reseñas de Google son las que da Google (cinco como mucho, las más relevantes): sin todas las reseñas, sin
  responderlas desde ERPlora, sin reseñas propias y sin la foto del autor (la página no carga imágenes de fuera: va su
  inicial). Sin la clave de Google en el servidor no se pregunta nada.
- La firma «© <año> ERPlora» del pie no se quita ni se cambia: el nombre y los datos legales del negocio van en la
  línea del pie.
- La activación real del módulo por negocio (`AppActivation`) llega en la fase 2.

## Cómo son las páginas (para quien lo mantiene)

- `frontend/routes.ts`: `/website` → `pages/WebsitePage.vue`.
- Componentes: `TemplatePicker` (las cuatro tarjetas, dibujos en CSS con los colores de la paleta), `PalettePicker`
  (las paletas en tarjetas, de `palettes.json`, con los dos `ColorInput` de los colores a la vista y «Restablecer
  colores»), `HoursEditor`, `GalleryEditor` (las fotos de la galería: una `ImageUpload` por foto, flechas para
  ordenarlas y otra `ImageUpload` para añadir al final, hasta 12), `ReviewsEditor` (el enlace de Google Maps y la nota
  de cómo están las reseñas, de `website.site.get` → `reviews`), `CategoryPicker` (lee
  `website.catalog.categories` al cambiar la fuente), `PreviewFrame` (el iframe de `/api/website/site/preview`),
  `ShareDialog` (`website-share-dialog`; el botón que lo abre es `website-share`); de `@erplora/ui/components`, `ColorInput` (en `PalettePicker`), `ImageUpload`, `InlineFeedback` y
  `useConfirm`.
- `lib/draft.ts` (copia del borrador, comparación, errores por campo), `lib/hours.ts`, `lib/upload.ts` (fichero →
  base64 → `website.image.upload`), `lib/palettes.ts` (las paletas del fichero compartido, los colores de un tema:
  `ownColours`, `currentColours`, `withColour` y `themeColours`).
- Textos en `frontend/locale/{en,es}.json`; los de la página pública, en el catálogo de Django de la app.
