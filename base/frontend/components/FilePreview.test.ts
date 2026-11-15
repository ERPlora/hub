import { readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

import { fetchFile } from '@erplora/ui/sdk';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { flush, mountBase } from '../__tests__/mount-base';
import { OFFICE_PREVIEW_MAX_BYTES } from '../lib/files';
import type { FileItem } from '../operations';
import FilePreview from './FilePreview.vue';

const mocks = vi.hoisted(() => ({ renderPdf: vi.fn() }));
vi.mock('@erplora/ui/sdk', async (importOriginal) => ({
  ...(await importOriginal<typeof import('@erplora/ui/sdk')>()),
  fetchFile: vi.fn(),
}));
vi.mock('../lib/pdf', () => ({ renderPdf: mocks.renderPdf }));
vi.mock('@ionic/vue', async (importOriginal) => {
  const { IonModalStub } = await import('../../../packages/ui/src/components/FormModal/__tests__/ionModalStub');
  return { ...(await importOriginal<typeof import('@ionic/vue')>()), IonModal: IonModalStub };
});

function item(name: string, preview: FileItem['preview'], content_type = 'text/plain'): FileItem {
  return { path: `Facturas/${name}`, name, size: 10, modified: null, content_type, preview };
}

/** `file`, heavier than the preview reads. */
const heavy = (file: FileItem): FileItem => ({ ...file, size: OFFICE_PREVIEW_MAX_BYTES + 1 });

const XLSX = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';
const DOCX = 'application/vnd.openxmlformats-officedocument.wordprocessingml.document';
const sample = (name: string) => readFileSync(join(dirname(fileURLToPath(import.meta.url)), '..', '__tests__', 'files', name));
const arrives = (bytes: BlobPart, name: string) => vi.mocked(fetchFile).mockResolvedValue({ blob: new Blob([bytes]), name });

async function show(file: FileItem, locale: 'en' | 'es' = 'en') {
  const m = await mountBase(FilePreview, { props: { file, open: true }, locale });
  await flush();
  return m;
}

const inDoc = (testid: string) => document.querySelector<HTMLElement>(`[data-testid="${testid}"]`);

/** Resolves once `done()` holds, watched in the document (its nodes and their classes) with no clock of its own: however
 *  long the machine takes, the test then checks what the page shows. A wait that never ends is cut by the test's
 *  budget, as any. */
function until(done: () => boolean): Promise<void> {
  return new Promise((resolve) => {
    if (done()) {
      resolve();
      return;
    }
    const watcher = new MutationObserver(() => {
      if (!done()) return;
      watcher.disconnect();
      resolve();
    });
    watcher.observe(document.body, { childList: true, subtree: true, attributes: true, attributeFilter: ['class'] });
  });
}

/** Resolves once the preview no longer says «Opening the file»: it shows the file, or says why it cannot (hub#1293),
 *  however long the machine takes to bring a library and read the file. At once when it does not say it. */
const settled = (): Promise<void> => until(() => !inDoc('file-preview-loading'));

/** Resolves once Ionic drew every element of the part `testid` (Stencil marks each one `hydrated`): a sheet's tab reads
 *  its name only then, a moment after the table, in Ionic's own time (hub#1300). At once when there is no such part. */
const drawn = (testid: string): Promise<void> =>
  until(() => {
    const part = inDoc(testid);
    return !part || [part, ...part.querySelectorAll('*')].every((el) => !el.localName.startsWith('ion-') || el.classList.contains('hydrated'));
  });

beforeEach(() => {
  vi.mocked(fetchFile).mockReset();
  mocks.renderPdf.mockReset();
});

afterEach(() => {
  document.body.innerHTML = '';
});

describe('FilePreview', () => {
  it('titles the viewer with the file’s name, with «Download» and «Close»', async () => {
    const m = await show(item('foto.png', 'image', 'image/png'));
    expect(inDoc('file-preview-title')?.textContent).toBe('foto.png');
    inDoc('file-preview-download')?.click();
    inDoc('file-preview-close')?.click();
    expect(m.wrapper.emitted('download')).toHaveLength(1);
    expect(m.wrapper.emitted('close')).toHaveLength(1);
  });

  it('shows an image from the hub’s own address, and zooms it', async () => {
    await show(item('foto.png', 'image', 'image/png'));
    const image = inDoc('file-preview-image') as HTMLImageElement;
    expect(image.getAttribute('src')).toBe('/api/files/raw?path=Facturas%2Ffoto.png&inline=true');
    expect(image.getAttribute('alt')).toBe('foto.png');
    // Fitted, like Drive's viewer: never larger than the file itself, nor than the viewer's width or height (the
    // stage pads 16 px a side); the zoom multiplies that. Here a 40×80 picture: its width is half its height.
    Object.defineProperty(image, 'naturalWidth', { value: 40 });
    Object.defineProperty(image, 'naturalHeight', { value: 80 });
    image.dispatchEvent(new Event('load'));
    await flush();
    const fit = 'min(40px, 100cqw - 32px, (100cqh - 32px) * 0.5)';
    expect(image.style.width).toBe(`calc(${fit} * 1)`);
    inDoc('file-preview-zoom-in')?.click();
    await flush();
    expect(image.style.width).toBe(`calc(${fit} * 1.25)`);
    inDoc('file-preview-zoom-out')?.click();
    inDoc('file-preview-zoom-out')?.click();
    await flush();
    expect(image.style.width).toBe(`calc(${fit} * 0.75)`);
    expect(fetchFile).not.toHaveBeenCalled();
  });

  it('plays audio and video from the hub’s own address, without zoom', async () => {
    await show(item('cancion.mp3', 'audio', 'audio/mpeg'));
    expect(inDoc('file-preview-audio')?.getAttribute('src')).toBe('/api/files/raw?path=Facturas%2Fcancion.mp3&inline=true');
    // Not offered: hidden (`v-show`; Ionic's slotted buttons are never added and removed in place).
    expect(inDoc('file-preview-zoom-in')?.style.display).toBe('none');
    document.body.innerHTML = '';
    await show(item('video.mp4', 'video', 'video/mp4'));
    expect(inDoc('file-preview-video')?.getAttribute('src')).toContain('video.mp4');
  });

  it('draws a PDF from the bytes the SDK fetched, and says when it shows only the first pages', async () => {
    vi.mocked(fetchFile).mockResolvedValue({ blob: new Blob([new Uint8Array([37, 80])]), name: 'informe.pdf' });
    const canvases = [document.createElement('canvas'), document.createElement('canvas')];
    mocks.renderPdf.mockResolvedValue({ pages: canvases, total: 42 });
    await show(item('informe.pdf', 'pdf', 'application/pdf'));
    await flush();
    expect(fetchFile).toHaveBeenCalledWith('/api/files/raw?path=Facturas%2Finforme.pdf&inline=true', 'application/pdf');
    expect(inDoc('file-preview-pdf')?.querySelectorAll('canvas')).toHaveLength(2);
    expect(inDoc('file-preview-cut')?.textContent).toContain('Showing the first 30 of 42 pages');
  });

  it('shows a text as it is, never as markup', async () => {
    vi.mocked(fetchFile).mockResolvedValue({ blob: new Blob(['<b>hola</b>']), name: 'pagina.html' });
    await show(item('pagina.html', 'text'));
    await flush();
    const text = inDoc('file-preview-text');
    expect(text?.textContent).toBe('<b>hola</b>');
    expect(text?.querySelector('b')).toBeNull();
  });

  it('shows a CSV as a table', async () => {
    vi.mocked(fetchFile).mockResolvedValue({ blob: new Blob(['producto,precio\n"Café, solo",1.20']), name: 'v.csv' });
    await show(item('ventas.csv', 'table'));
    await flush();
    const cells = [...(inDoc('file-preview-table')?.querySelectorAll('th, td') ?? [])].map((cell) => cell.textContent);
    expect(cells).toEqual(['producto', 'precio', 'Café, solo', '1.20']);
  });

  // hub#578: a JSON folds by parts, a spreadsheet is a table per sheet and a Word document its formatted text.
  it('shows a JSON as a tree that folds; a broken one as it is, saying so', async () => {
    arrives('{"a":[1,2]}', 'datos.json');
    await show(item('datos.json', 'json'));
    await flush();
    expect(inDoc('file-preview-json')?.querySelectorAll('details')).toHaveLength(2);
    expect(inDoc('file-preview-json')?.textContent?.replace(/\s+/g, ' ')).toContain('a: [ ] 2 items');
    expect(inDoc('file-preview-json-broken')).toBeNull();
    document.body.innerHTML = '';
    arrives('{"a":', 'roto.json');
    await show(item('roto.json', 'json'), 'es');
    await flush();
    expect(inDoc('file-preview-text')?.textContent).toBe('{"a":');
    expect(inDoc('file-preview-json-broken')?.textContent).toContain('no es un JSON válido');
  });

  it('shows a real .xlsx as a table per sheet, its cells as the sheet shows them', async () => {
    arrives(sample('sample.xlsx'), 'ventas.xlsx');
    await show(item('ventas.xlsx', '', XLSX), 'es');
    // Its library loads cold and reads the file in its own time, as the .docx's does (hub#1300).
    await settled();
    expect(inDoc('file-preview-table')).not.toBeNull();
    const cells = [...(inDoc('file-preview-table')?.querySelectorAll('th, td') ?? [])].map((cell) => cell.textContent);
    expect(cells.slice(0, 8)).toEqual(['Producto', 'Precio', 'Fecha', 'Pagado', 'Café solo', '1,2', '03/11/2026', '1']);
    await drawn('file-preview-sheet-tabs');
    expect([...document.querySelectorAll('[data-testid="file-preview-sheet-tab"]')].map((tab) => tab.textContent?.trim())).toEqual(['Ventas', 'Notas']);
    expect(inDoc('file-preview-none')).toBeNull();
  });

  it('shows a real .docx as its formatted text, and nothing of it runs', async () => {
    arrives(sample('sample.docx'), 'informe.docx');
    await show(item('informe.docx', '', DOCX));
    // Its library loads cold and reads the file in its own time: on a busy machine, longer than any clock (hub#1293).
    await settled();
    expect(inDoc('file-preview-document')?.querySelector('h1')?.textContent).toBe('Informe de noviembre');
    expect(document.querySelector('[data-testid="file-preview"] script, [data-testid="file-preview"] [onerror]')).toBeNull();
    expect(inDoc('file-preview-document')?.textContent).toContain('<script>alert(1)</script>');
  });

  it('a spreadsheet or a document that cannot be read says so (damaged), with the download', async () => {
    arrives(new Uint8Array([80, 75, 3, 4, 9, 9, 9]), 'roto.xlsx');
    await show(item('roto.xlsx', '', XLSX), 'es');
    // Each library is brought cold and refuses the file in its own time (hub#1300): each wait goes right after the
    // `show()` of a file the preview is still opening.
    await settled();
    expect(inDoc('file-preview-damaged')).not.toBeNull();
    expect(inDoc('file-preview-damaged')?.textContent).toContain('No se pudo leer el archivo');
    expect(inDoc('file-preview-damaged')?.textContent).toContain('Descárgalo');
    expect(inDoc('file-preview-error')).toBeNull();
    expect(inDoc('file-preview-download')).not.toBeNull();
    document.body.innerHTML = '';
    arrives(sample('sample.xlsx'), 'informe.docx');
    await show(item('informe.docx', '', DOCX));
    await settled();
    expect(inDoc('file-preview-damaged')?.textContent).toContain('The file could not be read');
  });

  it('one heavier than the preview reads is not even fetched: «too large», with the download', async () => {
    await show(heavy(item('enorme.xlsx', '', XLSX)), 'es');
    await flush();
    expect(fetchFile).not.toHaveBeenCalled();
    expect(inDoc('file-preview-too-large')?.textContent).toContain('Demasiado grande para la vista previa');
    expect(inDoc('file-preview-too-large')?.textContent).toContain('10 MB');
    document.body.innerHTML = '';
    await show(heavy(item('enorme.docx', '', DOCX)));
    await flush();
    expect(inDoc('file-preview-too-large')?.textContent).toContain('up to 10 MB');
  });

  it('a type it cannot show says so and offers the download, in the person’s language', async () => {
    await show(item('hoja.xls', '', 'application/vnd.ms-excel'), 'es');
    expect(inDoc('file-preview-none')?.textContent).toContain('Sin vista previa');
    expect(inDoc('file-preview-none')?.textContent).toContain('Descárgalo para abrirlo');
    expect(fetchFile).not.toHaveBeenCalled();
  });

  it('a file that does not arrive reads as that, never a blank viewer', async () => {
    vi.mocked(fetchFile).mockRejectedValue(Object.assign(new Error('lost'), { code: 'network_error' }));
    await show(item('informe.pdf', 'pdf', 'application/pdf'));
    await flush();
    expect(inDoc('file-preview-error')?.textContent).toContain('The file could not be opened');
    expect(inDoc('file-preview-error')?.textContent).toContain('did not arrive');
    expect(inDoc('file-preview-pdf')).toBeNull();
  });

  it('an image that does not load reads as that too', async () => {
    await show(item('foto.png', 'image', 'image/png'));
    inDoc('file-preview-image')?.dispatchEvent(new Event('error'));
    await flush();
    expect(inDoc('file-preview-error')).not.toBeNull();
  });

  it('shows a loading line while the file comes', async () => {
    vi.mocked(fetchFile).mockReturnValue(new Promise(() => undefined));
    await show(item('notas.txt', 'text'));
    expect(inDoc('file-preview-loading')?.textContent).toContain('Opening the file');
  });
});
