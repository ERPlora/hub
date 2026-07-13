// Puente Iconify → <ion-icon>. Los iconos llegan como SVG inline (string) — bien horneados en
// build por unplugin-icons (`~icons/<set>/<name>?raw`, ver vite.config.ts), bien traídos por un
// módulo en su manifest (ADR option-b: el `pack` resuelve el nombre Iconify a SVG). `ion-icon` NO
// acepta `<svg>` crudo en su prop `icon` (lo trataría como nombre a resolver vía addIcons), así que
// lo envolvemos en un data-URI, que sí reconoce (`isSrc` acepta `data:`). El resultado hereda
// color (currentColor) y tamaño del slot del ion-button, igual que un ionicon nativo.

/**
 * SVG inline (`<svg …>…</svg>`) → data-URI listo para `<ion-icon :icon="…">`.
 *
 * Formato EXACTO, copiado del que emite el propio set de ionicons — las dos partes importan:
 *
 * - `;utf8,` es el marcador que ionicons busca (`isEncodedDataUrl`) para parsear el SVG con
 *   DOMParser —sin red, compatible con CSP— en vez de caer a un `fetch()` por icono.
 * - El SVG va **CRUDO, sin `encodeURIComponent`**: ese DOMParser hace
 *   `parseFromString(url, 'text/html').querySelector('svg')` sobre la URL ENTERA (request.js), así
 *   que necesita encontrar el tag `<svg>` literal. Percent-encoded no lo encuentra → lanza
 *   "Could not parse svg" y el icono sale VACÍO.
 *
 * Contrato fijado en iconify.test.ts.
 */
export function svgToIcon(svg: string): string {
  return `data:image/svg+xml;utf8,${svg}`;
}

/** `true` si el valor ya es un SVG inline (lo trae un módulo) y no un nombre a resolver. */
export function isInlineSvg(value: string): boolean {
  return value.trimStart().startsWith('<svg');
}
