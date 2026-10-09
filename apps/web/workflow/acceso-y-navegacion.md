# WORKFLOW — Hub · pantallas · Acceso, navegación y perfil

Prefijo: HUB_SHELL

> Detalle del área «Acceso, navegación y perfil» (oleada 3). Lo que la persona ve y hace para
> entrar, moverse por el hub y cuidar su perfil. Lo que decide el servidor (cuánto dura una sesión,
> cómo frena a quien prueba PIN, qué dispositivo es de confianza) está en `HUB`
> (`workflow/acceso.md`, HUB-F130…F144) y aquí solo se enlaza. Las pantallas que se citan en
> `Pantalla:` son las de `## Pantallas` del índice `apps/web/WORKFLOW.md`.

## Referencia adoptada

Contrastada en `.claude/agents/qa-hub-restaurant.md` §2, en las decisiones de
`architecture/hub/auth.md` y en los comentarios de las vistas que citan su referencia:

- **Entrar con PIN en un dispositivo compartido, con rejilla de caras, y relevo de turno sin cerrar
  la venta**: Square (Team passcodes) y Toast (employee passcodes, «switch user» como capa encima de
  la app). PIN de longitud fija por negocio, 4 o 6, que entra al último dígito: Clover (hub#974).
- **Placa (RFID/NFC) como la misma identidad que el PIN, nunca sustituta**: Toast, Aloha/NCR,
  Square, Lightspeed (ADR-0347).
- **Arranque que no encuentra el servidor: un aviso y un solo gesto, reintentar**: Square, Toast,
  Lightspeed (hub#2143).
- **Una franja persistente mientras no hay conexión, que se va sola**: Square, Toast, Shopify POS
  ([Square — modo sin conexión](https://squareup.com/help/es/es/article/7777-process-card-payments-with-offline-mode)).
- **Dirección inexistente: una página que lo dice y una salida**: Shopify admin, Square Dashboard,
  Stripe, Odoo, Business Central (hub#1723).
- **Pantalla de venta sin el marco de la aplicación**: Odoo POS, Square, Lightspeed (pantalla
  completa).
- **Instalar como aplicación desde el navegador, sin que el producto lo pida**: hub#685, hub#1715.

## Antes de empezar

Lo común (hub dado de alta, primera entrada con una cuenta de erplora.com) está en el índice. Lo
propio de esta área:

- En una caja compartida: márcala como compartida (HUB_SHELL-F11), decide en **Ajustes › General**,
  tarjeta «Pinpad», si se pregunta quién vende y cada cuánto (HUB_SHELL-F99), y que cada persona
  tenga su PIN (HUB_SHELL-F03, HUB_SHELL-F22 o Empleados, HUB_SHELL-F85).
- Tras dar un PIN nuevo, recarga ERPlora en las cajas para que salga en la rejilla.

## Flujos

### HUB_SHELL-F01 Entrar con la cuenta de erplora.com
Estado: parcial — la verificación en dos pasos dice «Hemos enviado un código de un solo uso a tu email», pero erplora.com no manda nada: el código está en la app autenticadora de la persona (o es uno de recuperación); la pantalla no distingue «ya no eres miembro de este negocio» ni «un administrador te dio de baja» de unas credenciales erróneas: las tres dicen «No se pudo iniciar sesión. Revisa tus credenciales o la conexión.»; la casilla «Confiar en este dispositivo» no cambia nada en el hub (todo acceso con cuenta vuelve de confianza el dispositivo): desmarcarla solo evita el paso «Crea tu PIN» y que este navegador recuerde a la persona, y su ⓘ promete lo contrario
Actor: administrador, responsable, empleado
Pantalla: Acceso
Pasos:
1. Abre el hub sin sesión: sale **Acceso** con el logo del negocio y «Entra en tu negocio». Si el dispositivo ofrece PIN, arriba hay dos pestañas, «PIN» y «Email»; si no, solo el formulario.
2. Escribe «Email» y «Contraseña» (el ojo muestra la contraseña). En un dispositivo compartido sale marcada la casilla «Confiar en este dispositivo», con un botón ⓘ que explica «Acceso por PIN»; en uno marcado como personal, en su lugar, «Este dispositivo está configurado como personal: la sesión se queda abierta y nunca pide PIN. Un administrador puede cambiarlo en Ajustes › General.».
3. Pulsa «Entrar» (un círculo gira mientras trabaja). O pulsa «Continuar con Google»: el navegador va a erplora.com, que pide la cuenta de Google y vuelve al hub ya identificado.
4. Si la cuenta pide verificación, la tarjeta cambia a «Verifica que eres tú»: «Hemos enviado un código de un solo uso a tu email. Introdúcelo para continuar.». Es falso: erplora.com contesta `method: "totp"` y `delivered: false` y no manda nada; el código es el de la app autenticadora de la persona o uno de sus códigos de recuperación, y la pantalla no lee esos dos campos. Escribe el «Código de verificación» y pulsa «Verificar»; «Volver» regresa al formulario.
5. Si confiaste el dispositivo y aún no tienes PIN, la pantalla te pide uno (HUB_SHELL-F03). Si no, entras en la pantalla que habías pedido o en **Inicio**.
Entra: el correo y la contraseña (o el código de Google), que comprueba erplora.com; el identificador del dispositivo; si el hub ofrece PIN aquí (modo del dispositivo, confianza y dial del negocio, los tres leídos del hub sin sesión).
Sale: pide a erplora.com la credencial y al hub la sesión local (`/api/auth/cloud`, con el identificador de este navegador pero sin la casilla): el hub vuelve de confianza el dispositivo siempre. Con la sesión, vuelve a leer el contexto del hub para conocer la lista de caras, que no se da a un navegador que aún no era de confianza (HUB-F133); es esa lista la que decide si la persona ya tiene PIN (HUB_SHELL-F03). Guarda en este navegador la sesión, el nombre, el correo, el rol y los permisos de la persona, y los tokens de erplora.com, que solo se guardan cuando el hub ha dado la sesión; al empezar borra los que hubiera de un intento anterior (hub#2506). Salvo que se desmarque la casilla (marcada por defecto, también donde no se ve), apunta a la persona —nombre e iniciales, nunca su correo (hub#2536)— en la lista de caras de este navegador, que no se borra al cerrar sesión.
Si falla: campos vacíos o correo sin «@»: «Introduce un email válido y tu contraseña.». Credenciales erróneas, persona dada de baja o que ya no es miembro: «No se pudo iniciar sesión. Revisa tus credenciales o la conexión.». Código vacío: «Introduce el código que enviamos a tu email.»; erróneo o caducado: «Código incorrecto o caducado. Hemos enviado un código nuevo, inténtalo de nuevo.» (no vuelve a pedir la contraseña; tampoco se envía ningún código nuevo); otro fallo del código: «No se pudo verificar el código. Inténtalo de nuevo.». Google que no termina: «No se pudo iniciar sesión con Google. Inténtalo de nuevo.». Hub sin registrar: HUB_SHELL-F12. Cuando erplora.com acepta la contraseña y el hub rechaza después (baja, ya no miembro, hub que no contesta), en el navegador no queda ninguna credencial de erplora.com, ni la de esta persona ni la de un intento anterior.
Implicados: HUB-F130, HUB-F144, REC_ALTA-F07, SAAS_AUTH-F04, SAAS_AUTH-F16, SAAS_AUTH-F17, SAAS_AUTH-F20, SAAS_AUTH-F29
QA: qa-hub-restaurant §7.02

### HUB_SHELL-F02 Entrar desde el panel de erplora.com sin volver a teclear la contraseña
Estado: parcial — quien entra así nunca ve el paso «Elige un PIN»; y en un navegador el pase no lleva el identificador del dispositivo, así que el hub no lo vuelve de confianza: allí no aparecerá el pinpad, no sale en Dispositivos y «Este dispositivo» no se puede cambiar; solo en la app instalada equivale a HUB_SHELL-F01
Actor: administrador, responsable, empleado
Pantalla: Acceso
Pasos:
1. En erplora.com la persona pulsa entrar en su negocio (o abre la app instalada, que pasa por el mismo sitio).
2. El hub abre con un pase escondido en la dirección; la pantalla lo quita de la barra de direcciones antes de nada y lo canjea mientras enseña el indicador de carga.
3. La persona aparece dentro, en **Inicio**, sin haber visto la pantalla de acceso.
Entra: el pase de un solo uso (como mucho 128 caracteres; si es más largo se descarta sin canjear) y el identificador del dispositivo.
Sale: la sesión y los mismos datos guardados que HUB_SHELL-F01, sin pasar por el formulario y sin tocar la lista de caras de este navegador; antes de abrir la primera pantalla vuelve a leer el contexto del hub con la sesión, para conocer la lista de caras que usan Cambiar de usuario y el diálogo de aprobación (HUB-F133). El identificador del dispositivo solo viaja desde la app instalada; desde un navegador el hub no apunta el dispositivo ni le aplica el límite de dispositivos del plan. Un fallo se apunta en el registro de errores del hub con el código, nunca con el pase.
Si falla: el acceso normal sale con el aviso «No se pudo entrar desde el panel de ERPlora» — «Inicia sesión aquí para continuar.», una sola vez. ERPlora no se termina de abrir hasta que el canje acaba, sin tope de tiempo; a los 10 segundos solo deja de esperarlo la decisión de qué pantalla enseñar (sin confirmar qué ve la persona si el canje acaba bien después de ese plazo).
Implicados: HUB-F131, HUB_APP-F02, REC_ALTA-F07, SAAS_AUTH-F19, SAAS_DASHBOARD-F06, SAAS_DASHBOARD-F202
QA: ninguno

### HUB_SHELL-F03 Elegir el PIN la primera vez que se entra en una caja
Estado: parcial — un PIN que ya usa otra persona sale como «No se pudo guardar el PIN. Vuelve a intentarlo.» sin decir el motivo (Mi perfil sí lo dice); solo se ofrece si se marcó «Confiar en este dispositivo», y recargar la página en este paso entra sin PIN
Actor: administrador, responsable, empleado
Pantalla: Acceso
Pasos:
1. Tras HUB_SHELL-F01 con «Confiar en este dispositivo», en un dispositivo compartido que pregunta y si la persona aún no tiene PIN, la tarjeta cambia a «Crea tu PIN de acceso».
2. Teclea el PIN en el teclado de círculos: «Elige un PIN de {n} dígitos» (4 o 6, lo que diga el negocio).
3. Repite: «Confirma tu PIN».
4. Al acertar la repetición se guarda y se entra. El hub ya la deja entrar con PIN, pero la rejilla de caras de cada dispositivo de confianza la enseña la próxima vez que se cargue ERPlora en él (también en este).
Entra: la sesión recién abierta; la longitud del PIN del negocio.
Sale: pide al hub fijar el PIN de quien tiene la sesión (`/api/auth/set-pin`). Si la persona ya tenía PIN, no se le pide otro y se conserva el suyo.
Si falla: repetición distinta: «Los PIN no coinciden, inténtalo de nuevo» y vuelve al primer paso. Dígitos repetidos o seguidos (1111, 1234): «Ese PIN es demasiado fácil de adivinar: evita dígitos repetidos (1111) y secuencias (1234).». Cualquier rechazo del hub: «No se pudo guardar el PIN. Vuelve a intentarlo.».
Implicados: HUB-F132, REC_ALTA-F16
QA: qa-hub-restaurant §7.02

### HUB_SHELL-F04 Entrar con PIN
Estado: parcial — la rejilla es la lista que dio el hub al abrir ERPlora: quien recibe un PIN después no aparece y quien se da de baja sigue apareciendo (y recibe «PIN incorrecto») hasta recargar la página; en un hub donde nadie tenía PIN al abrir, tras el primer «Crea tu PIN» Acceso no ofrece el pinpad hasta recargar. Lo mismo vale para Cambiar de usuario y el diálogo de aprobación
Actor: responsable, empleado
Pantalla: Acceso
Pasos:
1. En un dispositivo compartido y de confianza cuyo negocio pide PIN, **Acceso** abre en la pestaña «PIN»: «Introduce tu PIN», «…o pasa tu placa: no hace falta elegir tu nombre antes.» y «Elige tu usuario» con una tarjeta por persona (cara con iniciales y nombre). Con una sola persona, ya sale elegida.
2. Toca tu nombre; sale tu cara y el teclado con tantos círculos como dígitos tenga el PIN del negocio. La flecha a la izquierda del 0 («Cambiar usuario») vuelve a la rejilla.
3. Teclea el PIN: entra solo al último dígito, sin botón.
4. Entras en la pantalla que habías pedido o en **Inicio**. El pie de la tarjeta dice «ERPlora · dispositivo de confianza».
Entra: la lista de personas con PIN y la longitud del PIN, que el hub da en su contexto, leída una vez, al abrir ERPlora; la lectura dice qué dispositivo pregunta y presenta la sesión que haya, porque la lista solo llega a una sesión viva o a un dispositivo que el PIN dejaría pasar (en otro, la rejilla sale vacía y queda «Email», HUB-F133). Tras entrar con la cuenta o desde el panel se vuelve a leer con la sesión nueva (HUB_SHELL-F01, F02); el nombre elegido y los dígitos. Cada tarjeta enseña solo la cara con las iniciales y el nombre: nunca el correo de nadie, ni el que el navegador guardase antes de hub#2536, que se olvida al abrir ERPlora.
Sale: pide al hub la sesión por PIN (`/api/auth/pin`) y guarda la sesión, el rol y los permisos (el correo de quien entra lo da después su perfil del hub, `/api/profile`, nunca la lista de caras); al tenerla, borra de este navegador los tokens de erplora.com que hubiera (una sesión de PIN nunca los lleva, hub#2506). Funciona aunque erplora.com no responda.
Si falla: PIN erróneo: los círculos se vacían y debajo «PIN incorrecto». Dispositivo que nunca entró con una cuenta o que un administrador quitó: «En este dispositivo todavía no funciona el PIN. Entra una vez con tu cuenta aquí y a partir de entonces sí funcionará.». Navegador que no guarda datos (ventana privada): «Este navegador no puede recordar qué dispositivo es, así que aquí no se puede usar un PIN. Entra con tu cuenta, o permite que este sitio guarde datos y vuelve a intentarlo.». Demasiados intentos: «Demasiados intentos fallidos. Espera {minutes} minutos y vuelve a intentarlo.» (los minutos redondeados hacia arriba; sin dato, «Espera unos minutos»). Siempre queda «Email» para entrar con la cuenta.
Implicados: HUB-F133, HUB-F135, REC_ALTA-F16
QA: qa-hub-restaurant §7.02

### HUB_SHELL-F05 Entrar pasando la placa
Estado: parcial — la lectura con tarjeta y tableta reales no está validada (pm#145): el lector USB y el NFC de Android solo se prueban con tests
Actor: responsable, empleado
Pantalla: Acceso
Pasos:
1. En la pestaña «PIN» de **Acceso** (con o sin persona elegida), pasa la tarjeta por el lector o acércala al NFC de la tableta. No hace falta tocar ningún campo.
2. La pantalla reconoce la ráfaga del lector por su velocidad y la manda al hub.
3. Entras como el dueño de la tarjeta.
Entra: el número que lee el lector o el NFC del aparato. Solo se atiende en el paso PIN y donde el hub ofrece pinpad; durante el alta del PIN o el código de verificación se ignora.
Sale: pide al hub la sesión por placa (`/api/auth/badge`); el resto como HUB_SHELL-F04.
Si falla: tarjeta que no es de nadie o cuyo dueño está de baja: «Esa placa no abre nada aquí. Entra con tu PIN o pídeselo a un administrador.». Dispositivo sin confianza, navegador sin datos o demasiados intentos: las mismas frases que HUB_SHELL-F04. El pinpad sigue disponible.
Implicados: HUB-F134, HUB_APP-F23
QA: ninguno

### HUB_SHELL-F06 Perder la sesión porque se abrió en otro dispositivo
Estado: hecho
Actor: sistema
Pantalla: Acceso
Pasos:
1. El plan del negocio admite un dispositivo a la vez y alguien entra en otro.
2. En este, la siguiente petición al hub vuelve rechazada; la pantalla comprueba que la sesión está de verdad cerrada y no por otro motivo.
3. Sale el aviso «Sesión abierta en otro dispositivo» y la persona va a **Acceso**, donde arriba se lee «Sesión abierta en otro dispositivo» — «Tu plan cubre un dispositivo a la vez, así que al entrar en otro se cerró la sesión de este. Vuelve a entrar para usarlo aquí, o amplía los dispositivos de tu plan.», con el botón «Actualizar plan».
4. Puede volver a entrar (y desaloja al otro) o ir a ampliar el plan.
Entra: el motivo que da el hub en el rechazo (`session_evicted_device_limit`).
Sale: la sesión local borrada; «Actualizar plan» abre erplora.com por la misma puerta que HUB_SHELL-F16.
Si falla: en la copia de Google Play no sale «Actualizar plan». Si el hub no dice el motivo, la persona ve HUB_SHELL-F07. Si no se puede abrir el navegador: «No se pudo abrir tu navegador. Entra en erplora.com para gestionar tu plan.».
Implicados: HUB-F137
QA: ninguno

### HUB_SHELL-F07 La sesión termina mientras se trabaja
Estado: hecho
Actor: sistema
Pantalla: Acceso
Pasos:
1. La sesión caduca (un turno de 12 horas en un dispositivo compartido, 30 días en uno personal, 1 hora si el negocio pide siempre el PIN), un administrador quita el dispositivo o da de baja a la persona.
2. La siguiente petición al hub (también la de la pantalla de una app) vuelve rechazada. La pantalla pregunta al hub si la sesión sigue viva: un rechazo por falta de rol o un corte de red no cierran nada.
3. Con la sesión muerta, sale el aviso «Tu sesión ha terminado: caducó o se abrió en otro dispositivo. Vuelve a entrar.» y la persona va a **Acceso**.
4. Si lo que caduca es la credencial de erplora.com o erplora.com dice que este negocio ya no existe, la persona va a **Acceso** sin aviso; en el segundo caso la app instalada olvida además el negocio.
Entra: el rechazo del hub y la comprobación de la sesión; el rechazo de erplora.com al renovar la credencial.
Sale: la sesión local cerrada una sola vez aunque haya muchas peticiones en vuelo; la venta a medias la guarda su app.
Si falla: sin red la sesión no se da por muerta: la pantalla enseña el error de conexión de cada sitio y la franja de HUB_SHELL-F14.
Implicados: HUB-F136
QA: qa-hub-restaurant §7.02

### HUB_SHELL-F08 Cerrar la sesión de una caja que nadie toca
Estado: parcial — el cierre lo hace solo la pantalla (el servidor no lo vigila: con la pantalla cerrada o colgada la sesión vive hasta su tope de 1 hora) y cierra sin avisar antes ni decir después por qué
Actor: sistema
Pantalla: Acceso
Pasos:
1. El negocio eligió en **Ajustes → General → Pinpad** «Volver a preguntar tras inactividad» con unos minutos (1, 5, 10, 15 o 30) y este dispositivo es compartido.
2. Nadie toca la pantalla (ni dedo, ni tecla, ni rueda) durante esos minutos.
3. La sesión se cierra y la caja vuelve a **Acceso**, al pinpad.
Entra: el dial del negocio y los minutos (5 si el valor guardado no se entiende), el modo del dispositivo y que haya sesión.
Sale: la sesión cerrada en el hub y en este navegador. La cuenta abierta la conserva su app.
Si falla: con «Hasta cerrar sesión», en un dispositivo personal o sin sesión el vigilante no se arma. Si la pantalla no puede leer el dial del negocio (la lectura del modo del dispositivo falla y no la corrige una lectura posterior de los ajustes, por ejemplo al abrir Ajustes › General), el vigilante se arma igual, como con «pedir siempre», con los minutos guardados o 5 si tampoco se conocen, y la caja avisa una vez abajo: «No se ha podido leer cómo pide el PIN esta caja. Por seguridad, volverá al pinpad tras N minutos sin usarla» (hub#2537); una lectura buena posterior manda y, si dice «por turno» o «Hasta cerrar sesión», lo desarma. La lectura rota no se reintenta sola: se corrige en el siguiente acceso, que vuelve a leer el modo (hub#2677). La persona no ve ningún mensaje de por qué volvió al pinpad. Quien cambie este tiempo revisa también la tarjeta Pinpad de Ajustes › General (área «Personas y permisos» de este documento), los topes de la pantalla (1, 5, 10, 15 o 30 minutos; 5 por defecto) y los del servidor (HUB-F140), y el tope de 1 hora de «pedir siempre» (HUB-F136).
Implicados: HUB-F136, HUB-F140, SALES-F17
QA: ninguno

### HUB_SHELL-F09 Cambiar de usuario sin perder la venta
Estado: parcial — el relevo no acepta la placa, solo nombre y PIN (el acceso y la aprobación sí la aceptan); las caras son las de HUB_SHELL-F04 (lista leída al abrir ERPlora)
Actor: responsable, empleado
Pantalla: Cambiar de usuario
Pasos:
1. En una caja compartida y de confianza cuyo negocio pide PIN, abre la tarjeta de usuario del menú y pulsa «Cambiar de usuario» (no sale en ningún otro caso).
2. Sobre la pantalla en curso se abre **Cambiar de usuario**: «La venta sigue abierta. A partir de ahora queda a nombre de quien entre aquí.» y «¿Quién se pone?» con una cara por persona.
3. Toca la tuya y teclea el PIN. La flecha («Otra persona») vuelve a las caras; «Cancelar» cierra sin cambiar nada.
4. Sale «Ahora atiende {name}»; la pantalla sigue donde estaba, pero montada de nuevo para quien entró: lo que se ve lo ha leído con su sesión, y «atrás» ya no lleva a las pantallas que había abierto quien se fue. La venta en curso sigue (la caja recuerda su cuenta abierta) y lo siguiente queda a nombre de quien entró. Si estaba en una app, o en una pestaña de una app, que su lanzador no le da (o el lanzador no se pudo leer), la caja va a **Inicio**. El panel del asistente se cierra y, al abrirlo, está vacío (HUB_SHELL-F195).
Entra: el nombre y el PIN de quien entra; la sesión de quien sale.
Sale: abre la sesión nueva por la misma puerta que HUB_SHELL-F04 y, solo cuando la tiene, cierra la anterior; olvida los tokens de erplora.com, el idioma, la apariencia y la conversación del asistente de quien se fue, y vuelve a leer para quien entra el plan, el lanzador y «Mis apps», y la lista «Termina de configurar tu negocio», en ese orden (hub#2506). Si una de esas lecturas falla, se ve que no se pudo cargar, nunca la lista de quien se fue. Después vuelve a montar la pantalla abierta y el panel del asistente (cerrado, sin texto, adjuntos, aviso de cuota ni modo configuración de quien se fue), o lleva a Inicio si esa pantalla no es para quien entra (hub#2539, hub#2538).
Si falla: PIN o nombre erróneos: «Esos datos no han funcionado. Revisa el nombre y el PIN, y vuelve a intentarlo.» y quien estaba dentro sigue dentro. Dispositivo sin dar de alta: «Este dispositivo todavía no está dado de alta para el PIN. Entra una vez con una cuenta de ERPlora en él y el PIN funcionará a partir de entonces.»; sin identificar: «Este dispositivo no ha podido identificarse. Recarga la página y vuelve a intentarlo.». Demasiados intentos: la frase de HUB_SHELL-F04. Si el hub aún no ha dado la lista de caras, se escribe «Su nombre» y se pulsa «Continuar».
Implicados: HUB-F138
QA: qa-hub-restaurant §7.02, L-13

### HUB_SHELL-F10 Cerrar sesión
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Menú lateral
Pasos:
1. Abre la tarjeta de usuario arriba del menú lateral (en el móvil, primero el menú con el botón de la barra).
2. Pulsa «Cerrar sesión».
3. El menú se cierra y sale **Acceso**.
Entra: la sesión.
Sale: pide al hub borrar la sesión (sin esperar la respuesta) y borra de este navegador la sesión, los tokens de erplora.com, el perfil, la apariencia y el idioma personales, el plan resuelto, el lanzador, la lista «Termina de configurar tu negocio» y la conversación del asistente. La lista de caras de este navegador (nombre e iniciales, sin correos) se conserva.
Si falla: si el hub no contesta, la sesión local se borra igual y la del hub caduca sola.
Implicados: HUB-F136
QA: ninguno

### HUB_SHELL-F11 Decidir si este dispositivo es compartido o personal
Estado: parcial — el rechazo del hub se pinta con su texto en inglés y el identificador del dispositivo («this hub does not know the device …»)
Actor: administrador
Pantalla: Ajustes › General
Pasos:
1. Desde el propio dispositivo, abre **Ajustes → General**; bajo «Este dispositivo»: «Cómo pregunta este dispositivo quién lo está usando. Cada dispositivo del negocio se decide por separado.».
2. Elige «Compartido — una caja o tablet que usan varias personas» («Pide PIN al entrar y la olvida al acabar el turno, así que cada venta queda atribuida a quien la hizo.») o «Personal — un dispositivo que solo usas tú» («La sesión se queda abierta y nunca pide PIN…»).
3. La marca se mueve solo cuando el hub confirma; mientras guarda, las opciones se desactivan.
4. La pantalla de acceso de este dispositivo cambia en consecuencia: pinpad en compartido, solo cuenta en personal.
Entra: el dispositivo que hace la petición (nunca otro); la sesión de administrador.
Sale: pide al hub guardar el modo (`PUT /api/device/mode`); el acceso, el relevo y el vigilante de inactividad leen el modo confirmado.
Si falla: sin ser administrador las opciones salen desactivadas con «Solo un administrador puede cambiar cómo entra la gente en este dispositivo.». Error sin motivo: «No se pudo cambiar este dispositivo. Comprueba la conexión e inténtalo de nuevo.»; con motivo, el texto del hub tal cual. El caso típico es un navegador que solo ha entrado por el pase del panel (HUB_SHELL-F02): el hub no lo conoce y la tarjeta enseña en inglés «this hub does not know the device `…`: sign in online on it once…»; se arregla entrando una vez con la cuenta en ese navegador.
Implicados: HUB-F139, REC_ALTA-F16
QA: qa-hub-restaurant §7.02

### HUB_SHELL-F12 Abrir un hub que todavía no está dado de alta
Estado: parcial — el rechazo dice «Comprueba la conexión e inténtalo de nuevo», cuando lo que falta es el alta del hub en erplora.com y reintentar no lo arregla
Actor: administrador, responsable, empleado
Pantalla: Acceso
Pasos:
1. Un hub instalado al que le falta su alta de máquina abre **Acceso**; cualquier otra dirección lleva aquí y una sesión guardada de antes se cierra.
2. No hay pinpad: solo el formulario de la cuenta.
3. Con una cuenta válida, la tarjeta dice «La cuenta es válida, pero no se pudo registrar este dispositivo. Comprueba la conexión e inténtalo de nuevo.» y no se entra.
Entra: el contexto público del hub (`registration_required`).
Sale: nada guardado.
Si falla: es el propio caso de fallo; el hub de demostración y el hub en la nube, que llegan dados de alta, no pasan por aquí.
Implicados: HUB-F160, REC_ALTA-F16
QA: ninguno

### HUB_SHELL-F13 Abrir ERPlora cuando el hub no contesta
Estado: hecho
Actor: sistema
Pantalla: No podemos conectar con tu negocio
Pasos:
1. Al abrir ERPlora sale un indicador de carga mientras el hub dice qué negocio es.
2. Si en 10 segundos no llega respuesta: «No podemos conectar con tu negocio» — «ERPlora no responde. Comprueba que este dispositivo tiene conexión a Internet y vuelve a intentarlo. Si sigue pasando, el problema puede ser nuestro.» con «Reintentar».
3. Si algo contesta pero no es el hub (un corte del proveedor, el hub reiniciándose): «Tu negocio no está disponible ahora mismo» — «…Este dispositivo y su conexión están bien: no tienes que revisar nada. Lo volvemos a intentar solos cada 30 segundos.» con «Reintentar ahora».
4. Cuando contesta, se abre ERPlora normal (el acceso o la pantalla en curso).
Entra: la respuesta del contexto del hub (`/api/hub/context`).
Sale: nada; no se monta el resto de la aplicación hasta que el hub contesta. El aviso habla en el último idioma que usó este dispositivo.
Si falla: es el propio caso de fallo.
Implicados: HUB-F161, HUB_APP-F11
QA: qa-hub-restaurant §7.16

### HUB_SHELL-F14 Saber que no hay conexión con el hub
Estado: hecho
Actor: sistema
Pantalla: Franja de conexión
Pasos:
1. Con sesión abierta, la pantalla pregunta al hub si está ahí cada 30 segundos mientras la pestaña está a la vista.
2. Si el navegador dice que no hay red, sale bajo la barra la franja «Sin conexión a Internet» — «Lo que necesita Internet —cargar pantallas, sincronizar, enviar facturas— no va a funcionar hasta que vuelva. Este aviso desaparece solo.».
3. Si hay red pero el hub no contesta dos veces seguidas (10 s cada intento, 5 s entre uno y otro; cualquier respuesta, también un error del servidor, cuenta como que está): «ERPlora no responde» — «Tu dispositivo parece tener conexión, pero ERPlora no contesta: puede ser tu Internet o un problema por nuestra parte…».
4. Al volver la conexión, la franja desaparece sola; no tiene botón.
Entra: el estado de red del navegador y la sonda de salud del hub.
Sale: nada guardado.
Si falla: la franja no sale en la pantalla de acceso. No hay modo sin conexión: todo lo que lee o guarda pasa por el hub, así que hasta que vuelva solo se ve lo que ya estaba en pantalla; al volver no se reintenta nada solo, y el corte no cierra la sesión. El reintento de lo que falló vive en cada pantalla, no en la franja.
Implicados: HUB-F161, HUB_APP-F11
QA: qa-hub-restaurant §7.16

### HUB_SHELL-F15 Moverse por el menú lateral y la barra superior
Estado: parcial — el menú enseña Empleados, Mi plan, Apps, Sistema y Ajustes a todo el mundo; un empleado entra y es cada pantalla la que le esconde lo que no puede hacer
Actor: administrador, responsable, empleado
Pantalla: Menú lateral
Pasos:
1. En escritorio el menú está fijo a la izquierda; el botón de panel de la barra lo pliega a iconos («Colapsar menú» / «Expandir menú»). En tableta y móvil se abre con el botón de la barra («Abrir menú») y se cierra al elegir.
2. Menú «General»: Inicio, Empleados, Archivos. «Cuenta»: Mi plan, Apps, Sistema, API (solo si Ajustes tiene encendido «Mostrar documentación de la API») y Ajustes. La entrada en uso sale marcada.
3. Las apps instaladas no están en el menú: se abren con el lanzador de la barra («Mis apps», una baldosa por app y «Apps» al final) o desde **Inicio**.
4. La barra superior lleva el título de la pantalla, «Atrás» en las de detalle, el lanzador y, desde 768 px, «erplora.com», «Cambiar de negocio», «Asistente» y la campana; «Asistente» solo si el asistente está disponible; en el móvil esas acciones se pliegan en «Más opciones» (⋮) y el número de la campana viaja con él. Una barra fina bajo la barra indica que hay peticiones en curso.
Entra: la lista de apps que el hub sirve a esta persona (ya filtrada por sus permisos), si la API está publicada, la sesión.
Sale: nada guardado (el plegado del menú no se recuerda al recargar). Las pantallas del menú se descargan en segundo plano tras entrar, para que un toque no dependa de la red.
Si falla: una pantalla cuyo código no llega: «No se ha podido abrir esa sección. Revisa la conexión y vuelve a intentarlo.»; si al arrancar no llega nada: «ERPlora no ha podido terminar de abrirse» con «Reintentar». Una pantalla que falla por dentro: «No se ha podido abrir esa sección. Algo ha fallado dentro de ERPlora; vuelve a intentarlo.»; si es la primera al abrir, a pantalla entera «No se ha podido abrir esta pantalla» — «Algo ha fallado dentro de ERPlora al abrir esta pantalla…» con «Reintentar». Lanzador vacío: «Aquí aparecerán tus apps. Pulsa Apps para añadir las que necesite tu negocio.».
Implicados: HUB-F31, HUB_APP-F28
QA: BD-03

### HUB_SHELL-F16 Ir a erplora.com ya identificado
Estado: parcial — [SEG] «Cambiar de negocio» dice que cierra la sesión y no la cierra: la sesión del hub y los tokens de erplora.com quedan vivos hasta que caducan
Actor: administrador, responsable, empleado
Pantalla: Barra superior
Pasos:
1. Para gestionar el negocio: botón «erplora.com» de la barra («Gestiona tu negocio en erplora.com» en el menú del móvil). Solo lo ve quien administra el hub y entró con su cuenta (no con PIN).
2. Para cambiar de plan: «Actualizar plan» al pie del menú lateral, visible para todos.
3. erplora.com se abre en otra pestaña (en la app instalada, en el navegador del sistema) ya identificado, en la página pedida; ERPlora se queda donde estaba.
4. En la app instalada, «Cambiar de negocio» pregunta «¿Cambiar de negocio?» — «Este dispositivo cerrará la sesión de este negocio y mostrará tu lista de negocios.»; «Cambiar» olvida la dirección del negocio y abre la lista de erplora.com, pero no cierra la sesión ni borra los tokens; «Cancelar» no hace nada.
Entra: la sesión (con cuenta), el permiso de administrar y la distribución de la app.
Sale: pide siempre al hub un pase de un solo uso hacia erplora.com; el hub solo lo da a una sesión abierta con la cuenta, y si no lo da la pantalla abre el enlace normal, que pide la contraseña.
Si falla: «No se pudo abrir tu navegador. Entra en erplora.com para gestionar tu negocio.» o, para el plan, «…para gestionar tu plan.». En la copia de Google Play no salen ni «erplora.com» ni «Actualizar plan».
Implicados: HUB-F142, HUB_APP-F04, HUB_APP-F29, SAAS_AUTH-F21
QA: L-17

### HUB_SHELL-F17 Abrir una dirección que el hub no tiene
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Esta página no existe
Pasos:
1. Con sesión, se abre una dirección que no es de ninguna pantalla (un enlace viejo, `/tpv`).
2. Dentro del hub, con su menú, sale «Esta página no existe» — «La dirección que has abierto no forma parte de este hub. Puede ser un enlace antiguo, o el nombre de una app adivinado: tus apps se abren desde el menú o desde Inicio.» y el botón «Ir a Inicio». La dirección pedida se queda en la barra.
3. Una app que este hub no tiene, abierta por su dirección, vuelve a **Inicio** con «Esta app no está disponible para este hub.».
Entra: la dirección.
Sale: nada.
Si falla: sin sesión, cualquier dirección lleva a **Acceso**. Las direcciones retiradas `/export`, `/import` llevan a Ajustes › Datos y copias y `/first-run` a Inicio.
Implicados: ninguno
QA: ninguno

### HUB_SHELL-F18 Poner la pantalla de una app a pantalla completa
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: Vista de un módulo
Pasos:
1. En una pantalla de app que lo ofrece (Vender, la Pantalla de cocina), elige «Pantalla completa» en su menú.
2. Desaparecen el menú lateral, la barra superior y las pestañas de abajo; en un navegador que lo permite, también la barra del navegador.
3. «Salir de pantalla completa» en el mismo menú, Esc (salir del modo del navegador) o irse de la app lo devuelven todo.
Entra: la petición de la app; que su pestaña lo haya declarado en su `module.json` (`navigation[].chrome`), cosa que comprueba la vista de un módulo. La app solo pide; el marco es del shell y solo atiende lo declarado (`lib/immersive.ts`, ADR-0048). Este flujo recoge también el antiguo HUB_SHELL-F55 «Vender a pantalla completa», retirado por describir el mismo gesto.
Sale: nada guardado; no se recuerda al volver.
Si falla: si el navegador no deja ocupar la pantalla entera (el iPhone no lo da), igual se esconden las barras del hub. Las franjas de bloqueo y de conexión siguen a la vista.
Implicados: KITCHEN-F10
QA: qa-hub-restaurant §7.17

### HUB_SHELL-F19 Abrir el hub en el móvil y dejarlo como aplicación
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Menú lateral
Pasos:
1. Al pie del menú lateral hay un código QR con «Ábrelo en el móvil» — «Escanea el código. Para dejarlo fijo, añádelo a la pantalla de inicio desde el menú del navegador.». Con el menú plegado sale solo el icono; tocarlo despliega el menú.
2. Escanea con la cámara del móvil: abre la dirección de este hub.
3. Desde el menú del navegador, «Instalar» o «Añadir a pantalla de inicio»: queda como aplicación «ERPlora».
Entra: la dirección del hub.
Sale: en un navegador se registra el trabajador que guarda la portada para abrir sin red; la app instalada y el modo desarrollo no lo usan.
Si falla: ERPlora nunca interrumpe para pedir que se instale. Una versión nueva del hub se aplica sola la próxima vez que se carga la página, sin aviso.
Implicados: HUB_APP-F03, REC_ALTA-F16
QA: ninguno

### HUB_SHELL-F20 Actualizar la aplicación instalada cuando hay versión nueva
Estado: hecho
Actor: administrador
Pantalla: Menú lateral
Pasos:
1. En la app instalada (Windows, macOS, Android), al pie del menú sale «Actualizar ERPlora ({version})» cuando hay una versión más nueva que la que corre aquí.
2. Púlsalo: «Actualizar ERPlora» explica qué pasa: en el ordenador, «Se abre tu navegador para descargar la versión {version}. No se instala nada solo…»; en Android, «Se abre la ficha de ERPlora en Google Play…».
3. «Descargar» (o «Abrir Google Play») abre el destino; «Ahora no» lo deja. ERPlora no se cierra ni recarga.
Entra: la versión de la app y la publicada, que el hub consulta al arrancar y cada 6 horas.
Sale: nada guardado; la descarga o la ficha de Play.
Si falla: «No hemos podido abrir tu navegador. Entra en erplora.com para conseguir la nueva versión.» (en Android, «…Google Play…»). Si no se sabe la versión, no sale nada. En un navegador no existe.
Implicados: HUB-F167, HUB_APP-F31
QA: ninguno

### HUB_SHELL-F21 Cambiar mis datos, foto, idioma y apariencia
Estado: parcial — el resumen de la cuenta se anuncia en inglés al lector de pantalla («Account summary», ERPlora/hub#2589)
Actor: administrador, responsable, empleado
Pantalla: Mi perfil
Pasos:
1. Abre la tarjeta de usuario del menú y pulsa «Perfil».
2. En «Datos de la cuenta» cambia «Nombre», «Apellidos» o «Correo electrónico» y pulsa «Guardar mis datos»: «Perfil guardado».
3. «Cambiar foto» sube una JPG, PNG o WebP («Foto actualizada»); «Quitar» la borra.
4. En «Preferencias», «Idioma» («Usar el idioma del negocio», «Español», «English») y «Apariencia» (modo «Sistema (auto)», «Claro», «Oscuro» y la paleta) se guardan al elegir y se aplican al momento; «Usar la apariencia del negocio» deshace lo propio.
Entra: el perfil de quien tiene la sesión.
Sale: pide al hub guardar el perfil, las preferencias y la foto; el idioma y la apariencia siguen a la persona en cualquier dispositivo en el que entre. El «Correo electrónico» es solo de contacto: no es el correo con el que se entra y el hub nunca da ni quita con él una membresía de erplora.com, ni al cambiarle el rol ni al darla de baja (HUB-F143, ERPlora/hub#2500).
Si falla: si el perfil no se pudo leer, «No se pudo cargar el perfil» («Tus datos siguen igual. Comprueba la conexión y vuelve a intentarlo.») con «Reintentar» en lugar de «Datos de la cuenta», «Preferencias» y «PIN», y sin «Cambiar foto»: no hay nada que guardar hasta que la lectura funcione; la cabecera (nombre y rol, de la sesión) y «Gestión de la cuenta» siguen, y mientras se lee sale el indicador de carga (hub#2541). Al guardar: «No se pudo guardar el perfil»; foto rechazada: «No se pudo guardar la foto. Usa JPG, PNG o WebP de hasta 2 MB.».
Implicados: HUB-F143
QA: ninguno

### HUB_SHELL-F22 Cambiar mi PIN desde Mi perfil
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Mi perfil
Pasos:
1. En **Mi perfil**, tarjeta «PIN» (solo cuando el perfil se pudo leer, HUB_SHELL-F21): «El PIN con el que entras en la caja. Cámbialo cuando quieras — no hace falta que lo haga nadie más.» (sin PIN: «Todavía no tienes un PIN. Establece uno para poder entrar también desde la caja.»).
2. Si ya tienes PIN, escribe «PIN actual».
3. Escribe «PIN nuevo» y «Repite el PIN nuevo» y pulsa «Cambiar PIN» (o «Establecer PIN»).
4. «PIN actualizado».
Entra: la sesión; la longitud del PIN del negocio.
Sale: pide al hub fijar el PIN propio (`/api/auth/set-pin`), con el actual si lo había.
Si falla: longitud distinta: «El PIN debe tener {n} dígitos.»; los dos no coinciden: «Los dos PIN no coinciden.»; fácil de adivinar: «Ese PIN se adivina a la primera…»; ya lo usa otra persona: «Ese PIN ya lo tiene otro usuario activo…»; actual erróneo: «Ese no es tu PIN actual. Escríbelo bien para poder fijar uno nuevo.»; treinta intentos en una hora (también los que salieron bien, HUB-F132, y las altas o ediciones con PIN que esa persona hizo en Empleados, HUB-F145 y HUB-F148): «Demasiados intentos de cambiar el PIN. Espera {minutes} minutos y vuelve a intentarlo.» (sin el tiempo: «…Espera unos minutos y vuelve a intentarlo.»). Otro fallo: «No se pudo guardar el perfil».
Implicados: HUB-F132, REC_ALTA-F16
QA: ninguno

### HUB_SHELL-F23 Gestionar o borrar mi cuenta de erplora.com
Estado: parcial — erplora.com pide la contraseña para borrar, así que una cuenta sin contraseña usable (la que solo entra con Google) no puede borrarse
Actor: administrador, responsable, empleado
Pantalla: Mi perfil
Pasos:
1. Al pie de **Mi perfil**, «Gestión de la cuenta»: con cuenta de erplora.com, «Puedes editar aquí tus propios datos. Sigue siendo tu cuenta de erplora.com.» y los botones «Gestionar cuenta en erplora.com» y «Borrar mi cuenta»; sin ella, «Esta identidad pertenece solo a este negocio…» y ningún botón.
2. Pulsa uno: erplora.com se abre en el navegador, en la página de la cuenta o en la confirmación de borrado, sin el resto del panel.
3. El borrado lo confirma erplora.com, no el hub, pidiendo la contraseña de la cuenta: una cuenta sin contraseña usable (la que solo entra con Google) no puede borrarse. Si la cuenta es la única propietaria de algún negocio, erplora.com no la borra: enseña esos negocios y pide borrarlos o traspasarlos antes desde erplora.com, así que ningún negocio se queda sin dueño cobrando (SAAS_DASHBOARD-F208).
Entra: los tokens de erplora.com de la sesión.
Sale: con sesión abierta con la cuenta, un pase de un solo uso para entrar ya identificado; con PIN, el enlace normal, que pide la contraseña.
Si falla: «No se pudo abrir la página de tu cuenta en el navegador. Entra en erplora.com para gestionarla.».
Implicados: HUB-F142, SAAS_AUTH-F13, SAAS_AUTH-F21, SAAS_DASHBOARD-F204, SAAS_DASHBOARD-F207, SAAS_DASHBOARD-F208, SAAS_DASHBOARD-F209, SAAS_DASHBOARD-F210
QA: L-17

## Cobertura contra la referencia

**Acceso y sesión**

| Elemento de la referencia | Estado | Flujo |
|---|---|---|
| Entrar con cuenta, segundo factor y Google | hecho | F01 |
| «Confiar en este dispositivo» decide si el dispositivo es de confianza | no hecho: el hub confía en todo acceso con cuenta; la casilla solo decide el PIN y si el navegador recuerda a la persona | F01 |
| Decir por qué no se entra (baja, ya no miembro) | parcial: misma frase que credenciales erróneas | F01 |
| Entrar desde el panel de gestión sin volver a identificarse | parcial: en el navegador no hace el dispositivo de confianza | F02 |
| Pedir el PIN propio en el primer acceso a una caja | parcial: solo con «Confiar» y no al entrar por el panel | F02, F03 |
| Rejilla de caras y PIN de longitud fija | parcial: la rejilla es la del arranque hasta recargar | F04 |
| Bloqueo por intentos con el tiempo de espera | hecho (lo aplica el servidor, HUB-F135) | F04 |
| Placa en el acceso | parcial: sin validar con hardware real | F05 |
| Placa en el relevo de turno | no hecho | F09 |
| Relevo de turno encima de la venta | parcial: la pantalla abierta sigue siendo la de quien se fue hasta navegar | F09 |
| Cierre por inactividad configurable | parcial: solo la pantalla; sin aviso previo ni motivo | F08 |
| Avisar de la sesión desalojada por el plan | hecho | F06 |
| Dispositivo compartido o personal | hecho (rechazo en inglés) | F11 |
| Cerrar todas mis sesiones | no hecho (tampoco en el servidor) | — |
| Modo quiosco (una sola app, sin salir) | no existe; lo más cercano es pantalla completa | F18 |

**Navegación y marco**

| Elemento de la referencia | Estado | Flujo |
|---|---|---|
| Arranque sin servidor: aviso y reintentar | hecho | F13 |
| Cambiar de negocio cerrando la sesión | parcial: no la cierra | F16 |
| Trabajar sin conexión con el hub | no existe (hub en la nube): solo se avisa | F14 |
| Franja persistente sin conexión | hecho | F14 |
| Menú filtrado por el rol | parcial: el menú enseña todo; recortan las pantallas | F15 |
| Lanzador de apps | hecho | F15, F32 |
| Página «no existe» con salida | hecho | F17 |
| Pantalla completa para el TPV y la cocina | hecho | F18 |
| Instalar como aplicación y abrir en el móvil | hecho (sin pedirlo nunca) | F19 |
| Avisar de una versión nueva de la app instalada | hecho | F20 |
| Avisar de una versión nueva del hub en el navegador | no hecho, a propósito: se aplica al recargar | F19 |
| Perfil: datos, foto, idioma, tema | hecho | F21 |
| Cambiar el propio PIN | hecho | F22 |
| Borrar la cuenta desde la app | hecho (en erplora.com) | F23 |

## Datos: de quién es cada dato

El perfil, el PIN, el modo del dispositivo y los dispositivos son del hub (`HUB`, HUB-F132, HUB-F139,
HUB-F143). Lo que esta área guarda en **el navegador del dispositivo** (leído en `src/lib/*.ts` y
`src/views/LoginPage.vue`):

| Dónde (navegador) | Qué guarda | Dato personal | Cuándo se borra |
|---|---|---|---|
| `erplora.session` | identificador, nombre, correo, foto, rol y permisos de quien tiene la sesión | sí | al cerrar sesión o perderla |
| `erplora.hub_session`, `erplora.hub_session_credential` | la sesión del hub y cómo se abrió (cuenta, PIN, placa) | credencial | al cerrar sesión |
| tokens de erplora.com (`erplora.access`, `erplora.refresh`) | la credencial de la cuenta | credencial | al cerrar sesión, en el relevo de turno, al entrar con PIN o placa y al empezar un acceso con cuenta (que solo los guarda cuando el hub le da la sesión); **no** con «Cambiar de negocio» [SEG] |
| `erplora.trusted_users`, `erplora.trusted` | id, nombre e iniciales de quien entró con su cuenta en este navegador sin desmarcar «Confiar» (marcada por defecto, también donde no se ve); nunca el correo (hub#2536): el que guardaba una versión anterior se borra al abrir ERPlora | sí (el nombre) | nunca al cerrar sesión, al quitar el dispositivo ni al pasarlo a personal; se recorta contra la lista del hub al abrir Acceso y se vacía si nadie tiene PIN |
| `erplora.device_id` | el identificador de este dispositivo | no | nunca (es lo que el hub reconoce como de confianza) |
| `erplora.locale` | el idioma activo | no | se rehace en cada arranque |
| `erplora.theme`, `erplora.palette` | claves antiguas del tema | no | se borran al arrancar |

El PIN no se guarda nunca: viaja en el cuerpo de la petición y el ticket del código de verificación
vive solo en memoria. En memoria (no en el navegador) están el lanzador y la lista de configuración:
se vacían al cerrar sesión y se vuelven a leer en el relevo. La conversación del asistente (`erplora.assistant.history`) es del área «Asistente».

## Reglas que no se rompen

Solo lo que el código hace cumplir:

- Con un hub sin alta, una sesión guardada se cierra y no hay pinpad (router, `authGate`).
- El pinpad y la placa solo se ofrecen con dispositivo compartido, de confianza **según el hub** y
  un negocio que pregunta; sin respuesta del hub, no hay pinpad. La placa solo se atiende en el paso
  PIN.
- Un rechazo del hub solo cierra la sesión si una comprobación aparte confirma que está muerta (no
  por falta de rol ni por un corte de red), y la cierra una vez aunque haya muchas peticiones en vuelo.
- El relevo de turno no navega y no suelta la sesión anterior hasta tener la nueva; un PIN erróneo no
  cambia nada. Con la nueva, vuelve a leer el plan, el lanzador y la lista para quien entra.
- Una sesión de PIN o placa nunca lleva credenciales de erplora.com: al abrirla se borran las que
  hubiera; un acceso con cuenta solo las guarda cuando el hub le ha dado la sesión (hub#2506).
- La rejilla de caras enseña nombre e iniciales y el navegador no guarda el correo de nadie para
  ella; el correo de quien entra con PIN o placa llega de su perfil del hub (hub#2536).
- El hub solo da el pase hacia erplora.com a una sesión abierta con la cuenta; a cualquier otra, la
  pantalla le abre el enlace normal, que pide la contraseña. El botón «erplora.com» solo se ofrece con
  el permiso de administrar.
- La franja de conexión no se puede cerrar.

Lo que hoy **no** se cumple y no es una regla, sino un hueco de seguridad [SEG] (detalle en sus
flujos): tras el relevo la pantalla abierta es la de quien se fue hasta navegar (HUB_SHELL-F09,
hub#2539); «Cambiar de negocio» no cierra la sesión (HUB_SHELL-F16).

## Lo que NO hace, a propósito

- No pide instalar ERPlora como aplicación ni interrumpe para ofrecerlo: el QR espera en el menú
  (hub#685, hub#1715).
- La franja sin conexión no tiene «Reintentar»: recargar perdería lo tecleado y no arreglaría la red;
  el reintento vive en la pantalla que falló.
- No adivina direcciones (`/tpv` → Vender): el shell no conoce los ids de las apps.
- La pantalla nunca decide si un PIN es correcto: lo decide el hub.
- Las apps no viven en el menú lateral: se abren desde el lanzador «Mis apps» de la barra superior y
  desde Inicio.
- No avisa de una versión nueva del hub en el navegador: se aplica sola al recargar.

## Dudas abiertas

Se resuelven con `market-decision`; no las decide el worker.

- **Menú por rol.** Square y Toast esconden lo que el rol no puede usar; aquí el empleado ve Empleados,
  Mi plan, Apps, Sistema y Ajustes y las pantallas le recortan dentro (HUB_SHELL-F15).
- **Cierre por inactividad.** ¿Aviso con cuenta atrás antes de cerrar y una frase después? Hoy vuelve
  al pinpad sin decir nada (HUB_SHELL-F08).
- **Placa en el relevo de turno** (HUB_SHELL-F09).
- **PIN tras entrar desde el panel.** ¿Pedirlo también ahí, como tras el acceso con «Confiar»?
  (HUB_SHELL-F02, HUB_SHELL-F03).
- **La casilla «Confiar en este dispositivo».** Hacerla real (que el hub no confíe sin ella) o
  quitarla; hoy su ⓘ promete lo que no pasa.
- **Pantalla «Activación requerida».** Retirarla o volver a cablearla: hoy no se alcanza.

## Fuentes contrastadas

- `hub` HUB-F138 (servidor) dice que quien entra en el relevo teclea su PIN «o pasa su placa»: el
  relevo no acepta placa (HUB_SHELL-F09). Lo del historial del asistente ya casa: HUB-F138 dice que el
  relevo lo borra, como hace `src/lib/user-switch.ts` (`switchUser`, hub#1544).
- `hub` HUB-F132 dice que la pantalla pide el PIN tras entrar por primera vez con la cuenta en un
  dispositivo compartido; solo lo hace si se marcó «Confiar» y nunca al entrar por el pase del panel.
- `hub` HUB-F136 dice que el cierre por inactividad lo hace solo la pantalla: confirmado
  (`src/lib/idle-logout.ts`), y además sin aviso.
- `hub` y el manual (`hand-book/hub/01-acceso-y-navegacion.md`, «Pantalla de activación cuando el Hub
  no puede confirmar un acceso válido»): la pantalla «Activación requerida» no se alcanza nunca;
  `src/lib/entitlement.ts` solo pone `unknown` o `unlocked`, nunca `needs_activation`.
- Manual 01: «En móvil, las acciones secundarias se agrupan en **Más**»: el botón no tiene texto, es
  ⋮ con el nombre accesible «Más opciones».
- `es.ts` `login.popoverBody` («Si no la marcas, siempre tendrás que iniciar sesión con email») es
  falso: el hub vuelve de confianza el dispositivo en todo acceso con cuenta (HUB_SHELL-F01).
- `es.ts` `shell.changeHubBody` («Este dispositivo cerrará la sesión de este negocio…»): no la cierra
  (HUB_SHELL-F16).
- `es.ts` `notFound.body` dice que las apps «se abren desde el menú»: no están en el menú lateral,
  se abren desde el lanzador de la barra o desde Inicio.
