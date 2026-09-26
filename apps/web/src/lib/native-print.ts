// The system print dialog of the installed app, for a document the page already holds (hub#2006).
//
// Inside the app's webview `window.print()` prints nothing (hub#862), so an A4 invoice had no way to
// reach a laser printer or «Save as PDF». The shell opens a window of its own with the document and
// asks the OS to print it: the dialog is the system's, so the printer list and the PDF option come
// with it. The Rust half is `print_document` in `apps/tauri/src-tauri/src/lib.rs`.
import { invokeTauri, isTauri } from './device';

/** The shell command that opens the system print dialog with an html document (hub#2006). */
export const NATIVE_PRINT_COMMAND = 'print_document';

/**
 * Opens the system print dialog with `html`. Resolves once the shell has taken the document.
 *
 * Rejects when there is no dialog to open: outside the installed app, on a platform without native
 * print (the shell answers `native_print_unsupported`), or on a build old enough not to have the
 * command. The print door takes its usual route then — a rejection is never a printed page.
 */
export async function printDocumentNatively(html: string): Promise<void> {
  if (!isTauri()) throw new Error('native_print_unavailable');
  try {
    await invokeTauri<null>(NATIVE_PRINT_COMMAND, { html });
  } catch (cause) {
    throw new Error(`native_print_failed: ${String(cause)}`, { cause });
  }
}
