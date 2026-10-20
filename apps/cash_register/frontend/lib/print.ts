// `printPaper(source)`: prints the session's report (CASH_REGISTER-F16) through the browser. The app runs
// with Trusted Types and a strict CSP, so no HTML string is ever built: a deep copy of the paper's own
// nodes goes into a body-level root, the browser prints, and the copy leaves on `afterprint`. print.css
// (bundled with this module) hides everything else on paper and the copy on screen. With Printing on in the
// business the report goes to the receipt printer's queue instead; this is the way out without it.
import './print.css';

/** The class of the body-level container the copy is printed from (print.css). */
export const PRINT_ROOT_CLASS = 'cash-register-print-root';

/** Prints `source` alone. Throws what the browser throws (the caller says «Could not print»). */
export function printPaper(source: HTMLElement): void {
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
