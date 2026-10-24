# Peticiones de UI de la app `base`

Lo que las pantallas de la plataforma necesitan de `@erplora/ui` y todavía no está. Mientras tanto usan lo más
parecido que ya existe (dicho en cada punto); se cambia en cuanto llegue.

## Iconos de documento en el registro del shell (`packages/ui/src/shell/icons.ts`)

- **Qué**: `ion:document-outline` y `ion:document-text-outline` (Ionicons, ya instalados con `ionicons/icons`: una
  importación y una entrada cada uno), para el icono de un archivo en «Archivos» (BASE-F52): un texto, un registro o
  una nota con la hoja de documento, como en Drive o Dropbox, y cualquier otro archivo con la hoja en blanco.
- **Hoy**: `lib/files.ts` (`ICONS`) usa los que hay registrados: `ion:code-slash-outline` para texto y JSON,
  `ion:receipt-outline` para PDF y `ion:file-tray-outline` para lo que no se previsualiza. Se entienden, pero un
  `.txt` con `</>` parece código.
- Al llegar: cambiar `text` a `ion:document-text-outline` y `''` a `ion:document-outline` en `ICONS` y su test
  (`lib/files.test.ts`).
