// @vitest-environment happy-dom
// sales#335 — the one script the public invoice page (`/p/<locator>`, served by the Rust core)
// loads: it names the ISO country codes the server lists, in the page's language, with the
// customer's own `Intl.DisplayNames`. It lives in `crates/server/assets/` and is `include_str!`-ed
// into the binary; this is the hub's only JS runner, so its behaviour is pinned here.
import { describe, it, expect, beforeEach } from 'vitest';
import { readFileSync } from 'node:fs';
import { dirname, resolve } from 'node:path';
import { fileURLToPath } from 'node:url';

// `path`, not `new URL(…, import.meta.url)`: under happy-dom `URL` is the DOM's, not Node's.
const SCRIPT = readFileSync(
  resolve(dirname(fileURLToPath(import.meta.url)), '../../../crates/server/assets/public-claim-names.js'),
  'utf8',
);

function renderPage(lang: string, codes: string[]): HTMLSelectElement {
  document.documentElement.lang = lang;
  const home = lang === 'en' ? 'Spain' : 'España';
  document.body.innerHTML =
    `<select id="f-customer_country" name="customer_country" data-names="region"><option value="" selected>${home}</option>` +
    codes.map((c) => `<option value="${c}">${c}</option>`).join('') +
    '</select>';
  new Function(SCRIPT)();
  return document.getElementById('f-customer_country') as HTMLSelectElement;
}

const labels = (select: HTMLSelectElement) => Array.from(select.options).map((o) => o.textContent);
const values = (select: HTMLSelectElement) => Array.from(select.options).map((o) => o.value);

describe('public claim page — country names (sales#335)', () => {
  beforeEach(() => {
    document.body.innerHTML = '';
  });

  it('names every code in the page language, keeping the value the form posts', () => {
    const select = renderPage('es', ['US', 'DE']);
    const names = new Intl.DisplayNames(['es'], { type: 'region' });
    expect(labels(select)).toContain(names.of('DE'));
    expect(labels(select)).toContain(names.of('US'));
    expect(values(select).sort()).toEqual(['', 'DE', 'US']);
  });

  it('keeps the home country first and selected, and sorts the rest by name', () => {
    // By code: DE < GB < US. By Spanish name: Alemania < Estados Unidos < Reino Unido.
    const select = renderPage('es', ['DE', 'GB', 'US']);
    expect(values(select)).toEqual(['', 'DE', 'US', 'GB']);
    expect(select.value).toBe('');
    expect(select.options[0].textContent).toBe('España');
  });

  it('follows the page language, not a fixed one', () => {
    const select = renderPage('en', ['DE', 'GB', 'US']);
    expect(labels(select)).toEqual(['Spain', 'Germany', 'United Kingdom', 'United States']);
  });

  it('keeps a label the module already gave, and leaves selects that did not ask alone', () => {
    document.documentElement.lang = 'es';
    document.body.innerHTML =
      '<select id="a" data-names="region"><option value="" selected>Casa</option>' +
      '<option value="FR">Mi Francia</option><option value="DE">DE</option></select>' +
      '<select id="b"><option value="">-</option><option value="US">US</option></select>';
    new Function(SCRIPT)();
    const a = document.getElementById('a') as HTMLSelectElement;
    expect(labels(a)).toEqual(['Casa', new Intl.DisplayNames(['es'], { type: 'region' }).of('DE'), 'Mi Francia']);
    expect(labels(document.getElementById('b') as HTMLSelectElement)).toEqual(['-', 'US']);
  });

  it('leaves the page alone when it has no country picker', () => {
    document.body.innerHTML = '<form><input name="customer_tax_id"></form>';
    expect(() => new Function(SCRIPT)()).not.toThrow();
    expect(document.body.innerHTML).toBe('<form><input name="customer_tax_id"></form>');
  });
});
