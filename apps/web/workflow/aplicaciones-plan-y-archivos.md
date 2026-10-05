# WORKFLOW — Hub (pantallas) · Aplicaciones, plan y archivos

Prefijo: HUB_SHELL

> Detalle del área «Aplicaciones, plan y archivos» (oleada 3): la pantalla **Apps** (tus apps y el
> catálogo: instalar, actualizar, activar, desactivar y desinstalar), **Mi plan** (facturas,
> suscripciones y pagos), los **límites del plan** (la pestaña Plan y límites de Sistema, cuyo resto
> es de otra área), las puertas hacia erplora.com para gestionar o mejorar el plan, y **Archivos**.
> Aquí se cuenta lo que ve la persona; qué hace el servidor detrás está en
> `hub-wf-modulos/workflow/modulos-aplicaciones.md` (HUB-F19…F35), `hub-wf-acceso/workflow/plan-y-sistema.md`
> (HUB-F162, F165) y `hub-wf-negocio-datos/workflow/negocio-y-datos.md` (HUB-F245, F246) y no se
> repite. Código: `apps/web/src/views/AppsPage.vue`, `BillingPage.vue`, `FilesPage.vue`,
> `components/PlanLimitsPanel.vue`, `FilePreviewModal.vue` y `lib/apps-catalog.ts`, `apps-list-columns.ts`,
> `installed-app-actions.ts`, `module-updates.ts`, `module-update-notice.ts`, `module-failure-message.ts`,
> `entitlement.ts`, `upgrade-plan-link.ts`, `management-link.ts`, `saas-door.ts`, `media.ts`,
> `file-preview.ts`.

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
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F31 (servir el menú, las pantallas y los ficheros de las aplicaciones, de donde sale la lista de apps)
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
Entra: el catálogo de erplora.com que reenvía el hub, en el idioma del negocio; cruzado con las apps instaladas en el hub, que es lo que manda para decir «Instalado» (el catálogo puede ir por detrás).
Sale: nada guardado. Recupera el catálogo al volver el foco a la ventana, para ver al instante una suscripción contratada fuera.
Si falla: «No se pudo cargar el catálogo. Revisa la conexión o el registro de este dispositivo.» con «Reintentar»; las filas que ya había se conservan. Sin respuesta todavía, «Cargando el catálogo…»; con una búsqueda sin resultados, «No hay apps que coincidan con tu búsqueda.» (cada situación con su frase).
Implicados: pendiente
Pendiente de enlazar: saas — marketplace: el catálogo de apps que reenvía el hub
QA: BD-03

### HUB_SHELL-F108 Saber cuánto cuesta una app antes de instalarla
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Apps
Pasos:
1. En el catálogo, la columna «Precio» dice «Gratis», «Incluida en tu plan», «{price} €/mes», «{price} €/año», «{price} €» (pago único) o «Consultar».
2. Si erplora.com manda una etiqueta de precio propia, esa es la que sale tal cual.
3. Una app sin importe conocido nunca enseña la unidad sola («€/mes» sin cifra): sale «Consultar».
4. La pestaña **De pago** reúne todo lo que no es gratis, incluidas las «Incluida en tu plan».
Entra: el precio, el ciclo y si va en el plan, que manda erplora.com.
Sale: nada guardado. El hub no cobra ni lleva a comprar: contratar es cosa de erplora.com (HUB_SHELL-F111).
Si falla: sin catálogo, HUB_SHELL-F107.
Implicados: pendiente
Pendiente de enlazar: saas — marketplace: precio, ciclo y plan de cada app
QA: ninguno

### HUB_SHELL-F109 Instalar una app
Estado: parcial — mientras dura la instalación el hub retiene todas las consultas y órdenes, también las de la caja, y ninguna pantalla se lo dice a quien está cobrando (solo la persona que instala ve «Instalando…»); y el aviso de éxito de la propia pantalla y el que llega del hub por el canal en vivo pueden pisarse entre sí (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Apps
Pasos:
1. En **Añadir apps**, el administrador pulsa el icono «Instalar» de una app «Disponible».
2. Si hay varias versiones publicadas, aparece «Elige una versión»: «Está seleccionada la última. Elige otra solo si te lo ha pedido soporte.», con «Continuar» y «Cancelar». Si hay una sola, no pregunta.
3. Si la app declara permisos, aparece «Permisos solicitados»: «Esta app solicita estos permisos. Podrás revisarlos después en Ajustes → Permisos.», con cada permiso y su descripción y los botones «Instalar y conceder» y «Cancelar». No se puede conceder solo una parte. Sin permisos, se instala directamente.
4. La fila pasa a «Instalando…» y va diciendo la fase: «Resolviendo versión…», «Descargando…», «Verificando integridad…», «Aplicando migraciones…»; si instala una dependencia, «Dependencia {name} — {phase}». Un aviso fijo dice «Instalando {name}…».
5. Al terminar sale «{name} instalado correctamente.» (se va solo), la fila pasa a «Instalado» y la app aparece en el menú y en Mis apps sin recargar.
Entra: la app y la versión elegidas; los permisos que declara (del hub si ya la conoce, y si no del catálogo).
Sale: pide al servidor la instalación (HUB-F19) y concede los permisos aceptados (HUB-F32); sigue las fases por el canal en vivo. Una instalación empezada desde otro dispositivo se ve igual en esta pantalla. Si se sale de Apps mientras instala, el aviso y su resultado pasan a un aviso global y no se pierden.
Si falla: HUB_SHELL-F110 a F115 según la causa. Si no es administrador: «Puedes ver las apps, pero solo un administrador puede instalarlas, activarlas o desinstalarlas.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F19 (instalar una aplicación del catálogo)
Pendiente de enlazar: hub — HUB-F32 (conceder o retirar un permiso de host a una aplicación)
Pendiente de enlazar: saas — marketplace: el plan de instalación, las versiones y la descarga
QA: BD-03

### HUB_SHELL-F110 Saber qué más se ha instalado de paso
Estado: parcial — el aviso que nombra lo instalado de paso no se va solo ni tiene botón de cerrar, y el aviso «instalado» del canal en vivo puede sustituirlo antes de que se lea (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Apps
Pasos:
1. El administrador instala una app que necesita otras (por ejemplo, Facturación necesita Impuestos).
2. El hub instala primero lo que falta; la fila enseña «Dependencia {name} — {phase}» mientras tanto.
3. Al terminar, el mismo aviso de éxito nombra todo: «{name} instalado correctamente. También se instaló: {names}.», con los nombres como los conoce el catálogo.
4. Las apps instaladas de paso aparecen en Mis apps como cualquier otra.
Entra: la lista de apps que el hub instaló de paso.
Sale: nada guardado en la pantalla. Es el reverso del aviso de desinstalar, que nombra lo que dejaría de funcionar (HUB_SHELL-F124). Una app sin dependencias nuevas recibe el aviso simple, sin «También se instaló».
Si falla: si no se puede instalar una dependencia, no se instala nada y sale el motivo (HUB_SHELL-F112).
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F19 (instalar una aplicación del catálogo: el plan de instalación con sus dependencias)
QA: BD-03

### HUB_SHELL-F111 Intentar instalar una app que necesita suscripción
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
1. El administrador pulsa «Instalar» en una app de pago que este negocio no tiene contratada.
2. La pantalla no intenta instalar: dice «{name} necesita una suscripción. Contrátala desde tu cuenta de ERPlora, en erplora.com, y se instalará aquí.». No hay botón que lleve a pagar.
3. El administrador contrata en erplora.com (en el navegador, en el móvil o en otro equipo) y vuelve a la ventana: el catálogo se recarga solo y la app ya se puede instalar.
4. Si la app (de pago o no) necesita otras de pago que faltan, la rechaza el hub y el aviso es otro y fijo: «{name} necesita apps que aún no tienes contratadas: {missing}. No se ha instalado nada.», con «Cerrar» y sin «Reintentar»; no cambia nada hasta contratar.
Entra: qué apps tiene permitidas el negocio, que manda erplora.com (si aún no se ha podido saber, se deja intentar y el hub decide).
Sale: nada guardado ni cobrado. La pantalla nunca lleva a una página de pago desde dentro (las tiendas de Google y Microsoft lo rechazan).
Si falla: sin conexión con erplora.com no se puede saber si hay suscripción: se deja pasar y el hub la comprueba al instalar.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F19 (instalar una aplicación del catálogo: dependencia de pago sin contratar)
Pendiente de enlazar: saas — suscripción de las apps de pago
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
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F19 (instalar una aplicación del catálogo: los motivos de rechazo)
QA: BD-03

### HUB_SHELL-F113 Seguir una instalación mientras se navega
Estado: parcial — mientras instala, las demás pantallas del hub esperan sin avisar de por qué, y el cliente no pone ningún límite a la espera de la orden de instalar (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Apps
Pasos:
1. El administrador lanza una instalación (HUB_SHELL-F109) y se va a otra pantalla del menú.
2. El aviso «Instalando {name}…» sigue a la vista como aviso global; cuando termina, el resultado (éxito o error con «Reintentar») sale donde esté, no en la pantalla de Apps que ya no existe.
3. Al volver a Apps, la fila vuelve a mostrar la fase en cuanto llega el siguiente aviso de progreso.
Entra: los avisos de progreso por fases que manda el hub por el canal en vivo.
Sale: nada guardado. La retención de consultas y órdenes durante la instalación es del servidor (HUB-F19): la pantalla de Apps no la nombra y quien cobra en otro dispositivo solo nota que sus pantallas tardan.
Si falla: si el canal en vivo se cae, la fila se queda en «Instalando…» hasta que la orden contesta o se recarga la pantalla.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F19 (instalar una aplicación del catálogo: el hub retiene todas las órdenes mientras dura)
QA: ninguno

### HUB_SHELL-F114 Ver que una app necesita un hub más nuevo
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Apps
Pasos:
1. En el catálogo, una app cuya versión exige una versión de ERPlora más alta que la de este hub sale con el estado «Necesita ERPlora {version}» y sin «Instalar».
2. En su lugar aparece la acción «Ver tu versión de ERPlora y sus actualizaciones», que lleva a **Sistema › Actualizaciones**, donde se ve qué versión corre el hub y qué se le ha cambiado (el hub se actualiza solo).
3. Si no se puede saber la versión del hub, o la app no declara mínimo, no se bloquea nada: el hub rechaza la instalación si hace falta («Esta app necesita un hub más nuevo: actualiza el hub e inténtalo de nuevo.» o, con las dos versiones, «Esta app necesita un hub más nuevo (ERPlora {required}). El tuyo tiene la {core}: actualiza el hub e inténtalo de nuevo.»).
Entra: el mínimo que declara la app y la versión del hub.
Sale: nada guardado.
Si falla: sin la versión del hub, la comprobación se salta y se avisa en la consola del navegador, no a la persona.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F20 (rechazar un paquete que rompe las reglas del hub: `core_version_too_old`)
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
Si falla: el aviso es el propio fallo; si el permiso tampoco se puede conceder desde Ajustes › Permisos, sale el motivo de esa pantalla.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F32 (conceder o retirar un permiso de host a una aplicación)
Pendiente de enlazar: hub — HUB_SHELL, Ajustes › Permisos (la pantalla donde se conceden los permisos de cada app)
QA: ninguno

### HUB_SHELL-F116 Actualizar una app
Estado: parcial — la pantalla solo ofrece versiones hacia delante (bajar de versión existe en el hub por la API con una versión explícita, pero no tiene botón); y los avisos de error y de «ya está al día» desaparecen a los 2,5 s (leído en el código, sin ejecutar)
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
Si falla: «No se pudo actualizar {name}. Sigue funcionando con la versión que tenía.» o la frase del hub; «La versión nueva de {name} necesita apps que aún no tienes contratadas: {missing}. No ha cambiado nada ni se ha cobrado nada.»; y si fallan la nueva y la vuelta atrás, «La actualización ha fallado y no se ha podido recuperar la versión anterior, así que esta app ya no está instalada. Vuelve a instalarla desde Apps; si también falla, avisa a soporte.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F23 (actualizar una aplicación)
Pendiente de enlazar: hub — HUB-F24 (consultar qué actualizaciones y versiones hay)
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
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F23 (actualizar una aplicación)
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
Entra: el mínimo de la versión nueva que ofrece el catálogo y la versión del hub.
Sale: nada guardado.
Si falla: sin la versión del hub o sin mínimo declarado, la fila ofrece «Actualizar» como siempre.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F24 (consultar qué actualizaciones y versiones hay: si hace falta un hub más nuevo)
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
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F24 (consultar qué actualizaciones y versiones hay)
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
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F24 (consultar qué actualizaciones y versiones hay: sin credencial o sin ERPlora sale «no lo sé»)
QA: ninguno

### HUB_SHELL-F121 Ver qué apps ya no se ofrecen
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Apps
Pasos:
1. Una app instalada que el catálogo ha retirado sale en **Mis apps** con la etiqueta «Retirada» junto al nombre.
2. Arriba, un aviso en amarillo lo explica: «Ya no están en el catálogo: {apps}. Aquí siguen funcionando y siguen recibiendo actualizaciones — simplemente ya no se ofrecen, así que no las encontrarás para instalarlas en otro sitio.».
3. La app sigue como cualquier otra: se abre, se desactiva y se desinstala.
Entra: para las apps que el catálogo no lista, el estado de publicación que pregunta el hub una a una. Con un hub sano no cuesta ninguna petición.
Sale: nada guardado.
Si falla: si no se puede preguntar, o el catálogo entero ha fallado, no se pinta nada: «no lo sé» no es «retirada». Una app solo «sin listar» (instalable por enlace directo) no lleva etiqueta.
Implicados: pendiente
Pendiente de enlazar: saas — marketplace: el estado de publicación de una app (listada, sin listar, retirada)
QA: ninguno

### HUB_SHELL-F122 Desactivar una app
Estado: parcial — el error de desactivar sale en un aviso que desaparece a los 2,5 s, también cuando es la negativa larga de un motor en inglés (HUB_SHELL-F125) (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Apps
Pasos:
1. En la fila de una app activa de **Mis apps**, el administrador pulsa el icono «Activar/Desactivar».
2. La pantalla pregunta siempre, con el nombre de la app en el título: «Desactivar {name}»: «{name} desaparece del TPV y sus pantallas dejan de abrirse. No se borra nada: al volver a activarla queda como estaba.».
3. Si otras apps dependen de ella, la misma pregunta añade «También se desactivarán (dependen de {name}):» y la lista con sus nombres.
4. Confirma con «Desactivar». Sale «{name} desactivado.», la fila pasa a «Inactivo», las arrastradas a «Inactivo (en cascada)» y la app desaparece del menú.
Entra: las dependencias que declaran las apps instaladas.
Sale: pide al servidor apagarla (HUB-F28). Los datos no se tocan. Cada pestaña y dispositivo del hub recibe el cambio y se refresca.
Si falla: «No se pudo cambiar el estado de {name}.» o la frase del motor que se niega (HUB_SHELL-F125).
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F28 (desactivar una aplicación preguntando antes si puede irse)
Pendiente de enlazar: verifactu — VERIFACTU-F32 (impedir apagar o desinstalar con registros sin enviar)
QA: L-14

### HUB_SHELL-F123 Activar una app
Estado: hecho
Actor: administrador
Pantalla: Apps
Pasos:
1. En la fila de una app inactiva, el administrador pulsa el mismo icono «Activar/Desactivar».
2. Pregunta «Activar {name}»: «{name} vuelve al TPV, con los datos que ya tenía.», y si necesita apps apagadas, «También se activarán (los necesita {name}):» con sus nombres.
3. Confirma con «Activar». Sale «{name} activado.», vuelve al menú y las arrastradas por una dependencia que se apagó vuelven solas.
Entra: las dependencias declaradas.
Sale: pide al servidor encenderla (HUB-F27).
Si falla: «No se pudo cambiar el estado de {name}.» o la frase del hub.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F27 (activar una aplicación)
QA: ninguno

### HUB_SHELL-F124 Desinstalar una app
Estado: parcial — «quitarla igualmente» no es un botón aparte: confirmar la pregunta ya fuerza la desinstalación aunque otras apps la necesiten, y qué pasa con esas apps en el siguiente arranque no se ha confirmado (HUB-F29)
Actor: administrador
Pantalla: Apps
Pasos:
1. En la fila de la app de **Mis apps**, el administrador pulsa el icono rojo «Desinstalar».
2. Pregunta «Desinstalar {name}». Si otras apps la necesitan —también las apagadas, y en cadena— las nombra antes: «Estas apps necesitan {name} y dejarán de funcionar:» con la lista.
3. Debajo, siempre: «La app dejará de estar disponible. Sus datos y archivos se conservarán para una reinstalación posterior.».
4. Confirma con «Desinstalar». Sale «{name} desinstalado.», desaparece de Mis apps y del menú, y el catálogo vuelve a ofrecerla.
Entra: las apps instaladas y sus dependencias, para nombrar lo que se rompe.
Sale: pide al servidor desinstalar (HUB-F29), forzando solo si la pregunta ya nombró dependientes. Los datos y archivos se quedan en la base y en Archivos.
Si falla: «No se pudo desinstalar {name}.»; si la lista con la que se preguntó se había quedado vieja y el hub encuentra dependientes: «{name} no se ha desinstalado: estas apps lo necesitan — {apps}. Desinstálalas antes.» (con los nombres que mandó el hub y la lista recargada); o la negativa de un motor (HUB_SHELL-F125).
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F29 (desinstalar una aplicación)
Pendiente de enlazar: verifactu — VERIFACTU-F32 (impedir apagar o desinstalar con registros sin enviar)
QA: L-14

### HUB_SHELL-F125 Ver que una app se niega a desactivarse o desinstalarse
Estado: parcial — la negativa de un motor sale con la frase en inglés tal como la escribió el motor, en un aviso que desaparece a los 2,5 s (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Apps
Pasos:
1. El administrador intenta desactivar o desinstalar VeriFactu (o una app de la que depende, como Facturación), o la última app que cumple el régimen fiscal del negocio, con registros sin aceptar por la AEAT.
2. El hub se niega y no cambia nada: ni la pedida ni las arrastradas.
3. La pantalla enseña el motivo en un aviso rojo; en el caso de VeriFactu: «{n} VeriFactu record(s) have not reached the AEAT yet: send them before disabling or removing the module.».
4. La app sigue «Activo» en la fila.
Entra: el rechazo del hub con el código del motor y la frase que mandó.
Sale: nada guardado. La pantalla solo conoce códigos genéricos de plataforma; la frase de un motor la pinta tal cual, porque el hub dice más que cualquier genérico.
Si falla: sin frase del hub, «No se pudo cambiar el estado de {name}.» o «No se pudo desinstalar {name}.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F28 (desactivar una aplicación preguntando antes si puede irse)
Pendiente de enlazar: hub — HUB-F29 (desinstalar una aplicación)
Pendiente de enlazar: verifactu — VERIFACTU-F32 (impedir apagar o desinstalar con registros sin enviar)
QA: L-14

### HUB_SHELL-F126 Ver las facturas del plan y descargarlas
Estado: parcial — el estado de una suscripción se pinta con el vocabulario de las facturas y cualquier valor que la pantalla no conoce sale como «Abierta» (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Mi plan
Pasos:
1. La persona pulsa **Mi plan** en el menú lateral. Se abre en **Facturas**.
2. Con la sesión de su cuenta de erplora.com ve una tabla: «Factura», «Fecha», «Vencimiento», «Importe» (en la moneda de la factura) y «Estado» («Borrador», «Abierta», «Pagada», «Anulada» o «Incobrable»). Sin facturas: «No hay facturas».
3. Pulsa «Descargar» en una fila. La factura se guarda como `factura-<número>.pdf`; sale «Guardado en {path}» si la app instalada dice dónde.
4. Quien entró solo con un PIN ve en su lugar «Consulta la facturación en tu cuenta de ERPlora»: «Tu sesión local sigue activa. Las facturas y suscripciones requieren la sesión de tu cuenta online en erplora.com.».
Entra: las facturas que da erplora.com con la sesión de la cuenta; el PDF se pide al descargar.
Sale: nada guardado en el hub. El hub no emite ni cobra: es información del plan.
Si falla: «No pudimos cargar la facturación» con «Comprueba la conexión e inténtalo de nuevo. Puedes seguir utilizando el Hub.» y «Reintentar»; si falla la descarga, un aviso (con la frase propia de la app instalada cuando no puede guardar archivos).
Implicados: pendiente
Pendiente de enlazar: saas — facturas y suscripciones del negocio en el panel de erplora.com
QA: ninguno

### HUB_SHELL-F127 Ver las suscripciones y dónde se gestionan los pagos
Estado: parcial — «Renueva» enseña la fecha aunque la suscripción esté marcada para cancelarse al final del periodo, y eso no se dice en la pantalla (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Mi plan
Pasos:
1. En **Mi plan** el administrador pulsa **Suscripciones**.
2. Lee arriba «Los cambios de plan se gestionan desde tu cuenta de ERPlora, en erplora.com.» y la tabla: «Suscripción», «Precio» (importe y ciclo, por ejemplo «/mes»), «Renueva» y «Estado». Sin ninguna: «No hay suscripciones activas».
3. Al volver a la ventana o a la pestaña del navegador, se recargan solas: contratar o cancelar en erplora.com se ve al volver.
4. En **Pagos** solo hay un aviso: «Los métodos de pago se gestionan desde tu cuenta de ERPlora, en erplora.com.».
Entra: las suscripciones que da erplora.com.
Sale: nada guardado. No hay botón para comprar, cambiar o cancelar: se hace fuera.
Si falla: lo mismo que HUB_SHELL-F126 (cuenta no iniciada, o error con «Reintentar»).
Implicados: pendiente
Pendiente de enlazar: saas — facturas y suscripciones del negocio en el panel de erplora.com
QA: ninguno

### HUB_SHELL-F128 Ver cuánto de los límites del plan se está usando
Estado: parcial — la etiqueta «Dentro del límite» / «Cerca del límite» solo puede cambiar en el plan gratuito: en un plan de pago sigue diciendo «Dentro del límite» aunque una barra esté en rojo; y con la pestaña ya abierta, una actualización que falla deja los últimos números sin avisar (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Sistema
Pasos:
1. El administrador abre **Sistema › Plan y límites**.
2. Ve el «Plan actual» con una etiqueta «Dentro del límite» o «Cerca del límite» y cinco tarjetas: «Memoria (RAM)», «CPU», «Base de datos», «Dispositivos» y «Personas». Memoria, CPU y base de datos llevan porcentaje y barra (verde, amarilla desde el 80 %, roja desde el 90 %); Dispositivos y Personas dicen «{n} / {tope}» y «Límite del plan» (o «Ilimitado»).
3. Lo que no se pudo medir sale como «n/d» («No disponible en este equipo»), nunca como cero. La base de datos sin cuota dice «Sin cuota de plan».
4. Se actualiza cada cinco segundos mientras la pestaña está abierta y visible («En vivo — se actualiza cada pocos segundos mientras esta página está abierta.»).
5. En el plan gratuito, si algún límite está al 80 % o todas las plazas de personas o dispositivos están ocupadas, arriba sale «Te estás quedando sin margen en tu plan» con la frase de la causa y «Los planes se gestionan desde tu cuenta de ERPlora, en erplora.com.», sin botón.
Entra: el uso del hub y los topes del último plan verificado (HUB-F165).
Sale: nada guardado.
Si falla: «Las métricas de recursos no están disponibles» con «El Hub no ha podido informar de su uso de recursos ahora mismo. Puedes reintentarlo.» y «Reintentar».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F165 (ver el uso de recursos frente a los límites del plan)
Pendiente de enlazar: hub — HUB-F162 (comprobar el plan y qué apps puede usar el negocio)
QA: ninguno

### HUB_SHELL-F129 Ir a erplora.com a gestionar o mejorar el plan
Estado: hecho
Actor: administrador, responsable, empleado
Pantalla: Mi plan
Pasos:
1. Al pie del menú lateral está el botón «Actualizar plan». Lo ve cualquier perfil (el dueño suele entrar con la sesión de la caja y esconderle su plan sería peor); lo que el hub hace al llegar lo decide erplora.com según el perfil.
2. Lo pulsa. Se abre el navegador del sistema en la página de cambio de plan de este hub en erplora.com, ya identificado con un pase de un solo uso (dentro de la app instalada el navegador no comparte cookies).
3. En la barra superior, un administrador que entró con su cuenta ve también el botón «erplora.com» («Gestiona tu negocio en erplora.com»), que abre el panel de este negocio.
4. Si no se puede abrir el navegador: «No se pudo abrir tu navegador. Entra en erplora.com para gestionar tu plan.» (o «…para gestionar tu negocio.»). Si el pase no se puede acuñar, se abre el enlace normal.
5. En la copia de la aplicación que reparte Google Play estos dos botones no están (la tienda lo trata como empujar al pago); los textos de Mi plan, Plan y límites y la ficha de persona siguen diciendo dónde se gestiona.
Entra: la distribución de la copia, la sesión (cuenta o PIN) y el identificador del negocio.
Sale: nada guardado en el hub; el pase lo pide el hub a erplora.com (HUB-F142).
Si falla: lo dicho en el paso 4; nunca un botón que no hace nada.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F142 (abrir erplora.com ya identificado)
Pendiente de enlazar: saas — emitir y canjear el pase de un solo uso hacia el panel
QA: L-17

### HUB_SHELL-F130 Ver los archivos del negocio
Estado: hecho
Actor: administrador, responsable, empleado, cajero
Pantalla: Archivos
Pasos:
1. La persona pulsa **Archivos** en el menú lateral (la ven todos los perfiles).
2. Mientras carga, el gestor muestra el indicador. Después ve el árbol de carpetas a la izquierda (en una pantalla estrecha se pliega en un selector), la ruta de la carpeta abierta, los archivos en vista de cuadrícula o de lista y el espacio usado («Espacio», o «Sin límite»).
3. Navega pulsando carpetas, busca en «Buscar archivos…» (solo dentro de la carpeta abierta) y, sin archivos, lee «Sin archivos».
4. En la raíz están las carpetas de las apps (adjuntos de cada una), los registros del sistema y la actividad. Algunas son de solo lectura.
Entra: el listado de la carpeta con qué se puede hacer en ella; cualquier perfil con sesión puede leerlas todas, incluidos los registros.
Sale: nada guardado.
Si falla: «No se pudieron cargar los archivos» con el motivo («Esta carpeta es de una app que no permite cambiar sus archivos.», el de erplora.com sin contestar o, si no llegó a salir, «Comprueba la conexión y vuelve a intentarlo.») y «Reintentar»; el gestor queda vacío sin inventar datos.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F245 (ver y descargar archivos)
Pendiente de enlazar: whatsapp_inbox — WHATSAPP_INBOX-F06 (los adjuntos recibidos se guardan en la carpeta de la app)
QA: ninguno

### HUB_SHELL-F131 Subir archivos y crear carpetas
Estado: hecho
Actor: administrador
Pantalla: Archivos
Pasos:
1. El administrador, dentro de una carpeta que lo permite, pulsa «Subir archivo» o arrastra archivos al gestor (se pueden varios).
2. Sale «Archivos subidos.» y la lista se recarga.
3. Para una carpeta nueva pulsa «Nueva carpeta», escribe el «Nombre de la carpeta» (hasta 100 caracteres) y «Crear carpeta». Sale «Carpeta creada.».
4. Quien no administra no ve el botón de subir; si intenta crear, renombrar, mover o borrar: «Solo un administrador puede modificar los archivos.».
Entra: los archivos o el nombre; la carpeta abierta.
Sale: pide al servidor guardar en el almacenamiento (HUB-F246); crear una carpeta cuenta como subir.
Si falla: «No se pudieron subir los archivos.» o la causa: «No se ha elegido ningún archivo para subir.», «Ahora mismo se están procesando demasiados archivos. Inténtalo de nuevo en un momento.», «Esta carpeta es de una app que no permite cambiar sus archivos.», «Ese nombre no es válido. Usa un nombre sin barras ni puntos sueltos.»; «No se pudo crear la carpeta.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F246 (subir, organizar y borrar archivos)
QA: ninguno

### HUB_SHELL-F132 Previsualizar y descargar un archivo
Estado: hecho
Actor: administrador, responsable, empleado, cajero
Pantalla: Archivos
Pasos:
1. La persona pulsa «Abrir» en un archivo. Se abre un visor grande dentro del hub, con el nombre como título, «Descargar» y «Cerrar» (y «Ampliar»/«Reducir» donde se puede).
2. El visor entiende imágenes, PDF (dibujado en pantalla; si es muy largo, «Mostrando las primeras {shown} de {total} páginas. Descarga el archivo para leerlo entero.»), hojas de cálculo (xlsx, xlsm, csv, tsv), Word moderno (docx), texto, registros y código, JSON plegable, vídeo y audio.
3. Para cualquier otro tipo (por ejemplo `.xls` o `.doc` antiguos) sale «Sin vista previa»: «Este tipo de archivo no se puede mostrar aquí. Descárgalo para abrirlo con una aplicación de tu dispositivo.».
4. «Descargar» (en el visor o en la fila) guarda el archivo; sale «Guardado en {path}» si la app dice dónde.
Entra: los bytes del archivo, que pide el hub al almacenamiento; el navegador nunca toca el almacenamiento.
Sale: nada guardado. Abrir un `.log` no descarga el lector de PDF.
Si falla: «No se pudo abrir el archivo»: «No llegó el contenido del archivo. Revisa la conexión e inténtalo de nuevo.»; «Ese archivo es demasiado grande para abrirlo aquí. Descárgalo.»; si la app instalada no puede guardar archivos (por ejemplo en una tableta), una frase propia que lo dice.
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F245 (ver y descargar archivos)
QA: ninguno

### HUB_SHELL-F133 Mover y renombrar un archivo o una carpeta
Estado: hecho
Actor: administrador
Pantalla: Archivos
Pasos:
1. Para mover, el administrador arrastra el archivo o la carpeta a otra carpeta del árbol, o elige «Mover a…». Sale «Movido a «{folder}».» (si va a la raíz, «Movido a «Archivos».»).
2. Para renombrar, elige «Renombrar» (o «Renombrar carpeta»): un diálogo con el nombre actual ya escrito (hasta 255 caracteres). Confirma y sale «Renombrado.».
3. Si renombra o mueve la carpeta en la que está, la pantalla sigue a su nueva ruta o sube a la de arriba.
4. Las carpetas de solo lectura no se pueden arrastrar, renombrar ni recibir archivos.
Entra: el origen y el destino, o el nombre nuevo.
Sale: pide al servidor el cambio (HUB-F246). Mover exige poder borrar en el origen y subir en el destino.
Si falla: «No se pudo mover. Puede que la carpeta de destino sea de solo lectura.» / «No se pudo renombrar. Puede que esta carpeta sea de solo lectura.» o la causa exacta: «El archivo ya está en esa carpeta.», «Una carpeta no se puede mover dentro de sí misma.», «Ese nombre no es válido. Usa un nombre sin barras ni puntos sueltos.», «Esta carpeta es de una app que no permite cambiar sus archivos.».
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F246 (subir, organizar y borrar archivos)
QA: ninguno

### HUB_SHELL-F134 Borrar un archivo o una carpeta
Estado: hecho
Actor: administrador
Pantalla: Archivos
Pasos:
1. El administrador elige «Eliminar» en un archivo (o «Eliminar carpeta»).
2. La pantalla pregunta: «Eliminar archivo»: «Vas a eliminar «{name}». Esta acción no se puede deshacer.»; o «Eliminar carpeta»: «Vas a eliminar «{name}» y todo su contenido. Esto no se puede deshacer.».
3. Confirma con «Eliminar». Sale «Archivo eliminado.» y la lista se recarga. Si borró la carpeta en la que estaba, sube a la de arriba.
Entra: la ruta.
Sale: pide al servidor el borrado (HUB-F246); no hay papelera. Las carpetas de las apps que no lo permiten no se pueden vaciar.
Si falla: «No se pudo eliminar el archivo.» o la causa (carpeta de solo lectura, sesión caducada: «Tu sesión ha caducado. Vuelve a entrar e inténtalo otra vez.», o «Ese archivo o carpeta ya no existe. Actualiza la lista.»).
Implicados: pendiente
Pendiente de enlazar: hub — HUB-F246 (subir, organizar y borrar archivos)
QA: ninguno
