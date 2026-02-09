/**
 * UI Helpers - Reusable components with UX library
 *
 * Included globally in base.html
 *
 * Toast (simple):
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
 * Show a toast notification using UX toast-item component.
 *
 * @param {string} message - Message to display
 * @param {string} color - Color: success, error, warning, primary (default: 'primary')
 * @param {number} duration - Duration in ms (default: 2000)
 */
function showToast(message, color = 'primary', duration = 2000) {
    const container = document.getElementById('toast-container');
    if (!container) return;

    const item = document.createElement('div');
    item.className = 'toast-item color-' + color;
    item.textContent = message;

    container.appendChild(item);

    // Auto-dismiss
    setTimeout(() => {
        item.style.opacity = '0';
        item.style.transform = 'translateY(0.5rem)';
        item.style.transition = 'opacity 0.3s, transform 0.3s';
        setTimeout(() => item.remove(), 300);
    }, duration);
}

/**
 * Shortcuts for common toast types
 */
const Toast = {
    success: (message, duration) => showToast(message, 'success', duration),
    error: (message, duration) => showToast(message, 'error', duration || 3000),
    warning: (message, duration) => showToast(message, 'warning', duration),
    info: (message, duration) => showToast(message, 'primary', duration),
};

// ============================================================================
// ALERT / CONFIRM DIALOGS (native)
// ============================================================================

function showAlert(header, message) {
    alert(header + '\n\n' + message);
}

function showConfirm(header, message, onConfirm) {
    if (confirm(header + '\n\n' + message)) {
        if (onConfirm) onConfirm();
        return true;
    }
    return false;
}

const Dialog = {
    alert: showAlert,
    confirm: showConfirm,
    error: (message) => showAlert('Error', message),
    success: (message) => showAlert('Success', message),
};

// ============================================================================
// EXPORTS
// ============================================================================

if (typeof module !== 'undefined' && module.exports) {
    module.exports = { showToast, Toast, showAlert, showConfirm, Dialog };
}

window.showToast = showToast;
window.Toast = Toast;
window.Dialog = Dialog;
window.showAlert = showAlert;
window.showConfirm = showConfirm;
