/**
 * Trae a la vista la pestaña activa del tabbar de footer (ADR-0022).
 *
 * Con más pestañas de las que caben, la barra scrollea en horizontal (polish.css, hub#165). Si la
 * pestaña activa NO viene de un toque sino de la URL —ModuleView deep-linkea `/m/<moduleId>/<navId>`,
 * y hoy `tables` y `verifactu` tienen 5 pestañas, que a 390px ya desbordan— al montar puede quedar
 * fuera de vista y el usuario no ve cuál está activa.
 *
 * Ionic no lo cubre: `ion-segment` no hace `scrollIntoView` y su prop `scrollable` solo cambia
 * layout y gestos. Se usa `scrollLeft` (y no `scrollIntoView`) para no arrastrar a los ancestros
 * scrolleables ni pelearse con el scroll de la página.
 */
export function scrollActiveTabIntoView(segment: HTMLElement | null): void {
  if (!segment) return;

  const activa = segment.querySelector<HTMLElement>('.segment-button-checked');
  if (!activa) return;

  // Todo cabe → no hay nada que traer.
  if (segment.scrollWidth <= segment.clientWidth) return;

  const inicio = activa.offsetLeft;
  const fin = inicio + activa.offsetWidth;
  const visibleInicio = segment.scrollLeft;
  const visibleFin = visibleInicio + segment.clientWidth;

  if (inicio < visibleInicio) {
    segment.scrollLeft = inicio;
  } else if (fin > visibleFin) {
    segment.scrollLeft = fin - segment.clientWidth;
  }
}

/** Qué bordes del tabbar esconden pestañas. `none` = caben todas. */
export type TabbarOverflow = 'none' | 'start' | 'end' | 'both';

/** Margen de subpíxel: `scrollLeft` es fraccionario y nunca iguala exactamente al tope. */
const EPSILON = 1;

/**
 * Calcula qué bordes esconden pestañas, para que el degradado se pinte SOLO donde hay más.
 *
 * Un degradado fijo a la derecha seguiría oscureciendo la última pestaña cuando ya has llegado al
 * final: se lee como un fallo de pintado, no como "hay más". Por eso son cuatro estados y no un
 * booleano.
 */
export function tabbarOverflow(segment: HTMLElement | null): TabbarOverflow {
  if (!segment) return 'none';

  const maximo = segment.scrollWidth - segment.clientWidth;
  if (maximo <= EPSILON) return 'none';

  const hayAntes = segment.scrollLeft > EPSILON;
  const hayDespues = segment.scrollLeft < maximo - EPSILON;

  if (hayAntes && hayDespues) return 'both';
  if (hayAntes) return 'start';
  return 'end';
}

/**
 * Publica el estado en `data-overflow` para que el degradado lo pinte desde CSS (polish.css).
 * El cálculo vive en JS porque CSS no sabe si un contenedor desborda ni por dónde va su scroll.
 */
export function syncTabbarOverflow(segment: HTMLElement | null): void {
  if (!segment) return;
  segment.dataset.overflow = tabbarOverflow(segment);
}

/** Cuánto se asoma la barra al dar la pista, y cuánto tarda en volver. */
const HINT_PX = 28;
const HINT_VUELTA_MS = 420;

/**
 * ¿Merece la pena dar la pista de scroll al entrar?
 *
 * El degradado dice que hay más; el movimiento enseña el GESTO. Pero es movimiento que el usuario
 * no ha pedido, así que solo se da cuando aporta:
 * - si caben todas las pestañas no hay nada que descubrir;
 * - si ya estás al final, a la derecha no queda nada;
 * - con `prefers-reduced-motion` no se anima, punto;
 * - si la barra ya se movió sola para revelar la pestaña activa, el usuario ya vio que se mueve —
 *   repetirlo sería un tirón raro.
 */
export function shouldHintScroll(opts: {
  overflow: TabbarOverflow;
  reducedMotion: boolean;
  yaScrolleado: boolean;
}): boolean {
  if (opts.reducedMotion) return false;
  if (opts.yaScrolleado) return false;
  return opts.overflow === 'end' || opts.overflow === 'both';
}

/**
 * Asoma la barra unos píxeles y la devuelve: enseña que se puede deslizar.
 *
 * Mueve el scroll REAL (no un `transform`) para que el degradado de borde se recalcule solo con el
 * evento `scroll` — al asomarse aparece el degradado izquierdo, lo que refuerza la pista en vez de
 * pelearse con ella.
 */
export function hintScroll(segment: HTMLElement | null): void {
  if (!segment) return;
  segment.scrollTo({ left: HINT_PX, behavior: 'smooth' });
  setTimeout(() => segment.scrollTo({ left: 0, behavior: 'smooth' }), HINT_VUELTA_MS);
}
