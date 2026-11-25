// `printPaper(paper, options)`: prints one paper of any app on the device. Inside the installed app it goes to the app's
// print screen; in a browser a deep copy of the paper goes into a body-level root, the body is marked as printing, the
// browser prints, and both leave on `afterprint`. The stylesheet only hides the page while the body is marked, so it
// never blanks another app's paper printed later, and the marked root shows even where another app's always-on print
// rule hides everything but its own root.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { PRINT_ROOT_CLASS, PRINTING_CLASS, printPaper } from './print';
import { PRINT_DOCUMENT_COMMAND, PrintRefused } from './print-paper';

// Read from disk: Vitest empties a stylesheet imported in a test.
const css = readFileSync(join(dirname(fileURLToPath(import.meta.url)), 'print.css'), 'utf8').replace(/\s+/g, ' ');

function paper(): HTMLElement {
  const el = document.createElement('section');
  el.className = 'sheet';
  el.innerHTML = '<h1>Table 4</h1><img src="data:image/png;base64,AAAA" alt="">';
  document.body.appendChild(el);
  return el;
}

const roots = () => [...document.querySelectorAll(`body > .${PRINT_ROOT_CLASS}`)];
const marked = () => document.body.classList.contains(PRINTING_CLASS);

const SHEET = { title: 'QR codes' };

type Invoke = (command: string, args?: unknown) => Promise<unknown>;
type TauriWindow = { __TAURI__?: { core: { invoke: Invoke } } };

function inTheApp(invoke: Invoke): void {
  (window as TauriWindow).__TAURI__ = { core: { invoke } };
}

afterEach(() => {
  vi.restoreAllMocks();
  delete (window as TauriWindow).__TAURI__;
  document.body.innerHTML = '';
  document.body.className = '';
});

describe('printPaper', () => {
  it('prints a deep copy from a body-level root with the body marked, and clears both on afterprint', async () => {
    const source = paper();
    let seen: { roots: Element[]; marked: boolean } = { roots: [], marked: false };
    const print = vi.spyOn(window, 'print').mockImplementation(() => {
      seen = { roots: roots(), marked: marked() };
    });
    await printPaper(source, SHEET);
    expect(print).toHaveBeenCalledOnce();
    expect(seen.marked).toBe(true);
    expect(seen.roots).toHaveLength(1);
    const copy = seen.roots[0].firstElementChild as HTMLElement;
    expect(copy).not.toBe(source);
    expect(copy.outerHTML).toBe(source.outerHTML);
    expect(source.isConnected).toBe(true);
    window.dispatchEvent(new Event('afterprint'));
    expect(roots()).toHaveLength(0);
    expect(marked()).toBe(false);
  });

  it('never builds the copy from an HTML string (Trusted Types)', async () => {
    const source = paper();
    vi.spyOn(window, 'print').mockImplementation(() => {});
    const innerHTML = vi.spyOn(Element.prototype, 'innerHTML', 'set');
    const insertAdjacentHTML = vi.spyOn(Element.prototype, 'insertAdjacentHTML');
    await printPaper(source, SHEET);
    expect(innerHTML).not.toHaveBeenCalled();
    expect(insertAdjacentHTML).not.toHaveBeenCalled();
  });

  it('a second print replaces a copy a previous one left behind', async () => {
    vi.spyOn(window, 'print').mockImplementation(() => {});
    await printPaper(paper(), SHEET);
    await printPaper(paper(), SHEET);
    expect(roots()).toHaveLength(1);
  });

  it('takes the copy and the mark away and rethrows when the browser cannot print', async () => {
    vi.spyOn(window, 'print').mockImplementation(() => {
      throw new Error('blocked');
    });
    await expect(printPaper(paper(), SHEET)).rejects.toThrow('blocked');
    expect(roots()).toHaveLength(0);
    expect(marked()).toBe(false);
  });

  it("inside the installed app, the paper goes to the app's print screen and the browser's dialog stays shut", async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    const invoke = vi.fn<Invoke>(async () => null);
    inTheApp(invoke);
    await printPaper(paper(), SHEET);
    expect(print).not.toHaveBeenCalled();
    const [command, args] = invoke.mock.calls[0];
    expect(command).toBe(PRINT_DOCUMENT_COMMAND);
    expect((args as { html: string }).html).toContain('<title>QR codes</title>');
    expect(roots()).toHaveLength(0);
    expect(marked()).toBe(false);
  });

  it('a refusal of the app comes back with its reason, and the browser is not asked', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    inTheApp(async () => Promise.reject('native_print_failed: no print service'));
    const refused = await printPaper(paper(), SHEET).catch((error: unknown) => error);
    expect(refused).toBeInstanceOf(PrintRefused);
    expect(print).not.toHaveBeenCalled();
  });

  it('its stylesheet hides the page only while the body is marked, and shows the root over any other rule', () => {
    expect(css).toMatch(/\.ep-print-root \{ display: none;? \}/);
    expect(css).toContain('@media print');
    expect(css).toMatch(/body\.ep-printing > :not\(\.ep-print-root\) \{ display: none !important;? \}/);
    expect(css).toMatch(/body\.ep-printing > \.ep-print-root \{ display: block !important;? \}/);
    // No rule hides the page while nothing of this module prints: another app's paper prints as before.
    expect(css).not.toMatch(/(^|[ }])body > :not/);
    expect(css).not.toContain('@page');
  });
});
