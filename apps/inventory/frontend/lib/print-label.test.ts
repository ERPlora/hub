// INVENTORY-F25: without the print queue, the label is printed from the browser: its print dialog shows only
// a sheet with the code, the SKU and the name (no price), built with the DOM (Trusted Types: no HTML strings),
// and the sheet goes once the dialog closes.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { printInBrowser } from './print-label';

afterEach(() => {
  document.head.innerHTML = '';
  document.body.innerHTML = '';
  vi.restoreAllMocks();
});

function plate(): SVGSVGElement {
  const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
  svg.setAttribute('data-testid', 'plate');
  svg.appendChild(document.createElementNS('http://www.w3.org/2000/svg', 'rect'));
  const app = document.createElement('main');
  app.appendChild(svg);
  document.body.appendChild(app);
  return svg;
}

describe('printInBrowser', () => {
  it('prints only a sheet with a copy of the code, the SKU and the name, then takes it away', () => {
    const svg = plate();
    let sheet: HTMLElement | null = null;
    let rules = '';
    vi.spyOn(window, 'print').mockImplementation(() => {
      sheet = document.querySelector<HTMLElement>('[data-testid=inventory-label-print]');
      rules = Array.from(document.querySelectorAll('style'), (style) => style.textContent).join('\n');
    });

    printInBrowser(svg, { sku: 'SHA-250', name: 'Shampoo' });

    expect(window.print).toHaveBeenCalledOnce();
    expect(sheet!.parentElement).toBe(document.body);
    expect(sheet!.querySelector('svg rect')).not.toBeNull();
    expect(sheet!.textContent).toContain('SHA-250');
    expect(sheet!.textContent).toContain('Shampoo');
    // On paper, everything but the sheet is hidden; on screen, the sheet never shows.
    expect(rules).toContain('@media print');
    expect(rules).toContain('body > :not([data-testid="inventory-label-print"])');
    expect(rules).toContain('@media screen');
    // Black on a white sheet whatever the theme, so the scanner reads the printed label (inventory#45).
    expect(rules).toMatch(/\[data-testid="inventory-label-print"\] \{[^}]*color: #000; background: #fff;/);
    // The original plate stays where it was.
    expect(document.querySelector('main [data-testid=plate]')).toBe(svg);

    window.dispatchEvent(new Event('afterprint'));
    expect(document.querySelector('[data-testid=inventory-label-print]')).toBeNull();
    expect(document.querySelectorAll('style')).toHaveLength(0);
  });
});
