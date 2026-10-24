# Peticiones de UI de la plataforma `base`

Lo que las pantallas de `base` necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo más parecido
que ya existe (dicho en cada punto); se cambia en cuanto llegue.

## Iconos del cuadro del asistente en el registro del shell (`packages/ui/src/shell/icons.ts`)

- **Qué**: registrar en `icons.ts` los cuatro iconos del cuadro del asistente (APP-BASE-9), de Lucide como los
  demás que no son de Ionicons: `lucide:paperclip` («Adjuntar un archivo»), `lucide:mic` («Dictar por voz»),
  `lucide:square` («Detener» y «Detener la grabación») y `lucide:volume-2` («Leer en voz alta»).
- **Hoy**: `base/frontend/lib/assistant-icons.ts` los hornea igual que el shell (`~icons/lucide/*`, sin red) y
  los pinta con `ion-icon :src` en `AssistantComposer.vue` y `AssistantMessage.vue`.
- Al llegar: cambiar esos `ion-icon` por `HubIcon name="lucide:…"` y borrar `assistant-icons.ts` y su test.

## `useI18n` en `@erplora/ui/shell`

- **Qué**: que el shell exporte el `t` y el `locale` de su instancia de vue-i18n para los `<script setup>`.
- **Hoy**: `base/frontend/lib/i18n.ts` (`useBaseI18n`) los lee de `$t` y `$i18n` de la instancia.
- Al llegar: sustituir `useBaseI18n` por esa importación.
