# Peticiones a `@erplora/ui` de la app VeriFactu

Lo que la app necesita del submódulo `packages/ui` y no puede añadir ella misma (fuera de su carril). Mientras
no llegue, la app usa lo indicado en «Mientras tanto».

| Petición | Para qué | Mientras tanto |
|---|---|---|
| Registrar `ion:document-text-outline` en `packages/ui/src/shell/icons.ts` | El icono de «Registros» del módulo actual (menú y pestaña) | `ion:list-outline` |
| Registrar `ion:shield-checkmark-outline` | El icono del módulo y de «Recuperación» del módulo actual | `lucide:shield-check` (registrado) |
| Un formateador de dinero en `@erplora/ui/components/format` | Pintar importes en céntimos («€12.10», «-12,10 €») sin copia por app | `frontend/lib/format.ts`, copia del de Facturación |
| Un componente de pestañas internas de una página (dos vías en Configuración) | Las pestañas «Lo remite ERPlora» / «Mi certificado» como las demás páginas | `ion-segment` con `mode="md"` |
