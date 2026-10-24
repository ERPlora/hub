// The PDF of Files' preview (BASE-G84): drawn with Mozilla's pdf.js (the old hub's), loaded only when a PDF opens. It
// runs in the page's own thread — its worker module handed over as `globalThis.pdfjsWorker`, which pdf.js uses instead
// of starting a Worker — so the strict CSP (`script-src` with a nonce and `strict-dynamic`) needs nothing new, and it
// reads the bytes the SDK fetched (it fetches nothing itself). The legacy build, for the webviews of the installed app.
import { PDF_PAGES } from './files';

export interface RenderedPdf {
  /** The pages drawn, at most `PDF_PAGES`. */
  pages: HTMLCanvasElement[];
  /** How many pages the PDF has. */
  total: number;
}

async function loadPdfjs() {
  const [pdfjs, worker] = await Promise.all([
    import('pdfjs-dist/legacy/build/pdf.mjs'),
    import('pdfjs-dist/legacy/build/pdf.worker.mjs'),
  ]);
  (globalThis as { pdfjsWorker?: unknown }).pdfjsWorker = worker;
  return pdfjs;
}

/** Draws the first `maxPages` pages of the PDF `data`, each in its own canvas, at `scale`. */
export async function renderPdf(data: Uint8Array, scale = 1.25, maxPages = PDF_PAGES): Promise<RenderedPdf> {
  const pdfjs = await loadPdfjs();
  const task = pdfjs.getDocument({ data, enableXfa: false });
  try {
    const doc = await task.promise;
    const pages: HTMLCanvasElement[] = [];
    for (let number = 1; number <= Math.min(doc.numPages, maxPages); number += 1) {
      const page = await doc.getPage(number);
      const viewport = page.getViewport({ scale });
      const canvas = document.createElement('canvas');
      canvas.width = Math.floor(viewport.width);
      canvas.height = Math.floor(viewport.height);
      await page.render({ canvas, viewport }).promise;
      pages.push(canvas);
    }
    return { pages, total: doc.numPages };
  } finally {
    await task.destroy();
  }
}
