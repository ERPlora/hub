// `printPaper(source, options)`: the session's report. Inside the installed app it goes to the app's print screen
// (`print_document`, hub#455: the webview prints nothing on `window.print()`). In a browser it is printed without a
// single HTML string (Trusted Types and a strict CSP are on): a deep copy goes into a body-level print root, the
// browser prints, and the copy leaves on `afterprint`. print.css hides everything else on paper.
import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { afterEach, describe, expect, it, vi } from 'vitest';

import { PRINT_DOCUMENT_COMMAND, PrintRefused } from '../../../../base/frontend/lib/print-paper';
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

const REPORT = { title: 'Cash closing (Z) S-1' };

type Invoke = (command: string, args?: unknown) => Promise<unknown>;
type TauriWindow = { __TAURI__?: { core: { invoke: Invoke } } };

/** The installed app's bridge, as the app puts it on the page. */
function inTheApp(invoke: Invoke): void {
  (window as TauriWindow).__TAURI__ = { core: { invoke } };
}

afterEach(() => {
  vi.restoreAllMocks();
  delete (window as TauriWindow).__TAURI__;
  document.body.replaceChildren();
});

describe('printPaper', () => {
  it('prints a deep copy from a body-level root and removes it after printing', async () => {
    const source = paper();
    let seen: Element[] = [];
    const print = vi.spyOn(window, 'print').mockImplementation(() => {
      seen = roots();
    });
    await printPaper(source, REPORT);
    expect(print).toHaveBeenCalledOnce();
    expect(seen).toHaveLength(1);
    expect(seen[0].firstElementChild?.outerHTML).toBe(source.outerHTML);
    expect(seen[0].firstElementChild).not.toBe(source);
    window.dispatchEvent(new Event('afterprint'));
    expect(roots()).toHaveLength(0);
  });

  it('a failed print leaves nothing behind and says so', async () => {
    vi.spyOn(window, 'print').mockImplementation(() => {
      throw new Error('blocked');
    });
    await expect(printPaper(paper(), REPORT)).rejects.toThrow('blocked');
    expect(roots()).toHaveLength(0);
  });

  it("inside the installed app, the report goes to the app's print screen and the browser's dialog stays shut", async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    const invoke = vi.fn<Invoke>(async () => null);
    inTheApp(invoke);
    await printPaper(paper(), REPORT);
    expect(print).not.toHaveBeenCalled();
    expect(invoke).toHaveBeenCalledOnce();
    const [command, args] = invoke.mock.calls[0];
    expect(command).toBe(PRINT_DOCUMENT_COMMAND);
    const html = (args as { html: string }).html;
    expect(html).toContain('<title>Cash closing (Z) S-1</title>');
    expect(html).toContain('<h1>Cash closing (Z)</h1>');
    expect(roots()).toHaveLength(0);
  });

  it("an app with no print screen on this system leaves it to the browser's dialog", async () => {
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    inTheApp(async () => Promise.reject('native_print_unsupported'));
    await printPaper(paper(), REPORT);
    expect(print).toHaveBeenCalledOnce();
  });

  it('a refusal of the app comes back with its reason, and the browser is not asked', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const print = vi.spyOn(window, 'print').mockImplementation(() => {});
    inTheApp(async () => Promise.reject('print_document_refused'));
    const refused = await printPaper(paper(), REPORT).catch((error: unknown) => error);
    expect(refused).toBeInstanceOf(PrintRefused);
    expect((refused as PrintRefused).reason).toBe('refused');
    expect(print).not.toHaveBeenCalled();
  });

  it('hides everything but the copy on paper, and the copy on screen', () => {
    expect(css).toContain(`.${PRINT_ROOT_CLASS} {\n  display: none;`);
    expect(css).toMatch(new RegExp(`@media print \\{[\\s\\S]*body > :not\\(\\.${PRINT_ROOT_CLASS}\\)`));
  });
});
