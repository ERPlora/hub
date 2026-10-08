// Global action feedback (success / error / info). Centralises what every page used to reinvent
// with its own `<ion-toast>` (Apps/Files/System). It uses Ionic's imperative `toastController`:
// it queues and stacks on its own, no `<ion-toast>` in any template.
//
// `bootActionFeedback()` also hooks ONE global listener to the events `ok-data-table` (OutfitKit)
// already emits when exporting/importing CSV (`csvExport`/`csvImport`, `bubbles+composed` → they
// cross the module WC's Shadow DOM up to the shell). That way EVERY table in the Hub (products,
// CRUDs…) confirms the download/the file read without touching a single module.
import { toastController } from '@ionic/vue';
import { i18n } from '../i18n';

export type ToastColor = 'success' | 'danger' | 'medium' | 'primary' | 'warning';

/**
 * Shows a global toast. `duration` in ms (0 = sticky, closed by its button). `id` names it so
 * {@link dismissToast} can withdraw it once what it says stops being true.
 */
export async function toast(
  message: string,
  color: ToastColor = 'medium',
  duration = 2600,
  id?: string,
): Promise<void> {
  const t = await toastController.create({
    message,
    color,
    duration,
    position: 'bottom',
    buttons: [{ text: 'OK', role: 'cancel' }],
    ...(id ? { id } : {}),
  });
  await t.present();
}

/**
 * Withdraws the toast shown with `id`. `false` when there is none on screen any more (it timed out
 * or was tapped away): Ionic rejects that case, and a notice already gone is not a failure.
 */
export async function dismissToast(id: string): Promise<boolean> {
  return toastController.dismiss(undefined, undefined, id).catch(() => false);
}

export const toastSuccess = (message: string): Promise<void> => toast(message, 'success');
export const toastError = (message: string): Promise<void> => toast(message, 'danger', 4500);
export const toastInfo = (message: string): Promise<void> => toast(message, 'primary');

/** Guard of `bootActionFeedback()`: the listeners are hooked once per page load. */
let booted = false;

/**
 * How many rows a CSV event of `ok-data-table` carries, or `undefined` when it cannot be known.
 *
 * The same key travels with TWO shapes (inventory#90): `csvExport` emits `{ rows: <how many> }`
 * while `csvImport` emits `{ headers, rows: [{…}, {…}] }` — the rows themselves. Dropping that
 * list into a sentence turned it into `[object Object]` once per row, which is what whoever
 * imported their catalogue actually read. Anything that is neither a list nor a countable number
 * is not counted: a figure that cannot be stated is not shown.
 */
function csvRowCount(e: Event): number | undefined {
  const rows = (e as CustomEvent<{ rows?: unknown }>).detail?.rows;
  if (Array.isArray(rows)) return rows.length;
  if (typeof rows === 'number' && Number.isFinite(rows) && rows >= 0) return Math.trunc(rows);
  return undefined;
}

/**
 * Global feedback for the OutfitKit actions that bubble up to the shell. Idempotent; called once
 * at boot (main.ts). A single listener covers every `ok-data-table` in the Hub.
 */
export function bootActionFeedback(): void {
  if (booted || typeof window === 'undefined') return;
  booted = true;

  // `t` with a runtime key: the catalogue is typed by its schema and the key is picked here
  // depending on whether there is a count to say.
  const t = i18n.global.t as unknown as (key: string, named?: Record<string, unknown>) => string;

  const announce = (plain: string, withRows: string, e: Event): void => {
    const n = csvRowCount(e);
    void toastSuccess(n === undefined ? t(plain) : t(withRows, { n }));
  };

  window.addEventListener('csvExport', (e) => {
    announce('actionFeedback.csvExported', 'actionFeedback.csvExportedRows', e);
  });
  // The import notice is about the FILE BEING READ, not about rows being created: when it fires
  // nothing exists yet — the module opens its preview ("nothing is created until you confirm") and
  // shows its own report with what really went in. Promising creations here would lie to whoever
  // then cancels that preview.
  window.addEventListener('csvImport', (e) => {
    announce('actionFeedback.csvImported', 'actionFeedback.csvImportedRows', e);
  });
}
