// INVENTORY-F25: the label printed on the device when the print queue is not reachable: a sheet with a copy of the
// barcode, the SKU and the name (no price). Inside the installed app the sheet goes to the app's print screen
// (`printInTheApp`, hub#455: its webview prints nothing on `window.print()`), a printer or «Save as PDF». In a browser
// it is the browser's print dialog with the sheet alone, gone once it closes. Built with DOM calls only: Trusted
// Types refuse HTML strings in production (the CSP allows inline styles).
import { printInTheApp } from '../../../../base/frontend/lib/print-paper';

export interface LabelText {
  sku: string;
  name: string;
}

const HOOK = 'inventory-label-print';

/** The sheet itself: black on white whatever the theme, so the scanner reads the printed label (inventory#45). */
const SHEET = `
  [data-testid="${HOOK}"] { display: block; text-align: center; padding: 8mm; color: #000; background: #fff;
    font-family: sans-serif; }
  [data-testid="${HOOK}"] svg { width: 60mm; height: 18mm; }
  [data-testid="${HOOK}"] .sku { font-size: 12pt; letter-spacing: 0.08em; margin-top: 2mm; }
  [data-testid="${HOOK}"] .name { font-size: 10pt; margin-top: 1mm; }`;

/** In the page the browser prints: the sheet alone on paper, never on screen. */
const RULES = `
@media screen { [data-testid="${HOOK}"] { display: none !important; } }
@media print {
  body > :not([data-testid="${HOOK}"]) { display: none !important; }${SHEET}
}`;

function sheetOf(barcode: SVGSVGElement, label: LabelText): HTMLElement {
  const sheet = document.createElement('div');
  sheet.setAttribute('data-testid', HOOK);
  const code = barcode.cloneNode(true) as SVGSVGElement;
  const sku = document.createElement('div');
  sku.className = 'sku';
  sku.textContent = label.sku;
  const name = document.createElement('div');
  name.className = 'name';
  name.textContent = label.name;
  sheet.append(code, sku, name);
  return sheet;
}

/**
 * Prints the label of `barcode` and `label`, and nothing else of the page. Rejects with what the app refused
 * (`PrintRefused`, with its reason): the caller says why.
 */
export async function printLabel(barcode: SVGSVGElement, label: LabelText): Promise<void> {
  const sheet = sheetOf(barcode, label);
  if (await printInTheApp(sheet, { title: `${label.sku} ${label.name}`, css: SHEET })) return;
  const style = document.createElement('style');
  style.textContent = RULES;
  document.head.appendChild(style);
  document.body.appendChild(sheet);
  window.addEventListener(
    'afterprint',
    () => {
      sheet.remove();
      style.remove();
    },
    { once: true },
  );
  window.print();
}
