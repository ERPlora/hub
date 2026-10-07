# WORKFLOW — Hub (servidor) · Personas, roles, permisos y llaves

Prefijo: HUB

> Detalle del área «Acceso, personas y plan» (oleada 3): quién puede entrar en el negocio, con qué
> rol, qué hace el hub cuando alguien pide algo sin permiso, cómo aprueba un responsable con su PIN,
> las normas que escribe el dueño y las llaves para sistemas externos. La pantalla **Empleados**
> (pestañas Personal, Roles, API keys y Aprobaciones) es de `HUB_SHELL`; aquí está lo que decide el
> servidor. El módulo Personal (`staff`) es otra cosa: su ficha de profesional se **vincula** a estas
> cuentas, no las crea. Técnico: `architecture/hub/auth.md`, `policies.md`, `public-api.md`.

## Referencia adoptada

Para esta parte del área (la de entrar y las sesiones está en [acceso.md](acceso.md)):

- **Aprobación de un responsable por acción, con su PIN o su placa, sin cerrar la sesión del cajero**:
  Toast (manager approval), Square; registro de quién pidió y quién aprobó (ADR-0238/0265).
- **Ficha del dueño en solo lectura para los demás administradores**: Shopify, Square, Toast,
  Lightspeed, Vagaro, Business Central (hub#1429).
- **Dar de baja, nunca borrar, a un empleado**: 11 de 11 referencias (ADR-0352).
- **Normas del dueño con nombre y parámetros sobre puntos de control del desarrollador** (límite +
  bloquear/aprobación): Shopify Validation Functions, Lightspeed X-Series Workflows; modo prueba como
  Stripe Radar «Review» (ADR-0476, `architecture/hub/policies.md`).
- **Llaves de API con secreto mostrado una vez, rotar y revocar, permisos por módulo y
  lectura/escritura** (`architecture/hub/public-api.md`, ADR-0057); documentación OpenAPI 3.1.

## Antes de empezar

- Da de alta al personal: locales con PIN o con cuenta (HUB-F145, HUB-F146), dentro de las plazas
  del plan (HUB-F147); enciende los roles que traen las apps (HUB-F150).

## Flujos

### HUB-F145 Dar de alta a una persona que entra solo con PIN
Estado: parcial — el freno de 30 intentos por hora de quien edita no para a quien va despacio (29 cada hora no bloquean nunca, unos 700 al día) y los intentos no dejan rastro: con tiempo se sigue pudiendo averiguar el PIN de otra persona (ERPlora/hub#2526)
Actor: administrador
Pantalla: HUB_SHELL: Empleados
Pasos:
1. En **Empleados → Personal**, el administrador pulsa añadir y marca «Usuario local».
2. Escribe el nombre, elige un rol que se pueda asignar y teclea su PIN (con los dígitos del negocio); si quiere, le da una placa.
3. Guarda.
4. La persona aparece en la lista y en el pinpad de los dispositivos compartidos de confianza.
Entra: la sesión de administrador; el nombre (hasta 150 caracteres), el rol, el PIN y la placa opcional; las plazas del plan (HUB-F147).
Sale: la ficha (`hub_user`) con el PIN y la placa guardados como huella; nada en erplora.com: esta persona no tiene cuenta y solo existe en este negocio. Más tarde se le puede añadir un correo y convertirla en persona con cuenta sin perder su historial (HUB-F148). Como el PIN es único, «ya lo tiene otro usuario activo» dice que ese número es de alguien: por eso cada alta que lleva PIN gasta un intento del presupuesto de **quien da el alta**, el mismo que el cambio del propio PIN (HUB-F132): 30 intentos por hora contados desde el primero, también los aceptados; agotado, no mira el número ni escribe nada durante una hora (ERPlora/hub#2518). Treinta caben para dar de alta a toda la plantilla seguida sin esperar, y aun así quien prueba números saca menos intentos al día que con los 5 en 5 minutos de antes (ERPlora/hub#2564).
Si falla: con correo, «local_has_email»; sin PIN, «Un usuario local entra con un PIN: sin él, nadie podría usar esta ficha.»; con rol de administrador, «local_cannot_administer»: el **alta** de un usuario local no admite administrador (ojo: la edición de la ficha sí deja subirlo después a administrador, HUB-F148, y un administrador con PIN entra por el pinpad con todos sus permisos; solo el pase a erplora.com, HUB-F142, exige haber entrado con la cuenta); un nombre que el hub ya conoce, aunque esté de baja, «Este hub ya conoce a alguien con ese nombre…»; PIN fácil o repetido, los mismos avisos que HUB-F132; placa con forma rara o ya usada, «Una placa tiene entre 4 y 64 caracteres…» o «Esa placa ya la lleva otro usuario activo…»; sin plazas, HUB-F147; con el presupuesto de intentos de PIN gastado, 429 `too_many_attempts` con los segundos que faltan, sin decir si el número estaba libre.
Implicados: HUB_SHELL-F81, STAFF-F01, REC_ALTA-F15
QA: qa-hub-restaurant §7.02

### HUB-F146 Invitar a una persona con su cuenta de erplora.com
Estado: parcial — si la invitación a erplora.com falla, la pantalla no tiene forma de reenviarla aunque el aviso dice «vuelve a guardar»
Actor: administrador
Pantalla: HUB_SHELL: Empleados
Pasos:
1. En **Empleados → Personal**, el administrador pulsa añadir y deja «Usuario local» sin marcar.
2. Escribe nombre, correo y rol (administrador, responsable o empleado) y, si va a trabajar en la caja compartida, un PIN.
3. Guarda. El hub crea la ficha y pide a erplora.com que dé de alta a esa persona como miembro del negocio con ese rol; es erplora.com quien le manda el correo de invitación.
4. La persona se pone su propia contraseña en erplora.com; cuando entra por primera vez, el hub la reconoce por el correo y usa la misma ficha (HUB-F130).
Entra: la sesión de administrador; nombre, correo, rol y PIN opcional; la credencial de máquina del hub hacia erplora.com.
Sale: la ficha con el correo de acceso escrito en los dos sitios (acceso y perfil); la membresía y la invitación en erplora.com (`POST /api/v1/hub/device/members/`). El administrador nunca conoce la contraseña. Hay una segunda puerta (`/api/members`, que la pantalla no usa) que es alta-o-reinvitación por correo: si el correo ya existe, le cambia el rol, la reactiva y vuelve a avisar a erplora.com; no lleva nombre, PIN ni placa, y comparte con Personal solo las barandillas, el rol concedible y el tope de plazas.
Si falla: sin correo, «account_needs_email»; un rol que no sea de los tres de fábrica, «A una cuenta de ERPlora solo se la puede invitar como admin, manager o employee…»; correo que el hub ya conoce, «Este hub ya conoce ese email…»; repartir administración sin ser administrador, «No puedes repartir un rol por encima del tuyo…». Si erplora.com no contesta, rechaza o frena, la ficha local queda escrita y la respuesta lo dice (`cloud_unreachable`, `cloud_rejected` o «Demasiados cambios en poco tiempo: la invitación todavía no ha salido…»). Volver a guardar **no** la reenvía: un alta nueva choca con «Este hub ya conoce ese email…» y guardar la ficha sin cambiar rol, correo ni estado no llama a erplora.com. Hoy solo la reenvía la puerta `/api/members`, y solo si cambia el rol o la persona no tenía membresía en erplora.com: con la credencial de máquina y el mismo rol, erplora.com contesta `invited: false` y no manda nada. Hub sin conectar con erplora.com: `not_enrolled`.
Implicados: HUB_SHELL-F82, STAFF-F01, STAFF-F03, REC_ALTA-F15, SAAS_DASHBOARD-F13, SAAS_DASHBOARD-F60, SAAS_DASHBOARD-F214
QA: qa-hub-restaurant §7.02

### HUB-F147 Llegar al tope de plazas del plan
Estado: parcial — al reincorporar a una persona con cuenta, erplora.com recibe el alta antes de que el hub compruebe la plaza; quien entra con su cuenta por primera vez no pasa por el tope
Actor: administrador
Pantalla: HUB_SHELL: Empleados
Pasos:
1. El plan del negocio admite un número de personas activas (3 en el gratuito).
2. El administrador intenta dar de alta, invitar o reincorporar a alguien con todas las plazas ocupadas.
3. El hub lo rechaza sin escribir nada. La pantalla ofrece «Actualizar plan» solo en la ficha de la persona, así que en la práctica solo se ve al reincorporar a alguien.
4. Dar de baja a alguien libera su plaza al momento.
Entra: el tope de personas del último plan verificado (HUB-F162); sin plan verificado no hay tope. Se cuentan solo las personas activas de este negocio.
Sale: nada escrito en el hub; el rechazo `hub.users.user_limit_reached` (409). Salvo al **reincorporar** a una persona con cuenta: el hub avisa antes a erplora.com (que recrea la membresía y la invitación) y solo después pide la plaza, así que con el plan lleno erplora.com ya la ha readmitido cuando el hub contesta 409. Dos altas a la vez no pueden coger la misma plaza: la plaza se pide en el mismo paso que se escribe. Cambiar el rol de quien ya está dentro no gasta plaza. Quien entra con su cuenta por primera vez no pasa por este tope: esa plaza la controla erplora.com.
Si falla: «Tu plan tiene todas las plazas ocupadas. Da de baja a alguien que ya no trabaje aquí, o pasa a un plan con más plazas.».
Implicados: HUB_SHELL-F83, REC_ALTA-F15, SAAS_DASHBOARD-F13, SAAS_DASHBOARD-F53, SAAS_DASHBOARD-F58
QA: ninguno

### HUB-F148 Cambiar el nombre, el rol, el PIN, la placa o el correo de una persona
Estado: parcial — el freno de 30 intentos por hora de quien edita no para a quien va despacio (29 cada hora no bloquean nunca, unos 700 al día) y los intentos no dejan rastro: con tiempo se sigue pudiendo averiguar el PIN de otra persona (ERPlora/hub#2526)
Actor: administrador
Pantalla: HUB_SHELL: Empleados
Pasos:
1. En **Empleados → Personal**, el administrador abre la ficha.
2. Cambia lo que haga falta: nombre, rol, PIN («Escribe un PIN nuevo para cambiarlo; déjalo en blanco y se queda como está»), placa o correo de acceso.
3. Guarda.
4. El rol nuevo vale desde la siguiente acción de esa persona, también en sesiones ya abiertas, y sus pantallas abiertas pierden el canal de avisos en vivo y lo vuelven a abrir con el rol nuevo (HUB-F60, ERPlora/hub#2571).
Entra: la sesión de administrador; los campos que cambian (solo esos).
Sale: la ficha. El orden depende del cambio: lo que concede (rol, correo, reincorporación) se pide primero a erplora.com y solo después se escribe aquí; el nombre, el PIN y la placa no se cuentan a erplora.com y funcionan aunque no conteste. El correo con el que se habla con erplora.com es el de acceso o, si no lo hay, el del perfil de la persona (HUB-F143). Una edición que trae PIN gasta un intento del presupuesto de **quien edita**, compartido con el alta (HUB-F145) y con el cambio del propio PIN (HUB-F132), sea cual sea la ficha: así nadie averigua en unos minutos el PIN de un compañero, el del dueño incluido, probando números en otra ficha (ERPlora/hub#2518); yendo despacio todavía se puede (ERPlora/hub#2526). Lo que no lleva PIN (nombre, rol, correo, baja) no gasta ni se frena. La edición **no** repite la guarda del alta local: un administrador puede subir a administrador a una persona que solo tiene PIN, y desde ese momento ese PIN abre una sesión de administrador (ver huecos).
Si falla: la ficha del dueño de la cuenta solo la cambia él, PIN incluido («Esta es la ficha del dueño de la cuenta y solo él puede cambiarla…»); nadie se da de alta su propia placa («Nadie da de alta su propia placa. Pídeselo a otro administrador.», salvo el dueño); la placa no puede quedar como única forma de entrar («La placa no puede ser su única vía de entrada…»); quitar el rol de administrador al último que queda, «No puedes dar de baja al último administrador…»; un rol de un módulo que está apagado, «Ya no se puede asignar «{role}».»; PIN o correo repetidos, los avisos de HUB-F132 y HUB-F146; con el presupuesto de intentos de PIN gastado, 429 `too_many_attempts` con los segundos que faltan, sin mirar el número ni escribir nada.
Implicados: HUB_SHELL-F84, HUB_SHELL-F85, HUB_SHELL-F86, HUB_SHELL-F87, HUB_SHELL-F92, STAFF-F03
QA: qa-hub-restaurant §7.02

### HUB-F149 Dar de baja y reincorporar a una persona
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Empleados
Pasos:
1. En **Empleados → Personal**, el administrador elige «Dar de baja» en la fila y confirma («Perderá el acceso al Hub, pero su historial se conserva.»).
2. El hub la desactiva, cierra sus sesiones y sus canales de avisos en vivo al momento (HUB-F60, ERPlora/hub#2571) y, si tenía cuenta, pide a erplora.com que le quite la membresía.
3. Para volver a contar con ella, abre su ficha y la reactiva: vuelve la misma persona, con su historial, si queda plaza.
Entra: la sesión de administrador; la persona.
Sale: la ficha desactivada (nunca borrada: ventas, aprobaciones y auditoría siguen nombrándola), sus sesiones borradas, y fuera del pinpad y de la lista de personas activas; la membresía retirada en erplora.com. Cerrar la puerta va primero en local y no depende de que erplora.com conteste. Reactivar pide plaza (HUB-F147) y la membresía otra vez, y erplora.com le vuelve a mandar el correo de invitación. La baja no toca las llaves de máquina del negocio: si esa persona, siendo dueña o administradora, acuñó una con la puerta de alta de dispositivo de erplora.com (que el hub no usa), sigue valiendo. Si la persona no tiene correo de acceso, la baja quita en erplora.com la membresía del correo de su perfil (HUB-F143). La comprobación del último administrador se hace antes de llamar a erplora.com y la escritura después: dos bajas o degradaciones simultáneas pueden dejar el negocio sin administrador (ver huecos). La revocación desde erplora.com (HUB-F144) tampoco mira si es el último.
Si falla: «No puedes darte de baja a ti mismo ni dejar el Hub sin ningún administrador.»; la ficha del dueño no la da de baja nadie más. Si erplora.com no contesta al quitar la membresía, la baja local se queda y la respuesta lo dice; esa persona no podrá entrar en el hub, pero sigue siendo miembro allí hasta que se repita.
Implicados: HUB_SHELL-F88, HUB_SHELL-F89, STAFF-F03, SAAS_AUTH-F22, SAAS_DASHBOARD-F16, SAAS_DASHBOARD-F61
QA: qa-hub-restaurant §7.02

### HUB-F150 Ver los roles y encender los que trae un módulo
Estado: parcial — el dueño no puede crear un rol propio ni cambiar qué permite cada rol: los roles y sus permisos los fijan los módulos instalados, y solo se encienden o apagan los que declara un módulo
Actor: administrador
Pantalla: HUB_SHELL: Empleados
Pasos:
1. En **Empleados → Roles** se ven los roles del negocio: los tres de fábrica (administrador, responsable —en pantalla, «Encargado»— y empleado; el catálogo puede traer además «Propietario», un rol antiguo que sale como «App desinstalada»), los que declaran los módulos instalados y cualquiera que ya tenga alguien, con sus permisos y sus miembros.
2. Un rol que trae un módulo (camarero, cocina…) se enciende para poder asignarlo.
3. Desde entonces aparece entre los roles al dar de alta o editar a una persona.
Entra: la sesión (leer, cualquiera; encender o apagar, administrador); los roles y permisos que declaran los módulos activos.
Sale: el rol encendido o apagado, con quién lo hizo (`hub_role_activation`). Los permisos de un rol son la suma de lo que le conceden los módulos activos con esa misma clave (un rol que «deriva» de responsable o empleado no hereda sus permisos); el administrador además administra el hub y toda sesión puede ver al personal. Un rol de un módulo no abre las puertas de administración del hub (miran el rol), pero si un manifiesto le concede `*`, ese comodín pasa todos los permisos, también los del núcleo (hoy ningún módulo publicado lo hace; el instalador no lo impide). Una plantilla del negocio también puede encender roles al importarse, por la misma puerta.
En este mismo documento se apoya en: HUB-F19 (Instalar una aplicación del catálogo), HUB-F20 (Rechazar un paquete que rompe las reglas del hub).
Si falla: los roles de fábrica no se apagan («immutable»); no se puede encender un rol que ningún módulo declara («unknown»); sin ser administrador, el aviso de permiso de la pestaña.
Implicados: HUB_SHELL-F91, REC_ALTA-F15
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
En este mismo documento se apoya en: HUB-F01 (Leer datos de un módulo), HUB-F03 (Ejecutar una orden de un módulo).
Si falla: no hay frase genérica en español para `permission_denied`: cada pantalla pinta su propio aviso de permiso.
Implicados: FLOWS-F01, HUB_SHELL-F193
QA: qa-hub-restaurant §6

### HUB-F152 Aprobar una acción con el PIN de un responsable
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: HUB_SHELL: Aprobación de un responsable
Pasos:
1. El cajero intenta algo que su rol no permite pero un responsable sí (un descuento por encima del límite, borrar una cuenta abierta): sale «Hace falta una aprobación» con «Se aprueba: {acción}». Solo se puede aprobar lo que el módulo concede expresamente al rol de responsable.
2. Un responsable o un administrador elige su nombre y teclea su PIN, o pasa su placa, sin cerrar la sesión del cajero.
3. El hub comprueba que esa persona existe, está activa, su PIN es correcto y **ella misma** podría hacer esa acción.
4. La acción se hace una sola vez, a nombre del cajero y aprobada por el responsable: «Aprobado por {name}».
Entra: la sesión del cajero; el nombre y PIN (o la placa) de quien aprueba; la orden exacta y sus datos.
Sale: un pase de un solo uso, válido 120 s, atado a ese negocio, ese cajero, esa orden y esos datos tal como los manda el cajero (aprobar un descuento del 25 % no sirve para uno del 60 %); no está atado a la sesión ni al dispositivo, sino al cajero. Vive en la memoria del proceso: un reinicio lo pierde y, durante un despliegue con dos copias del hub, no sirve en la otra. El pase se gasta y el recibo (quién pidió, quién aprobó, qué orden y permiso, una huella de los datos, fecha y si fue PIN o placa, con el índice de la placa) se escribe en el control de permisos, **antes** de validar los datos, aplicar las normas del dueño (HUB-F154) y lo fiscal: si la orden falla después, hay que pedir otra aprobación y el recibo queda. Sin recibo no se ejecuta. El SQL del módulo recibe el id del cajero y el id de quien aprobó (`:approved_by`), no sus nombres; un manejador WASM no recibe `approved_by`.
Si falla: nombre desconocido, PIN erróneo o persona de baja dan el mismo aviso, «Esos datos no aprueban esto. Revisa el nombre y el PIN, y vuelve a intentarlo.»; quien aprueba no puede hacerlo él mismo, «Esa persona no puede aprobarlo…»; lo que solo hace un administrador (identidad fiscal, plan, instalar apps), «Esto no se aprueba con un PIN…»; si el cajero ya tiene permiso, «Esto ya no necesita aprobación…». Cinco PIN erróneos con el mismo nombre lo frenan 5 minutos; esta puerta no tiene freno por dirección (HUB-F135).
Implicados: HUB_SHELL-F51, HUB_SHELL-F93, SALES-F14, SALES-F18
QA: qa-hub-restaurant §6

### HUB-F153 Consultar quién aprobó qué
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Empleados
Pasos:
1. El administrador abre **Empleados → Aprobaciones**.
2. Ve cada acción que necesitó el PIN de un responsable: cuándo, quién la pidió, quién la autorizó y el código de la orden y del permiso.
3. Busca por persona o acción; las personas dadas de baja siguen saliendo con su nombre.
Entra: la sesión de administrador (permiso de administrar el hub).
Sale: nada; es una lectura paginada del registro de aprobaciones (`hub.approvals.list`). Nadie puede editar ni borrar una fila; el hub las poda solo a los cuatro años.
En este mismo documento se apoya en: HUB-F253 (Purgar el historial por retención).
Si falla: «No se pudo cargar el registro de aprobaciones.»; vacío, «Todavía nadie ha tenido que autorizar nada en este Hub.».
Implicados: HUB_SHELL-F93
QA: ninguno

### HUB-F154 Escribir una norma propia del negocio
Estado: parcial — no hay pantalla (solo la API del hub con sesión de administrador); el desenlace «que lo apruebe un responsable» se rechaza porque aún no existe (hub#1710), solo «bloquear»
Actor: administrador
Pantalla: asistente
Pasos:
1. El administrador consulta qué puntos de control ofrecen los módulos instalados (por ejemplo, poner un descuento) y qué datos se pueden comparar en cada uno.
2. Escribe la norma: la condición («descuento mayor que 20»), el mensaje que verá quien choque con ella y si está en prueba o en vigor.
3. En prueba, el hub solo escribe una línea en el registro del proceso con lo que habría bloqueado, sin impedir nada (no queda guardado ni se ve en ninguna pantalla); en vigor, la orden que la cumple no se ejecuta y se ve el mensaje del dueño.
4. La norma se cambia, se apaga o se borra cuando se quiera.
Entra: la sesión de administrador (nunca una llave ni la máquina); los puntos de control que declara cada módulo; la condición en el mismo lenguaje de las automatizaciones.
Sale: la norma (`_policy`, con quién la creó, cambió o borró; el borrado es lógico), como mucho 20 por punto de control. Al llegar una orden, el hub la evalúa después de completar los datos y antes de ejecutarla; una norma solo puede restringir, nunca conceder.
En este mismo documento se apoya en: HUB-F03 (Ejecutar una orden de un módulo), HUB-F19 (Instalar una aplicación del catálogo).
Si falla: una orden bloqueada responde `policy.blocked` con el mensaje del dueño. Si a la orden le falta un dato que la norma necesita, el hub **deniega**. Una norma con el desenlace de aprobación se rechaza al guardarla (501).
Implicados: ninguno
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
Sale: la llave (`hub_api_key`) con su secreto guardado como huella, quién la creó y cuándo se usó por última vez. Los modos generales cubren también las apps que se instalen después. No caduca, y sigue viva aunque a quien la creó lo den de baja o le quiten la administración (`created_by` es solo auditoría). Revocar no la borra (queda «Revocada»). La llave «ERPlora app», que el hub se emite para leer sus propios avisos en vivo, no se rota ni se revoca.
En este mismo documento se apoya en: HUB-F60 (Avisar a las pantallas en vivo).
Si falla: «No se pudo crear la API key.»; la llave del sistema, «Esta clave la emite ERPlora para sí misma. No se puede rotar ni borrar.»; sin ser administrador, «Solo el propietario o un administrador puede gestionar las claves de API.». Rotar una llave revocada la vuelve a dejar activa.
Implicados: HUB_SHELL-F94, HUB_SHELL-F95, HUB_SHELL-F96, HUB_SHELL-F97
QA: ninguno

### HUB-F156 Leer y escribir datos del negocio con una llave de API
Estado: parcial — la operación se comprueba antes que la llave, así que sin llave se puede averiguar qué operaciones hay publicadas (ERPlora/hub#2550), y esta puerta no comprueba el plan contratado
Actor: sistema
Pantalla: ninguna
Pasos:
1. Un sistema externo (la gestoría, una tienda online) llama al hub con su llave.
2. Pide una consulta o una orden de un módulo por su nombre.
3. El hub comprueba, por este orden: que el módulo publica esa operación para terceros (antes de mirar la llave), que la llave existe y está activa, que no ha pasado su límite por minuto (el intento cuenta aunque luego falte permiso) y que la llave tiene el permiso.
4. Contesta igual que a la pantalla, y lo que escribe queda a nombre de la llave.
Entra: la llave en `Authorization: Bearer erpl_live_…`; la operación (`/api/v1/<módulo>/q/<consulta>` o `/c/<orden>`).
Sale: la respuesta del módulo; las escrituras con autor `apikey:<id>`; el último uso de la llave. La llave no ve al personal ni puede pedir aprobaciones, y no sirve en las puertas de la pantalla.
En este mismo documento se apoya en: HUB-F01 (Leer datos de un módulo), HUB-F03 (Ejecutar una orden de un módulo), HUB-F15 (Consultar qué órdenes y consultas acepta el hub).
Si falla: operación que el módulo no publica o no existe, 404 (las dos igual), también sin llave: un anónimo distingue así una operación publicada (401) de una que no (404); llave desconocida o revocada, 401; sin permiso, `permission_denied`; pasado el límite, `rate_limited` (429) con `Retry-After`.
Implicados: HUB_SHELL-F97
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
En este mismo documento se apoya en: HUB-F221 (Cambiar los ajustes del negocio).
Si falla: apagada, 404; sin sesión o con una llave, 401. La pantalla dice «No se pudo cargar la documentación» con «Reintentar».
Implicados: HUB_SHELL-F98
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
Implicados: HUB_SHELL-F80, KITCHEN-F10, STAFF-F01, STAFF-F03
QA: ninguno

## Cobertura contra la referencia

| Elemento | Estado | Flujo |
|---|---|---|
| Personas locales con PIN | hecho | HUB-F145 |
| Personas con cuenta e invitación | parcial (no se puede reenviar una invitación fallida) | HUB-F146 |
| Tope de plazas del plan | parcial (la reincorporación avisa a erplora.com antes del tope) | HUB-F147 |
| Ficha del dueño protegida | hecho | HUB-F148 |
| Baja sin borrado y reincorporación | hecho | HUB-F149 |
| Último administrador protegido | hecho | HUB-F148, HUB-F149 |
| Roles de fábrica | hecho | HUB-F150 |
| Roles propios del dueño y editar permisos por rol | no hecho | HUB-F150 |
| Rechazo sin permiso con oferta de aprobación | hecho | HUB-F151 |
| Aprobación del responsable por acción (PIN o placa) | hecho | HUB-F152 |
| Registro de aprobaciones | hecho | HUB-F153 |
| Normas del dueño: bloquear | parcial (sin pantalla) | HUB-F154 |
| Normas del dueño: «lo aprueba el encargado» | no hecho (hub#1710) | HUB-F154 |
| Llaves de API con permisos por módulo, límite por minuto | hecho | HUB-F155, HUB-F156 |
| Caducidad de una llave | no hecho | — |
| Documentación OpenAPI | hecho | HUB-F157 |

## Datos: de quién es cada dato

Las tablas de toda el área están en [acceso.md](acceso.md). Inventario de datos personales de
cuentas, roles, aprobaciones, normas y llaves (sacado de las migraciones de sistema):

| Dónde | Qué |
|---|---|
| `hub_role_activation` | `activated_by` |
| `_elevation_audit` | quién pidió y quién aprobó (ids), huella de los datos, índice de la placa; se conserva 4 años y no se borra a petición |
| `hub_api_key` | `created_by` |
| `_policy` | `created_by`, `updated_by`, `deleted_by` |

No hay borrado RGPD de empleados: la baja desactiva y conserva (HUB-F149; ver la duda común del
índice y HUB-F252).

## Reglas que no se rompen

- El **alta** de un usuario local no admite rol de administrador (la edición sí lo deja: hueco D1).
  Las puertas de administración del hub miran el **rol**, nunca la credencial: un administrador con
  PIN entra por el pinpad con sesión de administrador; solo el pase a erplora.com exige la cuenta.
  Un rol declarado por un módulo no abre esas puertas (salvo un `*` en el manifiesto, hueco D10).
- Nadie se da de baja a sí mismo; Personal rechaza dejar el negocio sin un administrador activo (no
  lo impiden la revocación desde erplora.com ni dos cambios simultáneos: D11); la ficha del dueño
  solo la toca el dueño; nadie da de alta su propia placa (salvo el dueño); nadie reparte un rol
  por encima del suyo.
- Personal nunca borra a una persona: la desactiva y borra sus sesiones. El restablecimiento del hub
  (HUB-F242, negocio y datos) sí borra las fichas, sin avisar a erplora.com (D12).
- La aprobación con PIN vale para una sola ejecución de esa orden con esos datos, 120 s como mucho,
  solo la da quien podría hacerlo, vive en la memoria de un proceso y su recibo se escribe (y el pase
  se gasta) en el control de permisos, antes de ejecutar.
- Una norma del dueño solo restringe, y si no puede evaluarse deniega.
- Las plazas del plan se piden en la misma escritura que da de alta.

## Lo que NO hace, a propósito

- No manda la invitación: el correo lo manda erplora.com.
- No deja que el dueño cree roles ni cambie lo que permite cada uno: eso lo declaran las apps.
- No persiste una aprobación en base de datos.

## Dudas abiertas

- **¿Puede un usuario solo-PIN ser administrador?** El alta lo prohíbe y la edición lo permite (D1):
  hay que decidir cuál de las dos es la regla y aplicarla en las dos puertas.
- **Revocar una llave «no se puede deshacer»** según la pantalla, pero «Rotar» la vuelve a activar.
- **Aprobación durante un despliegue**: el pase vive en un proceso; con dos copias del hub (o tras
  un reinicio) hay que volver a pedirlo.
- El borrado RGPD de un empleado está en las dudas comunes del índice.

## Fuentes contrastadas

- `architecture/hub/public-api.md` §4 dice que la documentación no devuelve 404 cuando está apagada y
  que el interruptor es local; hoy es un ajuste del servidor (`api_docs_enabled`, apagado de fábrica)
  y apagado responde 404 (HUB-F157).
- `crates/runtime/src/hub_users.rs` (comentario cerca de la l. 1420) dice «no soft-delete»; la baja sí
  es desactivación (HUB-F149).
- `crates/server/src/members.rs` (`census_id_by_access_email`, comentario) dice que el correo del
  perfil no decide; la lista de Personal (`COALESCE`, `crates/runtime/src/hub_users.rs:741-747`) sí lo
  usa para hablar con erplora.com cuando no hay correo de acceso.
- El aviso de Personal ante una invitación fallida dice «vuelve a guardar»; guardar sin cambios no
  reenvía nada (`crates/server/src/hub_users.rs:448-459`) (HUB-F146).
