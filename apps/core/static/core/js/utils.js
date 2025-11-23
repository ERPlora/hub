/**
 * Utils Component - JavaScript Utilities
 * Provides common utility functions for CSRF tokens and alert modals
 */

/**
 * Get cookie value by name (used for CSRF token)
 * @param {string} name - Cookie name
 * @returns {string|null} Cookie value or null if not found
 */
function getCookie(name) {
    let cookieValue = null;
    if (document.cookie && document.cookie !== '') {
        const cookies = document.cookie.split(';');
        for (let i = 0; i < cookies.length; i++) {
            const cookie = cookies[i].trim();
            if (cookie.substring(0, name.length + 1) === (name + '=')) {
                cookieValue = decodeURIComponent(cookie.substring(name.length + 1));
                break;
            }
        }
    }
    return cookieValue;
}

/**
 * Show success alert modal
 * @param {string} message - Success message to display
 * @param {string} [header='Éxito'] - Modal header text
 */
async function showSuccessAlert(message, header = 'Éxito') {
    const alert = document.createElement('ion-alert');
    alert.header = header;
    alert.message = message;
    alert.buttons = ['OK'];

    document.body.appendChild(alert);
    await alert.present();
}

/**
 * Show error alert modal
 * @param {string} message - Error message to display
 * @param {string} [header='Error'] - Modal header text
 */
async function showErrorAlert(message, header = 'Error') {
    const alert = document.createElement('ion-alert');
    alert.header = header;
    alert.message = message;
    alert.buttons = ['OK'];
    alert.cssClass = 'alert-danger';

    document.body.appendChild(alert);
    await alert.present();
}

/**
 * Show confirmation alert modal
 * @param {string} message - Confirmation message
 * @param {string} [header='Confirmar'] - Modal header text
 * @param {string} [confirmText='Confirmar'] - Confirm button text
 * @param {string} [cancelText='Cancelar'] - Cancel button text
 * @returns {Promise<boolean>} True if confirmed, false if cancelled
 */
async function showConfirmAlert(message, header = 'Confirmar', confirmText = 'Confirmar', cancelText = 'Cancelar') {
    return new Promise((resolve) => {
        const alert = document.createElement('ion-alert');
        alert.header = header;
        alert.message = message;
        alert.buttons = [
            {
                text: cancelText,
                role: 'cancel',
                handler: () => {
                    resolve(false);
                }
            },
            {
                text: confirmText,
                role: 'confirm',
                handler: () => {
                    resolve(true);
                }
            }
        ];

        document.body.appendChild(alert);
        alert.present();
    });
}

/**
 * Show toast notification
 * @param {string} message - Toast message
 * @param {string} [color='primary'] - Toast color (primary, success, warning, danger)
 * @param {number} [duration=2000] - Duration in milliseconds
 */
async function showToast(message, color = 'primary', duration = 2000) {
    const toast = document.createElement('ion-toast');
    toast.message = message;
    toast.duration = duration;
    toast.color = color;
    toast.position = 'top';

    document.body.appendChild(toast);
    await toast.present();
}

/**
 * Show loading spinner
 * @param {string} [message='Cargando...'] - Loading message
 * @returns {Promise<HTMLIonLoadingElement>} Loading element (call dismiss() to hide)
 */
async function showLoading(message = 'Cargando...') {
    const loading = document.createElement('ion-loading');
    loading.message = message;
    loading.spinner = 'crescent';

    document.body.appendChild(loading);
    await loading.present();
    return loading;
}

/**
 * Hide loading spinner
 * @param {HTMLIonLoadingElement} loading - Loading element returned from showLoading()
 */
async function hideLoading(loading) {
    if (loading) {
        await loading.dismiss();
    }
}

/**
 * Show action sheet (contextual menu)
 * @param {string} header - Action sheet header
 * @param {Array} buttons - Array of button objects with text, role, icon, handler
 * @returns {Promise<any>} Selected button result
 *
 * Example:
 * const result = await showActionSheet('Opciones', [
 *   { text: 'Editar', icon: 'create-outline', handler: () => console.log('Edit') },
 *   { text: 'Eliminar', icon: 'trash-outline', role: 'destructive', handler: () => console.log('Delete') },
 *   { text: 'Cancelar', role: 'cancel' }
 * ]);
 */
async function showActionSheet(header, buttons) {
    return new Promise((resolve) => {
        const actionSheet = document.createElement('ion-action-sheet');
        actionSheet.header = header;
        actionSheet.buttons = buttons.map(btn => ({
            ...btn,
            handler: () => {
                if (btn.handler) btn.handler();
                resolve(btn);
            }
        }));

        document.body.appendChild(actionSheet);
        actionSheet.present();
    });
}

/**
 * Show modal with custom HTML content
 * @param {string} htmlContent - HTML content to display in modal
 * @param {Object} [options] - Modal options
 * @param {string} [options.cssClass] - Custom CSS class
 * @param {boolean} [options.showBackdrop=true] - Show backdrop
 * @param {boolean} [options.backdropDismiss=true] - Dismiss on backdrop click
 * @returns {Promise<HTMLIonModalElement>} Modal element (call dismiss() to close)
 *
 * Example with form:
 * const modal = await showModal(`
 *   <ion-header>
 *     <ion-toolbar>
 *       <ion-title>Nuevo Producto</ion-title>
 *       <ion-buttons slot="end">
 *         <ion-button onclick="closeModal()">Cerrar</ion-button>
 *       </ion-buttons>
 *     </ion-toolbar>
 *   </ion-header>
 *   <ion-content class="ion-padding">
 *     <form id="productForm">
 *       <ion-item>
 *         <ion-label position="floating">Nombre</ion-label>
 *         <ion-input type="text" name="name" required></ion-input>
 *       </ion-item>
 *       <ion-item>
 *         <ion-label position="floating">Precio</ion-label>
 *         <ion-input type="number" name="price" required></ion-input>
 *       </ion-item>
 *       <ion-button expand="block" type="submit">Guardar</ion-button>
 *     </form>
 *   </ion-content>
 * `);
 *
 * // To close from inside the modal:
 * window.closeModal = () => modal.dismiss();
 */
async function showModal(htmlContent, options = {}) {
    const modal = document.createElement('ion-modal');

    // Set options
    if (options.cssClass) modal.cssClass = options.cssClass;
    if (options.showBackdrop !== undefined) modal.showBackdrop = options.showBackdrop;
    if (options.backdropDismiss !== undefined) modal.backdropDismiss = options.backdropDismiss;

    // Create content wrapper
    const wrapper = document.createElement('div');
    wrapper.innerHTML = htmlContent;
    modal.appendChild(wrapper);

    document.body.appendChild(modal);
    await modal.present();
    return modal;
}

/**
 * Show popover with custom content
 * @param {string} htmlContent - HTML content to display
 * @param {Event} event - Event object from the trigger element
 * @param {Object} [options] - Popover options
 * @returns {Promise<HTMLIonPopoverElement>} Popover element
 *
 * Example:
 * <ion-button onclick="showUserPopover(event)">Info</ion-button>
 *
 * async function showUserPopover(event) {
 *   await showPopover(`
 *     <ion-list>
 *       <ion-item button>Perfil</ion-item>
 *       <ion-item button>Configuración</ion-item>
 *       <ion-item button>Cerrar Sesión</ion-item>
 *     </ion-list>
 *   `, event);
 * }
 */
async function showPopover(htmlContent, event, options = {}) {
    const popover = document.createElement('ion-popover');
    popover.event = event;

    if (options.cssClass) popover.cssClass = options.cssClass;
    if (options.dismissOnSelect !== undefined) popover.dismissOnSelect = options.dismissOnSelect;

    const wrapper = document.createElement('div');
    wrapper.innerHTML = htmlContent;
    popover.appendChild(wrapper);

    document.body.appendChild(popover);
    await popover.present();
    return popover;
}

// Export functions to window for global access
if (typeof window !== 'undefined') {
    window.getCookie = getCookie;
    window.showSuccessAlert = showSuccessAlert;
    window.showErrorAlert = showErrorAlert;
    window.showConfirmAlert = showConfirmAlert;
    window.showToast = showToast;
    window.showLoading = showLoading;
    window.hideLoading = hideLoading;
    window.showActionSheet = showActionSheet;
    window.showModal = showModal;
    window.showPopover = showPopover;
}
