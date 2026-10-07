# WORKFLOW — Hub (pantallas) · Aplicaciones

Prefijo: HUB_SHELL

> Detalle del área «Aplicaciones, plan y archivos», primera mitad (HUB_SHELL-F105…F125): la pantalla
> **Apps** (tus apps y el catálogo: instalar, actualizar, activar, desactivar y desinstalar). La
> segunda mitad (Mi plan, límites del plan, puertas hacia erplora.com y Archivos, HUB_SHELL-F126…F134)
> está en `workflow/plan-y-archivos.md`. Aquí se cuenta lo que ve la persona; qué hace el servidor
> detrás está en el `workflow/modulos.md` del servidor (HUB-F19…F35) y no se repite. Código:
> `apps/web/src/views/AppsPage.vue` y `lib/apps-catalog.ts`, `apps-grid.ts`, `apps-list-columns.ts`,
> `installed-app-actions.ts`, `module-updates.ts`, `module-update-notice.ts`, `module-capabilities.ts`,
> `module-failure-message.ts` (este último es de «La vista de un módulo»; aquí se usa para la frase de
> un fallo de instalación).

## Referencia adoptada

Contrastada en los comentarios del propio código (que citan las issues donde se decidió); no se ha
rehecho.

- **Apps.** Odoo y Shopify para nombrar lo instalado de paso y lo que rompe un desinstalar (hub#1130,
  hub#1101, hub#773); el aviso de «plugin cerrado» de WordPress.org para una app retirada (ADR-0380,
  hub#1134).

## Antes de empezar

- Instalar, desactivar y desinstalar las ofrece la pantalla solo a un administrador.
- Instalar una app de pago exige que el negocio tenga la suscripción en erplora.com; el catálogo se
  recarga solo al volver a la ventana.

## Flujos

### HUB_SHELL-F105 Ver las apps instaladas en el negocio
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Apps
Pasos:
1. La persona pulsa **Apps** en el menú lateral (la ven todos los perfiles). Se abre en la pestaña **Mis apps**; una dirección con `#all` o `#paid` abre el catálogo.
2. Mientras llega la lista: «Cargando tus apps…». Después, tarjetas (o tabla, a elegir) con una app por fila: «App» (con la etiqueta «Retirada» si procede, HUB_SHELL-F121), «Versión» (la que corre, o «1.1.1 → 1.1.2» si hay una nueva) y «Estado» («Activo», «Inactivo» o «Inactivo (en cascada)»).
3. «Inactivo (en cascada)» no lo apagó nadie: se apagó porque se apagó una app de la que depende, y volverá sola cuando esa vuelva.
4. Se busca en «Buscar en tus apps…» y se filtra por estado.
5. Quien no administra ve arriba «Puedes ver las apps, pero solo un administrador puede instalarlas, activarlas o desinstalarlas.» y ninguna acción.
Entra: la lista de apps instaladas según el hub (no según el catálogo de erplora.com); cuál ofrece hoy el catálogo para cada una (HUB_SHELL-F116).
Sale: nada guardado. La lista se recarga sola al instalar, activar, desactivar o desinstalar desde otra pestaña u otro dispositivo y al cambiar de idioma; el catálogo, además, al volver a la ventana.
Si falla: sin respuesta, «No hemos podido leer tus apps. No ha habido respuesta, o esta sesión ya no es válida — vuelve a entrar si sigue pasando.» con «Reintentar»; la lista que ya había se conserva (un fallo nunca se lee como «no tienes apps»). Con una lista que de verdad vuelve vacía: «Aún no tienes apps. Abre «Añadir apps» para instalar la primera.».
Implicados: HUB-F31
QA: BD-03

### HUB_SHELL-F106 Abrir una app desde Apps
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
1. En la fila de una app activa de **Mis apps**, el administrador pulsa el icono «Abrir» (el primero de la fila).
2. El hub lleva a la pantalla de la app.
Entra: el menú de apps activas que ya tiene el shell.
Sale: nada guardado.
Si falla: una app apagada o que no pinta pantalla propia no lleva el botón «Abrir» (no se enseña apagado: se quita); el botón se vuelve a comprobar al pulsarlo por si el estado acaba de cambiar.
Implicados: ninguno
QA: ninguno

### HUB_SHELL-F107 Buscar una app en el catálogo
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Apps
Pasos:
1. La persona abre **Apps** y pulsa la pestaña **Añadir apps** (todo el catálogo) o **De pago** (solo las que no son gratis).
2. Mientras llega: «Cargando el catálogo…». Después, tarjetas (en un móvil siempre tarjetas) o tabla con «App», «Versión», «Categoría», «Descripción», «Precio» y «Estado» («Instalado», «Disponible», «No disponible», «Instalando…», «Actualizar a {version}» o «Necesita ERPlora {version}»).
3. Busca en «Buscar apps para añadir…» (nombre, descripción y categoría) y filtra por categoría, precio y estado.
4. Un administrador ve la acción «Instalar» o «Actualizar» en la fila que corresponda (HUB_SHELL-F109 y F116); en una demo, no: «Estás viendo el catálogo real en modo demostración. Conecta un negocio real para instalar apps.».
Entra: el catálogo de erplora.com que reenvía el hub; el hub pide el idioma del negocio (`?lang=`), pero esa puerta de erplora.com lo ignora: con la credencial de máquina sale en el idioma que manda la pantalla (`Accept-Language`, que el hub reenvía) y, si va con la cuenta de la persona, en el que tenga guardado en erplora.com (solo la puerta pública, la de un hub sin enrolar, respeta `?lang=`); cruzado con las apps instaladas en el hub, que es lo que manda para decir «Instalado» (el catálogo puede ir por detrás).
Sale: nada guardado. Recupera el catálogo al volver el foco a la ventana, para ver al instante una suscripción contratada fuera.
Si falla: «No se pudo cargar el catálogo. Revisa la conexión o el registro de este dispositivo.» con «Reintentar»; las filas que ya había se conservan. Sin respuesta todavía, «Cargando el catálogo…»; con una búsqueda sin resultados, «No hay apps que coincidan con tu búsqueda.» (cada situación con su frase).
Implicados: SAAS_PUBLIC-F12, SAAS_PUBLIC-F13, SAAS_PUBLIC-F14
QA: BD-03

### HUB_SHELL-F108 Saber cuánto cuesta una app antes de instalarla
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Apps
Pasos:
1. En el catálogo, la columna «Precio» dice «Gratis», «Incluida en tu plan», «{price} €/mes», «{price} €/año», «{price} €» (pago único) o «Consultar».
2. La pantalla pintaría tal cual una etiqueta de precio propia de erplora.com, pero el catálogo de erplora.com no la manda nunca: el importe sale del precio más bajo que declara (`price_from`, el mínimo de sus planes de pago).
3. Una app sin importe conocido nunca enseña la unidad sola («€/mes» sin cifra): sale «Consultar».
4. La pestaña **De pago** reúne todo lo que no es gratis, incluidas las «Incluida en tu plan».
Entra: el precio, el ciclo y si va en el plan, que manda erplora.com.
Sale: nada guardado. El hub no cobra ni lleva a comprar: contratar es cosa de erplora.com (HUB_SHELL-F111).
Si falla: sin catálogo, HUB_SHELL-F107.
Implicados: REC_ALTA-F22, SAAS_PUBLIC-F12
QA: ninguno

### HUB_SHELL-F109 Instalar una app
Estado: parcial — la instalación no tiene tope de tiempo ni en el hub ni en la pantalla (hub#2556); las apps que entran de paso no pasan por la pregunta de permisos y quedan con todos denegados, sin aviso; y el aviso de éxito de la pantalla y el del canal en vivo pueden pisarse (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Apps
Pasos:
1. En **Añadir apps**, el administrador pulsa el icono «Instalar» de una app «Disponible».
2. Si hay varias versiones publicadas, aparece «Elige una versión»: «Está seleccionada la última. Elige otra solo si te lo ha pedido soporte.», con «Continuar» y «Cancelar». Si hay una sola, no pregunta.
3. Si la app declara permisos, aparece «Permisos solicitados»: «Esta app solicita estos permisos. Podrás revisarlos después en Ajustes → Permisos.», con cada permiso y su descripción y los botones «Instalar y conceder» y «Cancelar». No se puede conceder solo una parte. Sin permisos, se instala directamente.
4. La fila pasa a «Instalando…» y va diciendo la fase: «Resolviendo versión…», «Descargando…», «Verificando integridad…», «Aplicando migraciones…»; si instala una dependencia, «Dependencia {name} — {phase}». Un aviso fijo dice «Instalando {name}…».
5. Al terminar sale «{name} instalado correctamente.» (se va solo), la fila pasa a «Instalado» y la app aparece en el menú y en Mis apps sin recargar.
Entra: la app y la versión elegidas; los permisos que declara (del hub si ya la conoce, y si no del catálogo). No se confirma el precio ni qué otras apps entrarán: solo la versión (si hay varias) y los permisos de la app pedida.
Sale: pide al servidor la instalación (HUB-F19) y concede los permisos aceptados (HUB-F32); sigue las fases por el canal en vivo. Una instalación empezada desde otro dispositivo se ve igual en esta pantalla, y el aviso «{name} instalado.» sale en todos los dispositivos que tengan Apps abierta. Las apps instaladas de paso no pasan por la pregunta de permisos ni los reciben: una dependencia con permisos de host queda con todo denegado y ningún aviso lo dice (el de HUB_SHELL-F115 es solo de la app pedida). Si se sale de Apps mientras instala, el aviso y su resultado pasan a un aviso global y no se pierden.
Si falla: HUB_SHELL-F110 a F115 según la causa. Si no es administrador: «Puedes ver las apps, pero solo un administrador puede instalarlas, activarlas o desinstalarlas.».
Implicados: HUB-F19, HUB-F32, REC_ALTA-F08, REC_ALTA-F22, SAAS_PUBLIC-F16, SAAS_PUBLIC-F17, SAAS_PUBLIC-F18
QA: BD-03

### HUB_SHELL-F110 Saber qué más se ha instalado de paso
Estado: parcial — el aviso que nombra lo instalado de paso no se va solo ni tiene botón de cerrar, y el aviso «instalado» del canal en vivo puede sustituirlo antes de que se lea (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Apps
Pasos:
1. El administrador instala una app que necesita otras (por ejemplo, Facturación necesita Impuestos).
2. El hub instala primero lo que falta; la fila enseña «Dependencia {name} — {phase}» mientras tanto, con el identificador de la dependencia (por ejemplo `taxes`).
3. Al terminar, el mismo aviso de éxito nombra todo: «{name} instalado correctamente. También se instaló: {names}.», con los nombres como los conoce el catálogo cuando los tiene y, si no, con el identificador.
4. Las apps instaladas de paso aparecen en Mis apps como cualquier otra.
Entra: la lista de apps que el hub instaló de paso.
Sale: nada guardado en la pantalla. Es el reverso del aviso de desinstalar, que nombra lo que se desinstala con ella (HUB_SHELL-F124). Una app sin dependencias nuevas recibe el aviso simple, sin «También se instaló».
Si falla: si no se puede instalar una dependencia, no se instala nada y sale el motivo (HUB_SHELL-F112).
Implicados: HUB-F19, SAAS_PUBLIC-F16
QA: BD-03

### HUB_SHELL-F111 Intentar instalar una app que necesita suscripción
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
1. El administrador pulsa «Instalar» en una app de pago que este negocio no tiene contratada.
2. La pantalla no intenta instalar: dice «{name} necesita una suscripción. Contrátala desde tu cuenta de ERPlora, en erplora.com, y se instalará aquí.». No hay botón que lleve a pagar.
3. El administrador contrata en erplora.com (en el navegador, en el móvil o en otro equipo) y vuelve a la ventana: el catálogo se recarga solo y la app ya se puede instalar.
4. Si la app (de pago o no) necesita otras de pago que faltan, la rechaza el hub y el aviso es otro y fijo: «{name} necesita apps que aún no tienes contratadas: {missing}. No se ha instalado nada.» (con los identificadores de las apps que faltan), con «Cerrar» y sin «Reintentar»; no cambia nada hasta contratar.
Entra: qué apps tiene permitidas el negocio, que manda erplora.com (si aún no se ha podido saber, se deja intentar y el hub decide).
Sale: nada guardado ni cobrado. La pantalla nunca lleva a una página de pago desde dentro (las tiendas de Google y Microsoft lo rechazan).
Si falla: sin conexión con erplora.com no se puede saber si hay suscripción: se deja pasar y el hub la comprueba al instalar.
Implicados: HUB-F19, REC_ALTA-F22, SAAS_DASHBOARD-F108, SAAS_PUBLIC-F16, SAAS_PUBLIC-F20, SAAS_PUBLIC-F21
QA: BD-03

### HUB_SHELL-F112 Ver por qué ha fallado una instalación y reintentarla
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
1. Una instalación falla (firma rechazada, paquete que no pasa la validación, ERPlora sin contestar…).
2. Sale un aviso rojo fijo, encima de la barra de pestañas de Apps, con la frase del hub traducida: por ejemplo «ERPlora no ha contestado a tiempo, así que la app no se ha instalado. Inténtalo en unos minutos.» o «ERPlora no ha aceptado las credenciales de este hub, así que no puede instalar apps. Reintentar no lo arregla; avisa a soporte.».
3. Pulsa «Reintentar» (misma app, misma versión y los mismos permisos ya aceptados, sin volver a preguntar) o «Cerrar».
4. Si lo que falla es de pago sin contratar, el aviso no ofrece reintentar (HUB_SHELL-F111).
Entra: el rechazo del hub con su código.
Sale: nada guardado; el hub deja la instalación como estaba. Sin frase para ese código, sale la frase que mandó el hub tal cual; sin ninguna, «No se pudo iniciar la instalación de {name}.».
Si falla: si el reintento vuelve a fallar, vuelve a salir el aviso con su motivo; al cerrar, la fila queda como «Disponible».
Implicados: HUB-F19
QA: BD-03

### HUB_SHELL-F113 Seguir una instalación mientras se navega
Estado: parcial — el cliente no pone ningún límite a la espera de la orden de instalar (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Apps
Pasos:
1. El administrador lanza una instalación (HUB_SHELL-F109) y se va a otra pantalla del menú.
2. El aviso «Instalando {name}…» sigue a la vista como aviso global; cuando termina, el resultado (éxito o error con «Reintentar») sale donde esté, no en la pantalla de Apps que ya no existe.
3. Al volver a Apps, la fila vuelve a mostrar la fase en cuanto llega el siguiente aviso de progreso.
Entra: los avisos de progreso por fases que manda el hub por el canal en vivo.
Sale: nada guardado. Mientras instala, el resto del hub sigue atendiendo (HUB-F19): quien cobra en otro dispositivo no espera a la instalación; la barra de espera de arriba solo se ve en el dispositivo que instala.
Si falla: si el canal en vivo se cae, la fila se queda en «Instalando…» hasta que la orden contesta o se recarga la pantalla. Si la instalación falla después de salir de Apps y volver, el resultado sale en el aviso global pero la fila de la pantalla nueva sigue en «Instalando…», porque solo la limpia el aviso de instalada (leído en el código, sin ejecutar). La orden de instalar no tiene tiempo máximo en el cliente.
Implicados: HUB-F19
QA: ninguno

### HUB_SHELL-F114 Ver que una app necesita un hub más nuevo
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
1. En el catálogo, una app cuya versión exige una versión de ERPlora más alta que la de este hub sale con el estado «Necesita ERPlora {version}» y sin «Instalar».
2. En su lugar aparece la acción «Ver tu versión de ERPlora y sus actualizaciones», que lleva a **Sistema › Actualizaciones**, donde se ve qué versión corre el hub y qué se le ha cambiado (el hub se actualiza solo).
3. Si no se puede saber la versión del hub, o la app no declara mínimo, no se bloquea nada: el hub rechaza la instalación si hace falta («Esta app necesita un hub más nuevo: actualiza el hub e inténtalo de nuevo.» o, con las dos versiones, «Esta app necesita un hub más nuevo (ERPlora {required}). El tuyo tiene la {core}: actualiza el hub e inténtalo de nuevo.»).
Entra: el mínimo que declara la app y la versión del hub, que viaja en el estado del sistema y solo se pide con sesión de dueño o administrador (HUB-F166): instalar es suyo, así que a quien no administra no se le pide ni se le avisa de ningún mínimo.
Sale: nada guardado.
Si falla: sin la versión del hub (el hub no contestó a quien administra), la comprobación se salta y se avisa en la consola del navegador, no a la persona.
Implicados: HUB-F20, HUB-F166, SAAS_PUBLIC-F15
QA: ninguno

### HUB_SHELL-F115 Saber que una app se instaló sin sus permisos
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
1. El administrador acepta los permisos y la app se instala, pero el hub no puede concederlos.
2. Sale un aviso rojo fijo: ««{name}» se instaló, pero no se pudieron conceder sus permisos. Sin ellos no funcionará: actívalos en Ajustes → Permisos.» con el botón «Ir a Permisos».
3. El botón lleva a **Ajustes › Permisos**, donde se enciende cada permiso de la app.
Entra: el fallo al conceder, que no deshace la instalación.
Sale: la app instalada y sin permisos; nada más.
En este mismo documento se apoya en: HUB_SHELL-F167 (Conceder un permiso a una app).
Si falla: el aviso es el propio fallo; si el permiso tampoco se puede conceder desde Ajustes › Permisos, sale el motivo de esa pantalla.
Implicados: HUB-F19, HUB-F32
QA: ninguno

### HUB_SHELL-F116 Actualizar una app
Estado: parcial — el aviso de «ya está al día» desaparece a los 2,5 s (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Apps
Pasos:
1. Una app instalada con versión nueva sale en **Mis apps** con «1.1.1 → 1.1.2» y el icono «Actualizar» (en el catálogo, con «Actualizar a {version}»). Sin versión nueva no hay botón.
2. El administrador pulsa «Actualizar». Si hay varias versiones por delante, «Elige una versión» (la última, marcada); si hay una, no pregunta. Las que están en cuarentena y las anteriores no salen.
3. Sale «Actualizando {name}…» y la fila muestra el giro. El hub instala y comprueba la versión nueva.
4. Al terminar: «{name} actualizado: {from} → {to}. Recargando para usar la versión nueva…» y la pantalla se recarga sola, porque la pantalla de la versión vieja sigue cargada hasta entonces.
5. Si ya estaba en la última: «{name} ya está en la última versión.».
Entra: la versión nueva que ofrece el catálogo; si soporte ha fijado una versión, esa manda.
Sale: pide al servidor la actualización (HUB-F23). Si falla, el hub deja la versión que había y funcionando.
Si falla: en un aviso rojo que se queda hasta que se pulsa «Cerrar» (ERPlora/hub#2594): «No se pudo actualizar {name}. Sigue funcionando con la versión que tenía.» o la frase del hub; «La versión nueva de {name} necesita apps que aún no tienes contratadas: {missing}. No ha cambiado nada ni se ha cobrado nada.»; si la versión elegida ya no se puede poner (soporte la fijó entretanto, o es anterior a la instalada), «Esta app no se puede pasar a esa versión: soporte ha fijado la versión que usa, o es anterior a la que tienes. No ha cambiado nada.» (hub#2546); y si fallan la nueva y la vuelta atrás, «La actualización ha fallado y no se ha podido recuperar la versión anterior, así que esta app ya no está instalada. Vuelve a instalarla desde Apps; si también falla, avisa a soporte.».
Implicados: HUB-F23, HUB-F24
QA: BD-03

### HUB_SHELL-F117 Actualizar todas las apps de una vez
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
1. En **Mis apps**, si hay apps con versión nueva, arriba sale «{n} apps tienen una versión nueva.» con el botón «Actualizar todas» (solo para administradores; se apaga mientras haya una actualización suelta en curso).
2. Lo pulsa. Se actualizan una detrás de otra, sin preguntar versión (cada una va a la que resuelve el hub): «Actualizando {name} ({current} de {total})…» con una barra, y la fila de la app en curso gira.
3. Al terminar, una lista con cada app: «{from} → {to}», «Ya estaba en la última versión» o el motivo del fallo con «Reintentar», y el resumen «{updated} de {total} apps actualizadas.».
4. Si no ha fallado ninguna, la pantalla se recarga sola una vez («{n} apps actualizadas. Recargando para usar las versiones nuevas…»). Si alguna ha fallado, no recarga: espera a que se lea y muestra «Recargar ahora» (si alguna se actualizó) o «Cerrar».
5. Si en el fondo ya estaban todas al día: «Tus apps ya estaban en la última versión.».
Entra: las apps con versión nueva que el hub marca (las que necesitan un hub más nuevo no entran, HUB_SHELL-F118).
Sale: usa la misma actualización que el botón de cada fila (HUB-F23), así que un fallo de una no frena a las demás. Mientras corre, el botón de cada fila queda apagado.
Si falla: cada fallo sale en su línea con la misma frase que daría «Actualizar» en su fila, incluida la de las apps de pago sin contratar.
Implicados: HUB-F23
QA: BD-03

### HUB_SHELL-F118 Ver que una actualización necesita un hub más nuevo
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
1. Una app instalada tiene versión nueva, pero esa versión exige más ERPlora del que corre el hub.
2. En la fila de Mis apps la versión dice «{version} · La versión {version} necesita ERPlora {floor}» y no hay «Actualizar»: en su lugar, «Ver tu versión de ERPlora y sus actualizaciones», que lleva a **Sistema › Actualizaciones**.
3. En el catálogo la fila dice «La versión {version} necesita ERPlora {floor}».
4. «Actualizar todas» y el aviso de la campana no cuentan esa app.
Entra: el mínimo de la versión nueva que ofrece el catálogo y la versión del hub, que solo se pide con sesión de dueño o administrador (HUB-F166, como en F114).
Sale: nada guardado.
Si falla: sin la versión del hub o sin mínimo declarado, la fila ofrece «Actualizar» como siempre.
Implicados: HUB-F24, HUB-F166
QA: ninguno

### HUB_SHELL-F119 Enterarse de que hay versiones nuevas
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
1. Con la sesión de un administrador, el shell pregunta al hub qué apps tienen versión nueva al entrar, cada seis horas mientras la pantalla esté visible y al cambiar de persona con el PIN.
2. En la campana de Notificaciones aparece «Actualizaciones de apps»: «{n} apps tienen una versión nueva. Actualízalas desde Mis apps.»; al tocarla lleva a **Apps › Mis apps**.
3. Abrir Apps o actualizar una app allí refresca la campana al instante, sin esperar a la siguiente comprobación.
4. Si no se pudo comprobar: «No se ha podido comprobar si hay actualizaciones» con «No hemos podido saber si tus apps tienen versiones nuevas. Revisa la conexión y vuelve a intentarlo.» y el botón «Comprobar de nuevo» (que dice «Comprobando…» mientras pregunta).
Entra: la respuesta del hub, app por app.
Sale: solo el contador de la campana; no se guarda nada. Una comprobación que falla no borra el número anterior ni lo pone a cero.
Si falla: lo dicho en el paso 4; quien no administra no ve este aviso.
Implicados: HUB-F24
QA: ninguno

### HUB_SHELL-F120 Volver a comprobar las actualizaciones cuando falla la comprobación
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
1. En **Mis apps**, el administrador ve un aviso amarillo: «No se ha podido comprobar si hay versiones nuevas de tus apps. Puede que no estén al día.» (el hub no pudo preguntar a erplora.com por alguna app, o la pregunta entera falló).
2. Pulsa «Reintentar» (apagado mientras pregunta).
3. Si contesta bien, el aviso desaparece y salen las actualizaciones que haya; si vuelve a fallar, sigue.
Entra: la respuesta del hub (cada app lleva «he podido comprobarlo» sí o no).
Sale: nada guardado. «No lo sé» nunca se pinta como «al día». Si una app sí se pudo comprobar y tiene versión nueva, se sigue ofreciendo aunque el aviso siga.
Si falla: el aviso no sale en el catálogo ni a quien no administra.
Implicados: HUB-F24
QA: ninguno

### HUB_SHELL-F121 Ver qué apps ya no se ofrecen
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Apps
Pasos:
1. Una app instalada que el catálogo ha retirado sale en **Mis apps** con la etiqueta «Retirada» junto al nombre.
2. Arriba, un aviso en amarillo lo explica: «Ya no están en el catálogo: {apps}. Aquí siguen funcionando y siguen recibiendo actualizaciones — simplemente ya no se ofrecen, así que no las encontrarás para instalarlas en otro sitio.». Es cierto en producción, donde erplora.com las sigue sirviendo a quien ya las tiene; en PRE no: el permiso firmado de PRE sale del catálogo y deja fuera las retiradas (HUB-F162). Si la app es de pago, su suscripción ya no se gestiona desde la página de erplora.com, que contesta 404 a una app fuera del catálogo.
3. La app sigue como cualquier otra: se abre, se desactiva y se desinstala.
Entra: para las apps que el catálogo no lista, el estado de publicación que pregunta el hub una a una. Con un hub sano no cuesta ninguna petición.
Sale: nada guardado.
Si falla: si no se puede preguntar, o el catálogo entero ha fallado, no se pinta nada: «no lo sé» no es «retirada». Una app solo «sin listar» (instalable por enlace directo) no lleva etiqueta.
Implicados: SAAS_DASHBOARD-F186, SAAS_DASHBOARD-F187, SAAS_PUBLIC-F22
QA: ninguno

### HUB_SHELL-F122 Desactivar una app
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
1. En la fila de una app activa de **Mis apps**, el administrador pulsa el icono «Activar/Desactivar».
2. La pantalla pregunta siempre, con el nombre de la app en el título: «Desactivar {name}»: «{name} desaparece del TPV y sus pantallas dejan de abrirse. No se borra nada: al volver a activarla queda como estaba.».
3. Si otras apps dependen de ella, la misma pregunta añade «También se desactivarán (dependen de {name}):» y la lista con sus nombres.
4. Confirma con «Desactivar». Sale «{name} desactivado.», la fila pasa a «Inactivo», las arrastradas a «Inactivo (en cascada)» y la app desaparece del menú.
Entra: las dependencias que declaran las apps instaladas.
Sale: pide al servidor apagarla (HUB-F28). Los datos no se tocan. Cada pestaña y dispositivo del hub recibe el cambio y se refresca.
Si falla: en un aviso rojo que se queda hasta que se pulsa «Cerrar» (ERPlora/hub#2594): «No se pudo cambiar el estado de {name}.» o la frase del motor que se niega (HUB_SHELL-F125).
Implicados: HUB-F28, VERIFACTU-F32
QA: L-14

### HUB_SHELL-F123 Activar una app
Estado: parcial — si falta una dependencia, el hub responde con error pero deja la app activa, y la fila sigue «Inactivo» hasta recargar (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Apps
Pasos:
1. En la fila de una app inactiva, el administrador pulsa el mismo icono «Activar/Desactivar».
2. Pregunta «Activar {name}»: «{name} vuelve al TPV, con los datos que ya tenía.», y si necesita apps apagadas, «También se activarán (los necesita {name}):» con sus nombres.
3. Confirma con «Activar». Sale «{name} activado.», vuelve al menú y las arrastradas por una dependencia que se apagó vuelven solas.
Entra: las dependencias declaradas.
Sale: pide al servidor encenderla (HUB-F27).
Si falla: en el mismo aviso rojo que se queda hasta que se pulsa «Cerrar» que al desactivar, «No se pudo cambiar el estado de {name}.» o la frase del hub; la pantalla solo recarga la lista si todo va bien, así que ese error no muestra la app ya activa.
Implicados: HUB-F27
QA: ninguno

### HUB_SHELL-F124 Desinstalar una app
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
1. En la fila de la app de **Mis apps**, el administrador pulsa el icono rojo «Desinstalar».
2. Pregunta «Desinstalar {name}». Si otras apps la necesitan —también las apagadas, y en cadena— las nombra antes: «Estas apps necesitan {name} y también se desinstalarán:» con la lista.
3. Debajo, siempre: «La app dejará de estar disponible. Sus datos y archivos se conservarán para una reinstalación posterior.».
4. Confirma con «Desinstalar». Sale «{name} desinstalado.»; ella y las apps nombradas desaparecen de Mis apps y del menú, y el catálogo vuelve a ofrecerlas.
Entra: las apps instaladas y sus dependencias, para nombrar lo que se va con ella.
Sale: pide al servidor desinstalar (HUB-F29), forzando solo si la pregunta ya nombró dependientes: el hub quita juntas la app y esas dependientes, y ninguna vuelve al reiniciar. Los datos y archivos de todas se quedan en la base y en Archivos.
Si falla: en un aviso rojo que se queda hasta que se pulsa «Cerrar» (ERPlora/hub#2594): «No se pudo desinstalar {name}.»; si la lista con la que se preguntó se había quedado vieja y el hub encuentra dependientes: «{name} no se ha desinstalado: estas apps lo necesitan — {apps}. Desinstálalas antes.» (con los identificadores que mandó el hub y la lista recargada); o la negativa de un motor (HUB_SHELL-F125).
Implicados: HUB-F29, VERIFACTU-F32
QA: L-14

### HUB_SHELL-F125 Ver que una app se niega a desactivarse o desinstalarse
Estado: parcial — la de VeriFactu no dice cuántos registros faltan: el hub manda el número solo dentro de su frase inglesa, no como dato (ERPlora/hub#2595) (visto en el banco, hub#2579)
Actor: administrador
Pantalla: Apps
Pasos:
1. El administrador intenta desactivar VeriFactu o una app cuya desactivación lo arrastra (Facturación), o desinstalar VeriFactu, con registros sin aceptar por la AEAT; o desactivar o desinstalar la última app que cumple el régimen fiscal del negocio. Desinstalar una app de la que depende VeriFactu también pasa por la negativa de su motor, porque confirmar la pregunta se la llevaría con ella (HUB_SHELL-F124).
2. El hub se niega y no cambia nada: ni la pedida ni las arrastradas.
3. La pantalla enseña el motivo en un aviso rojo, en el idioma de la pantalla, que se queda hasta que el administrador pulsa «Cerrar» (ERPlora/hub#2594): son frases largas que dicen qué hacer. VeriFactu con registros pendientes: «VeriFactu aún tiene registros que la AEAT no ha aceptado. Abre VeriFactu para enviarlos o corregirlos y vuelve a intentarlo.». La última app fiscal: «Tu negocio tiene que conservar una app que envíe sus facturas a Hacienda, y así se quedaría sin ninguna. Instala antes otra app que lo haga y vuelve a intentarlo.».
4. La app sigue «Activo» en la fila.
Entra: el rechazo del hub con el código del motor y la frase que mandó.
Sale: nada guardado. La pantalla traduce por el código las dos negativas fiscales (`verifactu.unsent_records`, `fiscal.no_provider_left`, hub#2579) igual que los códigos de plataforma; la frase de un motor cuyo código no conoce (uno publicado después que la pantalla) la pinta tal cual, porque dice más que cualquier genérico.
Si falla: sin frase del hub, «No se pudo cambiar el estado de {name}.» o «No se pudo desinstalar {name}.».
Implicados: HUB-F28, HUB-F29, VERIFACTU-F32
QA: L-14


## Cobertura contra la referencia

| Elemento | Estado | Flujo |
|---|---|---|
| Mis apps y catálogo con búsqueda y filtros | hecho | HUB_SHELL-F105 a F107 |
| Precio y plan de cada app | hecho | HUB_SHELL-F108 |
| Instalar, con versión, permisos y fases en vivo | parcial (hub retenido sin aviso) | HUB_SHELL-F109, F113 |
| Dependencias instaladas de paso | parcial (aviso fijo sin cerrar) | HUB_SHELL-F110 |
| App de pago sin contratar | hecho | HUB_SHELL-F111 |
| Error de instalación visible con reintento | hecho | HUB_SHELL-F112 |
| Necesita un hub más nuevo (instalar y actualizar) | hecho | HUB_SHELL-F114, F118 |
| Permisos de la app al instalar | hecho (todo o nada) | HUB_SHELL-F109, F115 |
| Conceder solo algunos de los permisos pedidos | no hecho | HUB_SHELL-F109 |
| Actualizar una / actualizar todas | parcial / hecho | HUB_SHELL-F116, F117 |
| Bajar de versión desde la pantalla | no hecho, a propósito (lo hace soporte con el pin; tampoco por la API, hub#2546) | HUB_SHELL-F116 |
| Ver qué cambia en la versión nueva antes de actualizar | no hecho (el historial está en Sistema › Actualizaciones, ya hecho) | HUB_SHELL-F116 |
| Aviso de versiones nuevas en la campana y reintento | hecho | HUB_SHELL-F119, F120 |
| App retirada del catálogo | hecho | HUB_SHELL-F121 |
| Desactivar / activar con cascada | hecho / parcial | HUB_SHELL-F122, F123 |
| Desinstalar nombrando lo que se va con ella | hecho (se quitan juntas al confirmar) | HUB_SHELL-F124 |
| Negativa de un motor (VeriFactu) | parcial (sin el número de registros; el aviso se queda hasta cerrarlo) | HUB_SHELL-F125 |

## Datos: de quién es cada dato

- **Apps instaladas, versiones y permisos**: del hub; el catálogo, el precio, la suscripción y el
  estado de publicación son de erplora.com. La pantalla no guarda nada.

## Reglas que no se rompen

- **Instalar, desactivar y desinstalar solo las ofrece la pantalla a un administrador**, y siempre
  preguntan antes de desactivar o desinstalar (el hub lo vuelve a comprobar: regla común del índice).
- Una lista que no se pudo leer (apps, catálogo) dice que no se pudo y conserva lo que ya tenía
  (`apps-refresh-keeps-the-screen.test.ts`; regla común del índice).

## Lo que NO hace, a propósito

- No baja una app de versión ni deja elegir qué permisos aceptar de los que pide.

## Dudas abiertas

Se resuelven con `market-decision`; no las decide el worker.

- ¿Conceder solo parte de los permisos que pide una app al instalar?

## Fuentes contrastadas

- Servidor HUB-F29: no hay opción aparte «quitarla igualmente»; confirmar la pregunta ya fuerza, y
  forzar se lleva las dependientes que la pregunta nombró (hub#2545).
- VERIFACTU-F32: hasta hub#2594 la frase salía en un aviso que desaparecía a los 2,5 s; ahora se queda hasta
  que se pulsa «Cerrar», como el fallo de instalar (hub#2244).
- Servidor HUB-F28 y VERIFACTU-F32: hasta hub#2579 la negativa fiscal salía en inglés en la pantalla
  española (la pantalla solo traducía códigos de plataforma); ahora se traduce por el código, y el
  número de registros pendientes, que el hub solo manda dentro de su frase inglesa, no se enseña.
- Servidor HUB-F23: una versión explícita sigue la regla de la lista (con pin, solo el pin; sin pin,
  solo hacia delante) y la que no la cumple sale `update_version_not_offered` (hub#2546).
