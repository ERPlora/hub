# WORKFLOW — Hub (servidor)

Prefijo: HUB
Alcance MVP: transversal

> Contrato de comportamiento del **servidor** del hub (pm#620, pm#621, hub#2491): `crates/server`,
> `crates/runtime` y los crates pequeños sin `WORKFLOW.md` propio. Se lee antes de tocar ese código y
> se actualiza en la misma PR que cambie un comportamiento. El detalle técnico vive en
> `architecture/hub/` (runtime-dispatcher, module-system, setup-status, public-claims, tenancy…);
> aquí se escribe lo que se observa. Las pantallas son de [apps/web/WORKFLOW.md](apps/web/WORKFLOW.md)
> (`HUB_SHELL`).
>
> **Para el integrador de la oleada 3**: cada apartado lleva al final una línea «Áreas del
> servidor que faltan aquí» donde se insertan los fragmentos de avisos, automatizaciones, acceso,
> impresión, negocio y datos, WhatsApp y asistente, y perfil fiscal. Lo que hay escrito antes de esa
> línea es lo común a todo el servidor y lo del área «Módulos y órdenes».

## Para qué sirve y para quién

El hub es el servidor de **un** negocio: una peluquería, un bar o una tienda que ERPlora aprovisiona
con su propia base de datos. No tiene funciones de negocio propias: las ponen las **aplicaciones**
(módulos) que el negocio instala desde el catálogo —Venta, Caja, Inventario, Citas, VeriFactu…—, y el
hub es quien las instala, las actualiza, las aísla entre sí y las sirve. Cada vez que alguien pide
datos o pide hacer algo, el hub decide si puede (sesión, permiso, PIN del responsable, plan
contratado, permisos de la app), comprueba lo que llega contra lo que la app declara, lo ejecuta en
una sola transacción con sus avisos a otras apps, y contesta con un código que la pantalla sabe
traducir. Además guarda lo que es del negocio y no de ninguna app (las personas y su acceso, los
ajustes, el perfil fiscal, la cola de impresión, las automatizaciones, el asistente).

Lo usan, sin verlo, todos los perfiles: **administrador** (instala apps, concede permisos, guarda
ajustes), **responsable** (aprueba con su PIN lo que un empleado no puede), **empleado** y **cajero**
(cobran y trabajan por las pantallas de las apps), el **asistente** (pide consultas y órdenes como
una persona más), y el **cliente** que, sin sesión, pide su factura en la página pública del tique.
Casi todos los flujos de este documento tienen como actor al **sistema** o a quien llama a la API: lo
que una persona hace en pantalla está en `HUB_SHELL`, y aquí está lo que el servidor garantiza.

### Qué gobierna cada fichero y qué código

| Área | Fichero | IDs | Código que gobierna |
|---|---|---|---|
| Módulos y órdenes: consultas, órdenes, puerta pública, redondeo | [workflow/modulos.md](workflow/modulos.md) | F01–F18 | `runtime`: dispatch, commands, queries, manifest, registry, native, wasm, wasm_cache, errors, error_registry, public_claim · `server`: dispatch_api, public_door, operations_catalog · crates `wasm-host`, `guest-sdk` |
| Módulos y órdenes: aplicaciones, ajustes, paneles, puesta en marcha | [workflow/modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) | F19–F35 | `runtime`: installer, module_lifecycle, module_update, module_package, lifecycle, loader, seed, migrations, migration_guard, capabilities, setup_status, settings_api (permisos de módulo), ui · `server`: module_api, install, install_guard, module_reconcile, settings (permisos de módulo) · crates `source`, `installer` |
| Avisos entre módulos | `workflow/avisos.md` | F50–F79 | `runtime`: events, events_api, event_shape, outbox, host_notify, scheduler · `server`: event_stream, outbox_admin, notify_transport, activity |
| Automatizaciones | `workflow/automatizaciones.md` | F80–F129 | `runtime/src/flows/`, flows_api, secret_box · `server`: flows_api, flow_io, flows_header_media, agent_runner |
| Acceso, personas y plan | `workflow/acceso.md` | F130–F189 | `runtime`: access, identity, hub_users, roles, permissions, policies, pin_policy, elevation, devices, api_keys, update_history… · `server`: auth, members, elevation, api_keys, entitlement, readiness, boot, system… · crate `cloud-client` |
| Impresión | `workflow/impresion.md` | F190–F219 | `runtime`: printing, print_* , host_print · `server`: print, print_ws |
| Negocio y datos | `workflow/negocio-y-datos.md` | F220–F259 | `runtime`: settings, export, import, erasure, retention, activity_log, reset, module_storage, money_backfill · `server`: settings, export_import, media, ingest, reset · crates `db`, `sync` |
| WhatsApp y asistente | `workflow/mensajeria-y-asistente.md` | F260–F299 | `server`: whatsapp_*, inbound_poll, assistant*, call_budget, embed · crate `vector` |
| Perfil fiscal | `workflow/fiscal.md` | F300–F339 | `runtime`: fiscal, fiscal_profile, certificate, gateway_identity, producer_facts · `server`: gateway_enrolment, representation_grant |

Otros documentos del mismo repo: `apps/web/WORKFLOW.md` (`HUB_SHELL`, pantallas),
`crates/plugins/verifactu/WORKFLOW.md` (`HUB_VERIFACTU`, motor fiscal),
`crates/peripherals/WORKFLOW.md` (`HUB_PERIPHERALS`) y `apps/tauri/WORKFLOW.md` (`HUB_APP`). Por la
regla del ancestro, este fichero gobierna todo lo que no tiene uno más cercano.

Áreas del servidor que faltan aquí: (integrador) una frase por área si hace falta.

## Referencia adoptada

Lo que el hub adopta como **plataforma de aplicaciones** (se adopta esto, no más):

- [Odoo — aplicaciones y módulos](https://www.odoo.com/documentation/17.0/applications/general/apps_modules.html):
  instalar arrastra las dependencias; actualizar sin reinstalar; quitar una app avisa antes de lo
  que arrastra. Odoo borra los datos al desinstalar; ERPlora no (como Business Central).
- [Business Central — instalar y desinstalar extensiones](https://learn.microsoft.com/en-us/dynamics365/business-central/ui-extensions-install-uninstall):
  desinstalar conserva los datos por defecto; una app con dependientes solo se quita junto con
  ellos, tras enseñarlos; tras instalar, la app puede pedir su configuración obligatoria (la lista
  de puesta en marcha, HUB-F35).
- Shopify (apps): la app declara al instalarse los permisos que pide y el dueño los concede; una app
  sin permiso no ejecuta lo que lo necesita (Ajustes › Permisos, HUB-F32).
- Toast y Square: la aprobación del responsable con su código en el momento, para una sola acción
  (HUB-F05; referencia contrastada en el módulo de Venta, SALES-F14).
- Cuiner *QuieroFactura* y Ágora *Crear factura*: el tique lleva un código para pedir la factura
  completa desde casa (HUB-F16, HUB-F17); plazo:
  [RD 1619/2012, art. 11.2](https://www.boe.es/buscar/act.php?id=BOE-A-2012-14696).
- [JSON Schema](https://json-schema.org/): el contenido de cada orden y consulta se valida contra el
  esquema que declara su módulo, con sus valores por defecto (HUB-F04).
- [Ley 46/1998, art. 11](https://www.boe.es/buscar/act.php?id=BOE-A-1998-29550): la mitad exacta se
  redondea hacia arriba; es el redondeo común del dinero (HUB-F18).

Áreas del servidor que faltan aquí: (integrador) referencias de avisos, automatizaciones, acceso,
impresión, negocio y datos, WhatsApp y asistente, perfil fiscal.

## Antes de empezar

- El hub lo **aprovisiona ERPlora** con su base de datos, su identificador, su credencial de máquina y
  el correo del dueño, que nace administrador. Sin credencial de máquina el hub no puede instalar ni
  actualizar apps del catálogo (solo reponer las que ya tenía guardadas, HUB-F25).
- Las apps se instalan desde **Apps** (HUB-F19) o importando la plantilla del sector en
  Ajustes › Datos, que instala las suyas por la misma puerta.
- Si una app pide permisos de host (red, certificado, impresora, avisar, administrar
  automatizaciones), concédelos en **Ajustes › Permisos** (HUB-F32); sin ellos su motor no corre y
  su paso de puesta en marcha sigue pendiente.
- Recorre la lista «Termina de configurar tu negocio» de Inicio (HUB-F35): datos del negocio,
  impresora, equipo y los pasos de cada app.
- Cada app con ajustes tiene su pestaña «Ajustes» (HUB-F33); algunas, como Caja, solo empiezan a
  aplicar sus reglas cuando se guardan por primera vez.

Áreas del servidor que faltan aquí: (integrador) personas y PIN, perfil fiscal, impresoras,
automatizaciones, WhatsApp.

## Pantallas

El servidor solo pinta **una** pantalla propia; todas las demás son de `HUB_SHELL`
([apps/web/WORKFLOW.md](apps/web/WORKFLOW.md)) y los flujos de aquí las nombran como
`HUB_SHELL: <pantalla>`.

### Página pública para pedir la factura
Se llega escaneando el segundo QR del tique o escribiendo `/p/<código>` en el navegador; no pide
sesión ni ejecuta código de la página (formulario HTML, en español o inglés según el idioma del
negocio o `?lang=`). Aparece «Pide tu factura», la explicación, el «Código del tique», los campos
«NIF/CIF», «Nombre o razón social», «Domicilio», los desplegables que el tique ofrezca (país, tipo de
documento) y «Emitir mi factura». Hecha: «Tu factura está emitida» con la referencia. Con error: el
motivo encima del formulario, con lo escrito; código desconocido, caducado o demasiados intentos:
un mensaje sin formulario (HUB-F17). No se indexa en buscadores.

Áreas del servidor que faltan aquí: (integrador) si otra área sirve una página propia.

## Flujos

El detalle de cada flujo vive en `workflow/`, con la misma gramática y el mismo prefijo. Los huecos
(`parcial`, `no hecho`) dicen el porqué en su línea `Estado:`. El servidor no tiene flujos propios de
un solo sector, así que no usa la clave `Vertical:`.

| ID | Flujo | Estado | Fichero |
|---|---|---|---|
| HUB-F01 | Leer datos de un módulo | hecho | [workflow/modulos.md](workflow/modulos.md) |
| HUB-F02 | Pedir una lista con búsqueda, filtros, orden y páginas | hecho | [workflow/modulos.md](workflow/modulos.md) |
| HUB-F03 | Ejecutar una orden de un módulo | hecho | [workflow/modulos.md](workflow/modulos.md) |
| HUB-F04 | Comprobar el contenido de una orden contra su esquema y rellenar lo que falta | hecho | [workflow/modulos.md](workflow/modulos.md) |
| HUB-F05 | Pedir la aprobación de un responsable cuando falta el permiso | hecho | [workflow/modulos.md](workflow/modulos.md) |
| HUB-F06 | Comprobar que la orden cambió algo | hecho | [workflow/modulos.md](workflow/modulos.md) |
| HUB-F07 | Cambiar solo algunos campos de una ficha | hecho | [workflow/modulos.md](workflow/modulos.md) |
| HUB-F08 | Rechazar desde fuera las órdenes internas de un módulo | hecho | [workflow/modulos.md](workflow/modulos.md) |
| HUB-F09 | Avisar de un duplicado con el código del módulo | hecho | [workflow/modulos.md](workflow/modulos.md) |
| HUB-F10 | Ejecutar el manejador de un módulo y validar lo que propone | hecho | [workflow/modulos.md](workflow/modulos.md) |
| HUB-F11 | Darle al manejador los datos de otros módulos antes de ejecutar | hecho | [workflow/modulos.md](workflow/modulos.md) |
| HUB-F12 | Ejecutar el motor propio de un módulo de confianza | hecho | [workflow/modulos.md](workflow/modulos.md) |
| HUB-F13 | Bloquear las órdenes de un módulo mientras otro no cumpla su condición | parcial | [workflow/modulos.md](workflow/modulos.md) |
| HUB-F14 | Contestar un fallo con un código estable y sin detalles internos | hecho | [workflow/modulos.md](workflow/modulos.md) |
| HUB-F15 | Consultar qué órdenes y consultas acepta el hub | hecho | [workflow/modulos.md](workflow/modulos.md) |
| HUB-F16 | Emitir el localizador para que el cliente pida su factura | hecho | [workflow/modulos.md](workflow/modulos.md) |
| HUB-F17 | Canjear un localizador en la página pública | parcial | [workflow/modulos.md](workflow/modulos.md) |
| HUB-F18 | Redondear el dinero igual en todos los módulos | hecho | [workflow/modulos.md](workflow/modulos.md) |
| HUB-F19 | Instalar una aplicación del catálogo | parcial | [workflow/modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F20 | Rechazar un paquete que rompe las reglas del hub | hecho | [workflow/modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F21 | Aplicar las migraciones de un módulo con su guarda | hecho | [workflow/modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F22 | Sembrar los datos de partida de un módulo | hecho | [workflow/modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F23 | Actualizar una aplicación | parcial | [workflow/modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F24 | Consultar qué actualizaciones y versiones hay | hecho | [workflow/modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F25 | Reponer las aplicaciones al arrancar y actualizarlas solas | hecho | [workflow/modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F26 | Seguir lo que otra copia del hub instaló, actualizó, apagó o quitó | hecho | [workflow/modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F27 | Activar una aplicación | hecho | [workflow/modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F28 | Desactivar una aplicación preguntando antes si puede irse | parcial | [workflow/modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F29 | Desinstalar una aplicación | parcial | [workflow/modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F30 | Instalar un módulo desde una carpeta en modo desarrollo | hecho | [workflow/modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F31 | Servir el menú, las pantallas y los ficheros de las aplicaciones | hecho | [workflow/modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F32 | Conceder o retirar un permiso de host a una aplicación | hecho | [workflow/modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F33 | Leer y guardar los ajustes de un módulo | parcial | [workflow/modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F34 | Servir los datos de los paneles de Inicio | hecho | [workflow/modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F35 | Calcular la lista de puesta en marcha | hecho | [workflow/modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |

Áreas del servidor que faltan aquí: (integrador) filas de avisos (F50–), automatizaciones (F80–),
acceso (F130–), impresión (F190–), negocio y datos (F220–), WhatsApp y asistente (F260–) y perfil
fiscal (F300–).

## Qué comparten los flujos de módulos

| Pieza compartida | Flujos que la usan |
|---|---|
| El embudo de una orden, con sus puertas siempre en el mismo orden: interna → bloqueo de otra app → permiso o PIN → edición parcial → esquema → reglas del dueño → candados fiscales → transacción | F03–F13 y toda orden de cualquier módulo, también las de la página pública (F17) y las de guardar ajustes (F33) |
| Los datos que pone el hub y nadie puede mandar (negocio, quién, hora, identidad fiscal, zona, idioma, demo, permisos concedidos, quién aprobó) | F01, F03, F10, F12 |
| El registro de cada app (`installer::install`): validar, migrar, sembrar, registrar; si falla una actualización, vuelve la versión anterior | F19–F23, F25, F26, F30 |
| El resolutor de versiones: la más nueva sin cuarentena, nunca hacia atrás, el pin de soporte gana | F23, F24, F25 |
| La pregunta «¿puede irse?» (proveedor fiscal + obligaciones pendientes del motor) | F28, F29 |
| Los permisos de host concedidos | F12, F32, F35 |

## Cobertura contra la referencia

| Elemento | Estado | Flujo |
|---|---|---|
| Instalar una app con sus dependencias | hecho | HUB-F19 |
| Instalar sin cobrar una dependencia de pago sin consentimiento | hecho (se para y dice qué contratar) | HUB-F19 |
| Verificar integridad y firma del paquete | hecho (firma obligatoria solo si el despliegue tiene claves) | HUB-F19 |
| Seguir cobrando mientras se instala una app | no hecho: la instalación retiene las órdenes | HUB-F19 |
| Actualizar una app sin reiniciar y volver a la anterior si falla | hecho | HUB-F23 |
| Actualizaciones automáticas | hecho al arrancar sin carpeta de descargas (nube); con carpeta, sin confirmar | HUB-F25 |
| No bajar de versión | parcial: la API con versión explícita sí baja | HUB-F23 |
| Apagar una app y lo que depende de ella | hecho | HUB-F28 |
| Desinstalar avisando de lo que depende | hecho | HUB-F29 |
| Desinstalar conservando los datos | hecho | HUB-F29 |
| Borrar los datos de una app desinstalada | no hecho, a propósito | — |
| Permisos de la app concedidos por el dueño | hecho | HUB-F32 |
| Ajustes por app con formulario generado | parcial: quién guarda difiere entre pantalla y servidor | HUB-F33 |
| Paneles de Inicio por app | hecho (servidor); el tablero es de `HUB_SHELL` | HUB-F34 |
| Lista de puesta en marcha | hecho | HUB-F35 |
| Aprobación del responsable con PIN para una acción | hecho | HUB-F05 |
| Validar lo que llega antes de ejecutar | hecho | HUB-F04 |
| Errores traducibles sin filtrar detalles internos | hecho | HUB-F14 |
| Factura completa pedida por el cliente desde el tique | parcial: errores que pueden salir en inglés | HUB-F16, HUB-F17 |
| Un solo redondeo del dinero en todo el producto | hecho en los módulos con manejador; el motor de VeriFactu va aparte | HUB-F18 |

Áreas del servidor que faltan aquí: (integrador) tablas de cobertura de las demás áreas.

## Datos: de quién es cada dato

- **Del hub (área de módulos)**: qué apps tiene el negocio, en qué versión, si están encendidas y el
  pin de soporte (`hub_module`); qué migraciones de cada app se aplicaron (`_hub_migrations`); la
  copia de cada paquete instalado (`hub_module_package`); los permisos de host concedidos a cada app
  (`_module_capability_grants`); los localizadores de la página pública y su clave
  (`_public_claim`, `_public_claim_key`); lo último que dijo el catálogo (`_hub_meta`,
  `setup.catalog_offer`).
- **De cada app**: sus tablas (con el prefijo de la app), sus ajustes y sus datos de partida. El hub
  las crea y migra, pero no las lee salvo por las consultas de la propia app (lecturas previas,
  bloqueos, ajustes, pasos de puesta en marcha, paneles). Desinstalar no las borra.
- **Lo que el hub pone en cada orden**: el negocio, quién pide, quién aprobó, la hora, la identidad
  fiscal del negocio, la zona y el idioma; viaja también dentro de los avisos que la orden emite.
- **Datos personales (inventario de esta área)**, recorridas las migraciones de sistema:
  - `_module_capability_grants.granted_by`: el usuario del hub que concedió o retiró un permiso.
  - `_public_claim`: quién emitió el localizador (`created_by`), el contenido sellado que decide la
    app que lo emite (hoy, líneas del tique; si incluye datos del cliente, sin confirmar), la
    referencia de la factura emitida. Los datos fiscales que escribe el cliente **no** se guardan en
    el localizador: van a la orden (y de ahí a la factura de Facturación).
  - `hub_module`, `_hub_migrations`, `hub_module_package`, `_public_claim_key`: sin datos personales.
  - Los avisos de una orden llevan quién la pidió y quién la aprobó, y la identidad fiscal del
    negocio (que para un autónomo es su nombre y su NIF).
  - El registro de errores guarda las **claves** del contenido de una orden fallida, nunca sus
    valores.

Áreas del servidor que faltan aquí: (integrador) datos de avisos, automatizaciones, acceso,
impresión, negocio y datos, WhatsApp y asistente, perfil fiscal.

## Reglas que no se rompen

Solo las que el código hace cumplir, por cualquier puerta (pantalla, asistente, automatización,
API, otra app).

- **Cada fila es de un negocio.** El hub pone él mismo el negocio (`:hub_id`), quién pide y la hora
  en todo el SQL de las apps, y los sobrescribe si alguien los manda; cada petición se resuelve
  contra la base de su negocio antes de tocar nada.
- **Una app solo escribe en sus tablas.** El SQL de sus órdenes y de su semilla, y sus migraciones,
  se rechazan si tocan tablas de otra app o del hub (HUB-F20, HUB-F21). Un manejador solo propone
  operaciones de su propia app, y un aviso solo lo atiende una orden de la app que escucha.
- **Primero se comprueba, luego se ejecuta.** El contenido se valida contra el esquema antes del
  manejador y de la base de datos; una consulta rechaza un dato que no conoce o que le falta.
- **Una orden es una transacción**: sus cambios y sus avisos a otras apps se guardan juntos o no se
  guarda nada; si declara un mínimo de filas y no llega, nada.
- **El permiso lo comprueba el servidor en cada orden.** Si lo tiene el perfil responsable de la app,
  se ofrece su PIN; la aprobación vale para una sola acción, de ese empleado, con ese contenido. Las
  consultas, la llave de API y las automatizaciones no se elevan.
- **Las órdenes internas de una app no se pueden pedir desde fuera.**
- **El dinero es un entero de unidades mínimas** y se redondea en un solo sitio, la mitad alejándose
  de cero (HUB-F18), en los módulos que enlazan la aritmética común.
- **Nada fiscal se simula.** Los candados fiscales del hub (perfil fiscal) se aplican a toda orden,
  también a las de un manejador o una automatización; una demo nunca sale del entorno de pruebas.
- **Las migraciones solo avanzan** y un `DROP` se convierte en un cambio de nombre: no se pierden
  datos al actualizar ni al desinstalar.
- **Una app que aún debe registros a la AEAT no se apaga ni se quita**, y en producción no se queda
  el hub sin quien cumpla su régimen fiscal.
- **Un paquete no entra sin su huella SHA-256**; con claves de confianza desplegadas, tampoco sin
  firma válida.
- **Una app no da administración**: sus roles no pueden redefinir uno del hub ni heredar del de
  administrador.
- **El cliente de la página pública solo rellena los campos que el localizador permite**; lo sellado
  en el mostrador gana siempre, y un localizador produce como mucho un documento.
- **Los errores no enseñan detalles internos** (motor de base de datos, direcciones de ERPlora): salen
  con un código estable y una frase fija.

Áreas del servidor que faltan aquí: (integrador) reglas de las demás áreas.

## Lo que NO hace, a propósito

- No tiene funciones de negocio: vender, cobrar, facturar o reservar son de las apps.
- No cobra una app de pago por su cuenta: si el plan pide comprarla, se para y lo dice.
- No borra los datos de una app al desinstalarla.
- No baja de versión una app desde la pantalla ni la actualiza a una versión en cuarentena.
- No pide PIN para leer: un informe no se desbloquea con el código del responsable.
- No deja que un manejador toque la base de datos, la red ni otra app: propone, y el hub valida.
- No pinta formularios de ajustes, paneles ni la lista de puesta en marcha: sirve los datos y
  `HUB_SHELL` los pinta.
- No deja a un módulo declararse imprescindible para vender: el nivel ⛔ de la puesta en marcha lo
  decide el hub.
- No ejecuta código en la página pública salvo un único fichero propio que pone nombre a los países.

Áreas del servidor que faltan aquí: (integrador) lo que no hacen las demás áreas.

## Dudas abiertas

Se resuelven con `market-decision`; no las decide el worker.

1. ¿Quién guarda los ajustes de una app: solo el administrador (la pantalla) o quien tenga el
   permiso de la orden de guardar (el servidor, el asistente)? Hoy discrepan (HUB-F33, SALES-F34,
   KITCHEN-F26, INVENTORY-F19).
2. ¿Debe una instalación dejar cobrar mientras descarga, o es aceptable parar la caja durante una
   instalación? (HUB-F19)
3. ¿Se puede bajar de versión una app con una versión explícita por la API de un administrador, o
   solo soporte? (HUB-F23)
4. En la app instalada (Windows, macOS, Android), donde la carpeta de descargas no se vacía, ¿se
   actualizan solas las apps al arrancar? Hoy solo lo hace el arranque que no encuentra la carpeta
   (HUB-F25).
5. Forzar la desinstalación de una app de la que dependen otras: ¿debe quitar (o apagar) esas otras?
   Odoo y Business Central las quitan juntas tras enseñarlas; hoy ERPlora las deja activas sin su
   dependencia (HUB-F29).
6. Cuando una orden aprobada con PIN falla después de la puerta, ¿se debe devolver la aprobación?
   (HUB-F05)
7. ¿Qué frase ve la cajera cuando una orden de Venta se rechaza porque la caja está cerrada? Hoy el
   código `protects_guard` no tiene traducción (HUB-F13, CASH_REGISTER-F04).

Áreas del servidor que faltan aquí: (integrador) dudas de las demás áreas.

## Fuentes contrastadas

- `crates/runtime/src/wasm.rs` dice que ejecutar un manejador WASM «aún no está soportado»: es un
  resto; los manejadores corren por `wasm_cache` y `erplora-wasm-host` (HUB-F10).
- El crate `crates/installer` describe el pipeline de instalación, pero ningún otro crate lo usa: la
  instalación real está en `crates/server/src/install.rs` (HUB-F19).
- La cabecera de `crates/server/src/module_reconcile.rs` dice que no sigue una desinstalación hecha
  por otra copia del hub; desde hub#2039 sí la sigue (HUB-F26).
- TAXES-F18 dice que el motor de VeriFactu usa el mismo redondeo común; el motor no enlaza
  `guest-sdk` y formatea sus importes por su cuenta (`chain.rs`, `format_amount`) — a contrastar en
  `HUB_VERIFACTU`.
- `guest-sdk/src/money.rs` llama «HALF_UP» al modo de redondeo; lo que aplica es la mitad
  alejándose de cero, que coincide con «hacia arriba» en importes positivos y redondea −0,5 a −1 en
  devoluciones (HUB-F18).
- El comentario de `request_install` dice «Auth = JWT del usuario»; además exige antes una sesión
  local de administrador (HUB-F19).
- `hand-book/hub/06-aplicaciones.md` habla de «Aviso de permisos solicitados antes de instalar»: es
  de la pantalla; el servidor instala la app sin ningún permiso concedido y los concede después por
  Ajustes › Permisos (HUB-F32).

Áreas del servidor que faltan aquí: (integrador) discrepancias de las demás áreas.
