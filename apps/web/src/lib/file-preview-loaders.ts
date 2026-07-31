// Adaptadores del visor de `/files` hacia las librerías PESADAS de cada formato.
//
// Todas se importan con `await import(...)` DENTRO de la función: Vite las emite en su propio
// chunk, así que abrir un `.log` no descarga pdf.js y abrir un PDF no descarga el lector de Excel.
// Es el motivo de que este módulo exista separado del componente.
//
// Nada de esto se renderiza en un `<iframe>`/`<object>`: la CSP del Hub Local los prohíbe
// (`frame-src 'none'; object-src 'none'`), así que el PDF se pinta en `<canvas>` y el .docx se
// convierte a HTML y se sanea. Ver ADR-0165.
import { decodeText, extensionOf, parseDelimited, sanitizeDocumentHtml } from './file-preview';

/** Una hoja del libro (o el fichero entero, si es un delimitado). */
export interface PreviewSheet {
  /** Nombre de la pestaña (el del libro; en un CSV, el del propio fichero). */
  name: string;
  /** Celdas ya convertidas a texto. La primera fila se usa como cabecera al pintar. */
  rows: string[][];
}

/** Resultado de leer una hoja de cálculo. */
export interface SheetPreview {
  sheets: PreviewSheet[];
}

/** Celda cruda (número, fecha, booleano, null…) → texto pintable. */
function cellToText(value: unknown): string {
  if (value === null || value === undefined) return '';
  if (value instanceof Date) return value.toISOString().slice(0, 10);
  return String(value);
}

/**
 * Hoja de cálculo → matriz de texto.
 * `.csv`/`.tsv` se parsean aquí (rápido, sin dependencias). `.xlsx`/`.xlsm` van a
 * `read-excel-file`, que lee OOXML en el navegador sin polyfills de Node.
 * `.xls` (OLE2 binario) NO llega aquí: `previewKindFor` ya lo manda a descarga.
 */
export async function loadSheet(bytes: ArrayBuffer, name: string): Promise<SheetPreview> {
  const ext = extensionOf(name);
  if (ext === 'csv' || ext === 'tsv') {
    return { sheets: [{ name, rows: parseDelimited(decodeText(bytes)) }] };
  }

  const { default: readXlsxFile, readSheetNames } = await import('read-excel-file');
  const blob = new Blob([bytes]);
  const found = await readSheetNames(blob);
  const names = found.length ? found : [name];
  const sheets: PreviewSheet[] = [];
  for (let index = 0; index < names.length; index += 1) {
    // `read-excel-file` numera las hojas desde 1.
    const raw = await readXlsxFile(blob, { sheet: index + 1 });
    sheets.push({ name: names[index], rows: raw.map((row) => row.map(cellToText)) });
  }
  return { sheets };
}

/**
 * `.docx` → HTML **saneado**. El fichero lo ha subido un tercero, así que la salida de mammoth
 * pasa siempre por la allowlist antes de tocar el DOM (ver `sanitizeDocumentHtml`).
 */
export async function loadDocx(bytes: ArrayBuffer): Promise<string> {
  const mammoth = (await import('mammoth')).default;
  const { value } = await mammoth.convertToHtml({ arrayBuffer: bytes });
  return sanitizeDocumentHtml(value);
}

/** Opciones de pintado del PDF. */
export interface RenderPdfOptions {
  /** Zoom. 1 = tamaño natural del documento. */
  scale: number;
  /** Tope de páginas a pintar de una vez (un PDF de 500 páginas colapsaría la pestaña). */
  maxPages?: number;
}

/**
 * Pinta el PDF **en canvas** dentro de `container` y devuelve el número total de páginas del
 * documento (que puede ser mayor que las pintadas si se aplica `maxPages`).
 * Canvas y no `<embed>`/`<iframe>`: la CSP del Hub Local trae `object-src 'none'` y
 * `frame-src 'none'`. pdf.js 5 ya no usa `eval` en ninguna ruta (por eso desapareció su opción
 * `isEvalSupported`), así que cumple `script-src 'self'` sin configuración extra.
 */
export async function renderPdf(
  bytes: ArrayBuffer,
  container: HTMLElement,
  options: RenderPdfOptions,
): Promise<number> {
  const pdfjs = await import('pdfjs-dist');
  // El worker se sirve del propio origen (Vite lo emite como asset) → cumple `script-src 'self'`.
  if (!pdfjs.GlobalWorkerOptions.workerSrc) {
    const worker = await import('pdfjs-dist/build/pdf.worker.min.mjs?url');
    pdfjs.GlobalWorkerOptions.workerSrc = worker.default;
  }

  const document_ = await pdfjs.getDocument({
    // pdf.js se queda con el buffer (lo "detacha"); se le pasa una copia para poder seguir
    // ofreciendo la descarga del original desde el modal.
    data: new Uint8Array(bytes.slice(0)),
  }).promise;

  container.replaceChildren();
  const total = document_.numPages;
  const limit = Math.min(total, options.maxPages ?? total);
  for (let number = 1; number <= limit; number += 1) {
    const page = await document_.getPage(number);
    const viewport = page.getViewport({ scale: options.scale });
    const canvas = document.createElement('canvas');
    canvas.className = 'preview-pdf-page';
    canvas.width = Math.ceil(viewport.width);
    canvas.height = Math.ceil(viewport.height);
    container.appendChild(canvas);
    const context = canvas.getContext('2d');
    if (context) {
      await page.render({ canvas, canvasContext: context, viewport }).promise;
    }
    page.cleanup();
  }
  return total;
}
