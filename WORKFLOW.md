# WORKFLOW — Hub (servidor)

Prefijo: HUB
Alcance MVP: transversal

> Contrato de comportamiento del **servidor** del hub (pm#620, pm#621, hub#2491): `crates/server`,
> `crates/runtime` y los crates pequeños sin `WORKFLOW.md` propio. Se lee antes de tocar ese código y
> se actualiza en la misma PR que cambie un comportamiento. El detalle técnico vive en
> `architecture/hub/`; aquí se escribe lo que se observa. Las pantallas son de
> [apps/web/WORKFLOW.md](apps/web/WORKFLOW.md) (`HUB_SHELL`).
>
> **Cómo se lee.** Este índice tiene solo lo **común** a todo el servidor. Antes de tocar código,
> abre también el fichero del área que lo gobierna (tabla de abajo): delante de sus flujos están su
> referencia adoptada y lo que hay que preparar (`## Antes de empezar`) y, al final, todo lo demás
> propio del área
> —cobertura contra la referencia, datos, reglas, lo que no hace, dudas abiertas y fuentes
> contrastadas—. Si el área está partida en varios ficheros, lo que vale para toda el área está en
> el primero.

## Para qué sirve y para quién

El hub es el servidor de **un** negocio: una peluquería, un bar o una tienda que ERPlora aprovisiona
con su propia base de datos. No tiene funciones de negocio propias: las ponen las **aplicaciones**
(módulos) que el negocio instala desde el catálogo —Venta, Caja, Inventario, Citas, VeriFactu…—, y el
hub es quien las instala, las actualiza, las aísla entre sí y las sirve. Cada vez que alguien pide
datos o pide hacer algo, el hub decide si puede (sesión, permiso, PIN del responsable, permisos de
la app y, en las puertas de las pantallas, el plan contratado), comprueba lo que llega contra lo que
la app declara, lo ejecuta en una sola transacción junto con los avisos que deja para otras apps, y
contesta con un código que la pantalla sabe traducir. Además guarda lo que es del negocio y no de
ninguna app: las personas y su acceso, los ajustes, el perfil fiscal, la cola de impresión, las
automatizaciones, el canal de WhatsApp y el asistente.

Lo usan, sin verlo, todos los perfiles: **administrador** (instala apps, concede permisos, guarda
ajustes), **responsable** (aprueba con su PIN lo que un empleado no puede), **empleado** y **cajero**
(cobran y trabajan por las pantallas de las apps), el **asistente** (pide consultas y órdenes como
una persona más), y el **cliente** que, sin sesión, pide su factura en la página pública del tique.
Casi todos los flujos tienen como actor al **sistema** o a quien llama a la API: lo que una persona
hace en pantalla está en `HUB_SHELL`, y aquí está lo que el servidor garantiza.

### Qué gobierna cada fichero y qué código

| Área | Qué cubre | Fichero | IDs | Código que gobierna |
|---|---|---|---|---|
| Módulos y órdenes | Consultas, órdenes y su embudo de puertas, manejadores, errores, página pública del tique, redondeo | [workflow/modulos.md](workflow/modulos.md) | F01–F18, F36 | `runtime`: dispatch, commands, queries, manifest, registry, native, wasm, wasm_cache, column_kinds_cache, errors, error_registry, public_claim, capabilities (F12) · `server`: dispatch_api, public_door, operations_catalog, error_sink · crates `wasm-host`, `guest-sdk`. Puertas que usa y gobierna acceso: `runtime` permissions, policies, elevation; `server` entitlement (el 402), api_keys (la puerta `expose_api`) |
| Módulos y órdenes | Instalar, actualizar, reponer, encender, apagar y quitar apps; permisos de host; ajustes de app; paneles; puesta en marcha | [workflow/modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) | F19–F35 | `runtime`: installer, module_lifecycle, module_update, module_package, lifecycle, loader, seed, migrations, migration_guard, manifest_warning_grandfather, capabilities, setup_status, settings_api (permisos de módulo), ui · `server`: module_api, install, install_guard, module_reconcile, settings (permisos de módulo) · crate `source` |
| Avisos entre módulos | Cola de avisos, entrega, reintentos, avisos caídos, canal en vivo, mensajes al exterior, tareas programadas, señal de última entrada | [workflow/avisos.md](workflow/avisos.md) | F50–F64 | `runtime`: events, events_api, event_shape, outbox, host_notify, scheduler, capabilities (reencola los avisos al conceder un permiso, F58) · `server`: event_stream, outbox_admin, notify_transport, activity (la señal de última entrada, F64; **no** es el registro de actividad, que es de negocio y datos) |
| Automatizaciones | El motor de automatizaciones: disparadores, pasos, permisos, secretos, preguntas, historial, recetas de fábrica | [workflow/automatizaciones.md](workflow/automatizaciones.md) | F80–F112 | `runtime`: flows/ (agent, approvals, def, executor, grants, http, mod, net, notify, query, schema, secrets, store, templates, triggers, waits), flows_api, secret_box · `server`: flows_api, flow_io, flows_header_media, agent_runner (el paso del asistente, compartido con asistente) |
| Acceso, personas y plan | Entrar (cuenta, PIN, placa), sesiones, dispositivos, perfil propio, freno de intentos | [workflow/acceso.md](workflow/acceso.md) | F130–F144 | `runtime`: access, access_email, identity, devices, device_mode, pin_policy, user_profile · `server`: auth, auth_api, login_throttle, address_guard, devices, device_mode, profile, members |
| Acceso, personas y plan | Cuentas del personal, roles, permisos, aprobación con PIN, normas del dueño, llaves de API | [workflow/personas-y-permisos.md](workflow/personas-y-permisos.md) | F145–F158 | `runtime`: hub_users, roles, permissions, policies, policies_api, elevation, api_keys · `server`: hub_users, members, policies_api, elevation, api_keys, openapi |
| Acceso, personas y plan | Arranque, plan firmado, latido, pasarela a erplora.com, salud, versión, freno de carga, un negocio por petición | [workflow/plan-y-sistema.md](workflow/plan-y-sistema.md) | F159–F171 | `runtime`: hub_meta, core_version, update_history, cloud_call · `server`: boot, boot_announce, readiness, shutdown, entitlement, cloud_call, cloud_proxy, daily_usage, usage_series, system, system_metrics, version, load_shed, tenant, csp_report · crate `cloud-client` |
| Impresión | Cola de impresión, funciones y mapa de documentos, dispositivos que imprimen, reintentar y descartar | [workflow/impresion.md](workflow/impresion.md) | F190–F207 | `runtime`: printing, print_queue, print_drain, print_hosts, print_routes, print_stations, host_print · `server`: print, print_ws |
| Negocio y datos | Ajustes del negocio, zona horaria y reloj del negocio, exportar e importar, restablecer, unidad del dinero | [workflow/negocio-y-datos.md](workflow/negocio-y-datos.md) | F220–F244 | `runtime`: settings, settings_api (ajustes del negocio, zona, reloj del negocio), export, import, import_sql, reset, money_backfill · `server`: settings, export_import, reset |
| Negocio y datos | Archivos, borrado de los datos de una persona, retención, registro de actividad, semilla SQL del arranque | [workflow/archivos-y-privacidad.md](workflow/archivos-y-privacidad.md) | F245–F255 | `runtime`: module_storage, erasure, retention, activity_log · `server`: media, module_storage |
| WhatsApp y asistente | Conectar el número, recoger y mandar WhatsApp, adjuntos, plantillas de Meta, cupo | [workflow/whatsapp.md](workflow/whatsapp.md) | F260–F272 | `server`: whatsapp_connect, inbound_poll, whatsapp_media, whatsapp_templates, whatsapp_header_samples, whatsapp_quota (la salida de los WhatsApp va por `notify_transport`, de avisos) |
| WhatsApp y asistente | Turno del asistente, herramientas, recorte por relevancia, anclaje, plan, denuncias, paso de IA en automatizaciones | [workflow/asistente.md](workflow/asistente.md) | F273–F279 | `server`: assistant, assistant_api, assistant_report, router, ingest, embed (y agent_runner, de automatizaciones) · crate `vector` |
| Perfil fiscal | Perfil fiscal, certificado, vía de envío, autorización, conexión segura, paso a producción, «sin vía no se cobra» | [workflow/fiscal.md](workflow/fiscal.md) | F300–F317 | `runtime`: fiscal, fiscal_profile, certificate, gateway_identity, producer_facts (y las ramas fiscales de commands) · `server`: gateway_enrolment, representation_grant, call_budget, settings (las puertas fiscales) |
| Esqueleto común | Sin flujos propios: lo gobierna este índice; quien cambie un comportamiento visible desde aquí lo escribe en el área a la que afecta | este fichero | — | `server`: main, lib, config (configuración del despliegue y CSP), routes (monta las rutas y el contexto público `/api/hub/context`), state, logging; solo pruebas: log_capture · `runtime`: lib, system_migrations (crea las tablas de sistema de todas las áreas; cada tabla la gobierna su área, ver «Datos»); solo pruebas: e2e_support · crate `db` (el adaptador de base de datos) |
| Sin uso | Ningún otro crate los enlaza: no gobiernan nada observable | — | — | crates `installer` (la instalación real es `runtime` installer y `server` install) y `sync` |

Números libres para flujos nuevos: F37–F49, F65–F79, F113–F129, F172–F189, F208–F219, F256–F259,
F280–F299 y F318–F339.

Otros documentos del mismo repo: `apps/web/WORKFLOW.md` (`HUB_SHELL`, pantallas),
`crates/plugins/verifactu/WORKFLOW.md` (`HUB_VERIFACTU`, el motor fiscal: sellar, enviar,
clasificar, contingencia, cadena, recuperación), `crates/peripherals/WORKFLOW.md` (`HUB_PERIPHERALS`,
la mitad de dispositivo de la impresión y el cajón) y `apps/tauri/WORKFLOW.md` (`HUB_APP`). Por la
regla del ancestro, este fichero gobierna todo lo que no tiene uno más cercano; también
`crates/tauri-plugin-erplora-android`, cuyo comportamiento describe `HUB_APP`: quien lo toque lee
además `apps/tauri/WORKFLOW.md`.

## Referencia adoptada

Lo común a todo el servidor (se adopta esto, no más):

- El hub es una **plataforma de aplicaciones** como las de Odoo, Business Central y Shopify: instala,
  actualiza, aísla y sirve apps con los permisos que concede el dueño, y desinstalar conserva los
  datos (como Business Central, no como Odoo).
- Para cada área se adopta la referencia de la **plataforma** de los productos de referencia (Odoo,
  Square, Toast, Shopify, Lightspeed, Business Central; para las automatizaciones, Zapier, Make y
  Shopify Flow), reutilizando la ya contrastada en los guiones de QA. En lo fiscal manda la norma
  (RD 1007/2023, Orden HAC/1177/2024), no un competidor.

Lo de cada área, con sus enlaces, está en `## Referencia adoptada` de su fichero:

- Módulos y órdenes: Odoo y Business Central (instalar y quitar apps), Shopify (permisos de la app),
  Toast y Square (aprobación del responsable), Cuiner y Ágora (factura pedida desde el tique), JSON
  Schema, Ley 46/1998 (redondeo) → [modulos.md](workflow/modulos.md),
  [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md).
- Avisos y automatizaciones: Transactional Outbox, Business Central Job Queue, Odoo OCA `queue_job`,
  y Zapier, Make, Power Automate, Shopify Flow, Odoo y Business Central para el motor →
  [avisos.md](workflow/avisos.md), [automatizaciones.md](workflow/automatizaciones.md).
- Acceso, personas y plan: Square, Toast y Clover (PIN), Toast, Aloha, Square y Lightspeed (placa),
  Shopify y Lightspeed (normas del dueño), licencia firmada sin conexión →
  [acceso.md](workflow/acceso.md).
- Impresión: Toast, Square, Lightspeed K, Odoo, Oracle Simphony, Epson ePOS, Star CloudPRNT →
  [impresion.md](workflow/impresion.md).
- Negocio y datos: Odoo, Square, Shopify y Business Central (ajustes, copias, plantillas), Shopify
  `customers/redact` y RGPD (borrado) → [negocio-y-datos.md](workflow/negocio-y-datos.md),
  [archivos-y-privacidad.md](workflow/archivos-y-privacidad.md).
- WhatsApp y asistente: la WhatsApp Cloud API de Meta; Business Central Copilot, Shopify Sidekick,
  Odoo AI, Intercom Fin; n8n, Zapier AI y Make → [whatsapp.md](workflow/whatsapp.md),
  [asistente.md](workflow/asistente.md).
- Perfil fiscal: RD 1007/2023, Orden HAC/1177/2024 y las preguntas frecuentes de la AEAT →
  [fiscal.md](workflow/fiscal.md).

## Antes de empezar

Lo común a todo el servidor:

- El hub lo **aprovisiona ERPlora** con su base de datos, su identificador, su credencial de máquina y
  el correo del dueño, que nace administrador; sin ellos no abre nada (HUB-F159, HUB-F160). Sin
  credencial de máquina el hub no instala ni actualiza apps del catálogo (solo repone las que ya
  tenía guardadas, HUB-F25), no recoge ni manda WhatsApp, no hay asistente en producción, no hay
  archivos y no publica su identidad fiscal.
- La primera persona entra con su **cuenta de erplora.com** (HUB-F130); ese primer acceso hace al
  dispositivo de confianza, y sin él en ese dispositivo no funciona el PIN (HUB-F133).
- Casi toda la configuración pide **sesión de dueño o administrador**; una llave de API no entra en
  las puertas de configuración.

Lo de cada área está en `## Antes de empezar` de su fichero: apps, permisos de host, ajustes de app y
puesta en marcha en [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md); permisos para
imprimir o avisar y lo que piden las automatizaciones en [avisos.md](workflow/avisos.md) y
[automatizaciones.md](workflow/automatizaciones.md); PIN, dispositivos y personal en
[acceso.md](workflow/acceso.md); impresoras en [impresion.md](workflow/impresion.md); país, zona y
quién puede tocar los datos en [negocio-y-datos.md](workflow/negocio-y-datos.md); número de WhatsApp
y asistente en [whatsapp.md](workflow/whatsapp.md); vía fiscal y paso a producción en
[fiscal.md](workflow/fiscal.md).

## Pantallas

El servidor solo pinta **una** pantalla propia; todas las demás son de `HUB_SHELL`
([apps/web/WORKFLOW.md](apps/web/WORKFLOW.md)) o de un módulo, y los flujos de aquí las nombran como
`HUB_SHELL: <pantalla>` o `<Módulo>: <pantalla>`.

### Página pública para pedir la factura
Se llega escaneando el segundo QR del tique o escribiendo `/p/<código>` en el navegador; no pide
sesión ni ejecuta código de la página (formulario HTML, en español o inglés según el idioma del
negocio o `?lang=`). Aparece «Pide tu factura», la explicación, el «Código del tique», los campos
«NIF/CIF», «Nombre o razón social», «Domicilio», los desplegables que el tique ofrezca (país, tipo de
documento) y «Emitir mi factura». Hecha: «Tu factura está emitida» con la referencia. Con error: el
motivo encima del formulario, con lo escrito; código desconocido, caducado o demasiados intentos:
un mensaje sin formulario (HUB-F17). No se indexa en buscadores.

### Pantallas de otros componentes que usan los flujos del servidor
Con los nombres canónicos de la sección «Pantallas» de [apps/web/WORKFLOW.md](apps/web/WORKFLOW.md)
y de la de cada módulo:
- Módulos: `HUB_SHELL` Apps, Menú lateral, Vista de un módulo, Vista de un módulo › Ajustes, Paneles
  de Inicio, Termina de configurar tu negocio y Ajustes › Permisos.
- Avisos y automatizaciones: `HUB_SHELL` Sistema › Eventos caídos, Campana de notificaciones y
  Ajustes › Permisos; `FLOWS` Automatizaciones y Editor de automatización; `WHATSAPP_INBOX` Ajustes
  (recetas). Sin pantalla, solo por la API: la traza de un aviso (HUB-F63) y lanzar a mano (HUB-F85).
- Acceso, personas y plan: `HUB_SHELL` Acceso, Cambiar de usuario, Aprobación de un responsable, Mi
  perfil, Ajustes › General (Este dispositivo, Pinpad, Dispositivos), Empleados (Personal, Roles, API
  keys, Aprobaciones), Documentación de la API, Sistema, Sistema › Plan y límites y
  Sistema › Actualizaciones. HUB-F154 solo tiene API.
- Impresión: `PRINTING` Impresoras; `HUB_SHELL` Ajustes › Impresión (tarjeta «Estado de impresión»)
  y Campana de notificaciones.
- Negocio y datos: `HUB_SHELL` Ajustes › General, Ajustes › Negocio, Ajustes › Datos y copias ›
  Exportar, Importar y Restablecer, y Archivos; `CUSTOMERS` Ficha de cliente; `WHATSAPP_INBOX` Bandeja
  de entrada.
- WhatsApp y asistente: `HUB_SHELL` Tu número, Vista de un módulo › Plan y Asistente; `WHATSAPP_INBOX`
  Bandeja de entrada y Plantillas de Meta; `FLOWS` Editor de automatización.
- Perfil fiscal: `VERIFACTU` Configuración, Ajustes y Contingencia; `SALES` Vender; `HUB_SHELL` Apps y
  Ajustes › Negocio.

## Flujos

El detalle de cada flujo vive en `workflow/`, con la misma gramática y el mismo prefijo. Los huecos
(`parcial`, `no hecho`) dicen el porqué en su línea `Estado:`. El servidor no tiene flujos propios de
un solo sector, así que no usa la clave `Vertical:`.

| ID | Flujo | Estado | Fichero |
|---|---|---|---|
| HUB-F01 | Leer datos de un módulo | hecho | [modulos.md](workflow/modulos.md) |
| HUB-F02 | Pedir una lista con búsqueda, filtros, orden y páginas | hecho | [modulos.md](workflow/modulos.md) |
| HUB-F03 | Ejecutar una orden de un módulo | hecho | [modulos.md](workflow/modulos.md) |
| HUB-F04 | Comprobar el contenido de una orden contra su esquema y rellenar lo que falta | hecho | [modulos.md](workflow/modulos.md) |
| HUB-F05 | Pedir la aprobación de un responsable cuando falta el permiso | parcial | [modulos.md](workflow/modulos.md) |
| HUB-F06 | Comprobar que la orden cambió algo | parcial | [modulos.md](workflow/modulos.md) |
| HUB-F07 | Cambiar solo algunos campos de una ficha | hecho | [modulos.md](workflow/modulos.md) |
| HUB-F08 | Rechazar desde fuera las órdenes internas de un módulo | hecho | [modulos.md](workflow/modulos.md) |
| HUB-F09 | Avisar de un duplicado con el código del módulo | parcial | [modulos.md](workflow/modulos.md) |
| HUB-F10 | Ejecutar el manejador de un módulo y validar lo que propone | parcial | [modulos.md](workflow/modulos.md) |
| HUB-F11 | Darle al manejador los datos de otros módulos antes de ejecutar | hecho | [modulos.md](workflow/modulos.md) |
| HUB-F12 | Ejecutar el motor propio de un módulo de confianza | hecho | [modulos.md](workflow/modulos.md) |
| HUB-F13 | Bloquear las órdenes de un módulo mientras otro no cumpla su condición | parcial | [modulos.md](workflow/modulos.md) |
| HUB-F14 | Contestar un fallo con un código estable y sin detalles internos | hecho | [modulos.md](workflow/modulos.md) |
| HUB-F15 | Consultar qué órdenes y consultas acepta el hub | hecho | [modulos.md](workflow/modulos.md) |
| HUB-F16 | Emitir el localizador para que el cliente pida su factura | parcial | [modulos.md](workflow/modulos.md) |
| HUB-F17 | Canjear un localizador en la página pública | parcial | [modulos.md](workflow/modulos.md) |
| HUB-F18 | Redondear el dinero igual en todos los módulos | hecho | [modulos.md](workflow/modulos.md) |
| HUB-F36 | Leer un teléfono en formato internacional igual en todos los módulos | parcial | [modulos.md](workflow/modulos.md) |
| HUB-F19 | Instalar una aplicación del catálogo | parcial | [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F20 | Rechazar un paquete que rompe las reglas del hub | hecho | [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F21 | Aplicar las migraciones de un módulo con su guarda | hecho | [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F22 | Sembrar los datos de partida de un módulo | hecho | [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F23 | Actualizar una aplicación | parcial | [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F24 | Consultar qué actualizaciones y versiones hay | hecho | [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F25 | Reponer las aplicaciones al arrancar y actualizarlas solas | parcial | [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F26 | Seguir lo que otra copia del hub instaló, actualizó, apagó o quitó | hecho | [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F27 | Activar una aplicación | hecho | [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F28 | Desactivar una aplicación preguntando antes si puede irse | hecho | [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F29 | Desinstalar una aplicación | parcial | [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F30 | Instalar un módulo desde una carpeta en modo desarrollo | hecho | [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F31 | Servir el menú, las pantallas y los ficheros de las aplicaciones | hecho | [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F32 | Conceder o retirar un permiso de host a una aplicación | hecho | [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F33 | Leer y guardar los ajustes de un módulo | parcial | [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F34 | Servir los datos de los paneles de Inicio | parcial | [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F35 | Calcular la lista de puesta en marcha | hecho | [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md) |
| HUB-F50 | Dejar un aviso en la cola al guardar una orden | hecho | [avisos.md](workflow/avisos.md) |
| HUB-F51 | Entregar un aviso a los módulos que lo escuchan | hecho | [avisos.md](workflow/avisos.md) |
| HUB-F52 | Reintentar un aviso que un módulo no pudo procesar | hecho | [avisos.md](workflow/avisos.md) |
| HUB-F53 | Mandar a «Eventos caídos» al momento lo que reintentar no arregla | hecho | [avisos.md](workflow/avisos.md) |
| HUB-F54 | Ver la cola de avisos caídos | parcial | [avisos.md](workflow/avisos.md) |
| HUB-F55 | Reenviar un aviso caído | hecho | [avisos.md](workflow/avisos.md) |
| HUB-F56 | Reenviar todos los avisos caídos | hecho | [avisos.md](workflow/avisos.md) |
| HUB-F57 | Cerrar un aviso caído con motivo | hecho | [avisos.md](workflow/avisos.md) |
| HUB-F58 | Reenviar solo lo que un permiso había rechazado, al concederlo | hecho | [avisos.md](workflow/avisos.md) |
| HUB-F59 | Contar los avisos caídos para la campana | hecho | [avisos.md](workflow/avisos.md) |
| HUB-F60 | Avisar a las pantallas en vivo | hecho | [avisos.md](workflow/avisos.md) |
| HUB-F61 | Mandar el email o el WhatsApp que pide un módulo o una automatización | parcial | [avisos.md](workflow/avisos.md) |
| HUB-F62 | Ejecutar las tareas programadas de los módulos | parcial | [avisos.md](workflow/avisos.md) |
| HUB-F63 | Seguir la cadena de lo que provocó un aviso | parcial | [avisos.md](workflow/avisos.md) |
| HUB-F64 | Contar que alguien usa el hub | hecho | [avisos.md](workflow/avisos.md) |
| HUB-F80 | Crear una automatización | hecho | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F81 | Ver las automatizaciones del negocio | hecho | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F82 | Arrancar una automatización cuando pasa algo en el negocio | hecho | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F83 | Arrancar una automatización según un horario, en la hora del negocio | parcial | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F84 | Arrancar una automatización una vez, en una fecha y hora | parcial | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F85 | Lanzar una automatización a mano | parcial | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F86 | Guardar los cambios de una automatización | parcial | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F87 | Pausar una automatización y volver a encenderla | parcial | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F88 | Borrar una automatización | parcial | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F89 | Paso «Hacer algo»: ejecutar la acción de un módulo | hecho | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F90 | Paso «Consultar algo»: leer datos de un módulo | hecho | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F91 | Paso «Solo sigue si» | hecho | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F92 | Paso «Esperar» | parcial | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F93 | Paso «Enviar un mensaje» a un cliente | hecho | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F94 | Paso «Llamar a otro sistema» | hecho | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F95 | Paso «Pedírselo al asistente» | parcial | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F96 | Paso «Preguntar antes a alguien» | parcial | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F97 | «Solo si» y «seguir si falla» en cada paso | hecho | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F98 | Conceder, limitar y retirar los permisos de una automatización | parcial | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F99 | Guardar secretos que no se pueden volver a leer | hecho | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F100 | Decidir una pregunta o una propuesta que espera | parcial | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F101 | Cerrar lo que nadie contestó a tiempo | hecho | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F102 | Guardar el historial de ejecuciones | hecho | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F103 | Reanudar una ejecución desde el paso que falló | no hecho | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F104 | Servir las recetas de fábrica de los módulos | hecho | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F105 | Encender una receta de fábrica con exactamente sus permisos | parcial | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F106 | Apagar una receta de fábrica sin borrarla | hecho | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F107 | Restaurar una receta a la versión actual de su módulo | parcial | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F108 | Ofrecer el catálogo de avisos del negocio | hecho | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F109 | Enseñar ejemplos reales de un aviso con los datos de personas ocultos | parcial | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F110 | Frenar una automatización que se dispara en bucle | parcial | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F111 | Decir qué versión de automatizaciones entiende el hub | hecho | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F112 | Subir la foto, el vídeo o el PDF de la cabecera de un WhatsApp | hecho | [automatizaciones.md](workflow/automatizaciones.md) |
| HUB-F130 | Entrar con la cuenta de erplora.com | hecho | [acceso.md](workflow/acceso.md) |
| HUB-F131 | Entrar desde el panel de erplora.com sin volver a teclear la contraseña | hecho | [acceso.md](workflow/acceso.md) |
| HUB-F132 | Elegir o cambiar el propio PIN | parcial | [acceso.md](workflow/acceso.md) |
| HUB-F133 | Entrar con PIN | parcial | [acceso.md](workflow/acceso.md) |
| HUB-F134 | Entrar pasando la placa | parcial | [acceso.md](workflow/acceso.md) |
| HUB-F135 | Frenar a quien prueba PIN o sesiones | hecho | [acceso.md](workflow/acceso.md) |
| HUB-F136 | Mantener la sesión abierta y cerrarla | parcial | [acceso.md](workflow/acceso.md) |
| HUB-F137 | Perder la sesión porque se abrió en otro dispositivo | hecho | [acceso.md](workflow/acceso.md) |
| HUB-F138 | Cambiar de usuario sin perder la venta | hecho | [acceso.md](workflow/acceso.md) |
| HUB-F139 | Marcar un dispositivo como compartido o personal | hecho | [acceso.md](workflow/acceso.md) |
| HUB-F140 | Decidir si el negocio pide PIN y cuántos dígitos tiene | hecho | [acceso.md](workflow/acceso.md) |
| HUB-F141 | Ver, nombrar y quitar los dispositivos del negocio | hecho | [acceso.md](workflow/acceso.md) |
| HUB-F142 | Abrir erplora.com ya identificado | hecho | [acceso.md](workflow/acceso.md) |
| HUB-F143 | Cambiar mis datos, idioma, apariencia y foto | hecho | [acceso.md](workflow/acceso.md) |
| HUB-F144 | Cerrar la puerta a quien ya no es miembro en erplora.com | parcial | [acceso.md](workflow/acceso.md) |
| HUB-F145 | Dar de alta a una persona que entra solo con PIN | parcial | [personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB-F146 | Invitar a una persona con su cuenta de erplora.com | parcial | [personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB-F147 | Llegar al tope de plazas del plan | parcial | [personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB-F148 | Cambiar el nombre, el rol, el PIN, la placa o el correo de una persona | parcial | [personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB-F149 | Dar de baja y reincorporar a una persona | hecho | [personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB-F150 | Ver los roles y encender los que trae un módulo | parcial | [personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB-F151 | Rechazar una orden para la que no se tiene permiso | hecho | [personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB-F152 | Aprobar una acción con el PIN de un responsable | hecho | [personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB-F153 | Consultar quién aprobó qué | hecho | [personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB-F154 | Escribir una norma propia del negocio | parcial | [personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB-F155 | Crear, rotar y revocar llaves de API | hecho | [personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB-F156 | Leer y escribir datos del negocio con una llave de API | parcial | [personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB-F157 | Consultar la documentación de la API | hecho | [personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB-F158 | Dar la lista de personas del negocio a los módulos | hecho | [personas-y-permisos.md](workflow/personas-y-permisos.md) |
| HUB-F159 | Arrancar el hub y avisar a erplora.com de que ya atiende | hecho | [plan-y-sistema.md](workflow/plan-y-sistema.md) |
| HUB-F160 | No abrir nada hasta que el hub esté registrado | hecho | [plan-y-sistema.md](workflow/plan-y-sistema.md) |
| HUB-F161 | Decir si el hub está listo para servir | parcial | [plan-y-sistema.md](workflow/plan-y-sistema.md) |
| HUB-F162 | Comprobar el plan y qué apps puede usar el negocio | parcial | [plan-y-sistema.md](workflow/plan-y-sistema.md) |
| HUB-F163 | Aplicar un cambio de plan al momento | hecho | [plan-y-sistema.md](workflow/plan-y-sistema.md) |
| HUB-F164 | Mandar el latido diario de uso a erplora.com | hecho | [plan-y-sistema.md](workflow/plan-y-sistema.md) |
| HUB-F165 | Ver el uso de recursos frente a los límites del plan | hecho | [plan-y-sistema.md](workflow/plan-y-sistema.md) |
| HUB-F166 | Ver el estado del sistema, sus registros y documentos | parcial | [plan-y-sistema.md](workflow/plan-y-sistema.md) |
| HUB-F167 | Saber qué versión corre y qué se le ha actualizado | parcial | [plan-y-sistema.md](workflow/plan-y-sistema.md) |
| HUB-F168 | Hablar con erplora.com en nombre del negocio | hecho | [plan-y-sistema.md](workflow/plan-y-sistema.md) |
| HUB-F169 | Dejar que un motor del hub llame a erplora.com con la identidad del negocio | hecho | [plan-y-sistema.md](workflow/plan-y-sistema.md) |
| HUB-F170 | Rechazar trabajo cuando el hub está saturado | parcial | [plan-y-sistema.md](workflow/plan-y-sistema.md) |
| HUB-F171 | Atender cada petición solo con los datos de su negocio | hecho | [plan-y-sistema.md](workflow/plan-y-sistema.md) |
| HUB-F190 | Pedir imprimir un documento desde una pantalla o un dispositivo | parcial | [impresion.md](workflow/impresion.md) |
| HUB-F191 | Pedir imprimir desde un módulo, un flujo o el asistente | parcial | [impresion.md](workflow/impresion.md) |
| HUB-F192 | Repetir una petición sin repetir el papel | hecho | [impresion.md](workflow/impresion.md) |
| HUB-F193 | Decidir por qué impresora sale cada documento | hecho | [impresion.md](workflow/impresion.md) |
| HUB-F194 | Cambiar a qué función va cada documento | parcial | [impresion.md](workflow/impresion.md) |
| HUB-F195 | Crear, renombrar y quitar una función de impresión | parcial | [impresion.md](workflow/impresion.md) |
| HUB-F196 | Dar de alta un dispositivo como el que imprime una función | hecho | [impresion.md](workflow/impresion.md) |
| HUB-F197 | Mantener vivo o retirar un dispositivo de impresión | parcial | [impresion.md](workflow/impresion.md) |
| HUB-F198 | Conectar el dispositivo a la cola en vivo | parcial | [impresion.md](workflow/impresion.md) |
| HUB-F199 | Sacar un trabajo de la cola y confirmar que salió el papel | parcial | [impresion.md](workflow/impresion.md) |
| HUB-F200 | Un trabajo que no sale acaba «muerto» | hecho | [impresion.md](workflow/impresion.md) |
| HUB-F201 | Trabajo en cola y nadie conectado para sacarlo | hecho | [impresion.md](workflow/impresion.md) |
| HUB-F202 | Saber qué funciones tienen quién las imprima | parcial | [impresion.md](workflow/impresion.md) |
| HUB-F203 | Leer la cola de trabajos | hecho | [impresion.md](workflow/impresion.md) |
| HUB-F204 | Reintentar un trabajo muerto | hecho | [impresion.md](workflow/impresion.md) |
| HUB-F205 | Descartar un trabajo que no debe salir | hecho | [impresion.md](workflow/impresion.md) |
| HUB-F206 | Cuánto tiempo guarda el hub los trabajos de impresión | parcial | [impresion.md](workflow/impresion.md) |
| HUB-F207 | Abrir el cajón por la impresora (lo que sabe el servidor) | parcial | [impresion.md](workflow/impresion.md) |
| HUB-F220 | Leer los ajustes del negocio | hecho | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F221 | Cambiar los ajustes del negocio | hecho | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F222 | Guardar la identidad del negocio | hecho | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F223 | Congelar el NIF y el país, y casar la región con el país | parcial | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F224 | Publicar la identidad del negocio en el SaaS | hecho | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F225 | Sembrar el país y la identidad de una demo al arrancar | hecho | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F226 | Moneda, decimales e idioma del negocio | parcial | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F227 | Fijar la zona horaria del negocio | hecho | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F228 | Entregar el reloj del negocio a los módulos en cada orden | hecho | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F229 | Mover los horarios de las automatizaciones con la zona | hecho | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F230 | Exportar los datos del negocio | parcial | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F231 | Meter los archivos y el certificado en el zip | parcial | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F232 | Ver qué tablas y cuántas filas lleva cada app | hecho | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F233 | Inspeccionar un fichero antes de importarlo | hecho | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F234 | Traer una plantilla del catálogo | hecho | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F235 | Importar un fichero o una plantilla | parcial | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F236 | Qué deja entrar el hub según de quién es el fichero | parcial | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F237 | Permisos, roles y automatizaciones que trae el fichero | hecho | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F238 | Volver a importar lo mismo | hecho | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F239 | El informe de la importación | hecho | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F240 | Reintentar lo que falló en una importación | parcial | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F241 | Deshacer una importación | parcial | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F242 | Restablecer el hub | parcial | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F243 | Convertir el dinero de un hub antiguo a céntimos | parcial | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F244 | Comprobar la unidad del dinero sin escribir | parcial | [negocio-y-datos.md](workflow/negocio-y-datos.md) |
| HUB-F245 | Ver y descargar archivos | hecho | [archivos-y-privacidad.md](workflow/archivos-y-privacidad.md) |
| HUB-F246 | Subir, organizar y borrar archivos | parcial | [archivos-y-privacidad.md](workflow/archivos-y-privacidad.md) |
| HUB-F247 | Guardar ficheros desde una app | hecho | [archivos-y-privacidad.md](workflow/archivos-y-privacidad.md) |
| HUB-F248 | Borrar los datos de una persona: el aviso único | parcial | [archivos-y-privacidad.md](workflow/archivos-y-privacidad.md) |
| HUB-F249 | Vaciar el historial del hub que nombra a la persona | parcial | [archivos-y-privacidad.md](workflow/archivos-y-privacidad.md) |
| HUB-F250 | Lo que le toca a cada app al recibir el aviso de borrado | parcial | [archivos-y-privacidad.md](workflow/archivos-y-privacidad.md) |
| HUB-F251 | Borrar los datos de un número sin ficha | no hecho | [archivos-y-privacidad.md](workflow/archivos-y-privacidad.md) |
| HUB-F252 | Borrar los datos de una persona del equipo | no hecho | [archivos-y-privacidad.md](workflow/archivos-y-privacidad.md) |
| HUB-F253 | Purgar el historial por retención | hecho | [archivos-y-privacidad.md](workflow/archivos-y-privacidad.md) |
| HUB-F254 | Registrar la actividad del negocio para el SaaS | hecho | [archivos-y-privacidad.md](workflow/archivos-y-privacidad.md) |
| HUB-F255 | Aplicar la semilla SQL del despliegue al arrancar | parcial | [archivos-y-privacidad.md](workflow/archivos-y-privacidad.md) |
| HUB-F260 | Conectar el número de WhatsApp del negocio | parcial | [whatsapp.md](workflow/whatsapp.md) |
| HUB-F261 | Saber qué número está conectado y si hay que reconectarlo | parcial | [whatsapp.md](workflow/whatsapp.md) |
| HUB-F262 | Desconectar o volver a conectar el número | hecho | [whatsapp.md](workflow/whatsapp.md) |
| HUB-F263 | Recoger los mensajes de WhatsApp que esperan en la plataforma | hecho | [whatsapp.md](workflow/whatsapp.md) |
| HUB-F264 | Distinguir lo que contesta el dueño desde el móvil y el historial al conectar | hecho | [whatsapp.md](workflow/whatsapp.md) |
| HUB-F265 | Saber a qué pregunta contesta lo que toca la clienta | hecho | [whatsapp.md](workflow/whatsapp.md) |
| HUB-F266 | Mandar un WhatsApp desde el hub | parcial | [whatsapp.md](workflow/whatsapp.md) |
| HUB-F267 | Ver una foto, una nota de voz o un documento de la clienta | hecho | [whatsapp.md](workflow/whatsapp.md) |
| HUB-F268 | Ver las plantillas del negocio con lo que dice Meta de cada una | hecho | [whatsapp.md](workflow/whatsapp.md) |
| HUB-F269 | Mandar una plantilla a revisión de Meta, nueva o editada | parcial | [whatsapp.md](workflow/whatsapp.md) |
| HUB-F270 | Subir a Meta la muestra de la cabecera de una plantilla | hecho | [whatsapp.md](workflow/whatsapp.md) |
| HUB-F271 | Borrar una plantilla en Meta | parcial | [whatsapp.md](workflow/whatsapp.md) |
| HUB-F272 | Reflejar en el hub el cupo y el consumo de WhatsApp del mes | parcial | [whatsapp.md](workflow/whatsapp.md) |
| HUB-F273 | Conversar con el asistente | hecho | [asistente.md](workflow/asistente.md) |
| HUB-F274 | Ofrecer al asistente las consultas y órdenes de los módulos y del núcleo | hecho | [asistente.md](workflow/asistente.md) |
| HUB-F275 | Recortar las herramientas a los módulos que importan para la pregunta | hecho | [asistente.md](workflow/asistente.md) |
| HUB-F276 | Anclar al asistente a lo que este hub tiene instalado | parcial | [asistente.md](workflow/asistente.md) |
| HUB-F277 | Ver el plan del asistente y lo que queda del mes | hecho | [asistente.md](workflow/asistente.md) |
| HUB-F278 | Denunciar una respuesta del asistente | parcial | [asistente.md](workflow/asistente.md) |
| HUB-F279 | Pedirle un paso al asistente dentro de una automatización | hecho | [asistente.md](workflow/asistente.md) |
| HUB-F300 | Resolver el perfil fiscal del hub al arrancar | parcial | [fiscal.md](workflow/fiscal.md) |
| HUB-F301 | Saber dónde y por qué vía declara el hub | hecho | [fiscal.md](workflow/fiscal.md) |
| HUB-F302 | Guardar o sustituir el certificado del negocio | parcial | [fiscal.md](workflow/fiscal.md) |
| HUB-F303 | Borrar el certificado del negocio | parcial | [fiscal.md](workflow/fiscal.md) |
| HUB-F304 | Elegir la vía de envío: mi certificado o ERPlora | hecho | [fiscal.md](workflow/fiscal.md) |
| HUB-F305 | Enviar la autorización de representación y seguir su estado | parcial | [fiscal.md](workflow/fiscal.md) |
| HUB-F306 | Pedir, recoger y renovar la conexión segura con la celda fiscal | parcial | [fiscal.md](workflow/fiscal.md) |
| HUB-F307 | Pasar a producción | parcial | [fiscal.md](workflow/fiscal.md) |
| HUB-F308 | Volver a pruebas mientras no se haya declarado nada en producción | parcial | [fiscal.md](workflow/fiscal.md) |
| HUB-F309 | Cerrar el perfil fiscal de un negocio que cesa | no hecho | [fiscal.md](workflow/fiscal.md) |
| HUB-F310 | Servir la declaración responsable y los datos del productor | parcial | [fiscal.md](workflow/fiscal.md) |
| HUB-F311 | Drenar la cola de contingencia por reloj | hecho | [fiscal.md](workflow/fiscal.md) |
| HUB-F312 | Drenar la cola a petición, con los permisos de quien la pide | hecho | [fiscal.md](workflow/fiscal.md) |
| HUB-F313 | En producción, sin vía no se cobra | parcial | [fiscal.md](workflow/fiscal.md) |
| HUB-F314 | Bloquear la cadena fiscal sin módulo que cumpla o con una instalación ajena | parcial | [fiscal.md](workflow/fiscal.md) |
| HUB-F315 | Clavar a pruebas un hub de demostración | hecho | [fiscal.md](workflow/fiscal.md) |
| HUB-F316 | No dejar en producción a un hub sin ningún módulo que cumpla su régimen | hecho | [fiscal.md](workflow/fiscal.md) |
| HUB-F317 | No emitir un documento fiscal sin la identidad del negocio | hecho | [fiscal.md](workflow/fiscal.md) |

## Qué comparten las áreas del servidor

Piezas que usan flujos de varias áreas: quien cambia una, abre los flujos de la tercera columna y
comprueba que siguen siendo ciertos. Lo que solo comparten los flujos de una misma área está en las
`## Reglas que no se rompen` de su fichero.

| Pieza compartida | Flujos que la usan | Si cambia, revisa |
|---|---|---|
| El embudo de una orden, con sus puertas siempre en el mismo orden: interna → bloqueo de otra app → permiso o PIN → edición parcial → esquema → reglas del dueño → permisos de host (motor nativo) → candados fiscales → transacción | Toda orden de cualquier módulo: F03–F13, F17, F33; F151, F152, F154; F89, F98; F274; F313, F314, F317 | La regla «El orden de las puertas…» de abajo; la Aprobación de un responsable de `HUB_SHELL` y SALES-F14 |
| Los datos que pone el hub en cada orden y nadie puede mandar (negocio, quién, hora, identidad fiscal, zona, idioma, demo, permisos concedidos, quién aprobó) | F01, F03, F10, F12; F222, F228; viajan dentro de cada aviso (F50) | Los manejadores y el SQL de los módulos que leen `:business_*`, `:timezone`, `:caller_lang` |
| La cola de avisos (`_event_outbox`) y su repartidor | F50–F63; F82, F93, F96; F191; F263, F266; F248, F249, F253; F03 (se guarda en la transacción de la orden) | Entrega al menos una vez, reintentos, «Eventos caídos», retención de 90 días y borrado de una persona |
| Los permisos de host concedidos a cada app (`_module_capability_grants`) | F12, F32, F35; F53, F58, F61; F111; F204, F205; F267–F270; F302 | Que el motor nativo, los avisos, la impresión, WhatsApp y el certificado sigan negando sin permiso; el reencolado de F58 |
| La credencial de máquina y el cliente de erplora.com (`cloud-client`) | F159, F164, F168, F169; F131; F19, F23–F25; F224, F234, F245–F247; F260–F272; F273, F275, F278; F305, F306 | Que nunca llegue al navegador (F168) y que cada puerta que la usa diga qué pasa sin ella |
| El plan firmado (entitlement) | F162, F163; F137, F147; el 402 de F01 y F03; la recogida de WhatsApp (F263) y su cupo (F272) | Qué puertas bloquean y cuáles no (regla del plan, abajo) |
| La pregunta «¿puede irse esta app?» (proveedor fiscal + obligaciones pendientes del motor) | F28, F29; F316 | Que desinstalar y desactivar miren lo mismo |
| El registro de una app al instalarla o actualizarla: consultas, órdenes, menú, recetas, tareas programadas, índice del asistente | F19, F23, F25, F26, F30; F104; F62; F275, F276 | Que desinstalar deshaga lo mismo que registrar (F29) |
| El registro único de errores y su envío a erplora.com | F14; F278; F166 | Que el texto que sale nunca lleve detalles internos |
| El latido diario a erplora.com | F164; F64; F254; F310; F272 | Lo que viaja en él y cuándo se borra lo entregado |
| La zona horaria del negocio | F227–F229; F83, F84; F62 (las tareas de los módulos siguen en UTC) | Que las horas de las automatizaciones sean hora de pared del negocio |
| Retención y borrado de una persona | F248–F253; los datos de avisos, automatizaciones, impresión (F206) y WhatsApp | Que lo terminal se vacíe y lo vivo no se toque |

## Cobertura contra la referencia

Cada área tiene su tabla (elemento de la referencia → estado → flujo) en su fichero. Lo que más
falta, por área:

- Módulos y órdenes ([modulos.md](workflow/modulos.md),
  [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md)): seguir cobrando mientras otra copia
  del hub se pone al día con una app (instalar y actualizar ya no paran la caja, y toda llamada a
  ERPlora para instalar se rinde a los 5 min); que una orden repetida no se ejecute dos veces; la
  factura pedida desde el tique.
- Avisos ([avisos.md](workflow/avisos.md)): avisar a quien lanzó lo que falló; tareas programadas con
  estado visible.
- Automatizaciones ([automatizaciones.md](workflow/automatizaciones.md)): reanudar desde el paso que
  falló; encender una receta todo-o-nada.
- Acceso, personas y plan ([acceso.md](workflow/acceso.md),
  [personas-y-permisos.md](workflow/personas-y-permisos.md),
  [plan-y-sistema.md](workflow/plan-y-sistema.md)): roles propios del dueño, «cerrar todas mis
  sesiones», el plan tras un reinicio sin conexión, el hub pausado.
- Impresión ([impresion.md](workflow/impresion.md)): «hecho» solo cuando sale el papel; retención de
  la cola.
- Negocio y datos ([negocio-y-datos.md](workflow/negocio-y-datos.md),
  [archivos-y-privacidad.md](workflow/archivos-y-privacidad.md)): borrar a una persona del equipo;
  plantilla que no lleve el certificado.
- WhatsApp y asistente ([whatsapp.md](workflow/whatsapp.md), [asistente.md](workflow/asistente.md)):
  la ventana de 24 h, los mensajes viejos tras un apagón, los motivos de Meta, la documentación de
  los módulos en el asistente.
- Perfil fiscal ([fiscal.md](workflow/fiscal.md)): cese de actividad; renovar la conexión segura;
  quitar el certificado en producción.

## Datos: de quién es cada dato

Lo común a todo el servidor:

- **Una base de datos por hub**, y además casi toda tabla de sistema lleva `hub_id`, que pone el hub
  y nadie puede mandar. No lo llevan las que son del despliegue o cuelgan de otra fila que sí lo
  lleva: `_hub_meta`, `_hub_migrations`, `_hub_system_migrations`, `_scheduled_tasks`,
  `_hub_fiscal_regime_registry`, `hub_api_key_rate_window`, `_hub_import_row` y
  `_hub_import_retired_row`; en `_event_delivery` es nulo en filas antiguas
  (`system_migrations.rs`).
- **Las tablas de sistema** (`hub_*` y `_*`) son del hub: las crea `system_migrations.rs`
  (`_hub_system_migrations` anota cuáles se aplicaron) y ningún módulo escribe en ellas salvo por las
  puertas del hub (ADR-0127). **Las tablas de cada app** llevan su prefijo, son de la app, el hub las
  crea y migra, y desinstalar no las borra.
- **Lo que el hub pone en cada orden**: el negocio, quién pide, quién aprobó, la hora, la identidad
  fiscal del negocio (que para un autónomo es su nombre y su NIF), la zona y el idioma; viaja también
  dentro de los avisos que la orden emite.
- **Lo que solo vive en memoria** y se pierde al reiniciar: el plan verificado, las aprobaciones con
  PIN sin gastar, los contadores de intentos, las memorias cortas del plan y de las series de uso
  (acceso), y los datos del productor y el permiso de envío de la celda fiscal (fiscal).
- **Retención**: lo terminal de avisos y automatizaciones se borra a los 90 días; los recibos de
  aprobación duran 4 años; la cola de impresión y los localizadores no se purgan (HUB-F253).

Qué tabla de sistema es de qué área (su inventario de datos personales está en `## Datos` del
fichero de esa área):

| Tablas | Área y fichero |
|---|---|
| `hub_module`, `_hub_migrations`, `hub_module_package`, `_module_capability_grants`, `_public_claim`, `_public_claim_key` | Módulos ([modulos.md](workflow/modulos.md), [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md)) |
| `_event_outbox`, `_event_delivery`, `_scheduled_tasks`, `_hub_activity` | Avisos ([avisos.md](workflow/avisos.md)) |
| `_flow`, `_flow_grants`, `_flow_triggers`, `_flow_runs`, `_flow_run_steps`, `_flow_approvals`, `_flow_run_waits`, `_flow_secrets` | Automatizaciones ([automatizaciones.md](workflow/automatizaciones.md)) |
| `hub_user`, `hub_session`, `hub_trusted_device`, `hub_user_profile`, `hub_user_pref`, `hub_role_activation`, `_elevation_audit`, `_hub_badge_key`, `hub_api_key`, `hub_api_key_rate_window`, `_policy`, `_update_history` | Acceso, personas y plan ([acceso.md](workflow/acceso.md)) |
| `_print_queue`, `_print_station`, `_print_route`, `_print_host` | Impresión ([impresion.md](workflow/impresion.md)) |
| `hub_settings`, `_hub_import_batch`, `_hub_import_row`, `_hub_import_retired_row`, `_hub_import_report` | Negocio y datos ([negocio-y-datos.md](workflow/negocio-y-datos.md)) |
| `_hub_activity_log`, y el almacenamiento de archivos (en erplora.com) | Negocio y datos ([archivos-y-privacidad.md](workflow/archivos-y-privacidad.md)); `_hub_activity_log` lo manda y vacía el latido de acceso |
| `hub_knowledge_chunk` | Asistente ([asistente.md](workflow/asistente.md)) |
| `_hub_fiscal_profile`, `_hub_fiscal_regime_registry`, `_hub_certificate`, `_hub_gateway_identity` | Perfil fiscal ([fiscal.md](workflow/fiscal.md)) |
| `_hub_meta`, `_hub_system_migrations` | Comunes: cada clave de `_hub_meta` la escribe su área |

## Reglas que no se rompen

Solo las que el código hace cumplir, por cualquier puerta (pantalla, asistente, automatización,
API, otra app). Las de cada área están en `## Reglas que no se rompen` de su fichero.

- **Cada fila es de un negocio.** El `hub_id` sale del despliegue, nunca de una cabecera (salvo en
  modo de desarrollo). El hub pone él mismo el negocio (`:hub_id`), quién pide y la hora en todo el
  SQL de las apps, y los sobrescribe si alguien los manda; cada petición se resuelve contra la base
  de su negocio antes de tocar nada, y ningún listado, reintento ni ejecución cruza de un hub a otro.
  El hub **no** comprueba que el SQL de una app filtre por `:hub_id`: la separación real es una base
  de datos por hub.
- **Una app solo escribe en sus tablas.** El SQL de sus órdenes y de su semilla, y sus migraciones,
  se rechazan si tocan tablas de otra app o del hub (HUB-F20, HUB-F21). Un manejador solo propone
  operaciones de su propia app, y un aviso solo lo atiende una orden de la app que escucha.
- **Primero se comprueba, luego se ejecuta.** El contenido de una orden se valida contra su esquema
  antes del manejador y de la base de datos; una consulta rechaza un dato que no conoce o que le
  falta. Excepción: las operaciones que propone un manejador no pasan por el esquema de su sub-orden
  (HUB-F10).
- **Una orden es una transacción**: sus cambios y la fila de cada aviso en la cola se guardan juntos o
  no se guarda nada; si declara un mínimo de filas y no llega, nada. Lo que hacen las apps que
  escuchan corre después, cada una en su propia transacción: si una falla, la orden sigue hecha y el
  aviso acaba en avisos caídos.
- **El permiso lo comprueba el servidor en cada orden.** Si lo tiene el perfil responsable de la app,
  se ofrece su PIN; la aprobación vale para una sola acción, de ese empleado, con ese contenido, y no
  sobrevive a otra copia del hub ni a un reinicio. Las consultas, la llave de API y las
  automatizaciones no se elevan.
- **El orden de las puertas de una orden no se cambia sin revisar** (HUB-F03): la huella del PIN se
  calcula sobre el contenido tal como llega, antes del cambio parcial y de los valores por defecto
  (si el esquema pasara delante, los PIN ya aprobados no casarían); las reglas del dueño tienen que ir
  después del permiso y del esquema (acceso); el permiso de una automatización fija parte del
  contenido antes del esquema (automatizaciones); `validate_payload`, que usan las aprobaciones
  manuales de los flujos, es la misma comprobación; la Aprobación de un responsable de `HUB_SHELL` y SALES-F14
  cuentan con que un cajero sin permiso vea `requires_elevation` antes que `invalid_payload`; y lo
  fijan `architecture/hub/runtime-dispatcher.md` §2.0 y las pruebas `kernel_conformance_permissions`,
  `command_elevation*` y `policy_gate_e2e`.
- **El plan contratado solo se comprueba en `/api/query` y `/api/command`** (402
  `module_entitlement_blocked`) y en la recogida de WhatsApp: la llave de API, la página pública, las
  automatizaciones, la cola de avisos y las tareas programadas no lo comprueban (hueco, HUB-F162).
- **Las órdenes internas de una app no se pueden pedir desde fuera**, ni las ofrece el asistente.
- **El dinero es un entero de unidades mínimas** y se redondea en un solo sitio, la mitad alejándose
  de cero (HUB-F18), en los módulos que enlazan la aritmética común.
- **Nada fiscal se simula.** Los candados fiscales del hub se aplican a toda orden, también a las de
  un manejador o una automatización; una demo nunca sale del entorno de pruebas (HUB-F315).
- **La credencial de máquina no sale nunca del servidor** (nunca llega al navegador): las credenciales de ERPlora solo viajan a erplora.com y a los anfitriones de confianza
  (HUB-F168). El hub no guarda credenciales de Meta ni del proveedor de IA.
- **Quién entra por cada puerta lo decide la sesión, no lo que dice la petición.** Una llave de API no
  es una persona: no entra por las puertas de la pantalla ni de configuración, no ve al personal y
  no pide aprobaciones. La cabecera `X-Erplora-Module` es una **declaración, no una autenticación**:
  si llega, el módulo que nombra necesita además su permiso de host; si no llega, basta la sesión.
- **Los errores no enseñan detalles internos** (motor de base de datos, direcciones de ERPlora): salen
  con un código estable y una frase fija (salvo el 401 de algunas puertas, que hoy sale sin código,
  HUB-F14).

## Lo que NO hace, a propósito

Lo común (lo de cada área, en `## Lo que NO hace, a propósito` de su fichero):

- No tiene funciones de negocio: vender, cobrar, facturar o reservar son de las apps.
- No pinta pantallas salvo la página pública del tique: sirve datos, y `HUB_SHELL` o el módulo los
  pintan (formularios de ajustes, paneles, lista de puesta en marcha, pantallas fiscales).
- No habla directamente con Meta, con un proveedor de IA ni con la AEAT: lo hacen la plataforma de
  ERPlora y la celda fiscal por él.
- No sirve varios negocios desde un proceso: la puerta multinegocio (`crates/server/src/tenant.rs`)
  existe pero no está cableada en producción.
- No ve nunca la contraseña de nadie ni manda correos de acceso: eso es de erplora.com.

## Dudas abiertas

Se resuelven con `market-decision` (negocio) o mirando el código (técnico); no las decide el worker
sobre la marcha. Las de cada área están en `## Dudas abiertas` de su fichero:
[modulos.md](workflow/modulos.md), [modulos-aplicaciones.md](workflow/modulos-aplicaciones.md),
[avisos.md](workflow/avisos.md), [automatizaciones.md](workflow/automatizaciones.md),
[acceso.md](workflow/acceso.md), [personas-y-permisos.md](workflow/personas-y-permisos.md),
[plan-y-sistema.md](workflow/plan-y-sistema.md), [impresion.md](workflow/impresion.md),
[negocio-y-datos.md](workflow/negocio-y-datos.md),
[archivos-y-privacidad.md](workflow/archivos-y-privacidad.md), [whatsapp.md](workflow/whatsapp.md),
[asistente.md](workflow/asistente.md) y [fiscal.md](workflow/fiscal.md).

Comunes a varias áreas:

1. **Reconciliar una app entre copias para esa copia del hub** —caja, avisos y comprobación de
   salud incluidos— mientras la descarga (HUB-F26, hub#2555). Instalar, actualizar e importar una
   plantilla ya descargan fuera del candado (HUB-F19, HUB-F23, hub#2508), y toda llamada a ERPlora
   de cualquiera de ellos —también la de reconciliar— se rinde a los 5 min (hub#2556). Afecta a
   todas las áreas, no solo a módulos.
2. **El plan tras un reinicio sin conexión** (HUB-F162): hoy el hub no aplica ningún tope hasta su
   primera comprobación buena. ¿Se guarda el último plan firmado en base de datos? Afecta al cobro,
   a las automatizaciones y a WhatsApp.
3. **Hub pausado** (HUB-F162): el servidor no tiene ese estado y la pantalla «Activación requerida»
   no se alcanza. ¿Qué debe ver el negocio cuando erplora.com le suspende el plan?
4. **Borrado RGPD de lo que no lleva el identificador de la ficha**: los WhatsApp entrantes, la cola
   de impresión, los localizadores, las ejecuciones vivas (HUB-F249, HUB-F251, HUB-F206). Cruza
   negocio y datos, avisos, automatizaciones, WhatsApp e impresión.
5. **Borrado RGPD de una persona del equipo que lo pide al irse** (HUB-F149, HUB-F252): hoy solo se
   desactiva. El recibo de aprobaciones se conserva 4 años por ley, pero nombre, correo y foto del
   perfil no tienen camino de borrado. ¿Se borran, o se seudonimiza la ficha? Cruza acceso y negocio
   y datos.

## Fuentes contrastadas

Discrepancias entre lo que dicen el manual, las `docs/`, `architecture/` o los guiones de QA y lo
que hace el código. Las de cada área están en `## Fuentes contrastadas` de su fichero. Comunes:

- Los documentos de `architecture/hub/` son «as-built» y van por detrás: varios siguen como
  «propuesta» o «pendiente» con el código ya hecho, o citan líneas y rutas que ya no casan (cada área
  dice cuáles). Son semilla, no verdad.
- Las pestañas de Ajustes se llaman «General» (no «Hub») y «Datos y copias» (no «Datos») (`es.ts`);
  `architecture/hub/auth.md` aún dice «Ajustes › Hub».
- Los textos que el servidor manda tal cual a la pantalla (rechazos del motor de automatizaciones,
  `409` de reenviar un aviso) están en inglés. Las negativas fiscales al apagar o desinstalar una
  app ya se traducen por su código (hub#2579).
