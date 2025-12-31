/**
 * UI Helpers - Componentes reutilizables con Ionic
 *
 * Incluido globalmente en base.html
 *
 * Toast (simple):
 *   showToast('Message', 'success');
 *   Toast.success('Saved!');
 *   Toast.error('Failed!');
 *
 * Notification (con título):
 *   Notify.success('Guardado', 'El producto se guardó correctamente');
 *   Notify.error('Error', 'No se pudo conectar al servidor');
 *   Notify.warning('Atención', 'Stock bajo en 5 productos');
 *   Notify.info('Info', 'Procesando...');
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
// NOTIFICATION (TOAST CON TÍTULO)
// ============================================================================

/**
 * Muestra una notificación toast con título y mensaje
 *
 * @param {Object} options - Opciones de la notificación
 * @param {string} options.title - Título de la notificación
 * @param {string} options.message - Mensaje de la notificación
 * @param {string} options.type - Tipo: 'success', 'warning', 'danger', 'info'
 * @param {number} options.duration - Duración en ms (default: 3000, 0 si showClose)
 * @param {string} options.position - Posición: 'top', 'bottom', 'middle'
 * @param {boolean} options.showClose - Mostrar botón de cerrar (default: true)
 * @returns {Promise<HTMLIonToastElement>}
 */
async function showNotification({
    title = '',
    message = '',
    type = 'info',
    duration = 3000,
    position = 'top',
    showClose = true
} = {}) {
    const colorMap = {
        success: 'success',
        warning: 'warning',
        danger: 'danger',
        error: 'danger',
        info: 'primary'
    };

    const iconMap = {
        success: 'checkmark-circle-outline',
        warning: 'warning-outline',
        danger: 'alert-circle-outline',
        error: 'alert-circle-outline',
        info: 'information-circle-outline'
    };

    const toast = document.createElement('ion-toast');
    toast.header = title;
    toast.message = message;
    toast.duration = showClose ? 0 : duration;
    toast.color = colorMap[type] || 'primary';
    toast.position = position;
    toast.icon = iconMap[type];

    if (showClose) {
        toast.buttons = [{
            icon: 'close-outline',
            role: 'cancel'
        }];
    }

    document.body.appendChild(toast);
    await toast.present();

    toast.addEventListener('didDismiss', () => toast.remove());

    return toast;
}

/**
 * Shortcuts para notificaciones con título
 */
const Notify = {
    success: (title, message, opts = {}) => showNotification({ title, message, type: 'success', ...opts }),
    error: (title, message, opts = {}) => showNotification({ title, message, type: 'danger', ...opts }),
    warning: (title, message, opts = {}) => showNotification({ title, message, type: 'warning', ...opts }),
    info: (title, message, opts = {}) => showNotification({ title, message, type: 'info', ...opts }),
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
    module.exports = { showToast, Toast, showNotification, Notify, showAlert, showConfirm, Dialog, showLoading, hideLoading };
}

// Make available globally for inline handlers
window.showToast = showToast;
window.Toast = Toast;
window.Notify = Notify;
window.Dialog = Dialog;
window.showAlert = showAlert;
window.showConfirm = showConfirm;
window.showLoading = showLoading;
window.hideLoading = hideLoading;
