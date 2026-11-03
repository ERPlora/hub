// `printPaper(source, options)`: prints the session's report (CASH_REGISTER-F16) on the device. Inside the installed
// app it goes to the app's print screen (`printInTheApp`, hub#455: its webview prints nothing on `window.print()`),
// a printer or «Save as PDF», titled `options.title`. In a browser it prints through the browser's dialog, and no
// HTML string is ever built (Trusted Types and a strict CSP): a deep copy of the paper's own nodes goes into a
// body-level root, the browser prints, and the copy leaves on `afterprint`. print.css (bundled with this module)
// hides everything else on paper and the copy on screen. With Printing on in the business the report goes to the
// receipt printer's queue instead; this is the way out without it.
import './print.css';

import { type PaperDocumentOptions, printInTheApp } from '../../../../base/frontend/lib/print-paper';

/** The class of the body-level container the copy is printed from (print.css). */
export const PRINT_ROOT_CLASS = 'cash-register-print-root';

/**
 * Prints `source` alone. Rejects with what the app refused (`PrintRefused`, with its reason) or what the browser
 * threw: the caller says «Could not print», with the reason when there is one (`printRefusal`).
 */
export async function printPaper(source: HTMLElement, options: PaperDocumentOptions): Promise<void> {
  if (await printInTheApp(source, options)) return;
  printInBrowser(source);
}

function printInBrowser(source: HTMLElement): void {
  for (const left of document.querySelectorAll(`body > .${PRINT_ROOT_CLASS}`)) left.remove();
  const root = document.createElement('div');
  root.className = PRINT_ROOT_CLASS;
  root.appendChild(source.cloneNode(true));
  document.body.appendChild(root);
  const done = (): void => {
    window.removeEventListener('afterprint', done);
    root.remove();
  };
  window.addEventListener('afterprint', done);
  try {
    window.print();
  } catch (error) {
    done();
    throw error;
  }
}
