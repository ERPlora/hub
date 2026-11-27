// flow: e2e-text-cut — the e2e's measure of a text cut by its box (screens-text-fits.spec.ts walks the screens with it).
// Each case puts a small page together and expects `cutTexts` to name what a person cannot read whole: a text cut
// with no «…», one that ends in «…» with no title to read it, and a short word split over two lines; and to leave
// alone what is whole, what a title gives whole, what scrolls, what is hidden on purpose and a form field's value.
import { expect, type Page, test } from '@playwright/test';

import { type CutText, cutTexts, measureInOneFont } from './text-cut';

/** A page of `body` at 390 × 844, in the font of the Hub's pages. */
async function pageOf(page: Page, body: string): Promise<CutText[]> {
  await page.setViewportSize({ width: 390, height: 844 });
  await page.setContent(`<!doctype html><html lang="es"><body style="margin: 0; font: 16px/1.25 sans-serif">${body}</body></html>`);
  return cutTexts(page);
}

const LONG = 'María del Carmen Fernández-Villaverde';
const NOWRAP = 'white-space: nowrap; overflow: hidden';

test.describe('cutTexts: the texts a person cannot read whole', () => {
  test('e2e-text-cut: a text cut by its box with no «…» is cut; the same box with room is not', async ({ page }) => {
    expect(await pageOf(page, `<div data-testid="who" style="width: 60px; ${NOWRAP}">${LONG}</div>`)).toEqual([
      { kind: 'cut', box: 'div[data-testid=who]', text: LONG },
    ]);
    expect(await pageOf(page, `<div style="width: 360px; ${NOWRAP}">${LONG}</div>`)).toEqual([]);
    const titled = await pageOf(page, `<div data-testid="who" title="${LONG}" style="width: 60px; ${NOWRAP}">${LONG}</div>`);
    expect(titled, 'with no «…» nothing says there is more: a title does not make it whole').toEqual([
      { kind: 'cut', box: 'div[data-testid=who]', text: LONG },
    ]);
  });

  test('e2e-text-cut: a text in a box two levels up, and a flex box that cannot draw «…», are cut', async ({ page }) => {
    const nested = await pageOf(page, `<button class="slot" style="width: 50px; ${NOWRAP}"><strong>Lucía Gómez</strong></button>`);
    expect(nested).toEqual([{ kind: 'cut', box: 'button.slot', text: 'Lucía Gómez' }]);
    const flex = await pageOf(page, `<div class="chip" style="display: flex; width: 70px; ${NOWRAP}; text-overflow: ellipsis">Productos de venta</div>`);
    expect(flex).toEqual([{ kind: 'cut', box: 'div.chip', text: 'Productos de venta' }]);
  });

  test('e2e-text-cut: «…» with no title is cut short; a title with the whole text, on it or above, reads it', async ({ page }) => {
    const ellipsis = `${NOWRAP}; text-overflow: ellipsis; width: 80px`;
    expect(await pageOf(page, `<h1 class="title" style="${ellipsis}">Automatizaciones</h1>`)).toEqual([
      { kind: 'ellipsis', box: 'h1.title', text: 'Automatizaciones' },
    ]);
    expect(await pageOf(page, `<h1 title="Automatizaciones" style="${ellipsis}">Automatizaciones</h1>`)).toEqual([]);
    expect(await pageOf(page, `<button title="10:00 ${LONG} — Corte"><span style="display: block; ${ellipsis}">${LONG}</span></button>`)).toEqual([]);
    expect(await pageOf(page, `<button title="Otra cosa"><span style="display: block; ${ellipsis}">${LONG}</span></button>`)).toEqual([
      { kind: 'ellipsis', box: 'span', text: LONG },
    ]);
  });

  test('e2e-text-cut: a line that pokes a pixel past its box is whole; one half hidden is cut', async ({ page }) => {
    const twoLines = (height: number) =>
      `<button class="tab" style="display: block; width: 70px; height: ${height}px; padding: 0; overflow: hidden; font: 13px/15px sans-serif">Lista de espera</button>`;
    expect(await pageOf(page, twoLines(29))).toEqual([]);
    expect(await pageOf(page, twoLines(22))).toEqual([{ kind: 'cut', box: 'button.tab', text: 'Lista de espera' }]);
  });

  test('e2e-text-cut: lines past a line clamp are cut short, unless a title gives them', async ({ page }) => {
    const clamp = 'display: -webkit-box; -webkit-box-orient: vertical; -webkit-line-clamp: 2; overflow: hidden; width: 140px';
    const text = 'Corte de mujer con lavado, peinado y tratamiento de brillo';
    expect(await pageOf(page, `<p class="name" style="${clamp}">${text}</p>`)).toEqual([{ kind: 'ellipsis', box: 'p.name', text }]);
    expect(await pageOf(page, `<p title="${text}" style="${clamp}">${text}</p>`)).toEqual([]);
  });

  test('e2e-text-cut: a short word split over two lines is split; a long token broken anywhere is not', async ({ page }) => {
    expect(await pageOf(page, '<div class="head" style="width: 40px; overflow-wrap: anywhere">Profesional</div>')).toEqual([
      { kind: 'split-word', box: 'div.head', text: 'Profesional' },
    ]);
    expect(await pageOf(page, '<div style="width: 60px; overflow-wrap: anywhere">https://erplora.com/p/salon-aurora/book</div>')).toEqual([]);
  });

  test('e2e-text-cut: what scrolls, what is hidden on purpose and a folded box are not cut', async ({ page }) => {
    const scroller = `<div style="width: 80px; overflow-x: auto; white-space: nowrap"><span>${LONG}</span></div>`;
    const srOnly = `<span style="position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0 0 0 0)">${LONG}</span>`;
    const folded = `<div style="height: 0; overflow: hidden"><p>${LONG}</p></div>`;
    const off = `<div style="display: none; width: 40px; ${NOWRAP}">${LONG}</div>`;
    expect(await pageOf(page, scroller + srOnly + folded + off)).toEqual([]);
  });

  test('e2e-text-cut: a text slotted into a web component is named through its host', async ({ page }) => {
    await pageOf(page, '<x-title data-testid="topbar">Automatizaciones</x-title>');
    await page.evaluate(() => {
      const host = document.querySelector('x-title') as HTMLElement;
      const root = host.attachShadow({ mode: 'open' });
      root.innerHTML = '<div class="toolbar-title" style="width: 70px; white-space: nowrap; overflow: hidden"><slot></slot></div>';
    });
    expect(await cutTexts(page)).toEqual([{ kind: 'cut', box: 'x-title[data-testid=topbar] >> div.toolbar-title', text: 'Automatizaciones' }]);
  });

  test('e2e-text-cut: the value an ion-select shows is the field’s, read whole by opening it', async ({ page }) => {
    await pageOf(page, '<x-select></x-select>');
    await page.evaluate((long) => {
      const host = document.querySelector('x-select') as HTMLElement;
      const root = host.attachShadow({ mode: 'open' });
      root.innerHTML = `<div part="text" style="width: 60px; white-space: nowrap; overflow: hidden; text-overflow: ellipsis">${long}</div>`;
    }, LONG);
    expect(await cutTexts(page), 'a field that is not an ion-select is measured').toHaveLength(1);
    await page.evaluate(() => {
      const old = document.querySelector('x-select') as HTMLElement;
      const select = document.createElement('ion-select');
      select.attachShadow({ mode: 'open' }).innerHTML = old.shadowRoot?.innerHTML ?? '';
      old.replaceWith(select);
    });
    expect(await cutTexts(page)).toEqual([]);
  });
});

test('e2e-text-cut: every page of the measure, also after it reloads itself, is drawn in Arial', async ({ browser }) => {
  const context = await browser.newContext();
  try {
    await measureInOneFont(context);
    const page = await context.newPage();
    const fontOf = () => page.evaluate(() => getComputedStyle(document.documentElement).getPropertyValue('--ion-font-family'));
    await page.goto('data:text/html,<!doctype html><html><body>Agenda</body></html>');
    expect(await fontOf()).toContain('Arial');
    await page.reload();
    expect(await fontOf(), 'after the page reloads itself').toContain('Arial');
  } finally {
    await context.close();
  }
});
