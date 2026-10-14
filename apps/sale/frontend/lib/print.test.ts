// `printPaper(source)`: one paper (a receipt, the till's bill) printed through the browser without a
// single HTML string (Trusted Types and a strict CSP are on): a deep copy of the paper goes into a
// body-level `.sale-print-root`, the browser prints, and the copy leaves on `afterprint`. The print
// stylesheet (bundled with this module, never a style element made by script) hides everything else
// on paper and the copy on screen.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { PRINT_ROOT_CLASS, printPaper } from './print';

// Read from disk: Vitest empties a stylesheet imported in a test (`?raw` included).
const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'print.css'), 'utf8');

function paper(): HTMLElement {
  const el = document.createElement('section');
  el.className = 'receipt';
  el.innerHTML = '<h1>Mi negocio</h1><p>TOTAL <b>12,50 €</b></p>';
  document.body.appendChild(el);
  return el;
}

const roots = () => [...document.querySelectorAll(`body > .${PRINT_ROOT_CLASS}`)];

afterEach(() => {
  vi.restoreAllMocks();
  document.body.innerHTML = '';
});

describe('printPaper', () => {
  it('prints a deep copy of the paper from a body-level print root, and leaves it there until afterprint', () => {
    const source = paper();
    let seen: Element[] = [];
    const print = vi.spyOn(window, 'print').mockImplementation(() => {
      seen = roots();
    });
    printPaper(source);
    expect(print).toHaveBeenCalledOnce();
    expect(seen).toHaveLength(1);
    const copy = seen[0].firstElementChild as HTMLElement;
    expect(copy).not.toBe(source);
    expect(copy.outerHTML).toBe(source.outerHTML);
    // The original paper stays where it was.
    expect(source.isConnected).toBe(true);
    expect(roots()).toHaveLength(1);
    window.dispatchEvent(new Event('afterprint'));
    expect(roots()).toHaveLength(0);
  });

  it('never builds the copy from an HTML string (Trusted Types)', () => {
    const source = paper();
    vi.spyOn(window, 'print').mockImplementation(() => {});
    const innerHTML = vi.spyOn(Element.prototype, 'innerHTML', 'set');
    const insertAdjacentHTML = vi.spyOn(Element.prototype, 'insertAdjacentHTML');
    printPaper(source);
    expect(innerHTML).not.toHaveBeenCalled();
    expect(insertAdjacentHTML).not.toHaveBeenCalled();
  });

  it('a second print replaces a copy a previous one left behind', () => {
    vi.spyOn(window, 'print').mockImplementation(() => {});
    printPaper(paper());
    printPaper(paper());
    expect(roots()).toHaveLength(1);
  });

  it('takes the copy away and says so when the browser cannot print', () => {
    vi.spyOn(window, 'print').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() => printPaper(paper())).toThrow('blocked');
    expect(roots()).toHaveLength(0);
  });

  it('its stylesheet hides everything but the copy on paper, and the copy on screen', () => {
    const flat = css.replace(/\s+/g, ' ');
    expect(flat).toContain('@media print');
    expect(flat).toMatch(/body > :not\(\.sale-print-root\) \{ display: none !important;? \}/);
    expect(flat).toMatch(/\.sale-print-root \{ display: none;? \}/);
  });
});
