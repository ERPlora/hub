# Peticiones de UI de la app `base`

Lo que las pantallas de la plataforma necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo más
parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

## Iconos de documento en el registro del shell (`packages/ui/src/shell/icons.ts`)

- **Qué**: `ion:document-outline` y `ion:document-text-outline` (Ionicons, ya instalados con `ionicons/icons`: una
  importación y una entrada cada uno), para el icono de un archivo en «Archivos» (BASE-F72): un texto, un registro o
  una nota con la hoja de documento, como en Drive o Dropbox, y cualquier otro archivo con la hoja en blanco.
- **Hoy**: `lib/files.ts` (`ICONS`) usa los que hay registrados: `ion:code-slash-outline` para texto y JSON,
  `ion:receipt-outline` para PDF y `ion:file-tray-outline` para lo que no se previsualiza. Se entienden, pero un
  `.txt` con `</>` parece código.
- Al llegar: cambiar `text` a `ion:document-text-outline` y `''` a `ion:document-outline` en `ICONS` y su test
  (`lib/files.test.ts`).

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

## Nombre del buscador en `@erplora/ui/components`

- **Qué**: exportar el `syncSearchbarInputName` del `DataTable` (`packages/ui/src/components/DataTable/searchbarName.ts`)
  para los `ion-searchbar` que no van dentro de una tabla: Ionic 8 nombra su campo «search text», en inglés, y un lector
  de pantalla lo anuncia así en español (lo vio la QA maestra, BASE-F107).
- **Hoy**: `base/frontend/lib/searchbar.ts` (`nameSearchbar`) hace lo mismo para «Archivos» (`FilesPage.vue`).
- Al llegar: usar el de `@erplora/ui/components` en `FilesPage.vue` y borrar `lib/searchbar.ts` y su test.
