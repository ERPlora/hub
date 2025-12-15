/**
 * UI Helpers - Componentes reutilizables con Ionic
 *
 * Incluido globalmente en base.html
 *
 * Toast:
 *   showToast('Message', 'success');
 *   Toast.success('Saved!');
 *   Toast.error('Failed!');
 *
 * Alert:
 *   showAlert('Title', 'Message');
 *   showConfirm('Delete?', 'Are you sure?', () => doDelete());
 */

// ============================================================================
// TOAST NOTIFICATIONS
// ============================================================================

/**
 * Muestra un toast notification de Ionic
 *
 * @param {string} message - Mensaje a mostrar
 * @param {string} color - Color del toast (success, danger, warning, primary, etc.)
 * @param {number} duration - Duración en milisegundos (default: 2000)
 * @param {string} position - Posición del toast (top, bottom, middle) (default: 'bottom')
 * @returns {Promise<void>}
 */
async function showToast(message, color = 'primary', duration = 2000, position = 'bottom') {
    const toast = document.createElement('ion-toast');
    toast.message = message;
    toast.duration = duration;
    toast.color = color;
    toast.position = position;

    document.body.appendChild(toast);
    await toast.present();

    // Cleanup después de que se cierre
    toast.addEventListener('didDismiss', () => {
        toast.remove();
    });
}

/**
 * Shortcuts para tipos comunes de toast
 */
const Toast = {
    success: (message, duration) => showToast(message, 'success', duration),
    error: (message, duration) => showToast(message, 'danger', duration),
    warning: (message, duration) => showToast(message, 'warning', duration),
    info: (message, duration) => showToast(message, 'primary', duration),
};

// ============================================================================
// ALERT DIALOGS
// ============================================================================

/**
 * Muestra un alert dialog de Ionic
 *
 * @param {string} header - Título del alert
 * @param {string} message - Mensaje del alert
 * @param {string} buttonText - Texto del botón (default: 'OK')
 * @returns {Promise<void>}
 */
async function showAlert(header, message, buttonText = 'OK') {
    const alert = document.createElement('ion-alert');
    alert.header = header;
    alert.message = message;
    alert.buttons = [buttonText];

    document.body.appendChild(alert);
    await alert.present();

    alert.addEventListener('didDismiss', () => {
        alert.remove();
    });
}

/**
 * Muestra un confirm dialog de Ionic
 *
 * @param {string} header - Título del confirm
 * @param {string} message - Mensaje del confirm
 * @param {Function} onConfirm - Callback cuando se confirma
 * @param {string} confirmText - Texto del botón confirmar (default: 'Confirm')
 * @param {string} cancelText - Texto del botón cancelar (default: 'Cancel')
 * @returns {Promise<boolean>} - True si se confirmó, false si se canceló
 */
async function showConfirm(header, message, onConfirm, confirmText = 'Confirm', cancelText = 'Cancel') {
    return new Promise((resolve) => {
        const alert = document.createElement('ion-alert');
        alert.header = header;
        alert.message = message;
        alert.buttons = [
            {
                text: cancelText,
                role: 'cancel',
                handler: () => resolve(false)
            },
            {
                text: confirmText,
                handler: () => {
                    if (onConfirm) onConfirm();
                    resolve(true);
                }
            }
        ];

        document.body.appendChild(alert);
        alert.present();

        alert.addEventListener('didDismiss', () => {
            alert.remove();
        });
    });
}

/**
 * Shortcuts para tipos comunes de dialogs
 */
const Dialog = {
    alert: showAlert,
    confirm: showConfirm,
    error: (message) => showAlert('Error', message),
    success: (message) => showAlert('Success', message),
};

// ============================================================================
// LOADING INDICATOR
// ============================================================================

let activeLoading = null;

/**
 * Muestra un loading indicator
 *
 * @param {string} message - Mensaje a mostrar (default: 'Loading...')
 * @returns {Promise<HTMLIonLoadingElement>}
 */
async function showLoading(message = 'Loading...') {
    // Cerrar loading anterior si existe
    if (activeLoading) {
        await activeLoading.dismiss();
    }

    const loading = document.createElement('ion-loading');
    loading.message = message;
    loading.spinner = 'crescent';

    document.body.appendChild(loading);
    await loading.present();

    activeLoading = loading;
    return loading;
}

/**
 * Oculta el loading indicator activo
 */
async function hideLoading() {
    if (activeLoading) {
        await activeLoading.dismiss();
        activeLoading.remove();
        activeLoading = null;
    }
}

// ============================================================================
// EXPORTS
// ============================================================================

// Export para uso en módulos ES6 (opcional)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { showToast, Toast, showAlert, showConfirm, Dialog, showLoading, hideLoading };
}
