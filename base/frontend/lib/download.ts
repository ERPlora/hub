// The one way a file the page holds leaves the Hub (hub#1041; the old hub's `save-download.ts`): the
// representation model of VeriFactu, a backup export, a file of Files, a CSV of a list, the API's document.
//
// - **A browser** gets it through a temporary link on an object URL, never added to the page; its own downloads say
//   it arrived, so nothing more is said here.
// - **The installed app** does nothing with that link (Android's webview has no download listener at all; the
//   desktop's writes the file without a word), so the bytes go to the app's `save_download` (ERPlora/app,
//   HUB_APP-F30), which writes them to the person's Downloads and answers where. That place is said on screen
//   («Saved to Download/anexo-i.pdf»): inside the app there is no download shelf, and nothing else would tell.
//   A refusal is said too, by its reason; an answer without a place is a failure, never «saved» without where.
import { isOlderAppRefusal, nativeBridge, toastError, toastSuccess } from '@erplora/ui/shell';

import { bytesToBase64 } from './data';

/** The app's command that writes a file into Downloads (ERPlora/app `src-tauri/src/lib.rs`). */
export const SAVE_DOWNLOAD_COMMAND = 'save_download';

/** Why the app did not save the file; each one is a sentence under `base.download.refusal`. */
type DownloadRefusal = 'unreachable' | 'unlinked' | 'outdated' | 'failed';

type Translate = (key: string, values?: Record<string, unknown>) => string;

function refusalOf(answer: string): DownloadRefusal {
  // A phone or a tablet with no Downloads folder the person could open: the one refusal they can act on.
  if (answer === 'downloads_unreachable') return 'unreachable';
  if (answer === 'not_the_linked_hub') return 'unlinked';
  // An app from before the command (Tauri's own answers: the ACL knows no such permission, or no such command).
  if (isOlderAppRefusal(answer)) return 'outdated';
  return 'failed';
}

function inTheBrowser(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

/**
 * Saves `blob` as `filename` where the person will find it, and says so where nothing else would. Resolves `true`
 * when the file was handed over (the browser's downloads, or the app's Downloads, whose place a toast says) and
 * `false` when the installed app could not save it (a toast says why); it never rejects.
 */
export async function saveFile(filename: string, blob: Blob, t: Translate, win: object = window): Promise<boolean> {
  const bridge = nativeBridge(win);
  if (!bridge) {
    inTheBrowser(filename, blob);
    return true;
  }
  let refusal: DownloadRefusal;
  try {
    const dataBase64 = bytesToBase64(new Uint8Array(await blob.arrayBuffer()));
    const saved = (await bridge.invoke(SAVE_DOWNLOAD_COMMAND, { name: filename, dataBase64 })) as { path?: unknown } | null;
    if (typeof saved?.path === 'string' && saved.path !== '') {
      void toastSuccess(t('base.download.savedTo', { path: saved.path }));
      return true;
    }
    console.error('hub: save_download answered no place', saved);
    refusal = 'failed';
  } catch (error) {
    console.error('hub: save_download refused', error);
    refusal = refusalOf(error instanceof Error ? error.message : String(error));
  }
  void toastError(t(`base.download.refusal.${refusal}`));
  return false;
}
