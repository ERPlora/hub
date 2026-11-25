// `printPaper(paper, options)`: prints one paper of any app on the device. Inside the installed app it goes to the app's
// print screen (`printInTheApp`: its webview prints nothing on `window.print()`), a printer or «Save as PDF». In a
// browser no HTML string is ever built (Trusted Types and a strict CSP): a deep copy of the paper's own nodes goes into
// a body-level root, the body is marked as printing, the browser prints, and both leave on `afterprint`. print.css
// hides the rest of the page only while the body is marked, so a paper of another app printed later is not blanked.
import './print.css';

import { type PaperDocumentOptions, printInTheApp } from './print-paper';

/** The class of the body-level container the copy is printed from (print.css). */
export const PRINT_ROOT_CLASS = 'ep-print-root';
/** The class the body carries while the browser prints the copy (print.css). */
export const PRINTING_CLASS = 'ep-printing';

/**
 * Prints `paper` alone. Rejects with what the app refused (`PrintRefused`, with its reason) or what the browser threw:
 * the caller says «Could not print», with the reason when there is one (`printRefusal`).
 */
export async function printPaper(paper: HTMLElement, options: PaperDocumentOptions): Promise<void> {
  if (await printInTheApp(paper, options)) return;
  printInBrowser(paper);
}

function printInBrowser(paper: HTMLElement): void {
  for (const left of document.querySelectorAll(`body > .${PRINT_ROOT_CLASS}`)) left.remove();
  const root = document.createElement('div');
  root.className = PRINT_ROOT_CLASS;
  root.appendChild(paper.cloneNode(true));
  document.body.appendChild(root);
  document.body.classList.add(PRINTING_CLASS);
  const done = (): void => {
    window.removeEventListener('afterprint', done);
    document.body.classList.remove(PRINTING_CLASS);
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
