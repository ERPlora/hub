# Base (`base`)

La plataforma del Hub: siempre está, no se activa ni se apaga. Sirve el shell (el menú lateral, la barra de arriba,
la campana y el asistente), el Inicio, la entrada al negocio, Apps, Sistema, Ajustes, Empleados, Archivos y la
documentación de la API, y por debajo lo que comparten todas las apps: el registro de negocios, la tenencia (una base
de datos por negocio), las operaciones, el outbox y su relevo, las tareas programadas y el contrato con erplora.com
por `/internal`.

- **Estado**: completa (2026-11-01): 101 de sus 108 flujos, `BASE-F01` … `F108`, están `hecho`; `BASE-F02`, `F11`,
  `F41`, `F50`, `F74` y `F82` están `descartado`, cada uno con su issue (hub#573, hub#576–hub#579, saas#190), y `BASE-F40`
  está `no hecho`, reabierto por hub#603.
- **Especificación**: [`WORKBOOK.md`](WORKBOOK.md) (en inglés, [`WORKBOOK.en.md`](WORKBOOK.en.md), hasta «Para quien
  lo mantiene»). Lo que se cambie de la plataforma se cambia antes allí; lo que no entra, en su «Lo que queda fuera».
- **Peticiones** a `@erplora/ui` que siguen abiertas: [`UI-REQUESTS.md`](UI-REQUESTS.md).
- **Tenencia, `/internal`, el worker y los comandos**: el [`README.md`](../README.md) del Hub y la skill
  `hub-tenancy`; las decisiones, en `PLAN-HUB.md` y `PLAN-DB.md` de la raíz de erplora-next.

## Qué hace hoy

- **El Inicio** (F01–F12, F38): el saludo, «Mis apps», «Termina de configurar tu negocio» con los pasos que declara
  cada app (el que impide facturar, primero y en rojo), el tablero de paneles de las apps, que se ponen al día solos,
  la actividad, la campana con los avisos de las apps y los eventos que no se entregaron, y las plantillas de un
  negocio como el suyo.
- **Apps** (F14–F27): las apps del negocio y el catálogo, su precio, lo que traen consigo, activar y desactivar (al
  momento y en todos los dispositivos), por qué una no se abre y la de pago bloqueada.
- **Sistema** (F39–F47): Uso y plan, con lo que usa el negocio y si tiene que ampliar, Actualizaciones (versión y fecha), los
  eventos caídos (reenviar o descartar) y el registro de sucesos; los errores de la pantalla se informan solos.
- **Ajustes** (F29–F37, F48–F51): Negocio (nombre, país, moneda, idioma y zona, tal como los tiene erplora.com),
  General, y Datos y copias: importar una plantilla o un fichero, revisar, leer el informe, reintentar, deshacer,
  exportar y restablecer por secciones (en un negocio con su propia base de datos).
- **La entrada** (F13, F52–F71): con la cuenta de erplora.com, con el salto desde su panel, con PIN o con la placa en
  una caja compartida, cambiar de usuario, Mi perfil, el PIN del negocio, los dispositivos y las sesiones que caducan
  o se pierden al cambiar de rol.
- **Archivos** (F72–F76): carpetas, subir, previsualizar (imágenes, PDF, texto, CSV, audio y vídeo), descargar,
  mover, renombrar y borrar.
- **Empleados** (F77–F91): el personal y sus plazas, una persona, su PIN y su placa, los roles, las aprobaciones y su
  registro, las llaves de API (crear, rotar, revocar y ver; en un negocio con su propia base de datos) y la
  documentación de la API.
- **El asistente** (F92–F106): con texto o con voz, usa las operaciones de todas las apps como herramientas según
  quién pregunta, pide confirmación con su tarjeta (y escribir para confirmar lo peligroso), tiene su límite de uso
  por plan y se le informa de una respuesta mala.
- **La QA maestra del Hub y el reporte a soporte** (F107, F108).

## Lo que queda fuera

El detalle está en «Lo que queda fuera» del [`WORKBOOK.md`](WORKBOOK.md): las cifras de uso y el aviso de ampliar de
Sistema › Recursos (hub#603), la fila de salud del Inicio (hub#573), el pase a
erplora.com (saas#190), las notas de versión (hub#576), Citas en la moneda del negocio (hub#577), la vista previa de
.xlsx y .docx (hub#578) y los roles que trae una app (hub#579).
