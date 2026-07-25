# Guía permanente de UI/UX y QA del Hub

Esta guía fija los patrones aprobados para el shell, las páginas core y las vistas de módulos.
Se aplica al Hub Cloud (PWA/web) — el único producto (ADR-0154). Una excepción funcional debe quedar
documentada; no se resuelve duplicando pantallas o inventando datos.

## 1. Modelo de producto y navegación

- Un Hub representa un negocio aislado. El SaaS puede administrar varios negocios y organizaciones,
  pero un Hub no conoce ni cambia a otros hubs.
- `/profile` pertenece al usuario autenticado: datos personales, foto y preferencias propias.
- `/settings#hub` pertenece al negocio/Hub: identidad, fiscalidad, apariencia común e integraciones.
- Datos, copia/restauración e importación/exportación viven en `/settings#data`; no se duplica una
  segunda pantalla de copias en Sistema.
- Sistema se reserva para diagnóstico y operación técnica: estado, módulos, almacenamiento y logs.
- Cada destino importante tiene una entrada directa y una URL estable. No se esconde una pantalla
  independiente dentro de una pestaña sin enlace navegable.

## 2. Shell y asistente

- En escritorio y tablet el asistente se muestra en paralelo a la página abierta. El usuario debe
  poder trabajar con ambos a la vez; la página se adapta al ancho disponible, no se sustituye ni se
  bloquea.
- En móvil el asistente puede superponerse porque no hay ancho útil para dos paneles.
- Abrir o cerrar el asistente no pierde filtros, scroll, formulario, ruta ni estado del módulo.
- Sidebar, topbar y menú de usuario usan los mismos nombres, iconos, permisos y destinos en todas
  las páginas.

## 3. Tema y preferencias

- La paleta del Hub es el valor común.
- La preferencia del usuario autenticado, si existe, prevalece solo para ese usuario.
- Si el usuario no tiene preferencia guardada, se aplica la del Hub.
- Las preferencias personales se persisten por `user_id`; cambiar de usuario vuelve a resolver la
  preferencia y nunca hereda la del usuario anterior.
- No se crea una tercera paleta ni una copia del mismo control en Tienda/Ajustes.

## 4. Páginas core

Las rutas core son Dashboard, Employees, Files, Billing, Apps, System, Settings, Profile, API Docs,
Activation y Login. Para cada una se verifica:

- encabezado, jerarquía y acciones coherentes;
- estados de carga, vacío, error, sin permiso y offline;
- formularios con etiquetas, errores junto al campo, foco al primer error y confirmación de guardado;
- acciones destructivas confirmadas y claramente diferenciadas;
- textos ES/EN completos, sin claves de traducción visibles;
- datos reales del runtime/SaaS; nunca tarjetas o módulos comerciales inventados.

En Apps, Demo usa el catálogo público real. Un Hub vinculado usa su credencial de máquina para el
catálogo privado y las operaciones autorizadas. La falta de red muestra reintento y no datos falsos.

## 5. Host y módulos

- El host mantiene ruta, pestaña interna, permisos, errores y ciclo de carga del Web Component.
- Las tablas de módulos usan `ok-data-table`, acciones de fila con icono y nombre accesible, y
  activan lista/tarjetas con un `cardTitle` significativo.
- En móvil se valida la vista de tarjetas; una tabla ancha no puede ser la única representación.
- Formularios y estados de módulos reutilizan OutfitKit/Ionic y los tokens del shell.
- Si `module.json` declara `static_files.folder`, el runtime almacena los ficheros del módulo en el
  backend de objetos del Cloud (bajo `modules/<folder>`).
- Los archivos que deban sobrevivir a un fallo de red se persisten antes del envío. VeriFactu
  conserva el XML exacto para poder reintentarlo.

## 6. Matriz mínima de regresión

### Viewports

- 1440 px y 1366 px: escritorio.
- 1024 px y 834 px: tablet con asistente paralelo.
- 390 px: móvil, navegación y asistente superpuesto.

### Interacción y accesibilidad

- Recorrido completo solo con teclado, foco visible y orden lógico.
- `Escape` cierra modales/paneles no destructivos y devuelve el foco al disparador.
- Botones solo-icono tienen nombre accesible; campos tienen etiqueta asociada.
- Contraste suficiente en claro/oscuro y con estados de éxito, aviso y error.
- No hay scroll horizontal de página; las áreas densas gestionan su propio desbordamiento.

### Contextos

- Con y sin el Bridge de hardware conectado.
- Usuario admin y usuario sin permisos suficientes.
- Español e inglés.
- Online, offline, respuesta lenta, error recuperable y sesión caducada.
- Datos vacíos y datos largos/reales.

## 7. Puertas antes de publicar

1. Typecheck, pruebas web y build de producción del Hub.
2. Pruebas Rust del workspace; las que requieran servicios externos se identifican como tales.
3. Pruebas y build de cada módulo modificado, además de los guards cross-módulo.
4. Pruebas SaaS del endpoint o contrato modificado.
5. Revisión visual en los cinco anchos y comprobación de consola/red sin errores nuevos.
6. `git diff --check`, revisión de que no se incluyen credenciales, bases locales, dependencias o
   artefactos temporales.

Esta lista es una puerta de publicación, no una comprobación opcional posterior.
