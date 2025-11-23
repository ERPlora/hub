/**
 * Data Table Component - Helper Functions
 * Provides functionality for table with search, pagination, and CRUD modals
 */

/**
 * Create data table mixin for Alpine.js components
 * Usage:
 *   function myApp() {
 *       return {
 *           ...createDataTableMixin(),
 *           // your specific implementations
 *           async loadData() {
 *               const response = await fetch(`/api/items/?page=${this.currentPage}&per_page=${this.perPage}&search=${this.searchQuery}`);
 *               const data = await response.json();
 *               this.items = data.results;
 *               this.total = data.total;
 *           },
 *           async saveItem() {
 *               // Your save logic here
 *           },
 *           async deleteItem(item) {
 *               // Your delete logic here
 *           }
 *       }
 *   }
 */
function createDataTableMixin() {
    return {
        // Table data
        items: [],

        // Search state
        searchQuery: '',

        // Pagination state
        currentPage: 1,
        perPage: 10,
        total: 0,

        // Modal state
        showCreateModal: false,
        showEditModal: false,
        saving: false,
        editingId: null,

        // Form data (override in parent component with specific fields)
        form: {},

        // Computed property for total pages
        get totalPages() {
            return Math.ceil(this.total / this.perPage) || 1;
        },

        // Search function (debounced)
        search() {
            // Reset to first page on search
            this.currentPage = 1;
            // Call loadData (must be implemented in parent component)
            if (typeof this.loadData === 'function') {
                this.loadData();
            }
        },

        // Navigate to previous page
        prevPage() {
            if (this.currentPage > 1) {
                this.currentPage--;
                if (typeof this.loadData === 'function') {
                    this.loadData();
                }
            }
        },

        // Navigate to next page
        nextPage() {
            if (this.currentPage < this.totalPages) {
                this.currentPage++;
                if (typeof this.loadData === 'function') {
                    this.loadData();
                }
            }
        },

        // Reset to first page
        resetPagination() {
            this.currentPage = 1;
            this.searchQuery = '';
        },

        // Modal methods
        openCreateModal() {
            this.resetForm();
            this.editingId = null;
            this.showCreateModal = true;
        },

        openEditModal(item) {
            this.editingId = item.id;
            // Copy item data to form (shallow copy)
            this.form = { ...item };
            this.showEditModal = true;
        },

        closeModal() {
            this.showCreateModal = false;
            this.showEditModal = false;
            this.resetForm();
            this.editingId = null;
            this.saving = false;
        },

        // Reset form (override in parent if needed)
        resetForm() {
            this.form = {};
        },

        // Import/Export methods
        async importData() {
            // Create file input element
            const input = document.createElement('input');
            input.type = 'file';
            input.accept = '.csv,.xlsx,.xls';

            input.onchange = async (e) => {
                const file = e.target.files[0];
                if (!file) return;

                // Show loading toast
                await this.showToast('Importing file...', 'primary');

                const formData = new FormData();
                formData.append('file', file);

                try {
                    // Get import URL from component (must be set)
                    const importUrl = this.getImportUrl ? this.getImportUrl() : null;
                    if (!importUrl) {
                        await this.showToast('Import URL not configured', 'danger');
                        return;
                    }

                    const response = await fetch(importUrl, {
                        method: 'POST',
                        headers: {
                            'X-CSRFToken': this.getCSRFToken()
                        },
                        body: formData
                    });

                    const result = await response.json();

                    if (response.ok && result.success) {
                        await this.showToast(
                            result.message || 'Import completed successfully',
                            'success'
                        );
                        await this.loadData();
                    } else {
                        await this.showToast(
                            result.message || 'Import failed',
                            'danger'
                        );
                    }
                } catch (error) {
                    console.error('Import error:', error);
                    await this.showToast('Error importing file', 'danger');
                }
            };

            // Trigger file picker
            input.click();
        },

        async exportData() {
            try {
                // Get export URL from component (must be set)
                const exportUrl = this.getExportUrl ? this.getExportUrl() : null;
                if (!exportUrl) {
                    await this.showToast('Export URL not configured', 'danger');
                    return;
                }

                // Show loading toast
                await this.showToast('Generating export...', 'primary');

                // Build URL with search query if present
                const url = new URL(exportUrl, window.location.origin);
                if (this.searchQuery) {
                    url.searchParams.append('search', this.searchQuery);
                }

                const response = await fetch(url.toString(), {
                    method: 'GET',
                    headers: {
                        'X-CSRFToken': this.getCSRFToken()
                    }
                });

                if (response.ok) {
                    // Get filename from Content-Disposition header or use default
                    const contentDisposition = response.headers.get('Content-Disposition');
                    let filename = 'export.csv';
                    if (contentDisposition) {
                        const matches = /filename[^;=\n]*=((['"]).*?\2|[^;\n]*)/.exec(contentDisposition);
                        if (matches != null && matches[1]) {
                            filename = matches[1].replace(/['"]/g, '');
                        }
                    }

                    // Download file
                    const blob = await response.blob();
                    const downloadUrl = window.URL.createObjectURL(blob);
                    const a = document.createElement('a');
                    a.href = downloadUrl;
                    a.download = filename;
                    document.body.appendChild(a);
                    a.click();
                    window.URL.revokeObjectURL(downloadUrl);
                    document.body.removeChild(a);

                    await this.showToast('Export completed successfully', 'success');
                } else {
                    const result = await response.json();
                    await this.showToast(
                        result.message || 'Export failed',
                        'danger'
                    );
                }
            } catch (error) {
                console.error('Export error:', error);
                await this.showToast('Error exporting data', 'danger');
            }
        },

        // Helper: Get CSRF token
        getCSRFToken() {
            return document.querySelector('[name=csrfmiddlewaretoken]')?.value || '';
        },

        // Helper: Show toast notification
        async showToast(message, color = 'primary') {
            const toast = document.createElement('ion-toast');
            toast.message = message;
            toast.duration = 3000;
            toast.color = color;
            toast.position = 'top';
            document.body.appendChild(toast);
            await toast.present();
        },

        // Helper: Show confirmation alert
        async showConfirmAlert(header, message, confirmText = 'Confirm', cancelText = 'Cancel') {
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
                        role: 'destructive',
                        handler: () => resolve(true)
                    }
                ];
                document.body.appendChild(alert);
                alert.present();
            });
        }
    };
}

// Export function to window for global access
if (typeof window !== 'undefined') {
    window.createDataTableMixin = createDataTableMixin;
}
