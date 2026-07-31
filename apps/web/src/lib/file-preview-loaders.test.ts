// @vitest-environment happy-dom
// Contrato de los adaptadores del visor de /files hacia las librerías PESADAS (pdf.js, xlsx, docx).
// Las libs van MOCKEADAS a propósito: aquí se prueba NUESTRA lógica (routing, cabeceras de hoja,
// saneado, opciones de seguridad de pdf.js), no que un tercero sepa leer su propio formato.
import { describe, it, expect, vi, beforeEach } from 'vitest';

const convertToHtml = vi.fn();
vi.mock('mammoth', () => ({ default: { convertToHtml: (...a: unknown[]) => convertToHtml(...a) } }));

const readXlsxFile = vi.fn();
const readSheetNames = vi.fn();
vi.mock('read-excel-file', () => ({
  default: (...a: unknown[]) => readXlsxFile(...a),
  readSheetNames: (...a: unknown[]) => readSheetNames(...a),
}));

const getDocument = vi.fn();
const GlobalWorkerOptions = { workerSrc: '' };
vi.mock('pdfjs-dist', () => ({
  getDocument: (...a: unknown[]) => getDocument(...a),
  GlobalWorkerOptions,
}));
vi.mock('pdfjs-dist/build/pdf.worker.min.mjs?url', () => ({ default: '/pdf.worker.mjs' }));

import { loadSheet, loadDocx, renderPdf } from './file-preview-loaders';

const bytesOf = (text: string): ArrayBuffer => new TextEncoder().encode(text).buffer;

beforeEach(() => {
  convertToHtml.mockReset();
  readXlsxFile.mockReset();
  getDocument.mockReset();
});

describe('loadSheet', () => {
  it('lee un CSV sin tocar la librería de Excel (el caso barato no paga el caro)', async () => {
    const sheet = await loadSheet(bytesOf('ref;total\nA-1;14,52'), 'ventas.csv');
    expect(readXlsxFile).not.toHaveBeenCalled();
    expect(sheet.sheets).toEqual([
      { name: 'ventas.csv', rows: [['ref', 'total'], ['A-1', '14,52']] },
    ]);
  });

  it('lee TODAS las hojas de un .xlsx, no solo la primera', async () => {
    readSheetNames.mockResolvedValue(['Enero', 'Febrero']);
    readXlsxFile.mockImplementation((_blob: unknown, options: { sheet: number }) =>
      Promise.resolve(options.sheet === 1 ? [['ref'], ['A-1']] : [['ref'], ['B-2']]),
    );
    const sheet = await loadSheet(bytesOf('PK...'), 'ventas.xlsx');
    expect(sheet.sheets.map((s) => s.name)).toEqual(['Enero', 'Febrero']);
    expect(sheet.sheets[1].rows).toEqual([['ref'], ['B-2']]);
  });

  it('convierte las celdas a texto para poder pintarlas (fechas y números incluidos)', async () => {
    readSheetNames.mockResolvedValue(['Hoja1']);
    readXlsxFile.mockResolvedValue([[1200, new Date('2026-07-31T00:00:00Z'), null]]);
    const sheet = await loadSheet(bytesOf('PK...'), 'x.xlsx');
    const [row] = sheet.sheets[0].rows;
    expect(row[0]).toBe('1200');
    expect(row[1]).toContain('2026-07-31');
    expect(row[2]).toBe('');
  });
});

describe('loadDocx', () => {
  it('sanea el HTML que devuelve mammoth antes de pintarlo', async () => {
    convertToHtml.mockResolvedValue({ value: '<p>ok</p><script>alert(1)</script>', messages: [] });
    const html = await loadDocx(bytesOf('PK...'));
    expect(html).toContain('<p>ok</p>');
    expect(html).not.toContain('<script');
  });
});

describe('renderPdf', () => {
  function fakePdf(pages: number) {
    const render = vi.fn(() => ({ promise: Promise.resolve() }));
    const page = {
      getViewport: () => ({ width: 600, height: 800 }),
      render,
      cleanup: vi.fn(),
    };
    getDocument.mockReturnValue({
      promise: Promise.resolve({ numPages: pages, getPage: () => Promise.resolve(page), destroy: vi.fn() }),
    });
    return render;
  }

  it('pinta una <canvas> por página dentro del contenedor', async () => {
    fakePdf(3);
    const container = document.createElement('div');
    const pages = await renderPdf(bytesOf('%PDF-'), container, { scale: 1 });
    expect(pages).toBe(3);
    expect(container.querySelectorAll('canvas')).toHaveLength(3);
  });

  it('carga el worker desde el propio origen, nunca de un CDN', async () => {
    // La CSP del Hub es `script-src 'self'` y el Hub Local funciona sin red: un worker de CDN
    // rompería las dos cosas. Vite emite el worker como asset del bundle.
    fakePdf(1);
    GlobalWorkerOptions.workerSrc = '';
    await renderPdf(bytesOf('%PDF-'), document.createElement('div'), { scale: 1 });
    expect(GlobalWorkerOptions.workerSrc).toBe('/pdf.worker.mjs');
    expect(GlobalWorkerOptions.workerSrc).not.toMatch(/^https?:/);
  });

  it('no deja páginas a medias de un render anterior', async () => {
    fakePdf(1);
    const container = document.createElement('div');
    container.appendChild(document.createElement('canvas'));
    await renderPdf(bytesOf('%PDF-'), container, { scale: 1 });
    expect(container.querySelectorAll('canvas')).toHaveLength(1);
  });
});
