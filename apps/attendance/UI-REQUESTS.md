# Peticiones de `apps/attendance` a `@erplora/ui`

## Iconos

Los que el módulo viejo pintaba y no están registrados en `packages/ui/src/shell/icons.ts` (un icono
sin registrar no pinta nada). Mientras tanto, la app usa los registrados que se indican:

| Deseado | Dónde | Mientras tanto |
|---|---|---|
| `ion:finger-print-outline` (o `material-symbols:badge-outline`) | Icono del módulo (página de apps, tienda): el del fichaje en el mercado | `ion:log-in-outline` (`ion:time-outline` es el de Horarios) |
| `ion:cafe-outline` | Botón «Empezar pausa» de Fichar | `ion:time-outline` |
| `ion:play-outline` | Botón «Terminar pausa» de Fichar | `ion:arrow-undo-outline` |
| `ion:location-outline` | Aviso «Al fichar la entrada desde este dispositivo se comprueba tu ubicación» | `ion:information-circle-outline` |
| `ion:locate-outline` | Botón «Usar mi ubicación actual» de Ajustes | `ion:globe-outline` |
| `ion:save-outline` | Botón «Guardar» de Ajustes | `lucide:save` |

Al registrarlos: cambiar el `icon` de `apps.py` (y `pnpm gen:app-icons`) y los `name` de las páginas;
`frontend/tabs.test.ts` y `icons.test.ts` del shell vigilan que estén registrados.

## Componentes

### Fecha y hora del negocio en «Corregir jornada»

- **Para qué:** la corrección (ATTENDANCE-F08) usa `ion-input type="datetime-local"`, que pinta en el
  orden del sistema operativo (en un Chrome en inglés con el Hub en español, `mm/dd/yyyy`). Es la misma
  petición de `apps/staff/UI-REQUESTS.md` («Fecha y hora en el orden del idioma del negocio»), con un
  `DateTimeField` (`v-model` `YYYY-MM-DDTHH:MM`, en la hora del negocio).

### Paneles del Inicio

- **Para qué:** el panel «Fichados ahora» (ATTENDANCE-F11) era un widget del Inicio del hub viejo. El
  Inicio del Hub es hoy la rejilla de apps; cuando tenga paneles, el de esta app lee
  `attendance.presence.list` (ya en vivo). Mientras tanto se ve encima de Registros
  (`frontend/components/PresenceCard.vue`).

## De la plataforma (no de `@erplora/ui`)

- **Modo del dispositivo** (compartido / personal): lo decide `base` con el PIN y el dispositivo de
  confianza (fase 2). `frontend/lib/device.ts` devuelve «compartido» hasta entonces; cuando la sesión lo
  traiga, ese fichero lo lee y ATTENDANCE-F03 pasa a `hecho`.
- **Relay del outbox** (fase 2): entrega `staff.member.terminated` a `attendance.record.close_for_terminated`
  (ATTENDANCE-F13). La reacción está hecha y probada contra Personal real; cuando el relay llegue,
  ATTENDANCE-F13 pasa a `hecho` sin tocar la app.
