// `printPaper(source)`: the session's report printed through the browser without a single HTML string
// (Trusted Types and a strict CSP are on): a deep copy goes into a body-level print root, the browser
// prints, and the copy leaves on `afterprint`. print.css hides everything else on paper.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { PRINT_ROOT_CLASS, printPaper } from './print';

const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'print.css'), 'utf8');

function paper(): HTMLElement {
  const el = document.createElement('section');
  const title = document.createElement('h1');
  title.textContent = 'Cash closing (Z)';
  el.appendChild(title);
  document.body.appendChild(el);
  return el;
}

const roots = () => [...document.querySelectorAll(`body > .${PRINT_ROOT_CLASS}`)];

afterEach(() => {
  vi.restoreAllMocks();
  document.body.replaceChildren();
});

describe('printPaper', () => {
  it('prints a deep copy from a body-level root and removes it after printing', () => {
    const source = paper();
    let seen: Element[] = [];
    const print = vi.spyOn(window, 'print').mockImplementation(() => {
      seen = roots();
    });
    printPaper(source);
    expect(print).toHaveBeenCalledOnce();
    expect(seen).toHaveLength(1);
    expect(seen[0].firstElementChild?.outerHTML).toBe(source.outerHTML);
    expect(seen[0].firstElementChild).not.toBe(source);
    window.dispatchEvent(new Event('afterprint'));
    expect(roots()).toHaveLength(0);
  });

  it('a failed print leaves nothing behind and says so', () => {
    vi.spyOn(window, 'print').mockImplementation(() => {
      throw new Error('blocked');
    });
    expect(() => printPaper(paper())).toThrow('blocked');
    expect(roots()).toHaveLength(0);
  });

  it('hides everything but the copy on paper, and the copy on screen', () => {
    expect(css).toContain(`.${PRINT_ROOT_CLASS} {\n  display: none;`);
    expect(css).toMatch(new RegExp(`@media print \\{[\\s\\S]*body > :not\\(\\.${PRINT_ROOT_CLASS}\\)`));
  });
});
