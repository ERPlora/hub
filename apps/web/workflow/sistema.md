# WORKFLOW — Hub · pantallas · Sistema

Prefijo: HUB_SHELL

> Detalle del área «Sistema»: la pantalla Sistema y sus cinco pestañas (Recursos, Plan y límites,
> Actualizaciones, Eventos caídos, Registros) y el informe automático de errores de la pantalla.
> Código: `views/SystemPage.vue` y `lib/system.ts`, `system-tabs.ts`, `system-health.ts`,
> `system-metrics.ts`, `system-usage.ts`, `dead-letter.ts`, `update-history.ts`, `app-update.ts`,
> `error-report.ts`. La pestaña Plan y límites la cuenta HUB_SHELL-F128
> (`workflow/plan-y-archivos.md`; aquí F141 quedó retirado); «Tus apps» de Actualizaciones, HUB_SHELL-F119 (`workflow/aplicaciones.md`).

## Referencia adoptada

El panel de estado de Square Dashboard / Toast («Hardware» y estado de impresoras), la página
«Estado del sistema» de Odoo (rendimiento + actualizaciones) y la bandeja de «eventos fallidos con
reintento» de Zapier / Make / Shopify Flow (ver, reintentar uno, reintentar todos, descartar). Ya
contrastadas en `qa-hub-flows` R8 y `qa-hub` §8.

## Antes de empezar

- Para ver y tocar los eventos caídos hace falta ser dueño o administrador; el resto de perfiles ve la
  pestaña como vacía (HUB_SHELL-F145).
- El estado del sistema (uso del servidor, versión y Registros) también es solo de dueño o
  administrador (HUB-F166): el resto de perfiles ve en Recursos solo las tarjetas de su dispositivo
  y no tiene la pestaña Registros.

## Flujos

### HUB_SHELL-F135 Abrir Sistema y moverse por sus pestañas
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Sistema
Pasos:
1. Pulsa **Sistema** en el menú lateral (sección «Cuenta»), o llega desde un enlace: la campana (Eventos caídos), la fila «Acceso a recursos locales y de red» de Ajustes, o el enlace de salud de Inicio.
2. Mientras el hub contesta, sale un círculo de carga en el centro de la pantalla.
3. Abajo hay cinco pestañas, en este orden: **Recursos**, **Plan y límites**, **Actualizaciones**, **Eventos caídos**, **Registros**. Se abre **Recursos**; la pestaña elegida queda en la dirección (`#resources`, `#plan`, `#updates`, `#events`, `#logs`), así que el botón Atrás y un enlace guardado vuelven a la misma pestaña.
4. Una dirección con una pestaña que no existe abre **Recursos**; la antigua `#backups` ya no es una pestaña: lleva a **Ajustes › Datos y copias**.
5. Quien no es dueño ni administrador ve cuatro pestañas: **Registros** no existe para él, y `#logs` abre **Recursos**.
Entra: la sesión de cualquiera de los perfiles (la entrada del menú no se oculta a nadie); el estado del sistema que da el hub (HUB-F166), que solo se pide con sesión de dueño o administrador: al resto no se le pide (el hub lo negaría) y no le sale ningún aviso de error por ello. Si la sesión pasa a ser de administrador con la pantalla abierta, se pide entonces; si deja de serlo (cambio de persona en una caja compartida), lo leído sale de la pantalla. También se llega a `#updates` desde Apps (acción de ver las actualizaciones del hub).
Sale: nada guardado.
Si falla: si el hub no contesta al estado del sistema sale, encima de la pestaña, el aviso «No se pudo consultar el sistema — Las métricas y los registros no están disponibles ahora. Puedes volver a intentarlo.» con **Reintentar**, que solo vuelve a pedir ese estado (cada pestaña pide lo suyo aparte). En móvil la barra de pestañas se desplaza; en tableta y escritorio caben todas.
Implicados: HUB-F166
QA: ninguno

### HUB_SHELL-F136 Ver cuánto está usando el hub
Estado: hecho
Actor: administrador
Pantalla: Sistema › Recursos
Pasos:
1. El dueño o un administrador abre **Recursos**. El título es «Recursos en la nube» y una pastilla dice «Nube». Quien no administra no ve este bloque (ni pide la evolución): en su lugar lee «Solo el dueño o un administrador puede ver cuánto está usando el hub.» y debajo le quedan las tarjetas de su dispositivo (F137–F140).
2. Debajo hay un selector de rango: «3 h», «24 h» (el que se abre) y «3 días». Es el máximo a propósito: erplora.com no guarda más.
3. Ve cuatro tarjetas: **CPU**, **Memoria**, **Base de datos** (siempre «PostgreSQL» y debajo «Base de datos compartida»: el hub no manda el tamaño; el tamaño solo lo da **Plan y límites**) y **Conexiones**. CPU, memoria y conexiones llevan el valor actual y la evolución del rango elegido, con la etiqueta «Últimas 24 horas» (o la del rango).
4. Cerca del límite de su plan, la tarjeta dice «Al {pct} % del límite de tu plan.»; por encima, «Al {pct} % del límite de tu plan: el hub puede ir más lento.». Si erplora.com marca que el plan se queda corto, sale además «Tu plan se está quedando corto de recursos. Con un plan mayor este hub tiene más margen.» con **Actualizar plan**, que abre erplora.com en el navegador del sistema; ese botón no sale en la copia que reparte Google Play.
5. Cambiar de rango vuelve a pedir la evolución. La pantalla no se refresca sola: se ve lo que había al abrirla o al cambiar de rango.
Entra: el estado actual del hub (HUB-F166) y la evolución de uso que el hub pide a erplora.com (HUB-F165); el aviso de plan corto lo decide erplora.com.
Sale: nada guardado. **Actualizar plan** sale por la puerta compartida a erplora.com con pase de un solo uso.
En este mismo documento se apoya en: HUB_SHELL-F16 (Ir a erplora.com ya identificado), HUB_SHELL-F129 (Ir a erplora.com a gestionar o mejorar el plan).
Si falla: lo que no se pudo medir sale «No hemos podido leerlo», nunca 0 ni una línea verde plana; si la evolución no llega pero el valor actual sí, se pinta ese valor. Si el viaje a erplora.com no se puede hacer, un aviso lo dice («No se pudo abrir tu navegador. Entra en erplora.com para gestionar tu plan.»).
Implicados: HUB-F165, HUB-F166
QA: ninguno

### HUB_SHELL-F137 Ver si la impresora está lista
Estado: parcial — la frase «Volveremos a comprobarlo solos» promete una repetición que esta pantalla no hace: solo comprueba al abrirla y con el botón de recomprobar
Actor: administrador, responsable, empleado
Pantalla: Sistema › Recursos
Pasos:
1. Abre **Recursos**. Si el hub no tiene la app de impresión instalada y activa, no hay tarjeta de impresora: un negocio que no imprime no ve nada de esto.
2. Con la app de impresión, sale la tarjeta **Tu impresora** con una pastilla y una frase: «Impresora lista — Los tiques salen solos al cobrar.»; «Impresora sin conectar — Puedes seguir cobrando: el tique sale en esta pantalla y lo imprimes desde aquí.» con el botón **Configurar la impresión** (lleva a la app de impresión); o «No hemos podido comprobar la impresora — No sabemos si está conectada; no afecta a nada más. Volveremos a comprobarlo solos.», sin botón.
3. El estado habla de la estación de tiques de venta (quién la está sacando ahora mismo), no de si este dispositivo ve un aparato: otra estación, como la cocina, no lo pone en verde.
4. El icono de **Recomprobar** (junto a la pastilla) vuelve a preguntar; si la app instalada de este dispositivo responde, la versión sale al final de la frase («· v1.4.0»).
5. Si este dispositivo no alcanza el hardware, debajo salen los pasos numerados de ponerlo en marcha: «Descargar», «Instalar», «Vincular», «Configurar» en un navegador, y solo «Vincular», «Configurar» dentro de la app instalada.
Entra: la cobertura de impresión (quién saca cada estación, HUB impresión), las apps instaladas y la sonda del hardware de este dispositivo (HUB_PERIPHERALS).
Sale: nada guardado.
Si falla: lo que no se pudo leer es el tercer estado, «No hemos podido comprobar», en neutro: nunca verde, y sin botón, porque el fallo no es tarea de quien mira. La lista de apps ilegible deja la tarjeta oculta.
Implicados: HUB-F202, PRINTING-F01, PRINTING-F04
QA: ninguno

### HUB_SHELL-F138 Descargar la app de ERPlora desde Sistema
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Sistema › Recursos
Pasos:
1. En un navegador, con la tarjeta **Tu impresora** a la vista y este dispositivo sin hardware, debajo de los pasos sale «Descargar la app de ERPlora — La app de ERPlora es la que habla con tus impresoras, el cajón y los escáneres. Elige tu sistema para continuar.».
2. Pulsa **Windows** (el botón destacado), **Linux** o **Android**. No hay macOS: erplora.com no publica ninguno.
3. El navegador abre la descarga que sirve erplora.com en ese momento y sale el aviso «Descargando ERPlora para {os}…».
4. Instala la app y la vincula (los pasos de arriba).
Entra: la plataforma elegida.
Sale: nada guardado. La descarga es la de erplora.com (siempre la última publicada).
En este mismo documento se apoya en: HUB_SHELL-F20 (Actualizar la aplicación instalada cuando hay versión nueva).
Si falla: «No se ha podido descargar el archivo.». Dentro de la app instalada este bloque no existe (sería la app ofreciéndose instalarse); actualizar la app instalada es otro gesto, desde el menú lateral.
Implicados: HUB_APP-F01, SAAS_PUBLIC-F33
QA: ninguno

### HUB_SHELL-F139 Volver a activar los avisos de este dispositivo
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Sistema › Recursos
Pasos:
1. Solo en un Android 13 o superior dentro de la app instalada, con los avisos rechazados y alguna app que avisa (cocina, citas o cualquiera con contador en la campana) activa, **Recursos** muestra la tarjeta «Los avisos están desactivados — Este dispositivo no te avisará cuando algo necesite tu atención. Actívalos y lo dirá en voz alta, aunque nadie esté mirando la pantalla.». En un navegador, en el escritorio o con los avisos concedidos no existe.
2. Pulsa **Activar los avisos**: el dispositivo vuelve a preguntar. La pantalla relee el estado real y empieza a escuchar con la pantalla apagada desde ese momento.
3. Si ya está concedido: «Listo: este dispositivo te avisará cuando algo necesite tu atención.» y la tarjeta desaparece.
4. Si no: «Tu dispositivo no ha vuelto a preguntar. Entra en sus ajustes, busca ERPlora y activa sus notificaciones.». **Abrir los ajustes** lleva a la página de la app en los ajustes del dispositivo; al volver a la app la tarjeta se actualiza sola.
Entra: el permiso de notificaciones del dispositivo y las apps activas.
Sale: el permiso del dispositivo y, si se concede, la escucha con pantalla apagada (HUB_APP).
En este mismo documento se apoya en: HUB_SHELL-F60 (Ver en la campana lo que espera atención), HUB_SHELL-F61 (Atender desde la campana lo que pone una app).
Si falla: si los ajustes del dispositivo no se pueden abrir (app más antigua que la orden) se dice a dónde ir a mano, con la misma frase.
Implicados: HUB_APP-F07, HUB_APP-F08, HUB_APP-F26
QA: ninguno

### HUB_SHELL-F140 Volver a permitir la búsqueda de impresoras
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Sistema › Recursos
Pasos:
1. Solo en un Android 17 o superior dentro de la app instalada, con el permiso de red local rechazado, **Recursos** muestra «La búsqueda de impresoras está bloqueada — Este dispositivo no tiene permiso para llegar a las impresoras de tu red, así que la búsqueda vuelve vacía por muchas impresoras que haya encendidas.». En cualquier otro sitio no existe: avisar de un bloqueo que no puede darse sería una falsa alarma.
2. Pulsa **Permitir la búsqueda**: el dispositivo vuelve a preguntar y la pantalla relee el estado real.
3. Concedido: «Listo: este dispositivo ya puede buscar impresoras en tu red.». Rechazado otra vez: «Tu dispositivo no ha vuelto a preguntar. Abre sus ajustes, busca ERPlora y concédele el acceso a la red local.», y **Abrir los ajustes** lleva a la página de la app.
Entra: el permiso de red local del dispositivo.
Sale: el permiso del dispositivo.
Si falla: igual que F139.
Implicados: HUB_APP-F08, HUB_PERIPHERALS-F01, PRINTING-F02
QA: ninguno

### HUB_SHELL-F141 [retirado] Ver el plan y sus límites
Implicados: ninguno
Sustituido por HUB_SHELL-F128 (`workflow/plan-y-archivos.md`): era el mismo gesto, la pestaña Sistema › Plan y límites (`components/PlanLimitsPanel.vue`).

### HUB_SHELL-F142 Saber qué versión corre y qué se le ha actualizado
Estado: parcial — un historial que no se pudo leer sale igual que uno vacío («No te hemos cambiado nada»), justo la confusión que Eventos caídos evita; no hay botón para actualizar el hub a propósito (se actualiza solo)
Actor: administrador, responsable, empleado
Pantalla: Sistema › Actualizaciones
Pasos:
1. Abre **Actualizaciones**. El título es «Qué te hemos actualizado» y, para un dueño o administrador, una pastilla dice «Vas por la {versión}» (con «—» si el hub no la dio); quien no administra no ve la pastilla, porque la versión viaja en el estado del sistema (HUB-F166).
2. Debajo: «Este Hub web se actualiza automáticamente durante los despliegues del servicio.». El hub se actualiza solo, sin preguntar y sin botón: esta pestaña existe para que el dueño pueda saber qué le cambiaron.
3. Si hubo cambios (como mucho los 20 últimos, de los últimos 90 días), salen agrupados por día (más reciente primero; «Hoy», «Ayer» o la fecha completa en el reloj del negocio): hora, nombre de la app como el dueño la conoce y «1.1.1 → 1.1.2».
4. Una vuelta atrás se dice: «Volvió a la {versión}: la nueva no arrancó». Una app que quedó sin funcionar: «Esta app no está funcionando: estamos en ello». El error técnico que causó la vuelta atrás no se pinta.
5. Sin cambios: «No te hemos cambiado nada — No hemos actualizado nada en este hub últimamente. Cuando lo hagamos, aparecerá aquí.». Al cambiar de idioma se vuelve a pedir, porque los nombres de las apps vienen ya traducidos.
Entra: la versión del hub y el historial de actualizaciones (HUB-F167).
Sale: nada guardado.
Si falla: la lectura no lanza nada y una lectura fallida sale como lista vacía; la versión ilegible, como «—».
Implicados: HUB-F23, HUB-F25, HUB-F167
QA: qa-hub-restaurant §7.00

### HUB_SHELL-F143 Saber si tus apps tienen una versión nueva
Estado: hecho
Actor: administrador
Pantalla: Sistema › Actualizaciones
Pasos:
1. En **Actualizaciones**, un administrador ve el bloque «Tus apps». Quien no administra no lo ve: no podría actualizar nada.
2. Dice una de cuatro cosas: «{n} app tiene una versión nueva.» / «{n} apps tienen una versión nueva.» con **Ir a Mis apps**; «Todas tus apps están al día.»; «Comprobando si tus apps tienen versiones nuevas…» mientras la primera comprobación no ha vuelto; o, si no se pudo comprobar, «No hemos podido saber si tus apps tienen versiones nuevas. Revisa la conexión y vuelve a intentarlo.» con **Comprobar de nuevo**.
3. **Ir a Mis apps** abre Apps en «Mis apps», donde se actualiza.
Entra: la misma cuenta que usa la campana (solo lo que este hub puede aplicar); esta pestaña no pregunta al catálogo por su cuenta.
Sale: nada guardado.
En este mismo documento se apoya en: HUB_SHELL-F105 (Ver las apps instaladas en el negocio), HUB_SHELL-F116 (Actualizar una app).
Si falla: una comprobación fallida nunca dice «al día»; con un recuento ya conocido, gana el recuento.
Implicados: HUB-F24
QA: ninguno

### HUB_SHELL-F144 Ver el registro de sucesos del sistema
Estado: parcial — el «evento» es el nombre interno del aviso y el «detalle» su estado crudo (`delivered`, `pending`) o su último error tal cual, sin traducir; «El runtime no ha reportado…» es jerga
Actor: administrador
Pantalla: Sistema › Registros
Pasos:
1. El dueño o un administrador abre **Registros**: el título es «Registro de eventos». Para el resto de perfiles la pestaña no existe (F135).
2. Ve una tabla con **Hora**, **Nivel** (pastilla INFO, WARN o ERROR; se puede filtrar por nivel) y **Evento** (el mensaje y, a su lado, el detalle). Se busca con «Buscar evento…» y pagina de 20 en 20.
3. Sin sucesos: «Sin eventos — El runtime no ha reportado eventos recientes.».
Entra: los 50 últimos avisos entre apps (HUB-F166) con su estado o su último error, sin el contenido del aviso; solo un dueño o administrador, igual que la cola de F145 (el último error puede llevar datos de un cliente).
Sale: nada guardado.
Si falla: si el estado del sistema no se pudo leer, sale el aviso general de F135 y debajo la lista vacía «Sin eventos»; el mensaje de cada fila es el del hub, sin traducir. Una lectura fallida sale como «Sin eventos» bajo el aviso de error.
Implicados: HUB-F166
QA: ninguno

### HUB_SHELL-F145 Ver los eventos caídos
Estado: parcial — quien no administra ve «Todo en orden» sin que nadie haya mirado la cola; la lista enseña solo los 100 más recientes y cada fila no muestra el contenido ni quién lo causó (el hub los da); la fila enseña el nombre interno del evento y el último error sin traducir (salvo en un WhatsApp, que dice qué pasó y por qué)
Actor: administrador
Pantalla: Sistema › Eventos caídos
Pasos:
1. Un administrador llega desde la fila «Eventos caídos» de la campana (que lleva a `#events`) o pulsando la pestaña **Eventos caídos**.
2. Mientras carga, un círculo. Con eventos, sale el texto «Arregla la causa (permiso, módulo caído…) y reenvía. El contenido no se edita: si la causa sigue, el evento vuelve a morir aquí.».
3. Cada fila trae el nombre interno del evento (en código), una insignia «{n}× intentos», el identificador de la app que lo emitió, cuándo ocurrió y el último error tal cual. Si el evento no se puede reenviar, debajo dice «Este no se puede reenviar: la autorización que lo permitía se retiró y el destinatario ya no está en la fila. Vuelve a conceder el permiso y relanza el flujo.» y no lleva el botón de reenviar.
4. Un WhatsApp que no llegó (HUB-F266) dice además, encima del error, qué pasó y por qué, en el idioma del negocio: «WhatsApp rechazó este mensaje: {motivo}» y debajo «No llegó a enviarse. Arregla la causa y reenvíalo.», o «WhatsApp aceptó este mensaje pero no lo entregó: {motivo}» y debajo «Reenviarlo no lo volvería a mandar: WhatsApp ya lo tiene. Avisa al cliente por otra vía, o contéstale desde la conversación cuando te escriba.» (sin botón de reenviar). El motivo es una frase por cada causa que da WhatsApp (por ejemplo, «el cliente no te ha escrito en las últimas 24 horas y, fuera de ese plazo, WhatsApp solo deja mandar una plantilla aprobada.»); una causa que la pantalla no conoce sale como «WhatsApp no dijo por qué.».
5. Cada fila lleva a la derecha dos iconos sin texto: reenviar (F146) y descartar (F148). Encima, **Reenviar todos** (F147).
6. Sin eventos: «Todo en orden — No hay eventos caídos. La cola de eventos vive en la base de datos: un reinicio nunca la pierde.».
7. Un perfil que no es dueño ni administrador no pide la cola (el hub se la negaría) y la pestaña le sale como si estuviera vacía.
Entra: la cola de eventos caídos del hub (HUB-F54); solo un dueño o administrador.
Sale: nada guardado. La lista se carga al entrar en la pestaña y cuando la sesión pasa a ser de administrador; no se refresca sola ni tiene botón de recargar.
En este mismo documento se apoya en: HUB_SHELL-F60 (Ver en la campana lo que espera atención), HUB_SHELL-F62 (Ver en la campana los avisos entre apps que no se entregaron).
Si falla: un fallo de lectura no es una cola vacía: sale «No se pudo consultar el sistema — No se pudo cargar la cola de eventos caídos. Comprueba la conexión y reintenta.» con **Reintentar**, para que un error de red o de permiso no se lea como «Todo en orden» (puede ser fiscal).
Implicados: CASH_REGISTER-F14, FLOWS-F25, HUB-F54, INVOICE-F06, REC_FISCAL-F09
QA: qa-hub-flows R8

### HUB_SHELL-F146 Reenviar un evento caído
Estado: parcial — el aviso de éxito dice «relay» (palabra interna, en español), los iconos de la fila no llevan texto ni etiqueta, y tras «ese mensaje ya no está en la cola» la fila vieja sigue a la vista hasta volver a entrar
Actor: administrador
Pantalla: Sistema › Eventos caídos
Pasos:
1. Quien arregló la causa (concedió el permiso, abrió la caja, corrigió la regla de impuestos) pulsa el icono de reenviar de la fila.
2. El botón de esa fila queda desactivado mientras se hace.
3. Sale «Evento reenviado al relay.», la lista se recarga y la fila desaparece; la fila de la campana se actualiza al instante.
4. Si la causa sigue, el evento vuelve a caer y reaparece en la lista.
Entra: el evento elegido (solo los reenviables tienen el botón).
Sale: el evento pendiente de nuevo, con los intentos a cero (HUB-F55); solo lo recibe la app que había fallado.
Si falla: «No se pudo reenviar: {motivo}». El motivo sale de un código, no del texto del hub: «ese mensaje ya no está en la cola; actualiza la lista.», «a ese mensaje le faltan los datos que necesita para volver a enviarse.», «se retiró el permiso que lo generó; vuelve a concederlo y lanza la automatización.», «la app que lo generó ya no tiene permiso para hacerlo.»; sin código conocido, «no se ha podido leer el motivo».
Implicados: CASH_REGISTER-F14, FLOWS-F25, HUB-F54, HUB-F55, INVENTORY-F21, INVOICE-F06, REC_FISCAL-F09
QA: qa-hub-flows R8

### HUB_SHELL-F147 Reenviar todos los eventos caídos
Estado: parcial — el aviso de éxito dice «relay» (palabra interna, en español) y no pide confirmación
Actor: administrador
Pantalla: Sistema › Eventos caídos
Pasos:
1. Tras una caída pasajera que tumbó varios eventos, el administrador arregla la causa y pulsa **Reenviar todos** (solo sale con la lista no vacía; se desactiva mientras trabaja).
2. Sale «{count} evento reenviado al relay.» o «{count} eventos reenviados al relay.», la lista se recarga y la campana se actualiza.
Entra: la sesión de administrador.
Sale: todos los eventos caídos reenviables del hub vuelven a la cola, también los que no caben en la lista de 100 (HUB-F56); los no reenviables se quedan.
Si falla: «No se pudo reenviar: {motivo}», con las mismas frases que F146.
Implicados: FLOWS-F25, HUB-F54, HUB-F56, INVOICE-F06
QA: qa-hub-flows R8

### HUB_SHELL-F148 Descartar un evento caído
Estado: parcial — la pantalla no pide ni envía motivo (el hub lo admite), usa la ventana de confirmación del navegador, y su texto habla de «fila» y de «relay»; no dice qué evento es ni qué deja de pasar
Actor: administrador
Pantalla: Sistema › Eventos caídos
Pasos:
1. El administrador decide que un evento no debe entregarse nunca (duplicado, ya resuelto a mano, ya no aplica) y pulsa el icono de la papelera de su fila.
2. El navegador pregunta, en su ventana de confirmación y no en la del producto: «¿Descartar este evento para siempre? La fila se conserva (auditable), pero el relay no volverá a entregarla. Úsalo solo si el evento no debe registrarse.».
3. Si acepta, sale «Evento descartado (se conserva para auditoría).», la lista se recarga y la campana se actualiza. Si cancela, no pasa nada.
Entra: el evento elegido.
Sale: el evento cerrado, con quién y cuándo (HUB-F57); no se borra y no se vuelve a intentar. Descartar el cobro de una venta la deja sin factura para siempre. La pantalla no manda motivo, así que el campo queda vacío.
Si falla: «No se pudo descartar: {motivo}», con las mismas frases que F146.
Implicados: FLOWS-F25, HUB-F54, HUB-F57, INVOICE-F06, REC_FISCAL-F09
QA: qa-hub-flows R8

### HUB_SHELL-F149 Informar de un error de la pantalla sin que nadie lo pida
Estado: parcial — es solo automático: no hay botón para que la persona cuente qué le ha pasado (el único informe a mano está bajo las respuestas del asistente)
Actor: sistema
Pantalla: ninguna
Pasos:
1. La persona no hace nada: cuando la pantalla lanza un error que nadie recogió, una promesa rechazada sin tratar o un fallo al pintar un componente, el shell lo apunta.
2. Lo envía al hub, sin ventana, sin captura y sin pedir confirmación.
3. Un error idéntico no se vuelve a enviar durante 30 segundos, y se recuerdan como mucho 50 distintos.
Entra: el mensaje del error, su pila, la dirección de la pantalla, el componente; la app de la vista de un módulo no consta (siempre vacío).
Sale: un informe al hub, que lo reenvía a erplora.com. No se guarda nada en el navegador.
En este mismo documento se apoya en: HUB_SHELL-F198 (Informar de una respuesta mala).
Si falla: no pasa nada visible: el envío es de mejor esfuerzo, no se reintenta y no genera otro informe.
Implicados: HUB-F278, SAAS-F05, SAAS_DASHBOARD-F71
Pendiente de enlazar: hub — HUB, el embudo de errores del frontend (`/api/error-report`) hacia erplora.com
QA: ninguno

## Cobertura contra la referencia

| Elemento | Estado | Flujo |
|---|---|---|
| Uso de CPU, memoria, BD y conexiones con rango | hecho | HUB_SHELL-F136 |
| Estado de impresoras, con salida para arreglarlo | parcial | HUB_SHELL-F137 |
| Avisos del dispositivo y búsqueda de impresoras, con salida | hecho | HUB_SHELL-F139, HUB_SHELL-F140 |
| Plan y límites en vivo | parcial | HUB_SHELL-F128 (`plan-y-archivos.md`; F141 retirado) |
| Versión que corre e historial de cambios | parcial | HUB_SHELL-F142 |
| Actualizar el hub desde la pantalla | no hecho a propósito (se actualiza solo) | HUB_SHELL-F142 |
| Actualizar las apps | hecho (desde Mis apps) | HUB_SHELL-F143 |
| Registro de sucesos | hecho | HUB_SHELL-F144 |
| Cola de eventos fallidos: ver, reenviar uno, reenviar todos | parcial | HUB_SHELL-F145, HUB_SHELL-F146, HUB_SHELL-F147 |
| Descartar con motivo | parcial (no se envía el motivo) | HUB_SHELL-F148 |
| Ver lo ya cerrado (quién, cuándo, por qué) | no hecho (el hub lo da, no hay pantalla) | HUB_SHELL-F148 |
| Informe de error automático | parcial | HUB_SHELL-F149 |
| Botón «Informar de un problema» a mano en Sistema | no hecho | — |

## Datos: de quién es cada dato

- La cola de eventos es del servidor; esta área no guarda nada propio. Lo único que la pantalla
  recuerda es la pestaña, en la dirección; el rango de uso no se guarda.
- Datos personales: el contenido de los eventos caídos (la pantalla no lo pinta pero el hub lo sirve).
  El informe automático de errores (HUB_SHELL-F149) puede arrastrar texto de pantalla dentro del
  mensaje o la pila.

## Reglas que no se rompen

- Descartar un evento caído no borra la fila.

## Lo que NO hace, a propósito

- No hay botón de «Actualizar el hub»: se actualiza solo y Sistema solo cuenta lo que cambió.
- No hay botón «Ver planes» en Plan y límites (regla común del índice: el hub no vende).
- No se edita el contenido de un evento caído: se arregla la causa y se reenvía tal cual.
- No hay pestaña de documentos en Sistema (retirada; quedan textos sin uso en los catálogos) ni macOS
  en la descarga de la app.

## Dudas abiertas

- ¿Descartar un evento caído debe pedir un motivo en pantalla (el hub lo admite)? Propuesta: sí, un
  campo opcional, y sustituir la ventana del navegador por la del producto.
- ¿Una pestaña de Eventos caídos para quien no administra debe decir «solo un administrador»?
  Propuesta: sí.
- ¿Los 100 eventos más recientes bastan, o hay que paginar?

## Fuentes contrastadas

- Manual `07-sistema.md`: dice «Eventos» y «acciones administrativas ocultas o rechazadas para otros
  roles»; la pestaña se llama «Eventos caídos» y a un no administrador le sale vacía («Todo en orden»).
- Servidor (HUB-F57): el motivo del descarte es opcional y se guarda; la pantalla no lo manda.
  Servidor (HUB-F54): el hub sirve el contenido y quién causó el evento; la pantalla no los pinta.
- Servidor (HUB-F166): «últimos 50 avisos entre apps como Registros y los documentos guardados en la
  nube»; la pantalla ya no tiene documentos.
