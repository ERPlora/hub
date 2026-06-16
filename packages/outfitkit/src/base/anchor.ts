// Decide la alineación de un panel flotante (popover propio) respecto a su disparador, eligiendo el
// lado con espacio en el viewport: alinear a la izquierda o a la derecha, y abrir hacia abajo o
// hacia arriba. REUTILIZABLE por cualquier componente con overlay propio (ok-app-launcher,
// ok-split-button, ok-command-palette, ok-color-picker, ok-menubar…). CSP-safe (solo geometría).
//
// Importante: NO usa `position: fixed` (se rompe si un ancestro tiene `transform`/`filter`, p.ej. en
// transiciones de ruta). El panel debe ser `position: absolute` relativo a su host; este helper solo
// devuelve QUÉ lado usar, y el componente aplica las clases (.end / .above) correspondientes.

export interface AnchorOptions {
  /** Separación vertical entre botón y panel (px). */
  gap?: number;
  /** Margen mínimo respecto a los bordes del viewport (px). */
  margin?: number;
}

export interface AnchorSide {
  /** true → alinear el borde DERECHO del panel con el del botón (abrir hacia la izquierda). */
  end: boolean;
  /** true → abrir hacia ARRIBA del botón (no hay sitio debajo y sí encima). */
  above: boolean;
}

export function computeAnchor(
  trigger: HTMLElement,
  panel: HTMLElement,
  opts: AnchorOptions = {},
): AnchorSide {
  const gap = opts.gap ?? 8;
  const margin = opts.margin ?? 8;
  const t = trigger.getBoundingClientRect();
  const p = panel.getBoundingClientRect();
  const vw = window.innerWidth;
  const vh = window.innerHeight;

  // Horizontal: por defecto se alinea a la izquierda del botón (abre hacia la derecha). Si el panel
  // no cabe por la derecha y sí hay sitio alineándolo a la derecha del botón, se voltea.
  const end = t.left + p.width > vw - margin && t.right - p.width >= margin;

  // Vertical: por defecto debajo; si no cabe debajo y sí encima, se abre hacia arriba.
  const above = t.bottom + gap + p.height > vh - margin && t.top - gap - p.height >= margin;

  return { end, above };
}
