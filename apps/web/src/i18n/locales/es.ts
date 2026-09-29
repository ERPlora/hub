// Textos del shell (chrome) en español. Solo cubre la navegación, la topbar y el footer del
// sidebar — NO los textos de cada vista (eso se irá migrando por pantalla). Mantener plano y
// agrupado por zona para que sea fácil de extender.
// Un hecho, una frase (hub#1693). Ver el comentario gemelo en `en.ts`: se declara una vez y se
// referencia, para que la pantalla de conexión y las del back-office no se separen nunca.
const CLOUD_UNREACHABLE = 'Tu hub no ha podido llegar a erplora.com. Revisa la conexión e inténtalo de nuevo.';

export default {
  // Nombre del idioma para el selector de Ajustes (se muestra tal cual). Requerido en cada locale.
  _meta: { name: 'Español' },
  nav: {
    general: 'General',
    account: 'Cuenta',
    home: 'Inicio',
    employees: 'Empleados',
    files: 'Archivos',
    // hub#365 — the money door, in the first person of the business. «Billing» names the ledger the
    // SaaS keeps; from inside the till what the owner asks is which plan they are on. One label for
    // two surfaces: this sidebar entry and the title of the page it opens.
    billing: 'Mi plan',
    apps: 'Apps',
    system: 'Sistema',
    settings: 'Ajustes',
    apiDocs: 'API',
    upgradePlan: 'Actualizar plan',
    upgradePlanError: 'No se pudo abrir tu navegador. Entra en erplora.com para gestionar tu plan.',
  },
  apiDocs: {
    title: 'Documentación de la API',
    introTitle: 'API pública del Hub',
    introBody:
      'Esta documentación lista los endpoints disponibles de los módulos instalados. Para llamarla, crea una API key en Usuarios → API keys y pégala como Bearer en «Authorize».',
    loading: 'Cargando documentación…',
    errorTitle: 'No se pudo cargar la documentación',
    errorBody: 'No se pudo obtener el spec de la API. Inicia sesión e inténtalo de nuevo.',
    retry: 'Reintentar',
  },
  topbar: {
    back: 'Atrás',
    apps: 'Mis apps',
    appsEmpty: 'Aquí aparecerán tus apps. Pulsa Apps para añadir las que necesite tu negocio.',
    appsClose: 'Cerrar',
    assistant: 'Asistente',
    // The way out to management (hub#364). It crosses a product boundary, so it names the
    // destination: `manageShort` is what is READ on the button, `manage` is the whole sentence the
    // accessible name reads out (hub#1400 — the entry used to be icon-only at the till). The short
    // one is the BRAND, so it is the same word in every language.
    manageShort: 'erplora.com',
    manage: 'Gestiona tu negocio en erplora.com',
    manageError: 'No se pudo abrir tu navegador. Entra en erplora.com para gestionar tu negocio.',
    notifications: 'Notificaciones',
    noNotifications: 'Todo al día. Sin notificaciones.',
    deadLettersTitle: 'Eventos caídos',
    deadLettersBody:
      'Hay {count} evento que el relay no pudo entregar. Revísalo y reenvíalo. | Hay {count} eventos que el relay no pudo entregar. Revísalos y reenvíalos.',
    // Impresión sin drenar (hub#987). Nombra la estación: «la impresión está parada» manda al dueño
    // a mirar cuatro impresoras; «la cocina está parada» lo manda a una.
    printingStalledTitle: 'Nadie está imprimiendo «{station}»',
    printingStalledBody:
      'Hay {count} documento esperando desde hace {minutes} min. Comprueba que la caja que imprime ahí está encendida. | Hay {count} documentos esperando desde hace {minutes} min. Comprueba que la caja que imprime ahí está encendida.',
    moduleUpdatesTitle: 'Actualizaciones de apps',
    moduleUpdatesBody:
      '{n} app tiene una versión nueva. Actualízala desde Mis apps. | {n} apps tienen una versión nueva. Actualízalas desde Mis apps.',
    // Nombre del menú en el que se pliega la barra en el móvil. Es solo-icono: esto es lo único con
    // lo que un lector de pantalla puede anunciarlo.
    more: 'Más opciones',
    configure: 'Configurar',
    menu: 'Abrir menú',
    collapseMenu: 'Colapsar menú',
    expandMenu: 'Expandir menú',
  },
  sidebar: {
    profile: 'Perfil',
    signOut: 'Cerrar sesión',
  },
  // Textos del shell de la app instalada. «Cambiar de negocio» (hub#447): la app recuerda UN
  // negocio y esta es la puerta del usuario hacia otro. Se habla de NEGOCIO, nunca de «hub».
  shell: {
    changeHub: 'Cambiar de negocio',
    changeHubTitle: '¿Cambiar de negocio?',
    changeHubBody:
      'Este dispositivo cerrará la sesión de este negocio y mostrará tu lista de negocios.',
    changeHubCancel: 'Cancelar',
    changeHubConfirm: 'Cambiar',
  },
  // hub#1736 — los dos botones que Ionic pone en TODO diálogo de selección (`ion-select`). Sus
  // valores por defecto son literales ingleses dentro de la propia librería, y los desplegables que
  // usa el comerciante los pintan los Web Components de los módulos: se traducen una vez, en el
  // shell, para todos (`lib/ionic-select-text.ts`).
  selectDialog: {
    ok: 'Aceptar',
    cancel: 'Cancelar',
  },
  actionFeedback: {
    csvExported: 'CSV exportado',
    csvExportedRows: 'CSV exportado · {n} fila | CSV exportado · {n} filas',
    csvImported: 'Fichero CSV leído',
    csvImportedRows: 'Fichero CSV leído · {n} fila | Fichero CSV leído · {n} filas',
  },
  // hub#1518 — una pantalla cuyo código no llegó (se cortó la conexión, o el fichero se quedó
  // viejo tras un despliegue). Dicho en cristiano: en un mostrador nadie sabe qué es un «chunk».
  viewLoad: {
    failedToast: 'No se ha podido abrir esa sección. Revisa la conexión y vuelve a intentarlo.',
    blockedTitle: 'ERPlora no ha podido terminar de abrirse',
    blockedBody:
      'Se ha cortado la conexión mientras se cargaba esta pantalla. Revisa la conexión y vuelve a intentarlo.',
    blockedAction: 'Reintentar',
    // hub#1524 — el otro motivo de la misma pantalla en blanco: ha reventado el código de la
    // pantalla. Con sus propias palabras a propósito: decirle a alguien que se ha cortado la
    // conexión cuando no es verdad lo manda a reiniciar un router que funciona.
    brokenTitle: 'No se ha podido abrir esta pantalla',
    brokenBody:
      'Algo ha fallado dentro de ERPlora al abrir esta pantalla. Vuelve a intentarlo y, si sigue pasando, cierra ERPlora y ábrelo de nuevo.',
    brokenAction: 'Reintentar',
    // hub#1590 — el mismo fallo de código, pero con el hub ya abierto. Aquí no hay nada en blanco
    // que rescatar, así que lleva un aviso corto y no el muro de texto: tapar un TPV en marcha
    // quitaría de vista la comanda que se está tomando. Con sus palabras, por lo mismo que arriba.
    brokenToast: 'No se ha podido abrir esa sección. Algo ha fallado dentro de ERPlora; vuelve a intentarlo.',
  },
  // hub#1723 — an address this hub does not have. NOT a mistake the person made: nine times out
  // of ten it is an old link or a guess at the name of an app, so the words point at the address
  // and then at the way out, without blaming anybody.
  notFound: {
    title: 'Esta página no existe',
    body: 'La dirección que has abierto no forma parte de este hub. Puede ser un enlace antiguo, o el nombre de una app adivinado: tus apps se abren desde el menú o desde Inicio.',
    action: 'Ir a Inicio',
  },
  // La app instalada es más antigua que la que publicamos (hub#400). Se la llama ERPlora, nunca
  // «la app»: «apps» ya es la palabra de lo que añades a tu negocio (ADR-0254), y un solo nombre
  // para dos cosas es como un cajero acaba desinstalando el TPV.
  installQr: {
    title: 'Ábrelo en el móvil',
    hint: 'Escanea el código. Para dejarlo fijo, añádelo a la pantalla de inicio desde el menú del navegador.',
  },
  appUpdate: {
    available: 'Actualizar ERPlora ({version})',
    confirmTitle: 'Actualizar ERPlora',
    confirmBody:
      'Se abre tu navegador para descargar la versión {version}. No se instala nada solo: termina de atender, cierra ERPlora y abre lo que hayas descargado.',
    action: 'Descargar',
    cancel: 'Ahora no',
    failed: 'No hemos podido abrir tu navegador. Entra en erplora.com para conseguir la nueva versión.',
    android: {
      confirmBody:
        'Se abre la ficha de ERPlora en Google Play. La versión {version} la instala Google Play: no hay ningún archivo que descargar ni que abrir.',
      action: 'Abrir Google Play',
      failed: 'No hemos podido abrir Google Play. Búscalo allí como ERPlora para conseguir la nueva versión.',
    },
  },
  assistant: {
    confirmTitle: 'El asistente quiere ejecutar una acción',
    confirmCancel: 'Cancelar',
    confirmRun: 'Ejecutar',
    title: 'Asistente',
    empty: 'Pregúntame por tus ventas, tu inventario o cualquier cosa de tu negocio.',
    emptySetup: 'Revisa la configuración de tu negocio. Elige una opción o escribe tu duda.',
    suggestWhatsMissing: '¿Qué falta por configurar?',
    suggestHowTo: '¿Cómo configuro',
    goTo: 'Ir a',
    placeholder: 'Escribe un mensaje…',
    send: 'Enviar',
    stop: 'Detener',
    close: 'Cerrar',
    noReply: '(sin respuesta)',
    error: 'No se pudo contactar con el asistente.',
    unavailable: 'El asistente no está disponible ahora mismo. Vuelve a intentarlo en unos minutos.',
    // saas#1540 — quedarse sin mensajes es un estado del PLAN, no una avería. Decir «no se
    // pudo contactar» convierte el único momento de conversión del tier gratuito en un fallo.
    quotaTitle: 'Has usado todos tus mensajes del asistente',
    quotaUsed: 'Plan {tier} — {used} de {limit} mensajes este mes.',
    quotaCta: 'Ver planes',
    includedInPlan: 'Incluido en tu plan {plan}.',
    includedInHubPlan: 'Incluido en tu plan.',
    upgradeHubPlan: 'Subir de plan',
    planOpenFailed: 'No se pudo abrir la página de tu plan en el navegador. Inténtalo de nuevo.',
    quotaRemaining: 'Plan {tier} — te quedan {remaining} de {limit} mensajes este mes.',
    quotaResets: 'Se renuevan el {date}.',
    quotaAskAdmin: 'Pídele al responsable del negocio que amplíe el plan del asistente.',
    quotaManagedInAccount: 'El plan del asistente se amplía desde tu cuenta de ERPlora, en erplora.com.',
    plansTitle: 'Elige un plan',
    plansConfirm: 'Ir al pago',
    planOption: '{name} — {price} €/mes',
    plansUnavailable: 'Ahora mismo no hay planes a los que ampliar.',
    checkoutOpenFailed: 'No se pudo abrir la página de pago en el navegador. Inténtalo de nuevo y, si sigue fallando, actualiza la app de ERPlora.',
    attach: 'Adjuntar archivo',
    attachRemove: 'Quitar adjunto',
    attachImage: 'imagen',
    attachTooLarge: 'El archivo es demasiado grande.',
    mic: 'Dictar por voz',
    micStop: 'Detener la grabación',
    micDenied: 'El acceso al micrófono está denegado. Permítelo en tu navegador para dictar.',
    micUnsupported: 'Este navegador no puede grabar audio.',
    micFailed: 'No se ha podido transcribir el audio.',
    report: 'Denunciar un problema',
    reportTitle: 'Denunciar esta respuesta',
    reportHint:
      'Si esta respuesta del asistente te parece inapropiada o dañina, envíanosla y la revisaremos.',
    reportPlaceholder: 'Comentario (opcional)',
    reportConfirm: 'Denunciar',
    reportSent: 'Gracias, hemos recibido tu denuncia.',
    reportError: 'No se pudo enviar la denuncia. Inténtalo de nuevo.',
    // hub#1038/#1039/#1048 — lo dice el RUNTIME, nunca el modelo: los recibos del turno no
    // respaldan lo que afirmó la respuesta. Se muestra como aviso sobre el propio mensaje.
    claimedWithoutEffect:
      'El asistente ha dicho que hizo un cambio, pero no se ejecutó ninguna acción. No se ha modificado nada.',
    unsourcedId:
      'Esta respuesta muestra un identificador que el asistente no ha leído de verdad. No te fíes de él.',
    unknownRoute: 'Esta respuesta señala una pantalla que no existe aquí.',
    // hub#1040 — cuando la app no sabe nombrar su propia acción se dice, en vez de rellenar el
    // hueco con el nombre interno del command (hub#363: ese vocabulario es nuestro, no del mostrador).
    confirmUnnamedAction: 'Una acción que esta app no sabe nombrar',
    // hub#1042 — lo destructivo pide más que un clic. Escribir el NÚMERO es lo que obliga a
    // leer la frase que dice cuántos van a caer.
    confirmDestructive: 'Esto no se puede deshacer desde la pantalla. Escribe {expected} para confirmar.',
    confirmDestructiveWord: 'BORRAR',
    confirmBulkAffected: 'Vas a borrar {count} registro. | Vas a borrar {count} registros.',
    confirmBulkUnknown:
      'No puedo saber cuántos registros borraría esto, así que no lo hago desde aquí. Abre la pantalla, donde puedes verlos.',
  },
  // hub#988 — la placa leída por el lector NFC del propio aparato. Solo dos frases, porque solo
  // estas dos merecen interrumpir: un aparato sin lector no dice nada (el lector USB sigue
  // funcionando igual que siempre, así que no hay nada que el usuario pueda hacer al respecto).
  badge: {
    nfcDisabled: 'El NFC está apagado en este aparato. Enciéndelo para leer las tarjetas acercándolas.',
    nfcRandomUid:
      'Esta tarjeta da un número distinto cada vez que se lee, así que no puede usarse como placa. Prueba con otra.',
  },
  // Lo que se le dice al usuario tras pulsar «descargar», lo pulse donde lo pulse (hub#480). Dentro
  // de la app instalada no hay barra de descargas ni aviso del sistema: si no lo decimos nosotros,
  // no lo dice nadie.
  download: {
    savedTo: 'Guardado en {path}',
    noPlaceToSave: 'Esta app no puede guardar archivos en un móvil o una tablet. Abre tu negocio en un navegador para descargarlo.',
    failed: 'No se ha podido descargar el archivo.',
  },
  files: {
    // hub#1776 — ver el comentario gemelo en `en.ts`.
    errors: {
      unauthorized: 'Tu sesión ha caducado. Vuelve a entrar e inténtalo otra vez.',
      forbidden: 'Solo el propietario o un administrador puede cambiar los archivos.',
      not_found: 'Ese archivo o carpeta ya no existe. Actualiza la lista.',
      media: {
        no_files: 'No se ha elegido ningún archivo para subir.',
        busy: 'Ahora mismo se están procesando demasiados archivos. Inténtalo de nuevo en un momento.',
        too_large: 'Ese archivo es demasiado grande para abrirlo aquí. Descárgalo.',
        invalid_name: 'Ese nombre no es válido. Usa un nombre sin barras ni puntos sueltos.',
        missing_path: 'Elige antes un archivo o una carpeta.',
        same_path: 'El archivo ya está en esa carpeta.',
        move_into_itself: 'Una carpeta no se puede mover dentro de sí misma.',
        read_only_folder: 'Esta carpeta es de una app que no permite cambiar sus archivos.',
      },
    },
    title: 'Archivos',
    subtitle: 'Todo lo que se guarda en la carpeta media: adjuntos de las apps, registros y actividad.',
    upload: 'Subir archivo',
    import: 'Importar',
    search: 'Buscar archivos…',
    folders: 'Carpetas',
    space: 'Espacio',
    empty: 'Sin archivos',
    download: 'Descargar',
    delete: 'Eliminar',
    open: 'Abrir',
    newFolder: 'Nueva carpeta',
    folderName: 'Nombre de la carpeta',
    createFolder: 'Crear carpeta',
    cancel: 'Cancelar',
    retry: 'Reintentar',
    loadErrorTitle: 'No se pudieron cargar los archivos',
    loadErrorBody: 'Comprueba la conexión y vuelve a intentarlo.',
    permissionDenied: 'Solo un administrador puede modificar los archivos.',
    uploadSuccess: 'Archivos subidos.',
    uploadError: 'No se pudieron subir los archivos.',
    openError: 'No se pudo abrir el archivo.',
    deleteTitle: 'Eliminar archivo',
    deleteBody: 'Vas a eliminar «{name}». Esta acción no se puede deshacer.',
    deleteSuccess: 'Archivo eliminado.',
    deleteError: 'No se pudo eliminar el archivo.',
    folderCreated: 'Carpeta creada.',
    folderError: 'No se pudo crear la carpeta.',
    rename: 'Renombrar',
    newName: 'Nombre nuevo',
    renameSuccess: 'Renombrado.',
    renameError: 'No se pudo renombrar. Puede que esta carpeta sea de solo lectura.',
    deleteFolderTitle: 'Eliminar carpeta',
    deleteFolderBody: 'Vas a eliminar «{name}» y todo su contenido. Esto no se puede deshacer.',
    moveSuccess: 'Movido a «{folder}».',
    moveError: 'No se pudo mover. Puede que la carpeta de destino sea de solo lectura.',
    move: 'Mover a…',
    renameFolder: 'Renombrar carpeta',
    deleteFolder: 'Eliminar carpeta',
    noLimit: 'Sin límite',
    close: 'Cerrar',
    previewZoomIn: 'Ampliar',
    previewZoomOut: 'Reducir',
    previewErrorTitle: 'No se pudo abrir el archivo',
    previewErrorBody: 'No llegó el contenido del archivo. Revisa la conexión e inténtalo de nuevo.',
    previewUnsupportedTitle: 'Sin vista previa',
    previewUnsupportedBody: 'Este tipo de archivo no se puede mostrar aquí. Descárgalo para abrirlo con una aplicación de tu dispositivo.',
    previewPdfTruncated: 'Mostrando las primeras {shown} de {total} páginas. Descarga el archivo para leerlo entero.',
  },
  // La checklist de configuración — la superficie del panel de `hub.setup.status` (hub#372).
  // `items.<key>` cubre SOLO los ítems del core: la clave de un ítem del core es también su clave
  // i18n; el título de un módulo viaja en inglés en su manifest y se pinta tal cual.
  boot: {
    unreachable: {
      title: 'No podemos conectar con tu negocio',
      body: 'ERPlora no responde. Comprueba que este dispositivo tiene conexión a Internet y vuelve a intentarlo. Si sigue pasando, el problema puede ser nuestro.',
      retry: 'Reintentar',
    },
    refused: {
      title: 'Tu negocio no está disponible ahora mismo',
      body: 'ERPlora responde, pero ahora mismo no puede abrir tu negocio. Este dispositivo y su conexión están bien: no tienes que revisar nada. Lo volvemos a intentar solos cada {seconds} segundos.',
      retry: 'Reintentar ahora',
    },
  },
  offline: {
    title: 'Sin conexión a Internet',
    body: 'Lo que necesita Internet —cargar pantallas, sincronizar, enviar facturas— no va a funcionar hasta que vuelva. Este aviso desaparece solo.',
    hubTitle: 'ERPlora no responde',
    hubBody: 'Tu dispositivo parece tener conexión, pero ERPlora no contesta: puede ser tu Internet o un problema por nuestra parte. Lo que lo necesita —cargar pantallas, sincronizar, enviar facturas— no va a funcionar hasta que vuelva. Este aviso desaparece solo.',
  },
  setup: {
    title: 'Termina de configurar tu negocio',
    progress: '{done} de {total} hechos',
    viewAll: 'Ver todo',
    viewLess: 'Ver menos',
    configure: 'Configurar',
    review: 'Pedírselo al asistente',
    doneLabel: 'Hecho',
    // Los tres niveles. Solo el ⛔ puede nombrar un rechazo, porque es el único que tiene un
    // dispatcher detrás (`enforce_fiscal_precondition`, ADR-0203) — y lo que rechaza es la FACTURA:
    // una venta sin identidad fiscal se cierra igual. El 🔴 es un módulo diciendo que su propia
    // configuración importa, y el core nunca deja que eso se convierta en una condición para
    // vender: dice cuánto importa y ahí se queda (hub#1726). Guardia:
    // `i18n/setup-level-copy.test.ts`.
    levelLegal: 'Necesario para facturar',
    levelFunctional: 'Importante',
    levelRecommended: 'Recomendado',
    // El tercer estado: una avería NUESTRA, no una tarea suya. No puede sonar a deber.
    unavailableLabel: 'Todavía no disponible',
    unavailableHint: 'Esto es cosa nuestra: por tu parte no hay nada que hacer aún. Estamos en ello.',
    // Un muro que no te toca a ti derribar (hub#435). Dice QUIÉN puede — nunca el nombre de un
    // permiso —, porque un bloqueo sin dueño deja al usuario sin ningún sitio al que ir.
    delegatedHint: 'Esto lo tiene que configurar un administrador.',
    inheritedHint: 'Vino de la plantilla que usaste. Merece un vistazo: tu sala y tus precios son tuyos.',
    missingPermissionHint: 'Esta app necesita un permiso que aún no le has dado. Sin él, no puede hacer su trabajo.',
    grantPermission: 'Dar permiso',
    completeTitle: 'Tu negocio está listo',
    completeBody: 'No queda nada pendiente en la checklist.',
    // La tarjeta héroe de un negocio que todavía no tiene apps (hub#368). Su único trabajo es la
    // PRIMERA elección, así que dice lo que hace un clic Y lo que deja para el dueño: una plantilla
    // trae las apps y el catálogo de un oficio, nunca los datos de ESTE negocio (ADR-0195 §4/§5).
    hero: {
      title: 'Empieza con un negocio como el tuyo',
      body: 'Elige el que más se parezca al tuyo y te dejamos sus apps y su catálogo listos de una vez. Después tendrás que poner tus propios datos.',
      use: 'Usar esta',
      more: 'Ver todas las plantillas',
      dismiss: 'Ahora no',
      working: 'Preparando «{name}»…',
      readyTitle: 'Ya tienes tus apps y tu catálogo',
      readyBody: 'Lo que queda es lo que solo puedes contestar tú: los datos de tu negocio. Los tienes en la lista de abajo.',
      sampleData: 'Trae además datos de ejemplo —clientes, citas— para que veas cómo funciona todo.',
      sampleDataUndo: 'Los datos de ejemplo están para que trastees. Puedes quitarlos cuando quieras desde Ajustes › Datos.',
      partialTitle: 'Casi: algo no ha entrado',
      // Una decisión de compra, nunca una avería (ADR-0060, hub#409): nombra lo que hay que añadir
      // en vez de pintar un error rojo sobre un plan que el dueño simplemente no ha contratado.
      blocked: 'Estas hay que añadirlas antes a tu plan: {apps}',
      failed: 'Hay algo más que no ha entrado. Puedes ver el detalle y reintentarlo en Ajustes › Datos.',
      failedApps: 'Estas no han entrado: {apps}. Puedes ver el detalle y reintentarlo en Ajustes › Datos.',
      // hub#899 — la otra mitad de la misma queja: cuando lo que falla es una SECCIÓN no hay app que
      // nombrar y la tarjeta caía en «Hay algo más que no ha entrado». Dos «algos» en una tarjeta,
      // justo en el minuto en que ella comprueba si su negocio está dentro.
      failedParts: 'Esto no ha entrado: {parts}. Puedes ver el detalle y reintentarlo en Ajustes › Datos.',
      failedAppsAndParts:
        'Estas no han entrado: {apps}. Tampoco {parts}. Puedes ver el detalle y reintentarlo en Ajustes › Datos.',
      partSettings: 'los ajustes del negocio',
      partTeam: 'las personas',
      partRoles: 'los roles y lo que puede hacer cada uno',
      partFiscal: 'los datos fiscales',
      partMedia: 'las imágenes',
      partAppData: 'los datos de {app}',
      notStartedTitle: 'No se ha podido abrir esa plantilla',
      notStartedBody: 'No ha cambiado nada en tu negocio. Inténtalo otra vez o cárgala desde Ajustes › Datos.',
      interruptedTitle: 'La configuración no ha terminado',
      // NO afirmamos que no ha cambiado nada: puede que ya haya entrado la mitad, y decir lo
      // contrario mandaría al dueño a pulsar otra vez encima.
      interruptedBody: 'Puede que parte ya esté dentro. Compruébalo en Ajustes › Datos antes de volver a intentarlo.',
      continue: 'Continuar',
      retry: 'Intentar otra vez',
      // hub#763 — la puerta al informe que nombran las frases de arriba. Ahora el informe sobrevive
      // a la navegación, así que este botón lleva a algo y no al catálogo de plantillas vacío.
      seeReport: 'Ver el informe',
    },
    // La franja bloqueante (hub#374): la superficie de las pantallas donde no está la checklist.
    // Dice la CONSECUENCIA, no la gravedad — ⛔ significa que el runtime rechaza el documento, así
    // que eso es lo que anuncia. Nunca dice «error»: no hay nada roto, hay algo que falta.
    blocking: {
      title: 'Todavía no puedes facturar',
      body: 'No se podrá emitir ningún ticket ni factura hasta que configures esto:',
      showMissing: 'Ver qué falta',
      hideMissing: 'Ocultar',
    },
    items: {
      apps: {
        title: 'Tus apps',
        description: 'Instala al menos una app de negocio para que el TPV tenga algo que vender.',
      },
      business_identity: {
        title: 'Los datos de tu negocio',
        description: 'Razón social y NIF: sin ellos no puedes emitir una factura.',
      },
      printer: {
        title: 'Configura la impresora',
        description: 'Da de alta el dispositivo que imprime los tiques de tus clientes, para que la primera venta salga en papel.',
      },
      team: {
        title: 'Tu equipo',
        description: 'Añade a las personas que usarán el TPV, cada una con su forma de entrar.',
      },
    },
  },
  dashboard: {
    // Contextual greeting by time of day (zone 1 — header). It stands in for the BUSINESS NAME
    // while the hub has none yet, so nobody is interpolated: greeting a person here is what put an
    // account address in the `<h1>` (hub#366).
    greetingMorning: 'Buenos días',
    greetingAfternoon: 'Buenas tardes',
    greetingEvening: 'Buenas noches',
    // Fecha larga del día, formateada por el locale del navegador (p. ej. «martes, 22 de julio»).
    todayLabel: 'Hoy',
    loading: 'Cargando…',
    tabSummary: 'Resumen',
    tabActivity: 'Actividad',
    activityDate: 'Fecha',
    activitySale: 'Venta',
    activityCustomer: 'Cliente',
    activityMethod: 'Método',
    activityAmount: 'Importe',
    activityStatus: 'Estado',
    activitySearchPlaceholder: 'Buscar actividad…',
    // Status badge of an activity row; it agrees with «venta» — the row is a sale (hub#863).
    activityStatusCompleted: 'Completada',
    activityStatusPending: 'Pendiente',
    widgets: 'Widgets',
    loadingWidgets: 'Cargando widgets…',
    customizePanel: 'Personalizar panel',
    closePanel: 'Cerrar',
    presetsTitle: 'Empezar desde un preset',
    activeWidgets: 'Activos · arrastra para reordenar',
    availableWidgets: 'Disponibles',
    emptyPanel: 'Panel vacío. Pulsa ⋮ para añadir widgets.',
    noWidgets: 'Ninguna app instalada ofrece widgets todavía.',
    widgetEmpty: 'Sin datos',
    widgetError: 'No disponible',
    // Tarjeta «Mis apps» (hub#367): el lanzador del panel. El título reutiliza `topbar.apps` — el
    // mismo nombre para lo mismo en las dos superficies.
    appsAdd: 'Añadir apps',
    appsEmpty: 'Aquí aparecerán tus apps. Añade las que necesite tu negocio.',
    // hub#894 — se dice EN LUGAR de `appsEmpty` cuando la lista no se pudo cargar. Nunca afirma que
    // el hub esté vacío, y propone recargar: las apps siguen instaladas.
    appsLoadError:
      'No se han podido cargar tus apps. Recarga la página; si sigue fallando, vuelve a iniciar sesión.',
    // hub#1722 — las baldosas del esqueleto son decorativas, así que esta es la frase que lleva una
    // línea de estado oculta junto a la rejilla para quien no está mirando: en pantalla la dicen las baldosas.
    appsLoading: 'Cargando tus apps…',
    blueprintTitle: 'Configura tu negocio',
    blueprintBody: 'Carga una plantilla para tu negocio o restaura una copia para empezar.',
    blueprintCta: 'Configurar',
    // Zona 4 — lo que el hub cuenta de sí mismo. La copy de la pill vive en `system.health.*`
    // (hub#375); «Sistema conectado/desconectado» se ha ido a propósito: era un veredicto sobre
    // todo sacado de una sonda que solo sabía del equipo de la impresora.
    openSystem: 'Ver sistema',
    // hub#1197 — en móvil la rejilla se pliega a las dos filas; esta es la baldosa que lleva al
    // resto, el mismo catálogo que ya abre ＋ Añadir apps (`/apps`).
    appsViewAll: 'Ver todas las apps',
  },
  profile: {
    title: 'Mi perfil',
    subtitle: 'Tu identidad y tus preferencias personales en este negocio.',
    accountTitle: 'Datos de la cuenta',
    preferencesTitle: 'Preferencias',
    name: 'Nombre',
    firstName: 'Nombre',
    lastName: 'Apellidos',
    email: 'Correo electrónico',
    role: 'Rol en este negocio',
    accountType: 'Tipo de cuenta',
    cloudAccount: 'Cuenta de erplora.com',
    cloudAccountError: 'No se pudo abrir la página de tu cuenta en el navegador. Entra en erplora.com para gestionarla.',
    localAccount: 'Usuario local de este negocio',
    unavailable: 'No disponible',
    defaultRole: 'Usuario',
    roleOwner: 'Propietario',
    roleAdmin: 'Administrador',
    roleManager: 'Responsable',
    roleEmployee: 'Empleado',
    language: 'Idioma',
    languageDesc: 'Se guarda para ti. Si no eliges uno, se usa el idioma del negocio.',
    appearance: 'Apariencia',
    appearanceDesc: 'Elige el modo y la paleta que prefieres.',
    useHubLanguage: 'Usar el idioma del negocio',
    useHubAppearance: 'Usar la apariencia del negocio',
    changePhoto: 'Cambiar foto',
    removePhoto: 'Quitar',
    saveProfile: 'Guardar mis datos',
    saving: 'Guardando…',
    saved: 'Perfil guardado',
    saveError: 'No se pudo guardar el perfil',
    loadError: 'No se pudo cargar el perfil',
    photoSaved: 'Foto actualizada',
    photoError: 'No se pudo guardar la foto. Usa JPG, PNG o WebP de hasta 2 MB.',
    manageTitle: 'Gestión de la cuenta',
    manageCloud:
      'Puedes editar aquí tus propios datos. Sigue siendo tu cuenta de erplora.com.',
    manageLocal:
      'Esta identidad pertenece solo a este negocio. Aquí no se conocen ni se muestran otros negocios.',
    manageInSaas: 'Gestionar cuenta en erplora.com',
    pinTitle: 'PIN',
    pinDesc: 'El PIN con el que entras en la caja. Cámbialo cuando quieras — no hace falta que lo haga nadie más.',
    pinSetupDesc: 'Todavía no tienes un PIN. Establece uno para poder entrar también desde la caja.',
    currentPin: 'PIN actual',
    newPin: 'PIN nuevo',
    confirmPin: 'Repite el PIN nuevo',
    changePin: 'Cambiar PIN',
    setPin: 'Establecer PIN',
    pinSaved: 'PIN actualizado',
    pinMismatch: 'Los dos PIN no coinciden.',
  },
  // hub#358 — «este dispositivo»: si esta terminal pregunta quién la está usando. El texto dice la
  // CONSECUENCIA de cada modo, nunca su nombre técnico: el dueño de un bar tiene que poder deducir,
  // solo de la frase, que uno de los dos significa «quien coja esto ya ha entrado como yo».
  deviceMode: {
    title: 'Este dispositivo',
    intro: 'Cómo pregunta este dispositivo quién lo está usando. Cada dispositivo del negocio se decide por separado.',
    shared: 'Compartido — una caja o tablet que usan varias personas',
    sharedConsequence:
      'Pide PIN al entrar y la olvida al acabar el turno, así que cada venta queda atribuida a quien la hizo.',
    personal: 'Personal — un dispositivo que solo usas tú',
    personalConsequence:
      'La sesión se queda abierta y nunca pide PIN: quien lo coja ya eres tú. Elígelo solo para un dispositivo que no toca nadie más, y vuelve a cambiarlo si lo pierdes.',
    adminOnly: 'Solo un administrador puede cambiar cómo entra la gente en este dispositivo.',
    saveError: 'No se pudo cambiar este dispositivo. Comprueba la conexión e inténtalo de nuevo.',
  },
  devices: {
    // hub#1697 — ver el comentario gemelo en `en.ts`.
    errors: {
      device_name_too_long: 'Ese nombre es demasiado largo. Ponle uno más corto y vuelve a guardar.',
      device_not_found: 'Ese dispositivo ya no está registrado aquí. Actualiza la lista.',
      unauthorized: 'Tu sesión ha caducado. Vuelve a entrar e inténtalo otra vez.',
      forbidden: 'Solo el propietario o un administrador puede gestionar los dispositivos.',
    },
    title: 'Dispositivos',
    intro:
      'Los dispositivos en los que alguien ha entrado. Si pierdes uno, quítalo aquí: su sesión se cierra al momento y deja de poder entrar con PIN.',
    thisDevice: 'El que estás usando',
    unnamed: 'Dispositivo sin nombre',
    rename: 'Ponerle nombre',
    nameLabel: 'Ponle el nombre del sitio: Barra, Cocina, Portátil del despacho',
    save: 'Guardar',
    lastSignedInBy: 'La última vez entró {who}',
    renameError: 'No se pudo cambiar el nombre. Comprueba la conexión e inténtalo de nuevo.',
    empty: 'Todavía no ha entrado nadie desde ningún dispositivo.',
    inUse: 'En uso ahora mismo',
    lastUsed: 'Se usó por última vez {when}',
    neverUsed: 'Añadido {when}, sin usar desde entonces',
    openUntil: 'Su sesión sigue abierta hasta {when}',
    modeShared: 'Pide PIN',
    modePersonal: 'Se queda abierto',
    revoke: 'Quitar este dispositivo',
    cancel: 'Dejarlo',
    confirm: '¿Quitar este dispositivo?',
    confirmCurrent:
      'Es el dispositivo que estás usando: al quitarlo se cerrará tu sesión y tendrás que volver a entrar.',
    consequence:
      'Su sesión se cierra al momento. Para volver a usarlo, alguien tiene que entrar en él con su cuenta.',
    adminOnly: 'Solo un administrador puede quitar un dispositivo.',
    loadError: 'No se pudieron cargar los dispositivos. Comprueba la conexión e inténtalo de nuevo.',
    revokeError: 'No se pudo quitar este dispositivo. Comprueba la conexión e inténtalo de nuevo.',
    // hub#2215 — quitar de golpe los dispositivos que ya nadie usa.
    pruneStale:
      'Quitar el dispositivo sin usar desde hace 30 días | Quitar los {n} dispositivos sin usar desde hace 30 días',
    pruneConfirm:
      '¿Quitar 1 dispositivo que nadie usa desde hace 30 días? | ¿Quitar {n} dispositivos que nadie usa desde hace 30 días?',
    pruneConsequence:
      'Dejan de aparecer aquí y, para volver a usar uno, alguien tendrá que entrar en él con su cuenta. Los usados en los últimos 30 días y el que estás usando se quedan.',
    pruneAction: 'Quitar',
    pruneError: 'No se pudieron quitar los dispositivos sin usar. Comprueba la conexión y vuelve a intentarlo.',
  },
  pinPolicy: {
    lengthTitle: 'Dígitos del PIN',
    lengthDigits: '{n} dígitos',
    lengthConsequence: 'Todo el mundo teclea el mismo número de dígitos, que es lo que permite que el teclado entre al último en vez de pedirte confirmar. Los PIN que ya se usan siguen funcionando hasta que su dueño los cambie.',
    title: 'Pinpad',
    intro:
      'Si se muestra el pinpad y se pregunta quién está en la caja. Vale para todo el negocio: además, cada dispositivo decide por su cuenta, arriba.',
    showPinpad: 'Mostrar pinpad',
    onConsequence:
      'El personal elige su nombre y teclea su PIN, así que cada venta lleva el nombre de quien la hizo.',
    offConsequence:
      'Nadie teclea un PIN. Quien abriera la caja por la mañana es el nombre de todas las ventas hasta que acabe el turno, las hiciera quien las hiciera: no podrás saber quién vendió qué ni quién hizo un descuento. El personal que solo tiene PIN y no tiene cuenta no podrá entrar.',
    idleTitle: 'Volver a preguntar tras inactividad',
    idleMinutes: '{n} min',
    idleUntilSignOut: 'Hasta cerrar sesión',
    idleMinutesConsequence:
      'Una caja que nadie toca durante {n} minuto cierra la sesión y muestra el pinpad: la siguiente venta lleva el nombre de la siguiente persona. | Una caja que nadie toca durante {n} minutos cierra la sesión y muestra el pinpad: la siguiente venta lleva el nombre de la siguiente persona.',
    idleUntilSignOutConsequence:
      'La caja no se bloquea sola por inactividad: la sesión sigue abierta hasta que quien entró cierre sesión, o hasta que caduque por el dispositivo.',
    adminOnly: 'Solo un administrador puede cambiar si se pregunta.',
    saveError: 'No se pudo cambiar. Comprueba la conexión e inténtalo de nuevo.',
  },
  // Ver la nota del bloque equivalente en `en.ts`.
  settings: {
    hubWide: 'Ajustes generales',
    currency: 'Moneda',
    currencyDesc: 'Moneda de tu negocio para precios y totales',
    hubLanguage: 'Idioma del negocio',
    hubLanguageDesc: 'Idioma por defecto para quien no haya elegido el suyo',
    saved: 'Ajustes guardados',
    saveError: 'No se pudieron guardar los ajustes',
    saveRefused: {
      demo_fiscal_environment_locked:
        'Una demo se queda siempre en el entorno de pruebas de la AEAT. Crea tu propio negocio en erplora.com para remitir de verdad.',
      business_tax_id_frozen:
        'El NIF ya no se puede cambiar: este negocio ya ha emitido con él.',
      hub_country_frozen:
        'El país ya no se puede cambiar: este negocio ya declara con sus normas fiscales. Escríbenos si el negocio se ha mudado de verdad.',
      // hub#1088: una por cada motivo de rechazo del NIF — la letra/dígito de control que no
      // cuadra se reescribe; «esto no tiene forma de NIF» es otra conversación.
      invalid_tax_id_type: 'El NIF debe ser un texto.',
      tax_id_too_long:
        'El NIF es demasiado largo: el límite de la AEAT es de 20 caracteres.',
      invalid_tax_id_format: 'Eso no tiene forma de NIF: DNI (12345678Z), NIE (X1234567L), CIF (B12345674) o identificador extranjero con prefijo de país (FR123456789).',
      invalid_tax_id_control: 'La letra o dígito de control del NIF no es el que corresponde: revísalo y vuelve a escribirlo.',
    },
    timezone: 'Zona horaria',
    timezoneDesc: 'Zona horaria para fechas y horarios',
    timezoneAuto: 'Automática (según el país)',
    timezoneAutoNow: 'Automática · {zone}, {time}',
    timezoneOptionNow: '{zone} · {time}',
    country: 'País',
    countryDesc: 'País para la configuración regional',
    countrySpain: 'España',
    countryPortugal: 'Portugal',
    theme: 'Tema',
    themeDesc: 'Modo de apariencia de la interfaz',
    themeSystem: 'Sistema (auto)',
    themeLight: 'Claro',
    themeDark: 'Oscuro',
    themePalette: 'Paleta de tema',
    paletteFollowHub: 'Usar la paleta del negocio',
    hubPalette: 'Paleta por defecto',
    hubPaletteDesc: 'La paleta que ven los usuarios que no han elegido una propia',
    saveChanges: 'Guardar cambios',
    showApiDocs: 'Mostrar documentación de la API',
    showApiDocsDesc: 'Añade una página interna con la documentación de la API (Swagger) para integraciones',
    hardware: 'Hardware',
    hardwareTitle: 'Acceso a recursos locales y de red',
    hardwareDesc: 'Impresoras, escáneres y otros dispositivos de este equipo o de su red',
    hardwareReady: 'Disponible aquí',
    hardwareAppOnly: 'Solo desde la app instalada',
    // «Arrancar al iniciar sesión» (ADR-0204 §7, hub#389). Solo app de escritorio.
    startOnLogin: 'Arrancar al iniciar sesión',
    startOnLoginDesc:
      'Abre ERPlora al iniciar sesión en este ordenador, para que los tiques siempre tengan dónde imprimirse',
    startOnLoginError: 'No se pudo cambiar el ajuste de arranque al iniciar sesión',
    disabled: 'Desactivado',
    fiscalIdentity: 'Datos del negocio',
    fiscalIdentityDesc: 'Identidad del obligado tributario (la usan las facturas y las apps fiscales).',
    fiscalNif: 'Identificador fiscal (NIF/CIF/VAT)',
    fiscalName: 'Razón social / nombre',
    businessStreet: 'Vía pública',
    businessStreetNumber: 'Número',
    businessPostalCode: 'Código postal',
    businessCity: 'Municipio',
    businessAddressLegacy: 'Dirección actual: {address}. Rellena los campos de arriba para sustituirla.',
    fiscalAddress: 'Dirección fiscal',
    shareWithErplora: 'Usar estos datos también para mi factura de ERPlora',
    shareWithErploraDesc: 'Al guardar, ERPlora también pone tu razón social, NIF y dirección en sus facturas hacia ti. Déjala sin marcar si a ERPlora le paga otra persona por este negocio, como tu gestoría. ERPlora siempre sabe quién es el negocio, porque lo necesita para presentar ante Hacienda.',
    shareWithErploraError: 'No se han podido compartir los datos con ERPlora.',
    defaultVat: 'IVA por defecto',
    defaultVatDesc: 'Tipo aplicado a productos nuevos',
    vatGeneral: '21% (general)',
    vatReduced: '10% (reducido)',
    vatSuperReduced: '4% (superreducido)',
    taxRegime: 'Régimen fiscal',
    taxRegimeDesc: 'Régimen de facturación',
    regimeGeneral: 'Régimen general',
    regimeEquivalence: 'Recargo de equivalencia',
    receiptTemplate: 'Impresoras y tique',
    receiptTemplateDesc: 'Da de alta tu impresora y configura el tique impreso y digital',
    receiptTemplateMissing: 'Instala la app Impresión para dar de alta tu impresora y configurar el tique',
    tabHub: 'General',
    tabBusiness: 'Negocio',
    tabTickets: 'Tiques',
    tabPermissions: 'Permisos',
    tabData: 'Datos y copias',
    dataImport: 'Importar',
    dataExport: 'Exportar',
    // Reset del hub (ADR-0170).
    dataReset: 'Restablecer',
    resetIntro:
      'Borra definitivamente los datos que marques. No se puede deshacer: si dudas, expórtate antes una copia.',
    resetExportFirst: 'Exportar una copia antes',
    resetImportsTitle: 'Deshacer una importación',
    resetImportsHint: 'Quita solo lo que trajo ese blueprint. Lo que hayas creado después se conserva.',
    resetSectionsTitle: 'O borrar por secciones',
    resetUndo: 'Deshacer',
    resetUndoTitle: 'Deshacer «{name}»',
    resetUndoBody:
      'Se borrará la fila que trajo este blueprint. Lo que creaste después se conserva. | Se borrarán las {n} filas que trajo este blueprint. Lo que creaste después se conserva.',
    resetUndoEdited: 'Cambiaste {areas} después de importar. Al deshacer solo se quedan tus cambios ahí: lo que este blueprint sustituyó no vuelve.',
    resetUndoNotRestored: 'En {areas} solo se han quedado tus cambios: lo que el blueprint había sustituido no ha vuelto. Revisa esa pantalla.',
    // Pluralización vue-i18n (`singular | plural`): sin ella, una sección con 1 elemento leía
    // «1 filas» (hub#765). El `n` que pasa la llamada elige la forma.
    resetRows: '{n} fila | {n} filas',
    resetSubmit: 'Restablecer el negocio',
    resetDeleted: '{n} fila borrada | {n} filas borradas',
    resetConfirmTitle: 'Esto no se puede deshacer',
    resetConfirmBody: 'Se borrará definitivamente {n} fila: | Se borrarán definitivamente {n} filas:',
    resetConfirmPlaceholder: 'nombre del negocio',
    resetCancel: 'Cancelar',
    resetConfirm: 'Borrar definitivamente',
    reset_hub_settings: 'Ajustes del negocio',
    reset_hub_users: 'Empleados',
    reset_media: 'Ficheros e imágenes',
    reset_fiscal: 'Configuración fiscal',
    reset_roles: 'Roles activos',
    reset_print_queue: 'Cola de impresión',
    permissionsTitle: 'Permisos de las apps',
    permissionsDesc: 'Concede o revoca los permisos que cada app pide (acceso a internet, certificado, impresora, notificaciones, administrar automatizaciones). Por seguridad, todo está denegado hasta que lo concedas.',
    permissionsAdminOnly: 'Solo un administrador puede cambiar los permisos.',
    permissionsNoModules: 'Ninguna app instalada pide permisos.',
    permissionsModuleNone: 'Esta app no pide permisos.',
    permissionsLoadError: 'No se pudieron cargar los permisos.',
    permissionGranted: '{cap} concedido a {app}.',
    permissionRevoked: '{cap} revocado a {app}.',
    permissionSaveError: 'No se pudo cambiar el permiso.',
    // Responsible declaration inside the product (art. 13.2 RRSIF — hub#528). The element names
    // (`NombreRazon`, `IdSistemaInformatico`…) are NOT translated: they are the ones of the
    // invoicing record and the screen exists to be read next to one.
    // hub#1174 — qué DEJA DE FUNCIONAR mientras el interruptor está apagado.
    capabilityBreaks: {
      network: 'Sin esto, la app no puede salir a internet: lo que sincroniza, envía o comprueba en línea se queda sin hacer.',
      certificate: 'Sin esto, tus facturas no se firman y no llegan a Hacienda.',
      printer: 'Sin esto, los tiques y las comandas se quedan en la cola de impresión y no sale ninguno.',
      notify: 'Sin esto, no llega ningún recordatorio ni confirmación a tus clientes por email, SMS o WhatsApp.',
      manage_flows: 'Sin esto, la app no puede crear ni editar tus automatizaciones, así que las que necesita no se ejecutan.',
      unknown: 'Sin esto, la parte de la app que necesita este permiso no funcionará.',
    },
  },
  // Print coverage (hub#800): who is printing each kind of ticket, and who is NOT.
  print: {
    coverageTitle: 'Estado de impresión',
    coverageDesc: 'Qué dispositivos están sacando cada tipo de tique ahora mismo.',
    roleReceipt: 'Tiques de venta',
    roleKitchen: 'Comandas de cocina',
    roleBar: 'Comandas de barra',
    roleLabel: 'Etiquetas',
    stalled: 'Nadie está imprimiendo esto — {n} tique en espera | Nadie está imprimiendo esto — {n} tiques en espera',
    unattended: 'El dispositivo que imprimía esto no responde',
    ready: 'Imprimiendo en {hosts}',
    hostHint: 'Abre la app de ERPlora en el equipo conectado a esta impresora.',
    coverageError: 'No se ha podido comprobar quién está imprimiendo ahora mismo.',
    ticketFailed: 'El tique NO se imprimió. Vuelve a imprimirlo desde la pantalla del tique.',
    ticketWaitingForPrinter:
      'El tique está en espera: aún no hay ninguna impresora dada de alta. Da una de alta y saldrá solo.',
    ticketNotComposed:
      'El tique no se pudo preparar y NO se imprimió. Imprímelo desde la pantalla del tique.',
    ticketWithoutFiscal:
      'El tique salió antes de que estuviera listo su QR de VeriFactu. Vuelve a imprimirlo desde la pantalla del tique para darle al cliente el completo.',
    comandaFailed:
      'No se imprimió la comanda de {station} de {label}. Revisa la impresora y avisa en {station}: la comanda está en la pantalla de cocina.',
    comandaWaitingForPrinter:
      'La comanda de {station} de {label} está en espera: aún no hay ninguna impresora dada de alta para esa estación. Da una de alta y saldrá sola.',
    stationKitchen: 'cocina',
    stationBar: 'barra',
    // hub#2171 — the system notice when a kitchen order comes in.
    comandaNotice: 'Nueva comanda',
    comandaNoticeFor: 'Nueva comanda · {label}',
    comandaNoticeLines: '{n} línea | {n} líneas',
    comandaDefaultLabel: 'sala',
  },
  // hub#2168 — system notices for a booking or cancellation that did NOT come from a till.
  appointmentNotice: {
    created: 'Nueva cita',
    createdFor: 'Nueva cita · {customer}',
    cancelled: 'Cita cancelada',
    cancelledFor: 'Cita cancelada · {customer}',
    when: '{date} a las {time}',
  },
  // hub#2303 — system notice when a bell counter goes up; {label} is the module's own counter label.
  bellNotice: {
    title: '{label} ({count})',
    body: 'Míralo en la campana para atenderlo.',
  },
  // hub#365 — this screen is the far end of the apps door, so it speaks the noun hub#367 chose:
  // «apps», never «modules». The KEYS keep saying module (`colModule`, `moduleInstalled`): they are
  // the manifest's word and renaming them would break nothing here and everything elsewhere.
  // «Conectar WhatsApp» — el bloque que el módulo de WhatsApp incrusta como <erp-whatsapp-connect> (hub#1600).
  // El dueño conecta el número del negocio desde aquí: popup de Meta, QR escaneado con la app de
  // WhatsApp Business. Los errores son frases que una persona puede accionar, por el código del SaaS.
  whatsappConnect: {
    intro: 'Conecta el número de WhatsApp de tu negocio. Iniciarás sesión con Facebook y escanearás un código QR con la app de WhatsApp Business de tu móvil.',
    connect: 'Conectar WhatsApp',
    connected: 'Conectado',
    businessApp: 'App de WhatsApp Business',
    connectedHelp: 'Los mensajes de tus clientes llegan a la Bandeja y las automatizaciones los contestan.',
    reconnectBadge: 'Hay que reconectar',
    reconnectNeeded:
      'WhatsApp ha retirado el permiso para escribir en nombre de tu negocio. Los mensajes de tus clientes no están llegando y nada de lo que contestes sale. Vuelve a conectar tu número para recuperar el canal.',
    reconnect: 'Volver a conectar WhatsApp',
    disconnect: 'Desconectar',
    disconnectConfirm: '¿Desconectar este número? Los mensajes dejarán de llegar aquí.',
    adminOnly: 'Solo un dueño o un administrador puede conectar el número de WhatsApp.',
    loading: 'Abriendo la conexión con WhatsApp…',
    connecting: 'Conectando tu número…',
    retry: 'Reintentar',
    errors: {
      cancelled: 'La conexión se canceló antes de terminar.',
      no_phone_number: 'No se añadió ningún número de teléfono. Vuelve a abrir la conexión y añade o elige un número.',
      no_business_account: 'Facebook no ha devuelto ninguna cuenta de WhatsApp Business. Inténtalo de nuevo y elige tu negocio en la ventana.',
      not_configured: 'WhatsApp todavía no está disponible en este hub. Contacta con soporte.',
      sdk_unavailable: 'No se pudo abrir la ventana de Facebook. Permite las ventanas emergentes en este sitio e inténtalo de nuevo.',
      cloud_unreachable: CLOUD_UNREACHABLE,
      unreachable: CLOUD_UNREACHABLE,
      forbidden: 'Solo un dueño o un administrador puede conectar el número de WhatsApp.',
      meta_unreachable: 'WhatsApp no responde ahora mismo. Vuelve a intentarlo en unos minutos.',
      meta_api_error: 'WhatsApp ha rechazado la conexión por un problema de nuestra parte. Contacta con soporte.',
      no_access_token: 'Facebook no ha dado el permiso para conectar. Abre de nuevo la conexión y acepta los permisos.',
      missing_code: 'La ventana de Facebook se cerró antes de terminar. Abre de nuevo la conexión y completa todos los pasos.',
      hub_not_found: 'erplora.com no reconoce este hub. Contacta con soporte.',
      number_not_found: 'Ese número ya no está conectado.',
      internal_error: 'erplora.com no ha podido terminar la conexión. Contacta con soporte si sigue pasando.',
      default: 'Algo ha fallado al conectar. Inténtalo de nuevo en un minuto.',
    },
  },
  apps: {
    searchInstalled: 'Buscar en tus apps…',
    searchCatalog: 'Buscar apps para añadir…',
    tabMine: 'Mis apps',
    // The same words as the ＋ tile on the panel (`dashboard.appsAdd`): one door, one name.
    tabCatalog: 'Añadir apps',
    tabPaid: 'De pago',
    emptyInstalled: 'Aún no tienes apps. Abre «Añadir apps» para instalar la primera.',
    loadingInstalled: 'Cargando tus apps…',
    installedLoadError:
      'No hemos podido leer tus apps. No ha habido respuesta, o esta sesión ya no es válida — vuelve a entrar si sigue pasando.',
    emptyCatalog: 'No hay apps que coincidan con tu búsqueda.',
    loadingCatalog: 'Cargando el catálogo…',
    catalogLoadError:
      'No se pudo cargar el catálogo. Revisa la conexión o el registro de este dispositivo.',
    retryCatalog: 'Reintentar',
    demoCatalogReadOnly: 'Estás viendo el catálogo real en modo demostración. Conecta un negocio real para instalar apps.',
    adminOnly: 'Puedes ver las apps, pero solo un administrador puede instalarlas, activarlas o desinstalarlas.',
    colModule: 'App',
    colVersion: 'Versión',
    colStatus: 'Estado',
    colCategory: 'Categoría',
    colDescription: 'Descripción',
    colPrice: 'Precio',
    statusActive: 'Activo',
    statusInactive: 'Inactivo',
    statusInactiveAuto: 'Inactivo (en cascada)',
    stateInstalled: 'Instalado',
    stateAvailable: 'Disponible',
    stateUnavailable: 'No disponible',
    stateNeedsNewerHub: 'Necesita ERPlora {version}',
    stateUpdateNeedsNewerHub: 'La versión {version} necesita ERPlora {floor}',
    stateInstalling: 'Instalando…',
    // hub#516: instalado, pero hay una versión más nueva publicada. Se nombra la versión — decir
    // «hay actualización» sin decir cuál es una insistencia, no una información.
    stateUpdatable: 'Actualizar a {version}',
    phaseResolving: 'Resolviendo versión…',
    phaseDownloading: 'Descargando…',
    phaseVerifying: 'Verificando integridad…',
    phaseInstalling: 'Aplicando migraciones…',
    phaseDependency: 'Dependencia {name} — {phase}',
    actionToggle: 'Activar/Desactivar',
    actionUninstall: 'Desinstalar',
    actionInstall: 'Instalar',
    actionUpdate: 'Actualizar',
    actionSeeHubUpdates: 'Ver tu versión de ERPlora y sus actualizaciones',
    actionOpen: 'Abrir',
    priceFree: 'Gratis',
    priceMonthly: '{price} €/mes',
    priceYearly: '{price} €/año',
    priceOneTime: '{price} €',
    priceOnRequest: 'Consultar',
    priceIncludedInPlan: 'Incluida en tu plan',
    alreadyInstalled: '{name} ya está instalado.',
    installing: 'Instalando {name}…',
    installSuccess: '{name} instalado correctamente.',
    // hub#1130: el cierre del plan de instalación (ADR-0060) arrastró dependencias — el dueño pidió
    // UNA app y le llegaron varias; nombrarlas en la MISMA confirmación es el reverso del `409
    // has_dependents` de hub#1101, que ya nombra lo que rompería un desinstalar.
    installSuccessWithDependencies: '{name} instalado correctamente. También se instaló: {names}.',
    installError: 'No se pudo iniciar la instalación de {name}.',
    // hub#2244: the sticky install error's two ways out.
    installRetry: 'Reintentar',
    noticeClose: 'Cerrar',
    // ADR-0060: el plan de instalación necesita módulos que el hub no tiene contratados.
    installBlocked: '{name} necesita apps que aún no tienes contratadas: {missing}. No se ha instalado nada.',
    // hub#516 — el botón de actualizar. `updateError` dice lo único que importa: el módulo NO se
    // ha quedado a medias, sigue corriendo la versión que tenía.
    updating: 'Actualizando {name}…',
    updateSuccess: '{name} actualizado: {from} → {to}.',
    updateSuccessReloading: '{name} actualizado: {from} → {to}. Recargando para usar la versión nueva…',
    updateUpToDate: '{name} ya está en la última versión.',
    updateError: 'No se pudo actualizar {name}. Sigue funcionando con la versión que tenía.',
    updateBlocked: 'La versión nueva de {name} necesita apps que aún no tienes contratadas: {missing}. No ha cambiado nada ni se ha cobrado nada.',
    updateAllOffer: '{n} app tiene una versión nueva. | {n} apps tienen una versión nueva.',
    updateAllAction: 'Actualizar todas',
    updateAllProgress: 'Actualizando {name} ({current} de {total})…',
    updateAllSummary: '{updated} de {total} app actualizada. | {updated} de {total} apps actualizadas.',
    updateAllUpToDate: 'Ya estaba en la última versión',
    updateAllRetry: 'Reintentar',
    updatesCheckFailed: 'No se ha podido comprobar si hay versiones nuevas de tus apps. Puede que no estén al día.',
    updateAllReload: 'Recargar ahora',
    updateAllDoneReloading: '{n} app actualizada. Recargando para usar la versión nueva… | {n} apps actualizadas. Recargando para usar las versiones nuevas…',
    updateAllNothingNew: 'Tus apps ya estaban en la última versión.',
    versionPickTitle: 'Elige una versión',
    versionPickBody: 'Está seleccionada la última. Elige otra solo si te lo ha pedido soporte.',
    versionPickConfirm: 'Continuar',
    versionLatest: '{version} (la última)',
    needsSubscription: '{name} necesita una suscripción. Contrátala desde tu cuenta de ERPlora, en erplora.com, y se instalará aquí.',
    deactivated: '{name} desactivado.',
    activated: '{name} activado.',
    toggleError: 'No se pudo cambiar el estado de {name}.',
    cascadeOffMsg: 'También se desactivarán (dependen de {name}):',
    cascadeOnMsg: 'También se activarán (los necesita {name}):',
    cascadeCancel: 'Cancelar',
    toggleOffTitle: 'Desactivar {name}',
    toggleOffBody: '{name} desaparece del TPV y sus pantallas dejan de abrirse. No se borra nada: al volver a activarla queda como estaba.',
    toggleOffConfirm: 'Desactivar',
    toggleOnTitle: 'Activar {name}',
    toggleOnBody: '{name} vuelve al TPV, con los datos que ya tenía.',
    toggleOnConfirm: 'Activar',
    uninstallTitle: 'Desinstalar {name}',
    uninstallBreaks: 'Estas apps necesitan {name} y dejarán de funcionar:',
    uninstallBody: 'La app dejará de estar disponible. Sus datos y archivos se conservarán para una reinstalación posterior.',
    uninstallConfirm: 'Desinstalar',
    uninstalled: '{name} desinstalado.',
    uninstallError: 'No se pudo desinstalar {name}.',
    uninstallBlocked: '{name} no se ha desinstalado: estas apps lo necesitan — {apps}. Desinstálalas antes.',
    moduleInstalledNamed: '{name} instalado.',
    moduleInstalled: 'App instalada.',
    consentTitle: 'Permisos solicitados',
    consentIntro: 'Esta app solicita estos permisos. Podrás revisarlos después en Ajustes → Permisos.',
    consentInstallGrant: 'Instalar y conceder',
    consentCancel: 'Cancelar',
    installedButNoPermissions: '«{name}» se instaló, pero no se pudieron conceder sus permisos. Sin ellos no funcionará: actívalos en Ajustes → Permisos.',
    goToPermissions: 'Ir a Permisos',
    publicationRetired: 'Retirada',
    retiredNotice: 'Ya no están en el catálogo: {apps}. Aquí siguen funcionando y siguen recibiendo actualizaciones — simplemente ya no se ofrecen, así que no las encontrarás para instalarlas en otro sitio.',
  },
  employees: {
    searchEmployee: 'Buscar usuario…',
    searchRole: 'Buscar rol…',
    tabStaff: 'Personal',
    tabRoles: 'Roles',
    tabApiKeys: 'API keys',
    tabApprovals: 'Aprobaciones',
    colEmployee: 'Usuario',
    colEmail: 'Email',
    colRole: 'Rol',
    colAccess: 'Acceso',
    // hub#463 — esta dirección parece correcta y no administra nada: su baja no revoca ninguna
    // membresía y su próximo login aterriza en otra fila. Cada motivo nombra la SALIDA, porque son
    // decisiones distintas y solo una persona puede tomarlas.
    accessEmailConflict: {
      badge: 'Hay que decidir',
      another_row_answers_for_it:
        'Otra persona ya entra con esta dirección, así que dar de baja a esta no revoca nada. Cambia el email de una de las dos.',
      two_profiles_claim_it:
        'Dos personas tienen esta dirección y nada dice cuál es. Dar de baja a esta no revoca nada. Quita la duplicada, o dale a una su propia dirección.',
    },
    colStatus: 'Estado',
    colCreatedAt: 'Alta',
    colMembers: 'Miembros',
    colPermissions: 'Permisos',
    actionEdit: 'Editar',
    actionDeactivate: 'Dar de baja',
    access: {
      pin: 'PIN local',
      pin_badge: 'PIN + placa',
      badge: 'Placa',
      cloud: 'Cuenta online',
      // Existe como persona del negocio, pero no puede iniciar sesión en el Hub.
      none: 'Sin acceso',
    },
    roles: {
      owner: 'Propietario',
      admin: 'Administrador',
      manager: 'Encargado',
      employee: 'Empleado',
      cashier: 'Cajero',
    },
    emptyStaff: 'Aún no hay nadie más en este Hub.',
    emptyRoles: 'Aún no hay roles disponibles.',
    loadErrorTitle: 'No se pudo cargar el personal',
    loadErrorBody: 'El Hub no respondió con la lista de usuarios. Vuelve a intentarlo.',
    retry: 'Reintentar',
    saveError: 'No se pudieron guardar los cambios.',
    created: 'Usuario creado.',
    updated: 'Usuario actualizado.',
    deactivated: 'Usuario dado de baja.',
    deleteError: 'No se pudo dar de baja al usuario.',
    deactivateTitle: 'Dar de baja',
    deactivateBody: 'Vas a dar de baja a «{name}». Perderá el acceso al Hub, pero su historial se conserva.',
    deactivateBlocked: 'No puedes darte de baja a ti mismo ni dejar el Hub sin ningún administrador.',
    ownerRowBlocked: 'La ficha del dueño de la cuenta solo la cambia él. Para traspasar el negocio, transfiere la cuenta en ERPlora.',
    active: 'Activo',
    inactive: 'De baja',
  },
  // Catálogo de roles (hub#352/hub#353): roles base ∪ los que declaran los módulos instalados ∪
  // los que alguien todavía lleva. El administrador enciende los que su negocio necesita.
  roleCatalog: {
    intro:
      'Estos son los roles que este Hub puede repartir. Los básicos están siempre; los que trae una app los enciendes tú cuando tu negocio los necesita.',
    colSource: 'Viene de',
    colActive: 'Disponible',
    sourceCore: 'Básico',
    sourceModule: '{module}',
    sourceInUse: 'App desinstalada',
    alwaysOn: 'Siempre disponible',
    // Va DENTRO de la celda, al lado del interruptor: tiene que caber en una línea.
    notDeclared: 'Ninguna app lo trae',
    adminOnly: 'Solo un administrador puede encender o apagar roles.',
    activated: 'Ya puedes asignar «{role}».',
    deactivated: 'Ya no se puede asignar «{role}».',
    toggleError: 'No se pudo cambiar «{role}».',
    loadError: 'No se pudo cargar el catálogo de roles.',
  },
  apiKeys: {
    // hub#1697 + hub#1700 — ver el comentario gemelo en `en.ts`.
    errors: {
      not_found: 'Esa clave ya no existe. Actualiza la lista y vuelve a intentarlo.',
      rate_limited: 'Demasiados intentos seguidos. Espera un momento y vuelve a intentarlo.',
      unauthorized: 'Tu sesión ha caducado. Vuelve a entrar e inténtalo otra vez.',
      forbidden: 'Solo el propietario o un administrador puede gestionar las claves de API.',
      api_key: {
        system_key: 'Esta clave la emite ERPlora para sí misma. No se puede rotar ni borrar.',
      },
    },
    // Lista
    searchKey: 'Buscar API key…',
    empty: 'Aún no hay API keys. Crea una para que un sistema externo pueda leer o escribir datos del Hub.',
    loadError: 'No se pudieron cargar tus claves de API. Vuelve a intentarlo en un momento.',
    newKey: 'Nueva API key',
    colName: 'Nombre',
    colPrefix: 'Token',
    colScope: 'Permisos',
    colStatus: 'Estado',
    colCreated: 'Creada',
    colLastUsed: 'Último uso',
    colRateLimit: 'Límite',
    colActions: 'Acciones',
    never: 'Nunca',
    statusActive: 'Activa',
    statusRevoked: 'Revocada',
    actionRotate: 'Rotar',
    actionRevoke: 'Revocar',
    short: { read: 'L', write: 'E' },
    // Crear
    newTitle: 'Nueva API key',
    name: 'Nombre',
    namePlaceholder: 'p. ej. Gestoría — facturas',
    rateLimit: 'Peticiones por minuto',
    rateLimitHint: 'Entre 1 y 10.000. Se aplica antes de ejecutar el comando.',
    perMinute: '{count}/min',
    // hub#504 — qué puede hacer una key (mismo modelo que el rol de un usuario)
    accessTitle: 'Qué puede hacer esta key',
    accessHint: 'Los modos generales cubren todas las apps de tu negocio, también las que instales después.',
    access: {
      full: 'Acceso total',
      read_only: 'Solo lectura',
      write_only: 'Solo escritura',
      custom: 'Por app',
    },
    systemKeyBadge: 'La emite ERPlora',
    systemKeyHint: 'ERPlora lee con esta key los cambios en vivo de tu negocio. No se puede rotar ni borrar.',
    scopeTitle: 'Permisos por módulo',
    scopeHint: 'Marca lectura y/o escritura por cada módulo instalado.',
    colModule: 'Módulo',
    colRead: 'Lectura',
    colWrite: 'Escritura',
    toggleAllRead: 'Lectura en todos los módulos',
    toggleAllWrite: 'Escritura en todos los módulos',
    readOf: 'Lectura de {module}',
    writeOf: 'Escritura de {module}',
    loadingModules: 'Cargando apps instaladas…',
    noModulesTitle: 'Sin módulos instalados',
    noModulesHint: 'Instala módulos desde Apps para poder darles permiso a una key.',
    noApiModulesTitle: 'Ningún módulo expone API todavía',
    noApiModulesHint: 'Solo los módulos con operaciones de API pública pueden incluirse en una key. Ninguno de los instalados la expone aún.',
    cancel: 'Cancelar',
    create: 'Crear key',
    createError: 'No se pudo crear la API key.',
    // Secreto (una vez)
    secretTitle: 'API key creada',
    secretWarnTitle: 'Copia el token ahora',
    secretWarnBody: 'Este es el único momento en que se muestra el secreto completo. Guárdalo en un lugar seguro; no se volverá a mostrar.',
    copy: 'Copiar',
    copied: 'Copiado',
    copyError: 'No se pudo copiar al portapapeles.',
    done: 'Hecho',
    // Rotar / revocar
    rotateError: 'No se pudo rotar la API key.',
    revokeTitle: 'Revocar API key',
    revokeBody: 'Vas a revocar «{name}». Cualquier sistema que use este token dejará de tener acceso de inmediato. Esta acción no se puede deshacer.',
    revoked: '«{name}» revocada.',
    revokeError: 'No se pudo revocar la API key.',
  },
  // Aprobaciones por PIN (hub#512, ADR-0265): el registro de cada aprobación que gastó un
  // encargado, y el único sitio donde el dueño del negocio puede leerlo sin entrar por SQL a su
  // propia base de datos. Se habla de PERSONAS y de ACCIONES, nunca de la maquinaria.
  approvals: {
    intro:
      'Cada acción que necesitó el PIN de un encargado: quién la pidió, quién la autorizó y para qué se usó. Este registro se conserva mientras tu negocio esté en ERPlora, y nadie —tampoco un administrador— puede editarlo ni borrarlo.',
    search: 'Buscar por persona o acción…',
    colWhen: 'Cuándo',
    colApprovedBy: 'Autorizado por',
    colRequestedBy: 'Lo pidió',
    colAction: 'Acción',
    colLevel: 'Nivel',
    colFingerprint: 'Referencia',
    colRequestedById: 'Lo pidió (id)',
    colApprovedById: 'Autorizado por (id)',
    userGone: 'Usuario dado de baja',
    empty: 'Todavía nadie ha tenido que autorizar nada en este Hub.',
    loadError: 'No se pudo cargar el registro de aprobaciones.',
  },
  employeeForm: {
    titleEdit: 'Editar usuario',
    titleNew: 'Nuevo usuario',
    fullName: 'Nombre y apellidos',
    email: 'Email',
    role: 'Rol',
    pin: 'PIN local',
    pinHelp: '{n} dígitos. En blanco, entra con su cuenta online.',
    pinSetHelp: 'Escribe un PIN nuevo para cambiarlo; déjalo en blanco y se queda como está.',
    clearPin: 'Retirar el PIN',
    badge: 'Placa',
    badgeHelp:
      'Pasa la tarjeta y se rellena sola: no hace falta hacer clic aquí antes. También puedes teclear el número, para un llavero o una etiqueta grabada.',
    badgeSetHelp:
      'Ya lleva una placa. Pasa una tarjeta nueva para sustituirla, o déjalo en blanco y se queda como está.',
    badgeNfcHelp:
      'Acerca la tarjeta a este aparato —o pásala por el lector— y se rellena sola. También puedes teclear el número, para un llavero o una etiqueta grabada.',
    badgeNfcSetHelp:
      'Ya lleva una placa. Acerca o pasa una tarjeta nueva para sustituirla, o déjalo en blanco y se queda como está.',
    clearBadge: 'Retirar la placa',
    localUser: 'Usuario local',
    localUserHelp:
      'Trabaja en este hub solo con un PIN: sin email y sin cuenta de ERPlora. Desmárcalo para darle una cuenta más adelante, sin perder su historial.',
    localPinHelp: '{n} dígitos. Obligatorio: es cómo entra esta persona.',
    accountEmailHelp:
      'Le mandamos por email una invitación a este hub. La contraseña la elige él: tú no la ves nunca.',
    accountPinHelp:
      'Opcional: {n} dígitos. Solo si además atiende una caja compartida de este hub.',
    errors: {
      // hub#1697 — ver el comentario gemelo en `en.ts`.
      last_admin: 'No puedes dar de baja al último administrador. Nombra antes a otro dueño o administrador.',
      unauthorized: 'Tu sesión ha caducado. Vuelve a entrar e inténtalo otra vez.',
      forbidden: 'Solo el propietario o un administrador puede gestionar el personal y los roles.',
      self_deactivation: 'No puedes darte de baja a ti mismo. Pídeselo a otro administrador.',
      self_badge_enrollment: 'Nadie da de alta su propia placa. Pídeselo a otro administrador.',
      not_found: 'Esa persona ya no está en este hub. Actualiza la lista.',
      local_needs_pin: 'Un usuario local entra con un PIN: sin él, nadie podría usar esta ficha.',
      account_needs_email: 'Un usuario de cuenta entra con su cuenta de ERPlora, así que el email es obligatorio. Marca «Usuario local» para dar de alta a quien trabaja en este hub con un PIN.',
      account_role_not_grantable: 'A una cuenta de ERPlora solo se la puede invitar como admin, manager o employee. Los roles que añade un módulo son del personal local.',
      email_taken: 'Este hub ya conoce ese email. Edita a ese usuario —reincorpóralo si estaba dado de baja— en vez de invitar una segunda identidad.',
      user_limit_reached: 'Tu plan tiene todas las plazas ocupadas. Da de baja a alguien que ya no trabaje aquí, o pasa a un plan con más plazas.',
      role_above_inviter: 'No puedes repartir un rol por encima del tuyo: administrar el hub solo lo concede quien ya lo administra.',
      owner_row: 'Esta es la ficha del dueño de la cuenta y solo él puede cambiarla, PIN incluido. Para traspasar el negocio, transfiere la cuenta en ERPlora.',
      invalid_email: 'Introduce un email válido.',
      pin_length: 'El PIN debe tener {n} dígitos.',
      pin_too_simple: 'Ese PIN se adivina a la primera: evita los dígitos repetidos (1111) y las cuestas seguidas (1234).',
      pin_in_use: 'Ese PIN ya lo tiene otro usuario activo. El PIN dice quién está en la caja, así que no lo pueden compartir dos personas.',
      pin_current_mismatch: 'Ese no es tu PIN actual. Escríbelo bien para poder fijar uno nuevo.',
      local_cannot_administer: 'Un usuario local no puede administrar el hub: administrar sale de una cuenta de ERPlora, nunca de un PIN.',
      local_has_email: 'Un usuario local no lleva email. Desmarca «Usuario local» para invitarlo como usuario de cuenta.',
      name_taken: 'Este hub ya conoce a alguien con ese nombre. Edita a ese usuario —reincorpóralo si estaba dado de baja— en vez de crear una segunda identidad.',
      badge_shape: 'Una placa tiene entre 4 y 64 caracteres: letras, dígitos, «-» y «_».',
      badge_in_use: 'Esa placa ya la lleva otro usuario activo. La placa dice quién está en la caja, así que no la pueden compartir dos personas.',
      badge_without_fallback: 'La placa no puede ser su única vía de entrada: si pierde la tarjeta se queda fuera. Consérvale el PIN, dale una cuenta, o retira también la placa.',
      // hub#1214 — ver la nota en `en.ts`.
      cloud_rate_limited: 'Demasiados cambios en poco tiempo: la invitación todavía no ha salido. Espera unos minutos y vuelve a guardar — no se ha perdido nada más.',
      cloud_rejected: 'No se ha podido crear la invitación para ese email. Revisa la dirección y vuelve a intentarlo; si sigue fallando, avisa a soporte.',
      cloud_unreachable: 'No hemos podido conectar con ERPlora para enviar la invitación. El usuario queda guardado aquí: vuelve a guardar dentro de un momento.',
      not_enrolled: 'Este hub todavía no puede enviar invitaciones. El usuario queda guardado aquí; avisa a soporte para que termine de configurarlo.',
    },
    activeUser: 'Usuario activo',
    required: 'Campo obligatorio',
    invalidEmail: 'Introduce un email válido',
    loadErrorTitle: 'No se pudo abrir el usuario',
    loadErrorBody: 'El registro no está disponible o no tienes permiso para consultarlo.',
    notFound: 'Usuario no encontrado.',
    unsavedTitle: 'Cambios sin guardar',
    unsavedBody: 'Si sales ahora perderás los cambios realizados.',
    keepEditing: 'Seguir editando',
    discard: 'Descartar cambios',
    cancel: 'Cancelar',
    save: 'Guardar',
    create: 'Crear',
    saving: 'Guardando…',
  },
  system: {
    // hub#1697 — ver el comentario gemelo en `en.ts`.
    reasonUnknown: 'no se ha podido leer el motivo',
    // hub#1697 — ver el comentario gemelo en `en.ts`.
    errors: {
      not_found: 'ese mensaje ya no está en la cola; actualiza la lista.',
      invalid_payload: 'a ese mensaje le faltan los datos que necesita para volver a enviarse.',
      flow: {
        release_revoked: 'se retiró el permiso que lo generó; vuelve a concederlo y lanza la automatización.',
      },
      module: {
        capability_denied: 'la app que lo generó ya no tiene permiso para hacerlo.',
      },
    },
    database: 'Base de datos',
    memory: 'Memoria',
    connections: 'Conexiones',
    // El titular de la tarjeta de la impresora, su palabra de estado y su frase vivían aquí, y
    // nombraban un proceso («Bridge») en vez de lo que hay sobre el mostrador. Ahora salen de
    // `system.health.*` (hub#375). Lo que queda abajo es el flujo de INSTALACIÓN, que sí va de un
    // programa y lo dice a propósito.
    recheck: 'Recomprobar',
    // Un producto, un nombre (hub#500). «Descargar ERPlora Bridge» y luego «instala ERPlora» eran
    // dos nombres para lo mismo, y uno de ellos era el de una app que ADR-0196 eliminó — «Bridge»
    // es jerga de plataforma, justo el lado que ADR-0254 dejó fuera de las pantallas del hub.
    downloadApp: 'Descargar la app de ERPlora',
    downloadAppHint: 'La app de ERPlora es la que habla con tus impresoras, el cajón y los escáneres. Elige tu sistema para continuar.',
    stepDownload: 'Descargar',
    stepInstall: 'Instalar',
    stepPair: 'Vincular',
    stepConfigure: 'Configurar',
    updatesCloudHint: 'Este Hub web se actualiza automáticamente durante los despliegues del servicio.',
    // Qué le hemos cambiado a este hub y desde qué versión (hub#564, ADR-0269 §3.5). Actualizamos
    // sin preguntar, así que lo mínimo que le debemos es que pueda SABER qué le cambió. Cada frase
    // nombra una app como él la conoce y una versión que puede comparar — nunca un digest, nunca
    // «la imagen», y nunca un changelog inventado.
    updateHistory: 'Qué te hemos actualizado',
    updatesRunning: 'Vas por la {version}',
    noUpdates: 'No te hemos cambiado nada',
    noUpdatesHint: 'No hemos actualizado nada en este hub últimamente. Cuando lo hagamos, aparecerá aquí.',
    today: 'Hoy',
    yesterday: 'Ayer',
    // Una vuelta atrás es una entrada más y lo dice con esas palabras: a qué versión volvió. El
    // error que la causó no se enseña a propósito — está escrito para nosotros, no para quien abre
    // la tienda.
    rolledBackTo: 'Volvió a la {version}: la nueva no arrancó',
    updateLost: 'Esta app no está funcionando: estamos en ello',
    documents: 'Documentos',
    noDocuments: 'Sin documentos',
    noDocumentsBucket: 'El bucket de almacenamiento de este hub está vacío.',
    searchDocument: 'Buscar documento…',
    loadErrorTitle: 'No se pudo consultar el sistema',
    loadErrorBody: 'Las métricas y los registros no están disponibles ahora. Puedes volver a intentarlo.',
    retry: 'Reintentar',
    eventLog: 'Registro de eventos',
    noEvents: 'Sin eventos',
    noEventsHint: 'El runtime no ha reportado eventos recientes.',
    searchEvent: 'Buscar evento…',
    tabResources: 'Recursos',
    tabPlan: 'Plan y límites',
    tabUpdates: 'Actualizaciones',
    tabLogs: 'Registros',
    tabEvents: 'Eventos caídos',
    deadEvents: 'Eventos caídos',
    deadEventsHint: 'Arregla la causa (permiso, módulo caído…) y reenvía. El contenido no se edita: si la causa sigue, el evento vuelve a morir aquí.',
    deadEventNotRetryable: 'Este no se puede reenviar: la autorización que lo permitía se retiró y el destinatario ya no está en la fila. Vuelve a conceder el permiso y relanza el flujo.',
    noDeadEvents: 'Todo en orden',
    noDeadEventsHint: 'No hay eventos caídos. La cola de eventos vive en la base de datos: un reinicio nunca la pierde.',
    deadEventsLoadError: 'No se pudo cargar la cola de eventos caídos. Comprueba la conexión y reintenta.',
    attempts: 'intentos',
    retryAll: 'Reenviar todos',
    retryDone: 'Evento reenviado al relay.',
    retryAllDone: '{count} evento reenviado al relay. | {count} eventos reenviados al relay.',
    retryFailed: 'No se pudo reenviar: {reason}',
    discardDone: 'Evento descartado (se conserva para auditoría).',
    discardFailed: 'No se pudo descartar: {reason}',
    discardConfirm: '¿Descartar este evento para siempre? La fila se conserva (auditable), pero el relay no volverá a entregarla. Úsalo solo si el evento no debe registrarse.',
    resourcesCloud: 'Recursos en la nube',
    resourcesSystem: 'Recursos del sistema',
    sourceCloud: 'Nube',
    // Selector de rango de las series de uso (saas#1511). El contrato para en 3 días a propósito.
    usageRange3h: '3 h',
    usageRange24h: '24 h',
    usageRange3d: '3 días',
    usageRangeLabel3h: 'Últimas 3 horas',
    usageRangeLabel24h: 'Últimas 24 horas',
    usageRangeLabel3d: 'Últimos 3 días',
    // Una métrica cerca del límite del plan o por encima (hub#1922): la frase la pone el hub.
    usageNearLimit: 'Al {pct} % del límite de tu plan.',
    usageOverLimit: 'Al {pct} % del límite de tu plan: el hub puede ir más lento.',
    planPressure: 'Tu plan se está quedando corto de recursos. Con un plan mayor este hub tiene más margen.',
    databaseShared: 'Base de datos compartida',
    colTime: 'Hora',
    colLevel: 'Nivel',
    colEvent: 'Evento',
    toastDownloadingApp: 'Descargando ERPlora para {os}…',
    // Lo que el hub cuenta de sí mismo, al que lleva el bar (hub#375). Cada frase nombra algo que
    // esa persona reconoce —la impresora— y, cuando hay algo que hacer, qué hacer. El tercer estado
    // es el honesto: no hemos podido comprobarlo. Nunca se disfraza de «va bien».
    health: {
      printerTitle: 'Tu impresora',
      printerReady: 'Impresora lista',
      printerReadyDetail: 'Los tiques salen solos al cobrar.',
      printerOffline: 'Impresora sin conectar',
      printerOfflineDetail:
        'Puedes seguir cobrando: el tique sale en esta pantalla y lo imprimes desde aquí.',
      printerAction: 'Configurar la impresión',
      printerUnknown: 'No hemos podido comprobar la impresora',
      printerUnknownDetail:
        'No sabemos si está conectada; no afecta a nada más. Volveremos a comprobarlo solos.',
      // hub#1629 — WhatsApp que se cae solo (permiso caducado, revocado por Meta, desvinculado).
      whatsappDown: 'WhatsApp ha dejado de funcionar',
      whatsappDownDetail:
        'No entran los mensajes de los clientes ni salen tus respuestas hasta que lo vuelvas a conectar.',
      whatsappAction: 'Volver a conectar WhatsApp',
      notMeasured: 'No hemos podido leerlo',
    },
    // hub#1886 — ver el comentario gemelo en `en.ts`.
    openDeviceSettings: 'Abrir los ajustes',
    notices: {
      primerHeader: 'Deja que te avisemos',
      primerMessage:
        'Cuando algo necesite tu atención podemos avisarte, aunque nadie esté mirando esta pantalla. Tu dispositivo te lo preguntará a continuación.',
      primerLater: 'Ahora no',
      primerAllow: 'Activar los avisos',
      blockedTitle: 'Los avisos están desactivados',
      blockedDetail:
        'Este dispositivo no te avisará cuando algo necesite tu atención. Actívalos y lo dirá en voz alta, aunque nadie esté mirando la pantalla.',
      blockedAction: 'Activar los avisos',
      blockedInSettings:
        'Tu dispositivo no ha vuelto a preguntar. Entra en sus ajustes, busca ERPlora y activa sus notificaciones.',
      turnedOn: 'Listo: este dispositivo te avisará cuando algo necesite tu atención.',
    },
  },
  planLimits: {
    currentPlan: 'Plan actual',
    unknownPlan: 'Desconocido',
    healthy: 'Dentro del límite',
    nearLimit: 'Cerca del límite',
    memory: 'Memoria (RAM)',
    cpu: 'CPU',
    database: 'Base de datos',
    devices: 'Dispositivos',
    users: 'Personas',
    na: 'n/d',
    naHint: 'No disponible en este equipo',
    capped: 'Límite del plan',
    unlimited: 'Ilimitado',
    usedOfLimit: '{used} de {limit}',
    usedNoLimit: '{used} en uso',
    coresOf: '{used} de {limit} vCPU',
    cores: '{used} núcleos',
    dbNoQuota: 'Sin cuota de plan',
    activeSessions: '{n} sesión activa | {n} sesiones activas',
    activeUsers: '{n} persona activa | {n} personas activas',
    liveNote: 'En vivo — se actualiza cada pocos segundos mientras esta página está abierta.',
    loadErrorTitle: 'Las métricas de recursos no están disponibles',
    loadErrorBody: 'El Hub no ha podido informar de su uso de recursos ahora mismo. Puedes reintentarlo.',
    retry: 'Reintentar',
    upgradeTitle: 'Te estás quedando sin margen en tu plan',
    upgradeMemory: 'Este hub está cerca de su límite de memoria. Con más margen funcionaría con soltura.',
    upgradeDatabase: 'Tu base de datos está cerca del límite de tu plan.',
    upgradeDevices: 'Estás usando todos los dispositivos que permite tu plan.',
    upgradeUsers: 'Tu plan tiene todas las plazas ocupadas, así que no puedes añadir a nadie más.',
    upgradeWhere: 'Los planes se gestionan desde tu cuenta de ERPlora, en erplora.com.',
  },
  billing: {
    invoices: 'Facturas',
    subscriptions: 'Suscripciones',
    payments: 'Pagos',
    colInvoice: 'Factura',
    colDate: 'Fecha',
    colDueDate: 'Vencimiento',
    colAmount: 'Importe',
    colStatus: 'Estado',
    colSubscription: 'Suscripción',
    colPrice: 'Precio',
    colRenews: 'Renueva',
    downloadInvoiceAria: 'Descargar {number}',
    issuedOn: 'Emitida {date}',
    duesOn: 'Vence {date}',
    download: 'Descargar',
    noInvoices: 'No hay facturas',
    noSubscriptions: 'No hay suscripciones activas',
    month: 'mes',
    ends: 'Finaliza',
    renews: 'Renueva',
    paymentsPortalNotice: 'Los métodos de pago se gestionan desde tu cuenta de ERPlora, en erplora.com.',
    managePlanHint: 'Los cambios de plan se gestionan desde tu cuenta de ERPlora, en erplora.com.',
    cloudAuthTitle: 'Consulta la facturación en tu cuenta de ERPlora',
    cloudAuthBody: 'Tu sesión local sigue activa. Las facturas y suscripciones requieren la sesión de tu cuenta online en erplora.com.',
    loadErrorTitle: 'No pudimos cargar la facturación',
    loadErrorBody: 'Comprueba la conexión e inténtalo de nuevo. Puedes seguir utilizando el Hub.',
    retry: 'Reintentar',
    statusDraft: 'Borrador',
    statusOpen: 'Abierta',
    statusPaid: 'Pagada',
    statusVoid: 'Anulada',
    statusUncollectible: 'Incobrable',
  },
  // hub#846 — the shell's ONE reaction when the RUNTIME says this session is no longer valid
  // (expired, or displaced by a sign-in on another device): explain it, instead of screens
  // quietly emptying into «no data» or a «Retry» that can never help.
  auth: {
    sessionEnded:
      'Tu sesión ha terminado: caducó o se abrió en otro dispositivo. Vuelve a entrar.',
  },
  login: {
    logoAlt: 'Logotipo del negocio',
    toggleTheme: 'Cambiar tema',
    subtitleSetup: 'Crea tu PIN de acceso',
    subtitlePin: 'Introduce tu PIN',
    subtitleEmail: 'Entra en tu negocio',
    tabPin: 'PIN',
    tabEmail: 'Email',
    emailLabel: 'Email',
    emailPlaceholder: "tu{'@'}empresa.com",
    passwordLabel: 'Contraseña',
    trustDevice: 'Confiar en este dispositivo',
    trustInfoAria: 'Más información sobre dispositivos de confianza',
    // hub#358: sustituye a la casilla «confiar en este dispositivo» cuando un administrador marcó
    // el dispositivo como personal. Dice la CONSECUENCIA (la sesión se queda abierta) —lo que
    // importa si el dispositivo se pierde— y dónde vive la decisión.
    personalDeviceNote:
      'Este dispositivo está configurado como personal: la sesión se queda abierta y nunca pide PIN. Un administrador puede cambiarlo en Ajustes › General.',
    popoverTitle: 'Acceso por PIN',
    popoverBody: 'Marca esta casilla para poder entrar con un <strong>PIN</strong> en este dispositivo la próxima vez, sin escribir email y contraseña. Si no la marcas, siempre tendrás que iniciar sesión con email.',
    signIn: 'Entrar',
    usePinInstead: 'Usar PIN en su lugar',
    chooseUser: 'Elige tu usuario',
    signInWithEmail: 'Iniciar sesión con email',
    changeUser: 'Cambiar usuario',
    pinIncorrect: 'PIN incorrecto',
    pinTooManyAttempts:
      'Demasiados intentos fallidos. Espera {minutes} minuto y vuelve a intentarlo. | Demasiados intentos fallidos. Espera {minutes} minutos y vuelve a intentarlo.',
    pinTooManyAttemptsNoWait: 'Demasiados intentos fallidos. Espera unos minutos y vuelve a intentarlo.',
    orSwipeBadge: '…o pasa tu placa: no hace falta elegir tu nombre antes.',
    badgeRejected: 'Esa placa no abre nada aquí. Entra con tu PIN o pídeselo a un administrador.',
    // hub#330. Sustituye a «PIN incorrecto» cuando lo que se rechazó fue el dispositivo, no los
    // dígitos. Decirle «PIN incorrecto» a quien lo ha escrito bien es la peor respuesta posible: lo
    // vuelve a teclear, y nada en pantalla nombra el gesto que lo arregla.
    deviceNotEnrolled:
      'En este dispositivo todavía no funciona el PIN. Entra una vez con tu cuenta aquí y a partir de entonces sí funcionará.',
    // El otro rechazo, y necesita sus propias palabras: este navegador no guarda nada entre cargas
    // (ventana privada, o datos del sitio desactivados), así que entrar con la cuenta no serviría —
    // la próxima visita volvería a ser un desconocido.
    deviceUnidentified:
      'Este navegador no puede recordar qué dispositivo es, así que aquí no se puede usar un PIN. Entra con tu cuenta, o permite que este sitio guarde datos y vuelve a intentarlo.',
    // ADR-0154: se muestra cuando la sesión de este dispositivo fue desalojada por un login en
    // otro dispositivo (plan de un solo dispositivo activo). Cableado desde hub#1801: el runtime
    // nombra el motivo en el 401 de la puerta que sondea el shell, `main.ts` lo trae en la query y
    // esta pantalla lo pinta. Antes, al desalojado se le devolvía al login sin una palabra, que se
    // lee como una caída del hub y acaba en una llamada a soporte.
    sessionTakenOver: 'Sesión abierta en otro dispositivo',
    // El CUERPO dice lo que el título no puede: cuál es la regla (es el plan, no un fallo suyo) y
    // qué hacer. Se ofrecen los dos gestos, y primero el que no cuesta nada.
    sessionTakenOverBody:
      'Tu plan cubre un dispositivo a la vez, así que al entrar en otro se cerró la sesión de este. Vuelve a entrar para usarlo aquí, o amplía los dispositivos de tu plan.',
    // hub#2152 — the pass from the ERPlora panel could not be redeemed; the login still works.
    courierFailed: 'No se pudo entrar desde el panel de ERPlora',
    courierFailedBody:
      'Inicia sesión aquí para continuar.',
    setupChoosePin: 'Elige un PIN de {n} dígitos',
    setupConfirmPin: 'Confirma tu PIN',
    setupMismatch: 'Los PIN no coinciden, inténtalo de nuevo',
    setupSaveError: 'No se pudo guardar el PIN. Vuelve a intentarlo.',
    setupPinTooSimple: 'Ese PIN es demasiado fácil de adivinar: evita dígitos repetidos (1111) y secuencias (1234).',
    footerTrustedDevice: 'dispositivo de confianza',
    footerSecureCloud: 'conexión segura',
    errorSignIn: 'No se pudo iniciar sesión. Revisa tus credenciales o la conexión.',
    errorMachineRegistration:
      'La cuenta es válida, pero no se pudo registrar este dispositivo. Comprueba la conexión e inténtalo de nuevo.',
    requiredFields: 'Introduce un email válido y tu contraseña.',
    // ADR-0157 §8: entra con la misma cuenta de Google que usas en el portal Cloud.
    orSeparator: 'o',
    continueWithGoogle: 'Continuar con Google',
    errorGoogle: 'No se pudo iniciar sesión con Google. Inténtalo de nuevo.',
    // Login 2-pasos (2FA por OTP de email, ERPlora/saas#994): pantalla de introducción del código.
    twoFactorSubtitle: 'Verifica que eres tú',
    twoFactorHint: 'Hemos enviado un código de un solo uso a tu email. Introdúcelo para continuar.',
    twoFactorCodeLabel: 'Código de verificación',
    twoFactorCodePlaceholder: 'Código de 6 dígitos',
    twoFactorVerify: 'Verificar',
    twoFactorBack: 'Volver',
    twoFactorRequired: 'Introduce el código que enviamos a tu email.',
    twoFactorIncorrect: 'Código incorrecto o caducado. Hemos enviado un código nuevo, inténtalo de nuevo.',
    twoFactorError: 'No se pudo verificar el código. Inténtalo de nuevo.',
  },
  // hub#363 — la aprobación del encargado, pedida sin cerrar la sesión del cajero. Cada línea se
  // lee en voz alta sobre el mostrador con una cola detrás, así que dice QUÉ HACER. La guarda
  // `i18n/elevation-copy.test.ts`, incluido lo único que no puede decir nunca: CUÁL de los tres
  // rechazos fue (nombre desconocido / PIN incorrecto / usuario desactivado). El runtime responde
  // a los tres igual a propósito, para que un diálogo que abre cualquiera no sirva para averiguar
  // quién trabaja aquí.
  elevation: {
    what: 'Se aprueba: {action}',
    whatFromModule: 'Se aprueba: una acción de {app}',
    whatUnknown: 'Se aprueba: una acción que esta app no sabe nombrar',
    title: 'Hace falta una aprobación',
    lead: 'Pide a un encargado que introduzca su PIN para aprobarlo.',
    orSwipeBadge: '…o que pase su placa: no hace falta pulsar nada antes.',
    chooseApprover: '¿Quién lo aprueba?',
    approverName: 'Su nombre',
    approverNamePlaceholder: 'Escribe su nombre',
    continue: 'Continuar',
    cancel: 'Cancelar',
    changeApprover: 'Otra persona',
    // La confirmación que ve el cajero: la acción salió, y a nombre de quién queda registrada.
    // Decirlo en voz alta es la mitad de lo que mantiene honesta la trazabilidad.
    approvedBy: 'Aprobado por {name}',
    rejected: 'Esos datos no aprueban esto. Revisa el nombre y el PIN, y vuelve a intentarlo.',
    approverCannot: 'Esa persona no puede aprobarlo. Pídeselo a alguien que pueda hacerlo por sí mismo.',
    notElevable:
      'Esto no se aprueba con un PIN. Tiene que hacerlo quien dirige tu negocio, entrando con su propia cuenta.',
    notRequired: 'Esto ya no necesita aprobación. Cierra esta ventana y vuelve a intentarlo.',
    failed: 'No se pudo enviar la aprobación. Comprueba la conexión y vuelve a intentarlo.',
  },
  // hub#456 — el turno cambia en mitad de un ticket. Cada frase la lee alguien con una cola
  // delante, y lo primero que tiene que decir el texto es que pulsar aquí NO pierde la venta: sin
  // esa frase el cajero termina el ticket a nombre de otro, que es justo lo que esto viene a
  // acabar.
  userSwitch: {
    menu: 'Cambiar de usuario',
    title: 'Cambiar de usuario',
    lead: 'La venta sigue abierta. A partir de ahora queda a nombre de quien entre aquí.',
    chooseUser: '¿Quién se pone?',
    userName: 'Su nombre',
    userNamePlaceholder: 'Escribe su nombre',
    continue: 'Continuar',
    cancel: 'Cancelar',
    someoneElse: 'Otra persona',
    // La confirmación: la caja ya es de otra persona, y las siguientes líneas de esta venta van
    // con su nombre.
    nowServing: 'Ahora atiende {name}',
    rejected: 'Esos datos no han funcionado. Revisa el nombre y el PIN, y vuelve a intentarlo.',
    deviceNotEnrolled:
      'Este dispositivo todavía no está dado de alta para el PIN. Entra una vez con una cuenta de ERPlora en él y el PIN funcionará a partir de entonces.',
    deviceUnidentified: 'Este dispositivo no ha podido identificarse. Recarga la página y vuelve a intentarlo.',
  },
  activation: {
    title: 'Activación requerida',
    lead: 'Este dispositivo tiene que comprobar tus apps en erplora.com antes de poder abrir tu negocio. Conéctate a internet y vuelve a intentarlo.',
    retry: 'Reintentar',
    retryError: 'Todavía no se han podido comprobar tus apps. Comprueba la conexión o inicia sesión con tu cuenta de ERPlora.',
    logout: 'Cerrar sesión',
  },
  exportPage: {
    title: 'Exportar configuración',
    lead: 'Empaqueta cómo está configurado este negocio — y si quieres sus datos — como una plantilla que puedes cargar en otro negocio.',
    adminOnly: 'Solo un administrador puede exportar el negocio.',
    name: 'Nombre',
    language: 'Idioma',
    sections: 'Secciones',
    purposeTitle: '¿Para qué es este archivo?',
    purposeBackup: 'Copia de seguridad de este negocio',
    purposeBackupDesc: 'Copia privada para restaurar o mudar este negocio. Incluye a tu gente y sus accesos.',
    purposeTemplate: 'Plantilla para compartir',
    purposeTemplateDesc: 'Para publicar o dar a otro negocio. Nunca incluye personas, PIN ni certificados fiscales.',
    purposeLocked: 'Esta es una instalación de demostración o de pruebas, así que solo puede exportar plantillas: las personas, los PIN y los datos fiscales nunca viajan en su archivo.',
    sectionUsers: 'Usuarios',
    sectionUsersDesc: 'Empleados, roles y permisos',
    sectionSettings: 'Ajustes',
    sectionSettingsDesc: 'Ajustes del negocio: moneda, idioma, datos fiscales',
    sectionSettingsDescTemplate: 'Ajustes del negocio: país, moneda, idioma y tema. Nunca el NIF ni la razón social.',
    sectionFiscal: 'Fiscal',
    sectionFiscalDesc: 'Configuración VeriFactu y el certificado de empresa',
    fiscalWarning: 'Incluye el certificado: el .p12 viaja tal cual y conserva su contraseña. Comparte el fichero solo con gente de confianza.',
    sectionMedia: 'Imágenes y media',
    sectionMediaDesc: 'Ficheros de la carpeta media',
    modules: 'Apps',
    modulesLead: 'Elige qué apps instaladas registra la plantilla y si sus datos viajan con ella.',
    loadingModules: 'Cargando apps instaladas…',
    colModule: 'App',
    colVersion: 'Versión',
    colInclude: 'App',
    colData: 'Datos',
    includeOf: 'Incluir {app}',
    dataOf: 'Datos de {app}',
    selectAll: 'Seleccionar todo',
    deselectAll: 'Deseleccionar todo',
    export: 'Exportar',
    exporting: 'Exportando…',
    done: '{filename} descargado.',
    errorTitle: 'La exportación falló',
    // hub#765: el runtime no respondió antes del plazo. Sin timeout el spinner giraba para siempre;
    // ahora aborta y lo dice, para que el usuario pueda reintentar en vez de irse sin saber.
    timeout: 'El servidor está tardando demasiado en generar la copia. Inténtalo de nuevo en un momento.',
  },
  importPermissions: {
    title: 'Permisos de tus apps',
    intro: 'La plantilla ha instalado estas apps y necesitan tu permiso para funcionar: una plantilla no puede dártelo por ti. Puedes cambiarlo cuando quieras en Ajustes → Permisos.',
    grant: 'Dar permisos',
    granting: 'Dando permisos…',
    later: 'Ahora no',
    grantError: 'No se han podido dar los permisos de {apps}. Vuelve a intentarlo o actívalos en Ajustes → Permisos.',
  },
  importPage: {
    title: 'Importar configuración',
    lead: 'Carga una plantilla: instala las apps que falten, aplica sus datos y copia las imágenes.',
    adminOnly: 'Solo un administrador puede importar.',
    pickTitle: 'Elige qué cargar',
    pickDesc: 'Elige una plantilla publicada para tu negocio, o sube un .blueprint.zip que hayas exportado o guardado como copia.',
    pickFile: 'Elegir fichero .blueprint.zip',
    fromCloud: 'Desde erplora.com',
    fromLocal: 'Subir desde archivo',
    fromLocalDesc: 'Un .blueprint.zip exportado de otro negocio o una copia de seguridad.',
    useTemplate: 'Usar plantilla',
    searchTemplates: 'Buscar plantillas',
    colTemplate: 'Plantilla',
    colDescription: 'Descripción',
    colLanguage: 'Idioma',
    colCountry: 'País',
    colVersion: 'Versión',
    colDownloads: 'Descargas',
    colSize: 'Tamaño',
    loadingCatalog: 'Cargando plantillas…',
    catalogEmpty: 'Todavía no hay plantillas publicadas para tu negocio.',
    catalogForbidden: 'Solo un administrador puede ver e importar plantillas.',
    catalogUnavailable: 'No se han podido cargar las plantillas ahora mismo. Puedes importar un archivo igualmente.',
    catalogRetry: 'Reintentar',
    inspecting: 'Leyendo el fichero…',
    inspectErrorTitle: 'No se pudo leer el fichero',
    manifestName: 'Nombre',
    manifestLanguage: 'Idioma',
    manifestCountry: 'País',
    manifestModules: 'Apps',
    manifestCreated: 'Creado',
    sections: 'Secciones detectadas',
    sectionUsers: 'Usuarios',
    sectionSettings: 'Ajustes',
    sectionFiscal: 'Fiscal',
    sectionFiscalDesc: 'Configuración VeriFactu y el certificado de empresa (.p12)',
    sectionMedia: 'Imágenes y media',
    sectionRoles: 'Roles',
    sectionCapabilities: 'Permisos de las apps',
    sectionFlows: 'Automatizaciones',
    sectionModule: 'App {id}',
    modulesTitle: 'Apps',
    withData: 'incluye datos',
    import: 'Importar',
    importing: 'Importando… instalando apps y aplicando datos.',
    importErrorTitle: 'La importación falló',
    back: 'Elegir otro fichero',
    reportTitle: 'Informe de la importación',
    reportModules: 'Apps',
    // hub#763 — este informe se ha RECUPERADO, no es el de una importación que acabas de correr.
    // El Dashboard manda a Datos tras un import parcial; este aviso dice de QUÉ import es el
    // informe (su nombre y cuándo fue) para que no aparezca de la nada.
    reportRecovered: 'Este es el informe de tu última importación de {name} ({when}). No todo entró.',
    // La vuelta al catálogo tras leer el informe recuperado, para que el admin pueda reintentar.
    reportDismiss: 'Ver las plantillas',
    // hub#845 — reintento SOLO de lo que no entró: el servidor vuelve a bajar la MISMA versión del
    // catálogo y re-ejecuta solo lo fallido; lo ya aplicado no se duplica jamás.
    retry: 'Reintentar lo que falta',
    retryNotRetryable:
      'Esta importación vino de un archivo subido a mano, así que no se puede reintentar automáticamente. Vuelve a subir el archivo y selecciona solo lo que falló.',
    retryVersionUnavailable:
      'La versión de la plantilla que usó esta importación ya no está en el catálogo, así que el reintento no se ejecutó — reintentar con otra versión podría cargar datos distintos.',
    retryBatchNotFound:
      'El informe de esta importación ya no está registrado (puede que se deshiciera), así que no hay nada que reintentar.',
    statusApplied: 'Aplicado',
    statusSkipped: 'Saltado',
    statusIgnored: 'Descartado',
    statusPartial: 'Aplicado en parte',
    statusFailed: 'Falló',
    // hub#409 / ADR-0060 — no se instaló porque el plan necesita una dependencia sin contratar.
    // Es una decisión de compra, no una avería: se dice QUÉ contratar (con el precio que mandó el
    // motor), nunca una ✗ roja y muda.
    statusBlocked: 'Requiere contratación',
    reasonBlocked:
      'No se ha instalado: necesita apps que aún no tienes contratadas: {missing}. Contrátalas y vuelve a cargarla — no se ha tocado nada más.',
    mediaFailed: '{n} sin copiar',
    reasonVersionSubstituted: 'La plantilla traía la {requested}; ha entrado la más reciente compatible, la {installed}.',
    reasonIdentityNotPortable:
      'Los usuarios, roles y PIN son del negocio que los creó. Cuentas descartadas: {n}. Nadie ha obtenido acceso al tuyo.',
    reasonSettingsNotPortable:
      'Se han aplicado el país, la moneda y el idioma. Ajustes descartados: {n} — el NIF, la razón social y demás datos son del negocio que creó el fichero; los tuyos se quedan como están.',
    reasonRolesNotActivatable:
      'Roles sin activar: {n}. Una plantilla solo puede activar roles que traigan las apps instaladas aquí, y nunca los administrativos.',
    reasonSystemTableNotPortable:
      'Filas descartadas: {n}. El fichero intentaba escribir los registros propios de este negocio — su perfil fiscal y su certificado. Son de esta instalación y ningún fichero puede cambiarlos.',
    reasonNumberingNotPortable:
      'Numeración descartada: {n}. Las series de facturación y los números ya emitidos son del negocio que creó el fichero. Tu numeración se queda como está — si aún no tienes series, configúralas en Ajustes.',
    reasonInstallationBoundData:
      'Registros descartados: {n}. Esta app lleva un registro oficial encadenado a la caja que lo emitió, así que solo vuelve a esa misma caja. La tuya empieza el suyo — aquí no se ha cambiado nada.',
    reasonTableGoneInInstalledVersion:
      'Filas descartadas: {n}. La plantilla se hizo para una versión anterior de esta app, y la que tienes instalada ya no guarda esos datos. Todo lo demás ha entrado — no hay nada que tengas que arreglar.',
    reasonCapabilityGrantsNotPortable:
      'Permisos de apps descartados: {n}. El acceso a tu impresora, a tu certificado de firma y a internet se concede solo en este terminal. No se ha permitido nada \u2014 concede lo que necesites en Ajustes \u203a Permisos.',
    reasonCapabilitiesNotGrantable:
      'Permisos sin restaurar: {n}. Esas apps ya no los piden, o no est\u00e1n instaladas aqu\u00ed. Todo lo dem\u00e1s se ha devuelto.',
    reasonFlowGrantsNotPortable:
      'Automatizaciones restauradas, pero apagadas. Lo que cada una tiene permitido hacer se concede solo en este terminal \u2014 rev\u00edsalas en Automatizaciones y enciende las que quieras.',
    reasonFlowsPausedWithoutGrants:
      'Algunas automatizaciones han vuelto apagadas: un permiso que ten\u00edan ya no est\u00e1 disponible aqu\u00ed. Abre Automatizaciones para ver qu\u00e9 le falta a cada una.',
    reasonFlowsNotRestorable:
      'Automatizaciones descartadas: {n}. Sus instrucciones nombran algo que aqu\u00ed no existe, as\u00ed que no se han podido guardar. El resto ha vuelto.',
    done: 'Ir al inicio',
  },
  moduleView: {
    loading: 'Cargando módulo…',
    loadError: 'No se pudo cargar el módulo.',
    loadErrorHint: 'Comprueba que el módulo siga instalado y activo, y vuelve a intentarlo.',
    offlineTitle: 'Sin conexión a Internet',
    offlineHint:
      'Esta pantalla necesita la conexión para cargarse. Revisa la red — vuelve sola en cuanto haya Internet otra vez.',
    retry: 'Reintentar',
    blockedTitle: 'Suscripción necesaria',
    blockedHint: 'Este módulo está deshabilitado porque su suscripción ya no está activa para este hub. Tus datos locales están a salvo y vuelven en cuanto vuelva la suscripción — se gestiona desde tu cuenta de ERPlora, en erplora.com.',
    protectedTitle: 'Abre la caja primero',
    protectedHint: 'Esta pantalla está bloqueada mientras la caja esté cerrada. Abre una sesión de caja para empezar a vender — la pantalla se recarga sola en cuanto se abre la caja.',
    emptyTitle: 'Aquí todavía no hay nada',
    emptyHint: 'Este módulo está instalado pero ahora mismo no tiene ninguna pantalla que abrir. Comprueba que está activo en Apps, o abre otro desde el menú.',
    notInstalledTitle: 'Esta app no está instalada',
    notInstalledHint: 'Este hub no tiene esta app. Búscala en el catálogo de Apps o abre otra desde el menú.',
    notInstalledAction: 'Ir al catálogo',
    // hub#1175 — the router says why it sent you back: a module id nobody's entitlement ever
    // named (a stale bookmark, a typo, a module this hub never installed) has no screen to open.
    notAvailableToast: 'Esta app no está disponible para este hub.',
  },
  moduleSettings: {
    tab: 'Ajustes',
    loading: 'Cargando ajustes…',
    loadError: 'No se pudieron cargar los ajustes.',
    save: 'Guardar',
    saved: 'Ajustes guardados.',
    saveError: 'No se pudieron guardar los ajustes.',
    adminOnly: 'Solo un administrador puede cambiar estos ajustes.',
    textPlaceholder: 'Escribe aquí…',
    invalidFields: 'Revisa los campos marcados y vuelve a guardar.',
    fieldInvalid: 'Este valor no se admite.',
    preview: 'Probar',
    previewError: 'No se pudo hacer la prueba.',
  },
  modulePlan: {
    tab: 'Plan',
    statusTitle: 'Tu plan',
    loadingStatus: 'Comprobando tu suscripción…',
    free: 'Gratis',
    perMonth: '/mes',
    perYear: '/año',
    trialDays: '{n} día de prueba | {n} días de prueba',
    quota: 'Incluye {quota}',
    overage: '{price} por unidad extra',
    noTiers: 'Este módulo no ofrece planes de pago.',
    trialEnds: 'Prueba hasta el {date}',
    renewsOn: 'Se renueva el {date}',
    cancelsOn: 'Se cancela el {date}',
    managedInAccount: 'Los planes de este módulo se gestionan desde tu cuenta de ERPlora, en erplora.com.',
    checkPurchase: 'Ya lo he contratado — comprobar',
    yourPlan: 'Tu plan',
    managePlan: 'Gestionar plan',
    managePlanError: 'No se pudo abrir la gestión del plan. Inténtalo de nuevo.',
    upgradeHubPlan: 'Sube de plan para tener más',
    purchaseDetected: 'Confirmado. Tu plan se ha actualizado.',
    // Lo que este hub lleva GASTADO de lo que incluye su plan (whatsapp_inbox#131). El nombre de
    // la métrica lo pone el módulo (`lib/module-quota.ts`): aquí nunca se escribe «conversaciones».
    usageTitle: 'Este mes',
    usageOfLimit: '{used} de {limit} {metric}',
    usageNoLimit: '{used} {metric}',
    usageNearLimit: 'Estás cerca de lo que incluye tu plan.',
    usageOverLimit: 'Has consumido todo lo que incluye tu plan este mes.',
    usageUnavailable: 'No se ha podido leer tu consumo. Inténtalo dentro de un momento.',
    status: {
      active: 'Activo',
      trialing: 'En prueba',
      expired: 'Caducado',
      none: 'Sin plan',
      canceled: 'Cancelado',
      past_due: 'Pago pendiente',
    },
    hint: {
      active: 'Tu suscripción está activa.',
      trialing: 'Estás en periodo de prueba.',
      expired: 'Tu suscripción ha caducado. Vuelve a contratar para seguir usándolo.',
      none: 'Aún no tienes un plan para este módulo.',
      free: 'Estás en {plan}, el plan con el que entra todo el mundo.',
      expiredOnFree: 'Tu suscripción ha caducado. Sigues en {plan}.',
      includedInPlan: 'Incluido en tu plan {plan}.',
      includedInHubPlan: 'Incluido en tu plan.',
      canceled: 'Tu suscripción está cancelada.',
      past_due: 'Hay un pago pendiente en tu suscripción.',
    },
  },

  // Hardware (impresoras, cajón). Las dos frases de abajo son el motivo de hub#338: un escaneo
  // puede acabar sin impresoras por dos razones OPUESTAS, y cada una le pide al usuario una cosa
  // distinta. Enseñar la que no toca le manda a arreglar algo que nunca estuvo roto.
  hardware: {
    printersBlocked:
      'ERPlora no ha podido buscar en esta red: el sistema no le ha dado permiso a la app para acceder a los dispositivos de la red local. Concédele el acceso a la red local a ERPlora en los ajustes del dispositivo y vuelve a buscar.',
    printersNone:
      'No se ha encontrado ninguna impresora en esta red. Comprueba que la impresora está encendida y conectada a la misma red que este dispositivo, y vuelve a buscar.',
    // ADR-0196 §3: desde el navegador, a secas, no hay forma de llegar a una impresora. Nombrar
    // la app es lo importante: es la frase que convierte «no funciona» en un paso siguiente.
    unavailable:
      'Desde el navegador, este dispositivo no puede llegar a las impresoras. Instala la app de ERPlora en el dispositivo conectado a la impresora y abre tu negocio desde ahí.',
    // hub#1773 — traducción de `localNetwork` de `en.ts` (el inglés es la fuente, ADR-0055).
    localNetwork: {
      primerHeader: 'Vamos a buscar tu impresora',
      primerMessage:
        'Para encontrar tu impresora tenemos que mirar los aparatos de tu red. Tu dispositivo te lo preguntará a continuación.',
      primerLater: 'Ahora no',
      primerAllow: 'Buscar mi impresora',
      blockedTitle: 'La búsqueda de impresoras está bloqueada',
      blockedDetail:
        'Este dispositivo no tiene permiso para llegar a las impresoras de tu red, así que la búsqueda vuelve vacía por muchas impresoras que haya encendidas.',
      blockedAction: 'Permitir la búsqueda',
      blockedInSettings:
        'Tu dispositivo no ha vuelto a preguntar. Abre sus ajustes, busca ERPlora y concédele el acceso a la red local.',
      turnedOn: 'Listo: este dispositivo ya puede buscar impresoras en tu red.',
    },
  },
  // Lo que dice el CORE cuando rechaza UN campo (hub#1190, ADR-0398 §6). Traducción de
  // `invalidField` de `en.ts` — el inglés es la fuente (ADR-0055).
  invalidField: {
    byField: {
      name: {
        required: 'Escribe el nombre.',
        too_long: 'Ese nombre es demasiado largo: usa 150 caracteres o menos.',
        duplicate:
          'Este hub ya conoce a alguien con ese nombre. Edita a ese usuario —reincorpóralo si estaba dado de baja— en vez de crear una segunda identidad.',
      },
      role: {
        required: 'Elige un rol.',
        too_long: 'Ese nombre de rol es demasiado largo: usa 50 caracteres o menos.',
      },
      pin: { format: 'El PIN es de {length} dígitos, solo números.' },
      badge: {
        length: 'La placa debe tener entre 4 y 64 caracteres.',
        format: 'La placa solo admite letras, dígitos, «-» y «_».',
      },
      email: { format: 'Ese correo electrónico no es válido.' },
      role_key: {
        required: 'Elige un rol.',
        immutable: 'Este rol viene con el hub: está siempre activo y no se puede apagar.',
        unknown:
          'Ninguna app instalada declara este rol. Instala la app que lo trae o elige otro rol.',
        inactive:
          'Este rol está apagado en este hub. Enciéndelo en Ajustes → Roles antes de asignarlo.',
      },
      language: { unknown: 'Ese idioma no está disponible en este hub.' },
      theme_mode: { unknown: 'Ese aspecto no es uno de los que ofrece este hub.' },
      theme_palette: { unknown: 'Esa combinación de colores no es una de las que ofrece este hub.' },
    },
    byReason: {
      required: 'Este campo es obligatorio.',
      too_long: 'Este valor es demasiado largo.',
      length: 'Este valor no tiene la longitud que espera este hub.',
      format: 'Este valor no tiene la forma que espera este hub.',
      unknown: 'Este hub no acepta ese valor.',
      immutable: 'Este valor no se puede cambiar.',
      inactive: 'Este valor está apagado en este hub.',
      duplicate: 'Este hub ya tiene ese valor.',
    },
  },
  runtimeErrorFacts: {
    core_version_too_old:
      'Esta app necesita un hub más nuevo (ERPlora {required}). El tuyo tiene la {core}: actualiza el hub e inténtalo de nuevo.',
  },
  // Traducción de `runtimeErrors` en `en.ts`: lo que el runtime contesta cuando falla una puerta
  // que habla con la nube. Un código sin frase aquí no se pinta nunca; el llamador cae a `default`.
  runtimeErrors: {
    cloud_unreachable: CLOUD_UNREACHABLE,
    install_cloud_unavailable: CLOUD_UNREACHABLE,
    install_cloud_denied:
      'ERPlora no ha aceptado las credenciales de este hub, así que no puede instalar apps. Reintentar no lo arregla; avisa a soporte.',
    install_not_in_catalog: 'Esa app no está disponible en tu catálogo.',
    install_cloud_rejected:
      'ERPlora no ha podido atender esta instalación ahora mismo. Inténtalo en unos minutos.',
    install_cloud_timeout:
      'ERPlora no ha contestado a tiempo, así que la app no se ha instalado. Inténtalo en unos minutos.',
    core_version_too_old: 'Esta app necesita un hub más nuevo: actualiza el hub e inténtalo de nuevo.',
    cloud_rejected: 'ERPlora no ha podido atenderlo ahora mismo. Inténtalo en unos minutos.',
    cloud_unreadable: 'ERPlora ha contestado algo que este hub no ha podido leer. Inténtalo en unos minutos.',
    hub_not_enrolled: 'Este hub todavía no está conectado con ERPlora.',
    module: {
      update_lost:
        'La actualización ha fallado y no se ha podido recuperar la versión anterior, así que esta app ya no está instalada. Vuelve a instalarla desde Apps; si también falla, avisa a soporte.',
    },
    default: 'No ha funcionado. Vuelve a intentarlo dentro de un minuto.',
  },
  // hub#1258 used to carry a `platformFailure` catalogue here (translation of the one in `en.ts`)
  // for what the core says when it refuses at the PLATFORM level — a byte-identical copy of
  // `platformFailureMessage` in `packages/module-sdk/src/index.ts` (hub#1102). hub#1315 removed
  // the copy: `lib/platform-failure.ts` now renders the SDK's own sentence directly, so there are
  // no i18n keys to keep in parity here any more.
} as const;
