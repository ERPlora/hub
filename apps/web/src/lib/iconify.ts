// Puente Iconify → <ion-icon>. Los iconos llegan como SVG inline (string) — bien horneados en
// build por unplugin-icons (`~icons/<set>/<name>?raw`, ver vite.config.ts), bien traídos por un
// módulo en su manifest (ADR option-b: el `pack` resuelve el nombre Iconify a SVG). `ion-icon` NO
// acepta `<svg>` crudo en su prop `icon` (lo trataría como nombre a resolver vía addIcons), así que
// lo envolvemos en un data-URI, que sí reconoce (`isSrc` acepta `data:`). El resultado hereda
// color (currentColor) y tamaño del slot del ion-button, igual que un ionicon nativo.

/** SVG inline (`<svg …>…</svg>`) → data-URI listo para `<ion-icon :icon="…">`. */
export function svgToIcon(svg: string): string {
  return `data:image/svg+xml,${encodeURIComponent(svg)}`;
}

/** `true` si el valor ya es un SVG inline (lo trae un módulo) y no un nombre a resolver. */
export function isInlineSvg(value: string): boolean {
  return value.trimStart().startsWith('<svg');
}
