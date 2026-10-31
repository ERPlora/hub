# Peticiones de `apps/attendance` a `@erplora/ui`

## Iconos

Los que el módulo viejo pintaba y no están registrados en `packages/ui/src/shell/icons.ts` (un icono
sin registrar no pinta nada). Mientras tanto, la app usa los registrados que se indican:

| Deseado | Dónde | Mientras tanto |
|---|---|---|
| `ion:cafe-outline` | Botón «Empezar pausa» de Fichar | `ion:time-outline` |
| `ion:play-outline` | Botón «Terminar pausa» de Fichar | `ion:arrow-undo-outline` |
| `ion:location-outline` | Aviso «Al fichar la entrada desde este dispositivo se comprueba tu ubicación» | `ion:information-circle-outline` |
| `ion:locate-outline` | Botón «Usar mi ubicación actual» de Ajustes | `ion:globe-outline` |
| `ion:save-outline` | Botón «Guardar» de Ajustes | `lucide:save` |

El del módulo ya es `ion:finger-print-outline` (registrado). Al registrar los demás: cambiar los `name` de las páginas;
`frontend/tabs.test.ts` y `icons.test.ts` del shell vigilan que estén registrados.

## Componentes

### Fecha y hora del negocio en «Corregir jornada»

- **Para qué:** la corrección (ATTENDANCE-F08) usa `ion-input type="datetime-local"`, que pinta en el
  orden del sistema operativo (en un Chrome en inglés con el Hub en español, `mm/dd/yyyy`). Es la misma
  petición de `apps/staff/UI-REQUESTS.md` («Fecha y hora en el orden del idioma del negocio»), con un
  `DateTimeField` (`v-model` `YYYY-MM-DDTHH:MM`, en la hora del negocio).
