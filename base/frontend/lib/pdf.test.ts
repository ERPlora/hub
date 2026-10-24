// The PDF of Files' preview (BASE-G84; the old hub drew it with pdf.js too): Mozilla's pdf.js, loaded only when a PDF
// opens, runs in the page's own thread (its worker module handed over as `globalThis.pdfjsWorker`: no Worker, so the
// strict CSP needs nothing new), reads the bytes it is given (it fetches nothing) and draws the first 30 pages.
import { afterEach, describe, expect, it, vi } from 'vitest';

const pdfjs = vi.hoisted(() => {
  const render = vi.fn(() => ({ promise: Promise.resolve() }));
  const page = { getViewport: vi.fn(({ scale }: { scale: number }) => ({ width: 100 * scale, height: 140 * scale })), render };
  const doc = { numPages: 42, getPage: vi.fn<(number: number) => Promise<typeof page>>(() => Promise.resolve(page)) };
  const task = { promise: Promise.resolve(doc), destroy: vi.fn(() => Promise.resolve()) };
  return { render, page, doc, task, getDocument: vi.fn<(params: Record<string, unknown>) => typeof task>(() => task) };
});
vi.mock('pdfjs-dist/legacy/build/pdf.mjs', () => ({ getDocument: pdfjs.getDocument }));
vi.mock('pdfjs-dist/legacy/build/pdf.worker.mjs', () => ({ WorkerMessageHandler: { setup: vi.fn() } }));

import { renderPdf } from './pdf';

afterEach(() => {
  vi.clearAllMocks();
  delete (globalThis as { pdfjsWorker?: unknown }).pdfjsWorker;
});

describe('renderPdf', () => {
  it('draws the first 30 pages of a long PDF, each in its canvas, and says how many it has', async () => {
    const drawn = await renderPdf(new Uint8Array([1, 2, 3]), 1.5);
    expect(drawn.total).toBe(42);
    expect(drawn.pages).toHaveLength(30);
    expect(drawn.pages[0]).toBeInstanceOf(HTMLCanvasElement);
    expect([drawn.pages[0].width, drawn.pages[0].height]).toEqual([150, 210]);
    expect(pdfjs.render).toHaveBeenCalledTimes(30);
    expect(pdfjs.doc.getPage.mock.calls.map(([n]) => n)).toEqual(Array.from({ length: 30 }, (_, i) => i + 1));
  });

  it('reads the bytes it is given, fetches nothing, and runs in the page’s thread', async () => {
    const bytes = new Uint8Array([9]);
    await renderPdf(bytes);
    expect(pdfjs.getDocument).toHaveBeenCalledWith(expect.objectContaining({ data: bytes, enableXfa: false }));
    expect(Object.keys(pdfjs.getDocument.mock.calls[0][0])).not.toContain('url');
    expect((globalThis as { pdfjsWorker?: { WorkerMessageHandler?: unknown } }).pdfjsWorker?.WorkerMessageHandler).toBeTruthy();
  });

  it('lets the document go once drawn, and when drawing fails', async () => {
    await renderPdf(new Uint8Array([1]));
    expect(pdfjs.task.destroy).toHaveBeenCalledTimes(1);
    pdfjs.render.mockImplementationOnce(() => ({ promise: Promise.reject(new Error('broken page')) }));
    await expect(renderPdf(new Uint8Array([1]))).rejects.toThrow('broken page');
    expect(pdfjs.task.destroy).toHaveBeenCalledTimes(2);
  });
});
