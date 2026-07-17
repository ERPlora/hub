// Constructor DOM del widget CORE de puesta en marcha del hub (ADR-0113 §4).
//
// Es imperativo a propósito: vive en el shadow del ok-widget-board bajo CSP estricta (sin
// innerHTML ni estilos que crucen el shadow), así que se construye a mano y se estila por elemento
// con los mismos tokens que theme/polish.css (las custom properties SÍ heredan al shadow).
//
// Simplificación 2026-07-17 (decisión humano): un ÚNICO CTA «configurar». La primera vez que se
// ve el hub, nadie necesita EXPORTAR configuración — eso se descubre luego en Ajustes › Datos o
// preguntando al asistente. Mezclar «importa una plantilla / o un backup / o exporta para reusar»
// en la primera pantalla era ruido: tres trabajos distintos, dos de ellos irrelevantes el día 1.
type T = (key: string) => string;

export function buildBlueprintWidget(cell: HTMLElement, t: T, onOpen: () => void): void {
  const card = document.createElement('ion-card');
  card.setAttribute('data-testid', 'dashboard-blueprint-widget');
  card.style.cssText =
    'margin:0;border-radius:var(--ok-radius);box-shadow:var(--ok-shadow-sm);border:1px solid var(--ion-border-color);';
  const content = document.createElement('ion-card-content');

  const title = document.createElement('h2');
  title.textContent = t('dashboard.blueprintTitle');
  title.style.cssText = 'font-size:1rem;font-weight:600;margin:0;';

  const body = document.createElement('p');
  body.textContent = t('dashboard.blueprintBody');
  body.style.cssText = 'color:var(--ion-color-medium);margin:0.15rem 0 0;';

  const actions = document.createElement('div');
  actions.style.cssText = 'display:flex;margin-top:0.75rem;';
  const cta = document.createElement('ion-button');
  cta.setAttribute('size', 'small');
  cta.setAttribute('data-testid', 'dashboard-blueprint-cta');
  cta.textContent = t('dashboard.blueprintCta');
  cta.addEventListener('click', () => onOpen());
  actions.append(cta);

  content.append(title, body, actions);
  card.append(content);
  cell.append(card);
}
