# WORKFLOW — Hub (servidor) · Personas, roles, permisos y llaves

Prefijo: HUB

> Detalle del área «Acceso, personas y plan» (oleada 3): quién puede entrar en el negocio, con qué
> rol, qué hace el hub cuando alguien pide algo sin permiso, cómo aprueba un responsable con su PIN,
> las normas que escribe el dueño y las llaves para sistemas externos. La pantalla **Empleados**
> (pestañas Personal, Roles, API keys y Aprobaciones) es de `HUB_SHELL`; aquí está lo que decide el
> servidor. El módulo Personal (`staff`) es otra cosa: su ficha de profesional se **vincula** a estas
> cuentas, no las crea. Técnico: `architecture/hub/auth.md`, `policies.md`, `public-api.md`.

## Flujos

### HUB-F145 Dar de alta a una persona que entra solo con PIN
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Empleados
Pasos:
1. En **Empleados → Personal**, el administrador pulsa añadir y marca «Usuario local».
2. Escribe el nombre, elige un rol que se pueda asignar y teclea su PIN (con los dígitos del negocio); si quiere, le da una placa.
3. Guarda.
4. La persona aparece en la lista y en el pinpad de los dispositivos compartidos de confianza.
Entra: la sesión de administrador; el nombre (hasta 150 caracteres), el rol, el PIN y la placa opcional; las plazas del plan (HUB-F147).
Sale: la ficha (`hub_user`) con el PIN y la placa guardados como huella; nada en erplora.com: esta persona no tiene cuenta y solo existe en este negocio. Más tarde se le puede añadir un correo y convertirla en persona con cuenta sin perder su historial (HUB-F148).
Si falla: con correo, «local_has_email»; sin PIN, «Un usuario local entra con un PIN: sin él, nadie podría usar esta ficha.»; con rol de administrador, «local_cannot_administer» (un PIN nunca administra el hub); un nombre que el hub ya conoce, aunque esté de baja, «Este hub ya conoce a alguien con ese nombre…»; PIN fácil o repetido, los mismos avisos que HUB-F132; placa con forma rara o ya usada, «Una placa tiene entre 4 y 64 caracteres…» o «Esa placa ya la lleva otro usuario activo…»; sin plazas, HUB-F147.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Empleados › Personal (alta con «Usuario local»)
Pendiente de enlazar: staff — STAFF-F01 (la ficha de profesional que luego se vincula a esta cuenta)
QA: qa-hub-restaurant §7.02

### HUB-F146 Invitar a una persona con su cuenta de erplora.com
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Empleados
Pasos:
1. En **Empleados → Personal**, el administrador pulsa añadir y deja «Usuario local» sin marcar.
2. Escribe nombre, correo y rol (administrador, responsable o empleado) y, si va a trabajar en la caja compartida, un PIN.
3. Guarda. El hub crea la ficha y pide a erplora.com que dé de alta a esa persona como miembro del negocio con ese rol; es erplora.com quien le manda el correo de invitación.
4. La persona se pone su propia contraseña en erplora.com; cuando entra por primera vez, el hub la reconoce por el correo y usa la misma ficha (HUB-F130).
Entra: la sesión de administrador; nombre, correo, rol y PIN opcional; la credencial de máquina del hub hacia erplora.com.
Sale: la ficha con el correo de acceso escrito en los dos sitios (acceso y perfil); la membresía y la invitación en erplora.com (`POST /api/v1/hub/device/members/`). El administrador nunca conoce la contraseña. La misma alta existe por la puerta `/api/members`, con las mismas reglas.
Si falla: sin correo, «account_needs_email»; un rol que no sea de los tres de fábrica, «A una cuenta de ERPlora solo se la puede invitar como admin, manager o employee…»; correo que el hub ya conoce, «Este hub ya conoce ese email…»; repartir administración sin ser administrador, «No puedes repartir un rol por encima del tuyo…». Si erplora.com no contesta, rechaza o frena, la ficha local queda escrita y la respuesta lo dice (`cloud_unreachable`, `cloud_rejected` o «Demasiados cambios en poco tiempo: la invitación todavía no ha salido…»); se arregla volviendo a guardar. Hub sin conectar con erplora.com: `not_enrolled`.
Implicados: pendiente
Pendiente de enlazar: saas — dar de alta a un miembro del negocio y mandarle la invitación
Pendiente de enlazar: hub — HUB_SHELL, Empleados › Personal (alta de cuenta)
Pendiente de enlazar: staff — STAFF-F01 (la cuenta que luego se vincula a la ficha de profesional)
QA: qa-hub-restaurant §7.02

### HUB-F147 Llegar al tope de plazas del plan
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Empleados
Pasos:
1. El plan del negocio admite un número de personas activas (3 en el gratuito).
2. El administrador intenta dar de alta, invitar o reincorporar a alguien con todas las plazas ocupadas.
3. El hub lo rechaza sin escribir nada y la pantalla ofrece «Actualizar plan».
4. Dar de baja a alguien libera su plaza al momento.
Entra: el tope de personas del último plan verificado (HUB-F162); sin plan verificado no hay tope. Se cuentan solo las personas activas de este negocio.
Sale: nada escrito; el rechazo `hub.users.user_limit_reached` (409). Dos altas a la vez no pueden coger la misma plaza: la plaza se pide en el mismo paso que se escribe. Cambiar el rol de quien ya está dentro no gasta plaza. Quien entra con su cuenta por primera vez no pasa por este tope: esa plaza la controla erplora.com.
Si falla: «Tu plan tiene todas las plazas ocupadas. Da de baja a alguien que ya no trabaje aquí, o pasa a un plan con más plazas.».
Implicados: pendiente
Pendiente de enlazar: saas — tope de plazas por plan en el permiso firmado y en la invitación
Pendiente de enlazar: hub — HUB_SHELL, Empleados (aviso de plazas y «Actualizar plan»)
QA: ninguno

### HUB-F148 Cambiar el nombre, el rol, el PIN, la placa o el correo de una persona
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Empleados
Pasos:
1. En **Empleados → Personal**, el administrador abre la ficha.
2. Cambia lo que haga falta: nombre, rol, PIN («Escribe un PIN nuevo para cambiarlo; déjalo en blanco y se queda como está»), placa o correo de acceso.
3. Guarda.
4. El rol nuevo vale desde la siguiente acción de esa persona, también en sesiones ya abiertas.
Entra: la sesión de administrador; los campos que cambian (solo esos).
Sale: la ficha. El orden depende del cambio: lo que concede (rol, correo, reincorporación) se pide primero a erplora.com y solo después se escribe aquí; el nombre, el PIN y la placa no se cuentan a erplora.com y funcionan aunque no conteste.
Si falla: la ficha del dueño de la cuenta solo la cambia él, PIN incluido («Esta es la ficha del dueño de la cuenta y solo él puede cambiarla…»); nadie se da de alta su propia placa («Nadie da de alta su propia placa. Pídeselo a otro administrador.», salvo el dueño); la placa no puede quedar como única forma de entrar («La placa no puede ser su única vía de entrada…»); quitar el rol de administrador al último que queda, «No puedes dar de baja al último administrador…»; un rol de un módulo que está apagado, «Ya no se puede asignar «{role}».»; PIN o correo repetidos, los avisos de HUB-F132 y HUB-F146.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Empleados › Personal (editar la ficha)
Pendiente de enlazar: staff — STAFF-F03 (el rol de permisos y el PIN son de la cuenta, no de la ficha de profesional)
QA: qa-hub-restaurant §7.02

### HUB-F149 Dar de baja y reincorporar a una persona
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Empleados
Pasos:
1. En **Empleados → Personal**, el administrador elige «Dar de baja» en la fila y confirma («Perderá el acceso al Hub, pero su historial se conserva.»).
2. El hub la desactiva, cierra sus sesiones al momento y, si tenía cuenta, pide a erplora.com que le quite la membresía.
3. Para volver a contar con ella, abre su ficha y la reactiva: vuelve la misma persona, con su historial, si queda plaza.
Entra: la sesión de administrador; la persona.
Sale: la ficha desactivada (nunca borrada: ventas, aprobaciones y auditoría siguen nombrándola), sus sesiones borradas, y fuera del pinpad y de la lista de personas activas; la membresía retirada en erplora.com. Cerrar la puerta va primero en local y no depende de que erplora.com conteste. Reactivar pide plaza (HUB-F147) y la membresía otra vez.
Si falla: «No puedes darte de baja a ti mismo ni dejar el Hub sin ningún administrador.»; la ficha del dueño no la da de baja nadie más. Si erplora.com no contesta al quitar la membresía, la baja local se queda y la respuesta lo dice; esa persona no podrá entrar en el hub, pero sigue siendo miembro allí hasta que se repita.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Empleados › Personal (dar de baja)
Pendiente de enlazar: saas — quitar a un miembro del negocio
Pendiente de enlazar: staff — STAFF-F03 (dar de baja la cuenta no toca la ficha de profesional)
QA: qa-hub-restaurant §7.02

### HUB-F150 Ver los roles y encender los que trae un módulo
Estado: parcial — el dueño no puede crear un rol propio ni cambiar qué permite cada rol: los roles y sus permisos los fijan los módulos instalados, y solo se encienden o apagan los que declara un módulo
Actor: administrador
Pantalla: HUB_SHELL: Empleados
Pasos:
1. En **Empleados → Roles** se ven los roles del negocio: los tres de fábrica (administrador, responsable y empleado), los que declaran los módulos instalados y cualquiera que ya tenga alguien, con sus permisos y sus miembros.
2. Un rol que trae un módulo (camarero, cocina…) se enciende para poder asignarlo.
3. Desde entonces aparece entre los roles al dar de alta o editar a una persona.
Entra: la sesión (leer, cualquiera; encender o apagar, administrador); los roles y permisos que declaran los módulos activos.
Sale: el rol encendido o apagado, con quién lo hizo (`hub_role_activation`). Los permisos de un rol son la suma de lo que le conceden los módulos activos; el administrador además administra el hub y toda sesión puede ver al personal. Un rol de un módulo nunca administra el hub. Una plantilla del negocio también puede encender roles al importarse, por la misma puerta.
Si falla: los roles de fábrica no se apagan («immutable»); no se puede encender un rol que ningún módulo declara («unknown»); sin ser administrador, el aviso de permiso de la pestaña.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Empleados › Roles
Pendiente de enlazar: hub — HUB, módulos y órdenes (los roles que declara un módulo y su validación al instalar)
QA: qa-hub-restaurant §6

### HUB-F151 Rechazar una orden para la que no se tiene permiso
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Una persona, una app o una llave pide al hub una consulta o una orden de un módulo.
2. El hub mira si su rol (o la llave) tiene el permiso que esa orden declara.
3. Si no lo tiene y es una consulta, la rechaza.
4. Si no lo tiene y es una orden que un responsable sí puede hacer, la rechaza diciendo que se puede aprobar con PIN, y la pantalla abre el diálogo de aprobación (HUB-F152); si no se puede aprobar, la rechaza sin más.
Entra: la sesión o la llave, y el permiso que declara el módulo para esa orden.
Sale: `permission_denied` (403) o `requires_elevation` (403) con el permiso que falta; nada ejecutado. Las páginas del propio hub que piden sesión de administrador (ajustes, personal, llaves, dispositivos, métricas, automatizaciones) contestan `forbidden` o 401 según la puerta. Una llave de API nunca recibe la oferta de aprobación.
Si falla: no hay frase genérica en español para `permission_denied`: cada pantalla pinta su propio aviso de permiso.
Implicados: pendiente
Pendiente de enlazar: hub — HUB, módulos y órdenes (el embudo de una orden y dónde va la comprobación de permiso)
Pendiente de enlazar: flows — FLOWS-F01 (la sesión de administrador que exige el motor)
QA: qa-hub-restaurant §6

### HUB-F152 Aprobar una acción con el PIN de un responsable
Estado: hecho
Actor: responsable, empleado
Pantalla: HUB_SHELL: Aprobación
Pasos:
1. El cajero intenta algo que su rol no permite pero un responsable sí (un descuento por encima del límite, una anulación): sale «Hace falta una aprobación» con «Se aprueba: {acción}».
2. Un responsable elige su nombre y teclea su PIN, o pasa su placa, sin cerrar la sesión del cajero.
3. El hub comprueba que esa persona existe, está activa, su PIN es correcto y **ella misma** podría hacer esa acción.
4. La acción se hace una sola vez, a nombre del cajero y aprobada por el responsable: «Aprobado por {name}».
Entra: la sesión del cajero; el nombre y PIN (o la placa) de quien aprueba; la orden exacta y sus datos.
Sale: un permiso de un solo uso, válido 120 s, atado a ese negocio, ese cajero, esa orden y esos datos (aprobar anular un tique de 4 € no sirve para uno de 400 €); vive en memoria y un reinicio lo pierde. Al gastarlo se escribe el recibo (quién pidió, quién aprobó, qué permiso, una huella de los datos y si fue PIN o placa) **antes** de ejecutar; sin recibo no se ejecuta. El módulo recibe los dos nombres (`created_by` y `approved_by`).
Si falla: nombre desconocido, PIN erróneo o persona de baja dan el mismo aviso, «Esos datos no aprueban esto. Revisa el nombre y el PIN, y vuelve a intentarlo.»; quien aprueba no puede hacerlo él mismo, «Esa persona no puede aprobarlo…»; lo que solo hace un administrador (identidad fiscal, plan, instalar apps), «Esto no se aprueba con un PIN…»; si el cajero ya tiene permiso, «Esto ya no necesita aprobación…». Cinco PIN erróneos con el mismo nombre lo frenan 5 minutos (HUB-F135).
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, diálogo de aprobación y SDK de módulos (reintento con la aprobación)
Pendiente de enlazar: sales — descuento por encima del límite y anulación con el PIN del encargado
QA: qa-hub-restaurant §6

### HUB-F153 Consultar quién aprobó qué
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Empleados
Pasos:
1. El administrador abre **Empleados → Aprobaciones**.
2. Ve cada acción que necesitó el PIN de un responsable: cuándo, quién la pidió, quién la autorizó, qué acción y una referencia.
3. Busca por persona o acción; las personas dadas de baja siguen saliendo con su nombre.
Entra: la sesión de administrador (permiso de administrar el hub).
Sale: nada; es una lectura paginada del registro de aprobaciones (`hub.approvals.list`). Nadie puede editar ni borrar una fila; el hub las poda solo a los cuatro años.
Si falla: «No se pudo cargar el registro de aprobaciones.»; vacío, «Todavía nadie ha tenido que autorizar nada en este Hub.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Empleados › Aprobaciones
Pendiente de enlazar: hub — HUB, negocio y datos (la poda de los recibos a los cuatro años)
QA: ninguno

### HUB-F154 Escribir una norma propia del negocio
Estado: parcial — no hay pantalla (solo la API del hub con sesión de administrador); el desenlace «que lo apruebe un responsable» se rechaza porque aún no existe (hub#1710), solo «bloquear»
Actor: administrador
Pantalla: asistente
Pasos:
1. El administrador consulta qué puntos de control ofrecen los módulos instalados (por ejemplo, poner un descuento) y qué datos se pueden comparar en cada uno.
2. Escribe la norma: la condición («descuento mayor que 20»), el mensaje que verá quien choque con ella y si está en prueba o en vigor.
3. En prueba, el hub apunta lo que habría bloqueado sin impedir nada; en vigor, la orden que la cumple no se ejecuta y se ve el mensaje del dueño.
4. La norma se cambia, se apaga o se borra cuando se quiera.
Entra: la sesión de administrador (nunca una llave ni la máquina); los puntos de control que declara cada módulo; la condición en el mismo lenguaje de las automatizaciones.
Sale: la norma (`_policy`, con quién la creó, cambió o borró; el borrado es lógico), como mucho 20 por punto de control. Al llegar una orden, el hub la evalúa después de completar los datos y antes de ejecutarla; una norma solo puede restringir, nunca conceder.
Si falla: una orden bloqueada responde `policy.blocked` con el mensaje del dueño. Si a la orden le falta un dato que la norma necesita, el hub **deniega**. Una norma con el desenlace de aprobación se rechaza al guardarla (501).
Implicados: pendiente
Pendiente de enlazar: hub — HUB, módulos y órdenes (carga de los puntos de control de cada módulo y el embudo de la orden)
QA: ninguno

### HUB-F155 Crear, rotar y revocar llaves de API
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Empleados
Pasos:
1. En **Empleados → API keys**, el administrador pulsa «Nueva API key».
2. Le pone nombre («Gestoría — facturas»), elige qué puede hacer («Acceso total», «Solo lectura», «Solo escritura» o «Por app» con lectura y escritura por módulo) y cuántas peticiones por minuto admite (1 a 10.000; 60 si no dice nada).
3. Crea la llave y copia el token: es la única vez que se ve entero.
4. «Rotar» da un token nuevo e invalida el anterior; «Revocar» la apaga de inmediato.
Entra: la sesión de administrador; los módulos instalados que exponen API.
Sale: la llave (`hub_api_key`) con su secreto guardado como huella, quién la creó y cuándo se usó por última vez. Los modos generales cubren también las apps que se instalen después. No caduca. Revocar no la borra (queda «Revocada»). La llave «ERPlora app», que el hub se emite para leer sus propios avisos en vivo, no se rota ni se revoca.
Si falla: «No se pudo crear la API key.»; la llave del sistema, «Esta clave la emite ERPlora para sí misma. No se puede rotar ni borrar.»; sin ser administrador, «Solo el propietario o un administrador puede gestionar las claves de API.». Rotar una llave revocada la vuelve a dejar activa.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Empleados › API keys
Pendiente de enlazar: hub — HUB, avisos entre módulos (la llave «ERPlora app» y el canal de avisos en vivo)
QA: ninguno

### HUB-F156 Leer y escribir datos del negocio con una llave de API
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un sistema externo (la gestoría, una tienda online) llama al hub con su llave.
2. Pide una consulta o una orden de un módulo por su nombre.
3. El hub comprueba que la llave está activa, que no ha pasado su límite por minuto, que el módulo publica esa operación para terceros y que la llave tiene el permiso.
4. Contesta igual que a la pantalla, y lo que escribe queda a nombre de la llave.
Entra: la llave en `Authorization: Bearer erpl_live_…`; la operación (`/api/v1/<módulo>/q/<consulta>` o `/c/<orden>`).
Sale: la respuesta del módulo; las escrituras con autor `apikey:<id>`; el último uso de la llave. La llave no ve al personal ni puede pedir aprobaciones, y no sirve en las puertas de la pantalla.
Si falla: llave desconocida o revocada, 401; operación que el módulo no publica o no existe, 404 (las dos igual); sin permiso, `permission_denied`; pasado el límite, `rate_limited` (429) con `Retry-After`.
Implicados: pendiente
Pendiente de enlazar: hub — HUB, módulos y órdenes (qué operaciones publica un módulo para terceros)
QA: ninguno

### HUB-F157 Consultar la documentación de la API
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: HUB_SHELL: Documentación de la API
Pasos:
1. Un administrador enciende la documentación de la API en los ajustes del negocio (viene apagada).
2. Cualquiera con sesión abre **API** en el menú: ve las operaciones que publican los módulos instalados.
3. Para probarlas pega una llave en «Authorize»; la documentación no da acceso por sí sola.
Entra: la sesión de la persona (no una llave); los módulos instalados.
Sale: nada guardado; el documento OpenAPI 3.1 del negocio (`/api/v1/openapi.json`), que crece y mengua al instalar o quitar módulos.
Si falla: apagada, 404; sin sesión o con una llave, 401. La pantalla dice «No se pudo cargar la documentación» con «Reintentar».
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Documentación de la API
Pendiente de enlazar: hub — HUB, negocio y datos (el ajuste que enciende la documentación)
QA: ninguno

### HUB-F158 Dar la lista de personas del negocio a los módulos
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un módulo o el propio hub necesita nombrar a alguien (la cocina a quien envió la comanda, Personal al vincular una ficha, el tique con quien atendió).
2. Pide al hub la lista de personas.
3. Recibe, por persona, su identificador, nombre, rol y si está activa; nunca el correo ni cómo entra.
Entra: cualquier sesión de una persona del negocio (todas pueden ver al personal); una llave de API no.
Sale: nada guardado; la lista (`hub.users.list`) con activos y de baja. Hay una hermana con los roles (`hub.roles.list`). La pantalla de acceso recibe sin sesión otra lista más corta: solo las personas activas con PIN.
Si falla: sin sesión o con una llave, sin permiso; cada módulo decide qué pinta (la cocina deja la comanda sin camarero).
Implicados: pendiente
Pendiente de enlazar: kitchen — KITCHEN-F10 (nombrar a quien envió la comanda)
Pendiente de enlazar: staff — STAFF-F03 (las cuentas activas que se ofrecen para vincular la ficha)
QA: ninguno
