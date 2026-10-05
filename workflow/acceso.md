# WORKFLOW — Hub (servidor) · Entrar y sesiones

Prefijo: HUB

> Detalle del área «Acceso, personas y plan» (oleada 3): cómo entra una persona en el hub, cuánto
> dura su sesión, qué hace el hub con cada dispositivo y cómo frena a quien prueba credenciales. Lo
> que la persona ve (la pantalla de acceso, el pinpad, las tarjetas de Ajustes) es de `HUB_SHELL`;
> aquí está lo que el servidor decide. Cuentas, roles, llaves, plan y sistema siguen en
> `workflow/personas-y-permisos.md` y `workflow/plan-y-sistema.md`. Lo técnico vive en
> `architecture/hub/auth.md` (§2.3, §2.9 y siguientes) y no se repite.

## Flujos

### HUB-F130 Entrar con la cuenta de erplora.com
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: HUB_SHELL: Acceso
Pasos:
1. En la pantalla de acceso, la persona escribe su correo y su contraseña (o pulsa «Continuar con Google») y, si su cuenta lo pide, el código de verificación que le llega por correo. Ese paso lo resuelve erplora.com; el hub no ve nunca la contraseña.
2. Con la cuenta ya comprobada, el hub mira si esa persona es miembro de **este** negocio en erplora.com. Si lo es, la busca entre sus usuarios (primero por su cuenta, después por su correo) y, si no la encuentra, la da de alta con el rol de empleado.
3. Si en erplora.com es dueña o administradora del negocio, el hub le garantiza como mínimo el rol de administrador; nunca le baja el rol que ya tuviera.
4. Si la persona entró desde un dispositivo identificado, el hub lo apunta como dispositivo de confianza (a partir de ahí el PIN funciona en él) y le pone de nombre el del navegador («Chrome · Android») si aún no tenía.
5. Se abre la sesión y la persona entra en Inicio.
Entra: la credencial firmada que entrega erplora.com (JWT con la lista de negocios de los que es miembro y su rol en cada uno), comprobada sin conexión con la clave pública de erplora.com que el hub carga al arrancar (`HUB_JWT_PUBLIC_KEY` o `/api/v1/auth/public-key/`); el `device_id` del navegador o de la app.
Sale: la sesión (`hub_session`, credencial `cloud`), la persona enlazada o creada (`hub_user`), su correo en el perfil si estaba vacío, la fila de confianza del dispositivo (`hub_trusted_device`) y una línea de actividad de inicio de sesión. Esta entrada no gasta plaza del plan: la plaza de un miembro la controla erplora.com.
Si falla: sin credencial, `cloud_token_missing`; credencial caducada o no firmada por erplora.com, `cloud_token_invalid`; el hub no pudo cargar la clave pública al arrancar, `cloud_login_not_configured` (503) y solo funciona el PIN; quien ya no es miembro, `not_a_member` (y el hub le cierra la puerta, HUB-F144); a quien el administrador dio de baja en el hub, `user_deactivated`. La pantalla no tiene frase propia para estos dos últimos: dice «No se pudo iniciar sesión. Revisa tus credenciales o la conexión.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Acceso (formulario de correo, Google y código de verificación)
Pendiente de enlazar: saas — inicio de sesión, segundo factor y emisión del JWT con la membresía por negocio
QA: qa-hub-restaurant §7.02

### HUB-F131 Entrar desde el panel de erplora.com sin volver a teclear la contraseña
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: HUB_SHELL: Acceso
Pasos:
1. En erplora.com la persona pulsa entrar en su negocio (o abre la app instalada, que pasa por el mismo sitio).
2. El navegador llega al hub con un pase de un solo uso escondido en la dirección; el hub lo canjea con erplora.com usando su propia credencial de máquina.
3. Con lo que devuelve erplora.com, el hub sigue exactamente el camino de HUB-F130: comprueba la membresía, enlaza o crea a la persona, confía en el dispositivo y abre la sesión.
4. La persona aparece dentro sin haber visto la pantalla de acceso.
Entra: el pase (máximo 128 caracteres, un solo uso, vida de 120 s, atado a este negocio); la credencial de máquina del hub.
Sale: lo mismo que HUB-F130, más los tokens de erplora.com de la persona para que el shell los guarde.
Si falla: pase vacío o demasiado largo, `courier_invalid`; pase caducado, usado o de otro negocio, `courier_rejected`; erplora.com rechaza al hub o no contesta, `cloud_rejected`, `cloud_unreachable` o `cloud_unreadable` (424). La pantalla dice «No se pudo entrar desde el panel de ERPlora» con «Inicia sesión aquí para continuar.» y deja el acceso normal a mano.
Implicados: pendiente
Pendiente de enlazar: saas — puertas de entrada al hub con pase de un solo uso (entrar en mi negocio, abrir la app)
Pendiente de enlazar: hub — HUB_SHELL, Acceso (canje del pase al cargar)
QA: ninguno

### HUB-F132 Elegir o cambiar el propio PIN
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: HUB_SHELL: Mi perfil
Pasos:
1. Tras entrar por primera vez con la cuenta en un dispositivo compartido, la pantalla pide «Elige un PIN de {n} dígitos» y «Confirma tu PIN»; desde **Mi perfil → PIN** se cambia cuando se quiera.
2. Si la persona ya tenía PIN, escribe primero el actual.
3. Escribe el nuevo dos veces y lo guarda.
4. Desde ese momento el pinpad de los dispositivos de confianza le deja entrar con él.
Entra: la sesión de la persona (solo puede tocar su propio PIN); el número de dígitos del negocio (4 o 6).
Sale: el PIN guardado como huella (argon2id) en su ficha; el anterior deja de valer. No se avisa a erplora.com.
Si falla: PIN actual que no coincide, «Ese no es tu PIN actual. Escríbelo bien para poder fijar uno nuevo.»; dígitos repetidos o seguidos (1111, 1234), «Ese PIN se adivina a la primera…»; PIN que ya usa otra persona activa, «Ese PIN ya lo tiene otro usuario activo…»; longitud distinta de la del negocio, el aviso de dígitos. La ficha del dueño de la cuenta solo la cambia él (HUB-F148), pero esta puerta es la suya.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Acceso (alta del PIN tras el primer acceso) y Mi perfil (cambiar mi PIN)
QA: qa-hub-restaurant §7.02

### HUB-F133 Entrar con PIN
Estado: hecho
Actor: responsable, empleado
Pantalla: HUB_SHELL: Acceso
Pasos:
1. En un dispositivo compartido y de confianza, la pantalla de acceso enseña la rejilla de personas con PIN del negocio («Elige tu usuario»).
2. La persona toca su nombre y teclea su PIN; el teclado entra solo al último dígito.
3. El hub comprueba, por este orden: que esta dirección no esté frenada (HUB-F135), que el dispositivo sea de confianza, que ese nombre no esté frenado y que el PIN sea el de una persona activa.
4. Se abre la sesión y la persona entra.
Entra: el nombre, el PIN y el `device_id`; la lista pública de personas con PIN y la longitud del PIN, que el hub sirve sin sesión a la pantalla de acceso (nombre, rol e identificador, nunca el correo).
Sale: la sesión (`hub_session`, credencial `pin`), con su duración según el dispositivo y el negocio (HUB-F136); si el plan admite un solo dispositivo, cierra las sesiones de los demás (HUB-F137). El PIN se comprueba en el hub: funciona aunque erplora.com no responda.
Si falla: dispositivo que nunca entró con una cuenta o que un administrador quitó (no se distinguen), «En este dispositivo todavía no funciona el PIN. Entra una vez con tu cuenta aquí…»; navegador que no guarda datos, «Este navegador no puede recordar qué dispositivo es…»; nombre o PIN erróneos, «PIN incorrecto»; demasiados fallos, «Demasiados intentos fallidos. Espera {minutes} minutos…». Con el dial del negocio en «no mostrar pinpad» no hay rejilla y quien solo tiene PIN no puede entrar (HUB-F140).
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Acceso (rejilla de personas y pinpad)
QA: qa-hub-restaurant §7.02

### HUB-F134 Entrar pasando la placa
Estado: parcial — la lectura con tarjeta y tableta reales no está validada (pm#145); el lector USB y el NFC de Android solo se prueban con tests
Actor: responsable, empleado
Pantalla: HUB_SHELL: Acceso
Pasos:
1. En la pantalla de acceso de un dispositivo de confianza («…o pasa tu placa: no hace falta elegir tu nombre antes.»), la persona pasa su tarjeta por el lector o la acerca al NFC de la tableta.
2. El hub busca a quién pertenece esa tarjeta y comprueba los mismos frenos que con el PIN (dirección, dispositivo de confianza, intentos sobre esa tarjeta).
3. Se abre la sesión de su dueño.
Entra: el número que lee el lector (4 a 64 caracteres) y el `device_id`.
Sale: la sesión (credencial `badge`, con la referencia de la tarjeta, nunca su número). Los intentos fallidos se cuentan contra la tarjeta, no contra un nombre.
Si falla: tarjeta que no es de nadie o cuyo dueño está de baja, un único aviso, «Esa placa no abre nada aquí. Entra con tu PIN o pídeselo a un administrador.»; dispositivo sin confianza o freno, los mismos avisos que HUB-F133.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Acceso (captura de la ráfaga del lector) y HUB_APP (lector NFC de Android)
QA: ninguno

### HUB-F135 Frenar a quien prueba PIN o sesiones
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada PIN o placa erróneos cuentan contra ese nombre (o esa tarjeta): con 5 fallos seguidos, ese nombre queda bloqueado 5 minutos; un acierto pone la cuenta a cero.
2. Además, el hub cuenta por la dirección desde la que llegan: 20 PIN o placas erróneos en 15 minutos, sea cual sea el nombre, o 20 sesiones inventadas distintas, bloquean el PIN y la placa a toda esa dirección durante 15 minutos.
3. Quien ya tiene sesión abierta sigue trabajando: el bloqueo solo cierra las puertas de PIN y placa.
4. La aprobación con el PIN de un responsable (HUB-F152) cuenta en el mismo contador por nombre.
Entra: los rechazos de las puertas de PIN, placa y aprobación; la dirección del último salto del proxy.
Sale: la respuesta `too_many_attempts` (429) con los segundos que faltan; una línea de registro `event=auth_failed` por fallo (con la dirección y, para sesiones, una huella del token, nunca el token) para que el borde pueda banear. Los contadores viven en memoria: un reinicio los pone a cero.
Si falla: detrás de una misma dirección pública (CGNAT, wifi de un centro comercial) veinte fallos ajenos cierran el PIN a toda la tienda 15 minutos; se pasa solo. La pantalla lo dice con «Demasiados intentos fallidos. Espera {minutes} minutos y vuelve a intentarlo.».
Implicados: pendiente
Pendiente de enlazar: infra — vigilante del borde que lee `event=auth_failed` y banea (infra#338)
QA: qa-hub-restaurant §7.02

### HUB-F136 Mantener la sesión abierta y cerrarla
Estado: parcial — el cierre por inactividad lo hace solo la pantalla; el servidor no lo vigila y su única red es el tope de 1 h de «pedir siempre». No hay «cerrar todas mis sesiones»
Actor: administrador, responsable, empleado
Pantalla: HUB_SHELL: Acceso
Pasos:
1. Al entrar, la sesión dura lo más corto entre lo que permite el dispositivo y lo que pide el negocio: 12 horas en un dispositivo compartido, 30 días en uno personal, y como mucho 1 hora si el negocio pide el PIN siempre. Un cliente que no dice qué dispositivo es recibe la corta.
2. Mientras dura, cada petición la vuelve a comprobar; no se alarga con el uso.
3. Con «pedir siempre» y un dispositivo compartido, la pantalla cierra la sesión tras los minutos de inactividad que eligió el negocio (5 por defecto, de 1 a 30) y vuelve al pinpad.
4. «Cerrar sesión» borra la sesión en el hub al momento.
5. Una sesión de administrador es una sesión abierta por alguien con rol de administrador (o la grafía antigua «owner»); es la que piden los ajustes, el personal, las llaves, los dispositivos, el motor de automatizaciones y las métricas.
Entra: el token de sesión en la cabecera `X-Hub-Session`; el modo del dispositivo (HUB-F139) y el dial del negocio (HUB-F140).
Sale: la sesión con su caducidad; al cerrarla, la fila borrada y una línea de actividad de cierre. Dar de baja a la persona o quitar el dispositivo también borra sus sesiones (HUB-F149, HUB-F141).
Si falla: una sesión caducada, borrada o de una persona dada de baja recibe 401 en su siguiente petición, también desde la pantalla de un módulo; la pantalla dice «Tu sesión ha terminado: caducó o se abrió en otro dispositivo. Vuelve a entrar.» y lleva al acceso. La venta a medias no se pierde: sus líneas ya estaban guardadas.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, detector de inactividad y reacción única al 401
Pendiente de enlazar: flows — FLOWS-F01 (la sesión de administrador que exige el motor de automatizaciones)
QA: qa-hub-restaurant §7.02

### HUB-F137 Perder la sesión porque se abrió en otro dispositivo
Estado: hecho
Actor: sistema
Pantalla: HUB_SHELL: Acceso
Pasos:
1. El plan del negocio admite un solo dispositivo a la vez (el plan gratuito).
2. Alguien entra en otro dispositivo, con PIN, placa o cuenta.
3. El hub da por terminadas las sesiones de todos los demás dispositivos y apunta el motivo.
4. En el dispositivo desalojado, la siguiente acción lleva al acceso con «Sesión abierta en otro dispositivo» y «Tu plan cubre un dispositivo a la vez…», con la salida a ampliar el plan.
Entra: el número de dispositivos del plan, del último plan verificado (HUB-F162); sin plan verificado no hay límite.
Sale: las sesiones de los otros dispositivos caducadas con el motivo `device_limit`; el 401 de la puerta que sondea la pantalla lleva el código `session_evicted_device_limit`. Las sesiones del mismo dispositivo se conservan.
Si falla: si el hub no puede leer el motivo, el 401 sale sin él y la pantalla solo dice que la sesión terminó.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Acceso (aviso de sesión desalojada y salida a ampliar el plan)
Pendiente de enlazar: saas — número de dispositivos por plan en el permiso firmado
QA: ninguno

### HUB-F138 Cambiar de usuario sin perder la venta
Estado: hecho
Actor: responsable, empleado
Pantalla: HUB_SHELL: Cambiar de usuario
Pasos:
1. En un dispositivo compartido y de confianza, quien está en la caja abre «Cambiar de usuario» en su menú.
2. La persona que entra elige su nombre y teclea su PIN (o pasa su placa).
3. El hub abre la sesión de la nueva persona por la misma puerta que HUB-F133; solo cuando la tiene, la pantalla cierra la del anterior.
4. La venta sigue en pantalla y lo siguiente queda a nombre de quien entró («Ahora atiende {name}»).
Entra: el nombre y el PIN (o la placa) de quien entra; el token de quien sale.
Sale: una sesión nueva y la anterior borrada. La pantalla además olvida las credenciales de erplora.com de quien se fue.
Si falla: un PIN rechazado no cambia nada (quien estaba dentro sigue dentro): «Esos datos no han funcionado…». Dispositivo sin confianza: «Este dispositivo todavía no está dado de alta para el PIN…». El historial del asistente de quien se fue sigue en la pantalla (hub#1544).
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Cambiar de usuario (la rejilla sobre la venta y el relevo de credenciales)
QA: qa-hub-restaurant §7.02, L-13 (discrepa)

### HUB-F139 Marcar un dispositivo como compartido o personal
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Ajustes
Pasos:
1. Desde el propio dispositivo, el administrador abre **Ajustes → General → Este dispositivo**.
2. Elige «Compartido — una caja o tablet que usan varias personas» o «Personal — un dispositivo que solo usas tú»; cada opción dice debajo su consecuencia.
3. El hub guarda la decisión en la ficha de confianza de ese dispositivo.
4. En compartido, la pantalla de acceso ofrece pinpad y la sesión dura un turno; en personal, no hay pinpad y la sesión dura 30 días.
Entra: el dispositivo (el que hace la petición, o uno nombrado); la sesión de administrador.
Sale: el modo, quién y cuándo lo cambió. La pantalla de acceso lo lee sin sesión junto con el dial del negocio y si el dispositivo es de confianza. Un dispositivo desconocido, ilegible o sin identificar se trata siempre como compartido. Entrar otra vez con la cuenta no pisa el modo.
Si falla: un dispositivo en el que nadie entró nunca con una cuenta no se puede marcar (`hub.device.unknown_device`); sin ser administrador, «Solo un administrador puede cambiar cómo entra la gente en este dispositivo.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Ajustes › General › Este dispositivo
QA: qa-hub-restaurant §7.02

### HUB-F140 Decidir si el negocio pide PIN y cuántos dígitos tiene
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Ajustes
Pasos:
1. El administrador abre **Ajustes → General → Pinpad**.
2. Enciende o apaga «Mostrar pinpad» y elige «Volver a preguntar tras inactividad» (1, 5, 10, 15 o 30 minutos, o «Hasta cerrar sesión»); en «Dígitos del PIN», 4 o 6.
3. Guarda.
4. Vale para todo el negocio y se combina con el modo de cada dispositivo: gana siempre lo más estricto.
Entra: la sesión de administrador.
Sale: los ajustes del negocio `pin_policy` (`always`, `per_shift` o `never`), `pin_inactivity_minutes` y `pin_length`, con quién los cambió. «No mostrar pinpad» nunca alarga la sesión de un dispositivo compartido: renuncia a saber quién vende, no al candado. Los PIN de la otra longitud siguen funcionando hasta que su dueño los cambia.
Si falla: un valor fuera de lo permitido se rechaza (422); sin ser administrador, «Solo un administrador puede cambiar si se pregunta.». Un valor guardado que no se entiende vuelve al de fábrica (`per_shift`, 5 minutos, 4 dígitos), nunca a «no preguntar».
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Ajustes › General › Pinpad
Pendiente de enlazar: hub — HUB, negocio y datos (los ajustes del negocio y su puerta de escritura)
QA: ninguno

### HUB-F141 Ver, nombrar y quitar los dispositivos del negocio
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Ajustes
Pasos:
1. El administrador abre **Ajustes → General → Dispositivos**: cada dispositivo en el que alguien entró con su cuenta, con su nombre, quién entró la última vez, cuándo se usó y si su sesión sigue abierta.
2. Para reconocerlo, le pone nombre («Barra», «Portátil del despacho», hasta 60 caracteres).
3. Si se pierde uno, pulsa «Quitar este dispositivo» y confirma: su sesión se cierra al momento y deja de poder entrar con PIN.
4. Con «Quitar los {n} dispositivos sin usar desde hace 30 días» limpia de golpe los que nadie usa; el que tiene en la mano nunca cuenta.
Entra: la sesión de administrador; el dispositivo desde el que pregunta.
Sale: el nombre del dispositivo; al quitarlo, sus sesiones borradas y su confianza retirada (con ella, el modo personal). Quitar el propio dispositivo cierra la sesión de quien lo hace. Volver a entrar con una cuenta lo hace de confianza otra vez: se corta el dispositivo, no la persona.
Si falla: «Ese dispositivo ya no está registrado aquí. Actualiza la lista.»; nombre largo, «Ese nombre es demasiado largo…»; sin ser administrador, «Solo el propietario o un administrador puede gestionar los dispositivos.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Ajustes › General › Dispositivos
QA: ninguno

### HUB-F142 Abrir erplora.com ya identificado
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: HUB_SHELL: Mi perfil
Pasos:
1. Quien entró con su contraseña pulsa «Gestionar cuenta en erplora.com», «Actualizar plan» o «Borrar mi cuenta».
2. El hub comprueba que la sesión se abrió con la cuenta (no con un PIN), que la credencial de erplora.com que presenta es de la misma persona y, salvo para su propia cuenta, que es administradora.
3. Pide a erplora.com un pase de un solo uso a nombre de esa persona y devuelve la dirección.
4. El navegador del sistema abre erplora.com ya identificado, en la página pedida.
Entra: la sesión, la credencial de erplora.com de la persona y el destino (solo rutas propias de erplora.com).
Sale: la dirección con el pase; nada guardado en el hub.
Si falla: sesión de PIN, `handoff_requires_cloud_login`; sin ser administrador para un destino de gestión, `handoff_requires_administer`; credencial de otra persona, `handoff_identity_mismatch`; destino no permitido, `handoff_destination_not_allowed`. En todos los casos la pantalla abre el enlace normal de erplora.com, que pide la contraseña.
Implicados: pendiente
Pendiente de enlazar: saas — emitir y canjear el pase de un solo uso hacia el panel
Pendiente de enlazar: hub — HUB_SHELL, puerta compartida a erplora.com (Mi perfil, Mi plan, Actualizar plan)
QA: L-17

### HUB-F143 Cambiar mis datos, idioma, apariencia y foto
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: HUB_SHELL: Mi perfil
Pasos:
1. La persona abre **Mi perfil**.
2. Cambia su nombre y apellidos, su correo de contacto, su idioma («Usar el idioma del negocio» o uno propio), su apariencia o su foto.
3. Pulsa «Guardar mis datos»: «Perfil guardado».
4. El idioma y la apariencia la siguen en cualquier dispositivo en el que entre.
Entra: la sesión (el perfil siempre es el de quien la tiene; no se puede pedir el de otro).
Sale: el perfil (`hub_user_profile`) y las preferencias (`hub_user_pref`); la foto en el almacén del hub. El correo del perfil es solo de contacto: el correo con el que entra y con el que erplora.com la reconoce lo cambia un administrador (HUB-F148). Nombre y apellidos hasta 150 caracteres; idioma español o inglés.
Si falla: «No se pudo guardar el perfil»; foto que no es JPG, PNG o WebP o pasa de 2 MB, «No se pudo guardar la foto. Usa JPG, PNG o WebP de hasta 2 MB.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Mi perfil
QA: ninguno

### HUB-F144 Cerrar la puerta a quien ya no es miembro en erplora.com
Estado: parcial — el hub solo se entera cuando esa persona vuelve a intentar entrar con su cuenta: erplora.com no avisa al quitar la membresía, así que hasta entonces su sesión, su PIN y su placa siguen funcionando
Actor: sistema
Pantalla: ninguna
Pasos:
1. Alguien a quien quitaron del negocio en erplora.com intenta entrar con su cuenta.
2. El hub ve que la credencial ya no lo nombra miembro de este negocio.
3. Antes de rechazarlo, lo da de baja en el hub y borra sus sesiones: deja de aparecer en el pinpad y su PIN y su placa dejan de servir.
4. Si más adelante vuelve a ser miembro, su próximo acceso con la cuenta lo reincorpora en la misma ficha, con el rol que le dé la membresía de ese día.
Entra: la credencial de erplora.com sin este negocio en su lista.
Sale: la ficha desactivada y marcada como cerrada por erplora.com (`cloud_revoked_at`), sus sesiones borradas; respuesta `not_a_member`. Una baja hecha por el administrador del hub no se deshace así: esa persona recibe `user_deactivated` hasta que la reincorporen (HUB-F149).
Si falla: si la baja local no se puede escribir, queda en el registro de errores y el acceso se rechaza igual.
Implicados: pendiente
Pendiente de enlazar: saas — quitar a un miembro del negocio
QA: ninguno
