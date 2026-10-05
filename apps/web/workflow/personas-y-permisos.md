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

## Referencia adoptada

Contrastada en los comentarios del propio código (que citan las issues donde se decidió) y en
`qa-hub-restaurant §2`; no se ha rehecho.

- **Personas y PIN.** Square (permisos de equipo, passcode), Toast (empleados, PIN), Lightspeed y
  Odoo (usuarios): una identidad por persona, baja sin borrado, PIN por caja. Longitud fija de 4 o 6
  dígitos con envío al último dígito: gana Clover sobre Toast (3-8), Lightspeed K (4-6) y Shopify
  (4-6), que obligan a un botón de confirmar (decisión hub#974, citada en `lib/pin-length.ts`).
- **Placa.** Captura por temporización en un listener global, nunca por foco de campo (el foro de
  Odoo es el archivo de por qué); revocar la placa sin tocar el PIN (el caso Lightspeed L-Series, de
  tarjeta irrevocable); Square, Toast y Aloha para «pasar la tarjeta» (hub#658, hub#988).
- **Dispositivos.** El listado de dispositivos de Google, Apple y Shopify: nombre que pone el
  negocio, última actividad, quitar con confirmación en la propia fila (hub#455, hub#2203, hub#2215).
- **Aprobación por PIN.** Square y Toast (el responsable autoriza sin cerrar la sesión del cajero);
  este fichero solo cubre el registro (ADR-0265, hub#512); el diálogo es de «La vista de un módulo».

## Antes de empezar

- Para dar de alta con cuenta, el hub tiene que estar enlazado con erplora.com (si no, el aviso «Este
  hub todavía no puede enviar invitaciones.»).
- Los roles de una app (camarero, cocina…) nacen apagados: se encienden en **Empleados › Roles**
  antes de poder asignarlos.
- Para que las llaves de API tengan algo que dar, hace falta al menos una app instalada que publique
  operaciones de API; la documentación de la API viene apagada y la enciende un administrador en
  **Ajustes › General** (HUB_SHELL-F161).

## Flujos

### HUB_SHELL-F80 Ver la lista de personas del negocio
Estado: parcial — con la lista caída, bajo el aviso de error la tabla sigue diciendo «Aún no hay nadie más en este Hub.», que parece un hecho sobre el negocio; y la columna «Rol» enseña el identificador (por ejemplo `kitchen`) de los roles que trae una app, no su nombre (leído en el código, sin ejecutar)
Actor: administrador, responsable, empleado
Pantalla: Empleados
Pasos:
1. La persona pulsa **Empleados** en el menú lateral (la entrada la ve todo el mundo) y se abre la pestaña **Personal**. Una dirección con `#roles`, `#apikeys` o `#approvals` abre esa pestaña directamente.
2. Mientras llega la lista sale un indicador de carga. Después, una tabla con una fila por persona, activa o de baja: «Usuario» (con su inicial), «Email», «Rol», «Acceso», «Estado» («Activo» o «De baja») y «Alta».
3. Puede buscar en «Buscar usuario…», filtrar por rol, estado y fecha de alta, elegir columnas y exportar la tabla a un CSV llamado `personal`.
4. Un administrador ve además el botón de añadir (HUB_SHELL-F81) y, en cada fila, «Editar» y «Dar de baja». El resto lo ve en solo lectura.
Entra: la lista de personas y la de roles, pedidas a la vez al hub; la sesión.
Sale: nada guardado. El correo de la columna «Email» es el de acceso o, si no lo hay, el que la persona escribió en su Mi perfil; con ese correo se da y se quita el acceso en erplora.com (ERPlora/hub#2500). Esa misma lista (identificador, nombre, rol y si está activa) es la que los módulos piden para nombrar a quien atiende o a quien envió una comanda; el correo y la forma de entrar no viajan a ellos (HUB-F158).
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
2. Escribe «Nombre y apellidos» (hasta 150 caracteres) y activa «Usuario local» (el panel no lleva texto de ayuda; solo la ficha de alta lo tiene y no se alcanza desde ninguna pantalla). El campo de email desaparece.
3. Elige el «Rol» entre los que se pueden asignar hoy (los de fábrica y los de las apps cuyo rol está encendido, HUB_SHELL-F91; los de una app salen con su identificador) y teclea el «PIN local»: solo dígitos, tantos como pida el negocio (4 o 6), enmascarado y con un ojo para verlo. Bajo el campo: «{n} dígitos. Obligatorio: es cómo entra esta persona.».
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
Estado: parcial — «Crear» se queda apagado mientras falte un email válido sin decir por qué; la persona invitada sale «Sin acceso» en rojo hasta su primer acceso; y si la invitación no sale, la ficha ya está guardada pero la lista no se recarga y «volver a guardar» no reenvía nada (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Empleados
Pasos:
1. En **Empleados › Personal**, el administrador abre el panel de añadir y deja «Usuario local» sin marcar.
2. Escribe el nombre y el «Email». Bajo el email: «Le mandamos por email una invitación a este hub. La contraseña la elige él: tú no la ves nunca.».
3. Elige el «Rol». A una cuenta solo se la puede invitar como administrador, encargado o empleado; un rol que trae una app es del personal local.
4. Si trabaja en una caja compartida, teclea además un PIN: «Opcional: {n} dígitos. Solo si además atiende una caja compartida de este hub.».
5. Pulsa «Crear». El panel se cierra, la lista se recarga y sale «Usuario creado.». En la columna «Acceso» sale «Sin acceso», en rojo, hasta que entre por primera vez con su cuenta (con PIN, «PIN local»).
Entra: nombre, email, rol y PIN opcional; la lista ya cargada (para adelantar «email repetido» antes de enviar).
Sale: pide al servidor el alta de la ficha y que erplora.com mande la invitación (HUB-F146). La pantalla adelanta el email repetido y el rol que una cuenta no admite mientras se teclea.
Si falla: «Un usuario de cuenta entra con su cuenta de ERPlora, así que el email es obligatorio. Marca «Usuario local» para dar de alta a quien trabaja en este hub con un PIN.», «Introduce un email válido.», «A una cuenta de ERPlora solo se la puede invitar como admin, manager o employee. Los roles que añade un módulo son del personal local.», «Este hub ya conoce ese email. Edita a ese usuario —reincorpóralo si estaba dado de baja— en vez de invitar una segunda identidad.», «No puedes repartir un rol por encima del tuyo: administrar el hub solo lo concede quien ya lo administra.». Si la invitación no sale, el panel sigue abierto con el motivo y la lista no se actualiza: la persona ya está guardada pero no se ve hasta volver a entrar en Empleados. «Volver a guardar» no reenvía: un segundo «Crear» se rechaza con «Este hub ya conoce ese email…». Hoy la única forma de reenviar la invitación desde la pantalla es recargar y cambiarle el rol, el correo o el estado en su ficha (o darla de baja y reincorporarla). Los avisos: «No hemos podido conectar con ERPlora para enviar la invitación. El usuario queda guardado aquí: vuelve a guardar dentro de un momento.», «No se ha podido crear la invitación para ese email. Revisa la dirección y vuelve a intentarlo; si sigue fallando, avisa a soporte.», «Demasiados cambios en poco tiempo: la invitación todavía no ha salido. Espera unos minutos y vuelve a guardar — no se ha perdido nada más.» o «Este hub todavía no puede enviar invitaciones. El usuario queda guardado aquí; avisa a soporte para que termine de configurarlo.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F146 (invitar a una persona con su cuenta de erplora.com)
Pendiente de enlazar: staff — STAFF-F01 (la cuenta que luego se vincula a la ficha de profesional)
QA: qa-hub-restaurant §6

### HUB_SHELL-F83 Llegar al tope de personas del plan
Estado: parcial — el botón «Actualizar plan» solo sale en la ficha de la persona, es decir, al reincorporar a alguien (HUB_SHELL-F89); al dar de alta desde la tabla sale solo la frase (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Empleados
Pasos:
1. El plan admite un número de personas activas. El administrador intenta dar de alta, invitar o reincorporar a alguien con todas las plazas ocupadas.
2. El hub lo rechaza y la pantalla dice: «Tu plan tiene todas las plazas ocupadas. Da de baja a alguien que ya no trabaje aquí, o pasa a un plan con más plazas.».
3. Solo en la ficha de la persona (se llega a ella desde «Editar», es decir, al reincorporar; la ficha de alta no se alcanza desde ninguna pantalla), bajo la frase aparece el botón «Actualizar plan», que abre en el navegador la página de cambio de plan de este hub en erplora.com, ya identificado (HUB_SHELL-F129). No sale en una copia repartida por Google Play ni con un fallo que no sea el tope.
4. Dar de baja a alguien libera su plaza al momento; el administrador vuelve a guardar.
Entra: el rechazo del servidor por plazas (`user_limit_reached`); la distribución de la copia (Play o no) que da el dispositivo.
Sale: nada guardado. El servidor decide el tope y lo aplica en el mismo paso que escribe (HUB-F147); la pantalla no cuenta plazas por su cuenta. Cuántas plazas hay usadas se ve en **Sistema › Plan y límites** (HUB_SHELL-F128), que avisa con «Tu plan tiene todas las plazas ocupadas, así que no puedes añadir a nadie más.» sin botón.
Si falla: si no se puede abrir el navegador, «No se pudo abrir tu navegador. Entra en erplora.com para gestionar tu plan.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F147 (llegar al tope de plazas del plan)
QA: ninguno

### HUB_SHELL-F84 Cambiar el nombre, el correo, el rol o el estado de una persona
Estado: parcial — la ficha ofrece en «Rol» todos los roles, también los de una app apagada (el servidor los rechaza con una frase que manda a «Ajustes → Roles», que no existe: se encienden en Empleados › Roles); la ficha no impide dejar el negocio sin administradores (solo frena el servidor); y quien no administra puede abrir la ficha por su dirección y solo recibe el rechazo al guardar
Actor: administrador
Pantalla: Ficha de usuario
Pasos:
1. En **Empleados › Personal**, el administrador pulsa «Editar» en la fila: se abre la **Ficha de usuario** («Editar usuario»).
2. Cambia lo que haga falta: «Nombre y apellidos», «Email» (en todas las fichas: ponérselo a una persona local la convierte en persona con cuenta e invita a ese correo; con un rol de app, erplora.com lo rechaza y el aviso habla de la dirección, no del rol), «Rol» y la casilla «Usuario activo». Los cambios de PIN y de placa son HUB_SHELL-F85 a F87.
3. Pulsa «Guardar». Solo viaja lo que ha cambiado. Sale «Usuario actualizado.» y vuelve a la lista.
4. Si hay cambios sin guardar y el administrador pulsa «Cancelar» o sale de la ficha, la pantalla pregunta «Cambios sin guardar» («Si sales ahora perderás los cambios realizados.») con «Seguir editando» y «Descartar cambios».
Entra: la ficha cargada desde la lista de personas y de roles; los campos que cambian.
Sale: pide al servidor la edición (HUB-F148). El rol nuevo vale desde la siguiente acción de esa persona.
Si falla: sin la ficha, «No se pudo abrir el usuario» con «El registro no está disponible o no tienes permiso para consultarlo.» y «Reintentar»; una persona que ya no está en la lista da el mismo aviso que un fallo de carga (la frase «Usuario no encontrado.» se descarta). La ficha del dueño de la cuenta solo la abre él: a otro administrador la tabla le avisa «La ficha del dueño de la cuenta solo la cambia él. Para traspasar el negocio, transfiere la cuenta en ERPlora.» y no abre el formulario (si llegara, «Esta es la ficha del dueño de la cuenta y solo él puede cambiarla…»). Quitar el rol de administrador al último, o apagar «Usuario activo» a quien lo es, solo lo rechaza el servidor («No puedes dar de baja al último administrador. Nombra antes a otro dueño o administrador.»), también cuando lo que se hizo fue degradarlo. Un rechazo por campo sale bajo el campo que lo causó (nombre, email, PIN o placa) y cualquier otro en el banner de arriba. Sin conexión con erplora.com al cambiar rol o email: los avisos «cloud_*» de HUB_SHELL-F82.
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
Sale: pide al servidor la edición con solo el PIN (HUB-F148). La ficha no comprueba el PIN antes de guardar (solo limita los dígitos que caben): lo valida el hub. Cambiar la longitud del negocio (HUB_SHELL-F100) no toca los PIN ya puestos. El PIN de uno mismo se cambia en **Mi perfil** (acceso y navegación), no aquí.
Si falla: un PIN de otra longitud sale bajo el campo («El PIN debe tener {n} dígitos.»); uno fácil («Ese PIN se adivina a la primera: evita los dígitos repetidos (1111) y las cuestas seguidas (1234).») o ya usado («Ese PIN ya lo tiene otro usuario activo…») sale en el aviso rojo de arriba. Este último confirma a quien edita que ese número es el PIN de alguien (ERPlora/hub#2499). El PIN del dueño de la cuenta no lo cambia nadie más («Esta es la ficha del dueño de la cuenta y solo él puede cambiarla, PIN incluido…»).
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
Sale: pide al servidor la edición con el PIN vacío (HUB-F148). A quien ya tiene PIN, un campo vacío no se lo quita: solo «Retirar el PIN» lo hace. A quien no lo tiene, cada guardado manda el vacío, sin efecto.
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
Sale: pide al servidor la edición con la placa (HUB-F148). A quien ya tiene placa, un campo vacío no se la quita: solo «Retirar la placa» lo hace. A quien no la tiene, cada guardado manda el vacío, sin efecto. La captura de la ráfaga es global del shell y a la ficha le llega la última pantalla que escucha (acceso y navegación, HUB_SHELL, Acceso).
Si falla: «Una placa tiene entre 4 y 64 caracteres: letras, dígitos, «-» y «_».» (se avisa mientras se teclea y bloquea «Guardar»), «Esa placa ya la lleva otro usuario activo. La placa dice quién está en la caja, así que no la pueden compartir dos personas.», «Nadie da de alta su propia placa. Pídeselo a otro administrador.», «La placa no puede ser su única vía de entrada…».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F148 (cambiar el nombre, el rol, el PIN, la placa o el correo de una persona)
Pendiente de enlazar: hub — HUB-F134 (captura de la ráfaga del lector y lector NFC de Android, HUB_SHELL Acceso y HUB_APP)
QA: ninguno

### HUB_SHELL-F88 Dar de baja a una persona
Estado: parcial — «Dar de baja» sale también en las filas ya de baja y en la del dueño, con un motivo falso; si erplora.com falla la fila sigue «Activo» aunque la baja ya esté aplicada; desde la ficha, apagar «Usuario activo» da de baja sin la pregunta ni los espejos de la tabla (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Empleados
Pasos:
1. En **Empleados › Personal**, el administrador pulsa «Dar de baja» en la fila de la persona.
2. La pantalla pregunta «Dar de baja»: «Vas a dar de baja a «{name}». Perderá el acceso al Hub, pero su historial se conserva.», con «Cancelar» y «Dar de baja». La pregunta no dice que en erplora.com se quita el acceso del correo que enseña la columna «Email», aunque sea el que la persona escribió en su Mi perfil (ERPlora/hub#2500).
3. Confirma. Sale «Usuario dado de baja.» y la fila pasa a «De baja».
Entra: la persona; la sesión de administrador.
Sale: pide al servidor la baja (HUB-F149): se desactiva, nunca se borra, y sus sesiones se cierran. Antes de preguntar, la pantalla se niega si el servidor lo rechazaría, con el aviso «No puedes darte de baja a ti mismo ni dejar el Hub sin ningún administrador.»; el servidor revalida.
Si falla: «No se pudo dar de baja al usuario.» o la frase del servidor traducida: «No puedes dar de baja al último administrador. Nombra antes a otro dueño o administrador.», «No puedes darte de baja a ti mismo. Pídeselo a otro administrador.». En una fila ya de baja o en la del dueño, la tabla contesta «No puedes darte de baja a ti mismo ni dejar el Hub sin ningún administrador.», que no es el motivo. Si erplora.com no contesta, la baja se queda en el hub pero la fila sigue diciendo «Activo» hasta recargar, y el aviso habla de una invitación. La tabla impide la baja propia, la del último administrador y la del dueño; la ficha no, y solo frena el servidor.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F149 (dar de baja y reincorporar a una persona)
Pendiente de enlazar: staff — STAFF-F03 (dar de baja la cuenta no toca la ficha de profesional)
QA: qa-hub-restaurant §6

### HUB_SHELL-F89 Reincorporar a una persona dada de baja
Estado: parcial — con el plan lleno, a una persona con cuenta erplora.com ya la ha readmitido cuando la pantalla dice que no hay plaza (ERPlora/hub#2500)
Actor: administrador
Pantalla: Ficha de usuario
Pasos:
1. En la lista, la persona sale con el estado «De baja». El administrador pulsa «Editar».
2. En la ficha enciende «Usuario activo» y pulsa «Guardar».
3. Vuelve la misma persona, con su historial; en la lista sale «Activo». Una persona con cuenta recibe de nuevo su membresía.
Entra: la ficha de la persona de baja.
Sale: pide al servidor la edición con el estado activo (HUB-F149); reactivar ocupa una plaza del plan.
Si falla: sin plazas, la frase y el botón «Actualizar plan» de HUB_SHELL-F83 (aunque la membresía y la invitación en erplora.com ya estén rehechas); si erplora.com no concede la membresía, los avisos «cloud_*» de HUB_SHELL-F82 y la persona sigue de baja.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F149 (dar de baja y reincorporar a una persona)
QA: ninguno

### HUB_SHELL-F90 Entender cómo entra cada persona
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Empleados
Pasos:
1. En la tabla de **Personal**, la columna «Acceso» dice por dónde puede entrar cada persona: «PIN local», «PIN + placa», «Placa», «Cuenta online» o «Sin acceso».
2. «Sin acceso» sale en rojo: es alguien que hoy no puede iniciar sesión, una persona que solo existe en la agenda o una invitada que aún no ha entrado con su cuenta. Cuando hay varias vías manda el PIN.
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
1. En **Empleados › Roles** aparece una explicación («Estos son los roles que este Hub puede repartir. Los básicos están siempre; los que trae una app los enciendes tú cuando tu negocio los necesita.») y una tabla con una fila por rol: «Rol», «Viene de» («Básico», el identificador del módulo —por ejemplo `kitchen`— o «App desinstalada»), «Disponible», «Miembros» y «Permisos» (solo los números). El nombre de un rol de app sale como lo escribió la app, en inglés.
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
Estado: parcial — los roles de una app salen con su identificador (`kitchen`) en el alta, en la ficha y en la columna «Rol»; y al editar se puede hacer administradora a una persona que solo entra con PIN (ERPlora/hub#2500) (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Empleados
Pasos:
1. Al dar de alta (HUB_SHELL-F81 y F82) o al editar (HUB_SHELL-F84), el administrador abre el desplegable «Rol».
2. En el alta rápida solo salen los roles que se pueden asignar hoy; en la ficha completa salen todos. Los tres de fábrica salen con su nombre («Administrador», «Encargado», «Empleado»); el de cajero lo trae el módulo de Venta y es uno más de los de app.
3. Al dar de alta, una cuenta solo admite administrador, encargado o empleado y el personal local no puede ser administrador. Al editar, la ficha ofrece todos los roles, también «Administrador» para alguien que solo tiene PIN, y el hub lo acepta (ERPlora/hub#2500): desde ese momento su PIN administra el hub. A una persona con cuenta, la ficha le ofrece roles de app y erplora.com los rechaza, con un aviso que habla de la dirección.
4. Guarda; el rol se ve en la columna «Rol» de la lista.
Entra: el catálogo de roles (HUB_SHELL-F91).
Sale: el rol en la ficha (HUB-F148). Repartir administración solo lo hace quien ya administra. Las claves `admin`, `manager` y `employee` son un contrato con erplora.com, los módulos y las traducciones: no se renombran.
Si falla: «A una cuenta de ERPlora solo se la puede invitar como admin, manager o employee…», «Un usuario local no puede administrar el hub…», «No puedes repartir un rol por encima del tuyo…»; el rol apagado, «Este rol está apagado en este hub. Enciéndelo en Ajustes → Roles antes de asignarlo.» (la ruta correcta es Empleados › Roles).
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F148 (cambiar el nombre, el rol, el PIN, la placa o el correo de una persona)
QA: qa-hub-restaurant §6

### HUB_SHELL-F93 Consultar quién aprobó qué
Estado: parcial — las columnas «Acción» y «Nivel» enseñan los nombres técnicos de la orden y del permiso (por ejemplo `sales.void_line`), no una frase; la explicación promete conservar el registro «mientras tu negocio esté en ERPlora» cuando el hub lo borra a los cuatro años (`retention.rs`); y quien no administra y llega con `#approvals` ve una página en blanco (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Empleados
Pasos:
1. El administrador abre **Empleados › Aprobaciones** (la pestaña solo existe para administradores; quien no administra y llega con `#approvals` o `#apikeys` ve la página en blanco, sin pestaña marcada: la guarda solo salta si la sesión cambia).
2. Lee la explicación («Cada acción que necesitó el PIN de un encargado: quién la pidió, quién la autorizó y para qué se usó…») y la tabla: «Cuándo» (fecha y hora), «Autorizado por», «Lo pidió», «Acción» y «Nivel».
3. Busca por persona o acción en «Buscar por persona o acción…», filtra por fechas, acción o nivel, y ordena por fecha. Cada cambio vuelve a pedir una sola página al hub.
4. Si necesita demostrar cuál fue, abre el selector de columnas: «Referencia» (una huella de los datos) y los dos identificadores están ocultos y van en la exportación a CSV.
Entra: el registro de aprobaciones, paginado en el servidor; la sesión de administrador.
Sale: nada; es solo lectura y nadie puede editar ni borrar una fila. La pestaña no pide nada hasta que se abre. Aprobar o rechazar no se hace aquí: la aprobación se da en el momento, con el PIN de un responsable, en el diálogo que sale en la pantalla donde se intentó (vista de un módulo) y vale 120 s; este registro es solo el recibo. Las preguntas y propuestas del asistente y de las automatizaciones se deciden en Automatizaciones › «Pendiente de ti», no aquí.
Si falla: «No se pudo cargar el registro de aprobaciones.» con «Reintentar» (un fallo no se confunde con un registro vacío); sin nada, «Todavía nadie ha tenido que autorizar nada en este Hub.»; quien ya no existe sale como «Usuario dado de baja».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F153 (consultar quién aprobó qué)
Pendiente de enlazar: hub — HUB-F152 (aprobar una acción con el PIN de un responsable, HUB_SHELL vista de un módulo: diálogo de aprobación)
Pendiente de enlazar: flows — FLOWS-F24 (las preguntas y propuestas se deciden en Automatizaciones › Pendiente de ti)
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
Si falla: «No se pudo crear la API key.» (o la frase traducida del servidor); «No se pudo copiar al portapapeles.» si el navegador no deja copiar. Si no hay ninguna app con API: «Ningún módulo expone API todavía» y no se puede crear una llave «Por app». Si la lista de apps no se pudo leer, la ventana dice lo mismo, como si ninguna publicara API. La matriz se carga una vez: una app instalada con la pantalla abierta no aparece hasta recargar (leído en el código, sin ejecutar).
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
1. Al abrir **Empleados › API keys**, la tabla lista cada llave: «Nombre», «Token» (solo el comienzo), «Permisos» (el modo, o el identificador de cada app con L de lectura y E de escritura), «Estado» («Activa» o «Revocada»), «Creada», «Último uso» (o «Nunca»), «Límite» (por ejemplo «60/min») y «Acciones».
2. Se puede buscar en «Buscar API key…».
Entra: la lista de llaves.
Sale: nada guardado. El token entero no se vuelve a ver. Ninguna pantalla dice que una llave sigue viva aunque den de baja a quien la creó o le quiten la administración (HUB-F155), y la tabla no tiene columna «Creada por».
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
Si falla: tras recargar en frío `/api-docs`, el ajuste puede no haber llegado aún y la guarda de la ruta llevar a Inicio aunque esté encendido (sin confirmar). Mientras llega, «Cargando documentación…». Si no llega: «No se pudo cargar la documentación» con «No se pudo obtener el spec de la API. Inicia sesión e inténtalo de nuevo.» y «Reintentar». Con el ajuste apagado la entrada no está y una dirección directa a `/api-docs` lleva a Inicio sin decir nada.
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

## Cobertura contra la referencia

| Elemento | Estado | Flujo |
|---|---|---|
| Alta de persona solo con PIN | hecho | HUB_SHELL-F81 |
| Alta con cuenta e invitación por correo | parcial (la invitada sale «Sin acceso» hasta su primer acceso) | HUB_SHELL-F82 |
| Reenviar una invitación | no hecho (la salida es volver a guardar, que choca con «email repetido») | HUB_SHELL-F82 |
| Tope de personas del plan | parcial (botón solo en la ficha) | HUB_SHELL-F83 |
| Editar, baja con historial y reincorporar | hecho / parcial | HUB_SHELL-F84, F88, F89 |
| PIN de otra persona: poner, cambiar, retirar | hecho | HUB_SHELL-F85, F86 |
| Placa: alta por lector USB o NFC y revocar | hecho | HUB_SHELL-F87 |
| Ver cómo entra cada persona | hecho | HUB_SHELL-F90 |
| Roles de fábrica y de apps; encender los de apps | parcial (identificadores a la vista; la ficha hace administrador a quien solo tiene PIN, hub#2500) | HUB_SHELL-F91, F92 |
| Crear un rol propio / editar qué permite un rol | no hecho (decisión del servidor: los roles los fijan las apps) | HUB_SHELL-F91 |
| Ver qué permisos concretos tiene un rol y quiénes son sus miembros | no hecho (solo recuentos) | HUB_SHELL-F91 |
| Registro de aprobaciones por PIN | parcial (códigos técnicos) | HUB_SHELL-F93 |
| Aprobar o rechazar desde una bandeja (propuestas del asistente, preguntas de automatizaciones) | no está en Empleados: se decide en Automatizaciones › Pendiente de ti (FLOWS-F24); la aprobación por PIN va en un diálogo de la vista de un módulo | — |
| Llaves de API: crear, ver una vez, rotar, revocar | hecho / parcial (rotar sin pregunta) | HUB_SHELL-F94 a F97 |
| Documentación de la API | parcial (textos) | HUB_SHELL-F98 |
| Política de PIN, longitud, inactividad | hecho | HUB_SHELL-F99, F100 |
| Dispositivos: ver, nombrar, quitar, limpiar | hecho | HUB_SHELL-F101 a F104 |
| Normas propias del negocio (políticas) | no hecho (sin pantalla; solo API y asistente) | — |

## Datos: de quién es cada dato

Ninguna de estas pantallas es dueña de un dato: leen y piden al servidor.

- **Personas** (nombre, email de acceso, rol, huella del PIN y de la placa, estado): del hub
  (`hub_user`, HUB-F145 a F149); la ficha de profesional de `staff` es otra cosa que se vincula. La
  membresía de la cuenta vive en erplora.com.
- **Roles y su activación**: del hub; las definen las apps instaladas.
- **Registro de aprobaciones**: del hub; solo lectura, nadie lo edita.
- **Llaves de API**: del hub; el token entero solo viaja una vez, al crear o rotar.
- **Dispositivos y su nombre**: del hub; el nombre lo escribe el negocio, el resto lo elige el
  dispositivo y solo sirve para reconocerlo.
- **Política de PIN, longitud y documentación de la API**: ajustes del negocio del hub.

Datos personales que pasan por estas pantallas: nombre y email de cada persona (en pantalla y en el
CSV `personal` que se baja al dispositivo); quién aprobó qué, con identificadores (CSV de
Aprobaciones); la etiqueta del dispositivo, que es el nombre de la última persona que entró. La
pantalla no guarda ninguno de ellos en el navegador (sin confirmar al revisar el almacenamiento local
de estos componentes: solo se han leído estas vistas).

## Reglas que no se rompen

- **Una persona no se borra: se da de baja** (la baja desactiva; ventas, aprobaciones y auditoría la
  siguen nombrando).
- **El PIN y la placa no se leen nunca**: el PIN va enmascarado al teclearlo y la pantalla solo sabe
  si existe; el token de una llave se enseña una vez.
- **Roles, política de PIN y dispositivos pintan lo que confirma el servidor**, sin optimismo local.
- La lista de personas y la de roles son la excepción conocida a «un fallo no se pinta como un
  vacío» (regla común del índice): bajo el aviso de error siguen diciendo «Aún no hay…»
  (HUB_SHELL-F80).

## Lo que NO hace, a propósito

- No crea roles ni edita permisos de un rol (los fijan las apps).
- No reenvía invitaciones, no enseña un PIN ni una placa ya puestos y no recupera un token.
- No edita las normas del negocio (políticas): no tienen pantalla.
- No aprueba ni rechaza nada desde Empleados: ese registro es solo lectura.

## Dudas abiertas

Se resuelven con `market-decision`; no las decide el worker.

- ¿Crear roles propios o editar qué permite cada uno? (el mercado suele ofrecerlo, sin contrastar en
  este encargo; en el hub lo fijan las apps.) Lo dice la decisión de roles del servidor; confirmar si
  entra en el MVP.
- ¿Reenviar una invitación que no salió? Hoy el aviso manda a «volver a guardar», que no funciona.
- ¿Pedir confirmación al rotar una llave de API? ¿Y avisar de que sobrevive a la baja de quien la creó?
- ¿Debe el aviso de plazas llevar «Actualizar plan» también en el alta rápida y en Sistema › Plan y
  límites, o es steering (hub#479)?

## Fuentes contrastadas

- Servidor HUB-F147: «la pantalla ofrece «Actualizar plan»». Solo la Ficha de usuario lo ofrece, y
  en la práctica solo al reincorporar; el alta de la tabla y Sistema › Plan y límites no.
- HUB-F145 «Pasos: elige un rol que se pueda asignar» vale en el alta; la ficha de edición ofrece todos
  (hub#2500).
- Servidor HUB-F140: «Guarda» como paso. Las tarjetas del pinpad guardan al mover cada control, sin
  botón.
- Servidor HUB-F153: «qué acción». La tabla enseña el código de la orden y del permiso.
  La explicación de la pestaña promete conservar el registro «mientras tu negocio esté en ERPlora»;
  el hub lo borra a los cuatro años (`crates/runtime/src/retention.rs:110-113`, confirmado).
- Servidor, actores «responsable»: el rol de la pantalla se llama «Encargado» (`manager`).
- Servidor HUB-F150: «tres roles de fábrica (administrador, responsable y empleado)». El catálogo
  de la pantalla puede traer además «Propietario» (rol antiguo, si alguien lo lleva), que sale como
  «App desinstalada».
- Código `PinPolicyCard` y `DevicesCard` (comentarios): «Ajustes › Hub». La pestaña se llama
  **General**.
- Frase de rol apagado en el catálogo de motivos: «Enciéndelo en Ajustes → Roles». Los roles se
  encienden en Empleados › Roles; el texto de la introducción de la Documentación de la API manda a
  «Usuarios → API keys», que hoy es Empleados › API keys.
- Manual `hand-book/hub/03-personas-y-permisos.md`: «Lista vacía con opción de alta» y «Perfil: PIN
  propio». Cierto; el PIN propio es de Mi perfil (HUB_SHELL-F22, área de acceso, que recoge además el
  oráculo del PIN de otros, hub#2499).
