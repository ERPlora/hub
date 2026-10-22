// The public page's live catalog (round 2026-10-21): the server paints the catalog from the publication's snapshot
// (`templates/website/sections/catalog.html`, good for search engines and for a visitor without JS) inside
// `[data-ep-block="catalog"]`; once the page loads, this refreshes it from `/api/website/public/catalog` (the
// published catalog's source, read live, priced in the visitor's language), rebuilding the same markup element by
// element with `textContent`, never `innerHTML`: a name the business typed stays text. A failed read (offline, the
// visit limit) keeps the snapshot, which is the published catalog. The editor's preview (`data-ep-preview`) is never
// refreshed: it shows the draft's own catalog.
import type { CatalogOut } from '../operations';

export const CATALOG_URL = '/api/website/public/catalog';

function element<K extends keyof HTMLElementTagNameMap>(tag: K, className: string, text?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

/** The catalog's markup, as `sections/catalog.html` paints it: Bootstrap's grid and list group. */
export function catalogNodes(catalog: CatalogOut, empty: string): HTMLElement[] {
  if (!catalog.groups.length) {
    const box = element('div', 'col-12');
    box.append(element('p', 'text-body-secondary mb-0', empty));
    return [box];
  }
  return catalog.groups.map((group) => {
    const box = element('div', 'col');
    if (group.name) box.append(element('h3', 'h5 mb-2 ws-display', group.name));
    const list = element('ul', 'list-group list-group-flush');
    for (const item of group.items) {
      const row = element('li', 'list-group-item bg-transparent px-0 d-flex align-items-baseline gap-3');
      const name = element('span', 'flex-grow-1', item.name);
      if (item.minutes) name.append(' ', element('small', 'text-body-secondary text-nowrap', `${item.minutes} min`));
      row.append(name);
      if (item.price_label) row.append(element('span', 'fw-semibold text-nowrap', item.price_label));
      list.append(row);
    }
    box.append(list);
    return box;
  });
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
