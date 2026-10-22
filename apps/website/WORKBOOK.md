# Workbook — Página web (app)
Prefijo: WEBSITE
Alcance MVP: transversal (peluquería y restaurante: la página del negocio en su propia dirección)
Estado de la app: completa (2026-10-21)
Lo que no entra todavía: ver «Lo que NO hace, a propósito».

> Manual de usuario y especificación de la app `website`. Nace en la ronda 2026-10-21 (PLAN §29; diseño de
> referencia `docs/plans/como-podriamos-contruir-una-inherited-sketch.md`): no es un porte del producto actual, que
> no tenía página pública por negocio. Cada flujo pasa a `hecho` cuando sus tests están en verde (servidor, páginas y
> la e2e `tests/e2e/website.spec.ts`).

## Para qué sirve y para quién

Página web le da a cada negocio una página sencilla en su propia dirección de ERPlora
(`https://<tu-negocio>.erplora.com/`). El propietario elige uno de cuatro diseños, rellena sus secciones (nombre y
logotipo, título y foto de portada, unas palabras sobre el negocio, su catálogo, cómo contactar, dónde está) y sus
colores, esconde lo que no usa y publica. Quien abre esa dirección sin haber entrado ve la página; el equipo entra
desde su botón **Entrar**, que todas las plantillas llevan y no se puede quitar. Mientras la página no está publicada
(o se ha desconectado), la dirección sigue llevando al acceso del equipo, como siempre.

Está pensada como las páginas de Square Online, Wix o Squarespace, pero reducida a lo que un salón o un restaurante
necesita: secciones fijas, sin arrastrar bloques, sin HTML ni código del usuario. Cambiar de diseño no pierde nada:
el contenido y el diseño se guardan por separado.

## Antes de empezar

- La app está en la categoría **Organización** y no necesita ninguna otra. Si el negocio tiene **Inventario** o
  **Servicios**, la sección Catálogo puede mostrar sus productos a la venta o sus servicios ofrecidos.
- Solo el **propietario** y el **administrador** cambian, publican o desconectan la página; el **responsable** la ve
  y comparte su dirección y su QR; el **empleado** no la ve.

## Pantallas

### Página web (`/website`)
Arriba, el estado: «Tu página web aún no está en línea…» (nunca publicada), «Tu página web está fuera de línea…»
(desconectada) o «Tu página web está en línea en …» (con la dirección), y «Tienes cambios que aún no están
publicados» cuando el borrador ha cambiado desde la última publicación. Al lado, **Guardar**, **Publicar**,
**Desconectar** (solo en línea) y **Compartir y QR**, y si todo está guardado o no.

Debajo, el editor y la vista previa. En un ordenador, uno al lado del otro; en una tableta o un móvil, una pestaña
**Editar / Vista previa** cambia entre los dos.

- **Diseño**: cuatro tarjetas con un dibujo de cada plantilla en los colores de la paleta: **Clásica** (centrada y
  atemporal: nombre y títulos con serifa, cabecera centrada sobre una franja suave y cada sección en una tarjeta),
  **Moderna** (barra fija, título y foto lado a lado y cada sección en dos columnas), **Minimalista** (una sola
  columna estrecha con mucho aire, letra de lectura con serifa y líneas finas entre secciones) y **Llamativa** (barra
  oscura, cabecera a todo el ancho en el color principal con mayúsculas grandes y un botón fuerte). Las cuatro sirven
  para un restaurante, una peluquería, una tienda o un servicio.
- **Colores**: ocho paletas en tarjetas con sus colores sobre el fondo claro y el oscuro, la elegida resaltada:
  **Océano**, **Bosque**, **Terracota**, **Pizarra**, **Rosa**, **Arena**, **Medianoche** y **Oliva**. Debajo, dos
  campos de color (**Color principal** y **Color secundario**) con los de la paleta elegida: cambiarlos hace tuya la
  paleta, y entonces aparece **Restablecer colores**, que vuelve a los de la paleta. Elegir otra paleta muestra los
  suyos (los cambios de la anterior se descartan). Cada paleta trae su versión clara y oscura y se lee bien en las dos
  (WCAG AA: textos, enlaces y botones); con colores cambiados, el fondo, las franjas y el texto salen de los dos
  colores y un color que no se leería se ajusta lo justo.
- **Fondo de la página**: **Claro**, **Oscuro** o **Automático** (por defecto): automático sigue el dispositivo de
  cada visitante, oscuro si está en modo oscuro y claro si no; lo dice una nota debajo.
- **Secciones**, en este orden, cada una plegable:
  - **Barra superior** (siempre en la página): nombre del negocio (hasta 80) y logotipo; **Entrar** siempre.
  - **Cabecera** (siempre): título (hasta 80), lema (hasta 160) y foto de portada.
  - **Sobre nosotros**: interruptor **Mostrar**, encabezado (vacío = «Sobre nosotros»), texto (hasta 4000, con
    **negrita**, listas y enlaces en Markdown; nada de HTML) y una foto.
  - **Catálogo**: **Mostrar**, encabezado (vacío = «Nuestros productos» o «Nuestros servicios»), **Qué mostrar**
    (Nada, Productos o Servicios; solo los de las apps que el negocio tiene), las **Categorías** (ninguna elegida =
    todas) y **Mostrar precios**.
  - **Contacto**: **Mostrar**, encabezado, teléfono, WhatsApp (con prefijo), correo, Instagram, Facebook, TikTok y X
    (enlaces `https://`) y, si se activa **Mostrar el horario**, el horario de la semana: cada día abierto o cerrado
    y hasta tres franjas (una hora de cierre anterior a la de apertura pasa de medianoche).
  - **Ubicación**: **Mostrar**, encabezado, hasta cuatro líneas de dirección y un enlace al mapa (`https://`, se abre
    aparte).
  - **Pie de página** (siempre): una línea de texto (por ejemplo, la razón social) y **Entrar**.
- Las imágenes (jpeg, png o webp, hasta 5 MB y 8000 px por lado) se suben desde cada campo de imagen: **Elegir
  imagen**, y después su miniatura, **Cambiar imagen** y **Quitar**.
- **Vista previa**: la página tal y como la verán los clientes con el diseño y el borrador de ahora, a ancho de
  ordenador o de móvil, y **Recargar**. Se recarga sola tras cada guardado.

### Compartir y QR
La dirección de la página web con **Copiar enlace**, su código QR y **Descargar PNG** (para imprimir) y
**Descargar SVG** (para ampliar sin perder calidad). Avisa de que, en el dispositivo donde se ha entrado, la
dirección abre la app (para ver la página: el móvil o una ventana privada) y, si la página no está en línea, de que
la dirección aún lleva al acceso del equipo.

### La página pública (`/` del negocio)
La plantilla elegida con lo publicado: barra superior con el nombre, el menú de secciones (plegado en un móvil) y
**Entrar**; cabecera (con un botón a la primera sección, salvo en la minimalista); las secciones que se muestran y
tienen contenido; pie con **Entrar**. Se adapta a móvil, tableta y ordenador (Bootstrap 5.3) sin desplazamiento
lateral, con la paleta elegida en claro o en oscuro; en automático, sigue el dispositivo del visitante y cambia si
este cambia con la página abierta (sin JavaScript, se ve en claro). El catálogo se pinta con lo publicado y, al abrir la
página, se refresca con los productos o servicios de ese momento y sus precios en el idioma del visitante. El resto
de textos de la página (Entrar, los días, los encabezados por defecto) sale en el idioma del navegador (inglés o
español); lo que escribe el propietario, tal cual.

## Estados de cada pantalla

| Estado | Qué ve la persona |
|---|---|
| Cargando | «Cargando tu página web…» con un indicador; la vista previa, su indicador hasta que llega la página. |
| Nunca publicada | El aviso «Tu página web aún no está en línea. Publícala para que tus clientes puedan verla.» |
| Fuera de línea | «Tu página web está fuera de línea. Publícala para volver a ponerla en línea.» |
| En línea | «Tu página web está en línea en …» y, con cambios sin publicar, «Tienes cambios que aún no están publicados.» |
| Guardando | «Guardando…»; luego «Todos los cambios guardados», o «Cambios sin guardar» mientras hay cambios. |
| Error | Al cargar: «No se pudo cargar la página web» con el motivo. Al guardar: el aviso y el mensaje bajo cada campo, sin perder lo escrito. Al publicar o desconectar: un aviso. La vista previa que no llega: «No se pudo cargar…» con **Recargar**. Un catálogo cuyas categorías no se pueden leer lo dice bajo el selector. |
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

### WEBSITE-F01 Rellenar y guardar el borrador
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, asistente, API
Pantalla: Página web
Pasos:
1. Abre **Página web** y despliega una sección.
2. Escribe: el borrador se guarda solo dos segundos después del último cambio, o al pulsar **Guardar**; también al
   salir de la pantalla si quedaba algo.
Entra: la plantilla, los colores y el contenido completo de las siete secciones. Las imágenes se nombran por su id;
la dirección donde se sirven la escribe el servidor.
Sale: el borrador guardado; los clientes no ven nada hasta publicar. Aviso `website.site.updated` (solo si algo
cambió).
Si falla: bajo cada campo, sin perder lo escrito: textos demasiado largos, un enlace que no empieza por `https://`,
un teléfono o un correo que no lo son, dos franjas iguales o un día repetido en el horario, «Esta imagen no se subió
a la página web de este negocio: vuelve a subirla.»

### WEBSITE-F02 Elegir el diseño, la paleta y el fondo
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, asistente, API
Pasos: pulsa una de las cuatro tarjetas de **Diseño**; una de las paletas y, si quieres, cambia sus dos colores
(**Restablecer colores** vuelve a los suyos); el fondo, **Claro**, **Oscuro** o **Automático**. Se guarda como en F01.
Sale: el mismo contenido con otro diseño o con otros colores; nada se pierde al cambiar.
Si falla: un color mal escrito no se guarda y el campo lo dice: «Escribe el color como #RRGGBB, por ejemplo #1A73E8.»

### WEBSITE-F03 Mostrar u ocultar una sección
Estado: hecho (servidor y pantalla)
Pasos: en Sobre nosotros, Catálogo, Contacto o Ubicación, el interruptor **Mostrar**. La barra superior, la cabecera
y el pie no se pueden ocultar.
Sale: lo oculto no se pinta en la página ni sale por la API pública; se conserva para volver a mostrarlo. Una sección
que se muestra pero no tiene nada (sin texto ni foto, sin datos de contacto, sin dirección ni mapa, sin catálogo)
tampoco se pinta.

### WEBSITE-F04 Subir una imagen
Estado: hecho (servidor y pantalla)
Pasos: en el logotipo, la portada o la foto de Sobre nosotros, **Elegir imagen**; **Quitar** la deja vacía.
Entra: jpeg, png o webp, hasta 5 MB y 8000 píxeles por lado; se comprueba el contenido, no solo el nombre.
Sale: la imagen guardada en el almacén de ficheros del negocio (S3 en AWS) bajo un nombre sacado de su contenido; la
misma imagen dos veces es un solo fichero. Aviso `website.image.uploaded`.
Si falla: «El archivo no llegó entero…», «El archivo está vacío.», «La imagen puede pesar 5 MB como mucho.»,
«Este archivo no es una imagen PNG.» (o JPEG, WEBP), «La imagen puede medir 8000 píxeles por lado como mucho.».

### WEBSITE-F05 Mostrar el catálogo
Estado: hecho (servidor y pantalla)
Pasos: en Catálogo, **Qué mostrar**: Productos (los de Inventario a la venta: activos y no agotados) o Servicios (los
ofrecidos); si quieres, las categorías y si se ven los precios.
Sale: al publicar, el catálogo se copia en lo publicado, agrupado por categoría en su orden (lo que no tiene
categoría, al final), hasta 200 elementos. La página pública lo refresca al abrirse.
Precios: «15,00 €», «Desde 40,00 €» y «20,00 € / hora» (servicios con precio desde o por hora), «Gratis»; un precio
variable no se muestra.

### WEBSITE-F06 Ver la vista previa
Estado: hecho (servidor y pantalla)
Pasos: la vista previa está al lado (ordenador) o en la pestaña **Vista previa** (tableta y móvil); **Ordenador** o
**Móvil** cambia su ancho.
Sale: el borrador pintado por el mismo código que la página pública, con el catálogo de ese momento; los enlaces no
se siguen y los buscadores no la indexan.

### WEBSITE-F07 Publicar
Estado: hecho (servidor y pantalla)
Pasos: **Publicar** → «¿Publicar tu página web?» → **Publicar**. Si había algo sin guardar, se guarda antes.
Sale: lo publicado = el borrador de ahora (diseño, colores, contenido y la copia del catálogo), una versión más y la
página en línea. Aviso `website.site.published` (con la versión). El borrador puede seguir cambiando sin tocar lo
publicado.
Si falla: «No se pudo publicar la página web» y lo publicado sigue como estaba.

### WEBSITE-F08 Desconectar la página
Estado: hecho (servidor y pantalla)
Pasos: **Desconectar** → «¿Desconectar tu página web?» → **Desconectar**.
Sale: la dirección vuelve a llevar al acceso del equipo; nada se pierde y publicar de nuevo sigue con la versión
siguiente. Aviso `website.site.unpublished`. Ya desconectada, no hace nada.

### WEBSITE-F09 Compartir la dirección y el QR
Estado: hecho (servidor y pantalla)
Actor: propietario, administrador, responsable
Pasos: **Compartir y QR** → **Copiar enlace**, **Descargar PNG** o **Descargar SVG**.
Sale: la dirección pública del negocio (como la ve el navegador: `https://<negocio>.erplora.com/`) y su QR.

### WEBSITE-F10 Visitar la página pública
Estado: hecho (servidor y e2e)
Actor: cualquiera, sin cuenta
Pasos: abre la dirección del negocio. **Entrar** lleva al acceso de ERPlora y, de vuelta, a la app.
Sale: la página publicada en el idioma del navegador, sin cookies, con su propia política de seguridad (sin scripts
del usuario: solo el paquete de la página, Bootstrap y el refresco del catálogo). Con sesión abierta, la dirección
abre la app como siempre.

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

Las dos públicas responden solo con la página en línea (si no, 404 `website.not_published`) y cuentan a cada
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
borrador lleva su descripción (nombre, lema, texto de Sobre nosotros, contacto, horario, ubicación, plantilla, paleta y
fondo), y la descripción de guardar le dice que el borrador se manda entero: lo lee primero con `website.site.get`,
cambia solo lo pedido y lo devuelve. Ejemplo: «Ponme en la web el horario de lunes a viernes de 9 a 20» → lee el
borrador, pone en `contact.hours` los cinco días con la franja `09:00`–`20:00` (deja el resto como estaba) y llama a
`website.site.save`; si además dice «y publícala», `website.site.publish`. No son herramientas del asistente, a
propósito: la vista previa (`website.site.preview`, una página HTML), la subida de imágenes (`website.image.upload`,
un fichero en base64 de hasta 5 MB) y el QR (`website.qr.get`, una imagen en base64), que se usan desde la pantalla, ni
las dos lecturas públicas de los visitantes (`website.public.*`).

### Lo que avisa

| Aviso | Cuándo | Qué lleva | Servicio |
|---|---|---|---|
| Borrador guardado | Guardar con algún cambio | `id` | `website.site.updated` |
| Página publicada | Publicar | `id`, `version` | `website.site.published` |
| Página desconectada | Desconectar una página en línea | `id`, `version` | `website.site.unpublished` |
| Imagen subida | Subir una imagen | `id` | `website.image.uploaded` |

### A qué reacciona y lo que necesita de otras apps
- No reacciona a avisos de otras apps y no requiere ninguna (`requires = []`).
- **Inventario** y **Servicios**, solo si están instaladas: el catálogo los lee por el nombre de sus consultas
  (`inventory.product.list_for_sale`, `inventory.category.list`, `inventory.product_category.list`,
  `service.service.list_for_sale`, `service.category.list`), con un contexto que solo puede leerlos; sin la app, el
  catálogo sale vacío, nunca un error.
- De la plataforma: el registro del hub (su id, para el almacén de ficheros; `base.operations.hub_id`), el almacén
  `storages["hub_files"]` y la vista `/p/media/…` (`base.storage`, `base.media`), el límite por visitante
  (`base.throttle`) y la entrada `/` (`base.public_home`, que llama a `apps/website/public_home.py`).

### Quién puede qué

| Permiso | Propietario | Administrador | Responsable | Empleado | Servicio |
|---|---|---|---|---|---|
| Ver el estado, compartir la dirección y el QR | sí | sí | sí | no | `website.view` |
| Cambiar, subir imágenes, previsualizar, publicar y desconectar | sí | sí | no | no | `website.manage` |

## Lo que NO hace, a propósito

- Una sola página por negocio: sin páginas adicionales ni `/p/<página>`.
- Sin dominio propio por negocio (ADR-0502), sin HTML, CSS ni JS del usuario y sin más plantillas que las cuatro.
- El horario no se importa de Horarios; no hay enlace de reservas hasta que exista la página de Reservas online en
  `/p/…`.
- Las imágenes se guardan tal cual (sin variantes de tamaño ni recorte, y sin quitarles los metadatos EXIF); no se
  borran las que dejan de usarse ni las versiones antiguas.
- Sin sitemap ni robots más allá de la etiqueta `noindex` de la vista previa.
- La activación real del módulo por negocio (`AppActivation`) llega en la fase 2.

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
- **Una sola guarda para lo público**: `/` (`public_home.is_published`) y la API pública (`website.public.*`) pasan por
  `queries._live`: el módulo encendido en el hub (en la fase 1, toda app instalada, `base.relay.active_apps`; con él
  apagado la API responde 404 `app_inactive` y `/` salta al login) y una publicación en línea de ese hub (si no,
  404 `website.not_published`).
- Anatomía completa: `apps.py`, `models.py`, `schemas.py`, `render.py`, `csp.py`, `public_home.py`, `storage.py`,
  `qr.py`, `queries.py`, `services.py`, `events.py`, `live.py`, `api.py`, `admin.py`, `locale/`, `templates/website/`
  y `frontend/`, con un `tests/test_<fichero>.py` por fichero. **Sin `views.py` ni `urls.py`** (PLAN §29): `/` es de
  `base` y `/p/media/…` también.
- Modelos: `Site` (una por hub, `hub_id` único: `template`, `theme`, `content` = borrador; `published_content` =
  plantilla, tema, contenido y la copia del catálogo de la última publicación; `published_version`, `published_at`,
  `is_live`) e `Image` (`hub_id` con índice, `key` única, `sha256`, tipo, ancho, alto y tamaño). UUIDv7.
- **Contenido = JSON validado** por `schemas.Content` (siete secciones cerradas; topbar, hero y footer sin
  `hidden`); `render_site` lo valida otra vez antes de pintar: una fila escrita a mano no cuela marcado. Lo que
  escribe el propietario pasa por el escape de Django, y el texto de Sobre nosotros por `live.markdown` (nh3, sin
  imágenes). Los enlaces solo `https://`.
- **Render y caché**: `public_home.respond` pinta la plantilla con lo publicado, en el idioma de `Accept-Language`
  (nunca una cookie), y guarda el HTML una hora en
  `website:home:<slug>:<versión>:<idioma>:<APP_VERSION>`: publicar cambia la versión y un despliegue cambia los
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
  barra, por atributos `data-bs-*`) y `apps/website/frontend/public/{site.css,mode.ts,catalog.ts}`. El refresco del catálogo
  reconstruye el bloque con `createElement`/`textContent`, nunca `innerHTML`; si falla, se queda la copia publicada.
- **Imágenes**: `services.upload_image` valida con Pillow (tipo real, tamaño, píxeles), guarda en
  `storages["hub_files"]` con clave por contenido y responde la URL de `base.media` (`/p/media/<hex>/website/img/…`,
  caché de un año). `base.media` solo sirve las carpetas públicas (`PUBLIC_FOLDERS`, hoy `website/img/`): el almacén
  guarda también documentos privados de otros módulos, que nunca salen por ahí; un nombre que es una carpeta en disco
  responde 404. Al guardar, cada imagen del contenido tiene que ser una subida de este hub y su URL la escribe el
  servidor.
- La subida va en base64 dentro del JSON de la operación (como el certificado de VeriFactu), con
  `accept_body_up_to(7 100 000)` en su ruta: una sola puerta para la SPA, las API keys y el asistente.
- El QR es `qrcode` (la misma librería del QR de VeriFactu), corrección media y zona tranquila de cuatro módulos.
- El admin del Hub (`hubs.erplora.com/admin`) es de solo lectura salvo `is_live` (desconectar una página por
  soporte): no se añade ni se borra nada desde allí, y esa escritura no deja aviso.
- Asistente: las operaciones que usa declaran `ai={"description"…}` y `risk` en las acciones; las de solo pantalla y
  las públicas no llevan `ai=` (`tests/test_apps.py`, que también exige descripción en cada campo de `SaveIn`).
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
  color fijo) y da a cada plantilla su letra y su espaciado con ganchos `ws-*` (`ws-display`, `ws-tracking`,
  `ws-hero`, `ws-logo`, `ws-prose`, `ws-btn-contrast` y uno por plantilla). `frontend/public/classes.test.ts` recorre
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

## Cómo son las páginas (para quien lo mantiene)

- `frontend/routes.ts`: `/website` → `pages/WebsitePage.vue`.
- Componentes: `TemplatePicker` (las cuatro tarjetas, dibujos en CSS con los colores de la paleta), `PalettePicker`
  (las paletas en tarjetas, de `palettes.json`, con los dos `ColorInput` de los colores a la vista y «Restablecer
  colores»), `HoursEditor`, `CategoryPicker` (lee
  `website.catalog.categories` al cambiar la fuente), `PreviewFrame` (el iframe de `/api/website/site/preview`),
  `ShareDialog`; de `@erplora/ui/components`, `ColorInput` (en `PalettePicker`), `ImageUpload`, `InlineFeedback` y
  `useConfirm`.
- `lib/draft.ts` (copia del borrador, comparación, errores por campo), `lib/hours.ts`, `lib/upload.ts` (fichero →
  base64 → `website.image.upload`), `lib/palettes.ts` (las paletas del fichero compartido, los colores de un tema:
  `ownColours`, `currentColours`, `withColour` y `themeColours`).
- Textos en `frontend/locale/{en,es}.json`; los de la página pública, en el catálogo de Django de la app.
