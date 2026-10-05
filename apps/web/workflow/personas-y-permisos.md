# WORKFLOW — Hub (pantallas) · Personas y permisos

Prefijo: HUB_SHELL

> Detalle del área «Personas y permisos» (oleada 3): lo que ve y hace quien administra a las
> personas del negocio desde el menú **Empleados** (pestañas Personal, Roles, API keys y
> Aprobaciones), la **Documentación de la API**, y las dos tarjetas de **Ajustes › General** que
> deciden cómo entra la gente: **Pinpad** (si se pide PIN y cuántos dígitos) y **Dispositivos**. Aquí
> se cuenta lo que ve la persona; qué hace el servidor detrás de cada gesto está en
> `hub-wf-acceso/workflow/personas-y-permisos.md` (HUB-F145…F158) y no se repite. El módulo
> **Personal** (`staff`) es otra cosa: su ficha de profesional se vincula a las cuentas que se crean
> aquí. Código: `apps/web/src/views/Employees*.vue`, `RolesPanel.vue`, `ApiKeysPanel.vue`,
> `ApprovalsPanel.vue`, `ApiDocsPage.vue`, `components/PinPolicyCard.vue`, `DevicesCard.vue` y
> `lib/hub-users.ts`, `approvals.ts`, `api-keys.ts`, `devices.ts`, `pinpad-dial.ts`, `badge-scanner.ts`,
> `nfc-badge.ts`.

## Flujos

### HUB_SHELL-F80 Ver la lista de personas del negocio
Estado: parcial — con la lista caída, bajo el aviso de error la tabla sigue diciendo «Aún no hay nadie más en este Hub.», que parece un hecho sobre el negocio (leído en el código, sin ejecutar)
Actor: administrador, responsable, empleado
Pantalla: Empleados
Pasos:
1. La persona pulsa **Empleados** en el menú lateral (la entrada la ve todo el mundo) y se abre la pestaña **Personal**. Una dirección con `#roles`, `#apikeys` o `#approvals` abre esa pestaña directamente.
2. Mientras llega la lista sale un indicador de carga. Después, una tabla con una fila por persona, activa o de baja: «Usuario» (con su inicial), «Email», «Rol», «Acceso», «Estado» («Activo» o «De baja») y «Alta».
3. Puede buscar en «Buscar usuario…», filtrar por rol, estado y fecha de alta, elegir columnas y exportar la tabla a un CSV llamado `personal`.
4. Un administrador ve además el botón de añadir (HUB_SHELL-F81) y, en cada fila, «Editar» y «Dar de baja». El resto lo ve en solo lectura.
Entra: la lista de personas y la de roles, pedidas a la vez al hub; la sesión.
Sale: nada guardado. Esa misma lista (identificador, nombre, rol y si está activa) es la que los módulos piden para nombrar a quien atiende o a quien envió una comanda; el correo y la forma de entrar no viajan a ellos (HUB-F158).
Si falla: si falla cualquiera de las dos lecturas, sale «No se pudo cargar el personal» con «El Hub no respondió con la lista de usuarios. Vuelve a intentarlo.» y el botón «Reintentar»; el botón de añadir desaparece hasta que cargue. Una lista realmente vacía dice «Aún no hay nadie más en este Hub.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F158 (dar la lista de personas del negocio a los módulos)
Pendiente de enlazar: kitchen — KITCHEN-F10 (la cocina nombra a quien envió la comanda con esta lista)
Pendiente de enlazar: staff — STAFF-F03 (las cuentas activas que se ofrecen al vincular una ficha de profesional)
QA: qa-hub-restaurant §6

### HUB_SHELL-F81 Dar de alta a una persona que entra solo con PIN
Estado: hecho
Actor: administrador
Pantalla: Empleados
Pasos:
1. En **Empleados › Personal**, el administrador pulsa el botón de añadir de la tabla: se abre un panel «Nuevo» con el formulario.
2. Escribe «Nombre y apellidos» (hasta 150 caracteres) y activa «Usuario local». El campo de email desaparece y el texto del interruptor lo explica: trabaja en este hub solo con un PIN, sin email y sin cuenta de ERPlora.
3. Elige el «Rol» entre los que se pueden asignar hoy (los de fábrica y los de las apps cuyo rol está encendido, HUB_SHELL-F91) y teclea el «PIN local»: solo dígitos, tantos como pida el negocio (4 o 6), enmascarado y con un ojo para verlo. Bajo el campo: «{n} dígitos. Obligatorio: es cómo entra esta persona.».
4. Pulsa «Crear» (se apaga mientras falte el nombre o haya un fallo evidente, y mientras guarda dice «Guardando…»).
5. El panel se cierra, la lista se recarga con la persona nueva y sale el aviso «Usuario creado.». La casilla «Usuario local» se queda como estaba para dar de alta a la siguiente.
Entra: nombre, rol y PIN (más la casilla); la lista de personas ya cargada, para adelantar los fallos evidentes.
Sale: pide al servidor el alta (HUB-F145); el panel solo adelanta lo que ya puede saber (PIN vacío, de otra longitud, fácil, rol de administrador, nombre repetido). Una placa no se puede dar de alta desde este panel, solo desde la ficha (HUB_SHELL-F87).
Si falla: el motivo sale dentro del panel, en rojo, y lo tecleado se conserva. «Un usuario local entra con un PIN: sin él, nadie podría usar esta ficha.», «El PIN debe tener {n} dígitos.», «Ese PIN se adivina a la primera: evita los dígitos repetidos (1111) y las cuestas seguidas (1234).», «Un usuario local no puede administrar el hub: administrar sale de una cuenta de ERPlora, nunca de un PIN.», «Este hub ya conoce a alguien con ese nombre. Edita a ese usuario —reincorpóralo si estaba dado de baja— en vez de crear una segunda identidad.» y, solo cuando responde el servidor, «Ese PIN ya lo tiene otro usuario activo. El PIN dice quién está en la caja, así que no lo pueden compartir dos personas.». Un rechazo que la pantalla no sabe traducir sale con la frase que mandó el servidor.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F145 (dar de alta a una persona que entra solo con PIN)
Pendiente de enlazar: staff — STAFF-F01 (la ficha de profesional que luego se vincula a esta cuenta)
QA: qa-hub-restaurant §6

### HUB_SHELL-F82 Invitar a una persona con su cuenta de erplora.com
Estado: parcial — «Crear» se queda apagado mientras falte un email válido sin decir por qué (el aviso de email que falta espera a pulsar «Crear», y apagado no se pulsa); y si la invitación no sale (erplora.com no contesta, la rechaza o frena), el servidor ya ha guardado la ficha pero el panel se queda abierto, no recarga la lista y el aviso manda a «volver a guardar»: un segundo guardado se rechaza con «Este hub ya conoce ese email» (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Empleados
Pasos:
1. En **Empleados › Personal**, el administrador abre el panel de añadir y deja «Usuario local» sin marcar.
2. Escribe el nombre y el «Email». Bajo el email: «Le mandamos por email una invitación a este hub. La contraseña la elige él: tú no la ves nunca.».
3. Elige el «Rol». A una cuenta solo se la puede invitar como administrador, encargado o empleado; un rol que trae una app es del personal local.
4. Si trabaja en una caja compartida, teclea además un PIN: «Opcional: {n} dígitos. Solo si además atiende una caja compartida de este hub.».
5. Pulsa «Crear». El panel se cierra, la lista se recarga y sale «Usuario creado.»; en la columna «Acceso» la persona sale como «Cuenta online» (o «PIN local» si tiene PIN).
Entra: nombre, email, rol y PIN opcional; la lista ya cargada (para adelantar «email repetido» antes de enviar).
Sale: pide al servidor el alta de la ficha y que erplora.com mande la invitación (HUB-F146). La pantalla adelanta el email repetido y el rol que una cuenta no admite mientras se teclea.
Si falla: «Un usuario de cuenta entra con su cuenta de ERPlora, así que el email es obligatorio. Marca «Usuario local» para dar de alta a quien trabaja en este hub con un PIN.», «Introduce un email válido.», «A una cuenta de ERPlora solo se la puede invitar como admin, manager o employee. Los roles que añade un módulo son del personal local.», «Este hub ya conoce ese email. Edita a ese usuario —reincorpóralo si estaba dado de baja— en vez de invitar una segunda identidad.», «No puedes repartir un rol por encima del tuyo: administrar el hub solo lo concede quien ya lo administra.». Si falla la invitación: «No hemos podido conectar con ERPlora para enviar la invitación. El usuario queda guardado aquí: vuelve a guardar dentro de un momento.», «No se ha podido crear la invitación para ese email. Revisa la dirección y vuelve a intentarlo; si sigue fallando, avisa a soporte.», «Demasiados cambios en poco tiempo: la invitación todavía no ha salido. Espera unos minutos y vuelve a guardar — no se ha perdido nada más.» o «Este hub todavía no puede enviar invitaciones. El usuario queda guardado aquí; avisa a soporte para que termine de configurarlo.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F146 (invitar a una persona con su cuenta de erplora.com)
Pendiente de enlazar: staff — STAFF-F01 (la cuenta que luego se vincula a la ficha de profesional)
QA: qa-hub-restaurant §6

### HUB_SHELL-F83 Llegar al tope de personas del plan
Estado: parcial — la salida «Actualizar plan» solo sale en la ficha completa de la persona; el panel de alta rápida de la tabla (por donde se da de alta casi siempre) da la frase sin botón (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Empleados
Pasos:
1. El plan admite un número de personas activas. El administrador intenta dar de alta, invitar o reincorporar a alguien con todas las plazas ocupadas.
2. El hub lo rechaza y la pantalla dice: «Tu plan tiene todas las plazas ocupadas. Da de baja a alguien que ya no trabaje aquí, o pasa a un plan con más plazas.».
3. En la ficha completa de la persona, bajo la frase aparece el botón «Actualizar plan», que abre en el navegador la página de cambio de plan de este hub en erplora.com, ya identificado (HUB_SHELL-F129). No sale en una copia repartida por Google Play ni con un fallo que no sea el tope.
4. Dar de baja a alguien libera su plaza al momento; el administrador vuelve a guardar.
Entra: el rechazo del servidor por plazas (`user_limit_reached`); la distribución de la copia (Play o no) que da el dispositivo.
Sale: nada guardado. El servidor decide el tope y lo aplica en el mismo paso que escribe (HUB-F147); la pantalla no cuenta plazas por su cuenta. Cuántas plazas hay usadas se ve en **Sistema › Plan y límites** (HUB_SHELL-F128), que avisa con «Tu plan tiene todas las plazas ocupadas, así que no puedes añadir a nadie más.» sin botón.
Si falla: si no se puede abrir el navegador, «No se pudo abrir tu navegador. Entra en erplora.com para gestionar tu plan.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F147 (llegar al tope de plazas del plan)
QA: ninguno

### HUB_SHELL-F84 Cambiar el nombre, el correo, el rol o el estado de una persona
Estado: parcial — la ficha completa ofrece en «Rol» todos los roles, también los de una app que está apagada; el servidor los rechaza y la frase manda a «Ajustes → Roles», que no existe (los roles se encienden en Empleados › Roles); y al dueño de la cuenta la baja desde la tabla le contesta «No puedes darte de baja a ti mismo…», que no es el motivo
Actor: administrador
Pantalla: Ficha de usuario
Pasos:
1. En **Empleados › Personal**, el administrador pulsa «Editar» en la fila: se abre la **Ficha de usuario** («Editar usuario»).
2. Cambia lo que haga falta: «Nombre y apellidos», «Email» (solo en una persona con cuenta), «Rol» y la casilla «Usuario activo». Los cambios de PIN y de placa son HUB_SHELL-F85 a F87.
3. Pulsa «Guardar». Solo viaja lo que ha cambiado. Sale «Usuario actualizado.» y vuelve a la lista.
4. Si hay cambios sin guardar y el administrador pulsa «Cancelar» o sale de la ficha, la pantalla pregunta «Cambios sin guardar» («Si sales ahora perderás los cambios realizados.») con «Seguir editando» y «Descartar cambios».
Entra: la ficha cargada desde la lista de personas y de roles; los campos que cambian.
Sale: pide al servidor la edición (HUB-F148). El rol nuevo vale desde la siguiente acción de esa persona.
Si falla: sin la ficha, «No se pudo abrir el usuario» con «El registro no está disponible o no tienes permiso para consultarlo.» y «Reintentar»; «Usuario no encontrado.» si ya no está en la lista. La ficha del dueño de la cuenta solo la abre él: a otro administrador la tabla le avisa «La ficha del dueño de la cuenta solo la cambia él. Para traspasar el negocio, transfiere la cuenta en ERPlora.» y no abre el formulario (si llegara, «Esta es la ficha del dueño de la cuenta y solo él puede cambiarla…»). Un rechazo por campo sale bajo el campo que lo causó (nombre, email, PIN o placa) y cualquier otro en el banner de arriba. Sin conexión con erplora.com al cambiar rol o email: los avisos «cloud_*» de HUB_SHELL-F82.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F148 (cambiar el nombre, el rol, el PIN, la placa o el correo de una persona)
Pendiente de enlazar: staff — STAFF-F03 (el rol de permisos y el PIN son de la cuenta, no de la ficha de profesional)
QA: qa-hub-restaurant §6

### HUB_SHELL-F85 Poner o cambiar el PIN de otra persona
Estado: hecho
Actor: administrador
Pantalla: Ficha de usuario
Pasos:
1. En la ficha de la persona, el administrador mira el campo «PIN local». Si ya tiene PIN, el campo sale vacío y dice: «Escribe un PIN nuevo para cambiarlo; déjalo en blanco y se queda como está.». El PIN actual no se enseña nunca, ni enmascarado: la pantalla solo sabe si lo hay.
2. Teclea el PIN nuevo: solo dígitos, tantos como pida el negocio, enmascarado, con teclado numérico, sin que el navegador lo autocomplete y con un ojo para verlo mientras se escribe.
3. Pulsa «Guardar».
4. En la lista, la columna «Acceso» de esa persona dice «PIN local» (o «PIN + placa»).
Entra: el PIN nuevo; el número de dígitos del negocio, que sale del arranque de la pantalla.
Sale: pide al servidor la edición con solo el PIN (HUB-F148); la pantalla comprueba la longitud y los PIN fáciles antes de enviar, pero que otro usuario activo ya lo tenga solo lo sabe el servidor. Cambiar la longitud del negocio (HUB_SHELL-F100) no toca los PIN ya puestos. El PIN de uno mismo se cambia en **Mi perfil** (acceso y navegación), no aquí.
Si falla: «El PIN debe tener {n} dígitos.», «Ese PIN se adivina a la primera: evita los dígitos repetidos (1111) y las cuestas seguidas (1234).», «Ese PIN ya lo tiene otro usuario activo…»; bajo el campo, no en un banner. El PIN del dueño de la cuenta no lo cambia nadie más («Esta es la ficha del dueño de la cuenta y solo él puede cambiarla, PIN incluido…»).
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F148 (cambiar el nombre, el rol, el PIN, la placa o el correo de una persona)
Pendiente de enlazar: hub — HUB-F132 (alta del PIN tras el primer acceso y cambio del PIN propio en Mi perfil, HUB_SHELL, Mi perfil)
QA: qa-hub-restaurant §6

### HUB_SHELL-F86 Retirar el PIN a una persona
Estado: hecho
Actor: administrador
Pantalla: Ficha de usuario
Pasos:
1. En la ficha de una persona que ya tiene PIN aparece el botón «Retirar el PIN».
2. El administrador lo pulsa: el campo se vacía y el botón desaparece. No pide confirmación.
3. Pulsa «Guardar». Sin PIN, una persona con cuenta sigue entrando con ella; una persona local queda en la lista como «Sin acceso».
Entra: la ficha; nada más.
Sale: pide al servidor la edición con el PIN vacío (HUB-F148). Un campo vacío sin tocar nunca borra el PIN de nadie: solo viaja el vacío si se pulsó «Retirar el PIN».
Si falla: «La placa no puede ser su única vía de entrada: si pierde la tarjeta se queda fuera. Consérvale el PIN, dale una cuenta, o retira también la placa.» si la persona tiene placa y se queda sin PIN ni cuenta.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F148 (cambiar el nombre, el rol, el PIN, la placa o el correo de una persona)
QA: ninguno

### HUB_SHELL-F87 Dar de alta o retirar la placa de una persona
Estado: hecho
Actor: administrador
Pantalla: Ficha de usuario
Pasos:
1. En la ficha de la persona, el administrador mira el campo «Placa». Sin placa: «Pasa la tarjeta y se rellena sola: no hace falta hacer clic aquí antes. También puedes teclear el número, para un llavero o una etiqueta grabada.». En un aparato con lector NFC dentro de la app instalada: «Acerca la tarjeta a este aparato —o pásala por el lector— y se rellena sola…».
2. Pasa la tarjeta por el lector (que escribe como un teclado) o la acerca al aparato: el número aparece en el campo aunque el cursor no esté ahí. Si prefiere, lo teclea (4 a 64 caracteres: letras, dígitos, «-» y «_»).
3. Pulsa «Guardar». En la lista, la persona sale con «PIN + placa» o «Placa».
4. Para retirarla, en una ficha que ya tiene placa pulsa «Retirar la placa» y guarda. Retirar la placa no toca el PIN, y perder la tarjeta nunca deja a nadie fuera.
Entra: el número de la tarjeta, de la ráfaga del lector o del toque NFC (el mismo camino para las dos).
Sale: pide al servidor la edición con la placa (HUB-F148). La placa solo viaja si se ha tocado: guardar otro cambio no revoca la tarjeta. La captura de la ráfaga es global del shell y a la ficha le llega la última pantalla que escucha (acceso y navegación, HUB_SHELL, Acceso).
Si falla: «Una placa tiene entre 4 y 64 caracteres: letras, dígitos, «-» y «_».» (se avisa mientras se teclea y bloquea «Guardar»), «Esa placa ya la lleva otro usuario activo. La placa dice quién está en la caja, así que no la pueden compartir dos personas.», «Nadie da de alta su propia placa. Pídeselo a otro administrador.», «La placa no puede ser su única vía de entrada…».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F148 (cambiar el nombre, el rol, el PIN, la placa o el correo de una persona)
Pendiente de enlazar: hub — HUB-F134 (captura de la ráfaga del lector y lector NFC de Android, HUB_SHELL Acceso y HUB_APP)
QA: ninguno

### HUB_SHELL-F88 Dar de baja a una persona
Estado: parcial — desde la ficha, apagar «Usuario activo» y guardar da de baja sin la pregunta ni los avisos de la tabla; el servidor sigue rechazando lo que no debe (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Empleados
Pasos:
1. En **Empleados › Personal**, el administrador pulsa «Dar de baja» en la fila de la persona.
2. La pantalla pregunta «Dar de baja»: «Vas a dar de baja a «{name}». Perderá el acceso al Hub, pero su historial se conserva.», con «Cancelar» y «Dar de baja».
3. Confirma. Sale «Usuario dado de baja.» y la fila pasa a «De baja».
Entra: la persona; la sesión de administrador.
Sale: pide al servidor la baja (HUB-F149): se desactiva, nunca se borra, y sus sesiones se cierran. Antes de preguntar, la pantalla se niega si el servidor lo rechazaría, con el aviso «No puedes darte de baja a ti mismo ni dejar el Hub sin ningún administrador.»; el servidor revalida.
Si falla: «No se pudo dar de baja al usuario.» o la frase del servidor traducida: «No puedes dar de baja al último administrador. Nombra antes a otro dueño o administrador.», «No puedes darte de baja a ti mismo. Pídeselo a otro administrador.»; si erplora.com no contesta al quitar la membresía, la baja local se queda y la pantalla enseña el aviso «cloud_*» de HUB_SHELL-F82.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F149 (dar de baja y reincorporar a una persona)
Pendiente de enlazar: staff — STAFF-F03 (dar de baja la cuenta no toca la ficha de profesional)
QA: qa-hub-restaurant §6

### HUB_SHELL-F89 Reincorporar a una persona dada de baja
Estado: hecho
Actor: administrador
Pantalla: Ficha de usuario
Pasos:
1. En la lista, la persona sale con el estado «De baja». El administrador pulsa «Editar».
2. En la ficha enciende «Usuario activo» y pulsa «Guardar».
3. Vuelve la misma persona, con su historial; en la lista sale «Activo». Una persona con cuenta recibe de nuevo su membresía.
Entra: la ficha de la persona de baja.
Sale: pide al servidor la edición con el estado activo (HUB-F149); reactivar ocupa una plaza del plan.
Si falla: sin plazas, la frase y el botón «Actualizar plan» de HUB_SHELL-F83; si erplora.com no concede la membresía, los avisos «cloud_*» de HUB_SHELL-F82 y la persona sigue de baja.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F149 (dar de baja y reincorporar a una persona)
QA: ninguno

### HUB_SHELL-F90 Entender cómo entra cada persona
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Empleados
Pasos:
1. En la tabla de **Personal**, la columna «Acceso» dice por dónde puede entrar cada persona: «PIN local», «PIN + placa», «Placa», «Cuenta online» o «Sin acceso».
2. «Sin acceso» sale en rojo: es alguien dado de alta como persona que no puede iniciar sesión en el hub (por ejemplo, un profesional que solo existe en la agenda). Cuando hay varias vías manda el PIN.
3. Junto al email puede salir una etiqueta roja «Hay que decidir»: esa dirección parece buena y no administra nada, así que dar de baja a esa persona no le quita el acceso. Al pasar el ratón se lee la causa: «Otra persona ya entra con esta dirección, así que dar de baja a esta no revoca nada. Cambia el email de una de las dos.» o «Dos personas tienen esta dirección y nada dice cuál es. Dar de baja a esta no revoca nada. Quita la duplicada, o dale a una su propia dirección.».
4. El administrador arregla la causa desde la ficha de una de las dos (HUB_SHELL-F84).
Entra: la lista de personas con su marca de conflicto de correo.
Sale: nada guardado; la pantalla solo describe.
Si falla: sin la lista, HUB_SHELL-F80. La causa del conflicto solo se lee al pasar el ratón: en una tableta sin ratón no se ve el texto, solo la etiqueta (leído en el código, sin ejecutar).
Implicados: ninguno
QA: ninguno

### HUB_SHELL-F91 Ver los roles y encender los que trae una app
Estado: parcial — el dueño no puede crear un rol propio ni cambiar lo que permite cada rol: la pantalla solo enseña cuántos permisos y cuántos miembros tiene cada uno, y enciende o apaga los que declara una app
Actor: administrador, responsable, empleado
Pantalla: Empleados
Pasos:
1. En **Empleados › Roles** aparece una explicación («Estos son los roles que este Hub puede repartir. Los básicos están siempre; los que trae una app los enciendes tú cuando tu negocio los necesita.») y una tabla con una fila por rol: «Rol», «Viene de» («Básico», el nombre de la app que lo trae o «App desinstalada»), «Disponible», «Miembros» y «Permisos» (solo los números).
2. Los tres roles básicos (administrador, encargado y empleado) dicen «Siempre disponible» y su interruptor no se puede mover. Un rol que ya nadie declara pero alguien aún lleva sale como «App desinstalada» con «Ninguna app lo trae» y tampoco se puede mover: no hay nada que encender (un rol antiguo como «Propietario», si alguien lo lleva, sale así).
3. El administrador enciende un rol de una app: sale «Ya puedes asignar «{role}».» y desde ese momento aparece al dar de alta o editar a una persona. Al apagarlo: «Ya no se puede asignar «{role}».» (quien ya lo lleva lo conserva).
4. Quien no administra ve el interruptor apagado; si lo intentara: «Solo un administrador puede encender o apagar roles.».
Entra: el catálogo de roles que da el hub: los básicos, los que declaran las apps instaladas y los que alguien aún lleva.
Sale: pide al servidor encender o apagar el rol (HUB-F150) y pinta lo que este contesta, sin adelantarse. Un rol de una app nace apagado: instalar una app no le da a nadie un rol que no pidió.
Si falla: «No se pudo cargar el catálogo de roles.» con «Reintentar»; si el servidor rechaza el cambio, el motivo sale en un banner rojo (no en un aviso que desaparece) y se puede releer: «No se pudo cambiar «{role}».» si no dio motivo, o «Este rol viene con el hub: está siempre activo y no se puede apagar.» / «Ninguna app instalada declara este rol. Instala la app que lo trae o elige otro rol.». Sesión caducada: «Tu sesión ha caducado. Vuelve a entrar e inténtalo otra vez.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F150 (ver los roles y encender los que trae un módulo)
Pendiente de enlazar: hub — HUB-F20 (la validación de los roles que declara un módulo al instalarlo)
QA: qa-hub-restaurant §6

### HUB_SHELL-F92 Asignar un rol a una persona
Estado: parcial — la ficha completa enseña los roles de una app con su identificador (por ejemplo `kitchen`) y no con el nombre que declara la app, que sí sale en la pestaña Roles (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Empleados
Pasos:
1. Al dar de alta (HUB_SHELL-F81 y F82) o al editar (HUB_SHELL-F84), el administrador abre el desplegable «Rol».
2. En el alta rápida solo salen los roles que se pueden asignar hoy; en la ficha completa salen todos. Los tres de fábrica salen con su nombre («Administrador», «Encargado», «Empleado»); el de cajero lo trae el módulo de Venta y es uno más de los de app.
3. Para una persona con cuenta solo vale administrador, encargado o empleado; para el personal local vale cualquiera menos administrador (un PIN nunca administra el hub).
4. Guarda; el rol se ve en la columna «Rol» de la lista.
Entra: el catálogo de roles (HUB_SHELL-F91).
Sale: el rol en la ficha (HUB-F148). Repartir administración solo lo hace quien ya administra.
Si falla: «A una cuenta de ERPlora solo se la puede invitar como admin, manager o employee…», «Un usuario local no puede administrar el hub…», «No puedes repartir un rol por encima del tuyo…»; el rol apagado, «Este rol está apagado en este hub. Enciéndelo en Ajustes → Roles antes de asignarlo.» (la ruta correcta es Empleados › Roles).
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F148 (cambiar el nombre, el rol, el PIN, la placa o el correo de una persona)
QA: qa-hub-restaurant §6

### HUB_SHELL-F93 Consultar quién aprobó qué
Estado: parcial — las columnas «Acción» y «Nivel» enseñan los nombres técnicos de la orden y del permiso (por ejemplo `sales.void_line`), no una frase; y la explicación promete conservar el registro «mientras tu negocio esté en ERPlora» cuando el servidor lo poda a los cuatro años (HUB-F153, sin confirmar contra el código) (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Empleados
Pasos:
1. El administrador abre **Empleados › Aprobaciones** (la pestaña solo existe para administradores; sin esa sesión una dirección con `#approvals` vuelve a Personal).
2. Lee la explicación («Cada acción que necesitó el PIN de un encargado: quién la pidió, quién la autorizó y para qué se usó…») y la tabla: «Cuándo» (fecha y hora), «Autorizado por», «Lo pidió», «Acción» y «Nivel».
3. Busca por persona o acción en «Buscar por persona o acción…», filtra por fechas, acción o nivel, y ordena por fecha. Cada cambio vuelve a pedir una sola página al hub.
4. Si necesita demostrar cuál fue, abre el selector de columnas: «Referencia» (una huella de los datos) y los dos identificadores están ocultos y van en la exportación a CSV.
Entra: el registro de aprobaciones, paginado en el servidor; la sesión de administrador.
Sale: nada; es solo lectura y nadie puede editar ni borrar una fila. La pestaña no pide nada hasta que se abre. Aprobar o rechazar no se hace aquí: la aprobación se da en el momento, con el PIN de un responsable, en el diálogo que sale en la pantalla donde se intentó (vista de un módulo) y vale 120 s; este registro es solo el recibo.
Si falla: «No se pudo cargar el registro de aprobaciones.» con «Reintentar» (un fallo no se confunde con un registro vacío); sin nada, «Todavía nadie ha tenido que autorizar nada en este Hub.»; quien ya no existe sale como «Usuario dado de baja».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F153 (consultar quién aprobó qué)
Pendiente de enlazar: hub — HUB-F152 (aprobar una acción con el PIN de un responsable, HUB_SHELL vista de un módulo: diálogo de aprobación)
QA: qa-hub-restaurant §6

### HUB_SHELL-F94 Crear una llave de API y copiar su token
Estado: hecho
Actor: administrador
Pantalla: Empleados
Pasos:
1. En **Empleados › API keys** (solo administradores), pulsa «Nueva API key»: se abre una ventana «Nueva API key».
2. Escribe el «Nombre» (por ejemplo «Gestoría — facturas») y las «Peticiones por minuto» (de 1 a 10.000; trae 60).
3. En «Qué puede hacer esta key» elige «Acceso total», «Solo lectura», «Solo escritura» o «Por app» («Los modos generales cubren todas las apps de tu negocio, también las que instales después.»). Viene marcado «Por app»: sale una matriz «Permisos por módulo» con una fila por app instalada que publica API, y columnas «Lectura» y «Escritura» (con casilla de todos).
4. Pulsa «Crear key». Se apaga mientras falte el nombre, el límite no sea válido o, en «Por app», no haya ninguna casilla marcada.
5. Sale «API key creada» con el aviso «Copia el token ahora»: «Este es el único momento en que se muestra el secreto completo. Guárdalo en un lugar seguro; no se volverá a mostrar.». Pulsa «Copiar» (el botón dice «Copiado» dos segundos) y «Hecho».
Entra: nombre, límite y permisos; las apps instaladas con API pública.
Sale: pide al servidor crear la llave (HUB-F155) y recibe el token entero una sola vez; la lista se recarga. Cerrar la ventana sin copiarlo lo pierde: solo queda rotar (HUB_SHELL-F95).
Si falla: «No se pudo crear la API key.» (o la frase traducida del servidor); «No se pudo copiar al portapapeles.» si el navegador no deja copiar. Si no hay ninguna app con API: «Ningún módulo expone API todavía» y no se puede crear una llave «Por app». Si la lista de apps no se pudo leer, la ventana dice lo mismo, como si ninguna publicara API (leído en el código, sin ejecutar).
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F155 (crear, rotar y revocar llaves de API)
QA: ninguno

### HUB_SHELL-F95 Rotar una llave de API
Estado: parcial — «Rotar» actúa al primer toque, sin pregunta, aunque deja de valer el token anterior al momento y revocar sí pregunta (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Empleados
Pasos:
1. En la fila de una llave activa, el administrador pulsa el icono «Rotar».
2. La pantalla pide la rotación y enseña la misma ventana de HUB_SHELL-F94, «API key creada», con el token nuevo una sola vez.
3. Copia el token y lo pone en el sistema externo; el anterior ya no funciona.
Entra: la llave elegida.
Sale: pide al servidor un token nuevo (HUB-F155) y recarga la lista.
Si falla: «No se pudo rotar la API key.» o la frase traducida; la llave que emite ERPlora para sí misma dice «La emite ERPlora» en lugar de los iconos y «Esta clave la emite ERPlora para sí misma. No se puede rotar ni borrar.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F155 (crear, rotar y revocar llaves de API)
QA: ninguno

### HUB_SHELL-F96 Revocar una llave de API
Estado: hecho
Actor: administrador
Pantalla: Empleados
Pasos:
1. En la fila de una llave activa, el administrador pulsa el icono «Revocar».
2. La pantalla pregunta «Revocar API key»: «Vas a revocar «{name}». Cualquier sistema que use este token dejará de tener acceso de inmediato. Esta acción no se puede deshacer.».
3. Confirma con «Revocar». Sale ««{name}» revocada.» y la fila queda como «Revocada», sin iconos (una llave revocada no se rota ni se revoca otra vez).
Entra: la llave elegida.
Sale: pide al servidor revocar (HUB-F155); la llave no se borra.
Si falla: «No se pudo revocar la API key.» o la frase traducida («Esa clave ya no existe. Actualiza la lista y vuelve a intentarlo.»).
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F155 (crear, rotar y revocar llaves de API)
QA: ninguno

### HUB_SHELL-F97 Ver las llaves de API y qué puede cada una
Estado: hecho
Actor: administrador
Pantalla: Empleados
Pasos:
1. Al abrir **Empleados › API keys**, la tabla lista cada llave: «Nombre», «Token» (solo el comienzo), «Permisos» (el modo, o las apps con L de lectura y E de escritura), «Estado» («Activa» o «Revocada»), «Creada», «Último uso» (o «Nunca»), «Límite» (por ejemplo «60/min») y «Acciones».
2. Se puede buscar en «Buscar API key…».
Entra: la lista de llaves.
Sale: nada guardado. El token entero no se vuelve a ver.
Si falla: sin llaves: «Aún no hay API keys. Crea una para que un sistema externo pueda leer o escribir datos del Hub.». Si la lectura se rechaza, el mensaje ocupa el lugar de esa frase y dice por qué («Solo el propietario o un administrador puede gestionar las claves de API.», «Tu sesión ha caducado. Vuelve a entrar e inténtalo otra vez.» o «No se pudieron cargar tus claves de API. Vuelve a intentarlo en un momento.»): un fallo nunca se lee como «no hay llaves».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F155 (crear, rotar y revocar llaves de API)
Pendiente de enlazar: hub — HUB-F156 (leer y escribir datos del negocio con una llave de API)
QA: ninguno

### HUB_SHELL-F98 Consultar la documentación de la API
Estado: parcial — el texto de introducción manda a «Usuarios → API keys», que hoy es Empleados › API keys; y ante cualquier fallo la pantalla dice «Inicia sesión e inténtalo de nuevo», también cuando la causa es otra (leído en el código, sin ejecutar)
Actor: administrador, responsable, empleado
Pantalla: Documentación de la API
Pasos:
1. Un administrador enciende «Mostrar documentación de la API» en **Ajustes › General** (viene apagado): «Añade una página interna con la documentación de la API (Swagger) para integraciones».
2. Aparece la entrada **API** en el menú. Cualquier persona con sesión la abre.
3. Ve «API pública del Hub» («Esta documentación lista los endpoints disponibles de los módulos instalados. Para llamarla, crea una API key… y pégala como Bearer en «Authorize».») y la documentación Swagger de las operaciones que publican las apps instaladas.
4. Para probarlas, pega una llave en «Authorize»; la documentación por sí sola no da acceso.
Entra: el documento de la API que pide el hub con la sesión de la persona; la llave la pega la persona.
Sale: nada guardado. Crece o mengua al instalar o quitar apps.
Si falla: mientras llega, «Cargando documentación…». Si no llega: «No se pudo cargar la documentación» con «No se pudo obtener el spec de la API. Inicia sesión e inténtalo de nuevo.» y «Reintentar». Con el ajuste apagado la entrada no está y una dirección directa a `/api-docs` lleva a Inicio sin decir nada.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F157 (consultar la documentación de la API)
Pendiente de enlazar: hub — HUB_SHELL, Ajustes (el interruptor «Mostrar documentación de la API»)
QA: ninguno

### HUB_SHELL-F99 Decidir si se pide PIN en la caja y cuándo se vuelve a pedir
Estado: hecho
Actor: administrador
Pantalla: Ajustes › General
Pasos:
1. En **Ajustes › General**, bajo el título «Pinpad», el administrador ve «Mostrar pinpad»: «Si se muestra el pinpad y se pregunta quién está en la caja. Vale para todo el negocio: además, cada dispositivo decide por su cuenta, arriba.».
2. Lo enciende o lo apaga. Debajo, siempre visible, la consecuencia de la posición actual. Encendido: «El personal elige su nombre y teclea su PIN, así que cada venta lleva el nombre de quien la hizo.». Apagado: «Nadie teclea un PIN. Quien abriera la caja por la mañana es el nombre de todas las ventas hasta que acabe el turno, las hiciera quien las hiciera: no podrás saber quién vendió qué ni quién hizo un descuento. El personal que solo tiene PIN y no tiene cuenta no podrá entrar.».
3. Con el pinpad encendido aparece «Volver a preguntar tras inactividad» con un control de paradas: 1, 5, 10, 15 o 30 min, o «Hasta cerrar sesión». Cada parada dice qué pasa («Una caja que nadie toca durante {n} minutos cierra la sesión y muestra el pinpad: la siguiente venta lleva el nombre de la siguiente persona.»).
4. Cada cambio se guarda al momento, sin botón de guardar, y la tarjeta enseña lo que el hub confirma, no lo que se pidió.
Entra: la sesión de administrador; la política actual, la misma que lee la pantalla de acceso.
Sale: pide al servidor guardar solo las claves del control (HUB-F140). Apagarlo y volver a encenderlo vuelve al valor de fábrica (pedir PIN por turno), no a los minutos de antes. Esta tarjeta nunca alarga la sesión de un dispositivo compartido.
Si falla: «No se pudo cambiar. Comprueba la conexión e inténtalo de nuevo.» en un banner rojo. Quien no administra ve los controles apagados y «Solo un administrador puede cambiar si se pregunta.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F140 (decidir si el negocio pide PIN y cuántos dígitos tiene)
Pendiente de enlazar: hub — HUB_SHELL, Acceso (la pantalla de acceso y el detector de inactividad que obedecen este control)
QA: ninguno

### HUB_SHELL-F100 Elegir cuántos dígitos tiene el PIN del negocio
Estado: hecho
Actor: administrador
Pantalla: Ajustes › General
Pasos:
1. Con el pinpad encendido (HUB_SHELL-F99), bajo «Dígitos del PIN» el administrador elige «4 dígitos» o «6 dígitos».
2. Se guarda al momento. Debajo: «Todo el mundo teclea el mismo número de dígitos, que es lo que permite que el teclado entre al último en vez de pedirte confirmar. Los PIN que ya se usan siguen funcionando hasta que su dueño los cambie.».
3. A partir de ese momento, el teclado del acceso, el alta de personas y las ayudas de los formularios piden esa longitud.
Entra: la elección.
Sale: pide al servidor guardar la longitud (HUB-F140). No toca los PIN existentes ni rellena con ceros.
Si falla: «No se pudo cambiar. Comprueba la conexión e inténtalo de nuevo.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F140 (decidir si el negocio pide PIN y cuántos dígitos tiene)
QA: ninguno

### HUB_SHELL-F101 Ver los dispositivos en los que se ha entrado
Estado: hecho
Actor: administrador
Pantalla: Ajustes › General
Pasos:
1. En **Ajustes › General**, bajo «Dispositivos»: «Los dispositivos en los que alguien ha entrado. Si pierdes uno, quítalo aquí: su sesión se cierra al momento y deja de poder entrar con PIN.».
2. Cada dispositivo es una fila con el nombre que le puso el negocio (o «Dispositivo sin nombre»), la etiqueta «El que estás usando» en el actual, el modo («Pide PIN» o «Se queda abierto»), «En uso ahora mismo» o «Se usó por última vez {when}» (o «Añadido {when}, sin usar desde entonces»), «Su sesión sigue abierta hasta {when}» y «La última vez entró {who}». El identificador no se enseña nunca.
3. Quien no administra ve la tarjeta con «Solo un administrador puede quitar un dispositivo.» y, porque el hub solo da la lista a un administrador, el banner de abajo con el rechazo.
Entra: la lista de dispositivos que da el hub, con las fechas en la hora del negocio.
Sale: nada guardado.
Si falla: a quien no administra, «Solo el propietario o un administrador puede gestionar los dispositivos.». Si no llega: «No se pudieron cargar los dispositivos. Comprueba la conexión e inténtalo de nuevo.» (o el motivo que dio el hub) en un banner, y la lista no dice «Todavía no ha entrado nadie desde ningún dispositivo.», que se reserva para una lista de verdad vacía.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F141 (ver, nombrar y quitar los dispositivos del negocio)
QA: ninguno

### HUB_SHELL-F102 Ponerle nombre a un dispositivo
Estado: hecho
Actor: administrador
Pantalla: Ajustes › General
Pasos:
1. En la fila del dispositivo, el administrador pulsa «Ponerle nombre».
2. Debajo de la fila sale un campo: «Ponle el nombre del sitio: Barra, Cocina, Portátil del despacho» (hasta 60 caracteres).
3. Escribe y pulsa «Guardar» (o «Dejarlo» para cerrar). La fila pasa a titularse con ese nombre.
Entra: el nombre.
Sale: pide al servidor guardar el nombre (HUB-F141). Es lo único de la fila que decide el negocio: lo demás lo elige el propio dispositivo y solo sirve para reconocerlo.
Si falla: «No se pudo cambiar el nombre. Comprueba la conexión e inténtalo de nuevo.» o «Ese nombre es demasiado largo. Ponle uno más corto y vuelve a guardar.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F141 (ver, nombrar y quitar los dispositivos del negocio)
QA: ninguno

### HUB_SHELL-F103 Quitar un dispositivo que se ha perdido
Estado: hecho
Actor: administrador
Pantalla: Ajustes › General
Pasos:
1. En la fila del dispositivo, el administrador pulsa el icono «Quitar este dispositivo».
2. Debajo de la fila sale la pregunta «¿Quitar este dispositivo?» con la consecuencia: «Su sesión se cierra al momento. Para volver a usarlo, alguien tiene que entrar en él con su cuenta.». Si es el que está usando: «Es el dispositivo que estás usando: al quitarlo se cerrará tu sesión y tendrás que volver a entrar.».
3. Confirma con «Quitar este dispositivo» (o «Dejarlo»). La fila desaparece. Si era el suyo, la sesión se cierra y va a la pantalla de acceso.
Entra: el dispositivo.
Sale: pide al servidor quitarlo (HUB-F141): se corta el dispositivo, no la persona, y quien tenga cuenta puede volver a entrar en él.
Si falla: «No se pudo quitar este dispositivo. Comprueba la conexión e inténtalo de nuevo.» o «Ese dispositivo ya no está registrado aquí. Actualiza la lista.»; nunca queda en la lista como hecho lo que se rechazó.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F141 (ver, nombrar y quitar los dispositivos del negocio)
QA: ninguno

### HUB_SHELL-F104 Quitar de golpe los dispositivos que nadie usa
Estado: hecho
Actor: administrador
Pantalla: Ajustes › General
Pasos:
1. Si hay dispositivos que nadie ha usado en 30 días (sin contar el que se tiene en la mano), sale un botón «Quitar el dispositivo sin usar desde hace 30 días» o «Quitar los {n} dispositivos sin usar desde hace 30 días».
2. Al pulsarlo, la pregunta «¿Quitar {n} dispositivos que nadie usa desde hace 30 días?» con «Dejan de aparecer aquí y, para volver a usar uno, alguien tendrá que entrar en él con su cuenta. Los usados en los últimos 30 días y el que estás usando se quedan.».
3. Confirma con «Quitar».
Entra: qué dispositivos están sin usar, que marca el hub.
Sale: pide al servidor quitarlos (HUB-F141).
Si falla: «No se pudieron quitar los dispositivos sin usar. Comprueba la conexión y vuelve a intentarlo.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F141 (ver, nombrar y quitar los dispositivos del negocio)
QA: ninguno
