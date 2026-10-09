# WORKFLOW — Hub (pantallas) · Plan y archivos

Prefijo: HUB_SHELL

> Detalle del área «Aplicaciones, plan y archivos», segunda mitad (HUB_SHELL-F126…F134): **Mi plan**
> (facturas, suscripciones y pagos), los **límites del plan** (la pestaña Plan y límites de Sistema,
> HUB_SHELL-F128, que absorbió el retirado HUB_SHELL-F141 del área Sistema), las puertas hacia erplora.com para gestionar o
> mejorar el plan, y **Archivos**. La primera mitad (Apps, HUB_SHELL-F105…F125) está en
> `workflow/aplicaciones.md`. Aquí se cuenta lo que ve la persona; qué hace el servidor detrás está en
> el `workflow/acceso.md` del servidor (HUB-F162, F165) y en su `workflow/negocio-y-datos.md`
> (HUB-F245, F246) y no se repite. Código: `apps/web/src/views/BillingPage.vue`, `FilesPage.vue`,
> `components/PlanLimitsPanel.vue`, `FilePreviewModal.vue` y `lib/entitlement.ts`,
> `upgrade-plan-link.ts`, `management-link.ts`, `saas-door.ts`, `open-external.ts`, `save-download.ts`,
> `media.ts`, `file-preview.ts`, `file-preview-loaders.ts`.

## Referencia adoptada

Contrastada en los comentarios del propio código; no se ha rehecho.

- **Plan y pagos.** Las reglas de las tiendas de Google Play y Microsoft Store contra empujar al pago
  desde dentro de la app (hub#479, hub#756): el hub informa y dice dónde, no vende. El guardarraíl es
  `no-purchase-steering.test.ts` (regla común del índice).
- **Archivos.** Un gestor tipo Drive (`ok-file-manager` de OutfitKit); el visor sin `iframe` por la CSP
  del hub local (ADR-0171, ADR-0172).

## Antes de empezar

- Para facturas, suscripciones y el paso a erplora.com hay que haber entrado con la cuenta, no con un
  PIN (regla común «Sesión de PIN frente a sesión con cuenta» del índice).

## Flujos

### HUB_SHELL-F126 Ver las facturas del plan y descargarlas
Estado: parcial — las facturas pendientes, fallidas o devueltas salen «Abierta», y la lista trae las facturas de la persona en todos sus negocios, no solo las de este hub (leído en el código y en el servicio de erplora.com, sin ejecutar)
Actor: administrador, responsable, empleado
Pantalla: Mi plan
Pasos:
1. La persona pulsa **Mi plan** en el menú lateral. Se abre en **Facturas**.
2. Con la sesión de su cuenta de erplora.com ve una tabla: «Factura», «Fecha», «Vencimiento», «Importe» (en la moneda de la factura) y «Estado» («Borrador», «Abierta», «Pagada», «Anulada» o «Incobrable»). Sin facturas: «No hay facturas».
3. Pulsa «Descargar» en una fila. La factura se guarda como `factura-<número>.pdf`; sale «Guardado en {path}» si la app instalada dice dónde.
4. Quien entró solo con un PIN ve en su lugar «Consulta la facturación en tu cuenta de ERPlora»: «Tu sesión local sigue activa. Las facturas y suscripciones requieren la sesión de tu cuenta online en erplora.com.».
Entra: las facturas del usuario que da erplora.com con la sesión de la cuenta (el hub no pide filtrar por negocio; los estados de erplora.com son borrador, pendiente, pagada, fallida y devuelta, y la pantalla solo conoce cinco de otro vocabulario); el PDF se pide al descargar. Cualquiera que haya entrado con su cuenta ve las suyas.
Sale: nada guardado en el hub. El hub no emite ni cobra: es información del plan.
Si falla: «No pudimos cargar la facturación» con «Comprueba la conexión e inténtalo de nuevo. Puedes seguir utilizando el Hub.» y «Reintentar»; si falla la descarga, un aviso (con la frase propia de la app instalada cuando no puede guardar archivos).
Implicados: HUB_APP-F30, REC_ALTA-F20, SAAS-F01, SAAS_DASHBOARD-F119, SAAS_DASHBOARD-F135
QA: ninguno

### HUB_SHELL-F127 Ver las suscripciones y dónde se gestionan los pagos
Estado: no hecho — la tabla no enseña nada cierto: la pantalla lee campos que erplora.com no manda (cada fila sale sin nombre, a «0,00 €/mes» y «Abierta»), la cancelación al final del periodo no se pinta, y lo que lista son las suscripciones de apps de la persona, no el plan de este hub (leído en el código y en el servicio de erplora.com, sin ejecutar)
Actor: administrador
Pantalla: Mi plan
Pasos:
1. En **Mi plan** el administrador pulsa **Suscripciones**.
2. Lee arriba «Los cambios de plan se gestionan desde tu cuenta de ERPlora, en erplora.com.» y la tabla: «Suscripción», «Precio» (importe y ciclo, por ejemplo «/mes»), «Renueva» y «Estado». Sin ninguna: «No hay suscripciones activas».
3. Al volver a la ventana o a la pestaña del navegador, se recargan solas: contratar o cancelar en erplora.com se ve al volver.
4. En **Pagos** solo hay un aviso: «Los métodos de pago se gestionan desde tu cuenta de ERPlora, en erplora.com.».
Entra: las suscripciones de apps de la persona que da erplora.com (importe, periodo, estado, fin de periodo); la pantalla busca otros nombres (`plan_name`, `plan_price`, `billing_cycle`, `cancel_at_period_end`) y los estados de erplora.com (`active`, `past_due`, `cancelled`, `unpaid`) no son de factura. erplora.com manda además `currency`, sacada de la moneda de la persona (con «USD» si no tiene), que la pantalla no lee: pinta siempre euros.
Sale: nada guardado. No hay botón para comprar, cambiar o cancelar: se hace fuera.
Si falla: lo mismo que HUB_SHELL-F126 (cuenta no iniciada, o error con «Reintentar»).
Implicados: SAAS_DASHBOARD-F119
QA: ninguno

### HUB_SHELL-F128 Ver cuánto de los límites del plan se está usando
Estado: parcial — la etiqueta «Dentro del límite» / «Cerca del límite» solo puede cambiar en el plan gratuito: en un plan de pago sigue diciendo «Dentro del límite» en verde aunque una barra esté en rojo (la memoria al 95 %); con la pestaña ya abierta, una actualización que falla deja los últimos números sin avisar; quien no administra ve «Las métricas de recursos no están disponibles» con un «Reintentar» que no sirve, porque el hub le niega el uso en vivo (401, también a una sesión válida sin rol); y el plan se pinta con el identificador interno con mayúscula («Free»), sin traducir (leído en el código, sin ejecutar)
Actor: administrador
Pantalla: Sistema › Plan y límites
Pasos:
1. El administrador abre **Sistema › Plan y límites** (la pestaña es de Sistema; este flujo recoge también el antiguo HUB_SHELL-F141 «Ver el plan y sus límites», retirado por describir lo mismo).
2. Ve el «Plan actual» (el nombre de la clave del plan con la inicial en mayúscula, sin traducir; o «Desconocido») con una etiqueta «Dentro del límite» o «Cerca del límite» y cinco tarjetas: «Memoria (RAM)», «CPU», «Base de datos», «Dispositivos» y «Personas». Memoria y CPU llevan porcentaje y barra (verde, amarilla desde el 80 %, roja desde el 90 %); Base de datos, el tamaño frente a la cuota del plan; Dispositivos y Personas dicen «{n} / {tope}» y «Límite del plan» (o «Ilimitado»).
3. Lo que no se pudo medir sale como «n/d» («No disponible en este equipo»), nunca como cero. La base de datos sin cuota dice «Sin cuota de plan».
4. Se actualiza cada cinco segundos mientras la pestaña está abierta y visible («En vivo — se actualiza cada pocos segundos mientras esta página está abierta.»).
5. En el plan gratuito, si la memoria o la base de datos pasan del 80 %, o están ocupadas todas las plazas de personas o dispositivos (la CPU no cuenta), arriba sale «Te estás quedando sin margen en tu plan» con la frase de la causa («Este hub está cerca de su límite de memoria…», «Estás usando todos los dispositivos que permite tu plan.», «Tu plan tiene todas las plazas ocupadas, así que no puedes añadir a nadie más.») y «Los planes se gestionan desde tu cuenta de ERPlora, en erplora.com.», sin botón: lo retiró a propósito el requisito de las tiendas de aplicaciones.
Entra: el uso en vivo del hub y los topes del último plan verificado (HUB-F165); el hub solo lo da a un administrador.
Sale: nada guardado.
Si falla: «Las métricas de recursos no están disponibles» con «El Hub no ha podido informar de su uso de recursos ahora mismo. Puedes reintentarlo.» y «Reintentar». Es el mismo aviso para un fallo del hub y para un perfil sin permiso.
Implicados: HUB-F162, HUB-F165
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
Implicados: HUB-F142, HUB_APP-F29, REC_ALTA-F20, SAAS_AUTH-F21, SAAS_DASHBOARD-F96, SAAS_DASHBOARD-F201
QA: L-17

### HUB_SHELL-F130 Ver los archivos del negocio
Estado: hecho
Actor: administrador, responsable, empleado, cajero
Pantalla: Archivos
Pasos:
1. La persona pulsa **Archivos** en el menú lateral (la ven todos los perfiles).
2. Mientras carga, el gestor muestra el indicador. Después ve el árbol de carpetas a la izquierda (en una pantalla estrecha se pliega en un selector), la ruta de la carpeta abierta, los archivos en vista de cuadrícula o de lista y el espacio usado («Espacio», o «Sin límite»).
3. Navega pulsando carpetas, busca en «Buscar archivos…» (solo dentro de la carpeta abierta) y, sin archivos, lee «Sin archivos».
4. En la raíz están las carpetas del negocio y, para el propietario o un administrador, también las de las apps (adjuntos de cada una), los registros del sistema y la actividad. Algunas son de solo lectura.
Entra: el listado de la carpeta con qué se puede hacer en ella. La pantalla enseña lo que sirve la API: a quien no administra (responsable, empleado, cajero) el servidor no le manda la carpeta de registros, la de actividad del sistema ni la de las apps con los XML de VeriFactu, así que no aparecen en el árbol (HUB-F245, ERPlora/hub#2495).
Sale: nada guardado.
Si falla: «No se pudieron cargar los archivos» con el motivo («Esta carpeta es de una app que no permite cambiar sus archivos.», el de erplora.com sin contestar o, si no llegó a salir, «Comprueba la conexión y vuelve a intentarlo.») y «Reintentar»; el gestor queda vacío sin inventar datos.
Implicados: HUB-F245, WHATSAPP_INBOX-F06
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
Implicados: HUB-F246
QA: ninguno

### HUB_SHELL-F132 Previsualizar y descargar un archivo
Estado: hecho
Actor: administrador, responsable, empleado, cajero
Pantalla: Archivos
Pasos:
1. La persona pulsa «Abrir» en un archivo. Se abre un visor grande dentro del hub, con el nombre como título, «Descargar» y «Cerrar» (y «Ampliar»/«Reducir» donde se puede).
2. El visor entiende imágenes, PDF (dibujado en pantalla; las primeras 30 páginas y, si es más largo, «Mostrando las primeras {shown} de {total} páginas. Descarga el archivo para leerlo entero.»; ampliar y reducir solo en imágenes y PDF), hojas de cálculo (xlsx, xlsm, csv, tsv), Word moderno (docx), texto, registros y código, JSON plegable, vídeo y audio.
3. Para cualquier otro tipo (por ejemplo `.xls` o `.doc` antiguos) sale «Sin vista previa»: «Este tipo de archivo no se puede mostrar aquí. Descárgalo para abrirlo con una aplicación de tu dispositivo.».
4. «Descargar» (en el visor o en la fila) guarda el archivo; sale «Guardado en {path}» si la app dice dónde.
Entra: los bytes del archivo, que pide el hub al almacenamiento; el navegador nunca toca el almacenamiento.
Sale: nada guardado. Abrir un `.log` no descarga el lector de PDF.
Si falla: cualquier fallo al traer o al dibujar sale como «No se pudo abrir el archivo»: «No llegó el contenido del archivo. Revisa la conexión e inténtalo de nuevo.» (el visor no distingue un archivo demasiado grande del resto; el tope de 25 MiB es del hub, HUB-F245, y su frase «Ese archivo es demasiado grande para abrirlo aquí. Descárgalo.» no llega a salir en el visor); si la app instalada no puede guardar archivos (por ejemplo en una tableta), una frase propia que lo dice.
Implicados: HUB-F245, HUB_APP-F30
QA: ninguno

### HUB_SHELL-F133 Mover y renombrar un archivo o una carpeta
Estado: hecho
Actor: administrador
Pantalla: Archivos
Pasos:
1. Para mover, el administrador arrastra el archivo o la carpeta a otra carpeta del árbol, o elige «Mover a…». Sale «Movido a «{folder}».» (si va a la raíz, «Movido a «Archivos».»).
2. Para renombrar, elige «Renombrar» (o «Renombrar carpeta»): un diálogo con el nombre actual ya escrito (hasta 255 caracteres). Confirma y sale «Renombrado.».
3. Si renombra o mueve la carpeta en la que está, la pantalla sigue a su nueva ruta o sube a la de arriba.
4. Las carpetas de solo lectura no se pueden arrastrar, renombrar ni recibir archivos. A quien no administra, el menú del gestor le sigue ofreciendo «Mover a…» y «Renombrar», que contestan «Solo un administrador puede modificar los archivos.».
Entra: el origen y el destino, o el nombre nuevo.
Sale: pide al servidor el cambio (HUB-F246). Mover exige poder borrar en el origen y subir en el destino.
Si falla: «No se pudo mover. Puede que la carpeta de destino sea de solo lectura.» / «No se pudo renombrar. Puede que esta carpeta sea de solo lectura.» o la causa exacta: «El archivo ya está en esa carpeta.», «Una carpeta no se puede mover dentro de sí misma.», «Ese nombre no es válido. Usa un nombre sin barras ni puntos sueltos.», «Esta carpeta es de una app que no permite cambiar sus archivos.».
Implicados: HUB-F246
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
Implicados: HUB-F246
QA: ninguno

## Cobertura contra la referencia

| Elemento | Estado | Flujo |
|---|---|---|
| Facturas | parcial (estados y alcance) | HUB_SHELL-F126 |
| Suscripciones | no hecho (lee campos que erplora.com no manda) | HUB_SHELL-F127 |
| Pagos (solo aviso) | hecho | HUB_SHELL-F127 |
| Límites del plan | parcial (etiqueta solo en gratuito, el aviso no cuenta la CPU, plan sin traducir) | HUB_SHELL-F128 |
| Gestionar o mejorar el plan en erplora.com | hecho | HUB_SHELL-F129 |
| Ver, subir, previsualizar, mover, renombrar, borrar archivos | hecho | HUB_SHELL-F130 a F134 |
| Copiar un archivo | no hecho (tampoco en el servidor, HUB-F246) | — |
| Papelera, compartir por enlace, buscar en todas las carpetas | no hecho (fuera del MVP) | — |

## Datos: de quién es cada dato

- **Facturas, suscripciones y límites del plan**: de erplora.com; el hub solo los pinta y no los guarda.
- **Archivos**: del almacenamiento de erplora.com (o disco en desarrollo); el hub los sirve.

Datos personales que pasan por estas pantallas: el PDF de cada factura, que se guarda en el
dispositivo; el contenido de `_logs` y de los XML, que en Archivos solo abren el propietario y un
administrador (HUB-F245). Las facturas que lista el hub son las de la persona en todos sus negocios.

## Reglas que no se rompen

- Una lista que no se pudo leer (facturas, archivos) dice que no se pudo y conserva lo que ya tenía
  (regla común del índice).
- La copia que reparte Google Play no lleva los botones de gestionar o mejorar el plan (regla común
  del índice, `no-purchase-steering.test.ts`).

## Lo que NO hace, a propósito

- No vende ni cambia el plan: contratar, cambiar, cancelar y los métodos de pago son de erplora.com.
- No copia archivos, no tiene papelera, no comparte por enlace.

## Dudas abiertas

Se resuelven con `market-decision`; no las decide el worker.

- ¿Copiar archivos entre carpetas?
- ¿Qué filtra erplora.com en las facturas (por negocio) y qué campos manda en las suscripciones? Hoy
  la pantalla de suscripciones no funciona (HUB_SHELL-F127).

## Fuentes contrastadas

- Manual `05-plan-y-facturas.md`: «Revisa la suscripción: plan, ciclo, renovación y estado». La
  pantalla no lo cumple (HUB_SHELL-F127). «Busca por número»: la tabla de facturas lleva buscador por
  número (sin confirmar que sea visible).
- Tests: el nombre de un test describe el texto, no una función (`FilesPage.move-copy` = mover +
  etiquetas, no copiar).
