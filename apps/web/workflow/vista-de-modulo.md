# WORKFLOW — Hub · pantallas · La vista de un módulo

Prefijo: HUB_SHELL

> Detalle del índice `apps/web/WORKFLOW.md`. Es el marco donde se pintan las 27 apps: lo que aquí
> se escribe lo dan por hecho todas ellas. Código: `views/ModuleView.vue`, `lib/module-loader.ts`,
> `components/ModuleSettingsForm.vue`, `lib/module-settings.ts`, `components/ModulePlanPanel.vue`,
> `lib/module-quota.ts`, `lib/module-usage.ts`, `lib/protects.ts`, `components/ElevationDialog.vue`,
> `lib/elevation.ts`, `lib/runtime-error-sentence.ts`, `lib/module-failure-message.ts`,
> `lib/invalid-field.ts`, `lib/slot-fillers.ts`, `lib/outfitkit-skew.ts` (la pantalla completa, `lib/immersive.ts`, es HUB_SHELL-F18 del área de acceso) y la
> traducción de rechazos del SDK (`packages/module-sdk/src/index.ts`, `unwrap`).

## Referencia adoptada

- **Estados de carga de una pantalla**: esqueleto de página (Shopify Polaris SkeletonPage, Ionic
  `ion-skeleton-text`); «cargando / sin red / fallo / vacío / no instalada» son frases distintas
  (hub#770, hub#1169, hub#1743).
- **Aprobación del encargado sin cerrar la sesión de la cajera** (Square, Toast, Aloha): diálogo con
  la persona y su PIN o su placa, la acción se hace una vez y queda a dos nombres. Contrastado en
  `sales/WORKFLOW.md` (Toast — anulaciones) y `qa-hub-restaurant.md` §6.
- **Bloqueo de la venta con la caja cerrada** (Odoo POS, Square: abrir caja antes de vender) —
  contrastado en `cash_register` (CASH_REGISTER-F04).
- **El hub no vende** (Google Play / Microsoft Store, anti-steering, hub#479): la pestaña Plan
  enseña planes y lleva a la cuenta del cliente, no a un checkout.

## Antes de empezar

- La pestaña «Ajustes» de una app solo existe si su `module.json` declara el bloque `settings`
  (hoy: appointments, attendance, cash_register, inventory, kitchen, sales, services, staff, tables),
  y solo la ve quien tiene el permiso de su orden de guardar (hub#2588); la pestaña «Plan», si
  declara `billing`.
- El bloqueo por suscripción, el rebote de apps fuera del plan y el estado de la pestaña «Plan» solo
  se ven con una sesión iniciada con cuenta de erplora.com (regla común «Sesión de PIN frente a
  sesión con cuenta» del índice; HUB_SHELL-F41, F46, F49).

## Flujos

### HUB_SHELL-F40 Abrir una app y ver su primera pestaña
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Vista de un módulo
Pasos:
1. La persona abre una app desde el lanzador «Mis apps» de la barra superior, desde «Mis apps» de Inicio o con «Abrir» en Apps (las apps no están en el menú lateral).
2. Mientras baja el código de la app se ve un esqueleto de página (una barra de título y seis filas grises); quien usa lector de pantalla oye «Cargando módulo…».
3. La app aparece con su nombre traducido arriba y, si tiene más de una pestaña, la barra de pestañas abajo; se abre en la primera pestaña y la dirección pasa a nombrarla (`/m/<app>/<pestaña>`), de modo que «Atrás» sale de la app y no recorre pestañas.
4. Un enlace directo a una pestaña (`/m/inventory/products`) abre esa pestaña.
Entra: el menú de las apps activas, con sus nombres en el idioma de la persona y la versión instalada (HUB-F31); el `module.json` y el código de la app, pedidos una sola vez por sesión.
Sale: la pantalla de la app montada. Recibe un cliente del hub identificado como esa app (para sus permisos de host); no es una barrera: puede leer consultas de otras apps con el permiso de la persona, y cualquier componente puede pedir otra identidad (`forModule` es pública) o usar `globalThis.erplora`. Lo que protege es el permiso de cada consulta y orden en el hub. Nada guardado.
Si falla: ver HUB_SHELL-F41. Si la persona se va de la app, la pantalla escondida suelta la app (deja de oír avisos y la dirección) y al volver la monta de nuevo: así una caja escondida no se come el `?appointment_id=` de la caja visible (hub#1797); un ir y volver rápido no deja la pantalla en el esqueleto para siempre (hub#2241). Una app cuyo `module.json` no declara bloque `ui` no tiene pantalla que montar: no sale en el lanzador (las demás sí) y su dirección directa dice «Aquí todavía no hay nada» (hub#2635).
Implicados: HUB-F31
QA: BD-03

### HUB_SHELL-F41 Entender por qué una app no se abre
Estado: parcial — una app cuyas pestañas exigen todas un permiso que la persona no tiene se pinta como «Aquí todavía no hay nada» y la manda a Apps; un enlace a una pestaña concreta sin permiso dice «Esta página no existe… enlace antiguo»; el rebote de una app fuera del plan solo ocurre con una sesión que trae cuenta de erplora.com (con PIN la app se abre y cada pantalla falla con 402 y una frase interna); y la vista no tiene estado propio «necesita un hub más nuevo» (eso solo se dice al instalar o actualizar)
Actor: empleado, responsable, administrador
Pantalla: Vista de un módulo
Pasos:
1. La persona abre una app y, en lugar de su pantalla, ve uno de estos avisos, cada uno con su motivo:
2. Sin red: «Sin conexión a Internet» — «Esta pantalla necesita la conexión para cargarse. Revisa la red — vuelve sola en cuanto haya Internet otra vez.» con «Reintentar»; al volver la red la pantalla se monta sola.
3. El hub contestó con un fallo: «No se pudo cargar el módulo.» — «Comprueba que el módulo siga instalado y activo, y vuelve a intentarlo.» con «Reintentar».
4. La app está instalada pero no da ninguna pestaña (apagada, ninguna que esta persona pueda ver, o su `module.json` no declara bloque `ui` y no hay pantalla que montar, HUB_SHELL-F40): «Aquí todavía no hay nada» — «Este módulo está instalado pero ahora mismo no tiene ninguna pantalla que abrir. Comprueba que está activo en Apps, o abre otro desde el menú.».
5. El hub no tiene esa app: «Esta app no está instalada» — «Este hub no tiene esta app. Búscala en el catálogo de Apps o abre otra desde el menú.» con «Ir al catálogo». Con el plan resuelto solo llega aquí una app del plan que no está instalada; con sesión de PIN, cualquier identificador que el hub no tenga.
6. La dirección nombra una pestaña que la app no tiene, o una que el menú le quitó a esta persona por permiso (un empleado en `/m/sales/departments`, o en `/m/attendance/settings` sin el permiso de guardar esos ajustes, hub#2588): la misma página «Esta página no existe» que el resto del hub («…Puede ser un enlace antiguo…»), con la dirección a la vista y la barra de pestañas debajo.
7. Con una sesión que trae cuenta de erplora.com (correo o Google) y el plan del hub ya leído, una app que el plan no nombra (o un identificador que el hub nunca tuvo) no se abre: sale «Esta app no está disponible para este hub.» y la persona vuelve a Inicio. Con sesión de PIN el shell no conoce el plan: la app se abre y cada pantalla falla con el rechazo del hub «el módulo `x` no está incluido en el entitlement vigente del hub».
Entra: el menú (HUB-F31), la lista de apps instaladas del hub y el permiso de apps del plan (HUB-F162).
Sale: nada.
Si falla: si la pregunta «¿está instalada?» falla, se ve el aviso de fallo (3), nunca uno inventado. Un hub que contesta 500 no se confunde con uno sin red (hub#1743). Una app de pago bloqueada no cae aquí: tiene su tarjeta (HUB_SHELL-F49).
Implicados: HUB-F31, HUB-F162
QA: BD-03

### HUB_SHELL-F42 Moverse entre las pestañas de una app
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Vista de un módulo
Pasos:
1. Con la app abierta, la persona toca otra pestaña de la barra inferior.
2. La pestaña nueva se monta; la dirección cambia sin apilar historial.
3. Si la barra no cabe (un móvil con cinco pestañas), se desplaza de lado y la pestaña activa se trae a la vista al entrar por un enlace: entera y fuera del difuminado que avisa de que hay más pestañas por ese lado; si es la primera o la última, la barra llega hasta su principio o su final, donde ya no hay difuminado (hub#2603). En tableta y escritorio las pestañas caben y la barra no se mueve.
4. Si la persona cambia de idioma, los nombres de las pestañas y el título se vuelven a pedir en el idioma nuevo sin recargar lo que hay en pantalla (un tique a medias no se pierde).
Entra: los nombres de las pestañas, que traduce el hub (HUB-F31); el shell añade dos pestañas suyas: «Ajustes» (si la app declara ajustes y la persona tiene el permiso de su orden de guardar, hub#2588) y «Plan» (si la app declara planes).
Sale: nada.
Si falla: si pedir los nombres en el idioma nuevo falla, se quedan los anteriores hasta el siguiente cambio (hub#2353).
Implicados: HUB-F31
QA: ninguno

### HUB_SHELL-F43 Ver los ajustes de una app en su pestaña «Ajustes»
Estado: parcial — salvo Cocina (que publica el nombre de cada opción en `en` y `es`, kitchen#159), ninguna app publica la traducción de sus opciones, así que sus listas salen con el valor interno (`ticket`)
Actor: empleado, responsable, administrador
Pantalla: Vista de un módulo › Ajustes
Pasos:
1. En una app que declara ajustes, la persona toca la pestaña «Ajustes» (engranaje), la última antes de «Plan». La pestaña solo sale a quien tiene el permiso que la app pide a su orden de guardar (`settings.set` → su `commands[…].permission`; el dueño y el administrador lo tienen siempre, por su rol, aunque hayan entrado antes de instalar la app); a los demás no les sale, como cualquier pestaña de la app que su permiso no abre, y si teclean la dirección (`/m/<app>/settings`) ven «Esta página no existe» (HUB_SHELL-F41 paso 6, hub#2588). Si la orden no pide permiso, la ve todo el que abre la app.
2. Mientras carga: «Cargando ajustes…».
3. Ve un formulario con un campo por ajuste, en el orden del esquema de la app. El control sale del tipo: `boolean`, o `integer` con `enum:[0,1]` → interruptor (se guarda como 0/1); cualquier otro `enum` → lista; `integer` o `number` → número; todo lo demás (un `string`, pero también un `array`, un `object` o un tipo anulable como `["integer","null"]`) → caja de texto, vacía con «Escribe aquí…».
4. Los textos los pone la app en su `locales/<idioma>.json`: el nombre en `settings.fields.<clave>.label` (si no, el `title` del esquema, y si no, la clave «humanizada»), la explicación en `…description`, el título del bloque en `settings.title` (se omite si repite el nombre de la app) y cada opción de una lista en `settings.fields.<clave>.options.<valor>` (si no, el valor crudo).
5. Cada valor es el guardado; si la app aún no tiene nada guardado (la lectura contesta sin fila), el `default` del esquema; si tampoco, apagado o vacío. Si la lectura FALLA, no se pinta el formulario (hub#2511): ni valores de fábrica ni «Guardar» (ver «Si falla»).
6. Quien llega aquí sin ser administrador (un responsable con el permiso de guardar) ve los campos sin poder tocarlos y la línea «Solo un administrador puede cambiar estos ajustes.», sin botón «Guardar» (HUB_SHELL-F44).
7. Si la app trae su propia pantalla de ajustes (`settings.component`), se monta esa en lugar del formulario genérico, sin el candado de administrador: hoy, Control horario (`erp-attendance-settings`). La puerta de la pestaña es la misma del paso 1.
Entra: el bloque `settings` del `module.json` (esquema, consulta de lectura y orden de guardar), el esquema servido con la app, las traducciones `settings` de su `locales/<idioma>.json` y la consulta de lectura (HUB-F33).
Sale: nada.
Si falla: si el esquema o la lectura de valores no cargan (red, hub reiniciándose, 5xx), en lugar del formulario sale «No se pudieron cargar los ajustes.» con «Tus ajustes guardados siguen igual. Comprueba la conexión y vuelve a intentarlo.» y el botón «Reintentar», que vuelve a leer; no hay «Guardar», así que nada se puede guardar encima de lo que no se leyó (hub#2511, mismo patrón que los eventos caídos de Sistema, HUB_SHELL-F145). Si la lectura se rechaza por permiso (`permission_denied` o `requires_elevation`), sale «No puedes ver estos ajustes» con «Pide a un administrador que los revise o los cambie si hace falta.», sin «Reintentar» (reintentar no lo arregla). Como la pestaña solo sale a quien puede guardar, este rechazo solo lo ve quien tiene el permiso de guardar y no el de leer (ninguna app de fábrica lo reparte así). Sin traducción de un campo, su título del esquema (inglés) o el nombre de la columna «humanizado» (`Warning Time Minutes`). Un campo de tipo objeto o lista se pinta como texto y, si se edita, se guarda como cadena y el hub lo rechaza.
Implicados: CASH_REGISTER-F01, HUB-F33, INVENTORY-F19, KITCHEN-F26, SALES-F34
QA: ninguno

### HUB_SHELL-F44 Guardar los ajustes de una app
Estado: parcial — la pantalla solo deja guardar al dueño o al administrador, mientras el servidor acepta a quien tenga el permiso de la orden de guardar (el responsable lo tiene en Ventas, Inventario, Cocina y Personal y lo hace por el asistente); y la pantalla no comprueba nada antes de enviar salvo el largo máximo de un texto (ni mínimos, ni máximos, ni patrones, ni obligatorios)
Actor: administrador
Pantalla: Vista de un módulo › Ajustes
Pasos:
1. El administrador cambia uno o varios campos.
2. Pulsa «Guardar»; el botón se desactiva mientras va.
3. Si el hub acepta: «Ajustes guardados.».
4. Si el hub rechaza campos concretos, debajo del formulario sale «No se pudieron guardar los ajustes.» con «Revisa los campos marcados y vuelve a guardar.», y cada campo rechazado lleva «Este valor no se admite.».
Entra: todos los valores del formulario, uno por campo del esquema, en la forma que declara el esquema (un sí/no guardado como 0/1 se manda como 0/1; un número vaciado, como `null`). Solo se puede guardar sobre valores LEÍDOS (HUB_SHELL-F43 paso 5, hub#2511): lo que la persona no tocó viaja con el valor guardado, nunca con el de fábrica. Se manda el formulario entero y no solo lo cambiado porque la orden de guardar de una app es un «sustituir todo» con todos los campos obligatorios (en Caja, `required` de los ocho y un `ON CONFLICT … SET` de todas las columnas): un envío parcial lo rechazaría el esquema o, rellenado con los de fábrica (HUB-F04), pisaría lo guardado.
Sale: la orden de guardar de la app, que pasa por el embudo de siempre: permiso, esquema con sus valores por defecto y su comprobación (HUB-F03, HUB-F04, HUB-F33). La app avisa a quien escuche, si su orden lo hace.
Si falla: un rechazo sin campos (permiso, una regla de la app) se queda en pantalla con su frase: la del catálogo del shell si el código la tiene; si no, el texto que dejó el SDK (la frase de plataforma, la de la app, o el del hub tal cual); solo si viene vacío, «No se pudieron guardar los ajustes.» (hub#1094). Siempre sale además el aviso flotante «No se pudieron guardar los ajustes.». Un rechazo de permiso llega como «permiso denegado: requiere `…`», con el nombre interno del permiso (leído en el código, sin ejecutar).
Implicados: CASH_REGISTER-F01, HUB-F04, HUB-F33, INVENTORY-F19, KITCHEN-F26, SALES-F34
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
Estado: parcial — una suscripción cancelada que sigue dentro del periodo pagado sale como «Activo» con «Se renueva el …», porque erplora.com la contesta `active`; para una app sin listar o retirada, «se gestionan desde tu cuenta de ERPlora» manda a una página que contesta 404; si erplora.com no contesta, la pestaña no lo dice: pinta el plan gratuito como «Activo» (o «Sin plan» en una app sin plan gratuito); y la consulta va directa a erplora.com con la cuenta de la persona, así que con una sesión de PIN (que no lleva cuenta de erplora.com) erplora.com la rechaza y cae siempre en ese mismo caso
Actor: empleado, responsable, administrador
Pantalla: Vista de un módulo › Plan
Pasos:
1. En una app que declara planes, la persona toca «Plan».
2. Arriba, «Tu plan» con «Comprobando tu suscripción…» y después el estado: «Activo», «En prueba», «Pago pendiente», «Cancelado», «Caducado» o «Sin plan», con su línea: «Se renueva el …», «Prueba hasta el …», «Se cancela el …» (que no se ve nunca con una fecha por venir: erplora.com contesta `active` a una suscripción cancelada mientras dura el periodo pagado, y `expired` cuando acaba), «Estás en {plan}, el plan con el que entra todo el mundo.», «Incluido en tu plan {plan}.» o «Tu suscripción ha caducado. Sigues en {plan}.».
3. Siempre: «Los planes de este módulo se gestionan desde tu cuenta de ERPlora, en erplora.com.». Para una app sin listar o retirada es falso: la página de la cuenta y la ficha de erplora.com contestan 404 a una app fuera del catálogo; solo queda cancelarla por la API del hub mientras siga publicada.
4. Debajo, una tarjeta por plan de la app con su nombre traducido, su precio («Gratis», «/mes», «/año») y lo que incluye («Incluye …», «{n} días de prueba», «… por unidad extra»); la del plan actual va destacada con «Tu plan». Si el nivel lo da el plan del hub, las tarjetas no llevan precio.
5. Una app sin planes: «Este módulo no ofrece planes de pago.».
Entra: los planes del `billing` del `module.json` y sus traducciones; el estado de la suscripción de esa app para este hub, pedido a erplora.com con la cuenta de la persona y el hub (`/api/v1/hub/device/module-subscription/`).
Sale: nada.
Si falla: ver el estado. Al volver a la ventana (o recuperar el foco) se vuelve a preguntar. Un plan que erplora.com nombra y esta versión de la app no conoce no se marca en ninguna tarjeta.
Implicados: HUB-F162, HUB-F272, WHATSAPP_INBOX-F13, SAAS-F01, SAAS_DASHBOARD-F62, SAAS_DASHBOARD-F112, SAAS_DASHBOARD-F116
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
Implicados: HUB-F272, WHATSAPP_INBOX-F13
QA: WA-03

### HUB_SHELL-F48 Ir a gestionar el plan de una app en erplora.com
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Vista de un módulo › Plan
Pasos:
1. En la pestaña «Plan», la persona pulsa «Gestionar plan» (o, si el nivel lo da el plan del hub y hay uno mayor, «Sube de plan para tener más»).
2. Se abre en el navegador la página de su cuenta en erplora.com para ese hub y esa app, ya con la sesión puesta.
3. Tras contratar, vuelve a la pantalla y pulsa «Ya lo he contratado — comprobar»: si erplora.com dice que la suscripción está activa, en prueba, cancelada pero vigente o con pago pendiente, sale «Confirmado. Tu plan se ha actualizado.» (también en los dos últimos casos); si no, o si la consulta falla, no se dice nada y solo cambia el bloque de estado.
Entra: el hub y la app; un pase de un solo uso para entrar en erplora.com.
Sale: nada en el hub. El hub no vende: no hay botón de comprar ni de cancelar en la app.
Si falla: «No se pudo abrir la gestión del plan. Inténtalo de nuevo.». En la app de Google Play los dos botones no aparecen (la línea «se gestionan desde tu cuenta…» sí).
Implicados: HUB-F142, HUB_APP-F29, SAAS_AUTH-F21, SAAS_DASHBOARD-F108
QA: ninguno

### HUB_SHELL-F49 Ver una app de pago bloqueada
Estado: parcial — solo con una cuenta de erplora.com en la sesión: con sesión de PIN el shell no sabe que la app está bloqueada, la abre y cada pantalla falla con «el módulo `x` no está incluido en el entitlement vigente del hub»; y al contratar la tarjeta desaparece pero la app no se vuelve a montar (pantalla en blanco hasta salir y volver)
Actor: empleado, responsable, administrador
Pantalla: Vista de un módulo
Pasos:
1. La suscripción de una app de pago ya no está activa para este hub.
2. Con una sesión iniciada con cuenta de erplora.com, al abrirla la persona ve la tarjeta «Suscripción necesaria» — «Este módulo está deshabilitado porque su suscripción ya no está activa para este hub. Tus datos locales están a salvo y vuelven en cuanto vuelva la suscripción — se gestiona desde tu cuenta de ERPlora, en erplora.com.», en lugar de la app.
3. La pestaña «Plan» sigue abierta. En la pestaña «Ajustes» se ven a la vez la tarjeta y el formulario.
4. Cuando se contrata (desde aquí o desde otro equipo), al volver a la ventana se vuelve a preguntar y la tarjeta desaparece, pero la app no se monta: la vista queda en blanco hasta salir de la app y volver a entrar.
Entra: la lista de apps bloqueadas del plan del hub (HUB-F162), que el shell solo pide si la sesión trae cuenta de erplora.com; sin ella (PIN, o tras un relevo con PIN) el shell no bloquea nada.
Sale: nada; los datos de la app no se tocan.
Si falla: el hub rechaza igualmente cada lectura y orden de la app (402), aunque la pantalla no lo sepa; con sesión de PIN eso es lo que ve la persona, con la frase interna del hub «el módulo `x` no está incluido en el entitlement vigente del hub», sin traducir.
Implicados: HUB-F162, SAAS_DASHBOARD-F116
QA: ninguno

### HUB_SHELL-F50 Ver una pantalla bloqueada hasta que otra app cumpla su condición
Estado: parcial — la vista se queda en blanco, sin aviso ni «Reintentar», si el código de la pantalla de apertura de caja no carga o si el menú de esa persona no trae ninguna pestaña de Caja y su código no se cargó antes en la sesión (el TPV solo vuelve cuando alguien abre la caja por otro camino: la app Caja, el asistente u otro dispositivo); si la lectura de la condición falla, el bloqueo cede y el TPV se monta, y la orden la rechaza después el hub con una frase en inglés que nombra apps internas
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
Implicados: CASH_REGISTER-F04, HUB-F13, SALES-F08
QA: R-01, B-01, BD-04

### HUB_SHELL-F51 Aprobar con el PIN de un responsable
Estado: hecho
Actor: empleado, responsable
Pantalla: Aprobación de un responsable
Pasos:
1. La cajera intenta algo que su perfil no permite pero el de responsable sí (un descuento por encima del tope, anular un tique). En lugar de un error se abre «Hace falta una aprobación» con «Se aprueba: {acción}», en palabras de la app y, si la app lo declara (`approval_label`), con la cifra que se aprueba (un descuento del 90 %).
2. Lee «Pide a un encargado que introduzca su PIN para aprobarlo.» y «…o que pase su placa: no hace falta pulsar nada antes.».
3. En «¿Quién lo aprueba?» toca la tarjeta de una persona (todas las del hub, sin filtrar por perfil); si el hub no ha dado ninguna, escribe el nombre y pulsa «Continuar».
4. Esa persona teclea su PIN (con «Otra persona» para volver atrás), o pasa su placa en cualquier momento.
5. La acción se hace una vez y sale «Aprobado por {name}». La sesión de la cajera no se cierra.
Entra: el rechazo del hub que dice qué permiso falta (`requires_elevation`); el nombre y el PIN, o la placa; las personas del hub (`pin_users`); el nombre de la acción en el idioma de la app (`commands` de su `locales`).
Sale: el PIN lo comprueba el hub, que da un pase de un solo uso atado a esa acción exacta; el SDK repite la orden con él una sola vez (HUB-F05, HUB-F152). Solo las órdenes piden aprobación: una consulta sin permiso es un rechazo.
Si falla: el diálogo se queda abierto: «Esos datos no aprueban esto. Revisa el nombre y el PIN, y vuelve a intentarlo.» (el mismo para nombre desconocido, PIN erróneo o persona de baja); «Esa persona no puede aprobarlo…»; «Esto no se aprueba con un PIN…»; «Esto ya no necesita aprobación…»; tras cinco intentos, la espera en minutos; cualquier otra cosa, «No se pudo enviar la aprobación. Comprueba la conexión y vuelve a intentarlo.». «Cancelar» (o cerrar) devuelve a la app el rechazo original, y lo que enseñe es cosa de la app. Si la app no sabe nombrar la acción: «Se aprueba: una acción de {app}» o «Se aprueba: una acción que esta app no sabe nombrar». La misma orden repetida (un doble toque) se une al diálogo abierto y recibe su mismo resultado; una acción distinta mientras hay uno abierto se rechaza, no se apila. Si tras aprobar el hub vuelve a pedir aprobación (pase caducado, otra copia del hub), no se abre otro diálogo: llega a la app como rechazo, con el texto en inglés «requires elevation: `…` needs approval from a manager», y hay que repetir la acción. El catálogo con los nombres de las acciones se carga una vez al entrar: una app instalada después o un cambio de idioma no se reflejan hasta recargar.
Implicados: HUB-F05, HUB-F152, SALES-F14
QA: qa-hub-restaurant §6

### HUB_SHELL-F52 Leer en palabras de la persona por qué el hub rechazó algo
Estado: parcial — los rechazos más comunes del núcleo no tienen frase: falta de permiso («permiso denegado: requiere `sales.void_sale`»), el bloqueo de caja, la aprobación cancelada y la app fuera del plan llegan con el texto del hub, en inglés o con nombres internos; y la frase propia de una app solo se conoce si su pantalla ya se pintó en esta página (un rechazo de Cocina en su pestaña «Ajustes» antes de abrir la cocina sale con el texto del hub)
Actor: sistema
Pantalla: Vista de un módulo
Pasos:
1. Una app pide algo al hub y el hub lo rechaza con un código estable (HUB-F14).
2. Antes de que la app lo enseñe, se elige la frase en este orden: la sesión se acabó; un fallo de la plataforma con frase propia (app que falta o está apagada, un dato que no se pudo leer, la acción demasiado grande o lenta, faltan datos fiscales, un fallo interno); la frase que la propia app escribió para ese código en el bloque `errors` de sus `locales`, en el idioma de la persona y si no en inglés; el texto que mandó el hub; y si no hay nada, «No se pudo completar la operación. Inténtalo de nuevo y avisa a un administrador si sigue pasando.».
3. Si el hub no contestó a una orden, la frase es «No sabemos si la operación se completó. Comprueba el resultado antes de reintentar.»; a una lectura, «No se han podido cargar los datos porque el hub no responde. Comprueba la conexión e inténtalo de nuevo.».
4. Las pantallas del propio shell traducen los códigos de la nube con su catálogo («ERPlora no ha podido atenderlo ahora mismo. Inténtalo en unos minutos.», «Esta app necesita un hub más nuevo…»). En Apps y las demás que usan esa traducción, un código sin frase nunca se pinta: sale «No ha funcionado. Vuelve a intentarlo dentro de un minuto.». La pestaña «Ajustes» de una app, en cambio, pinta el texto que dejó el SDK tal cual (p. ej. «permiso denegado: requiere `sales.manage_settings`»).
Entra: el sobre de error del hub (`code`, `message`, y aparte el permiso, los campos, la app y lo que falta); el bloque `errors` de los `locales` de cada app.
Sale: la frase que pinta la app o el shell. Nada guardado.
Si falla: sin frase en español, la persona lee el inglés de la app o del hub; esos casos se ven en el estado. Quién lee el sobre de error y hay que revisar si cambia: ver «Qué revisar si cambia el formato de los errores» en el índice.
Implicados: HUB-F13, HUB-F14
QA: ninguno

### HUB_SHELL-F53 Ver señalado el campo que el hub rechazó
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Vista de un módulo › Ajustes
Pasos:
1. La persona guarda un formulario y el hub rechaza uno o varios campos.
2. En los ajustes de una app, cada campo rechazado queda marcado («Este valor no se admite.»), como mucho cinco (el hub informa de cinco violaciones como mucho), y debajo del formulario «Revisa los campos marcados y vuelve a guardar.».
3. En los formularios del núcleo (personas, roles, perfil), el campo lleva su frase concreta («Escribe el nombre.», «El PIN es de {length} dígitos, solo números.», «Ese correo electrónico no es válido.») o, si no la hay para ese campo, la del motivo («Este campo es obligatorio.», «Este valor es demasiado largo.»).
4. En una app, la lista de campos rechazados le llega a su pantalla, que decide cómo marcarlos.
Entra: los campos que nombra el rechazo (`error.fields`, o `field` y `reason` en el núcleo), nunca sacados de la frase.
Sale: nada.
Si falla: un motivo sin frase en el catálogo deja la que mandó el hub.
Implicados: HUB-F04, HUB-F14
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
Implicados: SALES-F01
QA: ninguno

### HUB_SHELL-F55 [retirado] Vender a pantalla completa
Implicados: ninguno
Sustituido por HUB_SHELL-F18 (acceso y navegación): era el mismo gesto, la pantalla completa de `lib/immersive.ts`.

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

## Cobertura contra la referencia

| Elemento | Estado | Flujo |
|---|---|---|
| Cargando / sin red / fallo / vacío / no instalada / pestaña inexistente | hecho | HUB_SHELL-F40, HUB_SHELL-F41 |
| Estado «sin permiso» propio en la vista de una app | no hecho (se dice «Aquí todavía no hay nada») | HUB_SHELL-F41 |
| Estado «necesita un hub más nuevo» en la vista | no hecho (solo al instalar/actualizar en Apps) | HUB_SHELL-F41 |
| Pestañas y nombres traducidos, sin recargar al cambiar de idioma | hecho | HUB_SHELL-F42 |
| Ajustes declarativos: ver | parcial (lectura fallida → «No se pudieron cargar» con «Reintentar», hub#2511; la pestaña solo sale a quien puede guardar, hub#2588; pero las listas salen sin traducir, salvo en Cocina) | HUB_SHELL-F43 |
| Ajustes declarativos: guardar con el mismo permiso que el servidor | parcial (pantalla: solo administrador) | HUB_SHELL-F44 |
| Ajustes: validación antes de enviar (mínimos, obligatorios) | no hecho (solo el servidor) | HUB_SHELL-F44 |
| Probar un ajuste sin guardar | parcial (ninguna app lo declara) | HUB_SHELL-F45 |
| Plan de la app: estado, planes, «tu plan» | parcial (un fallo de erplora.com no se dice) | HUB_SHELL-F46 |
| Consumo del mes y aviso de tope | hecho | HUB_SHELL-F47 |
| Gestionar el plan fuera de la app (sin vender dentro) | hecho | HUB_SHELL-F48 |
| App bloqueada por suscripción, sin perder datos | parcial (solo con cuenta de erplora.com; no se remonta al contratar) | HUB_SHELL-F49 |
| Vender solo con la caja abierta (bloqueo en pantalla) | parcial | HUB_SHELL-F50 |
| Aprobación del encargado con PIN o placa | hecho | HUB_SHELL-F51 |
| Rechazos en el idioma de la persona | parcial (permiso, caja, aprobación cancelada, app fuera del plan; frase de la app solo tras pintarse) | HUB_SHELL-F52 |
| Campo rechazado señalado | hecho | HUB_SHELL-F53 |
| Piezas de otras apps dentro de una pantalla | hecho | HUB_SHELL-F54 |
| TPV a pantalla completa | hecho | HUB_SHELL-F18 (área de acceso; F55 retirado) |

## Datos: de quién es cada dato

Ninguno de estos flujos tiene tabla propia: todo lo que pintan se lee del hub o de erplora.com.

| Dato | Dueño | Cómo lo lee el shell |
|---|---|---|
| Menú, nombres traducidos, versión instalada | hub (HUB-F31) | `GET /api/navigation`, `GET /api/modules` |
| Bloques `settings`, `billing`, `protects`, `bell`, `provides_slots`, `chrome` | cada app (`module.json`) | el fichero servido, una vez por sesión |
| Valores de ajustes | cada app (su tabla `<app>_settings`) | la consulta y la orden que declara la app |
| Estado de la suscripción de una app | erplora.com | `/api/v1/hub/device/module-subscription/` con la cuenta de la persona |
| Apps permitidas y bloqueadas | erplora.com vía el hub (HUB-F162) | el plan del hub |
| Personas para aprobar | hub (`pin_users` del contexto) | `GET /api/hub/context` |

Dato personal que pasa por esta área (no se guarda en el shell): los nombres de todas las personas
del hub en el diálogo de aprobación, visibles a quien lo abre.

## Reglas que no se rompen

- **La aprobación se pide solo para órdenes, una a la vez, y se gasta una vez** (SDK `command` /
  `elevate`; `elevation.ts` `askForApproval`).
- **La pantalla no es la autoridad** (regla común del índice): el bloqueo de caja, el permiso de
  guardar ajustes y el bloqueo por suscripción los vuelve a aplicar el hub en cada orden. Con sesión
  de PIN la pantalla ni siquiera conoce el bloqueo por suscripción: solo lo aplica el hub.
- **La pantalla de una app recibe un cliente identificado como esa app** (`client.forModule(moduleId)`;
  la de bloqueo, como la app que bloquea), para sus permisos de host. **No es una barrera**: lee
  consultas de otras apps con el permiso de la persona, `forModule` es pública y `globalThis.erplora`
  no lleva identidad. Lo que protege es el permiso de cada consulta y orden en el hub.

## Lo que NO hace, a propósito

- No vende ni cancela suscripciones dentro del hub (regla común del índice, hub#479).
- No filtra por perfil la lista de personas del diálogo de aprobación (decide el hub; filtrarla
  publicaría quién es responsable).

## Dudas abiertas

- ¿La pestaña «Ajustes» debe dejar guardar a quien tenga el permiso de la orden (responsable), como
  el servidor, o el servidor debe exigir administrador? Afecta a SALES-F34, KITCHEN-F26,
  INVENTORY-F19, CASH_REGISTER-F01.

## Fuentes contrastadas

- `architecture/hub/module-system.md` §3quater pone el título de ajustes como cabecera del
  formulario: el shell lo omite si repite el nombre de la app.
- El comentario del SDK (`packages/module-sdk/src/index.ts:1212-1214`) dice que cinco apps
  (`customers`, `online_booking`, `tasks`, `tickets`, `whatsapp_inbox`) guardan sus frases de error
  en forma anidada: en `origin/main` las cinco ya tienen `errors` plano.
- El comentario de `ModuleView.vue` (guard con `component`) dice que «sin bundle, el fallback
  genérico se queda»; el fallback solo se pinta si el bloqueo NO declara componente, así que sin
  bundle la vista queda en blanco.
