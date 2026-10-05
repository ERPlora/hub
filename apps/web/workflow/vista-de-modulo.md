# WORKFLOW — Hub · pantallas · La vista de un módulo

Prefijo: HUB_SHELL

> Detalle del índice `apps/web/WORKFLOW.md`. Es el marco donde se pintan las 27 apps: lo que aquí
> se escribe lo dan por hecho todas ellas. Código: `views/ModuleView.vue`, `lib/module-loader.ts`,
> `components/ModuleSettingsForm.vue`, `lib/module-settings.ts`, `components/ModulePlanPanel.vue`,
> `lib/module-quota.ts`, `lib/module-usage.ts`, `lib/protects.ts`, `components/ElevationDialog.vue`,
> `lib/elevation.ts`, `lib/runtime-error-sentence.ts`, `lib/module-failure-message.ts`,
> `lib/invalid-field.ts`, `lib/slot-fillers.ts`, `lib/immersive.ts`, `lib/outfitkit-skew.ts` y la
> traducción de rechazos del SDK (`packages/module-sdk/src/index.ts`, `unwrap`).

## Flujos

### HUB_SHELL-F40 Abrir una app y ver su primera pestaña
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Vista de un módulo
Pasos:
1. La persona abre una app desde el menú lateral, desde «Mis apps» de Inicio o con «Abrir» en Aplicaciones.
2. Mientras baja el código de la app se ve un esqueleto de página (una barra de título y seis filas grises); quien usa lector de pantalla oye «Cargando módulo…».
3. La app aparece con su nombre traducido arriba y, si tiene más de una pestaña, la barra de pestañas abajo; se abre en la primera pestaña y la dirección pasa a nombrarla (`/m/<app>/<pestaña>`), de modo que «Atrás» sale de la app y no recorre pestañas.
4. Un enlace directo a una pestaña (`/m/inventory/products`) abre esa pestaña.
Entra: el menú de las apps activas, con sus nombres en el idioma de la persona y la versión instalada (HUB-F31); el `module.json` y el código de la app, pedidos una sola vez por sesión.
Sale: la pantalla de la app montada, con el cliente del hub limitado a esa app (el módulo no puede hablar en nombre de otro). Nada guardado.
Si falla: ver HUB_SHELL-F41. Si la persona se va de la app, la pantalla escondida suelta la app (deja de oír avisos y la dirección) y al volver la monta de nuevo: así una caja escondida no se come el `?appointment_id=` de la caja visible (hub#1797); un ir y volver rápido no deja la pantalla en el esqueleto para siempre (hub#2241).
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F31 (servir el menú, las pantallas y los ficheros de las aplicaciones)
QA: BD-03

### HUB_SHELL-F41 Entender por qué una app no se abre
Estado: parcial — una app cuyas pestañas exigen un permiso que la persona no tiene se pinta como «Aquí todavía no hay nada» y la manda a Apps, cuando el motivo es el permiso; y la vista no tiene estado propio «necesita un hub más nuevo» (eso solo se dice al instalar o actualizar)
Actor: empleado, responsable, administrador
Pantalla: Vista de un módulo
Pasos:
1. La persona abre una app y, en lugar de su pantalla, ve uno de estos avisos, cada uno con su motivo:
2. Sin red: «Sin conexión a Internet» — «Esta pantalla necesita la conexión para cargarse. Revisa la red — vuelve sola en cuanto haya Internet otra vez.» con «Reintentar»; al volver la red la pantalla se monta sola.
3. El hub contestó con un fallo: «No se pudo cargar el módulo.» — «Comprueba que el módulo siga instalado y activo, y vuelve a intentarlo.» con «Reintentar».
4. La app está instalada pero no da ninguna pestaña (apagada, o ninguna que esta persona pueda ver): «Aquí todavía no hay nada» — «Este módulo está instalado pero ahora mismo no tiene ninguna pantalla que abrir. Comprueba que está activo en Apps, o abre otro desde el menú.».
5. El hub no tiene esa app: «Esta app no está instalada» — «Este hub no tiene esta app. Búscala en el catálogo de Apps o abre otra desde el menú.» con «Ir al catálogo».
6. La dirección nombra una pestaña que la app no tiene: la misma página «no existe» que el resto del hub, con la dirección a la vista y la barra de pestañas debajo.
7. El plan del negocio no incluye esa app (nunca la nombró): no se abre; sale «Esta app no está disponible para este hub.» y la persona vuelve a Inicio.
Entra: el menú (HUB-F31), la lista de apps instaladas del hub y el permiso de apps del plan (HUB-F162).
Sale: nada.
Si falla: si la pregunta «¿está instalada?» falla, se ve el aviso de fallo (3), nunca uno inventado. Un hub que contesta 500 no se confunde con uno sin red (hub#1743). Una app de pago bloqueada no cae aquí: tiene su tarjeta (HUB_SHELL-F49).
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F31 (el menú quita las pestañas que piden un permiso que la persona no tiene)
Pendiente de enlazar: hub — HUB-F162 (qué apps puede usar el negocio)
QA: BD-03

### HUB_SHELL-F42 Moverse entre las pestañas de una app
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Vista de un módulo
Pasos:
1. Con la app abierta, la persona toca otra pestaña de la barra inferior.
2. La pestaña nueva se monta; la dirección cambia sin apilar historial.
3. Si la barra no cabe (un móvil con cinco pestañas), se desplaza de lado y la pestaña activa se trae a la vista al entrar por un enlace.
4. Si la persona cambia de idioma, los nombres de las pestañas y el título se vuelven a pedir en el idioma nuevo sin recargar lo que hay en pantalla (un tique a medias no se pierde).
Entra: los nombres de las pestañas, que traduce el hub (HUB-F31); el shell añade dos pestañas suyas: «Ajustes» (si la app declara ajustes) y «Plan» (si la app declara planes).
Sale: nada.
Si falla: si pedir los nombres en el idioma nuevo falla, se quedan los anteriores hasta el siguiente cambio (hub#2353).
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F31 (nombres de las pestañas traducidos por el hub)
QA: ninguno

### HUB_SHELL-F43 Ver los ajustes de una app en su pestaña «Ajustes»
Estado: parcial — si la lectura de los valores falla (sin permiso, un fallo pasajero), el formulario enseña los valores de fábrica como si fueran los del negocio, sin aviso; la pestaña sale a todo el mundo, tenga o no permiso de lectura; y una opción de una lista que la app no tradujo sale con su valor interno (`dine_in`, `ticket`)
Actor: empleado, responsable, administrador
Pantalla: Vista de un módulo › Ajustes
Pasos:
1. En una app que declara ajustes, la persona toca la pestaña «Ajustes» (engranaje), la última antes de «Plan».
2. Mientras carga: «Cargando ajustes…».
3. Ve un formulario con un campo por ajuste, en el orden que declara la app: interruptor para un sí/no, lista para una elección cerrada, número o texto (vacío, con «Escribe aquí…»). Cada campo con su nombre y, si la app lo trae, su explicación, traducidos por la app; arriba, el título del bloque si no repite el nombre de la app.
4. Cada valor es el guardado; si aún no hay nada guardado, el de fábrica que declara la app.
5. Quien no es administrador ve los campos sin poder tocarlos y la línea «Solo un administrador puede cambiar estos ajustes.», sin botón «Guardar».
6. Si la app trae su propia pantalla de ajustes, se monta esa en lugar del formulario genérico.
Entra: el bloque `settings` del `module.json` (esquema, consulta de lectura y orden de guardar), el esquema servido con la app, las traducciones `settings` de su `locales/<idioma>.json` y la consulta de lectura (HUB-F33).
Sale: nada.
Si falla: si el esquema no carga, «No se pudieron cargar los ajustes.». Si es la lectura de valores la que falla, no se dice nada y se ven los de fábrica (leído en el código, sin ejecutar). Sin traducción de un campo, su título del esquema (inglés) o el nombre de la columna «humanizado» (`Warning Time Minutes`).
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F33 (leer y guardar los ajustes de un módulo)
Pendiente de enlazar: cash_register — CASH_REGISTER-F01 (configurar cómo funciona la caja)
Pendiente de enlazar: sales — SALES-F34 (ajustar el TPV)
Pendiente de enlazar: kitchen — KITCHEN-F26 (ajustar la pantalla de cocina)
Pendiente de enlazar: inventory — INVENTORY-F19 (ajustar el inventario)
QA: ninguno

### HUB_SHELL-F44 Guardar los ajustes de una app
Estado: parcial — la pantalla solo deja guardar al administrador, mientras el servidor acepta a quien tenga el permiso de la orden de guardar (el responsable lo tiene en Ventas, Cocina, Inventario y lo hace por el asistente); la pantalla no comprueba nada antes de enviar (salvo el largo máximo de un texto); y como se manda el formulario entero, guardar tras una lectura fallida pisa lo guardado con los valores de fábrica
Actor: administrador
Pantalla: Vista de un módulo › Ajustes
Pasos:
1. El administrador cambia uno o varios campos.
2. Pulsa «Guardar»; el botón se desactiva mientras va.
3. Si el hub acepta: «Ajustes guardados.».
4. Si el hub rechaza campos concretos, debajo del formulario sale «No se pudieron guardar los ajustes.» con «Revisa los campos marcados y vuelve a guardar.», y cada campo rechazado lleva «Este valor no se admite.».
Entra: todos los valores del formulario, uno por campo del esquema, en la forma que declara el esquema (un sí/no guardado como 0/1 se manda como 0/1).
Sale: la orden de guardar de la app, que pasa por el embudo de siempre: permiso, esquema con sus valores por defecto y su comprobación (HUB-F03, HUB-F04, HUB-F33). La app avisa a quien escuche, si su orden lo hace.
Si falla: un rechazo sin campos (permiso, una regla de la app) se queda en pantalla con su frase: la del catálogo del hub si el código la tiene, o la que escribió la app; nunca un toast genérico solo (hub#1094). Siempre sale además el aviso flotante «No se pudieron guardar los ajustes.». Un rechazo de permiso llega como «permiso denegado: requiere `…`», con el nombre interno del permiso (leído en el código, sin ejecutar).
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F33 (la pantalla solo deja guardar al administrador; el servidor acepta a quien tenga el permiso)
Pendiente de enlazar: hub — HUB-F04 (comprobar el contenido de una orden contra su esquema y rellenar lo que falta)
Pendiente de enlazar: sales — SALES-F34 (ajustar el TPV)
Pendiente de enlazar: kitchen — KITCHEN-F26 (ajustar la pantalla de cocina)
Pendiente de enlazar: inventory — INVENTORY-F19 (ajustar el inventario)
Pendiente de enlazar: cash_register — CASH_REGISTER-F01 (configurar cómo funciona la caja)
QA: ninguno

### HUB_SHELL-F45 Probar un ajuste antes de guardarlo
Estado: parcial — el shell sabe pintar «Probar», pero ninguna de las 27 apps lo declara hoy en su esquema (tampoco Cocina), así que no aparece en ninguna pantalla
Actor: administrador, responsable, empleado
Pantalla: Vista de un módulo › Ajustes
Pasos:
1. Junto a un ajuste que solo se juzga oyéndolo o viéndolo (el volumen o el tono de un aviso) aparece «Probar», si la app lo declara.
2. La persona cambia el valor y pulsa «Probar», sin guardar.
3. La app hace la prueba (suena, parpadea) con el valor que hay en pantalla.
Entra: el valor del formulario sin guardar; la app declara la prueba en su esquema (`x-erplora-preview`) y la hace su propio componente.
Sale: nada guardado.
Si falla: «No se pudo hacer la prueba.». Si el código de la app no carga, el botón no aparece; el formulario sigue funcionando.
Implicados: ninguno
QA: ninguno

### HUB_SHELL-F46 Ver el plan de una app de pago en su pestaña «Plan»
Estado: parcial — si erplora.com no contesta, la pestaña no lo dice: pinta el plan gratuito como «Activo» (o «Sin plan» en una app sin plan gratuito); y la consulta va directa a erplora.com con la cuenta de la persona, así que con una sesión de PIN sin cuenta de erplora.com cae en ese mismo caso (sin confirmar)
Actor: empleado, responsable, administrador
Pantalla: Vista de un módulo › Plan
Pasos:
1. En una app que declara planes, la persona toca «Plan».
2. Arriba, «Tu plan» con «Comprobando tu suscripción…» y después el estado: «Activo», «En prueba», «Pago pendiente», «Cancelado», «Caducado» o «Sin plan», con su línea: «Se renueva el …», «Prueba hasta el …», «Se cancela el …», «Estás en {plan}, el plan con el que entra todo el mundo.», «Incluido en tu plan {plan}.» o «Tu suscripción ha caducado. Sigues en {plan}.».
3. Siempre: «Los planes de este módulo se gestionan desde tu cuenta de ERPlora, en erplora.com.».
4. Debajo, una tarjeta por plan de la app con su nombre traducido, su precio («Gratis», «/mes», «/año») y lo que incluye («Incluye …», «{n} días de prueba», «… por unidad extra»); la del plan actual va destacada con «Tu plan». Si el nivel lo da el plan del hub, las tarjetas no llevan precio.
5. Una app sin planes: «Este módulo no ofrece planes de pago.».
Entra: los planes del `billing` del `module.json` y sus traducciones; el estado de la suscripción de esa app para este hub, pedido a erplora.com con la cuenta de la persona y el hub (`/api/v1/hub/device/module-subscription/`).
Sale: nada.
Si falla: ver el estado. Al volver a la ventana (o recuperar el foco) se vuelve a preguntar. Un plan que erplora.com nombra y esta versión de la app no conoce no se marca en ninguna tarjeta.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F162 (comprobar el plan y qué apps puede usar el negocio)
Pendiente de enlazar: saas — estado de la suscripción de una app para un hub (`module-subscription`)
QA: ninguno

### HUB_SHELL-F47 Ver lo consumido este mes de lo que incluye el plan
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Vista de un módulo › Plan
Pasos:
1. En la pestaña «Plan» de una app que mide su consumo (hoy, WhatsApp), entre el estado y las tarjetas aparece «Este mes» con «{usado} de {tope} {métrica}» y una barra.
2. Desde el 80 %: «Estás cerca de lo que incluye tu plan.»; al llegar al tope: «Has consumido todo lo que incluye tu plan este mes.».
3. Sin tope (la app contesta cero o no hay cupo), solo «{usado} {métrica}», sin barra.
Entra: la consulta de consumo que declara la app (`billing.usage`), con el permiso de la propia app; el nombre de la métrica, traducido por la app.
Sale: nada.
Si falla: un fallo del hub: «No se ha podido leer tu consumo. Inténtalo dentro de un momento.». A quien no tiene permiso de leerlo no se le enseña la línea ni se le avisa de un fallo. El número lo escribe el hub una vez al día (HUB-F272): puede ir hasta un día por detrás.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F272 (reflejar en el hub el cupo y el consumo de WhatsApp del mes)
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F13 (ver el consumo del mes y llegar al tope)
QA: WA-03

### HUB_SHELL-F48 Ir a gestionar el plan de una app en erplora.com
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Vista de un módulo › Plan
Pasos:
1. En la pestaña «Plan», la persona pulsa «Gestionar plan» (o, si el nivel lo da el plan del hub y hay uno mayor, «Sube de plan para tener más»).
2. Se abre en el navegador la página de su cuenta en erplora.com para ese hub y esa app, ya con la sesión puesta.
3. Tras contratar, vuelve a la pantalla y pulsa «Ya lo he contratado — comprobar»: si ya tiene el plan, «Confirmado. Tu plan se ha actualizado.».
Entra: el hub y la app; un pase de un solo uso para entrar en erplora.com.
Sale: nada en el hub. El hub no vende: no hay botón de comprar ni de cancelar en la app.
Si falla: «No se pudo abrir la gestión del plan. Inténtalo de nuevo.». En la app de Google Play los dos botones no aparecen (la línea «se gestionan desde tu cuenta…» sí).
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F142 (puerta compartida a erplora.com: Mi plan, Actualizar plan)
QA: ninguno

### HUB_SHELL-F49 Ver una app de pago bloqueada
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Vista de un módulo
Pasos:
1. La suscripción de una app de pago ya no está activa para este hub.
2. Al abrirla, la persona ve la tarjeta «Suscripción necesaria» — «Este módulo está deshabilitado porque su suscripción ya no está activa para este hub. Tus datos locales están a salvo y vuelven en cuanto vuelva la suscripción — se gestiona desde tu cuenta de ERPlora, en erplora.com.», en lugar de la app.
3. La pestaña «Plan» sigue abierta.
4. Cuando se contrata (desde aquí o desde otro equipo), al volver a la ventana se vuelve a preguntar y la app se desbloquea sola.
Entra: la lista de apps bloqueadas del plan del hub (HUB-F162).
Sale: nada; los datos de la app no se tocan.
Si falla: el hub rechaza igualmente cada lectura y orden de la app (`module_entitlement_blocked`), aunque alguien la abra por otro camino.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F162 (una app que ya no está en el permiso deja de responder sin perder datos)
QA: ninguno

### HUB_SHELL-F50 Ver una pantalla bloqueada hasta que otra app cumpla su condición
Estado: parcial — si el código de la pantalla de desbloqueo (la apertura de caja) no carga, la vista se queda en blanco sin aviso; si la lectura de la condición falla, el bloqueo cede y el TPV se monta, y la orden la rechaza después el hub con una frase en inglés que nombra apps internas
Actor: empleado, responsable, administrador
Pantalla: Vista de un módulo
Pasos:
1. Caja tiene «Activar caja» guardado y no hay sesión de caja abierta; la cajera abre el TPV.
2. En lugar del TPV ve la pantalla de apertura de caja que aporta Caja, a pantalla completa en la misma dirección.
3. Abre la caja ahí mismo.
4. El TPV se monta solo, sin recargar.
5. Si la app que bloquea no trae pantalla propia, se ve la tarjeta «Abre la caja primero» — «Esta pantalla está bloqueada mientras la caja esté cerrada. Abre una sesión de caja para empezar a vender — la pantalla se recarga sola en cuanto se abre la caja.» con «Reintentar».
Entra: el bloque `protects` de las apps activas (la consulta de ajustes, el ajuste que lo arma, la ruta que protege y la consulta de la condición), leídas con la sesión de la persona; el aviso de reanudar (`cash_register.session_opened`).
Sale: nada. Esta es la mitad visible; la que manda es la del hub (HUB-F13), que rechaza las órdenes de la app protegida venga de donde venga.
Si falla: con la caja cerrada desde otro dispositivo mientras el TPV ya está abierto, el TPV sigue a la vista y la orden de cobro vuelve rechazada con la frase del hub (`protects_guard`, en inglés). La pestaña «Ajustes» y «Plan» de la app protegida nunca se bloquean.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F13 (bloquear las órdenes de un módulo mientras otro no cumpla su condición)
Pendiente de enlazar: cash_register — CASH_REGISTER-F04 (vender solo con la caja abierta)
Pendiente de enlazar: sales — SALES-F08 (cobrar sin la caja abierta)
QA: R-01, B-01, BD-04

### HUB_SHELL-F51 Aprobar con el PIN de un responsable
Estado: hecho
Actor: empleado, responsable
Pantalla: Aprobación de un responsable
Pasos:
1. La cajera intenta algo que su perfil no permite pero el de responsable sí (un descuento por encima del tope, anular un tique). En lugar de un error se abre «Hace falta una aprobación» con «Se aprueba: {acción}», en palabras de la app.
2. Lee «Pide a un encargado que introduzca su PIN para aprobarlo.» y «…o que pase su placa: no hace falta pulsar nada antes.».
3. En «¿Quién lo aprueba?» toca la tarjeta de una persona (todas las del hub, sin filtrar por perfil); si el hub no ha dado ninguna, escribe el nombre y pulsa «Continuar».
4. Esa persona teclea su PIN (con «Otra persona» para volver atrás), o pasa su placa en cualquier momento.
5. La acción se hace una vez y sale «Aprobado por {name}». La sesión de la cajera no se cierra.
Entra: el rechazo del hub que dice qué permiso falta (`requires_elevation`); el nombre y el PIN, o la placa; las personas del hub (`pin_users`); el nombre de la acción en el idioma de la app (`commands` de su `locales`).
Sale: el PIN lo comprueba el hub, que da un pase de un solo uso atado a esa acción exacta; el SDK repite la orden con él una sola vez (HUB-F05, HUB-F152). Solo las órdenes piden aprobación: una consulta sin permiso es un rechazo.
Si falla: el diálogo se queda abierto: «Esos datos no aprueban esto. Revisa el nombre y el PIN, y vuelve a intentarlo.» (el mismo para nombre desconocido, PIN erróneo o persona de baja); «Esa persona no puede aprobarlo…»; «Esto no se aprueba con un PIN…»; «Esto ya no necesita aprobación…»; tras cinco intentos, la espera en minutos; cualquier otra cosa, «No se pudo enviar la aprobación. Comprueba la conexión y vuelve a intentarlo.». «Cancelar» (o cerrar) devuelve a la app el rechazo original, y lo que enseñe es cosa de la app. Si la app no sabe nombrar la acción: «Se aprueba: una acción de {app}» o «Se aprueba: una acción que esta app no sabe nombrar». Un segundo pedido mientras hay uno abierto se rechaza, no se apila. Si la orden falla después de gastar el pase, hay que volver a pedir el PIN.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F05 (pedir la aprobación de un responsable cuando falta el permiso)
Pendiente de enlazar: hub — HUB-F152 (aprobar una acción con el PIN de un responsable)
Pendiente de enlazar: sales — SALES-F14 (descuento por encima del tope con el PIN del responsable)
QA: qa-hub-restaurant §6

### HUB_SHELL-F52 Leer en palabras de la persona por qué el hub rechazó algo
Estado: parcial — los rechazos más comunes del núcleo no tienen frase: falta de permiso («permiso denegado: requiere `sales.void_sale`»), el bloqueo de caja y la aprobación cancelada llegan con el texto del hub, en inglés o con nombres internos; y cinco apps (`customers`, `online_booking`, `tasks`, `tickets`, `whatsapp_inbox`) guardan sus frases en una forma que no se lee
Actor: sistema
Pantalla: Vista de un módulo
Pasos:
1. Una app pide algo al hub y el hub lo rechaza con un código estable (HUB-F14).
2. Antes de que la app lo enseñe, se elige la frase en este orden: la sesión se acabó; un fallo de la plataforma con frase propia (app que falta o está apagada, un dato que no se pudo leer, la acción demasiado grande o lenta, faltan datos fiscales, un fallo interno); la frase que la propia app escribió para ese código, en el idioma de la persona y si no en inglés; el texto que mandó el hub; y si no hay nada, una frase genérica.
3. Si el hub no contestó a una orden, la frase es «No sabemos si la operación se completó. Comprueba el resultado antes de reintentar.»; a una lectura, «No se han podido cargar los datos porque el hub no responde. Comprueba la conexión e inténtalo de nuevo.».
4. Las pantallas del propio shell (Ajustes de una app, Apps) traducen los códigos de la nube con su catálogo («ERPlora no ha podido atenderlo ahora mismo. Inténtalo en unos minutos.», «Esta app necesita un hub más nuevo…»); un código sin frase nunca se pinta: sale «No ha funcionado. Vuelve a intentarlo dentro de un minuto.».
Entra: el sobre de error del hub (`code`, `message`, y aparte el permiso, los campos, la app y lo que falta); el bloque `errors` de los `locales` de cada app.
Sale: la frase que pinta la app o el shell. Nada guardado.
Si falla: sin frase en español, la persona lee el inglés de la app o del hub; esos casos se ven en el estado.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F14 (contestar un fallo con un código estable y sin detalles internos)
Pendiente de enlazar: hub — HUB-F13 (el rechazo `protects_guard` no tiene frase propia)
QA: ninguno

### HUB_SHELL-F53 Ver señalado el campo que el hub rechazó
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Vista de un módulo › Ajustes
Pasos:
1. La persona guarda un formulario y el hub rechaza uno o varios campos.
2. En los ajustes de una app, cada campo rechazado queda marcado («Este valor no se admite.») y arriba «Revisa los campos marcados y vuelve a guardar.».
3. En los formularios del núcleo (personas, roles, perfil), el campo lleva su frase concreta («Escribe el nombre.», «El PIN es de {length} dígitos, solo números.», «Ese correo electrónico no es válido.») o, si no la hay para ese campo, la del motivo («Este campo es obligatorio.», «Este valor es demasiado largo.»).
4. En una app, la lista de campos rechazados le llega a su pantalla, que decide cómo marcarlos.
Entra: los campos que nombra el rechazo (`error.fields`, o `field` y `reason` en el núcleo), nunca sacados de la frase.
Sale: nada.
Si falla: un motivo sin frase en el catálogo deja la que mandó el hub.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F04 (comprobar el contenido de una orden contra su esquema)
QA: ninguno

### HUB_SHELL-F54 Ver dentro de una pantalla las piezas que aportan otras apps
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Vista de un módulo
Pasos:
1. Una app deja un hueco en su pantalla (el TPV, para elegir mesa o cliente; el cobro, para las líneas que paga otra app).
2. El shell busca las apps activas que aportan algo a ese hueco, las ordena por su prioridad y carga su código.
3. La pieza de cada app aparece en el hueco y lee sus datos ella misma, con su permiso.
Entra: el bloque `provides_slots` de cada app activa con derecho del plan.
Sale: nada.
Si falla: una app cuya pieza no carga se omite y las demás siguen; sin ninguna, el hueco queda vacío.
Implicados: pendiente
Pendiente de enlazar: sales — SALES-F01 (el TPV monta las piezas de mesa y cliente)
QA: ninguno

### HUB_SHELL-F55 Vender a pantalla completa
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Vista de un módulo
Pasos:
1. En una pestaña que lo declara (el TPV, la pantalla de cocina), la persona elige «Pantalla completa» en el menú de la app.
2. Desaparecen el menú lateral, la barra superior y la barra de pestañas; en el navegador, también su barra si lo deja.
3. «Salir de pantalla completa», salir del modo del navegador o irse de la app devuelven todo.
Entra: la lista `chrome` de la pestaña en el `module.json`; la app solo pide, el shell solo atiende lo declarado.
Sale: nada.
Si falla: si el navegador niega su pantalla completa (iPhone), el shell igualmente esconde su marco.
Implicados: pendiente
Pendiente de enlazar: kitchen — KITCHEN-F10 (el modo pantalla completa del shell en el tablero de cocina)
QA: ninguno

### HUB_SHELL-F56 Pintar una app con los componentes visuales del hub
Estado: parcial — la diferencia de versión entre los componentes del hub y los que trae la app solo se anota en la consola del navegador; nadie la ve ni la impide, y una app construida con otra versión puede pintarse mal
Actor: sistema
Pantalla: Vista de un módulo
Pasos:
1. El hub define al arrancar sus componentes visuales (tablas, tarjetas de plan, teclado de PIN…).
2. Una app trae su propia copia de esos componentes; donde el hub ya definió uno, gana el del hub y la copia de la app se descarta.
3. Si la app declara con qué versión se construyó y no es la del hub, se anota una vez por app en la consola.
Entra: el sello de versión de la app (`dist/outfitkit.json`) y el del hub.
Sale: una línea en la consola por app.
Si falla: nadie se entera salvo quien mire la consola.
Implicados: ninguno
QA: ninguno
