/**
 * Image Upload Component - Helper Functions
 * Provides utilities for image upload with preview
 */

/**
 * Initialize image upload with preview
 * @param {string} inputId - ID of the file input element
 * @param {string} previewId - ID of the image preview element (optional)
 * @param {string} labelId - ID of the label element to update with filename (optional)
 */
function initImageUpload(inputId, previewId = null, labelId = null) {
    const input = document.getElementById(inputId);

    if (!input) {
        console.warn(`[ImageUpload] Input element '${inputId}' not found`);
        return;
    }

    input.addEventListener('change', function(e) {
        const file = e.target.files[0];

        if (!file) return;

        // Validate file type
        if (!file.type.startsWith('image/')) {
            showErrorAlert('Por favor selecciona un archivo de imagen válido');
            input.value = '';
            return;
        }

        // Validate file size (2MB max)
        const maxSize = 2 * 1024 * 1024; // 2MB in bytes
        if (file.size > maxSize) {
            showErrorAlert('La imagen es demasiado grande. Tamaño máximo: 2MB');
            input.value = '';
            return;
        }

        // Update label with filename if labelId provided
        if (labelId) {
            const label = document.getElementById(labelId);
            if (label) {
                label.textContent = file.name;
            }
        }

        // Show preview if preview element exists
        if (previewId) {
            const preview = document.getElementById(previewId);
            if (preview) {
                const reader = new FileReader();
                reader.onload = function(e) {
                    preview.src = e.target.result;
                    preview.style.display = 'block';
                };
                reader.readAsDataURL(file);
            }
        }

        console.log(`[ImageUpload] File selected: ${file.name} (${(file.size / 1024).toFixed(2)} KB)`);
    });
}

/**
 * Clear image upload input and preview
 * @param {string} inputId - ID of the file input element
 * @param {string} labelId - ID of the label element
 * @param {string} originalLabel - Original label text
 * @param {string} previewId - ID of the preview element (optional)
 */
function clearImageUpload(inputId, labelId, originalLabel, previewId = null) {
    const input = document.getElementById(inputId);
    const label = document.getElementById(labelId);

    if (input) input.value = '';
    if (label) label.textContent = originalLabel;

    if (previewId) {
        const preview = document.getElementById(previewId);
        if (preview) {
            preview.src = '';
            preview.style.display = 'none';
        }
    }
}

// Export functions to window for global access
if (typeof window !== 'undefined') {
    window.initImageUpload = initImageUpload;
    window.clearImageUpload = clearImageUpload;
}
