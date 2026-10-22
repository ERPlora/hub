// The public page's live catalog: the block the server painted from the publication's snapshot
// (`[data-ep-block="catalog"]`) is rebuilt from `/api/website/public/catalog`, element by element and as text,
// never as HTML. A failed read keeps the snapshot; the editor's preview is never refreshed. The markup is the
// server's own: both are checked against one fixture (`catalog.fixture.json`; tests/test_render.py renders it).
import { beforeEach, describe, expect, it, vi } from 'vitest';

import type { CatalogOut } from '../operations';
import { catalogNodes, hydrateCatalog } from './catalog';
import FIXTURE from './catalog.fixture.json';

const SNAPSHOT = `
  <div data-ep-block="catalog" data-ep-source="service" data-ep-empty="Nothing to show here yet.">
    <div class="d-grid gap-5"><div id="ws-cat-1"><h3 class="h5 fw-semibold mb-3 ws-display">Old</h3></div></div>
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

const VOID = new Set(['area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'source', 'track', 'wbr']);

/** HTML as tokens, as the server's test reads it: `<tag a="…">` (attributes sorted), `</tag>`, each text collapsed. */
function tokens(nodes: Iterable<Node>): string[] {
  const box = document.createElement('div');
  box.append(...[...nodes].map((node) => node.cloneNode(true)));
  box.normalize();
  const out: string[] = [];
  const walk = (node: Node): void => {
    if (node.nodeType === Node.TEXT_NODE) {
      const text = (node.textContent ?? '').split(/\s+/).filter(Boolean).join(' ');
      if (text) out.push(text);
      return;
    }
    if (!(node instanceof Element)) return;
    const tag = node.tagName.toLowerCase();
    const attributes = [...node.attributes]
      .map((attribute) => `${attribute.name}="${attribute.value}"`)
      .sort((a, b) => a.localeCompare(b));
    out.push(`<${[tag, ...attributes].join(' ')}>`);
    node.childNodes.forEach(walk);
    if (!VOID.has(tag)) out.push(`</${tag}>`);
  };
  box.childNodes.forEach(walk);
  return out;
}

function fragment(html: string): Node[] {
  const box = document.createElement('div');
  box.innerHTML = html;
  return [...box.childNodes];
}

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

describe('catalogNodes', () => {
  it.each(FIXTURE.cases.map((example) => [example.name, example] as const))(
    'builds the server’s own markup (%s)',
    (_name, example) => {
      expect(tokens(catalogNodes(example.catalog as CatalogOut, FIXTURE.empty))).toEqual(tokens(fragment(example.html)));
    },
  );
});

describe('hydrateCatalog', () => {
  it('reads the live catalog and rebuilds the block as the server paints it', async () => {
    const fetchImpl = answer(FRESH);
    await hydrateCatalog(page(), fetchImpl);
    expect(fetchImpl).toHaveBeenCalledWith('/api/website/public/catalog', { headers: { Accept: 'application/json' } });
    const block = document.querySelector('[data-ep-block="catalog"]') as HTMLElement;
    expect(tokens(block.childNodes)).toEqual(tokens(catalogNodes(FRESH as CatalogOut, 'Nothing to show here yet.')));
    // One named category: no pills; a card per item, the price as a pill, the initial on the placeholder.
    expect(block.querySelector('.nav-pills')).toBeNull();
    expect([...block.querySelectorAll('.card-title')].map((title) => title.textContent)).toEqual([
      'Cut',
      '<img src=x onerror=alert(1)>',
      'Advice',
    ]);
    expect(block.querySelector('.badge')?.textContent).toBe('15,00 €');
    expect(block.querySelector('.ws-thumb')?.textContent).toBe('C');
  });

  it('writes every name as text: nothing the business typed becomes HTML', async () => {
    await hydrateCatalog(page(), answer(FRESH));
    expect(document.querySelector('[data-ep-block] img')).toBeNull();
    expect(document.body.textContent).toContain('<img src=x onerror=alert(1)>');
  });

  it('an empty catalog says so with the page’s own words', async () => {
    await hydrateCatalog(page(), answer({ ...FRESH, groups: [] }));
    const empty = document.querySelector('[data-ep-block] > p');
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
