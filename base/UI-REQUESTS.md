# Peticiones de UI de `base`

Lo que las pantallas de la plataforma necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo más
parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

## Una entrada del menú lateral que sale según un ajuste (APP-BASE-5, BASE-F90 y BASE-F91)

- **Qué**: que una entrada de `ShellSidebar` pueda decir cuándo sale (por ejemplo, una función o un `Ref<boolean>`),
  como la entrada «API» del hub viejo, que solo aparecía con «Mostrar documentación de la API» encendido y se iba al
  apagarlo, sin recargar.
- **Hoy**: no hay entrada «API» en el menú; la documentación se abre desde **Ajustes › General** («Abrir la
  documentación de la API») y desde **Empleados › API keys** («Documentación de la API»).
- Al llegar: añadir en `frontend/main.ts` (`SIDEBAR`) la entrada `/api-docs` condicionada por
  `base.api_doc.settings`, y su test en `frontend/main.test.ts`.

## El icono `ion:finger-print-outline` en los iconos del shell (APP-BASE-5, BASE-F85)

- **Qué**: registrar `finger-print-outline` (y `shield-checkmark-outline`) de Ionicons en
  `packages/ui/src/shell/icons.ts`, los de las pestañas «Aprobaciones» y «Roles» del hub viejo.
- **Hoy**: `ion:checkmark-done-outline` en «Aprobaciones» y `ion:shield-outline` en «Roles»
  (`base/frontend/pages/EmployeesPage.vue`).
- Al llegar: cambiar los dos nombres y su test (`EmployeesPage.test.ts`).
