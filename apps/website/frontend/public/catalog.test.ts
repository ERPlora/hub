// The public page's live catalog: the block the server painted from the publication's snapshot
// (`[data-ep-block="catalog"]`) is rebuilt from `/api/website/public/catalog`, element by element and as text,
// never as HTML. A failed read keeps the snapshot; the editor's preview is never refreshed.
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { hydrateCatalog } from './catalog';

const SNAPSHOT = `
  <div class="row row-cols-1 row-cols-md-2 row-cols-xl-3 g-4" data-ep-block="catalog" data-ep-source="service"
       data-ep-empty="Nothing to show here yet.">
    <div class="col"><h3 class="h5 mb-2 ws-display">Old</h3></div>
  </div>`;

const FRESH = {
  source: 'service',
  show_prices: true,
  groups: [
    {
      name: 'Hair',
      items: [
        { name: 'Cut', price: 1500, price_kind: 'fixed', minutes: 30, price_label: '15,00 €' },
        { name: '<img src=x onerror=alert(1)>', price: null, price_kind: 'none', minutes: null, price_label: '' },
      ],
    },
    { name: '', items: [{ name: 'Advice', price: 0, price_kind: 'free', minutes: 10, price_label: 'Gratis' }] },
  ],
};

function page(body = SNAPSHOT, preview = false): Document {
  document.body.innerHTML = body;
  if (preview) document.body.setAttribute('data-ep-preview', '');
  else document.body.removeAttribute('data-ep-preview');
  return document;
}

const answer = (data: unknown, status = 200) => vi.fn().mockResolvedValue(new Response(JSON.stringify(data), { status }));

beforeEach(() => {
  document.body.innerHTML = '';
});

describe('hydrateCatalog', () => {
  it('reads the live catalog and rebuilds the block as the server paints it', async () => {
    const fetchImpl = answer(FRESH);
    await hydrateCatalog(page(), fetchImpl);
    expect(fetchImpl).toHaveBeenCalledWith('/api/website/public/catalog', { headers: { Accept: 'application/json' } });
    const block = document.querySelector('[data-ep-block="catalog"]') as HTMLElement;
    // The markup of `templates/website/sections/catalog.html`, with Bootstrap's own classes.
    const groups = [...block.children];
    expect(groups.map((group) => group.className)).toEqual(['col', 'col']);
    expect(groups[0].querySelector('h3')?.className).toBe('h5 mb-2 ws-display');
    expect(groups[0].querySelector('h3')?.textContent).toBe('Hair');
    expect(groups[1].querySelector('h3')).toBeNull();
    expect(groups[0].querySelector('ul')?.className).toBe('list-group list-group-flush');
    const first = groups[0].querySelectorAll('li')[0];
    expect(first.className).toBe('list-group-item bg-transparent px-0 d-flex align-items-baseline gap-3');
    expect([...first.children].map((child) => [child.className, child.textContent])).toEqual([
      ['flex-grow-1', 'Cut 30 min'],
      ['fw-semibold text-nowrap', '15,00 €'],
    ]);
    expect(first.querySelector('small')?.className).toBe('text-body-secondary text-nowrap');
    // Without minutes or a price, only the name.
    const second = groups[0].querySelectorAll('li')[1];
    expect([...second.children].map((child) => child.className)).toEqual(['flex-grow-1']);
    expect(second.querySelector('small')).toBeNull();
  });

  it('writes every name as text: nothing the business typed becomes HTML', async () => {
    await hydrateCatalog(page(), answer(FRESH));
    expect(document.querySelector('[data-ep-block] img')).toBeNull();
    expect(document.body.textContent).toContain('<img src=x onerror=alert(1)>');
  });

  it('an empty catalog says so with the page’s own words', async () => {
    await hydrateCatalog(page(), answer({ ...FRESH, groups: [] }));
    const empty = document.querySelector('[data-ep-block] > .col-12 > p');
    expect(empty?.className).toBe('text-body-secondary mb-0');
    expect(empty?.textContent).toBe('Nothing to show here yet.');
  });

  it('keeps the snapshot when the read fails or answers an error', async () => {
    await hydrateCatalog(page(), vi.fn().mockRejectedValue(new TypeError('offline')));
    expect(document.querySelector('[data-ep-block] h3')?.textContent).toBe('Old');
    await hydrateCatalog(page(), answer({ error: { code: 'base.rate_limited' } }, 429));
    expect(document.querySelector('[data-ep-block] h3')?.textContent).toBe('Old');
  });

  it('leaves the editor’s preview and a page without a catalog alone', async () => {
    const fetchImpl = answer(FRESH);
    await hydrateCatalog(page(SNAPSHOT, true), fetchImpl);
    await hydrateCatalog(page('<main></main>'), fetchImpl);
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
