// Files › the preview (BASE-G84; the old hub's FilePreviewModal, HUB_SHELL-F132): a large viewer inside the hub with
// the file's name, «Download» and «Close» («Zoom in»/«Zoom out» on images and PDFs). Images, audio and video load
// from the hub's own address; a PDF, a text, a CSV or a JSON is fetched through the SDK (same origin, the session) and
// drawn here. Any other type says «No preview» and offers the download. A failure to bring or draw it reads «The file
// could not be opened», never a blank viewer.
import { fetchFile } from '@erplora/ui/sdk';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { flush, mountBase } from '../__tests__/mount-base';
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

async function show(file: FileItem, locale: 'en' | 'es' = 'en') {
  const m = await mountBase(FilePreview, { props: { file, open: true }, locale });
  await flush();
  return m;
}

const inDoc = (testid: string) => document.querySelector<HTMLElement>(`[data-testid="${testid}"]`);

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
    inDoc('file-preview-zoom-in')?.click();
    await flush();
    expect(image.style.width).toBe('125%');
    inDoc('file-preview-zoom-out')?.click();
    inDoc('file-preview-zoom-out')?.click();
    await flush();
    expect(image.style.width).toBe('75%');
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

  it('shows a CSV as a table and a JSON tidied', async () => {
    vi.mocked(fetchFile).mockResolvedValue({ blob: new Blob(['producto,precio\n"Café, solo",1.20']), name: 'v.csv' });
    await show(item('ventas.csv', 'table'));
    await flush();
    const cells = [...(inDoc('file-preview-table')?.querySelectorAll('th, td') ?? [])].map((cell) => cell.textContent);
    expect(cells).toEqual(['producto', 'precio', 'Café, solo', '1.20']);
    document.body.innerHTML = '';
    vi.mocked(fetchFile).mockResolvedValue({ blob: new Blob(['{"a":[1,2]}']), name: 'datos.json' });
    await show(item('datos.json', 'json'));
    await flush();
    expect(inDoc('file-preview-text')?.textContent).toBe('{\n  "a": [\n    1,\n    2\n  ]\n}');
  });

  it('a type it cannot show says so and offers the download, in the person’s language', async () => {
    await show(item('hoja.xlsx', '', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet'), 'es');
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
