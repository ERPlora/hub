// Toast global de feedback de acciones (éxito / error / info). Centraliza lo que hoy cada página
// reinventaba con su propio `<ion-toast>` (Marketplace/Files/System). Usa el `toastController` de
// Ionic (imperativo): encola/apila solo, no necesita un `<ion-toast>` en la plantilla.
//
// Además `bootActionFeedback()` engancha UN listener global a los eventos que `ok-data-table`
// (OutfitKit) ya emite al exportar/importar CSV (`csvExport`/`csvImport`, con `bubbles+composed`
// → cruzan el Shadow DOM del WC del módulo hasta el shell). Así CUALQUIER tabla del Hub (productos,
// CRUDs…) muestra confirmación de descarga/importación sin tocar cada módulo.
import { toastController } from '@ionic/vue';

export type ToastColor = 'success' | 'danger' | 'medium' | 'primary' | 'warning';

/** Muestra un toast global. `duration` en ms (0 = persistente con botón cerrar). */
export async function toast(message: string, color: ToastColor = 'medium', duration = 2600): Promise<void> {
  const t = await toastController.create({
    message,
    color,
    duration,
    position: 'bottom',
    buttons: [{ text: 'OK', role: 'cancel' }],
  });
  await t.present();
}

export const toastSuccess = (message: string): Promise<void> => toast(message, 'success');
export const toastError = (message: string): Promise<void> => toast(message, 'danger', 4500);
export const toastInfo = (message: string): Promise<void> => toast(message, 'primary');

/**
 * Feedback global de acciones de OutfitKit que burbujean al shell. Idempotente; se llama una vez
 * en el boot (main.ts). Un único listener cubre todas las `ok-data-table` del Hub.
 */
let booted = false;
export function bootActionFeedback(): void {
  if (booted || typeof window === 'undefined') return;
  booted = true;

  const rowsOf = (e: Event): number | undefined =>
    (e as CustomEvent<{ rows?: number }>).detail?.rows;
  const filas = (n: number | undefined): string =>
    n == null ? '' : ` · ${n} ${n === 1 ? 'fila' : 'filas'}`;

  window.addEventListener('csvExport', (e) => {
    void toastSuccess(`CSV exportado${filas(rowsOf(e))}`);
  });
  window.addEventListener('csvImport', (e) => {
    void toastSuccess(`CSV importado${filas(rowsOf(e))}`);
  });
}
