// The public page's live catalog (round 2026-10-21): the server paints the catalog from the publication's snapshot
// (`templates/website/sections/catalog.html`, good for search engines and for a visitor without JS) inside
// `[data-ep-block="catalog"]`; once the page loads, this refreshes it from `/api/website/public/catalog` (the
// published catalog's source, read live, priced in the visitor's language), rebuilding the same markup (a grid of
// cards; `catalog.fixture.json` holds it for both sides' tests) element by element with `textContent`, never
// `innerHTML`: a name the business typed stays text. A failed read (offline, the visit limit) keeps the snapshot,
// which is the published catalog. The editor's preview (`data-ep-preview`) is never refreshed: it shows the draft's
// own catalog.
import type { CatalogOut } from '../operations';

export const CATALOG_URL = '/api/website/public/catalog';

function element<K extends keyof HTMLElementTagNameMap>(tag: K, className = '', text?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/** The anchor of the `index`-th category (from 0), the target of its pill. */
const anchor = (index: number): string => `ws-cat-${index + 1}`;

/** An item's card: a gradient with its initial (the catalog has no photos), its name, its minutes and its price. */
function card(item: CatalogOut['groups'][number]['items'][number]): HTMLElement {
  const col = element('div', 'col');
  const box = element('div', 'card h-100 border-0 rounded-4 shadow-sm overflow-hidden ws-lift');
  const thumb = element('div', 'ratio ratio-21x9 ws-thumb');
  thumb.setAttribute('aria-hidden', 'true');
  // The first letter, as Django's `first|upper` takes it: a whole character, never half of one.
  thumb.append(
    element('span', 'd-flex align-items-center justify-content-center fs-1 fw-bold ws-display', (Array.from(item.name)[0] ?? '').toUpperCase()),
  );
  const body = element('div', 'card-body d-flex align-items-start justify-content-between gap-3');
  const text = element('div');
  text.append(element('h4', 'h6 card-title mb-1', item.name));
  if (item.minutes) text.append(element('p', 'small text-body-secondary mb-0', `${item.minutes} min`));
  body.append(text);
  if (item.price_label) body.append(element('span', 'badge rounded-pill text-bg-secondary fs-6 text-nowrap', item.price_label));
  box.append(thumb, body);
  col.append(box);
  return col;
}

/** The catalog's markup, as `sections/catalog.html` paints it (`catalog.fixture.json` holds it for both): pills to
 * jump between two or more named categories, then each category's heading and its grid of cards. */
export function catalogNodes(catalog: CatalogOut, empty: string): HTMLElement[] {
  if (!catalog.groups.length) return [element('p', 'text-body-secondary mb-0', empty)];
  const nodes: HTMLElement[] = [];
  const named = catalog.groups.flatMap((group, index) => (group.name ? [{ name: group.name, index }] : []));
  if (named.length > 1) {
    const pills = element('ul', 'nav nav-pills flex-wrap gap-2 mb-4');
    for (const { name, index } of named) {
      const pill = element('li', 'nav-item');
      const link = element('a', 'nav-link rounded-pill border', name);
      link.setAttribute('href', `#${anchor(index)}`);
      pill.append(link);
      pills.append(pill);
    }
    nodes.push(pills);
  }
  const groups = element('div', 'd-grid gap-5');
  catalog.groups.forEach((group, index) => {
    const box = element('div');
    box.id = anchor(index);
    if (group.name) box.append(element('h3', 'h5 fw-semibold mb-3 ws-display', group.name));
    const grid = element('div', 'row row-cols-1 row-cols-md-2 row-cols-lg-3 g-4');
    grid.append(...group.items.map(card));
    box.append(grid);
    groups.append(box);
  });
  nodes.push(groups);
  return nodes;
}

// The public page is not the SPA: no spa-config, no session, no SDK to go through. Its one request is this GET of the
// public catalog, which needs none of them.
// eslint-disable-next-line no-restricted-globals -- see above
export async function hydrateCatalog(doc: Document = document, fetchImpl: typeof fetch = fetch): Promise<void> {
  if (doc.body.hasAttribute('data-ep-preview')) return;
  const block = doc.querySelector<HTMLElement>('[data-ep-block="catalog"]');
  if (!block) return;
  let catalog: CatalogOut;
  try {
    const response = await fetchImpl(CATALOG_URL, { headers: { Accept: 'application/json' } });
    if (!response.ok) return; // The snapshot stays: it is the published catalog.
    catalog = (await response.json()) as CatalogOut;
  } catch {
    return; // Offline or an unreadable answer: the snapshot stays, as above.
  }
  block.replaceChildren(...catalogNodes(catalog, block.dataset.epEmpty ?? ''));
}
