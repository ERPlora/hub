// The public page's Google reviews: the block the server painted with what the Hub keeps (`[data-ep-block="reviews"]`)
// gets its summary (the rating, its stars and the count) and its cards rebuilt from `/api/website/public/reviews`,
// element by element and as text, never as HTML, so a refresh after a publication shows without a new page. A failed
// read, or an answer with nothing to show, keeps what is there; the editor's preview is never refreshed. The markup is
// the server's own: both are checked against one fixture (`reviews.fixture.json`; tests/test_render.py renders it).
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { fragment, tokens } from '../__tests__/tokens';
import type { ReviewsOut } from '../operations';
import { hydrateReviews, listNodes, summaryNodes } from './reviews';
import FIXTURE from './reviews.fixture.json';

const FULL = FIXTURE.cases[0].view as ReviewsOut;

const SNAPSHOT = `
  <div data-ep-block="reviews">
    <div class="d-flex"><div class="d-flex align-items-center gap-3" data-ep-reviews-summary><span>3.0</span></div>
      <div class="d-flex flex-wrap gap-2"><a class="btn" href="https://maps.google.com/?cid=1">See on Google</a></div></div>
    <div data-ep-reviews-list><p class="old">Old review</p></div>
    <p class="small">Rating and reviews from Google Maps.</p>
  </div>`;

function page(body = SNAPSHOT, preview = false): Document {
  document.body.innerHTML = body;
  if (preview) document.body.setAttribute('data-ep-preview', '');
  else document.body.removeAttribute('data-ep-preview');
  return document;
}

const answer = (data: unknown, status = 200) => vi.fn().mockResolvedValue(new Response(JSON.stringify(data), { status }));
const summary = () => document.querySelector('[data-ep-reviews-summary]') as HTMLElement;
const list = () => document.querySelector('[data-ep-reviews-list]') as HTMLElement;

beforeEach(() => {
  document.body.innerHTML = '';
});

describe('summaryNodes and listNodes', () => {
  it.each(FIXTURE.cases.map((example) => [example.name, example] as const))(
    'build the server’s own markup (%s)',
    (_name, example) => {
      const view = example.view as ReviewsOut;
      expect(tokens(summaryNodes(view))).toEqual(tokens(fragment(example.summary)));
      expect(tokens(listNodes(view))).toEqual(tokens(fragment(example.list)));
    },
  );
});

describe('hydrateReviews', () => {
  it('reads the reviews kept and rebuilds the summary and the cards as the server paints them', async () => {
    const fetchImpl = answer(FULL);
    await hydrateReviews(page(), fetchImpl);
    expect(fetchImpl).toHaveBeenCalledWith('/api/website/public/reviews', { headers: { Accept: 'application/json' } });
    expect(tokens(summary().childNodes)).toEqual(tokens(summaryNodes(FULL)));
    expect(tokens(list().childNodes)).toEqual(tokens(listNodes(FULL)));
    expect(list().querySelectorAll('figure.card')).toHaveLength(3);
    // The buttons and Google's attribution stay as the server wrote them.
    expect(document.querySelector('.btn')?.getAttribute('href')).toBe('https://maps.google.com/?cid=1');
    expect(document.body.textContent).toContain('Rating and reviews from Google Maps.');
  });

  it('writes every name and text as text: nothing an author typed becomes HTML', async () => {
    await hydrateReviews(page(), answer(FULL));
    expect(list().querySelector('b')).toBeNull();
    expect(list().textContent).toContain('Lucía <b>M.</b>');
  });

  it('a cut review keeps its whole text in its title', async () => {
    await hydrateReviews(page(), answer(FULL));
    const text = list().querySelector('blockquote p') as HTMLElement;
    expect(text.textContent).toBe('Me encanta…');
    expect(text.title).toBe('Me encanta, de verdad, volveré siempre.');
  });

  it('keeps what is there when the read fails, answers an error or has nothing to show', async () => {
    await hydrateReviews(page(), vi.fn().mockRejectedValue(new TypeError('offline')));
    expect(list().textContent).toContain('Old review');
    await hydrateReviews(page(), answer({ error: { code: 'base.rate_limited' } }, 429));
    expect(list().textContent).toContain('Old review');
    await hydrateReviews(page(), answer({ ...FULL, available: false, reviews: [] }));
    expect(list().textContent).toContain('Old review');
    expect(summary().textContent).toBe('3.0');
  });

  it('leaves the editor’s preview and a page without reviews alone', async () => {
    const fetchImpl = answer(FULL);
    await hydrateReviews(page(SNAPSHOT, true), fetchImpl);
    await hydrateReviews(page('<main></main>'), fetchImpl);
    expect(fetchImpl).not.toHaveBeenCalled();
  });
});
