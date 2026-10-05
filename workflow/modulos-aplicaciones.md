# WORKFLOW — Hub (servidor) · Módulos: aplicaciones, ajustes y puesta en marcha

Prefijo: HUB

> Lo que hace el servidor del hub con las **aplicaciones** (módulos) del negocio: instalarlas,
> validarlas, migrar sus tablas, sembrar sus datos de partida, actualizarlas, reponerlas al arrancar,
> encenderlas, apagarlas y quitarlas; servir sus pantallas y sus ficheros; concederles permisos de
> host; leer y guardar sus ajustes; servir los datos de sus paneles de Inicio; y calcular la lista de
> puesta en marcha. Las pantallas (Apps, la vista de un módulo, Inicio, Ajustes › Permisos) son de
> `HUB_SHELL`; aquí se escribe la mitad del servidor. Las consultas y órdenes de un módulo ya
> instalado están en [modulos.md](modulos.md).

## Flujos

### HUB-F19 Instalar una aplicación del catálogo
Estado: parcial — mientras dura la instalación (descarga incluida) el hub retiene todas las consultas y órdenes, también las de la caja, hasta que termina o el catálogo deja de contestar (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: HUB_SHELL: Apps
Pasos:
1. En **Apps**, un administrador pulsa «Instalar» en una app del catálogo (con la versión de fábrica o una elegida).
2. El hub pide a ERPlora el plan de instalación: la app y las dependencias que le faltan, en orden, con su versión y su huella.
3. Si alguna dependencia es de pago y el negocio no la tiene contratada, no instala nada y devuelve qué falta y dónde contratarlo; nunca cobra por su cuenta.
4. Por cada app del plan, y avisando en vivo de cada fase («resolving», «downloading», «verifying», «installing»): descarga el paquete, comprueba su huella SHA-256 (obligatoria) y su firma según la política del despliegue, lo descomprime sin dejar que un fichero se salga de su carpeta, lo valida (HUB-F20), migra sus tablas (HUB-F21), siembra sus datos de partida (HUB-F22), registra sus consultas, órdenes, menú, traducciones, recetas de automatización, puntos de reglas y tareas programadas, y la deja **activa**.
5. Guarda una copia del paquete en la base del propio hub, avisa a ERPlora de que está instalada e indexa sus textos para el asistente.
6. Las pantallas reciben `module.installed` y refrescan el menú; la respuesta dice qué dependencias se instalaron de paso.
Entra: `POST /api/modules/request-install` con sesión de administrador y la credencial de máquina del hub; el catálogo y los paquetes de ERPlora. También instalan por aquí la importación de una plantilla (Ajustes › Datos) y la reposición del arranque (HUB-F25).
Sale: la fila de la app en `hub_module` (activa), sus tablas y datos de partida, su copia (`hub_module_package`), sus tareas programadas, sus recetas de automatización disponibles y el aviso en vivo. Una app ya instalada no se reinstala: contesta con la que hay.
Si falla: dependencia de pago sin contratar, `install_blocked` (409) con lo que hay que comprar; versión inexistente o app fuera del catálogo del hub, 404; firma rechazada, `install_bad_signature` (403); un paquete que no pasa la validación o una migración que falla, `install_runtime_failed` (422) y el hub queda como estaba; la app necesita un hub más nuevo, `core_version_too_old` (422): «Esta app necesita un hub más nuevo: actualiza el hub e inténtalo de nuevo.»; ERPlora no contesta a tiempo, «ERPlora no ha contestado a tiempo, así que la app no se ha instalado. Inténtalo en unos minutos.» (424). Ningún fallo sale como 5xx. Fallar al guardar la copia, al avisar a ERPlora o al indexar no deshace la instalación.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Apps: el botón «Instalar», el consentimiento de permisos y las fases en vivo
Pendiente de enlazar: hub — HUB, negocio y datos: importar una plantilla instala sus apps por esta puerta
Pendiente de enlazar: hub — HUB, automatizaciones: las recetas de fábrica que la app publica al registrarse
Pendiente de enlazar: hub — HUB, avisos: las tareas programadas que la app declara
Pendiente de enlazar: saas — marketplace: el plan de instalación, las versiones, la descarga y el registro de la instalación
QA: BD-03

### HUB-F20 Rechazar un paquete que rompe las reglas del hub
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Antes de tocar nada, el hub lee el `module.json` del paquete: rechaza lo que no entiende y cambia lo que se ejecuta, y anota como aviso lo que solo cuesta una pantalla o un botón.
2. Comprueba que el SQL de sus órdenes y de su semilla solo escriba en tablas propias, que sus códigos de error sean de su espacio, que cada aviso que escucha lo atienda una orden suya, que sus roles no redefinan uno del hub ni concedan administración, que su régimen fiscal esté bien declarado y que, si cumple el régimen fiscal de este negocio, sea gratis.
3. Rechaza un módulo que se llame `hub` (espacio reservado), que necesite un hub más nuevo o cuyas dependencias no estén instaladas o sean más viejas que el mínimo que declara.
4. Compila los esquemas de sus consultas y órdenes; uno que no compila aborta la instalación.
Entra: el paquete ya descargado y verificado.
Sale: nada si se rechaza; si pasa, sigue la instalación. Los avisos del manifiesto quedan en el registro y en la lista de apps (`manifest_warnings`).
Si falla: el motivo con su código estable (`role_grants_admin`, `fiscal.provider_not_free`, `missing_dependency`, `dependency_too_old`, `core_version_too_old`…); si era una actualización, la versión anterior sigue funcionando.
Implicados: ninguno
QA: ninguno

### HUB-F21 Aplicar las migraciones de un módulo con su guarda
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al instalar, actualizar o volver a registrar un módulo, el hub junta las migraciones que declara el manifiesto con las que trae el paquete, ordenadas por nombre, y aplica solo las que este hub aún no tiene.
2. Antes de aplicar cada una, la guarda comprueba que solo toque tablas del módulo (su prefijo, nunca `hub_*` ni `_*`), que su SQL haga lo que dice su tipo (añadir, rellenar datos o retirar) y que no tenga bloques que no se puedan leer.
3. En una migración de retirada, cada `DROP` se convierte en un cambio de nombre a `_deprecated_…`: los datos siguen ahí y volver atrás es renombrar. Borrar filas en ella se rechaza.
4. Anota cada migración aplicada; las ya aplicadas no se repiten nunca.
Entra: `migrations/postgres/*.sql` del paquete y su tipo declarado (`expand` si no dice nada).
Sale: las tablas del módulo; el registro `_hub_migrations`. Las migraciones solo van hacia delante: no hay vuelta atrás.
Si falla: `hub.module_migration_rejected` con el fichero y el motivo; las que ya entraron se quedan y la que falló se reintenta en el siguiente intento. Una migración que no está en el manifiesto pero viaja en el paquete se aplica igual, con un aviso en el registro.
Implicados: ninguno
QA: ninguno

### HUB-F22 Sembrar los datos de partida de un módulo
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Tras migrar, el hub ejecuta la semilla que declara el módulo (unidades, categorías fiscales, la semana de horario por defecto…), con el negocio y la hora, y firmada por «system».
2. La semilla es del propio módulo y la hace repetible su SQL (`WHERE NOT EXISTS`): corre al instalar, en cada actualización y en cada arranque que vuelve a registrar el módulo, sin duplicar.
3. El hub aprende de esa misma guarda qué fila considera «la misma» el módulo, y qué tablas siembra enteras como marcador de posición, para que una plantilla importada no las duplique y sustituya la semana genérica por la suya.
4. Para Impuestos en un negocio de España, añade además los tipos de IVA que faltan.
Entra: `seed.postgres` del manifiesto.
Sale: las filas de partida del módulo, firmadas por «system».
Si falla: un error en la semilla aborta la instalación o la actualización (la versión anterior sigue); el SQL de la semilla solo puede escribir en tablas del módulo (HUB-F20).
Implicados: pendiente
Pendiente de enlazar: schedules — SCHEDULES-F12 (partir de una semana por defecto al instalar y al actualizar)
Pendiente de enlazar: hub — HUB, negocio y datos: importar una plantilla sin duplicar lo que sembró el módulo
QA: BD-01

### HUB-F23 Actualizar una aplicación
Estado: parcial — por la API, con una versión explícita, se puede bajar de versión (la pantalla solo ofrece hacia delante); y si fallan la nueva y la vuelta atrás, la respuesta nombra la versión en lugar de la app (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: HUB_SHELL: Apps
Pasos:
1. En **Apps**, un administrador pulsa «Actualizar» en una app instalada (o elige una versión de la lista, HUB-F24).
2. El hub decide la versión: la más nueva publicada que no esté en cuarentena, nunca hacia atrás, y la que fije soporte si hay un pin.
3. Si ya está en esa versión, contesta sin hacer nada.
4. Si no, la instala por el mismo camino que HUB-F19 (huella, firma, validación, migraciones, semilla), con las mismas fases en vivo.
5. Si la nueva falla, vuelve a poner la que tenía: el hub sigue con ella y lo dice.
6. Anota el cambio en el historial de actualizaciones, reindexa sus textos para el asistente y avisa `module.updated` y `module.installed`.
Entra: `POST /api/modules/:id/update` con sesión de administrador y credencial de máquina; versión opcional.
Sale: la app en la versión nueva (o en la de antes), la línea del historial y los avisos en vivo.
Si falla: app no instalada, `update_not_installed` (404); dependencia de pago, `install_blocked` (409); la nueva falla y vuelve la anterior: respuesta correcta con el aviso `module.update_failed_kept_previous`; fallan las dos: `module.update_lost` (424) y la pantalla dice «La actualización ha fallado y no se ha podido recuperar la versión anterior, así que esta app ya no está instalada. Vuelve a instalarla desde Apps; si también falla, avisa a soporte.». Las migraciones que la versión nueva ya aplicó se quedan.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Apps: el botón «Actualizar» y el desplegable de versión
Pendiente de enlazar: hub — HUB, acceso: el historial de actualizaciones que se ve en Sistema
QA: BD-03

### HUB-F24 Consultar qué actualizaciones y versiones hay
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: HUB_SHELL: Apps
Pasos:
1. Al abrir **Apps** (o al empezar una sesión de administrador, para la campana), la pantalla pregunta qué ofrece hoy el catálogo para cada app activa.
2. El hub pregunta a ERPlora app por app y responde con la instalada, la que se ofrecería con el mismo criterio que la actualización automática, si hace falta un hub más nuevo para ella y si de verdad pudo preguntar.
3. Para elegir versión, un administrador pide la lista de una app: solo versiones hacia delante, ninguna en cuarentena, ninguna si soporte la fijó.
Entra: `GET /api/modules/updates` (cualquier sesión) y `GET /api/modules/:id/versions` (sesión de administrador).
Sale: nada guardado.
Si falla: sin credencial de máquina o con ERPlora sin contestar, cada app sale como «no lo sé» (`checked: false`), nunca como «al día»; la lista de versiones sale vacía.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Apps y campana: el aviso de actualizaciones disponibles
QA: BD-03

### HUB-F25 Reponer las aplicaciones al arrancar y actualizarlas solas
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al arrancar, el hub vuelve a registrar cada app que su base dice instalada, desde la carpeta de descargas, respetando las que el administrador había apagado.
2. Si una no está en la carpeta (en la nube la carpeta se vacía en cada despliegue), la vuelve a descargar del catálogo, y en ese momento elige la última versión instalable: así las apps se actualizan solas. Si la nueva falla, vuelve a la que tenía y lo avisa.
3. Si el catálogo no contesta, la repone de la copia guardada en la propia base, con las mismas comprobaciones de huella y firma.
4. Lo que no se pueda reponer por ninguna vía se denuncia y deja la comprobación de salud del hub en rojo, para que el despliegue no se dé por bueno.
Entra: `hub_module`, la carpeta de descargas, el catálogo y `hub_module_package`.
Sale: el hub sirviendo las mismas apps (o versiones más nuevas), las líneas del historial de actualizaciones y, si falta alguna, el aviso de arranque incompleto.
Si falla: un hub sin credencial de máquina no puede volver a descargar y depende de la copia local; una app instalada antes de que existiera la copia y sin catálogo queda fuera y la salud del hub lo dice.
Implicados: pendiente
Pendiente de enlazar: hub — HUB, acceso: la comprobación de salud que exige todas las apps registradas y el historial de actualizaciones
QA: ninguno

### HUB-F26 Seguir lo que otra copia del hub instaló, actualizó, apagó o quitó
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Durante un despliegue conviven dos copias del mismo hub contra la misma base; cada 15 segundos (ajustable) cada una compara lo que tiene registrado con lo que dice la base.
2. Una app instalada o actualizada por la otra copia se carga exactamente en la versión anotada: de su carpeta, de la copia guardada o, si no hay, del catálogo.
3. Una app quitada por la otra se olvida; una apagada o encendida por la otra cambia aquí también.
4. Las pantallas conectadas a esta copia reciben el aviso en vivo correspondiente.
Entra: `hub_module` y `HUB_MODULE_RECONCILE_SECS`.
Sale: el registro de esta copia igual que la base.
Si falla: una versión que no se puede cargar no se reintenta hasta que la base anote otra; la app sigue con lo que tenía.
Implicados: ninguno
QA: ninguno

### HUB-F27 Activar una aplicación
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Apps
Pasos:
1. Un administrador enciende una app apagada.
2. El hub la enciende junto con todas las apps de las que depende.
3. Después vuelve a encender sola cada app que se había apagado arrastrada por otra, en cuanto sus dependencias vuelven a estar activas; las que apagó una persona siguen apagadas.
4. Las pantallas reciben `module.activated`.
Entra: `POST /api/modules/:id/activate` con sesión de administrador.
Sale: el estado en `hub_module`.
Si falla: app no instalada, error; sin sesión de administrador, 401.
Implicados: ninguno
QA: ninguno

### HUB-F28 Desactivar una aplicación preguntando antes si puede irse
Estado: parcial — la negativa de un módulo sale con la frase de su motor, que hoy está en inglés en la pantalla española
Actor: administrador
Pantalla: HUB_SHELL: Apps
Pasos:
1. Un administrador apaga una app.
2. El hub calcula todo lo que caería con ella: la app y cada app activa que depende de ella, en cadena.
3. Si el negocio ya factura en producción y ese conjunto se lleva al último módulo que cumple su régimen fiscal, lo niega.
4. Pregunta al motor de cada app del conjunto si aún debe algo a una autoridad (VeriFactu: registros sin aceptar por la AEAT); si alguna debe, no apaga ninguna.
5. Si puede, apaga la pedida (queda apagada hasta que alguien la encienda) y las arrastradas (vuelven solas, HUB-F27). Las pantallas reciben `module.deactivated`.
Entra: `POST /api/modules/:id/deactivate` con sesión de administrador.
Sale: el estado en `hub_module`. Una app apagada no sirve consultas ni órdenes (`module_inactive`) ni aporta menú, paneles ni pasos de puesta en marcha.
Si falla: el código del módulo con su recuento (409) o el candado fiscal del hub; nada cambia. Al arrancar, volver a apagar lo que ya estaba apagado no pasa por estas preguntas.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F32 (impedir apagar o desinstalar con registros sin enviar)
Pendiente de enlazar: hub — HUB, perfil fiscal: el candado del proveedor fiscal en producción
QA: L-14

### HUB-F29 Desinstalar una aplicación
Estado: parcial — forzar la desinstalación de una app de la que dependen otras deja esas otras activas sin ella (qué pasa en el siguiente arranque, sin confirmar); y la negativa de un módulo sale en inglés como en HUB-F28
Actor: administrador
Pantalla: HUB_SHELL: Apps
Pasos:
1. Un administrador pide desinstalar una app.
2. El hub aplica, por este orden, el candado del proveedor fiscal, la pregunta al motor de la app (HUB-F28) y, salvo que se pida forzar, la comprobación de dependientes: si otras apps instaladas la necesitan, apagadas o no, lo niega y las nombra.
3. Si se confirma «quitarla igualmente», solo se salta la comprobación de dependientes; los candados fiscales siguen.
4. Quita sus consultas, órdenes, menú y tareas programadas, olvida los roles que solo ella declaraba (las personas conservan su rol), borra su fila y su copia guardada, y quita sus textos del índice del asistente.
5. Las pantallas reciben `module.uninstalled`.
Entra: `POST /api/modules/:id/uninstall` con sesión de administrador y, opcionalmente, `{"force": true}`.
Sale: la app fuera del hub. **Sus tablas y sus datos se quedan** en la base.
Si falla: dependientes, `has_dependents` (409) con la lista en `dependents`; motor con trabajo pendiente o último proveedor fiscal, su código (409); nada cambia.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F32 (impedir apagar o desinstalar con registros sin enviar)
Pendiente de enlazar: hub — HUB_SHELL, Apps: el aviso que nombra lo que se rompe y ofrece quitarla igualmente
QA: L-14

### HUB-F30 Instalar un módulo desde una carpeta en modo desarrollo
Estado: hecho
Actor: administrador
Pantalla: ninguna
Pasos:
1. Solo con el hub en modo desarrollo (`HUB_DEV_MODE`), un administrador pide instalar un módulo ya descomprimido en una carpeta de pruebas, o el hub instala al arrancar todos los de `HUB_MODULES_DIR` en orden de dependencias.
2. El hub lo valida, migra y registra como cualquier otro, sin pasar por el catálogo ni la firma.
Entra: `POST /api/modules/install {dir}`.
Sale: el módulo instalado y activo; los que fallan al arrancar se anotan y la salud del hub lo dice.
Si falla: fuera de modo desarrollo o fuera de la carpeta de pruebas, 403; carpeta inexistente, 422. En producción `HUB_MODULES_DIR` se ignora y se dice en el registro.
Implicados: ninguno
QA: ninguno

### HUB-F31 Servir el menú, las pantallas y los ficheros de las aplicaciones
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: HUB_SHELL: menú lateral
Pasos:
1. Al entrar, la pantalla pide el menú: el hub devuelve las pestañas de las apps activas, con su nombre en el idioma pedido y la versión instalada, y quita las que piden un permiso que la persona no tiene.
2. También dice cuántas apps activas hay, para que un menú vacío no se confunda con un hub sin apps.
3. La pantalla carga el código y el `module.json` de cada app por una dirección con la versión dentro, que se puede guardar para siempre; la dirección sin versión se revalida siempre.
4. La lista de apps instaladas lleva estado, dependencias, si publica API y los avisos de su manifiesto.
Entra: `GET /api/navigation`, `GET /api/modules` (con sesión) y `/modules/:id/v/:versión/…` (sin sesión).
Sale: nada guardado.
Si falla: una app no instalada o un fichero que no existe, 404 (nunca la página del hub disfrazada de código). Una pestaña sin permiso declarado se enseña a todos; detrás, cada consulta y orden vuelve a comprobar el permiso.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, menú lateral y vista de un módulo
QA: BD-03

### HUB-F32 Conceder o retirar un permiso de host a una aplicación
Estado: hecho
Actor: administrador
Pantalla: HUB_SHELL: Ajustes › Permisos
Pasos:
1. Una app declara qué necesita del hub (red, certificado, impresora, avisar a clientes, administrar automatizaciones); al instalarla no tiene ninguno concedido.
2. Un administrador, en **Ajustes › Permisos**, concede o retira cada uno.
3. El hub solo acepta permisos que existen y que esa app declara, y anota quién y cuándo.
4. Al conceder, vuelve a poner en la cola los avisos que esa app no pudo atender por faltarle el permiso.
Entra: `GET /api/modules/:id/capabilities` (cualquier sesión) y `PUT` del mismo con sesión de administrador.
Sale: `_module_capability_grants`. Sin el permiso, el motor propio de la app no corre (HUB-F12), sus recordatorios no salen y su paso de puesta en marcha sigue pendiente (HUB-F35). Una copia de seguridad del mismo hub los vuelve a conceder al restaurarse; una plantilla, no.
Si falla: un permiso desconocido o no declarado, error; si los avisos no se pueden volver a encolar, se quedan en avisos caídos y se dice en el registro.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Ajustes › Permisos
Pendiente de enlazar: hub — HUB, avisos: reintentar los avisos rechazados por falta de permiso
QA: BD-03

### HUB-F33 Leer y guardar los ajustes de un módulo
Estado: parcial — la pantalla solo deja guardar al administrador, mientras el servidor acepta a quien tenga el permiso de la orden de guardar (el responsable lo tiene en varios módulos y lo hace por el asistente)
Actor: administrador, responsable, asistente
Pantalla: HUB_SHELL: vista de un módulo › Ajustes
Pasos:
1. Si el módulo declara un bloque de ajustes, la pantalla le añade la pestaña «Ajustes»: pinta un formulario a partir del esquema del módulo (o el componente propio que el módulo indique).
2. Para cargarlo, ejecuta la consulta de lectura del módulo, con su permiso.
3. Al pulsar «Guardar», manda todos los valores a la orden de guardar del módulo, que pasa por el embudo de siempre (HUB-F03): su permiso, su esquema con sus valores por defecto y su comprobación de filas.
4. La pantalla dice «Ajustes guardados.».
Entra: el bloque `settings` del `module.json` (esquema, consulta, orden).
Sale: la fila de ajustes del módulo y el aviso que su orden emita.
Si falla: «No se pudieron cargar los ajustes.» o «No se pudieron guardar los ajustes.»; un campo rechazado por el esquema vuelve señalado («Revisa los campos marcados y vuelve a guardar.»). Quien no es administrador ve «Solo un administrador puede cambiar estos ajustes.» y no tiene «Guardar»; por el asistente o la API guarda igualmente si tiene el permiso.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, vista de un módulo: la pestaña «Ajustes» generada desde el bloque de ajustes
Pendiente de enlazar: cash_register — CASH_REGISTER-F01 (configurar cómo funciona la caja)
Pendiente de enlazar: sales — SALES-F34 (ajustar el TPV)
Pendiente de enlazar: kitchen — KITCHEN-F26 (ajustar la pantalla de cocina)
Pendiente de enlazar: inventory — INVENTORY-F19 (ajustar el inventario)
QA: qa-hub-restaurant §7.03 (discrepa)

### HUB-F34 Servir los datos de los paneles de Inicio
Estado: hecho
Actor: empleado, responsable, administrador
Pantalla: HUB_SHELL: Inicio
Pasos:
1. Cada app declara sus paneles de Inicio en su `module.json`: título, tamaño, a qué negocios aplica, si salen de fábrica, qué permiso piden, qué consulta los alimenta y con qué avisos se refrescan.
2. La pantalla lee esos manifiestos y pide al hub, por la puerta de consultas normal, la consulta de cada panel visible.
3. El hub la ejecuta con el permiso de quien mira, como cualquier consulta (HUB-F01).
4. Cuando el hub emite en vivo uno de los avisos que el panel declara, la pantalla vuelve a pedirla.
Entra: el bloque `widgets` de cada `module.json`; la sesión de quien mira.
Sale: nada guardado; los datos del panel. El hub no pinta paneles ni decide cuáles se ven: solo sirve el manifiesto, la consulta y los avisos en vivo.
Si falla: un panel cuya consulta exige un permiso que la persona no tiene recibe `permission_denied`; un panel de una app apagada o fuera del plan no tiene datos. Un panel no se refresca con un aviso que su app no declara (por ejemplo, el stock tras una venta, INVENTORY-F17).
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Inicio: el tablero de paneles, su selección y su refresco
Pendiente de enlazar: hub — HUB, avisos: el canal en vivo que dispara el refresco
Pendiente de enlazar: cash_register — CASH_REGISTER-F12 (ver la caja en los paneles del inicio)
Pendiente de enlazar: inventory — INVENTORY-F17 (ver el panel y los productos con stock bajo)
Pendiente de enlazar: verifactu — VERIFACTU-F31 (vigilar los envíos desde el panel y los eventos)
QA: R-01, qa-hub-restaurant §7.12

### HUB-F35 Calcular la lista de puesta en marcha
Estado: hecho
Actor: sistema
Pantalla: HUB_SHELL: Inicio
Pasos:
1. Cuando la pantalla o el asistente piden la lista («Termina de configurar tu negocio»), el hub la calcula en ese momento: nadie marca un paso a mano.
2. Pone sus cuatro pasos propios, por este orden: «Tus apps» (hecho con una app activa), los datos del negocio (hecho con razón social y NIF válidos), la impresora (hecho con un dispositivo dado de alta para imprimir tiques) y el equipo (hecho con más de una persona activa).
3. Añade un paso por cada app activa, incluida en el plan y aplicable al país del negocio que lo declare: ejecuta su consulta con la sesión de quien pregunta y lo da por hecho si la primera fila cumple todas sus condiciones y la app tiene concedidos los permisos de host que pide; si le falta un permiso, el paso lleva a Ajustes › Permisos.
4. Gradúa cada paso: ⛔ legal solo para lo que el hub de verdad rechazaría al facturar (los datos del negocio y, en producción sin vía hasta la AEAT, el paso de la app que pide el certificado); 🔴 o 🟡 según diga el módulo.
5. A cada persona solo le enseña los pasos que puede hacer, salvo un ⛔ pendiente, que ve todo el mundo; devuelve los pasos ordenados, los recuentos y si los datos los trajo una plantilla.
Entra: `hub.setup.status` (consulta del hub, con sesión); el bloque `setup` de cada `module.json`; lo último que dijo el catálogo (una hora de validez).
Sale: `{items, pending, unavailable, blocking_pending, total}`; nada guardado salvo la última respuesta del catálogo.
Si falla: un paso cuya comprobación no se puede hacer (sin permiso para la consulta, una lectura rota) no sale, en vez de salir pendiente. «Tus apps» sale como no disponible si el catálogo dijo hace menos de una hora que no hay nada instalable.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Inicio: la tarjeta «Termina de configurar tu negocio», la franja de bloqueo y el asistente que la leen
Pendiente de enlazar: inventory — INVENTORY-F28 (completar el primer paso «Tu catálogo»)
Pendiente de enlazar: schedules — SCHEDULES-F03 (confirmar la semana por defecto)
Pendiente de enlazar: tables — TABLES-F02 (el paso «Tus mesas» queda hecho con una mesa en uso)
Pendiente de enlazar: invoice — INVOICE-F14 (preparar la numeración desde la tarea de Inicio)
Pendiente de enlazar: cash_register — CASH_REGISTER-F01 (los primeros pasos de Caja)
QA: BD-01, BD-02
