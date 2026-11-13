// INVENTORY-F25: without the print queue, the label is printed on the device: a sheet with the code, the SKU and
// the name (no price). Inside the installed app it goes to the app's print screen (`print_document`, hub#455: the
// webview prints nothing on `window.print()`). In a browser its print dialog shows only that sheet, built with the
// DOM (Trusted Types: no HTML strings), and the sheet goes once the dialog closes.
import { afterEach, describe, expect, it, vi } from 'vitest';

import { PRINT_DOCUMENT_COMMAND, PrintRefused } from '../../../../base/frontend/lib/print-paper';
import { printLabel } from './print-label';

type Invoke = (command: string, args?: unknown) => Promise<unknown>;
type TauriWindow = { __TAURI__?: { core: { invoke: Invoke } } };

/** The installed app's bridge, as the app puts it on the page. */
function inTheApp(invoke: Invoke): void {
  (window as TauriWindow).__TAURI__ = { core: { invoke } };
}

afterEach(() => {
  delete (window as TauriWindow).__TAURI__;
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

describe('printLabel', () => {
  it('in a browser, prints only a sheet with a copy of the code, the SKU and the name, then takes it away', async () => {
    const svg = plate();
    let sheet: HTMLElement | null = null;
    let rules = '';
    vi.spyOn(window, 'print').mockImplementation(() => {
      sheet = document.querySelector<HTMLElement>('[data-testid=inventory-label-print]');
      rules = Array.from(document.querySelectorAll('style'), (style) => style.textContent).join('\n');
    });

    await printLabel(svg, { sku: 'SHA-250', name: 'Shampoo' });

    expect(window.print).toHaveBeenCalledOnce();
    expect(sheet!.parentElement).toBe(document.body);
    expect(sheet!.querySelector('svg rect')).not.toBeNull();
    expect(sheet!.textContent).toContain('SHA-250');
    expect(sheet!.textContent).toContain('Shampoo');
    // On paper, everything but the sheet is hidden; on screen, the sheet never shows.
    expect(rules).toContain('@media print');
    expect(rules).toContain('body > :not([data-testid="inventory-label-print"])');
    expect(rules).toContain('@media screen');
    // Black on a white sheet whatever the theme, so the scanner reads the printed label.
    expect(rules).toMatch(/\[data-testid="inventory-label-print"\] \{[^}]*color: #000; background: #fff;/);
    // The original plate stays where it was.
    expect(document.querySelector('main [data-testid=plate]')).toBe(svg);

    window.dispatchEvent(new Event('afterprint'));
    expect(document.querySelector('[data-testid=inventory-label-print]')).toBeNull();
    expect(document.querySelectorAll('style')).toHaveLength(0);
  });

  it("inside the installed app, the sheet goes to the app's print screen, and nothing is added to the page", async () => {
    const svg = plate();
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    const invoke = vi.fn<Invoke>(async () => null);
    inTheApp(invoke);

    await printLabel(svg, { sku: 'SHA-250', name: 'Shampoo' });

    expect(print).not.toHaveBeenCalled();
    expect(invoke).toHaveBeenCalledOnce();
    const [command, args] = invoke.mock.calls[0];
    expect(command).toBe(PRINT_DOCUMENT_COMMAND);
    const doc = new DOMParser().parseFromString((args as { html: string }).html, 'text/html');
    expect(doc.title).toBe('SHA-250 Shampoo');
    const sheet = doc.body.firstElementChild as HTMLElement;
    expect(sheet.dataset.testid).toBe('inventory-label-print');
    expect(sheet.querySelector('svg rect')).not.toBeNull();
    expect(sheet.textContent).toContain('SHA-250');
    expect(sheet.textContent).toContain('Shampoo');
    const rules = doc.head.querySelector('style')?.textContent ?? '';
    // Black on a white sheet, shown (the document is the sheet alone: nothing to hide on screen or on paper).
    expect(rules).toMatch(/\[data-testid="inventory-label-print"\] \{[^}]*color: #000; background: #fff;/);
    expect(rules).not.toContain('display: none');
    expect(document.querySelector('[data-testid=inventory-label-print]')).toBeNull();
    expect(document.querySelectorAll('style')).toHaveLength(0);
  });

  it("an app with no print screen on this system leaves it to the browser's dialog", async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    inTheApp(async () => Promise.reject('native_print_unsupported'));
    await printLabel(plate(), { sku: 'SHA-250', name: 'Shampoo' });
    expect(print).toHaveBeenCalledOnce();
  });

  it('a refusal of the app comes back with its reason', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    inTheApp(async () => Promise.reject('not_the_linked_hub'));
    const refused = await printLabel(plate(), { sku: 'SHA-250', name: 'Shampoo' }).catch((error: unknown) => error);
    expect(refused).toBeInstanceOf(PrintRefused);
    expect((refused as PrintRefused).reason).toBe('unlinked');
  });
});
