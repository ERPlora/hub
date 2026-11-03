// The paper printed inside the installed app (hub#455): `window.print()` prints nothing in the app's webview, so the
// paper goes to the app's own print screen instead — ERPlora/app's `print_document` command, which takes a whole HTML
// document and opens the system's print dialog with it (a printer or «Save as PDF»; Android's PrintManager, the
// desktop's print window). The document is the paper alone and stands on its own: the page's styles that dress the
// paper, inline (the print window allows no stylesheet and runs no script), and its images at an address the print
// window can reach. A refusal of the app comes back with its reason, which the caller says.
import { afterEach, describe, expect, it, vi } from 'vitest';

import {
  paperDocument,
  PRINT_DOCUMENT_COMMAND,
  printInTheApp,
  PrintRefused,
  printRefusal,
  withReason,
} from './print-paper';

type Invoke = (command: string, args?: unknown) => Promise<unknown>;

const STYLES = `
.receipt { width: 80mm; color: #000; }
.receipt__total b { font-weight: 700; }
.receipt::after { content: ''; display: block; }
.somewhere-else { color: red; }
body { position: fixed; overflow: hidden; }
@media print { .receipt { padding: 2mm; } .somewhere-else { display: none; } }
@media (max-width: 1px) { .not-the-paper { color: blue; } }
`;

function page(): HTMLElement {
  const style = document.createElement('style');
  style.textContent = STYLES;
  document.head.appendChild(style);
  const paper = document.createElement('section');
  paper.className = 'receipt';
  const title = document.createElement('h1');
  title.textContent = 'Mi negocio';
  const total = document.createElement('p');
  total.className = 'receipt__total';
  total.append('TOTAL ', Object.assign(document.createElement('b'), { textContent: '12,50 €' }));
  const qr = document.createElement('img');
  qr.setAttribute('src', 'data:image/svg+xml;base64,PHN2Zy8+');
  qr.setAttribute('alt', 'QR');
  const logo = document.createElement('img');
  logo.setAttribute('src', '/media/logo.png');
  logo.setAttribute('loading', 'lazy');
  logo.setAttribute('alt', 'Logo');
  paper.append(title, total, qr, logo);
  document.body.appendChild(paper);
  return paper;
}

function inTheApp(invoke: Invoke): object {
  return { __TAURI__: { core: { invoke } } };
}

afterEach(() => {
  vi.restoreAllMocks();
  document.head.innerHTML = '';
  document.body.innerHTML = '';
});

describe('paperDocument', () => {
  it('is a whole HTML page with the paper alone, its title and its language', () => {
    const html = paperDocument(page(), { title: 'Tique T-1', lang: 'es' });
    expect(html.startsWith('<!doctype html>')).toBe(true);
    expect(html).toContain('<html lang="es">');
    expect(html).toContain('<meta charset="utf-8">');
    expect(html).toContain('<title>Tique T-1</title>');
    const body = new DOMParser().parseFromString(html, 'text/html').body;
    expect(body.children).toHaveLength(1);
    expect(body.firstElementChild?.className).toBe('receipt');
    expect(body.textContent).toContain('TOTAL 12,50 €');
  });

  it('carries the styles that dress the paper, inline, and none of the rest of the page', () => {
    const html = paperDocument(page(), { title: 'T' });
    const css = new DOMParser().parseFromString(html, 'text/html').head.querySelector('style')?.textContent ?? '';
    expect(css).toContain('.receipt');
    expect(css).toContain('80mm');
    expect(css).toContain('font-weight: 700');
    // A pseudo-element of the paper is the paper's too.
    expect(css).toContain('.receipt::after');
    // A print rule of the paper keeps its @media; what styles nothing on the paper stays out.
    expect(css).toMatch(/@media print\s*\{[^}]*\.receipt\s*\{[^}]*padding: 2mm/);
    expect(css).not.toContain('somewhere-else');
    expect(css).not.toContain('not-the-paper');
    expect(css).not.toContain('position: fixed');
    // No stylesheet link and no script: the print window allows neither.
    expect(html).not.toMatch(/<link|<script/i);
  });

  it('a style that tries to close its element cannot break out of the document head', () => {
    const paper = page();
    const style = document.createElement('style');
    style.textContent = '.receipt h1 { font-family: "</style><script>x</script>"; }';
    document.head.appendChild(style);
    const html = paperDocument(paper, { title: 'T' });
    expect(html).not.toContain('</style><script>');
    expect(new DOMParser().parseFromString(html, 'text/html').querySelector('script')).toBeNull();
  });

  it('escapes the title', () => {
    const html = paperDocument(page(), { title: 'A & B <i>' });
    expect(html).toContain('<title>A &amp; B &lt;i&gt;</title>');
  });

  it('its images point where the print window reaches them, and load at once', () => {
    const html = paperDocument(page(), { title: 'T' });
    const images = [...new DOMParser().parseFromString(html, 'text/html').body.querySelectorAll('img')];
    expect(images.map((img) => img.getAttribute('src'))).toEqual([
      'data:image/svg+xml;base64,PHN2Zy8+',
      new URL('/media/logo.png', document.baseURI).href,
    ]);
    expect(images.some((img) => img.hasAttribute('loading'))).toBe(false);
  });

  it('leaves the paper on screen untouched', () => {
    const paper = page();
    const before = paper.outerHTML;
    paperDocument(paper, { title: 'T' });
    expect(paper.outerHTML).toBe(before);
  });

  it('adds the extra rules it is given (a sheet with no stylesheet of its own)', () => {
    const html = paperDocument(page(), { title: 'T', css: '.label { width: 60mm; }' });
    expect(html).toContain('.label { width: 60mm; }');
  });
});

describe('printInTheApp', () => {
  it('in a browser (no app bridge) asks nothing: the browser prints', async () => {
    await expect(printInTheApp(page(), { title: 'T' }, {})).resolves.toBe(false);
  });

  it("in the app, hands the paper's document to the system's print screen", async () => {
    const invoke = vi.fn<Invoke>(async () => null);
    const paper = page();
    await expect(printInTheApp(paper, { title: 'Bill', lang: 'en' }, inTheApp(invoke))).resolves.toBe(true);
    expect(invoke).toHaveBeenCalledExactlyOnceWith(PRINT_DOCUMENT_COMMAND, {
      html: paperDocument(paper, { title: 'Bill', lang: 'en' }),
    });
    expect(PRINT_DOCUMENT_COMMAND).toBe('print_document');
  });

  it('an app with no print screen on this system (native_print_unsupported) leaves it to the browser', async () => {
    const invoke = vi.fn<Invoke>(async () => Promise.reject('native_print_unsupported'));
    await expect(printInTheApp(page(), { title: 'T' }, inTheApp(invoke))).resolves.toBe(false);
  });

  it.each([
    ['print_document_refused', 'refused'],
    ['native_print_failed: the document did not load in 30000 ms', 'failed'],
    ['not_the_linked_hub', 'unlinked'],
    ['print_document not allowed. Command not found', 'outdated'],
    ['Command print_document not found', 'outdated'],
    ['something else', 'failed'],
  ])('a refusal of the app (%s) comes back with its reason (%s)', async (answer, reason) => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const invoke = vi.fn<Invoke>(async () => Promise.reject(answer));
    const refused = await printInTheApp(page(), { title: 'T' }, inTheApp(invoke)).catch((error: unknown) => error);
    expect(refused).toBeInstanceOf(PrintRefused);
    expect((refused as PrintRefused).reason).toBe(reason);
    expect(console.error).toHaveBeenCalled();
  });

  it('an Error with the code as its message is read the same', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
    const invoke = vi.fn<Invoke>(async () => Promise.reject(new Error('print_document_refused')));
    const refused = await printInTheApp(page(), { title: 'T' }, inTheApp(invoke)).catch((error: unknown) => error);
    expect((refused as PrintRefused).reason).toBe('refused');
  });
});

describe('printRefusal and withReason', () => {
  const t = (key: string) => `«${key}»`;

  it('says the reason of a refusal of the app in the reader language', () => {
    expect(printRefusal(new PrintRefused('outdated', 'x'), t)).toBe('«base.print.refusal.outdated»');
    expect(printRefusal(new PrintRefused('refused', 'x'), t)).toBe('«base.print.refusal.refused»');
  });

  it('has nothing to add to what the browser throws', () => {
    expect(printRefusal(new Error('blocked'), t)).toBeNull();
    expect(printRefusal('blocked', t)).toBeNull();
  });

  it('puts the reason after the failure, once', () => {
    expect(withReason('Could not print', 'update the app')).toBe('Could not print: update the app');
    expect(withReason('Could not print.', 'update the app')).toBe('Could not print: update the app');
    expect(withReason('Could not print.', null)).toBe('Could not print.');
  });
});
