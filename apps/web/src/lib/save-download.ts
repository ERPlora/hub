// The ONE way a file leaves the till: a document from `/files`, a backup export, an invoice PDF.
//
// This is the sibling of `open-external.ts` and it exists for the other half of the same defect.
// ADR-0255 taught the installed app to LEAVE for the system browser and deliberately left three
// `window.open` calls behind (hub#480), because none of them was about going somewhere — all three
// were about saving a file, and a browser is no answer for that: these bytes are fetched by THIS
// page with the hub session attached, and a separate program has no session to fetch them with.
//
// So the page keeps the bytes and, where there is one, the shell keeps the disk:
//  - **Browser / PWA** → the download manager, through the usual `<a download>` on an object URL.
//    Exactly what four screens each had their own copy of, now written once.
//  - **Installed app** → the shell writes the file and answers with the PATH, which the caller
//    shows. That is not decoration: inside the app there is no download shelf, no notification and
//    no Downloads button, so the path is the only trace the user gets that the file arrived.
//
// Why the anchor is not simply left to work inside the app: on **Android** it never does. wry
// registers no `DownloadListener` on that platform at all, so `<a download>` on a `blob:` is a
// press that does nothing, forever — the very failure ADR-0255 set out to end. On the desktop wry
// does have a default handler, but it writes the file in silence, and a till user has no browser
// chrome to go looking in.
//
// And on a phone or tablet the shell REFUSES rather than pretends: there the folder the OS calls
// Downloads belongs to the app, not to the user (Android closed `Android/data` to every file
// manager in version 11), so "saved to …" would be a lie with a path attached. That refusal is the
// one the user can act on, and it gets its own sentence.
import { invokeTauri, isTauri } from './device';

/** The shell command that writes a file where the user will find it (hub#480). */
export const SAVE_DOWNLOAD_COMMAND = 'save_download';

/**
 * The shell's way of saying *this device has no Downloads folder the user could open*. It travels
 * as the rejection value of the `invoke`, because `ShellError` serializes to its own message.
 */
const DOWNLOADS_UNREACHABLE = 'downloads_unreachable';

/** Largest slice of bytes turned into characters at once — a whole file would blow the arg limit. */
const BASE64_CHUNK = 0x8000;

/**
 * The file could not be saved. Callers must turn this into something the user can read: a button
 * that does nothing when pressed is the defect this module exists to end.
 */
export class SaveDownloadError extends Error {
  constructor(readonly fileName: string, options?: { cause?: unknown }) {
    super(`save_download_failed: ${fileName}`, options);
    this.name = 'SaveDownloadError';
  }
}

/**
 * The i18n key that says what happened, in the user's own words.
 *
 * Two sentences, because only one of them is actionable. *No place to save* is a phone or a tablet
 * running the installed app: the file would land somewhere no file manager opens, and the way out
 * is to open the business in a browser. Everything else — a refused name, a full disk, an app old
 * enough not to have the command at all — is a plain failure.
 */
export function saveDownloadMessageKey(error: unknown): 'download.noPlaceToSave' | 'download.failed' {
  const cause = error instanceof SaveDownloadError ? error.cause : undefined;
  return String(cause ?? '').includes(DOWNLOADS_UNREACHABLE)
    ? 'download.noPlaceToSave'
    : 'download.failed';
}

/** The bytes as the `invoke` boundary can carry them: base64, not a JSON array of numbers. */
function toBase64(bytes: Uint8Array): string {
  let binary = '';
  for (let at = 0; at < bytes.length; at += BASE64_CHUNK) {
    binary += String.fromCharCode(...bytes.subarray(at, at + BASE64_CHUNK));
  }
  return btoa(binary);
}

/**
 * Saves `blob` under `name` somewhere the user can find it.
 *
 * Resolves with the absolute path when the installed app wrote the file — the caller SHOWS it — and
 * with `null` in a browser, where the download manager has already told the user and we have
 * nothing to add.
 *
 * Rejects with {@link SaveDownloadError} when it could not be done: this device has no Downloads
 * folder the user could open, the name was refused, the write failed, or the app is an older build
 * with no `save_download` command at all. That last one matters — a till that has not updated yet
 * still cannot save, but it now says so instead of ignoring the press.
 */
export async function saveDownload(name: string, blob: Blob): Promise<string | null> {
  if (isTauri()) {
    const bytes = new Uint8Array(await blob.arrayBuffer());
    let saved: { path?: string } | null;
    try {
      saved = await invokeTauri<{ path?: string }>(SAVE_DOWNLOAD_COMMAND, {
        name,
        dataBase64: toBase64(bytes),
      });
    } catch (cause) {
      throw new SaveDownloadError(name, { cause });
    }
    // A save nobody can point at is not a save: without a path there is nothing to tell the user,
    // and «saved» with no «where» is how a file gets lost inside an app with no download shelf.
    if (!saved?.path) throw new SaveDownloadError(name, { cause: 'download_without_a_path' });
    return saved.path;
  }

  const objectUrl = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = objectUrl;
  anchor.download = name;
  document.body.appendChild(anchor);
  anchor.click();
  anchor.remove();
  // The object URL has to outlive the click that started the download, and nothing tells us when it
  // is done. A second is what every one of the four screens this replaces already waited.
  window.setTimeout(() => URL.revokeObjectURL(objectUrl), 1_000);
  return null;
}
