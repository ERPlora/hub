// The public page's Google reviews (2026-10-22): the server paints the rating, its stars, the count and up to five
// review cards with what the Hub keeps from Google (`templates/website/sections/reviews.html`, good for search engines
// and for a visitor without JS) inside `[data-ep-block="reviews"]`; once the page loads, this refreshes the summary
// (`[data-ep-reviews-summary]`) and the cards (`[data-ep-reviews-list]`) from `/api/website/public/reviews`, so what
// the Hub read from Google after the page was kept shows at once. It rebuilds the same markup (`reviews.fixture.json`
// holds it for both sides' tests) element by element with `textContent`, never `innerHTML`: an author's words stay
// text. A failed read (offline, the visit limit) or an answer with nothing to show keeps what is there. The browser
// never talks to Google: the Hub does. The editor's preview (`data-ep-preview`) is never refreshed.
import type { ReviewOut, ReviewsOut, StarKind } from '../operations';

export const REVIEWS_URL = '/api/website/public/reviews';

/** The class each star takes besides `ws-icon ws-icon-star`: on, half (site.css) or off. */
const STAR_CLASS: Record<StarKind, string> = { on: 'text-warning', half: 'ws-star-half', off: 'text-body-tertiary' };
const NEW_TAB = { target: '_blank', rel: 'noopener noreferrer' };

function element<K extends keyof HTMLElementTagNameMap>(tag: K, className = '', text?: string): HTMLElementTagNameMap[K] {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function link(className: string, href: string, text: string): HTMLAnchorElement {
  const anchor = element('a', className, text);
  anchor.setAttribute('href', href);
  for (const [name, value] of Object.entries(NEW_TAB)) anchor.setAttribute(name, value);
  return anchor;
}

/** Five stars in a row, read out as one label. */
function starRow(className: string, stars: StarKind[], label: string): HTMLElement {
  const row = element('div', className);
  row.setAttribute('role', 'img');
  row.setAttribute('aria-label', label);
  for (const star of stars) {
    const icon = element('span', `ws-icon ws-icon-star ${STAR_CLASS[star]}`);
    icon.setAttribute('aria-hidden', 'true');
    row.append(icon);
  }
  return row;
}

/** The summary, as `sections/reviews.html` paints it inside `[data-ep-reviews-summary]`: the rating, its stars and
 * the count. */
export function summaryNodes(view: ReviewsOut): HTMLElement[] {
  const nodes: HTMLElement[] = [];
  if (view.rating_label) nodes.push(element('span', 'display-5 fw-bold lh-1', view.rating_label));
  const column = element('div', 'd-flex flex-column gap-1');
  if (view.stars.length) column.append(starRow('d-flex gap-1 fs-5', view.stars, view.stars_label));
  column.append(element('span', 'small text-body-secondary', view.count_label));
  nodes.push(column);
  return nodes;
}

/** One review's card: the author's initial and name (linked to their profile), when (linked to the review), its
 * stars and its text (cut, with the whole of it in the title). */
function card(review: ReviewOut): HTMLElement {
  const col = element('div', 'col');
  const figure = element('figure', 'card h-100 border-0 rounded-4 shadow-sm mb-0');
  const body = element('div', 'card-body p-4 d-flex flex-column gap-3');
  const caption = element('figcaption', 'd-flex align-items-center gap-3');
  const initial = element('span', 'ws-glyph rounded-circle fw-semibold', review.initial);
  initial.setAttribute('aria-hidden', 'true');
  const who = element('span', 'd-flex flex-column');
  who.append(
    review.author_uri
      ? link('fw-semibold text-reset text-decoration-none', review.author_uri, review.author)
      : element('span', 'fw-semibold', review.author),
  );
  if (review.when) {
    who.append(review.uri ? link('small text-body-secondary', review.uri, review.when) : element('span', 'small text-body-secondary', review.when));
  }
  caption.append(initial, who);
  body.append(caption, starRow('d-flex gap-1', review.stars, review.stars_label));
  if (review.text) {
    const quote = element('blockquote', 'mb-0');
    const text = element('p', 'mb-0', review.text);
    if (review.full_text) text.setAttribute('title', review.full_text);
    quote.append(text);
    body.append(quote);
  }
  figure.append(body);
  col.append(figure);
  return col;
}

/** The cards, as `sections/reviews.html` paints them inside `[data-ep-reviews-list]`; none without reviews. */
export function listNodes(view: ReviewsOut): HTMLElement[] {
  if (!view.reviews.length) return [];
  const grid = element('div', 'row row-cols-1 row-cols-md-2 row-cols-lg-3 g-4');
  grid.append(...view.reviews.map(card));
  return [grid];
}

// The public page is not the SPA: no spa-config, no session, no SDK to go through. Its request is this GET of the
// public reviews, which needs none of them.
// eslint-disable-next-line no-restricted-globals -- see above
export async function hydrateReviews(doc: Document = document, fetchImpl: typeof fetch = fetch): Promise<void> {
  if (doc.body.hasAttribute('data-ep-preview')) return;
  const block = doc.querySelector<HTMLElement>('[data-ep-block="reviews"]');
  if (!block) return;
  let view: ReviewsOut;
  try {
    const response = await fetchImpl(REVIEWS_URL, { headers: { Accept: 'application/json' } });
    if (!response.ok) return; // What the server painted stays.
    view = (await response.json()) as ReviewsOut;
  } catch {
    return; // Offline or an unreadable answer: what the server painted stays, as above.
  }
  if (!view.available) return;
  block.querySelector('[data-ep-reviews-summary]')?.replaceChildren(...summaryNodes(view));
  block.querySelector('[data-ep-reviews-list]')?.replaceChildren(...listNodes(view));
}
