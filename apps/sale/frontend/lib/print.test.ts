// `printPaper(source, options)`: one paper (a receipt, the till's bill). Inside the installed app it goes to the
// app's print screen (`print_document`, hub#455: the webview prints nothing on `window.print()`). In a browser it is
// printed without a single HTML string (Trusted Types and a strict CSP are on): a deep copy of the paper goes into a
// body-level `.sale-print-root`, the browser prints, and the copy leaves on `afterprint`. The print
// stylesheet (bundled with this module, never a style element made by script) hides everything else
// on paper and the copy on screen.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { PRINT_DOCUMENT_COMMAND, PrintRefused } from '../../../../base/frontend/lib/print-paper';
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

const BILL = { title: 'Bill' };

type Invoke = (command: string, args?: unknown) => Promise<unknown>;
type TauriWindow = { __TAURI__?: { core: { invoke: Invoke } } };

/** The installed app's bridge, as the app puts it on the page. */
function inTheApp(invoke: Invoke): void {
  (window as TauriWindow).__TAURI__ = { core: { invoke } };
}

afterEach(() => {
  vi.restoreAllMocks();
  delete (window as TauriWindow).__TAURI__;
  document.body.innerHTML = '';
});

describe('printPaper', () => {
  it('prints a deep copy of the paper from a body-level print root, and leaves it there until afterprint', async () => {
    const source = paper();
    let seen: Element[] = [];
    const print = vi.spyOn(window, 'print').mockImplementation(() => {
      seen = roots();
    });
    await printPaper(source, BILL);
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

  it('never builds the copy from an HTML string (Trusted Types)', async () => {
    const source = paper();
    vi.spyOn(window, 'print').mockImplementation(() => {});
    const innerHTML = vi.spyOn(Element.prototype, 'innerHTML', 'set');
    const insertAdjacentHTML = vi.spyOn(Element.prototype, 'insertAdjacentHTML');
    await printPaper(source, BILL);
    expect(innerHTML).not.toHaveBeenCalled();
    expect(insertAdjacentHTML).not.toHaveBeenCalled();
  });

  it('a second print replaces a copy a previous one left behind', async () => {
    vi.spyOn(window, 'print').mockImplementation(() => {});
    await printPaper(paper(), BILL);
    await printPaper(paper(), BILL);
    expect(roots()).toHaveLength(1);
  });

  it('takes the copy away and says so when the browser cannot print', async () => {
    vi.spyOn(window, 'print').mockImplementation(() => {
      throw new Error('blocked');
    });
    await expect(printPaper(paper(), BILL)).rejects.toThrow('blocked');
    expect(roots()).toHaveLength(0);
  });

  it("inside the installed app, the paper goes to the app's print screen and the browser's dialog stays shut", async () => {
    const source = paper();
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    const invoke = vi.fn<Invoke>(async () => null);
    inTheApp(invoke);
    await printPaper(source, BILL);
    expect(print).not.toHaveBeenCalled();
    expect(invoke).toHaveBeenCalledOnce();
    const [command, args] = invoke.mock.calls[0];
    expect(command).toBe(PRINT_DOCUMENT_COMMAND);
    const html = (args as { html: string }).html;
    expect(html).toContain('<title>Bill</title>');
    expect(html).toContain('TOTAL <b>12,50 €</b>');
    expect(roots()).toHaveLength(0);
  });

  it("an app with no print screen on this system leaves it to the browser's dialog", async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    inTheApp(async () => Promise.reject('native_print_unsupported'));
    await printPaper(paper(), BILL);
    expect(print).toHaveBeenCalledOnce();
  });

  it('a refusal of the app comes back with its reason, and the browser is not asked', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    inTheApp(async () => Promise.reject('native_print_failed: no print service'));
    const refused = await printPaper(paper(), BILL).catch((error: unknown) => error);
    expect(refused).toBeInstanceOf(PrintRefused);
    expect((refused as PrintRefused).reason).toBe('failed');
    expect(print).not.toHaveBeenCalled();
    expect(roots()).toHaveLength(0);
  });

  it('its stylesheet hides everything but the copy on paper, and the copy on screen', () => {
    const flat = css.replace(/\s+/g, ' ');
    expect(flat).toContain('@media print');
    expect(flat).toMatch(/body > :not\(\.sale-print-root\) \{ display: none !important;? \}/);
    expect(flat).toMatch(/\.sale-print-root \{ display: none;? \}/);
  });
});
