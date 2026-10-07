# WORKFLOW — Hub (servidor) · Entrar y sesiones

Prefijo: HUB

> **Para qué sirve el área «Acceso, personas y plan».** El servidor del hub decide quién entra y
> cómo: con la cuenta de erplora.com (la contraseña y el segundo factor los resuelve erplora.com; el
> hub comprueba la credencial firmada y la membresía de **este** negocio), con un PIN o pasando una
> placa en un dispositivo de confianza, y cuánto dura la sesión según el dispositivo (compartido o
> personal) y lo que pide el negocio. Guarda las cuentas del personal (locales con PIN o con cuenta e
> invitación de erplora.com), sus roles y lo que cada rol puede, aprueba una acción con el PIN de un
> responsable sin cerrar la sesión del cajero, aplica las normas que escribe el dueño y emite llaves
> para sistemas externos. Comprueba su plan firmado (apps permitidas, plazas de personas y
> dispositivos) y sigue funcionando sin conexión dentro de su gracia, manda el latido de uso, habla
> con erplora.com en nombre del negocio sin enseñar nunca su credencial de máquina, y cuenta su
> propia salud (listo para servir, recursos, versión, actualizaciones). Lo usan el **administrador**
> (personal, roles, llaves, dispositivos, PIN del negocio, métricas), el **responsable** (aprobar con
> su PIN) y todos los perfiles (entrar, su perfil, su PIN); el resto lo hace el **sistema** solo. Lo
> que vale para toda el área (sus tablas, lo que vive en memoria, la referencia) está al final de
> este fichero.
>
> Detalle del área «Acceso, personas y plan» (oleada 3): cómo entra una persona en el hub, cuánto
> dura su sesión, qué hace el hub con cada dispositivo y cómo frena a quien prueba credenciales. Lo
> que la persona ve (la pantalla de acceso, el pinpad, las tarjetas de Ajustes) es de `HUB_SHELL`;
> aquí está lo que el servidor decide. Cuentas, roles, llaves, plan y sistema siguen en
> `workflow/personas-y-permisos.md` y `workflow/plan-y-sistema.md`. Lo técnico vive en
> `architecture/hub/auth.md` (§2.3, §2.9 y siguientes) y no se repite.

## Referencia adoptada

La de toda el área está contrastada en `architecture/hub/auth.md` (decisiones de
mercado ya tomadas con referencias) y en `.claude/agents/qa-hub-restaurant.md` §2/§6. La de cuentas,
aprobaciones, normas y llaves está en [personas-y-permisos.md](personas-y-permisos.md); la del plan,
en [plan-y-sistema.md](plan-y-sistema.md). Para entrar y las sesiones se adopta esto:

- **Acceso con PIN en dispositivo compartido, rejilla de caras y relevo sin cerrar la venta**:
  Square (Team passcodes), Toast (employee passcodes, «switch user» como capa sobre la app). PIN de
  longitud **fija por negocio, 4 o 6**, que entra solo al último dígito: modelo de Clover (hub#974).
- **Placa (RFID/NFC/banda) como presentación de la misma identidad, nunca sustituta del PIN**:
  Toast, Aloha/NCR, Square, Lightspeed (ADR-0347, 15 referencias). Nadie da de alta su propia placa
  (Toast).
- **Lista de dispositivos con «quitar este dispositivo» y limpieza de los no usados en 30 días**:
  pantallas de cuenta de Google, Apple, Microsoft y Shopify (ADR-0258, hub#2215).

## Antes de empezar

- La primera persona entra con su cuenta de erplora.com (HUB-F130) desde la aplicación instalada:
  ese primer acceso hace al dispositivo **de confianza** y es su alta; sin él, en ese dispositivo no
  funciona el PIN (HUB-F133).
- Cada persona elige su PIN propio (HUB-F132). En **Ajustes › General** se decide si cada dispositivo
  es compartido o personal (HUB-F139), si el negocio pide PIN y cuántos dígitos tiene (HUB-F140).
- El personal se da de alta en [personas-y-permisos.md](personas-y-permisos.md) (HUB-F145 a HUB-F150).

## Flujos

### HUB-F130 Entrar con la cuenta de erplora.com
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: HUB_SHELL: Acceso
Pasos:
1. En la pantalla de acceso, la persona escribe su correo y su contraseña (o pulsa «Continuar con Google») y, si su cuenta tiene la verificación en dos pasos, el código de su app autenticadora o uno de sus códigos de recuperación (erplora.com no manda nada por correo: contesta `delivered: false`). Ese paso lo resuelve erplora.com; el hub no ve nunca la contraseña.
2. Con la cuenta ya comprobada, el hub mira si esa persona es miembro de **este** negocio en erplora.com. Si lo es, la busca entre sus usuarios (primero por su cuenta de erplora.com, después por su correo de acceso, comparado **letra a letra, mayúsculas incluidas**) y, si no la encuentra, la da de alta con el rol por defecto del despliegue (`HUB_DEFAULT_ROLE`; empleado si no se dice).
3. Si en erplora.com es dueña o administradora del negocio, el hub le garantiza como mínimo el rol de administrador; nunca le baja el rol que ya tuviera.
4. Si la persona entró desde un dispositivo identificado, el hub lo apunta como dispositivo de confianza (a partir de ahí el PIN funciona en él) y le pone de nombre el del navegador («Chrome · Android») si aún no tenía. La casilla «Confiar en este dispositivo» de la pantalla no interviene: el hub lo marca siempre que llega el identificador del dispositivo.
5. Se abre la sesión y la persona entra en Inicio.
Entra: la credencial firmada que entrega erplora.com (JWT con la lista de negocios de los que es miembro y su rol en cada uno), comprobada sin conexión con la clave pública de erplora.com que el hub carga al arrancar (`HUB_JWT_PUBLIC_KEY` o `/api/v1/auth/public-key/`); el `device_id` del navegador o de la app.
Sale: la sesión (`hub_session`, credencial `cloud`), la persona enlazada o creada (`hub_user`), su correo en el perfil si estaba vacío, la fila de confianza del dispositivo (`hub_trusted_device`) y una línea de actividad de inicio de sesión. Esta entrada no gasta plaza del plan: la plaza de un miembro la controla erplora.com. Si el correo del token difiere solo en mayúsculas del que se escribió al invitar, el hub crea una **segunda** ficha (sin pasar por el tope de plazas) y la invitada queda sin enlazar (ver huecos).
Si falla: sin credencial, `cloud_token_missing`; credencial caducada o no firmada por erplora.com, `cloud_token_invalid`; el hub no pudo cargar la clave pública al arrancar, `cloud_login_not_configured` (503) y solo funciona el PIN; quien ya no es miembro, `not_a_member` (y el hub le cierra la puerta, HUB-F144); a quien el administrador dio de baja en el hub, `user_deactivated`. La pantalla no tiene frase propia para estos dos últimos: dice «No se pudo iniciar sesión. Revisa tus credenciales o la conexión.». Si erplora.com acepta la contraseña y el hub rechaza la entrada, la pantalla no deja guardados los tokens de erplora.com (HUB_SHELL-F01, hub#2506).
Implicados: HUB_SHELL-F01, SAAS_AUTH-F16, SAAS_AUTH-F17, SAAS_AUTH-F20, SAAS_AUTH-F29, SAAS_DASHBOARD-F13, SAAS_DASHBOARD-F15
QA: qa-hub-restaurant §7.02

### HUB-F131 Entrar desde el panel de erplora.com sin volver a teclear la contraseña
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: HUB_SHELL: Acceso
Pasos:
1. En erplora.com la persona pulsa entrar en su negocio (o abre la app instalada, que pasa por el mismo sitio).
2. El navegador llega al hub con un pase de un solo uso escondido en la dirección; el hub lo canjea con erplora.com usando su propia credencial de máquina.
3. Con lo que devuelve erplora.com, el hub sigue exactamente el camino de HUB-F130: comprueba la membresía, enlaza o crea a la persona y abre la sesión. Solo cuando se entra desde la aplicación instalada confía además en el dispositivo; desde el navegador, este paso no lo da de alta para el PIN.
4. La persona aparece dentro sin haber visto la pantalla de acceso.
Entra: el pase (máximo 128 caracteres, un solo uso, vida de 120 s, atado a este negocio); la credencial de máquina del hub.
Sale: lo mismo que HUB-F130, más los tokens de erplora.com de la persona para que el shell los guarde.
Si falla: pase vacío o demasiado largo, `courier_invalid`; pase caducado, usado o de otro negocio, `courier_rejected`; erplora.com rechaza al hub o no contesta, `cloud_rejected`, `cloud_unreachable` o `cloud_unreadable` (424). La pantalla dice «No se pudo entrar desde el panel de ERPlora» con «Inicia sesión aquí para continuar.» y deja el acceso normal a mano.
Implicados: HUB_SHELL-F02, REC_ALTA-F07, SAAS_AUTH-F19, SAAS_DASHBOARD-F04, SAAS_DASHBOARD-F06, SAAS_DASHBOARD-F07
QA: ninguno

### HUB-F132 Elegir o cambiar el propio PIN
Estado: parcial — el freno de 30 intentos por hora no para a quien va despacio (29 cada hora no bloquean nunca, unos 700 al día) y los intentos no dejan rastro: con tiempo se sigue pudiendo averiguar el PIN de otra persona (ERPlora/hub#2526)
Actor: administrador, responsable, empleado
Pantalla: HUB_SHELL: Mi perfil
Pasos:
1. Tras entrar por primera vez con la cuenta en un dispositivo compartido, la pantalla pide «Elige un PIN de {n} dígitos» y «Confirma tu PIN» solo si la persona no tenía PIN, marcó «Confiar en este dispositivo» y el negocio pregunta por el PIN; nunca tras entrar desde el panel de erplora.com. Desde **Mi perfil → PIN** se cambia cuando se quiera.
2. Si la persona ya tenía PIN, escribe primero el actual.
3. Escribe el nuevo dos veces y lo guarda.
4. Desde ese momento el hub le deja entrar con él en los dispositivos de confianza; la rejilla del pinpad no la enseña hasta que se recarga la pantalla.
Entra: la sesión de la persona (solo puede tocar su propio PIN); el número de dígitos del negocio (4 o 6).
Sale: el PIN guardado como huella (argon2id) en su ficha; el anterior deja de valer. No se avisa a erplora.com. Como el PIN es único, el rechazo «ya lo tiene otro usuario activo» dice que ese número es de alguien; por eso esta puerta gasta un presupuesto de intentos por persona (ERPlora/hub#2499): 30 por hora contados desde el primero, también los que se aceptan, y agotado no mira el número durante una hora. Es el mismo presupuesto que gastan el alta y la edición de personas con PIN en Empleados (HUB-F145, HUB-F148, ERPlora/hub#2518): uno por persona entre las tres puertas, del tamaño de una plantilla entera dada de alta seguida, y que a quien prueba números le deja menos intentos al día que los 5 en 5 minutos de la entrada (ERPlora/hub#2564).
Si falla: PIN actual que no coincide, «Ese no es tu PIN actual. Escríbelo bien para poder fijar uno nuevo.»; dígitos repetidos o seguidos (1111, 1234), «Ese PIN se adivina a la primera…»; PIN que ya usa otra persona activa, «Ese PIN ya lo tiene otro usuario activo…»; longitud distinta de la del negocio, el aviso de dígitos; con los 30 intentos de la hora gastados, «Demasiados intentos de cambiar el PIN. Espera {minutes} minutos y vuelve a intentarlo.» (429 `too_many_attempts`), sin decir si el número estaba libre. La ficha del dueño de la cuenta solo la cambia él (HUB-F148), pero esta puerta es la suya.
Implicados: HUB_SHELL-F03, HUB_SHELL-F22, HUB_SHELL-F85
QA: qa-hub-restaurant §7.02

### HUB-F133 Entrar con PIN
Estado: parcial — las bajas siguen saliendo en la rejilla hasta recargar
Actor: responsable, empleado
Pantalla: HUB_SHELL: Acceso
Pasos:
1. En un dispositivo compartido y de confianza, la pantalla de acceso enseña la rejilla de personas con PIN del negocio («Elige tu usuario»).
2. La persona toca su nombre y teclea su PIN; el teclado entra solo al último dígito.
3. El hub comprueba, por este orden: que esta dirección no esté frenada (HUB-F135), que el dispositivo sea de confianza, que ese nombre no esté frenado y que el PIN sea el de una persona activa.
4. Se abre la sesión y la persona entra.
Entra: el nombre, el PIN y el `device_id`; la lista de personas con PIN y la longitud del PIN, que el hub da en su contexto a la pantalla de acceso (nombre, rol e identificador, nunca el correo; la misma respuesta lleva el identificador del negocio). La lista solo llega a quien el PIN dejaría pasar, preguntado en el mismo orden: una sesión viva (aprobación y cambio de usuario; una sesión inventada cuenta contra la dirección como en cualquier puerta, HUB-F135); si no, una dirección no frenada y un dispositivo de confianza (o el freno de dispositivos apagado, o el primero de una demo virgen). A cualquier otro el hub le contesta igual, pero con la lista vacía: el resto del contexto (moneda, idioma, zona, longitud del PIN) no nombra a nadie (ERPlora/hub#2510). El identificador del negocio sigue llegando a todos: erplora.com lo lee sin credencial para comprobar que un dominio propio llega a este hub, y no es un secreto (la importación que se fiaba de él se arregla en ERPlora/hub#2497). En una demo (`HUB_DEMO`) sin ningún dispositivo de confianza, el primero que manda un PIN queda adoptado.
Sale: la sesión (`hub_session`, credencial `pin`), con su duración según el dispositivo y el negocio (HUB-F136); si el plan admite un solo dispositivo, cierra las sesiones de los demás (HUB-F137). El PIN se comprueba en el hub: funciona aunque erplora.com no responda.
Si falla: dispositivo que nunca entró con una cuenta o que un administrador quitó (no se distinguen), «En este dispositivo todavía no funciona el PIN. Entra una vez con tu cuenta aquí…»; navegador que no guarda datos, «Este navegador no puede recordar qué dispositivo es…»; nombre o PIN erróneos, «PIN incorrecto»; demasiados fallos, «Demasiados intentos fallidos. Espera {minutes} minutos…». Con el dial del negocio en «no mostrar pinpad» no hay rejilla y quien solo tiene PIN no puede entrar (HUB-F140).
Implicados: HUB_SHELL-F04, REC_ALTA-F16, SAAS_PUBLIC-F80, SAAS_PUBLIC-F83
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
Implicados: HUB_APP-F23, HUB_SHELL-F05, HUB_SHELL-F87
QA: ninguno

### HUB-F135 Frenar a quien prueba PIN o sesiones
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Cada PIN o placa erróneos cuentan contra ese nombre (o esa tarjeta): con 5 fallos seguidos, ese nombre queda bloqueado 5 minutos; un acierto pone la cuenta a cero.
2. Además, el hub cuenta por la dirección desde la que llegan: 20 PIN o placas erróneos en 15 minutos, sea cual sea el nombre, o 20 sesiones inventadas distintas, bloquean el PIN y la placa a toda esa dirección durante 15 minutos; mientras dura, la lectura del contexto tampoco le da la lista de caras (HUB-F133). Una sesión inventada presentada en esa lectura cuenta igual; la misma sesión caducada repetida (una caja que arranca cada mañana) cuenta una sola vez.
3. Quien ya tiene sesión abierta sigue trabajando: el bloqueo solo cierra las puertas de PIN y placa.
4. La aprobación con el PIN de un responsable (HUB-F152) cuenta en el mismo contador por nombre, pero **no** pasa por el freno por dirección (ni lo consulta ni le suma fallos); con placa, la aprobación cuenta contra el número leído y el acceso contra su índice, así que son dos contadores para la misma tarjeta. El cambio del propio PIN (HUB-F132), y el alta y la edición con PIN de Empleados (HUB-F145, HUB-F148), tienen su propio presupuesto por persona (no por nombre ni por dirección): 30 intentos por hora contados desde el primero, cuentan también los aceptados (un PIN aceptado también informa) y entrar bien con el PIN no lo pone a cero.
Entra: los rechazos de las puertas de PIN y placa (y, solo por nombre, de la aprobación) y las sesiones que no resuelven en la lectura del contexto (HUB-F133); la dirección del último salto del proxy (`X-Forwarded-For`); sin esa cabecera no hay freno por dirección.
Sale: la respuesta `too_many_attempts` (429) con los segundos que faltan; una línea de registro `event=auth_failed` por fallo (con la dirección y, para sesiones, una huella del token, nunca el token) para que el borde pueda banear. Los contadores viven en memoria: un reinicio los pone a cero.
Si falla: detrás de una misma dirección pública (CGNAT, wifi de un centro comercial) veinte fallos ajenos cierran el PIN a toda la tienda 15 minutos; se pasa solo. La pantalla lo dice con «Demasiados intentos fallidos. Espera {minutes} minutos y vuelve a intentarlo.».
Implicados: HUB_SHELL-F04
Pendiente de enlazar: infra — vigilante del borde que lee `event=auth_failed` y banea (infra#338)
QA: qa-hub-restaurant §7.02

### HUB-F136 Mantener la sesión abierta y cerrarla
Estado: parcial — el cierre por inactividad lo hace solo la pantalla; el servidor no lo vigila y su única red es el tope de 1 h de «pedir siempre». No hay «cerrar todas mis sesiones»
Actor: administrador, responsable, empleado
Pantalla: HUB_SHELL: Acceso
Pasos:
1. Al entrar, la sesión dura lo más corto entre lo que permite el dispositivo y lo que pide el negocio: 12 horas en un dispositivo compartido, 30 días en uno personal, y como mucho 1 hora si el negocio pide el PIN siempre. Un cliente que no dice qué dispositivo es recibe la corta.
2. La caducidad se fija al **abrir** la sesión: mientras dura, cada petición la vuelve a comprobar, no se alarga con el uso, y cambiar después el modo del dispositivo o el dial del negocio no acorta las sesiones ya abiertas.
3. Con «pedir siempre» y un dispositivo compartido, la pantalla cierra la sesión tras los minutos de inactividad que eligió el negocio (5 por defecto, de 1 a 30) y vuelve al pinpad.
4. «Cerrar sesión» borra la sesión en el hub al momento.
5. Una sesión de administrador es una sesión abierta por alguien con rol de administrador (o la grafía antigua «owner»); es la que piden los ajustes, el personal, las llaves, los dispositivos, el motor de automatizaciones y las métricas.
Entra: el token de sesión en la cabecera `X-Hub-Session`; el modo del dispositivo (HUB-F139) y el dial del negocio (HUB-F140).
Sale: la sesión con su caducidad; al cerrarla, la fila borrada y una línea de actividad de cierre. Dar de baja a la persona o quitar el dispositivo también borra sus sesiones (HUB-F149, HUB-F141). De esa caducidad dependen además: la lista de dispositivos («sesión abierta», último uso) y su limpieza de 30 días (HUB-F141), el recuento de dispositivos con sesión del latido (HUB-F164) y de Plan y límites (HUB-F165), la cookie de las fotos (es el mismo token) y el plazo en que sigue viva la sesión de quien se quitó en erplora.com (HUB-F144). Cambiar la duración obliga a revisar esos flujos.
Si falla: una sesión caducada, borrada o de una persona dada de baja recibe 401 en su siguiente petición, también desde la pantalla de un módulo; la pantalla dice «Tu sesión ha terminado: caducó o se abrió en otro dispositivo. Vuelve a entrar.» y lleva al acceso. La venta a medias no se pierde: sus líneas ya estaban guardadas.
Implicados: FLOWS-F01, HUB_SHELL-F07, HUB_SHELL-F08, HUB_SHELL-F10, HUB_SHELL-F195, SAAS_AUTH-F10, SAAS_AUTH-F12, SAAS_AUTH-F18
QA: qa-hub-restaurant §7.02

### HUB-F137 Perder la sesión porque se abrió en otro dispositivo
Estado: hecho
Actor: sistema
Pantalla: HUB_SHELL: Acceso
Pasos:
1. El plan del negocio admite un solo dispositivo a la vez (el plan gratuito). Ese tope lo pone erplora.com en el permiso firmado, y en erplora.com ninguna migración lo escribe: solo el comando manual `sync_hub_plans`; si no se ha ejecutado, el gratuito llega sin tope y nadie es desalojado.
2. Alguien entra en otro dispositivo, con PIN, placa o cuenta.
3. El hub da por terminadas las sesiones de todos los demás dispositivos y apunta el motivo.
4. En el dispositivo desalojado, la siguiente acción lleva al acceso con «Sesión abierta en otro dispositivo» y «Tu plan cubre un dispositivo a la vez…», con la salida a ampliar el plan.
Entra: el número de dispositivos del plan, del último plan verificado (HUB-F162); sin plan verificado no hay límite, y un acceso que no dice qué dispositivo es (el acceso con cuenta no lo exige) no desaloja a nadie: solo el siguiente acceso que sí lo dice desaloja a todos los demás.
Sale: las sesiones de los otros dispositivos caducadas con el motivo `device_limit`; el 401 de la puerta que sondea la pantalla lleva el código `session_evicted_device_limit`. Las sesiones del mismo dispositivo se conservan.
Si falla: si el hub no puede leer el motivo, el 401 sale sin él y la pantalla solo dice que la sesión terminó.
Implicados: HUB_APP-F06, HUB_SHELL-F06, SAAS_DASHBOARD-F59, SAAS_DASHBOARD-F206
QA: ninguno

### HUB-F138 Cambiar de usuario sin perder la venta
Estado: hecho
Actor: responsable, empleado
Pantalla: HUB_SHELL: Cambiar de usuario
Pasos:
1. En un dispositivo compartido y de confianza, quien está en la caja abre «Cambiar de usuario» en su menú.
2. La persona que entra elige su nombre y teclea su PIN. El relevo no acepta la placa: quien entra con placa lo hace desde la pantalla de acceso (HUB-F134).
3. El hub abre la sesión de la nueva persona por la misma puerta que HUB-F133; solo cuando la tiene, la pantalla cierra la del anterior.
4. La venta sigue en pantalla y lo siguiente queda a nombre de quien entró («Ahora atiende {name}»).
Entra: el nombre y el PIN de quien entra; el token de quien sale.
Sale: una sesión nueva y la anterior borrada. Cuando el PIN nuevo se acepta, la pantalla además olvida las credenciales de erplora.com y la conversación con el asistente de quien se fue (hub#1538, hub#1544, cerrada). El servidor no guarda ninguna conversación del asistente que haya que borrar.
Tras el relevo, la pantalla vuelve a leer para quien entra el plan, el lanzador, «Mis apps» y la lista de configuración (HUB_SHELL-F09, hub#2506). Hueco de la pantalla (no del servidor): la pantalla abierta sigue siendo la de quien se fue hasta que se navega (hub#2539).
Si falla: un PIN rechazado no cambia nada (quien estaba dentro sigue dentro, con su conversación): «Esos datos no han funcionado…». Dispositivo sin confianza: «Este dispositivo todavía no está dado de alta para el PIN…».
Implicados: HUB_SHELL-F09, HUB_SHELL-F195
QA: qa-hub-restaurant §7.02, L-13

### HUB-F139 Marcar un dispositivo como compartido o personal
Estado: parcial — sin haber entrado, el hub dice de cualquier identificador de dispositivo que le presenten si es de confianza, no solo del que pregunta (ERPlora/hub#2551)
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › General
Pasos:
1. Desde el propio dispositivo, el administrador abre **Ajustes → General → Este dispositivo**.
2. Elige «Compartido — una caja o tablet que usan varias personas» o «Personal — un dispositivo que solo usas tú»; cada opción dice debajo su consecuencia.
3. El hub guarda la decisión en la ficha de confianza de ese dispositivo.
4. En compartido, la pantalla de acceso ofrece pinpad y la sesión dura un turno; en personal, no hay pinpad y la sesión dura 30 días.
Entra: el dispositivo (el que hace la petición, o uno nombrado); la sesión de administrador.
Sale: el modo, quién y cuándo lo cambió. La pantalla de acceso lo lee sin sesión junto con el dial del negocio y si el dispositivo es de confianza. Un dispositivo desconocido, ilegible o sin identificar se trata siempre como compartido. Entrar otra vez con la cuenta no pisa el modo. El cambio vale para las sesiones que se abran a partir de ahora: la abierta conserva su caducidad (HUB-F136). La puerta sin sesión que lee la pantalla de acceso dice, para cualquier identificador que se le presente, su modo y si es de confianza.
Si falla: un dispositivo en el que nadie entró nunca con una cuenta no se puede marcar (`hub.device.unknown_device`); sin ser administrador, «Solo un administrador puede cambiar cómo entra la gente en este dispositivo.».
Implicados: HUB_APP-F06, HUB_SHELL-F11, REC_ALTA-F16
QA: qa-hub-restaurant §7.02

### HUB-F140 Decidir si el negocio pide PIN y cuántos dígitos tiene
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › General
Pasos:
1. El administrador abre **Ajustes → General → Pinpad**.
2. Enciende o apaga «Mostrar pinpad» y elige «Volver a preguntar tras inactividad» (1, 5, 10, 15 o 30 minutos, o «Hasta cerrar sesión»); en «Dígitos del PIN», 4 o 6.
3. Cada control se guarda al moverlo, sin botón de guardar.
4. Vale para todo el negocio y se combina con el modo de cada dispositivo: gana siempre lo más estricto.
Entra: la sesión de administrador.
Sale: los ajustes del negocio `pin_policy` (`always`, `per_shift` o `never`), `pin_inactivity_minutes` y `pin_length`, con quién los cambió. «No mostrar pinpad» nunca alarga la sesión de un dispositivo compartido: renuncia a saber quién vende, no al candado. Los PIN de la otra longitud siguen funcionando hasta que su dueño los cambia. Como la duración se fija al abrir, pasar a «pedir siempre» no acorta las sesiones ya abiertas (hasta 30 días en un dispositivo personal).
En este mismo documento se apoya en: HUB-F220 (Leer los ajustes del negocio), HUB-F221 (Cambiar los ajustes del negocio).
Si falla: un valor fuera de lo permitido se rechaza (422); sin ser administrador, «Solo un administrador puede cambiar si se pregunta.». Un valor guardado que no se entiende vuelve al de fábrica (`per_shift`, 5 minutos, 4 dígitos), nunca a «no preguntar».
Implicados: HUB_SHELL-F08, HUB_SHELL-F99, HUB_SHELL-F100, REC_ALTA-F15
QA: ninguno

### HUB-F141 Ver, nombrar y quitar los dispositivos del negocio
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › General
Pasos:
1. El administrador abre **Ajustes → General → Dispositivos**: cada dispositivo en el que alguien entró con su cuenta, con su nombre, quién entró la última vez, cuándo se usó y si su sesión sigue abierta.
2. Para reconocerlo, le pone nombre («Barra», «Portátil del despacho», hasta 60 caracteres).
3. Si se pierde uno, pulsa «Quitar este dispositivo» y confirma: su sesión se cierra al momento y deja de poder entrar con PIN.
4. Con «Quitar los {n} dispositivos sin usar desde hace 30 días» limpia de golpe los que nadie usa; el que tiene en la mano nunca cuenta.
Entra: la sesión de administrador; el dispositivo desde el que pregunta.
Sale: el nombre del dispositivo; al quitarlo, sus sesiones borradas y su confianza retirada (con ella, el modo personal). Quitar el propio dispositivo cierra la sesión de quien lo hace. Volver a entrar con una cuenta lo hace de confianza otra vez: se corta el dispositivo, no la persona.
Si falla: «Ese dispositivo ya no está registrado aquí. Actualiza la lista.»; nombre largo, «Ese nombre es demasiado largo…»; sin ser administrador, «Solo el propietario o un administrador puede gestionar los dispositivos.».
Implicados: HUB_SHELL-F101, HUB_SHELL-F102, HUB_SHELL-F103, HUB_SHELL-F104
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
Implicados: HUB_SHELL-F16, HUB_SHELL-F23, HUB_SHELL-F48, HUB_SHELL-F129, SAAS-F01, SAAS_AUTH-F21
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
Sale: el perfil (`hub_user_profile`) y las preferencias (`hub_user_pref`); la foto en el almacén del hub. El correo del perfil no es el de acceso (ese lo cambia un administrador, HUB-F148), pero **si la persona no tiene correo de acceso** (todo usuario local), Personal usa el del perfil en su lugar y con él decide qué membresía de erplora.com da o quita al cambiarle el rol o darla de baja (HUB-F148, HUB-F149). Como el perfil se edita sin comprobar a quién pertenece el correo, es un hueco de seguridad (ver huecos). Nombre y apellidos hasta 150 caracteres; idioma español o inglés.
Si falla: «No se pudo guardar el perfil»; foto que no es JPG, PNG o WebP o pasa de 2 MB, «No se pudo guardar la foto. Usa JPG, PNG o WebP de hasta 2 MB.».
Implicados: HUB_SHELL-F21
QA: ninguno

### HUB-F144 Cerrar la puerta a quien ya no es miembro en erplora.com
Estado: parcial — el hub solo se entera cuando esa persona vuelve a intentar entrar con su cuenta: erplora.com no avisa al quitar la membresía, así que hasta entonces su sesión, su PIN y su placa siguen funcionando
Actor: sistema
Pantalla: ninguna
Pasos:
1. Alguien a quien quitaron del negocio en erplora.com intenta entrar con su cuenta.
2. El hub ve que la credencial ya no lo nombra miembro de este negocio. Eso solo pasa con una credencial de un acceso nuevo (contraseña, Google o el pase desde el panel, que es lo único que manda la pantalla del hub): una credencial **renovada** copia la lista de negocios de la que renueva y sigue nombrándolo miembro mientras se renueve, y la puerta del hub acepta cualquier credencial firmada y vigente, sin distinguir si es renovada.
3. Antes de rechazarlo, lo da de baja en el hub y borra sus sesiones: deja de aparecer en el pinpad y su PIN y su placa dejan de servir.
4. Si más adelante vuelve a ser miembro, su próximo acceso con la cuenta lo reincorpora en la misma ficha, con el rol que le dé la membresía de ese día.
Entra: la credencial de erplora.com sin este negocio en su lista.
Sale: la ficha desactivada y marcada como cerrada por erplora.com (`cloud_revoked_at`), sus sesiones borradas; respuesta `not_a_member`. Hasta ese intento, su sesión abierta vive hasta su caducidad (12 h en compartido, 30 días en personal, 1 h con «pedir siempre») y su PIN y su placa valen sin plazo; si su correo de acceso difiere en mayúsculas del de la cuenta, ni siquiera ese intento la cierra. Para cortarla en el acto, se da de baja en el hub (HUB-F149). Una baja hecha por el administrador del hub no se deshace así: esa persona recibe `user_deactivated` hasta que la reincorporen (HUB-F149).
Si falla: si la baja local no se puede escribir, queda en el registro de errores y el acceso se rechaza igual.
Implicados: HUB_SHELL-F01, REC_ALTA-F15, SAAS_AUTH-F22, SAAS_DASHBOARD-F16
QA: ninguno

## Cobertura contra la referencia

| Elemento | Estado | Flujo |
|---|---|---|
| Acceso con cuenta (correo, Google, segundo factor) | hecho (el segundo factor lo hace erplora.com) | HUB-F130 |
| Entrar desde el panel sin volver a teclear | hecho | HUB-F131 |
| PIN propio, cambio con el PIN actual | hecho | HUB-F132 |
| PIN de longitud fija por negocio (4 o 6), no adivinable, único | hecho | HUB-F132, HUB-F140, HUB-F145 |
| Caducidad o rotación obligatoria del PIN | no hecho (ningún TPV de referencia la exige; fuera) | — |
| Acceso con PIN en dispositivo compartido de confianza | hecho | HUB-F133 |
| Acceso con placa (lector USB, NFC) | parcial (sin validar con hardware real) | HUB-F134 |
| Freno por intentos (por nombre, por placa, por dirección) | hecho | HUB-F135 |
| Duración de sesión por dispositivo y por negocio | hecho | HUB-F136 |
| Bloqueo por inactividad | parcial (lo hace la pantalla) | HUB-F136 |
| Cerrar todas mis sesiones | no hecho | — |
| Un dispositivo a la vez en el plan gratuito | hecho | HUB-F137 |
| Cambio rápido de usuario sobre la venta | hecho (solo con PIN, sin placa) | HUB-F138 |
| Dispositivo compartido / personal | hecho | HUB-F139 |
| Lista de dispositivos, nombrar, quitar, limpiar | hecho | HUB-F141 |

## Datos: de quién es cada dato

Del área (tablas de sistema; cuáles no llevan `hub_id` lo dice el índice): `hub_user` (personas), `hub_session` (sesiones),
`hub_trusted_device` (dispositivos de confianza y su modo), `hub_user_profile` y `hub_user_pref`
(perfil y preferencias), `hub_role_activation` (roles encendidos), `_elevation_audit` (recibos de
aprobación), `_hub_badge_key` (clave de las placas, sin puerta HTTP), `hub_api_key` y
`hub_api_key_rate_window` (llaves y su ventana), `_policy` (normas), `_update_history` (versiones),
`_hub_meta`, y los ajustes `pin_policy`, `pin_inactivity_minutes`, `pin_length` y `api_docs_enabled`
en `hub_settings` (que guarda la puerta de ajustes de [negocio-y-datos.md](negocio-y-datos.md),
HUB-F221). El latido de uso manda y vacía `_hub_activity_log`, que es de negocio y datos (HUB-F254).

En memoria del proceso (se pierden al reiniciar): el plan verificado, las aprobaciones sin gastar,
los contadores de intentos, las memorias de 60 s del plan y de 30 s de las series.

Inventario de datos personales (sacado de las migraciones de sistema); el de cuentas, aprobaciones,
normas y llaves está en [personas-y-permisos.md](personas-y-permisos.md):

| Dónde | Qué |
|---|---|
| `hub_user` | nombre, correo de acceso, `cloud_user_id`, huella del PIN, índice y huella de la placa, rol, activo, `cloud_revoked_at`, marca de dueño |
| `hub_user_profile` | nombre, apellidos, correo de contacto, ruta de la foto (y la foto en el almacén) |
| `hub_user_pref` | idioma, tema, paleta |
| `hub_session` | quién, cuándo, dispositivo, con qué credencial y qué placa (índice), motivo de cierre; sin IP ni navegador |
| `hub_trusted_device` | `label` = nombre de la última persona que entró en él; `mode_set_by` |
| Registro del proceso | la dirección IP en las líneas `event=auth_failed` |

## Reglas que no se rompen

- Un PIN solo funciona en un dispositivo donde antes entró una cuenta (confianza armada por defecto;
  solo `HUB_DEVICE_TRUST=off` la desarma) (HUB-F133).
- Un dispositivo desconocido o un valor ilegible se tratan como compartido; un dial ilegible vuelve
  al de fábrica, nunca a «no preguntar»; ninguno de los dos controles alarga lo que el otro acortó.
- Un PIN es único entre las personas activas, de la longitud del negocio y no adivinable, en todas
  las puertas (alta, edición, perfil).
- El acceso con cuenta solo **sube** el rol hasta administrador, nunca lo baja ni da «owner».
- La caducidad de una sesión se fija al abrirla; cambiar el modo o el dial solo afecta a las nuevas.

## Lo que NO hace, a propósito

- No caduca ni obliga a cambiar el PIN.
- No guarda la IP ni el navegador de una sesión.
- No marca el modo del dispositivo desde la pantalla de acceso (solo lo lee).

## Fuentes contrastadas

- `architecture/hub/auth.md` («El PIN, como credencial») dice 4–8 dígitos; el código admite 4 o 6,
  fijo por negocio (`crates/runtime/src/pin_policy.rs`, hub#974).
- Que «Este dispositivo» está en «Ajustes › General» y no en «Ajustes › Hub», como dice
  `architecture/hub/auth.md`, está en las fuentes comunes del índice.
