// INVENTORY-F25: the label printed from the browser when the print queue is not reachable: a sheet with a copy
// of the barcode, the SKU and the name (no price) that only paper shows, the browser's print dialog, and the
// sheet gone once it closes. Built with DOM calls only: Trusted Types refuse HTML strings in production (the
// CSP allows inline styles).

export interface LabelText {
  sku: string;
  name: string;
}

const HOOK = 'inventory-label-print';

const RULES = `
@media screen { [data-testid="${HOOK}"] { display: none !important; } }
@media print {
  body > :not([data-testid="${HOOK}"]) { display: none !important; }
  [data-testid="${HOOK}"] { display: block; text-align: center; padding: 8mm; color: #000; background: #fff;
    font-family: sans-serif; }
  [data-testid="${HOOK}"] svg { width: 60mm; height: 18mm; }
  [data-testid="${HOOK}"] .sku { font-size: 12pt; letter-spacing: 0.08em; margin-top: 2mm; }
  [data-testid="${HOOK}"] .name { font-size: 10pt; margin-top: 1mm; }
}`;

/** Opens the browser's print dialog for `barcode` and `label`, and nothing else of the page. */
export function printInBrowser(barcode: SVGSVGElement, label: LabelText): void {
  const style = document.createElement('style');
  style.textContent = RULES;
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
