// The files a scenario's owner attaches (assistant-scenario.ts), made at run time and never kept in the repo: a real
// spreadsheet (.xlsx, written here), and a delivery note printed by the browser from one page, as a text PDF or as a
// phone-like photo of the paper on a counter. Pure but for the page it is given, so Vitest proves it.
import { strToU8, zipSync } from 'fflate';

import type { Attachment, DeliveryNote } from './assistant-scenario.ts';

export const SHEET_TYPE = 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet';

/** A file as Playwright's `setInputFiles` takes it, and as the chat sends it. */
export interface AttachedFile {
  name: string;
  mimeType: string;
  buffer: Buffer;
}

/** How a delivery note becomes bytes: printed as a PDF, or photographed. */
export interface Renderer {
  pdf: (html: string) => Promise<Buffer>;
  photo: (html: string, type: 'jpeg' | 'png') => Promise<Buffer>;
}

/** What `renderWith` needs of a Playwright page. */
export interface PrintingPage {
  setContent: (html: string) => Promise<unknown>;
  setViewportSize: (size: { width: number; height: number }) => Promise<unknown>;
  pdf: (options: { format: string; printBackground: boolean }) => Promise<Buffer>;
}

/** The screenshot of that page, in a type: the e2e's `capture()` (helpers.ts), which every screenshot goes through. */
export type Shoot = (options: { type: 'jpeg' | 'png'; quality?: number }) => Promise<Buffer>;

const xml = (text: string): string => text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');

function column(index: number): string {
  let name = '';
  for (let left = index + 1; left > 0; left = Math.floor((left - 1) / 26)) name = String.fromCharCode(65 + ((left - 1) % 26)) + name;
  return name;
}

function cell(value: string | number | null, at: string): string {
  if (value === null) return '';
  if (typeof value === 'number') return `<c r="${at}"><v>${value}</v></c>`;
  return `<c r="${at}" t="inlineStr"><is><t xml:space="preserve">${xml(value)}</t></is></c>`;
}

const sheetXml = (rows: (string | number | null)[][]): string =>
  '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>' +
  '<worksheet xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main"><sheetData>' +
  rows.map((row, r) => `<row r="${r + 1}">${row.map((value, c) => cell(value, `${column(c)}${r + 1}`)).join('')}</row>`).join('') +
  '</sheetData></worksheet>';

const MAIN = 'http://schemas.openxmlformats.org/officeDocument/2006/relationships';
const PACKAGE = 'http://schemas.openxmlformats.org/package/2006/relationships';

/** A one-sheet workbook with `rows` (texts, numbers, or empty cells), as Excel writes the minimum of one. */
export function xlsxOf(sheet: string, rows: (string | number | null)[][]): Uint8Array {
  return zipSync({
    '[Content_Types].xml': strToU8(
      '<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">' +
        '<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/><Default Extension="xml" ContentType="application/xml"/>' +
        '<Override PartName="/xl/workbook.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet.main+xml"/>' +
        '<Override PartName="/xl/worksheets/sheet1.xml" ContentType="application/vnd.openxmlformats-officedocument.spreadsheetml.worksheet+xml"/></Types>',
    ),
    '_rels/.rels': strToU8(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="${PACKAGE}"><Relationship Id="rId1" Type="${MAIN}/officeDocument" Target="xl/workbook.xml"/></Relationships>`),
    'xl/workbook.xml': strToU8(
      `<?xml version="1.0" encoding="UTF-8" standalone="yes"?><workbook xmlns="http://schemas.openxmlformats.org/spreadsheetml/2006/main" xmlns:r="${MAIN}"><sheets><sheet name="${xml(sheet)}" sheetId="1" r:id="rId1"/></sheets></workbook>`,
    ),
    'xl/_rels/workbook.xml.rels': strToU8(`<?xml version="1.0" encoding="UTF-8" standalone="yes"?><Relationships xmlns="${PACKAGE}"><Relationship Id="rId1" Type="${MAIN}/worksheet" Target="worksheets/sheet1.xml"/></Relationships>`),
    'xl/worksheets/sheet1.xml': strToU8(sheetXml(rows)),
  });
}

/** «0,42» or «0.42» in cents. */
const cents = (text: string): number => Math.round(Number(text.replace(',', '.')) * 100);
const euros = (value: number): string => (value / 100).toFixed(2).replace('.', ',');

function lineRows(note: DeliveryNote): { rows: string; total: number } {
  let total = 0;
  const rows = note.lines.map((line) => {
    const amount = Math.round(Number(line.quantity.replace(',', '.')) * cents(line.unitCost));
    total += amount;
    return `<tr><td>${xml(line.product)}</td><td class="n">${xml(line.quantity)}</td><td class="n">${xml(line.unitCost)} €</td><td class="n">${euros(amount)} €</td></tr>`;
  });
  return { rows: rows.join(''), total };
}

const PAPER_CSS =
  'body{margin:0;font-family:Arial,Helvetica,sans-serif;color:#1d1d1d}' +
  '.paper{background:#fff;padding:48px;width:720px}' +
  'h1{font-size:30px;margin:0 0 8px}p{font-size:20px;margin:4px 0}' +
  'table{width:100%;border-collapse:collapse;margin-top:24px;font-size:20px}' +
  'th,td{border-bottom:1px solid #999;padding:10px 6px;text-align:left}.n{text-align:right}' +
  '.total{font-size:24px;font-weight:bold;text-align:right;margin-top:18px}';
const PHOTO_CSS =
  'body{background:radial-gradient(circle at 30% 20%,#9a7b5b,#5e4530);padding:70px 40px;min-height:1100px}' +
  '.paper{transform:rotate(-2.2deg);box-shadow:12px 18px 30px rgba(0,0,0,.45);filter:brightness(.95) contrast(1.05)}';

/** The delivery note as one printed page, or as a photo of it on a counter, slightly turned and shaded. */
export function noteHtml(note: DeliveryNote, look: 'paper' | 'photo'): string {
  const { rows, total } = lineRows(note);
  const css = look === 'photo' ? PAPER_CSS + PHOTO_CSS : PAPER_CSS;
  return (
    `<!doctype html><html lang="es"><head><meta charset="utf-8"><style>${css}</style></head><body><div class="paper">` +
    `<h1>ALBARÁN DE ENTREGA</h1><p><b>${xml(note.supplier)}</b></p><p>Albarán nº ${xml(note.number)} · Fecha ${xml(note.date)}</p>` +
    `<table><thead><tr><th>Producto</th><th class="n">Cantidad</th><th class="n">Precio ud.</th><th class="n">Importe</th></tr></thead><tbody>${rows}</tbody></table>` +
    `<p class="total">Total: ${euros(total)} €</p></div></body></html>`
  );
}

/** The bytes and type of an attachment, as the composer takes it. */
export async function attachmentFile(attachment: Attachment, render: Renderer): Promise<AttachedFile> {
  const { name } = attachment;
  if (attachment.kind === 'xlsx') return { name, mimeType: SHEET_TYPE, buffer: Buffer.from(xlsxOf(attachment.sheet, attachment.rows)) };
  if (attachment.kind === 'pdf') return { name, mimeType: 'application/pdf', buffer: await render.pdf(noteHtml(attachment.note, 'paper')) };
  const type = name.toLowerCase().endsWith('.png') ? 'png' : 'jpeg';
  return { name, mimeType: `image/${type}`, buffer: await render.photo(noteHtml(attachment.note, 'photo'), type) };
}

/** A renderer on a page of its own: the PDF as Chromium prints it, the photo at a phone's portrait size. */
export function renderWith(page: PrintingPage, shoot: Shoot): Renderer {
  return {
    pdf: async (html) => {
      await page.setContent(html);
      return page.pdf({ format: 'A4', printBackground: true });
    },
    photo: async (html, type) => {
      await page.setViewportSize({ width: 900, height: 1200 });
      await page.setContent(html);
      return shoot({ type, ...(type === 'jpeg' ? { quality: 82 } : {}) });
    },
  };
}
