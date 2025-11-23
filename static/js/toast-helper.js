/**
 * Toast Helper - Notificaciones reutilizables con Ionic Toast
 *
 * Usage:
 * <script src="{% static 'components/toast_helper/toast-helper.js' %}"></script>
 *
 * showToast('Operation successful!', 'success');
 * showToast('Error occurred', 'danger', 5000);
 */

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

// Export para uso en módulos ES6 (opcional)
if (typeof module !== 'undefined' && module.exports) {
    module.exports = { showToast, Toast };
}
