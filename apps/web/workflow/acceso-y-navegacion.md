# WORKFLOW — Hub · pantallas · Acceso, navegación y perfil

Prefijo: HUB_SHELL

> Detalle del área «Acceso, navegación y perfil» (oleada 3). Lo que la persona ve y hace para
> entrar, moverse por el hub y cuidar su perfil. Lo que decide el servidor (cuánto dura una sesión,
> cómo frena a quien prueba PIN, qué dispositivo es de confianza) está en `HUB`
> (`workflow/acceso.md`, HUB-F130…F144) y aquí solo se enlaza. Las pantallas que se citan en
> `Pantalla:` son las de `## Pantallas` del índice `apps/web/WORKFLOW.md`.

## Flujos

### HUB_SHELL-F01 Entrar con la cuenta de erplora.com
Estado: parcial — la pantalla no distingue «ya no eres miembro de este negocio» ni «un administrador te dio de baja» de unas credenciales erróneas: las tres dicen «No se pudo iniciar sesión. Revisa tus credenciales o la conexión.»
Actor: administrador, responsable, empleado
Pantalla: Acceso
Pasos:
1. Abre el hub sin sesión: sale **Acceso** con el logo del negocio y «Entra en tu negocio». Si el dispositivo ofrece PIN, arriba hay dos pestañas, «PIN» y «Email»; si no, solo el formulario.
2. Escribe «Email» y «Contraseña» (el ojo muestra la contraseña). En un dispositivo compartido sale marcada la casilla «Confiar en este dispositivo», con un botón ⓘ que explica «Acceso por PIN»; en uno marcado como personal, en su lugar, «Este dispositivo está configurado como personal: la sesión se queda abierta y nunca pide PIN. Un administrador puede cambiarlo en Ajustes › General.».
3. Pulsa «Entrar» (un círculo gira mientras trabaja). O pulsa «Continuar con Google»: el navegador va a erplora.com, que pide la cuenta de Google y vuelve al hub ya identificado.
4. Si la cuenta pide verificación, la tarjeta cambia a «Verifica que eres tú»: «Hemos enviado un código de un solo uso a tu email. Introdúcelo para continuar.». Escribe el «Código de verificación» y pulsa «Verificar»; «Volver» regresa al formulario.
5. Si confiaste el dispositivo y aún no tienes PIN, la pantalla te pide uno (HUB_SHELL-F03). Si no, entras en la pantalla que habías pedido o en **Inicio**.
Entra: el correo y la contraseña (o el código de Google), que comprueba erplora.com; el identificador del dispositivo; si el hub ofrece PIN aquí (modo del dispositivo, confianza y dial del negocio, los tres leídos del hub sin sesión).
Sale: pide a erplora.com la credencial y al hub la sesión local (`/api/auth/cloud`); guarda en este navegador la sesión, el nombre, el correo, el rol y los permisos de la persona, y los tokens de erplora.com. Con «Confiar» marcado apunta a la persona en la lista de caras de este navegador (con su correo).
Si falla: campos vacíos o correo sin «@»: «Introduce un email válido y tu contraseña.». Credenciales erróneas, persona dada de baja o que ya no es miembro: «No se pudo iniciar sesión. Revisa tus credenciales o la conexión.». Código erróneo o caducado: «Código incorrecto o caducado. Hemos enviado un código nuevo, inténtalo de nuevo.» (no vuelve a pedir la contraseña). Google que no termina: «No se pudo iniciar sesión con Google. Inténtalo de nuevo.». Hub sin registrar: HUB_SHELL-F12.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F130 (entrar con la cuenta de erplora.com)
Pendiente de enlazar: hub — HUB-F144 (cerrar la puerta a quien ya no es miembro)
Pendiente de enlazar: saas — inicio de sesión, código de verificación por correo y vuelta de Google al hub
QA: qa-hub-restaurant §7.02

### HUB_SHELL-F02 Entrar desde el panel de erplora.com sin volver a teclear la contraseña
Estado: parcial — quien entra así nunca ve el paso «Elige un PIN»: en una caja compartida tiene que ir a Mi perfil → PIN por su cuenta para poder entrar después con PIN
Actor: administrador, responsable, empleado
Pantalla: Acceso
Pasos:
1. En erplora.com la persona pulsa entrar en su negocio (o abre la app instalada, que pasa por el mismo sitio).
2. El hub abre con un pase escondido en la dirección; la pantalla lo quita de la barra de direcciones antes de nada y lo canjea mientras enseña el indicador de carga.
3. La persona aparece dentro, en **Inicio**, sin haber visto la pantalla de acceso.
Entra: el pase de un solo uso (como mucho 128 caracteres; si es más largo se descarta sin canjear) y el identificador del dispositivo.
Sale: la misma sesión y los mismos datos guardados que HUB_SHELL-F01, sin pasar por el formulario. Un fallo se apunta en el registro de errores del hub con el código, nunca con el pase.
Si falla: el acceso normal sale con el aviso «No se pudo entrar desde el panel de ERPlora» — «Inicia sesión aquí para continuar.», una sola vez. Si el canje tarda más de 10 segundos, la pantalla deja de esperarlo y sigue como si no hubiera pase.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F131 (canjear el pase de un solo uso)
Pendiente de enlazar: hub — HUB_APP, abrir el hub desde la app instalada con el pase del panel
Pendiente de enlazar: saas — puertas de entrada al hub con pase de un solo uso
QA: ninguno

### HUB_SHELL-F03 Elegir el PIN la primera vez que se entra en una caja
Estado: parcial — un PIN que ya usa otra persona sale como «No se pudo guardar el PIN. Vuelve a intentarlo.» sin decir el motivo (Mi perfil sí lo dice); solo se ofrece si se marcó «Confiar en este dispositivo», y recargar la página en este paso entra sin PIN
Actor: administrador, responsable, empleado
Pantalla: Acceso
Pasos:
1. Tras HUB_SHELL-F01 con «Confiar en este dispositivo», en un dispositivo compartido que pregunta y si la persona aún no tiene PIN, la tarjeta cambia a «Crea tu PIN de acceso».
2. Teclea el PIN en el teclado de círculos: «Elige un PIN de {n} dígitos» (4 o 6, lo que diga el negocio).
3. Repite: «Confirma tu PIN».
4. Al acertar la repetición se guarda y se entra. Desde ese momento la persona sale en la rejilla de caras de los dispositivos de confianza.
Entra: la sesión recién abierta; la longitud del PIN del negocio.
Sale: pide al hub fijar el PIN de quien tiene la sesión (`/api/auth/set-pin`). Si la persona ya tenía PIN, no se le pide otro y se conserva el suyo.
Si falla: repetición distinta: «Los PIN no coinciden, inténtalo de nuevo» y vuelve al primer paso. Dígitos repetidos o seguidos (1111, 1234): «Ese PIN es demasiado fácil de adivinar: evita dígitos repetidos (1111) y secuencias (1234).». Cualquier rechazo del hub: «No se pudo guardar el PIN. Vuelve a intentarlo.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F132 (elegir o cambiar el propio PIN)
QA: qa-hub-restaurant §7.02

### HUB_SHELL-F04 Entrar con PIN
Estado: hecho
Actor: responsable, empleado
Pantalla: Acceso
Pasos:
1. En un dispositivo compartido y de confianza cuyo negocio pide PIN, **Acceso** abre en la pestaña «PIN»: «Introduce tu PIN», «…o pasa tu placa: no hace falta elegir tu nombre antes.» y «Elige tu usuario» con una tarjeta por persona (cara con iniciales y nombre). Con una sola persona, ya sale elegida.
2. Toca tu nombre; sale tu cara y el teclado con tantos círculos como dígitos tenga el PIN del negocio. La flecha a la izquierda del 0 («Cambiar usuario») vuelve a la rejilla.
3. Teclea el PIN: entra solo al último dígito, sin botón.
4. Entras en la pantalla que habías pedido o en **Inicio**. El pie de la tarjeta dice «ERPlora · dispositivo de confianza».
Entra: la lista de personas con PIN y la longitud del PIN, que el hub sirve sin sesión; el nombre elegido y los dígitos.
Sale: pide al hub la sesión por PIN (`/api/auth/pin`) y guarda la sesión, el rol y los permisos. Funciona aunque erplora.com no responda.
Si falla: PIN erróneo: los círculos se vacían y debajo «PIN incorrecto». Dispositivo que nunca entró con una cuenta o que un administrador quitó: «En este dispositivo todavía no funciona el PIN. Entra una vez con tu cuenta aquí y a partir de entonces sí funcionará.». Navegador que no guarda datos (ventana privada): «Este navegador no puede recordar qué dispositivo es, así que aquí no se puede usar un PIN. Entra con tu cuenta, o permite que este sitio guarde datos y vuelve a intentarlo.». Demasiados intentos: «Demasiados intentos fallidos. Espera {minutes} minutos y vuelve a intentarlo.» (los minutos redondeados hacia arriba; sin dato, «Espera unos minutos»). Siempre queda «Email» para entrar con la cuenta.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F133 (entrar con PIN)
Pendiente de enlazar: hub — HUB-F135 (frenar a quien prueba PIN)
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
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F134 (entrar pasando la placa)
Pendiente de enlazar: hub — HUB_APP, lector NFC de Android
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
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F137 (perder la sesión porque se abrió en otro dispositivo)
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
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F136 (mantener la sesión abierta y cerrarla)
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
Si falla: con «Hasta cerrar sesión», en un dispositivo personal o sin sesión el vigilante no se arma. La persona no ve ningún mensaje de por qué volvió al pinpad.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F136 (el cierre por inactividad solo lo hace la pantalla)
Pendiente de enlazar: hub — HUB-F140 (decidir si el negocio pide PIN y tras cuántos minutos)
QA: ninguno

### HUB_SHELL-F09 Cambiar de usuario sin perder la venta
Estado: parcial — el relevo no acepta la placa, solo nombre y PIN (el acceso y la aprobación sí la aceptan)
Actor: responsable, empleado
Pantalla: Cambiar de usuario
Pasos:
1. En una caja compartida y de confianza cuyo negocio pide PIN, abre la tarjeta de usuario del menú y pulsa «Cambiar de usuario» (no sale en ningún otro caso).
2. Sobre la pantalla en curso se abre **Cambiar de usuario**: «La venta sigue abierta. A partir de ahora queda a nombre de quien entre aquí.» y «¿Quién se pone?» con una cara por persona.
3. Toca la tuya y teclea el PIN. La flecha («Otra persona») vuelve a las caras; «Cancelar» cierra sin cambiar nada.
4. Sale «Ahora atiende {name}»; la pantalla sigue donde estaba y lo siguiente queda a nombre de quien entró.
Entra: el nombre y el PIN de quien entra; la sesión de quien sale.
Sale: abre la sesión nueva por la misma puerta que HUB_SHELL-F04 y, solo cuando la tiene, cierra la anterior; olvida los tokens de erplora.com, el idioma, la apariencia y la conversación del asistente de quien se fue.
Si falla: PIN o nombre erróneos: «Esos datos no han funcionado. Revisa el nombre y el PIN, y vuelve a intentarlo.» y quien estaba dentro sigue dentro. Dispositivo sin dar de alta: «Este dispositivo todavía no está dado de alta para el PIN. Entra una vez con una cuenta de ERPlora en él y el PIN funcionará a partir de entonces.»; sin identificar: «Este dispositivo no ha podido identificarse. Recarga la página y vuelve a intentarlo.». Demasiados intentos: la frase de HUB_SHELL-F04. Si el hub aún no ha dado la lista de caras, se escribe «Su nombre» y se pulsa «Continuar».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F138 (cambiar de usuario sin perder la venta)
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
Sale: pide al hub borrar la sesión (sin esperar la respuesta) y borra de este navegador la sesión, los tokens de erplora.com, el perfil, la apariencia y el idioma personales, el plan resuelto y la conversación del asistente. La lista de caras y correos de este navegador se conserva.
Si falla: si el hub no contesta, la sesión local se borra igual y la del hub caduca sola.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F136 (cerrar la sesión en el hub)
QA: ninguno

### HUB_SHELL-F11 Decidir si este dispositivo es compartido o personal
Estado: parcial — el rechazo del hub se pinta con su texto en inglés y el identificador del dispositivo («this hub does not know the device …»)
Actor: administrador
Pantalla: Este dispositivo
Pasos:
1. Desde el propio dispositivo, abre **Ajustes → General**; bajo «Este dispositivo»: «Cómo pregunta este dispositivo quién lo está usando. Cada dispositivo del negocio se decide por separado.».
2. Elige «Compartido — una caja o tablet que usan varias personas» («Pide PIN al entrar y la olvida al acabar el turno, así que cada venta queda atribuida a quien la hizo.») o «Personal — un dispositivo que solo usas tú» («La sesión se queda abierta y nunca pide PIN…»).
3. La marca se mueve solo cuando el hub confirma; mientras guarda, las opciones se desactivan.
4. La pantalla de acceso de este dispositivo cambia en consecuencia: pinpad en compartido, solo cuenta en personal.
Entra: el dispositivo que hace la petición (nunca otro); la sesión de administrador.
Sale: pide al hub guardar el modo (`PUT /api/device/mode`); el acceso, el relevo y el vigilante de inactividad leen el modo confirmado.
Si falla: sin ser administrador las opciones salen desactivadas con «Solo un administrador puede cambiar cómo entra la gente en este dispositivo.». Error sin motivo: «No se pudo cambiar este dispositivo. Comprueba la conexión e inténtalo de nuevo.»; con motivo, el texto del hub tal cual.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F139 (marcar un dispositivo como compartido o personal)
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
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F160 (no abrir nada hasta que el hub esté registrado)
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
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F161 (decir si el hub está listo para servir)
QA: qa-hub-restaurant §7.16

### HUB_SHELL-F14 Seguir trabajando sin conexión
Estado: hecho
Actor: sistema
Pantalla: Franja de conexión
Pasos:
1. Con sesión abierta, la pantalla pregunta al hub si está ahí cada 30 segundos mientras la pestaña está a la vista.
2. Si el navegador dice que no hay red, sale bajo la barra la franja «Sin conexión a Internet» — «Lo que necesita Internet —cargar pantallas, sincronizar, enviar facturas— no va a funcionar hasta que vuelva. Este aviso desaparece solo.».
3. Si hay red pero el hub falla dos veces seguidas: «ERPlora no responde» — «Tu dispositivo parece tener conexión, pero ERPlora no contesta: puede ser tu Internet o un problema por nuestra parte…».
4. Al volver la conexión, la franja desaparece sola; no tiene botón.
Entra: el estado de red del navegador y la sonda de salud del hub.
Sale: nada guardado.
Si falla: la franja no sale en la pantalla de acceso. El reintento de lo que falló vive en cada pantalla, no en la franja.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F161 (la salud del hub que pregunta la sonda)
QA: qa-hub-restaurant §7.16

### HUB_SHELL-F15 Moverse por el menú lateral y la barra superior
Estado: parcial — el menú enseña Empleados, Mi plan, Apps, Sistema y Ajustes a todo el mundo; un empleado entra y es cada pantalla la que le esconde lo que no puede hacer
Actor: administrador, responsable, empleado
Pantalla: Menú lateral
Pasos:
1. En escritorio el menú está fijo a la izquierda; el botón de panel de la barra lo pliega a iconos («Colapsar menú» / «Expandir menú»). En tableta y móvil se abre con el botón de la barra («Abrir menú») y se cierra al elegir.
2. Menú «General»: Inicio, Empleados, Archivos. «Cuenta»: Mi plan, Apps, Sistema, API (solo si Ajustes tiene encendido «Mostrar documentación de la API») y Ajustes. La entrada en uso sale marcada.
3. Las apps instaladas no están en el menú: se abren con el lanzador de la barra («Mis apps», una baldosa por app y «Apps» al final) o desde **Inicio**.
4. La barra superior lleva el título de la pantalla, «Atrás» en las de detalle, el lanzador y, desde 768 px, «erplora.com», «Cambiar de negocio», «Asistente» y la campana; en el móvil esas acciones se pliegan en «Más opciones» (⋮) y el número de la campana viaja con él. Una barra fina bajo la barra indica que hay peticiones en curso.
Entra: la lista de apps que el hub sirve a esta persona (ya filtrada por sus permisos), si la API está publicada, la sesión.
Sale: nada guardado (el plegado del menú no se recuerda al recargar). Las pantallas del menú se descargan en segundo plano tras entrar, para que un toque no dependa de la red.
Si falla: una pantalla cuyo código no llega: «No se ha podido abrir esa sección. Revisa la conexión y vuelve a intentarlo.»; si al arrancar no llega nada: «ERPlora no ha podido terminar de abrirse» con «Reintentar». Una pantalla que falla por dentro: «No se ha podido abrir esa sección. Algo ha fallado dentro de ERPlora; vuelve a intentarlo.». Lanzador vacío: «Aquí aparecerán tus apps. Pulsa Apps para añadir las que necesite tu negocio.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F31 (servir el menú, las pantallas y los ficheros de las aplicaciones)
QA: BD-03

### HUB_SHELL-F16 Ir a erplora.com ya identificado
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Barra superior
Pasos:
1. Para gestionar el negocio: botón «erplora.com» de la barra («Gestiona tu negocio en erplora.com» en el menú del móvil). Solo lo ve quien administra el hub y entró con su cuenta (no con PIN).
2. Para cambiar de plan: «Actualizar plan» al pie del menú lateral, visible para todos.
3. erplora.com se abre en otra pestaña (en la app instalada, en el navegador del sistema) ya identificado, en la página pedida; ERPlora se queda donde estaba.
4. En la app instalada, «Cambiar de negocio» pregunta «¿Cambiar de negocio?» — «Este dispositivo cerrará la sesión de este negocio y mostrará tu lista de negocios.»; «Cambiar» olvida el negocio y abre la lista de erplora.com, «Cancelar» no hace nada.
Entra: la sesión (con cuenta), el permiso de administrar y la distribución de la app.
Sale: pide al hub un pase de un solo uso hacia erplora.com; si no lo da, abre el enlace normal, que pide la contraseña.
Si falla: «No se pudo abrir tu navegador. Entra en erplora.com para gestionar tu negocio.» o, para el plan, «…para gestionar tu plan.». En la copia de Google Play no salen ni «erplora.com» ni «Actualizar plan».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F142 (abrir erplora.com ya identificado)
Pendiente de enlazar: hub — HUB_APP, olvidar el negocio y abrir la lista de negocios
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
Si falla: sin sesión, cualquier dirección lleva a **Acceso**. Las direcciones retiradas `/export`, `/import` llevan a Ajustes › Datos y `/first-run` a Inicio.
Implicados: ninguno
QA: ninguno

### HUB_SHELL-F18 Poner la pantalla de una app a pantalla completa
Estado: hecho
Actor: empleado, responsable
Pantalla: Vista de un módulo
Pasos:
1. En una pantalla de app que lo ofrece (Vender, la Pantalla de cocina), elige «Pantalla completa» en su menú.
2. Desaparecen el menú lateral, la barra superior y las pestañas de abajo; en un navegador que lo permite, también la barra del navegador.
3. «Salir de pantalla completa» en el mismo menú, o Esc, lo devuelve. Salir de esa pantalla también.
Entra: la petición de la app; que su pestaña lo haya declarado en su `module.json` (`navigation[].chrome`), cosa que comprueba la vista de un módulo de este mismo documento.
Sale: nada guardado; no se recuerda al volver.
Si falla: si el navegador no deja ocupar la pantalla entera, igual se esconden las barras del hub. Las franjas de bloqueo y de conexión siguen a la vista.
Implicados: pendiente
Pendiente de enlazar: kitchen — KITCHEN-F10 (el modo pantalla completa del tablero de cocina)
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
Implicados: ninguno
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
Implicados: pendiente
Pendiente de enlazar: hub — HUB_APP, la versión instalada y su actualización
Pendiente de enlazar: hub — HUB-F167 (saber qué versión corre)
QA: ninguno

### HUB_SHELL-F21 Cambiar mis datos, foto, idioma y apariencia
Estado: parcial — el resumen de la cuenta se anuncia en inglés al lector de pantalla («Account summary»); si el perfil no carga, el formulario queda vacío y solo avisa «No se pudo cargar el perfil»
Actor: administrador, responsable, empleado
Pantalla: Mi perfil
Pasos:
1. Abre la tarjeta de usuario del menú y pulsa «Perfil».
2. En «Datos de la cuenta» cambia «Nombre», «Apellidos» o «Correo electrónico» y pulsa «Guardar mis datos»: «Perfil guardado».
3. «Cambiar foto» sube una JPG, PNG o WebP («Foto actualizada»); «Quitar» la borra.
4. En «Preferencias», «Idioma» («Usar el idioma del negocio», «Español», «English») y «Apariencia» (modo «Sistema (auto)», «Claro», «Oscuro» y la paleta) se guardan al elegir y se aplican al momento; «Usar la apariencia del negocio» deshace lo propio.
Entra: el perfil de quien tiene la sesión.
Sale: pide al hub guardar el perfil, las preferencias y la foto; el idioma y la apariencia siguen a la persona en cualquier dispositivo en el que entre.
Si falla: «No se pudo guardar el perfil»; foto rechazada: «No se pudo guardar la foto. Usa JPG, PNG o WebP de hasta 2 MB.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F143 (cambiar mis datos, idioma, apariencia y foto)
QA: ninguno

### HUB_SHELL-F22 Cambiar mi PIN desde Mi perfil
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Mi perfil
Pasos:
1. En **Mi perfil**, tarjeta «PIN»: «El PIN con el que entras en la caja. Cámbialo cuando quieras — no hace falta que lo haga nadie más.» (sin PIN: «Todavía no tienes un PIN. Establece uno para poder entrar también desde la caja.»).
2. Si ya tienes PIN, escribe «PIN actual».
3. Escribe «PIN nuevo» y «Repite el PIN nuevo» y pulsa «Cambiar PIN» (o «Establecer PIN»).
4. «PIN actualizado».
Entra: la sesión; la longitud del PIN del negocio.
Sale: pide al hub fijar el PIN propio (`/api/auth/set-pin`), con el actual si lo había.
Si falla: longitud distinta: «El PIN debe tener {n} dígitos.»; los dos no coinciden: «Los dos PIN no coinciden.»; fácil de adivinar: «Ese PIN se adivina a la primera…»; ya lo usa otra persona: «Ese PIN ya lo tiene otro usuario activo…»; actual erróneo: «Ese no es tu PIN actual. Escríbelo bien para poder fijar uno nuevo.». Otro fallo: «No se pudo guardar el perfil».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F132 (elegir o cambiar el propio PIN)
QA: ninguno

### HUB_SHELL-F23 Gestionar o borrar mi cuenta de erplora.com
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Mi perfil
Pasos:
1. Al pie de **Mi perfil**, «Gestión de la cuenta»: con cuenta de erplora.com, «Puedes editar aquí tus propios datos. Sigue siendo tu cuenta de erplora.com.» y los botones «Gestionar cuenta en erplora.com» y «Borrar mi cuenta»; sin ella, «Esta identidad pertenece solo a este negocio…» y ningún botón.
2. Pulsa uno: erplora.com se abre en el navegador, en la página de la cuenta o en la confirmación de borrado, sin el resto del panel.
3. El borrado lo confirma erplora.com, no el hub.
Entra: los tokens de erplora.com de la sesión.
Sale: con sesión abierta con la cuenta, un pase de un solo uso para entrar ya identificado; con PIN, el enlace normal, que pide la contraseña.
Si falla: «No se pudo abrir la página de tu cuenta en el navegador. Entra en erplora.com para gestionarla.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F142 (pase hacia la cuenta propia)
Pendiente de enlazar: saas — página de la cuenta y borrado de la cuenta
QA: L-17
