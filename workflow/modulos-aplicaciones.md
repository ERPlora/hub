# WORKFLOW — Hub (servidor) · Módulos: aplicaciones, ajustes y puesta en marcha

Prefijo: HUB

> Lo que hace el servidor del hub con las **aplicaciones** (módulos) del negocio: instalarlas,
> validarlas, migrar sus tablas, sembrar sus datos de partida, actualizarlas, reponerlas al arrancar,
> encenderlas, apagarlas y quitarlas; servir sus pantallas y sus ficheros; concederles permisos de
> host; leer y guardar sus ajustes; servir los datos de sus paneles de Inicio; y calcular la lista de
> puesta en marcha. Las pantallas (Apps, la vista de un módulo, Inicio, Ajustes › Permisos) son de
> `HUB_SHELL`; aquí se escribe la mitad del servidor. Las consultas y órdenes de un módulo ya
> instalado están en [modulos.md](modulos.md).

## Antes de empezar

- Las apps se instalan desde **Apps** (HUB-F19) o importando la plantilla del sector en
  Ajustes › Datos y copias, que instala las suyas por la misma puerta.
- Si una app pide permisos de host (red, certificado, impresora, avisar, administrar
  automatizaciones), concédelos al instalarla (el diálogo de Apps los concede justo después, por la
  puerta de HUB-F32) o en **Ajustes › Permisos** (HUB-F32); sin ellos su motor no corre y su paso de
  puesta en marcha sigue pendiente.
- Recorre la lista «Termina de configurar tu negocio» de Inicio (HUB-F35): datos del negocio,
  impresora, equipo y los pasos de cada app.
- Cada app con ajustes tiene su pestaña «Ajustes» (HUB-F33); algunas, como Caja, solo empiezan a
  aplicar sus reglas cuando se guardan por primera vez.

## Flujos

### HUB-F19 Instalar una aplicación del catálogo
Estado: parcial — mientras se instala una app (descarga, firma, migraciones, semilla y aviso a ERPlora incluidos) el hub no atiende ninguna petición —ni la caja, ni el menú, ni la comprobación de salud—, sin tope total de tiempo; un fallo a mitad deja migraciones, semilla y dependencias aplicadas (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: HUB_SHELL: Apps
Pasos:
1. En **Apps**, un administrador pulsa «Instalar» en una app del catálogo (con la versión de fábrica o una elegida).
2. El hub pide a ERPlora el plan de instalación: la app y las dependencias que le faltan, en orden, con su versión y su huella.
3. Si alguna dependencia es de pago y el negocio no la tiene contratada, no instala nada y devuelve qué falta y dónde contratarlo; nunca cobra por su cuenta.
4. Por cada app del plan, y avisando en vivo de cada fase («resolving», «downloading», «verifying», «installing»): descarga el paquete, comprueba su huella SHA-256 (obligatoria) y su firma según la política del despliegue, lo descomprime sin dejar que un fichero se salga de su carpeta, lo valida (HUB-F20), migra sus tablas (HUB-F21), siembra sus datos de partida (HUB-F22), registra sus consultas, órdenes, menú, traducciones, recetas de automatización, puntos de reglas y tareas programadas, y la deja **activa**.
5. Guarda una copia del paquete en la base del propio hub, avisa a ERPlora de que está instalada e indexa sus textos para el asistente.
6. Las pantallas reciben `module.installed` y refrescan el menú; la respuesta dice qué dependencias se instalaron de paso.
Entra: `POST /api/modules/request-install` con sesión de administrador y la credencial de máquina del hub; el catálogo y los paquetes de ERPlora. También instalan por aquí la importación de una plantilla (Ajustes › Datos y copias) y la reposición del arranque (HUB-F25).
Sale: la fila de la app en `hub_module` (activa), sus tablas y datos de partida, su copia (`hub_module_package`), sus tareas programadas, sus recetas de automatización disponibles y el aviso en vivo. Durante todo el proceso el hub mantiene su candado de escritura: cada petición (consultas, órdenes, menú, autenticación, `/readyz`) espera; cada espera de red tiene un tope de 30 s sin recibir nada, pero una descarga lenta que sigue enviando retiene el hub sin límite. Con el plan de ERPlora, una app ya instalada no se reinstala y una dependencia de pago para todo; si el plan no llega y se resuelve por el manifiesto, esas dos garantías no existen (se reinstala, actualiza o baja lo ya instalado, `install.rs:1504-1581`).
Si falla: dependencia de pago sin contratar, `install_blocked` (409) con lo que hay que comprar; versión inexistente o app fuera del catálogo del hub, 404; firma rechazada, `install_bad_signature` (403); un paquete que no pasa la validación o una migración que falla, `install_runtime_failed` (422) —el motivo concreto se pierde en el código—, y lo que ya se aplicó (migraciones, filas de semilla, dependencias instaladas de paso, declaración del régimen fiscal) se queda; la app necesita un hub más nuevo, `core_version_too_old` (422): «Esta app necesita un hub más nuevo: actualiza el hub e inténtalo de nuevo.»; ERPlora no contesta a tiempo, «ERPlora no ha contestado a tiempo, así que la app no se ha instalado. Inténtalo en unos minutos.» (424). El sobre de error es `{ok: false, error: "<frase>", code}`, con el código en la raíz. Sin sesión de administrador, 401 (también con sesión que no es de administrador). Ningún fallo de instalación sale como 5xx. Fallar al guardar la copia, al avisar a ERPlora o al indexar no deshace la instalación.
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
1. Antes de migrar, el hub lee el `module.json` del paquete: rechaza lo que no entiende y cambia lo que se ejecuta, y anota como aviso lo que solo cuesta una pantalla o un botón.
2. Comprueba que el SQL de sus órdenes y de su semilla solo escriba en tablas propias, que sus códigos de error sean de su espacio, que cada aviso que escucha lo atienda una orden suya, que sus roles no redefinan uno del hub ni concedan administración, que su régimen fiscal esté bien declarado y que, si cumple el régimen fiscal de este negocio, sea gratis.
3. Rechaza un módulo que se llame `hub` (espacio reservado), que necesite un hub más nuevo o cuyas dependencias no estén instaladas o sean más viejas que el mínimo que declara.
4. Compila los esquemas de sus consultas y órdenes; uno que no compila aborta la instalación, pero esto ocurre **después** de migrar y sembrar.
Entra: el paquete ya descargado y verificado.
Sale: si se rechaza en los pasos 1–3, nada salvo la declaración del régimen fiscal, que se escribe antes de comprobar el nombre `hub` y las dependencias; si se rechaza en el paso 4, quedan las migraciones y la semilla ya aplicadas. Si pasa, sigue la instalación. Los avisos del manifiesto quedan en el registro y en la lista de apps (`manifest_warnings`).
Si falla: por la puerta de desarrollo (HUB-F30), el motivo con su código estable (`role_grants_admin`, `fiscal.provider_not_free`, `missing_dependency`, `dependency_too_old`…); desde el catálogo y al actualizar, todos se aplanan a `install_runtime_failed` salvo `core_version_too_old`. Si era una actualización, el hub sigue sirviendo la versión anterior.
Implicados: ninguno
QA: ninguno

### HUB-F21 Aplicar las migraciones de un módulo con su guarda
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al instalar, actualizar o volver a registrar un módulo, el hub junta las migraciones que declara el manifiesto con las que trae el paquete, ordenadas por nombre, y aplica solo las que este hub aún no tiene.
2. Antes de aplicar cada una, la guarda comprueba que solo toque tablas del módulo (su prefijo, nunca `hub_*` ni `_*`), que su SQL haga lo que dice su tipo (añadir, rellenar datos o retirar) y que no tenga bloques que no se puedan leer.
3. En una migración de retirada, `DROP TABLE` y `DROP COLUMN` se convierten en un cambio de nombre a `_deprecated_…`: los datos siguen ahí y volver atrás es renombrar. `DROP INDEX` y `DROP CONSTRAINT` se ejecutan de verdad. Borrar filas en ella se rechaza, y una retirada que renombra o cambia un tipo exige la línea `-- contract: <versión>`. Nueve ficheros publicados con `DROP` o tablas `_taxes_*` entran tal cual por una lista de excepciones.
4. Anota cada migración aplicada; las ya aplicadas no se repiten nunca.
Entra: `migrations/postgres/*.sql` del paquete y su tipo declarado (`expand` si no dice nada).
Sale: las tablas del módulo; el registro `_hub_migrations`. Las migraciones solo van hacia delante: no hay vuelta atrás.
Si falla: `hub.module_migration_rejected` con el fichero y el motivo (desde el catálogo llega como `install_runtime_failed`); las que ya entraron se quedan —el hub no deshace migraciones— y la que falló se reintenta en el siguiente intento (si una que falla a la mitad se deshace sola depende del adaptador de base de datos, sin confirmar). Una migración que no está en el manifiesto pero viaja en el paquete se aplica igual, con un aviso en el registro.
Implicados: ninguno
QA: ninguno

### HUB-F22 Sembrar los datos de partida de un módulo
Estado: hecho
Actor: sistema
Pantalla: ninguna
Pasos:
1. Tras migrar, el hub ejecuta la semilla que declara el módulo (unidades, categorías fiscales, la semana de horario por defecto…), con el negocio y la hora, y firmada por «system».
2. La semilla es del propio módulo y la hace repetible su SQL (`WHERE NOT EXISTS`): corre cada vez que el módulo se registra —instalar, actualizar, rehidratar al arrancar, re-descargar y reconciliar—. No pisa datos del negocio si el módulo escribe esa guarda; el hub no la impone.
3. El hub aprende de esa misma guarda qué fila considera «la misma» el módulo, y qué tablas siembra enteras como marcador de posición, para que una plantilla importada no las duplique y sustituya la semana genérica por la suya.
4. Para Impuestos en un negocio de España, añade además los tipos de IVA que faltan.
Entra: `seed.postgres` del manifiesto.
Sale: las filas de partida del módulo, firmadas por «system».
Si falla: un error en la semilla aborta la instalación o la actualización (el hub sigue sirviendo la versión anterior), pero las sentencias anteriores de la semilla se quedan: no corre en una transacción. El SQL de la semilla solo puede escribir en tablas del módulo (HUB-F20).
Implicados: pendiente
Pendiente de enlazar: schedules — SCHEDULES-F12 (partir de una semana por defecto al instalar y al actualizar)
Pendiente de enlazar: hub — HUB, negocio y datos: importar una plantilla sin duplicar lo que sembró el módulo
QA: BD-01

### HUB-F23 Actualizar una aplicación
Estado: parcial — un administrador puede, por la API y con una versión explícita, bajar de versión saltándose el pin de soporte (y quizá la cuarentena); actualizar paraliza el hub entero como instalar (HUB-F19); un fallo deja migraciones, semilla y dependencias de la versión nueva; actualizar una app apagada la enciende (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: HUB_SHELL: Apps
Pasos:
1. En **Apps**, un administrador pulsa «Actualizar» en una app instalada (o elige una versión de la lista, HUB-F24).
2. Sin versión, el hub decide: la más nueva publicada que no esté en cuarentena, nunca hacia atrás, y la que fije soporte si hay un pin. Con una versión explícita (la pide el cuerpo de la petición, basta sesión de administrador) se usa tal cual: sin el resolutor, sin pin y, si llega por el plan de ERPlora, quizá sin cuarentena. En la nube el siguiente despliegue la vuelve a subir a la última; en la app instalada se queda.
3. Si ya está en esa versión, contesta sin hacer nada.
4. Si no, la instala por el mismo camino que HUB-F19 (huella, firma, validación, migraciones, semilla), con las mismas fases en vivo.
5. Si la nueva falla, el hub repone en memoria la que tenía y sigue sirviéndola, y lo dice; el segundo intento de la vuelta atrás no reinstala nada. Las migraciones, las filas de semilla y las dependencias que la nueva ya aplicó se quedan. La app queda encendida aunque estuviera apagada.
6. Anota el cambio en el historial de actualizaciones, reindexa sus textos para el asistente y avisa `module.updated` y `module.installed`.
Entra: `POST /api/modules/:id/update` con sesión de administrador y credencial de máquina; versión opcional.
Sale: la app en la versión nueva (o en la de antes), la línea del historial y los avisos en vivo.
Si falla: app no instalada, `update_not_installed` (404); dependencia de pago, `install_blocked` (409); la nueva falla y vuelve la anterior: respuesta correcta con el aviso `module.update_failed_kept_previous`; fallan las dos (en la práctica, solo si alguien quita la app entre los dos intentos): `module.update_lost` (424), con la versión en lugar del nombre de la app en `error`, y la pantalla dice «La actualización ha fallado y no se ha podido recuperar la versión anterior, así que esta app ya no está instalada. Vuelve a instalarla desde Apps; si también falla, avisa a soporte.». Las migraciones que la versión nueva ya aplicó se quedan.
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
Si falla: sin credencial de máquina o con ERPlora sin contestar, cada app sale como «no lo sé» (`checked: false`), nunca como «al día»; la lista de versiones sale vacía. Si falla la lectura de la base, `/api/modules/updates` contesta 500. Solo se consultan las apps activas.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Apps y campana: el aviso de actualizaciones disponibles
QA: BD-03

### HUB-F25 Reponer las aplicaciones al arrancar y actualizarlas solas
Estado: parcial — en la nube cada despliegue vuelve a encender las apps que el administrador había apagado (la re-descarga y la copia local las registran activas); el pin de soporte de una app apagada se ignora; con la carpeta de descargas ya presente, la copia local no vuelve a comprobar huella ni firma
Actor: sistema
Pantalla: ninguna
Pasos:
1. Al arrancar, el hub vuelve a registrar cada app que su base dice instalada desde la carpeta de descargas; solo en este camino vuelve a apagar las que el administrador había apagado a mano (las apagadas en cascada vuelven activas).
2. Cada app que no queda registrada (porque falta `cache/<app>/<versión>/module.json` —en la nube la carpeta se vacía en cada despliegue— o porque su registro falla) la vuelve a descargar del catálogo, y en ese momento elige la última versión instalable: así las apps se actualizan solas, app por app. Con la carpeta presente no se actualiza nada. Si la nueva falla, vuelve a la que tenía y lo avisa. Las apps re-descargadas quedan encendidas, estuvieran como estuvieran.
3. Si el catálogo no contesta, la repone de la copia guardada en la propia base, con las comprobaciones de huella y firma (salvo que su carpeta ya exista, en cuyo caso se usa sin volver a comprobar); también queda encendida.
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
4. Las pantallas conectadas a esta copia reciben el aviso en vivo correspondiente; al recargar una versión distinta sale `module.installed`, nunca `module.updated`, y no se reindexa el asistente.
5. Mientras carga, esta copia mantiene su candado de escritura, descarga del catálogo incluida, y no atiende peticiones (como HUB-F19).
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
3. Después vuelve a encender sola cada app que se había apagado arrastrada por otra, en cuanto sus dependencias vuelven a estar activas. Una dependencia que alguien apagó a mano sí se enciende (paso 2); las demás apps apagadas a mano siguen apagadas.
4. Las pantallas reciben `module.activated`, solo para la app pedida.
Entra: `POST /api/modules/:id/activate` con sesión de administrador.
Sale: el estado en `hub_module`.
Si falla: app no instalada, 404; si falta una dependencia, la respuesta es 404 pero la app pedida ya quedó guardada como activa (defecto). Sin sesión, o con sesión que no es de administrador, 401 (todas las puertas de F19–F30 contestan 401, no 403).
Implicados: ninguno
QA: ninguno

### HUB-F28 Desactivar una aplicación preguntando antes si puede irse
Estado: parcial — la negativa del motor del módulo (`verifactu.unsent_records`) y la del candado fiscal del propio hub (`fiscal.no_provider_left`) salen con su frase en inglés, sin traducción en la pantalla española
Actor: administrador
Pantalla: HUB_SHELL: Apps
Pasos:
1. Un administrador apaga una app.
2. El hub calcula todo lo que caería con ella: la app y cada app activa que depende de ella, en cadena.
3. Si el perfil fiscal del negocio está activo y ese conjunto se lleva al último módulo que cumple su régimen fiscal, lo niega.
4. Pregunta al motor de cada app del conjunto si aún debe algo a una autoridad (VeriFactu: registros sin aceptar por la AEAT); si alguna debe, no apaga ninguna.
5. Si puede, apaga la pedida (queda apagada hasta que alguien la encienda) y las arrastradas (vuelven solas, HUB-F27). Las pantallas reciben `module.deactivated`, solo para la app pedida. En la nube, el siguiente despliegue puede volver a encenderla (HUB-F25).
Entra: `POST /api/modules/:id/deactivate` con sesión de administrador.
Sale: el estado en `hub_module`. Una app apagada no sirve consultas ni órdenes (`module_inactive`) ni aporta menú, paneles ni pasos de puesta en marcha.
Si falla: el código del módulo con su recuento (409) o el candado fiscal del hub; nada cambia. Al arrancar, volver a apagar lo que ya estaba apagado no pasa por estas preguntas.
Implicados: pendiente
Pendiente de enlazar: verifactu — VERIFACTU-F32 (impedir apagar o desinstalar con registros sin enviar)
Pendiente de enlazar: hub — HUB, perfil fiscal: el candado del proveedor fiscal en producción
QA: L-14

### HUB-F29 Desinstalar una aplicación
Estado: parcial — forzar deja activas las apps que dependen de la quitada; en el siguiente arranque el hub vuelve a instalar sola la app quitada desde el catálogo o, sin catálogo, arranca con la salud en rojo; quedan sus permisos de host y ERPlora no se entera; las negativas salen en inglés como en HUB-F28
Actor: administrador
Pantalla: HUB_SHELL: Apps
Pasos:
1. Un administrador pide desinstalar una app.
2. El hub aplica, por este orden, el candado del proveedor fiscal, la pregunta al motor de la app (HUB-F28) y, salvo que se pida forzar, la comprobación de dependientes: si otras apps instaladas la necesitan, apagadas o no, lo niega y las nombra.
3. La pantalla de Apps enseña antes las apps que dependen de ella y, si la persona confirma su pregunta de desinstalar, ya manda forzar (`force: true`): no hay un segundo paso «quitarla igualmente». Forzar solo se salta la comprobación de dependientes; los candados fiscales siguen, pero solo miran la app quitada. Las dependientes quedan activas y registradas sin su dependencia: en el siguiente arranque fallan con `missing_dependency`, la re-descarga de cada una vuelve a instalar la app quitada en su última versión y, sin catálogo, su copia local falla y la salud del hub queda en rojo.
4. Quita sus consultas, órdenes, menú y tareas programadas, olvida los roles que solo ella declaraba (las personas conservan su rol), borra su fila y su copia guardada, y quita sus textos del índice del asistente.
5. Las pantallas reciben `module.uninstalled`.
Entra: `POST /api/modules/:id/uninstall` con sesión de administrador y, opcionalmente, `{"force": true}`.
Sale: la app fuera del hub. **Sus tablas y sus datos se quedan** en la base, y también su carpeta en la caché de descargas, sus permisos de host concedidos y su declaración fiscal. ERPlora no recibe aviso de la desinstalación.
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
Sale: el módulo instalado y activo, sin aviso en vivo (`module.installed`), sin copia guardada y sin indexar para el asistente; los que fallan al arrancar se anotan y la salud del hub lo dice. Es la única puerta que conserva el código concreto de un rechazo del paquete (HUB-F20).
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
3. La pantalla carga el código, los iconos y las traducciones de cada app por una dirección con la versión dentro, que se puede guardar para siempre; el `module.json` lo pide siempre por la dirección sin versión, que se revalida siempre.
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
4. Al conceder, vuelve a poner en la cola **todos** los avisos del hub que murieron por falta de un permiso de host, no solo los de esa app (los que siguen sin permiso vuelven a morir).
Entra: `GET /api/modules/:id/capabilities` (cualquier sesión) y `PUT` del mismo con sesión de administrador.
Sale: `_module_capability_grants`. Sin el permiso, el motor propio de la app no corre (HUB-F12), sus recordatorios no salen y su paso de puesta en marcha sigue pendiente (HUB-F35). Una copia de seguridad del mismo hub los vuelve a conceder al restaurarse; una plantilla, no.
Si falla: un permiso desconocido o no declarado, error. Varios cambios en un mismo guardado no son atómicos: si uno falla, los anteriores ya quedaron; un valor que no sea verdadero o falso se toma como «retirar». Si los avisos no se pueden volver a encolar, se quedan en avisos caídos y se dice en el registro. Al restaurar una copia, quién concedió queda como `blueprint`.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, Ajustes › Permisos
Pendiente de enlazar: hub — HUB, avisos: reintentar los avisos rechazados por falta de permiso
QA: BD-03

### HUB-F33 Leer y guardar los ajustes de un módulo
Estado: parcial — la pantalla solo deja guardar al administrador, mientras el servidor acepta a quien tenga el permiso de la orden de guardar (el responsable lo tiene en Venta, Inventario y Cocina y lo hace por el asistente); y si la lectura de los ajustes falla (por ejemplo, sin permiso), la pantalla enseña los valores de fábrica del esquema como si fueran los guardados
Actor: administrador, responsable, asistente
Pantalla: HUB_SHELL: vista de un módulo › Ajustes
Pasos:
1. Si el módulo declara un bloque de ajustes, la pantalla le añade la pestaña «Ajustes»: pinta un formulario a partir del esquema del módulo (o el componente propio que el módulo indique).
2. Para cargarlo, ejecuta la consulta de lectura del módulo, con su permiso.
3. Al pulsar «Guardar», manda todos los valores a la orden de guardar del módulo, que pasa por el embudo de siempre (HUB-F03): su permiso y su esquema con sus valores por defecto. Con un componente propio del módulo (`settings.component`), la pantalla no pone ningún candado de administrador.
4. La pantalla dice «Ajustes guardados.».
Entra: el bloque `settings` del `module.json` (esquema, consulta, orden).
Sale: la fila de ajustes del módulo y el aviso que su orden emita.
Si falla: si la consulta de lectura falla, el error se traga y se pintan los valores de fábrica del esquema como si fueran los del negocio («No se pudieron cargar los ajustes.» solo sale si falla otra cosa, como el esquema). Los ven así quienes no tienen permiso de leerlos —hoy solo los empleados de Venta e Inventario, cuya consulta de lectura pide el permiso de gestionar los ajustes; en Cocina y Caja el empleado sí puede leerlos— y cualquiera tras un fallo pasajero de lectura; solo un administrador puede pisar entonces lo guardado con esos valores de fábrica, si guarda sin darse cuenta; al guardar, «No se pudieron guardar los ajustes.»; un campo rechazado por el esquema vuelve señalado («Revisa los campos marcados y vuelve a guardar.»). Quien no es administrador ve «Solo un administrador puede cambiar estos ajustes.» y no tiene «Guardar»; por el asistente o la API guarda igualmente si tiene el permiso.
Implicados: pendiente
Pendiente de enlazar: hub — HUB_SHELL, vista de un módulo: la pestaña «Ajustes» generada desde el bloque de ajustes
Pendiente de enlazar: cash_register — CASH_REGISTER-F01 (configurar cómo funciona la caja)
Pendiente de enlazar: sales — SALES-F34 (ajustar el TPV)
Pendiente de enlazar: kitchen — KITCHEN-F26 (ajustar la pantalla de cocina)
Pendiente de enlazar: inventory — INVENTORY-F19 (ajustar el inventario)
QA: qa-hub-restaurant §7.03 (discrepa)

### HUB-F34 Servir los datos de los paneles de Inicio
Estado: parcial — la pantalla no oculta un panel por el permiso que declara: quien no lo tiene ve el panel con «No disponible»; los paneles con componente propio no se refrescan con avisos
Actor: empleado, responsable, administrador
Pantalla: HUB_SHELL: Inicio
Pasos:
1. Cada app declara sus paneles de Inicio en su `module.json`: título, tamaño, a qué negocios aplica, si salen de fábrica, qué permiso piden, qué consulta los alimenta y con qué avisos se refrescan.
2. La pantalla lee esos manifiestos y pide al hub, por la puerta de consultas normal, la consulta de cada panel visible.
3. El hub la ejecuta con el permiso de quien mira, como cualquier consulta (HUB-F01).
4. Cuando el hub emite por el canal en vivo (`/ws`) uno de los avisos que el panel declara, la pantalla vuelve a pedirla; solo en los paneles declarativos, no en los de componente propio.
Entra: el bloque `widgets` de cada `module.json`; la sesión de quien mira.
Sale: nada guardado; los datos del panel. El hub no pinta paneles ni decide cuáles se ven: solo sirve el manifiesto, la consulta y los avisos en vivo.
Si falla: un panel cuya consulta exige un permiso que la persona no tiene recibe `permission_denied` y se pinta con «No disponible» (la pantalla no lo oculta por su `permission`). Los paneles de una app apagada, fuera del plan, o sin ninguna pestaña visible para esa persona no se pintan. Un panel no se refresca con un aviso que su app no emite: Inventario no emite ningún aviso que sus paneles escuchen cuando una venta descuenta stock, solo al cruzar el umbral (INVENTORY-F17).
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
2. Pone sus cuatro pasos propios, por este orden: «Tus apps» (hecho con una app activa), los datos del negocio (hecho con razón social y NIF válidos), la impresora (hecho con al menos un dispositivo dado de alta como host de impresión de la estación de tiques, esté conectado o no; no hace falta una impresora ni una ruta) y el equipo (hecho con más de una persona activa).
3. Añade un paso por cada app activa, incluida en el plan y aplicable al país del negocio que lo declare: ejecuta su consulta con la sesión de quien pregunta y lo da por hecho si la primera fila cumple todas sus condiciones y la app tiene concedidos los permisos de host que pide; si le falta un permiso, el paso lleva a Ajustes › Permisos.
4. Gradúa cada paso: ⛔ legal solo para lo que el hub de verdad rechazaría al facturar (los datos del negocio y, en cualquier entorno que no sea pruebas —también con el perfil sin resolver— sin vía hasta la AEAT, el paso de la app que pide el certificado); 🔴 o 🟡 según diga el módulo.
5. A cada persona solo le enseña los pasos que puede hacer, salvo un ⛔ pendiente, que ve todo el mundo (un paso de módulo sin `permission` lo ve todo el mundo); devuelve los pasos ordenados, los recuentos y si los datos los trajo una plantilla.
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

## Cobertura contra la referencia

Referencia adoptada para la plataforma de aplicaciones (se adopta esto, no más):

- [Odoo — aplicaciones y módulos](https://www.odoo.com/documentation/17.0/applications/general/apps_modules.html):
  instalar arrastra las dependencias; actualizar sin reinstalar; quitar una app avisa antes de lo
  que arrastra. Odoo borra los datos al desinstalar; ERPlora no (como Business Central).
- [Business Central — instalar y desinstalar extensiones](https://learn.microsoft.com/en-us/dynamics365/business-central/ui-extensions-install-uninstall):
  desinstalar conserva los datos por defecto; una app con dependientes solo se quita junto con
  ellos, tras enseñarlos; tras instalar, la app puede pedir su configuración obligatoria (la lista
  de puesta en marcha, HUB-F35).
- Shopify (apps): la app declara al instalarse los permisos que pide y el dueño los concede; una app
  sin permiso no ejecuta lo que lo necesita (Ajustes › Permisos, HUB-F32).

| Elemento | Estado | Flujo |
|---|---|---|
| Instalar una app con sus dependencias | hecho | HUB-F19 |
| Instalar sin cobrar una dependencia de pago sin consentimiento | hecho (se para y dice qué contratar) | HUB-F19 |
| Verificar integridad y firma del paquete | hecho (firma obligatoria solo si el despliegue tiene claves) | HUB-F19 |
| Seguir cobrando mientras se instala, actualiza o reconcilia una app | no hecho: el hub entero deja de atender, sin tope total de tiempo | HUB-F19, HUB-F23, HUB-F26 |
| Actualizar una app sin reiniciar y volver a la anterior si falla | hecho | HUB-F23 |
| Actualizaciones automáticas | parcial: al arrancar, app por app, solo las que no están en la carpeta de descargas (en la nube, todas); en la nube vuelven encendidas las apagadas | HUB-F25 |
| No bajar de versión ni saltarse el pin de soporte | parcial: un administrador, por la API con versión explícita, baja y se salta el pin | HUB-F23 |
| Apagar una app y lo que depende de ella | hecho | HUB-F28 |
| Desinstalar avisando de lo que depende | parcial: si se fuerza, las dependientes quedan activas y la app quitada vuelve en el siguiente arranque | HUB-F29 |
| Desinstalar conservando los datos | hecho | HUB-F29 |
| Borrar los datos de una app desinstalada | no hecho, a propósito | — |
| Permisos de la app concedidos por el dueño | hecho | HUB-F32 |
| Ajustes por app con formulario generado | parcial: quién guarda difiere entre pantalla y servidor; quien no puede leerlos (empleados de Venta e Inventario) ve los de fábrica | HUB-F33 |
| Paneles de Inicio por app | parcial: un panel sin permiso sale «No disponible» en vez de ocultarse | HUB-F34 |
| Lista de puesta en marcha | hecho | HUB-F35 |

## Datos: de quién es cada dato

- **Del hub (ciclo de vida de las apps)**: qué apps tiene el negocio, en qué versión, si están
  encendidas y el pin de soporte (`hub_module`); qué migraciones de cada app se aplicaron
  (`_hub_migrations`); la copia de cada paquete instalado (`hub_module_package`); los permisos de host
  concedidos a cada app (`_module_capability_grants`); lo último que dijo el catálogo (`_hub_meta`,
  `setup.catalog_offer`).
- **Datos personales**: `_module_capability_grants.granted_by`, el usuario del hub que concedió o
  retiró un permiso (`blueprint` si lo concedió una copia restaurada). `hub_module`, `_hub_migrations`
  y `hub_module_package` no tienen datos personales.

## Reglas que no se rompen

- **Las migraciones solo avanzan** y un `DROP TABLE` o `DROP COLUMN` se convierte en un cambio de
  nombre a `_deprecated_…` (`DROP INDEX` y `DROP CONSTRAINT` se ejecutan; nueve ficheros publicados
  entran por una lista de excepciones): no se pierden filas al actualizar ni al desinstalar. El hub
  no deshace una migración aplicada, ni siquiera si la instalación falla después.
- **Una app que aún debe registros a la AEAT no se apaga ni se quita**, y en producción no se queda
  el hub sin quien cumpla su régimen fiscal (HUB-F28, HUB-F29; el candado del proveedor es de
  [fiscal.md](fiscal.md), HUB-F316).
- **Un paquete no entra sin su huella SHA-256**; con claves de confianza desplegadas, tampoco sin
  firma válida.
- **Una app no da administración**: sus roles no pueden redefinir uno del hub ni heredar del de
  administrador.
- **Piezas que comparten los flujos de esta parte** (si cambias una, revisa todos sus flujos):
  - el registro de cada app (`installer::install`): validar, migrar, sembrar, registrar; si falla una
    actualización, vuelve la versión anterior — HUB-F19 a HUB-F23, HUB-F25, HUB-F26, HUB-F30;
  - el resolutor de versiones: la más nueva sin cuarentena, nunca hacia atrás, el pin de soporte
    gana — HUB-F23, HUB-F24, HUB-F25;
  - los permisos de host concedidos — HUB-F12, HUB-F32, HUB-F35 (y, fuera del área, los del índice).

## Lo que NO hace, a propósito

- No cobra una app de pago por su cuenta: si el plan pide comprarla, se para y lo dice.
- No borra los datos de una app al desinstalarla.
- No ofrece en la pantalla bajar de versión ni versiones en cuarentena (por la API, un administrador
  con versión explícita sí puede bajar: hueco, HUB-F23).
- No deja a un módulo declararse imprescindible para vender: el nivel ⛔ de la puesta en marcha lo
  decide el hub.

## Dudas abiertas

Se resuelven con `market-decision`; no las decide el worker. (Que instalar o actualizar deja al hub
entero sin atender está en las dudas comunes del índice.)

1. ¿Quién guarda los ajustes de una app: solo el administrador (la pantalla) o quien tenga el
   permiso de la orden de guardar (el servidor, el asistente)? Hoy discrepan (HUB-F33, SALES-F34,
   KITCHEN-F26, INVENTORY-F19).
2. ¿Se puede bajar de versión una app con una versión explícita por la API de un administrador, o
   solo soporte? (HUB-F23)
3. En la app instalada (Windows, macOS, Android), donde la carpeta de descargas no se vacía, las apps
   no se actualizan solas al arrancar (solo las que no encuentra en la carpeta); y en la nube cada
   despliegue vuelve a encender las apagadas. ¿Es lo que se quiere? (HUB-F25)
4. Forzar la desinstalación de una app de la que dependen otras: ¿debe quitar (o apagar) esas otras?
   Odoo y Business Central las quitan juntas tras enseñarlas; hoy ERPlora las deja activas sin su
   dependencia, y en el siguiente arranque vuelve a instalar sola la app quitada o, sin catálogo,
   arranca con la salud en rojo (HUB-F29).
5. Sin confirmar en el código del hub (lo verificó el verificador de la oleada y no lo pudo cerrar):
   - si la cuarentena se respeta con una versión explícita que llega por el plan de ERPlora (depende
     del SaaS);
   - si `/readyz` retenido por el candado durante una instalación larga hace que Swarm reinicie el
     contenedor (depende del `healthcheck` de `infra`);
   - si una migración que falla a la mitad se deshace sola (depende de si `erplora-db` ejecuta cada
     fichero en una transacción);
   - si `request_install`, que no pasa `module_id_is_safe` como actualizar y versiones, es explotable:
     el id y la versión van sin codificar dentro de las URLs firmadas a ERPlora y de las rutas de
     caché.

## Fuentes contrastadas

- El crate `crates/installer` describe el pipeline de instalación, pero ningún otro crate lo usa: la
  instalación real está en `crates/server/src/install.rs` (HUB-F19).
- La cabecera de `crates/server/src/module_reconcile.rs` dice que no sigue una desinstalación hecha
  por otra copia del hub; desde hub#2039 sí la sigue (HUB-F26).
- El comentario de `request_install` dice «Auth = JWT del usuario»; además exige antes una sesión
  local de administrador (HUB-F19).
- `hand-book/hub/06-aplicaciones.md` habla de «Aviso de permisos solicitados antes de instalar»: es
  de la pantalla; el servidor instala la app sin ningún permiso concedido y la pantalla los concede
  justo después por la puerta de HUB-F32 (`AppsPage.vue`, `doInstall`).
- INVENTORY-F19 dice que, sin permiso, sale «No se pudieron cargar los ajustes.»; la pantalla pinta en
  silencio los valores de fábrica (HUB-F33). SALES-F34 y KITCHEN-F26 deberían decir lo mismo para
  Venta (en Cocina el empleado sí los lee), y KITCHEN-F26 que el responsable guarda por el asistente.
- CASH_REGISTER-F12 dice que el empleado no ve «Caja (sesión actual)»; lo ve, con «No disponible»
  (HUB-F34).
- CASH_REGISTER-F01 no describe su paso de puesta en marcha («Tu caja»: hecho tras el primer
  guardado, solo administrador, 🟡) (HUB-F35).
- VERIFACTU-F32: la pantalla no traduce `verifactu.unsent_records` (HUB-F28).
